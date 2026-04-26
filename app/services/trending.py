from __future__ import annotations

import asyncio
import logging
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import httpx
from fastapi import HTTPException

from app.core.config import Settings
from app.schemas.jobs import CreateBlogJobRequest, CreatePptJobRequest, JobCreatedResponse
from app.schemas.trending import TrendingPaperArtifactStatus, TrendingPrewarmResponse
from app.services.blog import BlogService
from app.services.ppt import PptService
from app.storage.s3 import S3Storage


logger = logging.getLogger(__name__)


class TrendingService:
    def __init__(
        self,
        settings: Settings,
        storage: S3Storage,
        blogs: BlogService,
        ppts: PptService,
    ):
        self.settings = settings
        self.storage = storage
        self.blogs = blogs
        self.ppts = ppts

    def cover_key_for(self, paper_id: str) -> str:
        keys = self.blogs.keys_for(paper_id)
        return f"{keys['base']}/{self.settings.trending_cover_subdir.strip('/')}/page_1.jpg"

    async def fetch_trending_paper_ids(self, *, limit: Optional[int] = None) -> list[str]:
        max_items = limit or self.settings.trending_limit
        async with httpx.AsyncClient(timeout=30.0) as client:
            for days in (7, 14, 30):
                response = await client.get(
                    self.settings.trending_api_url,
                    params={"days": days, "limit": max_items},
                )
                if response.status_code >= 400:
                    logger.warning(
                        "Trending API failed: days=%s status=%s",
                        days,
                        response.status_code,
                    )
                    continue
                payload = response.json()
                papers = payload.get("data", {}).get("papers")
                if isinstance(papers, list) and papers:
                    return self._extract_paper_ids(papers)[:max_items]
        return []

    def _extract_paper_ids(self, papers: list[Any]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for paper in papers:
            if not isinstance(paper, dict):
                continue
            raw_id = str(paper.get("arxiv_id") or "").strip()
            if not raw_id:
                continue
            paper_id = self.blogs.normalize_paper_id(raw_id.split("v")[0] or raw_id)
            if paper_id in seen:
                continue
            seen.add(paper_id)
            result.append(paper_id)
        return result

    async def ensure_cover(self, paper_id: str, *, force: bool = False) -> str:
        normalized = self.blogs.normalize_paper_id(paper_id)
        cover_key = self.cover_key_for(normalized)
        if not force and await self.storage.exists_async(cover_key):
            return cover_key

        source_pdf_key = self.blogs.keys_for(normalized)["source_pdf"]
        await self.blogs.ensure_source_pdf(normalized, source_pdf_key)
        pdf_bytes = await self.storage.read_bytes_async(source_pdf_key)

        with tempfile.TemporaryDirectory(prefix=f"trending-cover-{normalized.replace('/', '-')}-") as tmp:
            tmp_path = Path(tmp)
            pdf_path = tmp_path / "paper.pdf"
            output_prefix = tmp_path / "page"
            pdf_path.write_bytes(pdf_bytes)
            process = await asyncio.create_subprocess_exec(
                "pdftoppm",
                "-jpeg",
                "-r",
                str(self.settings.trending_cover_dpi),
                "-f",
                "1",
                "-singlefile",
                str(pdf_path),
                str(output_prefix),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()
            if process.returncode != 0:
                message = stderr.decode("utf-8", errors="ignore").strip()
                raise RuntimeError(f"pdftoppm failed for {normalized}: {message}")

            jpg_path = output_prefix.with_suffix(".jpg")
            if not jpg_path.exists():
                raise RuntimeError(f"pdftoppm did not create a cover image for {normalized}")
            await self.storage.upload_bytes_with_retry_async(
                cover_key,
                jpg_path.read_bytes(),
                "image/jpeg",
            )
        return cover_key

    async def get_cover_url(self, paper_id: str, *, expires_in_seconds: int = 1800) -> tuple[str, str]:
        normalized = self.blogs.normalize_paper_id(paper_id)
        cover_key = self.cover_key_for(normalized)
        if not await self.storage.exists_async(cover_key):
            raise HTTPException(status_code=404, detail="Trending cover is not ready")
        return cover_key, await self.storage.presign_get_url_async(cover_key, expires_in_seconds)

    async def prewarm(
        self,
        *,
        force: bool = False,
        limit: Optional[int] = None,
        top_artifact_count: Optional[int] = None,
        slide_count: Optional[int] = None,
        language: Optional[str] = None,
        progress: Optional[Callable[[str], None]] = None,
    ) -> TrendingPrewarmResponse:
        started_at = time.perf_counter()
        paper_ids = await self.fetch_trending_paper_ids(limit=limit)
        top_count = top_artifact_count
        if top_count is None:
            top_count = self.settings.trending_top_artifact_count
        top_count = max(0, min(top_count, len(paper_ids)))
        concurrency = max(1, self.settings.trending_prewarm_concurrency)
        semaphore = asyncio.Semaphore(concurrency)
        cover_done = 0

        def emit(message: str) -> None:
            if progress:
                progress(message)

        emit(
            f"fetched {len(paper_ids)} trending papers; "
            f"covers={len(paper_ids)}, blog/ppt top={top_count}, concurrency={concurrency}"
        )

        statuses = [
            TrendingPaperArtifactStatus(paper_id=paper_id, rank=index + 1)
            for index, paper_id in enumerate(paper_ids)
        ]

        async def run_cover(index: int, paper_id: str) -> None:
            nonlocal cover_done
            async with semaphore:
                status = statuses[index]
                try:
                    cover_item_started = time.perf_counter()
                    emit(f"[{index + 1}/{len(paper_ids)}] cover start {paper_id}")
                    status.cover_s3_key = await self.ensure_cover(paper_id, force=force)
                    status.cover_ready = True
                    cover_done += 1
                    emit(
                        f"[{index + 1}/{len(paper_ids)}] cover done {paper_id} "
                        f"({time.perf_counter() - cover_item_started:.1f}s, {cover_done}/{len(paper_ids)})"
                    )
                except Exception as exc:
                    logger.exception("Trending prewarm failed: paper_id=%s", paper_id)
                    status.error = str(exc)
                    emit(f"[{index + 1}/{len(paper_ids)}] cover failed {paper_id}: {exc}")

        cover_started_at = time.perf_counter()
        await asyncio.gather(
            *(run_cover(index, paper_id) for index, paper_id in enumerate(paper_ids))
        )
        cover_elapsed = time.perf_counter() - cover_started_at
        emit(
            f"cover summary: ready={sum(1 for paper in statuses if paper.cover_ready)}/{len(statuses)}, "
            f"elapsed={cover_elapsed:.1f}s"
        )

        async def run_artifacts(index: int, paper_id: str) -> None:
            async with semaphore:
                status = statuses[index]
                try:
                    blog_started = time.perf_counter()
                    emit(f"[{index + 1}/{top_count}] blog start {paper_id}")
                    blog_job = await self.blogs.create_job(
                        CreateBlogJobRequest(paper_id=paper_id, force=force)
                    )
                    status.blog_status = await self._wait_for_blog(blog_job)
                    emit(
                        f"[{index + 1}/{top_count}] blog {status.blog_status} {paper_id} "
                        f"({time.perf_counter() - blog_started:.1f}s)"
                    )

                    ppt_started = time.perf_counter()
                    emit(f"[{index + 1}/{top_count}] ppt start {paper_id}")
                    ppt_job = await self.ppts.create_job(
                        CreatePptJobRequest(
                            paper_id=paper_id,
                            force=force,
                            language=language,
                            slide_count=slide_count,
                        )
                    )
                    status.ppt_status = await self._wait_for_ppt(ppt_job)
                    emit(
                        f"[{index + 1}/{top_count}] ppt {status.ppt_status} {paper_id} "
                        f"({time.perf_counter() - ppt_started:.1f}s)"
                    )
                except Exception as exc:
                    logger.exception("Trending artifact prewarm failed: paper_id=%s", paper_id)
                    status.error = str(exc)
                    emit(f"[{index + 1}/{top_count}] artifact failed {paper_id}: {exc}")

        await asyncio.gather(
            *(run_artifacts(index, paper_id) for index, paper_id in enumerate(paper_ids[:top_count]))
        )
        emit(f"prewarm done: elapsed={time.perf_counter() - started_at:.1f}s")
        return TrendingPrewarmResponse(
            status="ok",
            generated_at=datetime.now(timezone.utc),
            total_papers=len(paper_ids),
            top_artifact_count=top_count,
            papers=statuses,
        )

    async def _wait_for_blog(self, created: JobCreatedResponse) -> str:
        status = await self._wait_for_job("blog", created.job_id, created.status)
        if status == "succeeded":
            await self.blogs.get_result(created.job_id)
        return status

    async def _wait_for_ppt(self, created: JobCreatedResponse) -> str:
        status = await self._wait_for_job("ppt", created.job_id, created.status)
        if status == "succeeded":
            await self.ppts.get_result(created.job_id)
        return status

    async def _wait_for_job(self, job_type: str, job_id: str, initial_status: str) -> str:
        status = initial_status
        for _ in range(360):
            if status in {"succeeded", "failed"}:
                return status
            await asyncio.sleep(5)
            detail = (
                await self.blogs.get_job(job_id)
                if job_type == "blog"
                else await self.ppts.get_job(job_id)
            )
            status = detail.status
        raise TimeoutError(f"{job_type} job timed out: {job_id}")
