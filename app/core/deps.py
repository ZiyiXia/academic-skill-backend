from functools import lru_cache

from app.core.config import get_settings
from app.services.blog import BlogService
from app.services.jobs import JobService
from app.services.ppt import PptService
from app.services.research import ResearchService
from app.services.search import SearchService
from app.services.trending import TrendingService
from app.storage.s3 import S3Storage


@lru_cache
def get_storage() -> S3Storage:
    return S3Storage(get_settings())


@lru_cache
def get_job_service() -> JobService:
    return JobService(get_storage(), get_settings())


@lru_cache
def get_search_service() -> SearchService:
    return SearchService(get_settings())


@lru_cache
def get_research_service() -> ResearchService:
    return ResearchService(get_settings())


@lru_cache
def get_blog_service() -> BlogService:
    return BlogService(get_settings(), get_storage(), get_job_service())


@lru_cache
def get_ppt_service() -> PptService:
    return PptService(get_settings(), get_storage(), get_job_service())


@lru_cache
def get_trending_service() -> TrendingService:
    return TrendingService(
        get_settings(),
        get_storage(),
        get_blog_service(),
        get_ppt_service(),
    )
