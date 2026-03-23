from fastapi import APIRouter, Depends

from app.core.deps import get_blog_service
from app.schemas.jobs import CreateBlogJobRequest, JobCreatedResponse, JobDetailResponse
from app.schemas.blog import BlogResultResponse
from app.services.blog import BlogService


router = APIRouter()


@router.post("/jobs", response_model=JobCreatedResponse)
async def create_blog_job(
    payload: CreateBlogJobRequest,
    service: BlogService = Depends(get_blog_service),
) -> JobCreatedResponse:
    return await service.create_job(payload)


@router.get("/jobs/{job_id}", response_model=JobDetailResponse)
async def get_blog_job(
    job_id: str,
    service: BlogService = Depends(get_blog_service),
) -> JobDetailResponse:
    return await service.get_job(job_id)


@router.get("/jobs/{job_id}/result", response_model=BlogResultResponse)
async def get_blog_result(
    job_id: str,
    service: BlogService = Depends(get_blog_service),
) -> BlogResultResponse:
    return await service.get_result(job_id)
