from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class BlogResultResponse(BaseModel):
    paper_id: str
    generated_at: Optional[datetime] = None
    download_url: str
    expires_in_seconds: int = 1800
