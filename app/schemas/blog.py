from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class BlogResultResponse(BaseModel):
    paper_id: str
    markdown: str
    generated_at: Optional[datetime] = None
    markdown_s3_key: str
    meta_s3_key: Optional[str] = None
