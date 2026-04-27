from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse

from app.core.deps import get_trending_service
from app.schemas.trending import (
    TrendingCoverUrlResponse,
    TrendingPrewarmRequest,
    TrendingPrewarmResponse,
)
from app.services.trending import TrendingService


router = APIRouter()


@router.post("/prewarm", response_model=TrendingPrewarmResponse)
async def prewarm_trending(
    payload: TrendingPrewarmRequest,
    service: TrendingService = Depends(get_trending_service),
) -> TrendingPrewarmResponse:
    return await service.prewarm(
        force=payload.force,
        limit=payload.limit,
        top_artifact_count=payload.top_artifact_count,
        slide_count=payload.slide_count,
        language=payload.language,
    )


@router.get("/current")
async def get_current_trending(
    service: TrendingService = Depends(get_trending_service),
) -> dict:
    return await service.get_current_manifest()


@router.get("/covers/{paper_id}/url", response_model=TrendingCoverUrlResponse)
async def get_trending_cover_url(
    paper_id: str,
    service: TrendingService = Depends(get_trending_service),
) -> TrendingCoverUrlResponse:
    s3_key, download_url = await service.get_cover_url(paper_id)
    return TrendingCoverUrlResponse(
        paper_id=paper_id,
        s3_key=s3_key,
        download_url=download_url,
        expires_in_seconds=1800,
    )


@router.get("/covers/{paper_id}")
async def redirect_trending_cover(
    paper_id: str,
    service: TrendingService = Depends(get_trending_service),
) -> RedirectResponse:
    _, download_url = await service.get_cover_url(paper_id)
    return RedirectResponse(download_url, status_code=307)
