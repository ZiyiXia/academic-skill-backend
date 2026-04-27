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

    def daily_manifest_key_for(self, now: Optional[datetime] = None) -> str:
        current = now or datetime.now(timezone.utc)
        return f"trending/{current.strftime('%Y-%m-%d')}.json"

    def current_manifest_key(self) -> str:
        return "trending/current.json"

    async def fetch_trending_paper_ids(self, *, limit: Optional[int] = None) -> list[str]:
        papers = await self.fetch_trending_raw(limit=limit)
        return [paper["paper_id"] for paper in papers]

    async def fetch_trending_raw(self, *, limit: Optional[int] = None) -> list[dict[str, Any]]:
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
                    return self._normalize_trending_raw(papers)[:max_items]
        return []

    def _normalize_trending_raw(self, papers: list[Any]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
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
            result.append({**paper, "paper_id": paper_id})
        return result

    async def fetch_paper_metadata(self, paper_id: str) -> dict[str, Any] | None:
        params = {
            "arxiv_id": paper_id,
            "type": "head",
            "token": self.settings.rag_api_token,
        }
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                response = await client.get(
                    f"{self.settings.rag_api_base_url.rstrip('/')}/arxiv/",
                    params=params,
                )
                if response.status_code >= 400:
                    return None
                payload = response.json()
                if isinstance(payload, dict):
                    detail = str(payload.get("detail") or "").lower()
                    if "arxiv paper not found" in detail:
                        return None
                    return payload
            except Exception:
                logger.exception("Trending metadata fetch failed: paper_id=%s", paper_id)
        return None

    def _extract_authors(self, meta: dict[str, Any]) -> list[dict[str, Any]]:
        raw_authors = meta.get("authors")
        if isinstance(raw_authors, str):
            return [{"name": name.strip(), "orgs": []} for name in raw_authors.split(",") if name.strip()]
        if not isinstance(raw_authors, list):
            raw_authors = meta.get("author") if isinstance(meta.get("author"), list) else []
        authors = []
        for author in raw_authors:
            if isinstance(author, str) and author.strip():
                authors.append({"name": author.strip(), "orgs": []})
            elif isinstance(author, dict) and isinstance(author.get("name"), str):
                authors.append({"name": author["name"], "orgs": author.get("orgs") or []})
        return authors

    def _extract_recommended_by(self, raw: dict[str, Any]) -> list[dict[str, str | None]]:
        candidates = [
            raw.get("recommended_by"),
            raw.get("recommenders"),
            raw.get("kols"),
            raw.get("top_kols"),
            raw.get("mentioned_by"),
            raw.get("users"),
            raw.get("top_users"),
            raw.get("mentions"),
            raw.get("timeline"),
        ]
        found: dict[str, dict[str, str | None]] = {}

        def visit(value: Any) -> None:
            if not value:
                return
            if isinstance(value, list):
                for item in value:
                    visit(item)
                return
            if isinstance(value, str):
                handle = value.strip().lstrip("@")
                if handle:
                    found[f"@{handle}"] = {"handle": f"@{handle}", "url": f"https://x.com/{handle}"}
                return
            if not isinstance(value, dict):
                return
            raw_handle = (
                value.get("handle")
                or value.get("username")
                or value.get("screen_name")
                or value.get("user_handle")
                or value.get("twitter_handle")
                or value.get("x_handle")
            )
            raw_url = value.get("url") or value.get("profile_url") or value.get("twitter_url") or value.get("x_url")
            if isinstance(raw_handle, str) and raw_handle.strip():
                normalized = raw_handle.strip().lstrip("@")
                found[f"@{normalized}"] = {
                    "handle": f"@{normalized}",
                    "url": raw_url if isinstance(raw_url, str) and raw_url.strip() else f"https://x.com/{normalized}",
                }
            for nested in value.values():
                if isinstance(nested, list):
                    visit(nested)

        for candidate in candidates:
            visit(candidate)
        return list(found.values())[:3]

    async def build_published_papers(
        self,
        raw_papers: list[dict[str, Any]],
        statuses: list[TrendingPaperArtifactStatus],
    ) -> list[dict[str, Any]]:
        status_by_id = {status.paper_id: status for status in statuses}
        metadata = await asyncio.gather(
            *(self.fetch_paper_metadata(paper["paper_id"]) for paper in raw_papers)
        )
        published: list[dict[str, Any]] = []
        for raw, meta in zip(raw_papers, metadata):
            if not meta:
                continue
            paper_id = raw["paper_id"]
            status = status_by_id.get(paper_id)
            categories = meta.get("categories") if isinstance(meta.get("categories"), list) else []
            timeline = raw.get("timeline") if isinstance(raw.get("timeline"), dict) else {}
            published.append(
                {
                    "arxiv_id": paper_id,
                    "title": meta.get("title") or f"arXiv:{paper_id}",
                    "abstract": meta.get("abstract") or "",
                    "authors": self._extract_authors(meta),
                    "score": 0,
                    "url": raw.get("arxiv_url") or f"https://arxiv.org/abs/{paper_id}",
                    "date": meta.get("publish_at") or timeline.get("latest_mention"),
                    "rank": len(published) + 1,
                    "stats": raw.get("stats") or {},
                    "categories": categories,
                    "tldr": meta.get("tldr"),
                    "github_url": meta.get("github_url"),
                    "venue": meta.get("venue") or meta.get("journal_name"),
                    "citations": meta.get("citations"),
                    "coverImageUrl": None,
                    "cover_s3_key": status.cover_s3_key if status else None,
                    "recommendedBy": self._extract_recommended_by(raw),
                }
            )
        return published

    async def publish_trending_manifest(
        self,
        raw_papers: list[dict[str, Any]],
        statuses: list[TrendingPaperArtifactStatus],
        *,
        cover_elapsed_seconds: float,
    ) -> None:
        now = datetime.now(timezone.utc)
        papers = await self.build_published_papers(raw_papers, statuses)
        manifest = {
            "version": 1,
            "published_at": now.isoformat(),
            "cover_elapsed_seconds": round(cover_elapsed_seconds, 3),
            "total_papers": len(papers),
            "papers": papers,
        }
        daily_key = self.daily_manifest_key_for(now)
        await self.storage.write_json_async(daily_key, manifest)
        await self.storage.write_json_async(self.current_manifest_key(), manifest)

    async def get_current_manifest(self) -> dict[str, Any]:
        key = self.current_manifest_key()
        if not await self.storage.exists_async(key):
            raise HTTPException(status_code=404, detail="Trending manifest is not published")
        return await self.storage.read_json_async(key)

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
        raw_papers = await self.fetch_trending_raw(limit=limit)
        paper_ids = [paper["paper_id"] for paper in raw_papers]
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
        if statuses and all(status.cover_ready for status in statuses):
            await self.publish_trending_manifest(
                raw_papers,
                statuses,
                cover_elapsed_seconds=cover_elapsed,
            )
            emit(f"published trending manifest: {self.current_manifest_key()}")
        else:
            emit("skipped trending manifest publish: not all covers are ready")

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
