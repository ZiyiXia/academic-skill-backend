from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import HTTPException

from app.core.config import Settings
from app.schemas.jobs import JobCreatedResponse, JobDetailResponse, JobMeta, JobStatus, JobType
from app.storage.s3 import S3Storage


class JobService:
    def __init__(self, storage: S3Storage, settings: Settings):
        self.storage = storage
        self.settings = settings

    def _job_key(self, job_type: JobType, job_id: str) -> str:
        return f"{self.settings.skill_job_prefix}/{job_type}/{job_id}/meta.json"

    def create_meta(
        self,
        job_type: JobType,
        paper_id: str,
        status: JobStatus = "queued",
        progress: int = 0,
        stage: Optional[str] = None,
        message: Optional[str] = None,
        upstream_progress: Optional[float] = None,
        result: Optional[dict] = None,
        error_message: Optional[str] = None,
    ) -> JobMeta:
        now = datetime.now(timezone.utc)
        return JobMeta(
            job_id=uuid4().hex,
            job_type=job_type,
            paper_id=paper_id,
            status=status,
            progress=progress,
            stage=stage,
            message=message,
            upstream_progress=upstream_progress,
            result=result,
            error_message=error_message,
            created_at=now,
            updated_at=now,
        )

    def save_meta(self, meta: JobMeta) -> None:
        self.storage.write_json(
            self._job_key(meta.job_type, meta.job_id),
            meta.model_dump(mode="json"),
        )

    async def save_meta_async(self, meta: JobMeta) -> None:
        await self.storage.write_json_async(
            self._job_key(meta.job_type, meta.job_id),
            meta.model_dump(mode="json"),
        )

    def load_meta(self, job_type: JobType, job_id: str) -> JobMeta:
        key = self._job_key(job_type, job_id)
        if not self.storage.exists(key):
            raise HTTPException(status_code=404, detail="Job not found")
        return JobMeta.model_validate(self.storage.read_json(key))

    async def load_meta_async(self, job_type: JobType, job_id: str) -> JobMeta:
        key = self._job_key(job_type, job_id)
        if not await self.storage.exists_async(key):
            raise HTTPException(status_code=404, detail="Job not found")
        return JobMeta.model_validate(await self.storage.read_json_async(key))

    def update_meta(
        self,
        meta: JobMeta,
        *,
        status: Optional[JobStatus] = None,
        progress: Optional[int] = None,
        stage: Optional[str] = None,
        message: Optional[str] = None,
        upstream_progress: Optional[float] = None,
        result: Optional[dict] = None,
        error_message: Optional[str] = None,
    ) -> JobMeta:
        try:
            current = self.load_meta(meta.job_type, meta.job_id)
        except HTTPException:
            current = meta
        updated = current.model_copy(
            update={
                "status": status or current.status,
                "progress": current.progress if progress is None else progress,
                "stage": current.stage if stage is None else stage,
                "message": current.message if message is None else message,
                "upstream_progress": current.upstream_progress if upstream_progress is None else upstream_progress,
                "result": current.result if result is None else result,
                "error_message": current.error_message if error_message is None else error_message,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        self.save_meta(updated)
        return updated

    async def update_meta_async(
        self,
        meta: JobMeta,
        *,
        status: Optional[JobStatus] = None,
        progress: Optional[int] = None,
        stage: Optional[str] = None,
        message: Optional[str] = None,
        upstream_progress: Optional[float] = None,
        result: Optional[dict] = None,
        error_message: Optional[str] = None,
    ) -> JobMeta:
        try:
            current = await self.load_meta_async(meta.job_type, meta.job_id)
        except HTTPException:
            current = meta
        updated = current.model_copy(
            update={
                "status": status or current.status,
                "progress": current.progress if progress is None else progress,
                "stage": current.stage if stage is None else stage,
                "message": current.message if message is None else message,
                "upstream_progress": current.upstream_progress if upstream_progress is None else upstream_progress,
                "result": current.result if result is None else result,
                "error_message": current.error_message if error_message is None else error_message,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        await self.save_meta_async(updated)
        return updated

    def spawn(
        self,
        meta: JobMeta,
        worker: Callable[[JobMeta], Awaitable[dict]],
    ) -> JobCreatedResponse:
        async def runner() -> None:
            current = await self.update_meta_async(meta, status="running", progress=5, stage="init", message="Job started", error_message=None)
            try:
                result = await worker(current)
                await self.update_meta_async(current, status="succeeded", progress=100, stage="complete", message="Job completed", result=result, error_message=None)
            except Exception as exc:
                error_text = str(exc).strip() or f"{type(exc).__name__}: {repr(exc)}"
                await self.update_meta_async(current, status="failed", progress=current.progress, message=error_text, error_message=error_text)

        asyncio.create_task(runner())
        return JobCreatedResponse(
            job_id=meta.job_id,
            job_type=meta.job_type,
            status=meta.status,
            progress=meta.progress,
            stage=meta.stage,
            message=meta.message,
            upstream_progress=meta.upstream_progress,
        )

    def to_detail(self, meta: JobMeta) -> JobDetailResponse:
        return JobDetailResponse(**meta.model_dump())
