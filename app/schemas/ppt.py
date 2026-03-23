from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SlideItem(BaseModel):
    index: int
    s3_key: str


class PptResultResponse(BaseModel):
    paper_id: str
    generated_at: Optional[datetime] = None
    slides_prefix: str
    slides: list[SlideItem]
    style_content_s3_key: Optional[str] = None
