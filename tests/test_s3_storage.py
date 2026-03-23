from botocore.config import Config

from app.core.config import Settings
from app.storage.s3 import S3Storage


def _build_settings() -> Settings:
    return Settings(
        app_name="academic-skill-backend",
        app_env="test",
        log_level="INFO",
        search_api_url="http://example.com/search",
        ppt_create_url="http://example.com/ppt",
        arxiv_pdf_base_url="https://arxiv.org/pdf",
        rag_api_base_url="https://example.com/rag",
        rag_api_token="token",
        s3_bucket="bucket",
        s3_region="us-east-1",
        s3_endpoint="http://example.com/s3",
        s3_access_key="key",
        s3_secret_key="secret",
        blog_s3_prefix="deepxiv/blogs",
        slides_s3_subdir="slides",
        skill_job_prefix="academic-skill/jobs",
        blog_image_gen_url="http://example.com/image-gen",
        blog_llm_base_url="https://api.example.com/v1",
        blog_llm_api_key="key",
        blog_llm_model="model",
        research_llm_base_url="https://api.example.com/v1",
        research_llm_api_key="key",
        research_llm_model="model",
        slides_default_count=5,
        slides_default_lang="en",
    )


def test_s3_client_uses_required_checksum_mode(monkeypatch):
    captured = {}

    def fake_client(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("app.storage.s3.boto3.client", fake_client)
    S3Storage(_build_settings())

    config = captured["config"]
    assert isinstance(config, Config)
    assert config.request_checksum_calculation == "when_required"
    assert config.response_checksum_validation == "when_required"
