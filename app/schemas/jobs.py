from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


JobType = Literal["blog", "ppt"]
JobStatus = Literal["queued", "running", "succeeded", "failed"]


class JobMeta(BaseModel):
    job_id: str
    job_type: JobType
    paper_id: str
    status: JobStatus
    progress: int = Field(ge=0, le=100)
    stage: Optional[str] = None
    message: Optional[str] = None
    upstream_progress: Optional[float] = None
    error_message: Optional[str] = None
    result: Optional[dict[str, Any]] = None
    temp_prefix: Optional[str] = None
    cleanup_after: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class JobCreatedResponse(BaseModel):
    job_id: str
    job_type: JobType
    status: JobStatus
    progress: int
    stage: Optional[str] = None
    message: Optional[str] = None
    upstream_progress: Optional[float] = None


class JobDetailResponse(BaseModel):
    job_id: str
    job_type: JobType
    paper_id: str
    status: JobStatus
    progress: int
    stage: Optional[str] = None
    message: Optional[str] = None
    upstream_progress: Optional[float] = None
    error_message: Optional[str] = None
    result: Optional[dict[str, Any]] = None
    temp_prefix: Optional[str] = None
    cleanup_after: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class CreateBlogJobRequest(BaseModel):
    paper_id: str = Field(min_length=1)
    force: bool = False


class CreatePptJobRequest(BaseModel):
    paper_id: str = Field(min_length=1)
    force: bool = False
    language: Optional[str] = None
    slide_count: Optional[int] = Field(default=None, ge=1, le=30)
