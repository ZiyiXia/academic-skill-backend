from typing import Optional, Union
from pydantic import BaseModel, Field


class SearchPapersRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=20, ge=1, le=100)
    authors: Optional[list[str]] = None
    orgs: Optional[list[str]] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    date_search_type: Optional[str] = None
    date_str: Optional[Union[str, list[str]]] = None


class SearchPaperItem(BaseModel):
    paper_id: Optional[str] = None
    title: Optional[str] = None
    abstract: Optional[str] = None
    score: Optional[float] = None
    url: Optional[str] = None
    date: Optional[str] = None
    authors: list[str] = Field(default_factory=list)


class SearchPapersResponse(BaseModel):
    status: str = "success"
    query: str
    total: int
    items: list[SearchPaperItem]
