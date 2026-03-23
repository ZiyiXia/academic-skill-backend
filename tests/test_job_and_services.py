from datetime import datetime, timezone

import pytest

from app.core.config import Settings
from app.schemas.jobs import CreateBlogJobRequest, CreatePptJobRequest
from app.schemas.research import ResearchRequest
from app.services.blog import BlogService
from app.services.jobs import JobService
from app.services.ppt import PptService
from app.services.research import ResearchService


class FakeStorage:
    def __init__(self):
        self.objects = {}

    def exists(self, key: str) -> bool:
        return key in self.objects

    def read_text(self, key: str) -> str:
        return self.objects[key].decode("utf-8")

    def write_text(self, key: str, content: str, content_type: str = "text/plain; charset=utf-8") -> None:
        self.objects[key] = content.encode("utf-8")

    def write_json(self, key: str, payload: dict) -> None:
        import json
        self.write_text(key, json.dumps(payload, ensure_ascii=False))

    def read_json(self, key: str) -> dict:
        import json
        return json.loads(self.read_text(key))

    def upload_bytes(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = data

    def list_keys(self, prefix: str) -> list[str]:
        return [key for key in self.objects if key.startswith(prefix)]


def build_settings() -> Settings:
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
        s3_endpoint=None,
        s3_access_key=None,
        s3_secret_key=None,
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


@pytest.mark.asyncio
async def test_research_generates_report_with_mocked_tools(monkeypatch):
    service = ResearchService(build_settings())
    llm_responses = iter([
        {
            "goal": "Study transformer scaling",
            "angle": "Focus on representative methods and bottlenecks",
            "sub_questions": ["What methods dominate?", "What are the main bottlenecks?"],
            "search_queries": ["transformer scaling", "transformer scaling limitations"],
            "focus_aspects": ["methods", "limitations"],
            "finish_criteria": ["Enough evidence collected"],
        },
        {
            "action": "inspect",
            "arxiv_id": "1706.03762",
            "inspect_type": "brief",
            "why": "Need a representative landmark paper",
        },
        {
            "action": "finish",
            "reason": "Enough evidence collected",
        },
        {
            "title": "Transformer Scaling Report",
            "executive_summary": "Transformers remain dominant but face efficiency bottlenecks.",
            "key_findings": ["Transformers remain dominant.", "Efficiency is a bottleneck."],
            "sections": [{"heading": "Landscape", "content": "Transformers dominate the area."}],
            "notable_papers": [
                {
                    "arxiv_id": "1706.03762",
                    "title": "Attention Is All You Need",
                    "contribution": "Introduced the Transformer.",
                    "evidence": ["Transformer replaces recurrence with attention."],
                }
            ],
            "limitations": ["Limited to retrieved evidence."],
            "follow_up_questions": ["How do scaling laws differ across domains?"],
            "markdown": "# Transformer Scaling Report",
        },
    ])

    async def fake_complete_json(system_prompt: str, user_prompt: str):
        return next(llm_responses)

    async def fake_search_papers(query: str, top_k: int):
        return {
            "status": "success",
            "query": query,
            "total": 1,
            "items": [
                {
                    "paper_id": "1706.03762",
                    "title": "Attention Is All You Need",
                    "abstract": "Introduces the Transformer architecture.",
                    "score": 42.0,
                    "url": "https://arxiv.org/abs/1706.03762",
                    "date": "2017-06-12",
                    "authors": ["Ashish Vaswani"],
                }
            ],
        }

    async def fake_inspect_paper(arxiv_id: str, inspect_type: str, *, section_name=None):
        assert arxiv_id == "1706.03762"
        assert inspect_type == "brief"
        return {
            "arxiv_id": arxiv_id,
            "title": "Attention Is All You Need",
            "tldr": "Transformer replaces recurrence with attention mechanisms.",
        }

    monkeypatch.setattr(service, "_complete_json", fake_complete_json)
    monkeypatch.setattr(service, "_search_papers", fake_search_papers)
    monkeypatch.setattr(service, "_inspect_paper", fake_inspect_paper)

    result = await service.run(ResearchRequest(query="transformer scaling"))
    assert result.status == "success"
    assert result.report["title"] == "Transformer Scaling Report"
    assert result.report["tool_trace"][1]["tool"] == "search"
    assert result.report["tool_trace"][3]["tool"] == "arxiv:brief"


@pytest.mark.asyncio
async def test_blog_cached_result_short_circuits_generation():
    settings = build_settings()
    storage = FakeStorage()
    jobs = JobService(storage, settings)
    service = BlogService(settings, storage, jobs)
    keys = service.keys_for("1234.5678")
    storage.write_text(keys["blog_markdown"], "# Blog")
    storage.write_json(keys["blog_meta"], {"generated_at": datetime.now(timezone.utc).isoformat()})

    created = await service.create_job(CreateBlogJobRequest(paper_id="1234.5678"))
    assert created.status == "succeeded"
    detail = await service.get_job(created.job_id)
    assert detail.result["markdown_s3_key"] == keys["blog_markdown"]


@pytest.mark.asyncio
async def test_ppt_cached_result_short_circuits_generation():
    settings = build_settings()
    storage = FakeStorage()
    jobs = JobService(storage, settings)
    service = PptService(settings, storage, jobs)
    prefix = service._slides_prefix("1234.5678")
    for index in range(1, settings.slides_default_count + 1):
        storage.upload_bytes(f"{prefix}/slide_{index}.png", b"png", "image/png")

    created = await service.create_job(CreatePptJobRequest(paper_id="1234.5678"))
    assert created.status == "succeeded"
    detail = await service.get_job(created.job_id)
    assert len(detail.result["slides"]) == settings.slides_default_count


@pytest.mark.asyncio
async def test_ppt_uses_recreate_outline_when_outline_artifacts_are_missing(monkeypatch):
    settings = build_settings()
    storage = FakeStorage()
    jobs = JobService(storage, settings)
    service = PptService(settings, storage, jobs)
    keys = service.blogs.keys_for("1234.5678")
    calls = {"recreate": 0, "ensure": 0}

    async def fake_recreate(paper_id: str) -> None:
        calls["recreate"] += 1
        storage.write_text(keys["style_json"], "{\"slides\": []}")
        storage.write_text(keys["content_json"], "{\"slides\": []}")

    async def fake_ensure(paper_id: str, *, force_init: bool = False) -> None:
        calls["ensure"] += 1

    async def fake_wait_for_slides(paper_id: str, expected_count: int, attempts: int = 15, interval_sec: int = 2) -> list[dict]:
        return [{"index": idx + 1, "s3_key": service._slide_key(paper_id, idx + 1)} for idx in range(expected_count)]

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        async def aiter_lines(self):
            yield 'data: {"event":"result","stage":"complete"}'

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(service.blogs, "ensure_outline_from_existing_ocr", fake_recreate)
    monkeypatch.setattr(service.blogs, "ensure_prerequisites", fake_ensure)
    monkeypatch.setattr(service, "_wait_for_slides", fake_wait_for_slides)
    monkeypatch.setattr("app.services.ppt.httpx.AsyncClient", FakeClient)

    result = await service._run_job(jobs.create_meta("ppt", "1234.5678"))
    assert calls["recreate"] == 1
    assert calls["ensure"] == 0
    assert len(result["slides"]) == settings.slides_default_count
