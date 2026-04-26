from functools import lru_cache
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel


class Settings(BaseModel):
    app_name: str
    app_env: str
    log_level: str

    search_api_url: str
    ppt_create_url: str
    arxiv_pdf_base_url: str
    rag_api_base_url: str
    rag_api_token: Optional[str] = None

    s3_bucket: str
    s3_region: str
    s3_endpoint: Optional[str] = None
    s3_access_key: Optional[str] = None
    s3_secret_key: Optional[str] = None

    blog_s3_prefix: str
    slides_s3_subdir: str
    skill_job_prefix: str
    skill_run_prefix: str

    blog_image_gen_url: str
    blog_llm_base_url: str
    blog_llm_api_key: Optional[str] = None
    blog_llm_model: str
    research_llm_base_url: str
    research_llm_api_key: Optional[str] = None
    research_llm_model: str
    slides_default_count: int
    slides_default_lang: str
    trending_api_url: str
    trending_limit: int
    trending_top_artifact_count: int
    trending_cover_subdir: str
    trending_cover_dpi: int
    trending_prewarm_concurrency: int


def _env(name: str, default: Optional[str] = None) -> str:
    value = os.getenv(name, default)
    if value is None or value == "":
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _env_opt(name: str) -> Optional[str]:
    value = os.getenv(name)
    return value if value else None


@lru_cache
def get_settings() -> Settings:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    load_dotenv(env_path, override=False)
    return Settings(
        app_name=_env("APP_NAME", "academic-skill-backend"),
        app_env=_env("APP_ENV", "development"),
        log_level=_env("LOG_LEVEL", "INFO"),
        search_api_url=_env("SEARCH_API_URL"),
        ppt_create_url=_env("PPT_CREATE_URL"),
        arxiv_pdf_base_url=_env("ARXIV_PDF_BASE_URL"),
        rag_api_base_url=_env("RAG_API_BASE_URL", "https://data.rag.ac.cn"),
        rag_api_token=_env_opt("RAG_API_TOKEN") or "kEzse_SlML7gzjT9Y9-yL96ArB0ESW7wFzYhZey5Zds",
        s3_bucket=_env("S3_BUCKET"),
        s3_region=_env("S3_REGION", "us-east-1"),
        s3_endpoint=_env_opt("S3_ENDPOINT"),
        s3_access_key=_env_opt("S3_ACCESS_KEY"),
        s3_secret_key=_env_opt("S3_SECRET_KEY"),
        blog_s3_prefix=_env("BLOG_S3_PREFIX", "deepxiv/blogs"),
        slides_s3_subdir=_env("SLIDES_S3_SUBDIR", "slides"),
        skill_job_prefix=_env("SKILL_JOB_PREFIX", "academic-skill/jobs"),
        skill_run_prefix=_env("SKILL_RUN_PREFIX", "academic-skill/runs"),
        blog_image_gen_url=_env("BLOG_IMAGE_GEN_URL", "http://120.92.112.87:32500"),
        blog_llm_base_url=_env("BLOG_LLM_BASE_URL", "https://api.openai.com/v1"),
        blog_llm_api_key=_env_opt("BLOG_LLM_API_KEY"),
        blog_llm_model=_env("BLOG_LLM_MODEL", "gpt-4.1"),
        research_llm_base_url=_env("RESEARCH_LLM_BASE_URL", os.getenv("BLOG_LLM_BASE_URL", "https://api.openai.com/v1")),
        research_llm_api_key=_env_opt("RESEARCH_LLM_API_KEY") or _env_opt("BLOG_LLM_API_KEY"),
        research_llm_model=_env("RESEARCH_LLM_MODEL", os.getenv("BLOG_LLM_MODEL", "gpt-4.1")),
        slides_default_count=int(_env("SLIDES_DEFAULT_COUNT", "5")),
        slides_default_lang=_env("SLIDES_DEFAULT_LANG", "en"),
        trending_api_url=_env("TRENDING_API_URL", "https://api.rag.ac.cn/trending_arxiv_papers/api/trending"),
        trending_limit=int(_env("TRENDING_LIMIT", "30")),
        trending_top_artifact_count=int(_env("TRENDING_TOP_ARTIFACT_COUNT", "3")),
        trending_cover_subdir=_env("TRENDING_COVER_SUBDIR", "cover"),
        trending_cover_dpi=int(_env("TRENDING_COVER_DPI", "160")),
        trending_prewarm_concurrency=int(_env("TRENDING_PREWARM_CONCURRENCY", "3")),
    )
