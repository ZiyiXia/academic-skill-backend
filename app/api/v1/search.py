from fastapi import APIRouter, Depends

from app.core.deps import get_search_service
from app.schemas.search import SearchPapersRequest, SearchPapersResponse
from app.services.search import SearchService


router = APIRouter()


@router.post("/papers", response_model=SearchPapersResponse)
async def search_papers(
    payload: SearchPapersRequest,
    service: SearchService = Depends(get_search_service),
) -> SearchPapersResponse:
    return await service.search_papers(payload)
