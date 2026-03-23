from __future__ import annotations

import asyncio
import contextlib
import json
import re
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import HTTPException

from app.core.config import Settings
from app.schemas.blog import BlogResultResponse
from app.schemas.jobs import CreateBlogJobRequest, JobCreatedResponse, JobDetailResponse, JobMeta
from app.services.jobs import JobService
from app.storage.s3 import S3Storage


IMAGE_REGEX = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")
RAW_IMAGE_REGEX = re.compile(r"\bimgs\/[^\s)\"']+")


class BlogService:
    MAX_FULL_TEXT_CHARS = 220_000

    def __init__(self, settings: Settings, storage: S3Storage, jobs: JobService):
        self.settings = settings
        self.storage = storage
        self.jobs = jobs

    def normalize_paper_id(self, paper_id: str) -> str:
        normalized = paper_id.replace("arxiv:", "").strip()
        if not normalized or re.search(r"[^\w.\-/]", normalized):
            raise HTTPException(status_code=422, detail="Invalid paper_id")
        return normalized

    def keys_for(self, paper_id: str) -> dict[str, str]:
        normalized = self.normalize_paper_id(paper_id)
        base = f"{self.settings.blog_s3_prefix.rstrip('/')}/{normalized}"
        return {
            "base": base,
            "source_pdf": f"{base}/source/paper.pdf",
            "ocr_prefix": f"{base}/ocr",
            "full_text": f"{base}/ocr/full_text.md",
            "content_json": f"{base}/gen/content.json",
            "style_json": f"{base}/gen/style_content.json",
            "blog_markdown": f"{base}/blog/blog.md",
            "blog_meta": f"{base}/blog/blog_meta.json",
        }

    def _extract_image_refs(self, markdown: str) -> list[str]:
        refs = set()
        for match in IMAGE_REGEX.finditer(markdown):
            ref = (match.group(1) or "").strip().replace("./", "").lstrip("/")
            if ref and "imgs/" in ref and not ref.startswith(("http://", "https://", "data:")):
                refs.add(ref)
        for match in RAW_IMAGE_REGEX.finditer(markdown):
            refs.add(match.group(0).strip())
        return sorted(refs)

    async def _wait_for_key(self, key: str, timeout_sec: int = 180, poll_sec: int = 6) -> bool:
        for _ in range(max(1, timeout_sec // poll_sec)):
            if await self.storage.exists_async(key):
                return True
            await asyncio.sleep(poll_sec)
        return await self.storage.exists_async(key)

    async def _wait_for_prerequisites(self, keys: dict[str, str], timeout_sec: int = 180) -> bool:
        for _ in range(max(1, timeout_sec // 6)):
            if await self._prerequisite_artifacts_ready(keys):
                return True
            await asyncio.sleep(6)
        return await self._prerequisite_artifacts_ready(keys)

    async def _ocr_artifacts_ready(self, keys: dict[str, str]) -> bool:
        if not await self.storage.exists_async(keys["full_text"]):
            page_keys = await self._list_page_markdown_keys(keys)
            return len(page_keys) > 0
        full_text = await self.storage.read_text_async(keys["full_text"])
        for ref in self._extract_image_refs(full_text):
            image_key = ref if ref.startswith(f"{keys['ocr_prefix']}/") else f"{keys['ocr_prefix']}/{ref}"
            if not await self.storage.exists_async(image_key):
                return False
        return True

    async def _list_page_markdown_keys(self, keys: dict[str, str]) -> list[str]:
        prefix = f"{keys['ocr_prefix']}/"
        page_keys = [
            key for key in await self.storage.list_keys_async(prefix)
            if re.search(r"/page_\d+\.md$", key)
        ]
        page_keys.sort(key=lambda key: int(re.search(r"page_(\d+)\.md$", key).group(1)))
        return page_keys

    async def _read_ocr_markdown(self, keys: dict[str, str]) -> str:
        if await self.storage.exists_async(keys["full_text"]):
            return await self.storage.read_text_async(keys["full_text"])
        page_keys = await self._list_page_markdown_keys(keys)
        if not page_keys:
            return ""
        parts = [(await self.storage.read_text_async(key)).strip() for key in page_keys]
        return "\n\n".join(part for part in parts if part)

    async def _download_pdf(self, paper_id: str) -> bytes:
        url = f"{self.settings.arxiv_pdf_base_url.rstrip('/')}/{paper_id}.pdf"
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "pdf" not in content_type.lower() and not response.content.startswith(b"%PDF"):
                raise RuntimeError(f"Expected PDF from arXiv, got content-type={content_type or 'unknown'}")
            return response.content

    async def _run_init_style_json(self, paper_id: str, keys: dict[str, str], *, return_on_ocr_ready: bool, meta: Optional[JobMeta] = None) -> None:
        url = f"{self.settings.blog_image_gen_url.rstrip('/')}/api/v1/ppt/initStyleJson"
        payload = {
            "taskId": f"blog-{paper_id.replace('/', '-')}-{int(datetime.now(timezone.utc).timestamp())}",
            "version": 1,
            "paperUrls": [keys["source_pdf"]],
            "textPrompt": "Academic style",
            "slideCount": max(1, min(30, self.settings.slides_default_count)),
            "language": "English",
            "ocrResultToSavePath": keys["ocr_prefix"],
            "styleContentJsonToSavePath": keys["style_json"],
            "contentJsonToSavePath": keys["content_json"],
        }

        await self._stream_upstream_sse(
            url=url,
            payload=payload,
            error_message="initStyleJson failed",
            until_ready=self._ocr_artifacts_ready if return_on_ocr_ready else self._prerequisite_artifacts_ready,
            keys=keys,
            timeout_loops=45 if return_on_ocr_ready else 90,
            timeout_error="OCR artifacts were not ready before blog timeout window" if return_on_ocr_ready else "initStyleJson completed without writing content/style artifacts",
            meta=meta,
        )

    async def _stream_upstream_sse(
        self,
        *,
        url: str,
        payload: dict,
        error_message: str,
        until_ready,
        keys: dict[str, str],
        timeout_loops: int,
        timeout_error: str,
        meta: Optional[JobMeta] = None,
    ) -> None:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                url,
                json=payload,
                headers={"Accept": "text/event-stream", "Content-Type": "application/json"},
            ) as response:
                response.raise_for_status()
                state = {"stage": "", "event": "", "message": ""}

                async def consume_stream() -> None:
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        raw = line.replace("data:", "", 1).strip()
                        if not raw:
                            continue
                        try:
                            event = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        state["stage"] = str(event.get("stage", ""))
                        state["event"] = str(event.get("event", ""))
                        state["message"] = str(event.get("message") or event.get("content") or "")
                        state["progress"] = event.get("progress")
                        if meta is not None:
                            self.jobs.update_meta(
                                meta,
                                status="running",
                                stage=state["stage"] or "running",
                                message=state["message"] or None,
                                upstream_progress=float(state["progress"]) if isinstance(state["progress"], (int, float)) else None,
                            )
                        if state["event"] == "error":
                            raise RuntimeError(state["message"] or error_message)

                consumer = asyncio.create_task(consume_stream())
                try:
                    for _ in range(timeout_loops):
                        if await until_ready(keys):
                            return
                        if consumer.done():
                            exc = consumer.exception()
                            if exc:
                                raise exc
                            if state["stage"] == "complete":
                                break
                        await asyncio.sleep(4)

                    if await until_ready(keys):
                        return
                    raise RuntimeError(timeout_error)
                finally:
                    consumer.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await consumer

    async def _prerequisite_artifacts_ready(self, keys: dict[str, str]) -> bool:
        return await self.storage.exists_async(keys["content_json"]) and await self.storage.exists_async(keys["style_json"])

    async def ensure_outline_from_existing_ocr(self, paper_id: str, meta: Optional[JobMeta] = None) -> None:
        keys = self.keys_for(paper_id)
        if await self._prerequisite_artifacts_ready(keys):
            return
        full_text = await self._read_ocr_markdown(keys)
        if not full_text.strip():
            raise RuntimeError("OCR markdown is empty; cannot recreate outline")
        if not await self.storage.exists_async(keys["full_text"]):
            await self.storage.write_text_async(keys["full_text"], full_text, "text/markdown; charset=utf-8")

        url = f"{self.settings.blog_image_gen_url.rstrip('/')}/api/v1/ppt/reCreateOutline"
        payload = {
            "taskId": f"outline-{paper_id.replace('/', '-')}-{int(datetime.now(timezone.utc).timestamp())}",
            "version": 1,
            "ocrResultStorePath": keys["ocr_prefix"],
            "textPrompt": "Academic style",
            "slideCount": max(1, min(30, self.settings.slides_default_count)),
            "language": "English",
            "styleContentJsonToSave": keys["style_json"],
            "contentJsonToSavePath": keys["content_json"],
        }
        await self._stream_upstream_sse(
            url=url,
            payload=payload,
            error_message="reCreateOutline failed",
            until_ready=self._prerequisite_artifacts_ready,
            keys=keys,
            timeout_loops=75,
            timeout_error="reCreateOutline completed without writing content/style artifacts",
            meta=meta,
        )

    async def ensure_prerequisites(self, paper_id: str, *, force_init: bool = False, meta: Optional[JobMeta] = None) -> None:
        keys = self.keys_for(paper_id)
        if not force_init and await self._wait_for_prerequisites(keys, timeout_sec=15):
            return
        await self._run_init_style_json(paper_id, keys, return_on_ocr_ready=False, meta=meta)
        if not await self._wait_for_prerequisites(keys):
            raise RuntimeError("Prerequisite artifacts are still missing after initStyleJson")

    async def _generate_markdown(self, full_text: str) -> tuple[str, str]:
        if not self.settings.blog_llm_api_key:
            raise RuntimeError("BLOG_LLM_API_KEY is required for blog generation")
        prompt = "\n".join(
            [
                "You are an expert science writer.",
                "Create an English, concise, reader-friendly blog post from OCR markdown of a paper.",
                "Requirements:",
                "- Keep it compact and structured with headings.",
                "- Preserve and explain key figures, equations, and algorithms only when important.",
                "- Use valid markdown only.",
                "- When referencing images from OCR, keep relative image paths as imgs/... in markdown image syntax.",
                "- Do not fabricate citations or experiments.",
                "- End with a short \"Key Takeaways\" section.",
                "",
                "OCR Markdown Input:",
                full_text[: self.MAX_FULL_TEXT_CHARS],
            ]
        )
        url = f"{self.settings.blog_llm_base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self.settings.blog_llm_model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": "You write high-quality technical blogs in markdown."},
                {"role": "user", "content": prompt},
            ],
        }
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.settings.blog_llm_api_key}",
                },
                json=payload,
            )
            if response.status_code >= 400:
                raise RuntimeError(f"LLM request failed: {response.status_code}")
            data = response.json()
        markdown = data.get("choices", [{}])[0].get("message", {}).get("content")
        if not isinstance(markdown, str) or not markdown.strip():
            raise RuntimeError("LLM returned empty markdown")
        return markdown, self.settings.blog_llm_model

    async def try_get_cached_result(self, paper_id: str) -> Optional[dict]:
        keys = self.keys_for(paper_id)
        if not await self.storage.exists_async(keys["blog_markdown"]):
            return None
        markdown = await self.storage.read_text_async(keys["blog_markdown"])
        has_meta = await self.storage.exists_async(keys["blog_meta"])
        meta = await self.storage.read_json_async(keys["blog_meta"]) if has_meta else {}
        return {
            "paper_id": paper_id,
            "markdown": markdown,
            "generated_at": meta.get("generated_at"),
            "markdown_s3_key": keys["blog_markdown"],
            "meta_s3_key": keys["blog_meta"] if has_meta else None,
        }

    async def _run_job(self, meta: JobMeta, *, force: bool = False) -> dict:
        paper_id = self.normalize_paper_id(meta.paper_id)
        keys = self.keys_for(paper_id)
        cached = await self.try_get_cached_result(paper_id)
        if cached and not force:
            return cached

        self.jobs.update_meta(meta, status="running", stage="download", message="Downloading paper PDF")
        pdf = await self._download_pdf(paper_id)
        self.jobs.update_meta(meta, status="running", stage="upload_pdf", message="Uploading paper PDF to S3")
        await self.storage.upload_bytes_with_retry_async(keys["source_pdf"], pdf, "application/pdf")
        await self._run_init_style_json(paper_id, keys, return_on_ocr_ready=True, meta=meta)
        self.jobs.update_meta(meta, status="running", stage="blog_generate", message="Generating blog markdown")
        if not await self._wait_for_key(keys["full_text"], timeout_sec=30):
            full_text = await self._read_ocr_markdown(keys)
        else:
            full_text = await self.storage.read_text_async(keys["full_text"])
        if not full_text.strip():
            raise RuntimeError("OCR markdown is empty")

        markdown, model = await self._generate_markdown(full_text)
        await self.storage.write_text_async(keys["blog_markdown"], markdown, "text/markdown; charset=utf-8")
        meta_payload = {
            "arxiv_id": paper_id,
            "model": model,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "ready",
        }
        await self.storage.write_json_async(keys["blog_meta"], meta_payload)
        return {
            "paper_id": paper_id,
            "markdown": markdown,
            "generated_at": meta_payload["generated_at"],
            "markdown_s3_key": keys["blog_markdown"],
            "meta_s3_key": keys["blog_meta"],
        }

    async def create_job(self, payload: CreateBlogJobRequest) -> JobCreatedResponse:
        paper_id = self.normalize_paper_id(payload.paper_id)
        cached = await self.try_get_cached_result(paper_id)
        if cached and not payload.force:
            meta = self.jobs.create_meta("blog", paper_id, status="succeeded", progress=100, stage="complete", message="Reused cached blog result", result=cached)
            self.jobs.save_meta(meta)
            return JobCreatedResponse(job_id=meta.job_id, job_type=meta.job_type, status=meta.status, progress=meta.progress, stage=meta.stage, message=meta.message, upstream_progress=meta.upstream_progress)

        meta = self.jobs.create_meta("blog", paper_id)
        return self.jobs.spawn(meta, lambda job_meta: self._run_job(job_meta, force=payload.force))

    async def get_job(self, job_id: str) -> JobDetailResponse:
        meta = self.jobs.load_meta("blog", job_id)
        return self.jobs.to_detail(meta)

    async def get_result(self, job_id: str) -> BlogResultResponse:
        meta = self.jobs.load_meta("blog", job_id)
        if meta.status != "succeeded" or not meta.result:
            raise HTTPException(status_code=409, detail="Blog result is not ready")
        markdown_s3_key = meta.result.get("markdown_s3_key")
        if not markdown_s3_key:
            raise HTTPException(status_code=500, detail="Blog result is missing markdown storage key")
        return BlogResultResponse(
            paper_id=meta.result["paper_id"],
            generated_at=datetime.fromisoformat(meta.result["generated_at"]) if meta.result.get("generated_at") else None,
            download_url=await self.storage.presign_get_url_async(markdown_s3_key, expires_in_seconds=1800),
            expires_in_seconds=1800,
        )
