from fastapi import APIRouter

from app.api.v1.blog import router as blog_router
from app.api.v1.ppt import router as ppt_router
from app.api.v1.research import router as research_router
from app.api.v1.search import router as search_router


api_router = APIRouter()
api_router.include_router(search_router, prefix="/v1/search", tags=["search"])
api_router.include_router(research_router, prefix="/v1/research", tags=["research"])
api_router.include_router(blog_router, prefix="/v1/blog", tags=["blog"])
api_router.include_router(ppt_router, prefix="/v1/ppt", tags=["ppt"])
