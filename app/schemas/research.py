from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ResearchMessage(BaseModel):
    role: Literal["system", "user", "assistant"] = "user"
    content: str = Field(min_length=1)


class ResearchRequest(BaseModel):
    query: str = Field(min_length=1)
    context: Optional[dict[str, Any]] = None
    history: list[ResearchMessage] = Field(default_factory=list)
    max_iterations: int = Field(default=4, ge=1, le=8)
    search_top_k: int = Field(default=5, ge=1, le=10)
    include_trace: bool = True


class ResearchResponse(BaseModel):
    status: str
    message: str
    report: Optional[dict[str, Any]] = None
