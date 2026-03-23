from __future__ import annotations

import json
import asyncio
import re
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import HTTPException

from app.core.config import Settings
from app.schemas.jobs import CreatePptJobRequest, JobCreatedResponse, JobDetailResponse, JobMeta
from app.schemas.ppt import PptResultResponse, SlideItem
from app.services.blog import BlogService
from app.services.jobs import JobService
from app.storage.s3 import S3Storage


class PptService:
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

    def _normalize_language(self, language: Optional[str]) -> str:
        raw = (language or self.settings.slides_default_lang).strip().lower()
        return "Chinese" if raw in {"zh", "chinese"} else "English"

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
        has_style_content = await self.storage.exists_async(style_content_s3_key)
        generated_at = None
        if has_style_content:
            generated_at = datetime.now(timezone.utc).isoformat()
        return {
            "paper_id": paper_id,
            "generated_at": generated_at,
            "slides_prefix": self._slides_prefix(paper_id),
            "slides": slides,
            "style_content_s3_key": style_content_s3_key if has_style_content else None,
        }

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

        keys = self.blogs.keys_for(paper_id)
        self.jobs.update_meta(meta, status="running", stage="prerequisite", message="Checking PPT prerequisites")
        if not await self.storage.exists_async(keys["style_json"]) or not await self.storage.exists_async(keys["content_json"]):
            await self.blogs.ensure_outline_from_existing_ocr(paper_id, meta=meta)
        if not await self.storage.exists_async(keys["style_json"]) or not await self.storage.exists_async(keys["content_json"]):
            await self.blogs.ensure_prerequisites(paper_id, force_init=False, meta=meta)
        if not await self.storage.exists_async(keys["style_json"]):
            raise RuntimeError("Missing prerequisite style_content.json")
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
            self.jobs.update_meta(meta, status="running", stage="init", message="Calling createSlides upstream")
            async with client.stream(
                "POST",
                self.settings.ppt_create_url,
                json=payload,
                headers={"Accept": "text/event-stream", "Content-Type": "application/json"},
            ) as response:
                response.raise_for_status()
                line_iter = response.aiter_lines().__aiter__()
                saw_terminal_event = False
                # Fail fast when upstream keeps the stream open but does not emit data.
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
                    self.jobs.update_meta(
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

        self.jobs.update_meta(meta, status="running", stage="verify", message="Waiting for slide outputs in S3")
        slides = await self._wait_for_slides(paper_id, expected_count)
        if len(slides) < expected_count:
            raise RuntimeError(f"Slides output incomplete. Expected {expected_count}, got {len(slides)}")

        return {
            "paper_id": paper_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "slides_prefix": slides_prefix,
            "slides": slides,
            "style_content_s3_key": self._style_content_key(paper_id) if await self.storage.exists_async(self._style_content_key(paper_id)) else None,
        }

    async def create_job(self, payload: CreatePptJobRequest) -> JobCreatedResponse:
        paper_id = self.blogs.normalize_paper_id(payload.paper_id)
        expected_count = payload.slide_count or self.settings.slides_default_count
        cached = await self.try_get_cached_result(paper_id, expected_count)
        if cached and not payload.force:
            meta = self.jobs.create_meta("ppt", paper_id, status="succeeded", progress=100, stage="complete", message="Reused cached PPT result", result=cached)
            self.jobs.save_meta(meta)
            return JobCreatedResponse(job_id=meta.job_id, job_type=meta.job_type, status=meta.status, progress=meta.progress, stage=meta.stage, message=meta.message, upstream_progress=meta.upstream_progress)

        meta = self.jobs.create_meta("ppt", paper_id)
        return self.jobs.spawn(meta, lambda job_meta: self._run_job(job_meta, language=payload.language, slide_count=payload.slide_count, force=payload.force))

    async def get_job(self, job_id: str) -> JobDetailResponse:
        meta = self.jobs.load_meta("ppt", job_id)
        return self.jobs.to_detail(meta)

    async def get_result(self, job_id: str) -> PptResultResponse:
        meta = self.jobs.load_meta("ppt", job_id)
        if meta.status != "succeeded" or not meta.result:
            raise HTTPException(status_code=409, detail="PPT result is not ready")
        return PptResultResponse(
            paper_id=meta.result["paper_id"],
            generated_at=datetime.fromisoformat(meta.result["generated_at"]) if meta.result.get("generated_at") else None,
            slides_prefix=meta.result["slides_prefix"],
            slides=[SlideItem(**item) for item in meta.result["slides"]],
            style_content_s3_key=meta.result.get("style_content_s3_key"),
        )
