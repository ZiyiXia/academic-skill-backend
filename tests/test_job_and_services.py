import asyncio
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

    def read_bytes(self, key: str) -> bytes:
        return self.objects[key]

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

    async def exists_async(self, key: str) -> bool:
        return self.exists(key)

    async def read_text_async(self, key: str) -> str:
        return self.read_text(key)

    async def read_bytes_async(self, key: str) -> bytes:
        return self.read_bytes(key)

    async def write_text_async(self, key: str, content: str, content_type: str = "text/plain; charset=utf-8") -> None:
        self.write_text(key, content, content_type)

    async def write_json_async(self, key: str, payload: dict) -> None:
        self.write_json(key, payload)

    async def read_json_async(self, key: str) -> dict:
        return self.read_json(key)

    async def upload_bytes_with_retry_async(self, key: str, data: bytes, content_type: str, *, attempts: int = 4, backoff_sec: float = 2.0) -> None:
        self.upload_bytes(key, data, content_type)

    async def list_keys_async(self, prefix: str) -> list[str]:
        return self.list_keys(prefix)

    async def presign_get_url_async(self, key: str, expires_in_seconds: int = 1800) -> str:
        return f"https://example.com/download/{key}?expires={expires_in_seconds}"


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
    react_messages = iter([
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_search_1",
                    "type": "function",
                    "function": {
                        "name": "search_papers",
                        "arguments": '{"query":"transformer scaling"}',
                    },
                }
            ],
        },
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_brief_1",
                    "type": "function",
                    "function": {
                        "name": "get_paper_brief",
                        "arguments": '{"arxiv_id":"1706.03762"}',
                    },
                }
            ],
        },
        {
            "role": "assistant",
            "content": "I have enough evidence to write the report.",
        },
    ])

    async def fake_chat_completion(*, messages, tools=None, tool_choice=None):
        return next(react_messages)

    async def fake_chat_completion_text(messages):
        return (
            "{"
            '"title":"Transformer Scaling Report",'
            '"markdown":"# Transformer Scaling Report\\n\\n'
            'Transformers remain dominant but face efficiency bottlenecks. '
            'This mocked report is intentionally long enough to pass markdown length checks. '
            'It summarizes representative methods, tradeoffs, and limitations in current scaling practice. '
            'Attention Is All You Need remains a foundational reference and later work focuses on efficiency, '
            'context extension, and systems-level optimization for large-scale training and inference. '
            'The report also emphasizes data quality and evaluation protocol design as practical bottlenecks."'
            "}"
        )

    async def fake_search_papers(search_query_args: dict):
        return {
            "status": "success",
            "query": search_query_args["query"],
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

    monkeypatch.setattr(service, "_chat_completion", fake_chat_completion)
    monkeypatch.setattr(service, "_chat_completion_text", fake_chat_completion_text)
    monkeypatch.setattr(service, "_search_papers", fake_search_papers)
    monkeypatch.setattr(service, "_inspect_paper", fake_inspect_paper)

    result = await service.run(ResearchRequest(query="transformer scaling"))
    assert result.status == "success"
    assert result.report["title"] == "Transformer Scaling Report"
    tool_steps = [step for step in result.report["tool_trace"] if step.get("type") == "tool"]
    assert tool_steps[0]["tool"] == "search_papers"
    assert tool_steps[1]["tool"] == "get_paper_brief"


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
async def test_blog_result_returns_presigned_download_url():
    settings = build_settings()
    storage = FakeStorage()
    jobs = JobService(storage, settings)
    service = BlogService(settings, storage, jobs)
    generated_at = datetime.now(timezone.utc).isoformat()
    meta = jobs.create_meta(
        "blog",
        "1234.5678",
        status="succeeded",
        progress=100,
        stage="complete",
        result={
            "paper_id": "1234.5678",
            "generated_at": generated_at,
            "markdown_s3_key": "deepxiv/blogs/1234.5678/blog/blog.md",
        },
    )
    jobs.save_meta(meta)

    result = await service.get_result(meta.job_id)
    assert result.paper_id == "1234.5678"
    assert result.expires_in_seconds == 1800
    assert result.download_url.endswith("deepxiv/blogs/1234.5678/blog/blog.md?expires=1800")


@pytest.mark.asyncio
async def test_blog_reuses_running_job_id(monkeypatch):
    settings = build_settings()
    storage = FakeStorage()
    jobs = JobService(storage, settings)
    service = BlogService(settings, storage, jobs)
    blocker = asyncio.Event()

    async def fake_run_job(meta, *, force: bool = False):
        await blocker.wait()
        return {
            "paper_id": meta.paper_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "markdown_s3_key": service.keys_for(meta.paper_id)["blog_markdown"],
        }

    monkeypatch.setattr(service, "_run_job", fake_run_job)

    first = await service.create_job(CreateBlogJobRequest(paper_id="1234.5678", force=True))
    second = await service.create_job(CreateBlogJobRequest(paper_id="1234.5678", force=True))

    assert first.job_id == second.job_id
    blocker.set()
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_blog_create_job_persists_meta_before_return():
    settings = build_settings()
    storage = FakeStorage()
    jobs = JobService(storage, settings)
    service = BlogService(settings, storage, jobs)
    keys = service.keys_for("1234.5678")
    storage.write_text(keys["blog_markdown"], "# Blog")
    storage.write_json(keys["blog_meta"], {"generated_at": datetime.now(timezone.utc).isoformat()})

    created = await service.create_job(CreateBlogJobRequest(paper_id="1234.5678"))
    detail = await service.get_job(created.job_id)

    assert detail.job_id == created.job_id
    assert detail.status == "succeeded"


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
async def test_ppt_result_returns_presigned_download_url():
    settings = build_settings()
    storage = FakeStorage()
    jobs = JobService(storage, settings)
    service = PptService(settings, storage, jobs)
    paper_id = "1234.5678"
    generated_at = datetime.now(timezone.utc).isoformat()
    slide_key = service._slide_key(paper_id, 1)
    storage.upload_bytes(slide_key, b"fake-png", "image/png")
    meta = jobs.create_meta(
        "ppt",
        paper_id,
        status="succeeded",
        progress=100,
        stage="complete",
        result={
            "paper_id": paper_id,
            "generated_at": generated_at,
            "slides": [{"index": 1, "s3_key": slide_key}],
        },
    )
    jobs.save_meta(meta)

    async def fake_ensure_pdf_artifact(paper_id_arg: str, slides: list[dict]) -> str:
        assert paper_id_arg == paper_id
        assert slides[0]["s3_key"] == slide_key
        return service._pdf_key(paper_id_arg)

    service._ensure_pdf_artifact = fake_ensure_pdf_artifact  # type: ignore[method-assign]

    result = await service.get_result(meta.job_id)
    assert result.paper_id == paper_id
    assert result.expires_in_seconds == 1800
    assert result.download_url.endswith(f"{service._pdf_key(paper_id)}?expires=1800")


@pytest.mark.asyncio
async def test_ppt_uses_recreate_outline_when_outline_artifacts_are_missing(monkeypatch):
    settings = build_settings()
    storage = FakeStorage()
    jobs = JobService(storage, settings)
    service = PptService(settings, storage, jobs)
    keys = service.blogs.keys_for("1234.5678")
    calls = {"recreate": 0, "ensure": 0}

    async def fake_recreate(paper_id: str, meta=None) -> None:
        calls["recreate"] += 1
        storage.write_text(keys["style_json"], "{\"slides\": []}")
        storage.write_text(keys["content_json"], "{\"slides\": []}")

    async def fake_ensure(paper_id: str, *, force_init: bool = False, meta=None) -> None:
        calls["ensure"] += 1

    async def fake_wait_for_slides(paper_id: str, expected_count: int, attempts: int = 15, interval_sec: int = 2) -> list[dict]:
        return [{"index": idx + 1, "s3_key": service._slide_key(paper_id, idx + 1)} for idx in range(expected_count)]

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        async def aiter_lines(self):
            yield 'data: {"event":"result","stage":"complete"}'

    class FakeStream:
        async def __aenter__(self):
            return FakeResponse()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, *args, **kwargs):
            return FakeStream()

    monkeypatch.setattr(service.blogs, "ensure_outline_from_existing_ocr", fake_recreate)
    monkeypatch.setattr(service.blogs, "ensure_prerequisites", fake_ensure)
    monkeypatch.setattr(service, "_wait_for_slides", fake_wait_for_slides)
    monkeypatch.setattr("app.services.ppt.httpx.AsyncClient", FakeClient)

    result = await service._run_job(jobs.create_meta("ppt", "1234.5678"))
    assert calls["recreate"] == 1
    assert calls["ensure"] == 0
    assert len(result["slides"]) == settings.slides_default_count
