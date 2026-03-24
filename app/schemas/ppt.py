from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SlideItem(BaseModel):
    index: int
    s3_key: str


class PptResultResponse(BaseModel):
    paper_id: str
    generated_at: Optional[datetime] = None
    download_url: str
    expires_in_seconds: int = 1800
