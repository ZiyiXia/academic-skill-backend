from fastapi import APIRouter, Depends

from app.core.deps import get_ppt_service
from app.schemas.jobs import CreatePptJobRequest, JobCreatedResponse, JobDetailResponse
from app.schemas.ppt import PptResultResponse
from app.services.ppt import PptService


router = APIRouter()


@router.post("/jobs", response_model=JobCreatedResponse)
async def create_ppt_job(
    payload: CreatePptJobRequest,
    service: PptService = Depends(get_ppt_service),
) -> JobCreatedResponse:
    return await service.create_job(payload)


@router.get("/jobs/{job_id}", response_model=JobDetailResponse)
async def get_ppt_job(
    job_id: str,
    service: PptService = Depends(get_ppt_service),
) -> JobDetailResponse:
    return await service.get_job(job_id)


@router.get("/jobs/{job_id}/result", response_model=PptResultResponse)
async def get_ppt_result(
    job_id: str,
    service: PptService = Depends(get_ppt_service),
) -> PptResultResponse:
    return await service.get_result(job_id)
