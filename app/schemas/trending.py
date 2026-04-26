from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TrendingPrewarmRequest(BaseModel):
    force: bool = False
    limit: Optional[int] = Field(default=None, ge=1, le=100)
    top_artifact_count: Optional[int] = Field(default=None, ge=0, le=30)
    slide_count: Optional[int] = Field(default=None, ge=1, le=30)
    language: Optional[str] = None


class TrendingPaperArtifactStatus(BaseModel):
    paper_id: str
    rank: int
    cover_s3_key: Optional[str] = None
    cover_ready: bool = False
    blog_status: Optional[str] = None
    ppt_status: Optional[str] = None
    error: Optional[str] = None


class TrendingPrewarmResponse(BaseModel):
    status: str
    generated_at: datetime
    total_papers: int
    top_artifact_count: int
    papers: list[TrendingPaperArtifactStatus]


class TrendingCoverUrlResponse(BaseModel):
    paper_id: str
    s3_key: str
    download_url: str
    expires_in_seconds: int = 1800
