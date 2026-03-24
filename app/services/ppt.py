from __future__ import annotations

import json
import asyncio
import re
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional

import httpx
from fastapi import HTTPException
from PIL import Image

from app.core.config import Settings
from app.schemas.jobs import CreatePptJobRequest, JobCreatedResponse, JobDetailResponse, JobMeta
from app.schemas.ppt import PptResultResponse
from app.services.blog import BlogService
from app.services.jobs import JobService
from app.storage.s3 import S3Storage


class PptService:
    _running_tasks: set[str] = set()

    def __init__(self, settings: Settings, storage: S3Storage, jobs: JobService):
        self.settings = settings
        self.storage = storage
        self.jobs = jobs
        self.blogs = BlogService(settings, storage, jobs)

    def _slides_prefix(self, paper_id: str) -> str:
        keys = self.blogs.keys_for(paper_id)
        return f"{keys['base']}/{self.settings.slides_s3_subdir.strip('/')}"

    def _style_content_key(self, paper_id: str) -> str:
        return f"{self._slides_prefix(paper_id)}/style_content_filled.json"

    def _slide_key(self, paper_id: str, index: int) -> str:
        return f"{self._slides_prefix(paper_id)}/slide_{index}.png"

    def _pdf_key(self, paper_id: str) -> str:
        return f"{self._slides_prefix(paper_id)}/slides.pdf"

    def _normalize_language(self, language: Optional[str]) -> str:
        raw = (language or self.settings.slides_default_lang).strip().lower()
        return "Chinese" if raw in {"zh", "chinese"} else "English"

    def _get_style_slide_count(self, raw_style_json: str) -> int:
        try:
            parsed = json.loads(raw_style_json)
        except json.JSONDecodeError:
            return 0
        if isinstance(parsed, dict):
            styled_slides = parsed.get("styled_slides")
            slides = parsed.get("slides")
            if isinstance(styled_slides, list):
                return len(styled_slides)
            if isinstance(slides, list):
                return len(slides)
        return 0

    async def _list_slide_items(self, paper_id: str) -> list[dict]:
        prefix = f"{self._slides_prefix(paper_id)}/"
        keys = [
            key for key in await self.storage.list_keys_async(prefix)
            if re.search(r"/slide_\d+\.png$", key)
        ]
        keys.sort(key=lambda key: int(re.search(r"slide_(\d+)\.png$", key).group(1)))
        items = []
        for key in keys:
            match = re.search(r"slide_(\d+)\.png$", key)
            if match:
                items.append({"index": int(match.group(1)), "s3_key": key})
        return items

    async def try_get_cached_result(self, paper_id: str, expected_count: int) -> Optional[dict]:
        slides = await self._list_slide_items(paper_id)
        if len(slides) < expected_count:
            return None
        style_content_s3_key = self._style_content_key(paper_id)
        pdf_s3_key = self._pdf_key(paper_id)
        has_style_content = await self.storage.exists_async(style_content_s3_key)
        has_pdf = await self.storage.exists_async(pdf_s3_key)
        generated_at = None
        if has_style_content:
            generated_at = datetime.now(timezone.utc).isoformat()
        return {
            "paper_id": paper_id,
            "generated_at": generated_at,
            "slides_prefix": self._slides_prefix(paper_id),
            "slides": slides,
            "style_content_s3_key": style_content_s3_key if has_style_content else None,
            "pdf_s3_key": pdf_s3_key if has_pdf else None,
        }

    async def _build_pdf_bytes(self, slides: list[dict]) -> bytes:
        images: list[Image.Image] = []
        try:
            for slide in slides:
                slide_bytes = await self.storage.read_bytes_async(slide["s3_key"])
                with Image.open(BytesIO(slide_bytes)) as opened:
                    images.append(opened.convert("RGB"))
            if not images:
                raise RuntimeError("No slide images available to build PDF")
            buffer = BytesIO()
            images[0].save(buffer, format="PDF", save_all=True, append_images=images[1:])
            return buffer.getvalue()
        finally:
            for image in images:
                image.close()

    async def _ensure_pdf_artifact(self, paper_id: str, slides: list[dict]) -> str:
        pdf_key = self._pdf_key(paper_id)
        if await self.storage.exists_async(pdf_key):
            return pdf_key
        pdf_bytes = await self._build_pdf_bytes(slides)
        await self.storage.upload_bytes_with_retry_async(pdf_key, pdf_bytes, "application/pdf")
        return pdf_key

    async def _wait_for_slides(self, paper_id: str, expected_count: int, attempts: int = 15, interval_sec: int = 2) -> list[dict]:
        for _ in range(attempts):
            slides = await self._list_slide_items(paper_id)
            if len(slides) >= expected_count:
                return slides
            await asyncio.sleep(interval_sec)
        return await self._list_slide_items(paper_id)

    async def _run_job(self, meta: JobMeta, *, language: Optional[str] = None, slide_count: Optional[int] = None, force: bool = False) -> dict:
        paper_id = self.blogs.normalize_paper_id(meta.paper_id)
        expected_count = slide_count or self.settings.slides_default_count
        cached = await self.try_get_cached_result(paper_id, expected_count)
        if cached and not force:
            return cached
        if paper_id in self._running_tasks:
            raise RuntimeError("PPT generation is already in progress for this paper")
        self._running_tasks.add(paper_id)

        try:
            keys = self.blogs.keys_for(paper_id)
            await self.jobs.update_meta_async(meta, status="running", stage="prerequisite", message="Checking PPT prerequisites")

            style_json_exists = await self.storage.exists_async(keys["style_json"])
            content_json_exists = await self.storage.exists_async(keys["content_json"])
            should_regenerate_prerequisites = not style_json_exists
            style_content_json = ""

            if style_json_exists:
                style_content_json = await self.storage.read_text_async(keys["style_json"])
                existing_style_slides = self._get_style_slide_count(style_content_json)
                if existing_style_slides > 0 and existing_style_slides < expected_count:
                    should_regenerate_prerequisites = True
                    await self.jobs.update_meta_async(
                        meta,
                        status="running",
                        stage="prerequisite",
                        message=f"Existing style_content has {existing_style_slides} slides (< {expected_count}); regenerating prerequisites",
                    )

            if not content_json_exists:
                should_regenerate_prerequisites = True
                await self.jobs.update_meta_async(
                    meta,
                    status="running",
                    stage="prerequisite",
                    message="content.json is missing; regenerating prerequisites",
                )

            if should_regenerate_prerequisites:
                await self.jobs.update_meta_async(
                    meta,
                    status="running",
                    stage="prerequisite",
                    message="Running initStyleJson flow for PPT prerequisites",
                )
                await self.blogs.ensure_prerequisites(paper_id, force_init=True, meta=meta)
                if not await self.storage.exists_async(keys["style_json"]):
                    raise RuntimeError("Missing usable style_content.json after prerequisite generation")
                style_content_json = await self.storage.read_text_async(keys["style_json"])

            if not style_content_json.strip():
                raise RuntimeError("style_content.json is empty")

            slides_prefix = self._slides_prefix(paper_id)
            slide_paths = [self._slide_key(paper_id, index + 1) for index in range(expected_count)]
            payload = {
                "taskId": f"slides-{paper_id.replace('/', '-')}-{int(datetime.now(timezone.utc).timestamp())}",
                "version": 1,
                "styleContentJson": style_content_json,
                "textPrompt": f"{self._normalize_language(language)} academic style",
                "slideCount": expected_count,
                "slideToSavePaths": slide_paths,
                "styleContentJsonToSave": self._style_content_key(paper_id),
            }

            async with httpx.AsyncClient(timeout=None) as client:
                await self.jobs.update_meta_async(meta, status="running", stage="init", message="Calling createSlides upstream")
                async with client.stream(
                    "POST",
                    self.settings.ppt_create_url,
                    json=payload,
                    headers={"Accept": "text/event-stream", "Content-Type": "application/json"},
                ) as response:
                    response.raise_for_status()
                    line_iter = response.aiter_lines().__aiter__()
                    saw_terminal_event = False
                    no_event_timeout_sec = 600

                    while True:
                        try:
                            line = await asyncio.wait_for(line_iter.__anext__(), timeout=no_event_timeout_sec)
                        except StopAsyncIteration:
                            break
                        except asyncio.TimeoutError as exc:
                            raise RuntimeError(
                                f"createSlides upstream stalled: no SSE event for {no_event_timeout_sec}s"
                            ) from exc

                        if not line.startswith("data:"):
                            continue
                        raw = line.replace("data:", "", 1).strip()
                        if not raw:
                            continue
                        try:
                            event = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        stage = str(event.get("stage", ""))
                        event_name = str(event.get("event", "progress"))
                        message = str(event.get("message") or event.get("content") or "")
                        upstream_progress = event.get("progress")
                        await self.jobs.update_meta_async(
                            meta,
                            status="running",
                            stage=stage or "running",
                            message=message or None,
                            upstream_progress=float(upstream_progress) if isinstance(upstream_progress, (int, float)) else None,
                        )
                        if event_name == "error":
                            raise RuntimeError(message or "Slides generation failed")
                        if event_name == "result" or stage == "complete":
                            saw_terminal_event = True
                            break

                    if not saw_terminal_event:
                        raise RuntimeError("createSlides stream ended without a completion event")

            await self.jobs.update_meta_async(meta, status="running", stage="verify", message="Waiting for slide outputs in S3")
            slides = await self._wait_for_slides(paper_id, expected_count)
            if len(slides) < expected_count:
                raise RuntimeError(f"Slides output incomplete. Expected {expected_count}, got {len(slides)}")
            pdf_s3_key = await self._ensure_pdf_artifact(paper_id, slides)

            return {
                "paper_id": paper_id,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "slides_prefix": slides_prefix,
                "slides": slides,
                "style_content_s3_key": self._style_content_key(paper_id) if await self.storage.exists_async(self._style_content_key(paper_id)) else None,
                "pdf_s3_key": pdf_s3_key,
            }
        finally:
            self._running_tasks.discard(paper_id)

    async def create_job(self, payload: CreatePptJobRequest) -> JobCreatedResponse:
        paper_id = self.blogs.normalize_paper_id(payload.paper_id)
        expected_count = payload.slide_count or self.settings.slides_default_count
        cached = await self.try_get_cached_result(paper_id, expected_count)
        if cached and not payload.force:
            meta = self.jobs.create_meta("ppt", paper_id, status="succeeded", progress=100, stage="complete", message="Reused cached PPT result", result=cached)
            await self.jobs.save_meta_async(meta)
            return JobCreatedResponse(job_id=meta.job_id, job_type=meta.job_type, status=meta.status, progress=meta.progress, stage=meta.stage, message=meta.message, upstream_progress=meta.upstream_progress)

        meta = self.jobs.create_meta("ppt", paper_id)
        await self.jobs.save_meta_async(meta)
        return self.jobs.spawn(meta, lambda job_meta: self._run_job(job_meta, language=payload.language, slide_count=payload.slide_count, force=payload.force))

    async def get_job(self, job_id: str) -> JobDetailResponse:
        meta = await self.jobs.load_meta_async("ppt", job_id)
        return self.jobs.to_detail(meta)

    async def get_result(self, job_id: str) -> PptResultResponse:
        meta = await self.jobs.load_meta_async("ppt", job_id)
        if meta.status != "succeeded" or not meta.result:
            raise HTTPException(status_code=409, detail="PPT result is not ready")
        slides = meta.result.get("slides") or []
        if not slides:
            raise HTTPException(status_code=500, detail="PPT result is missing slide outputs")
        pdf_s3_key = meta.result.get("pdf_s3_key") or await self._ensure_pdf_artifact(meta.result["paper_id"], slides)
        return PptResultResponse(
            paper_id=meta.result["paper_id"],
            generated_at=datetime.fromisoformat(meta.result["generated_at"]) if meta.result.get("generated_at") else None,
            download_url=await self.storage.presign_get_url_async(pdf_s3_key, expires_in_seconds=1800),
            expires_in_seconds=1800,
        )
