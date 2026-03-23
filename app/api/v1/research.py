from fastapi import APIRouter, Depends

from app.core.deps import get_research_service
from app.schemas.research import ResearchRequest, ResearchResponse
from app.services.research import ResearchService


router = APIRouter()


@router.post("", response_model=ResearchResponse)
async def run_research(
    payload: ResearchRequest,
    service: ResearchService = Depends(get_research_service),
) -> ResearchResponse:
    return await service.run(payload)
