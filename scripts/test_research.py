#!/usr/bin/env python
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import Settings, get_settings
from app.schemas.research import ResearchRequest
from app.services.research import ResearchService


def build_mock_settings() -> Settings:
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
        research_llm_model="research-model",
        slides_default_count=5,
        slides_default_lang="en",
    )


def print_result(title: str, payload: dict[str, Any]) -> None:
    print(f"[{title}]")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print()


def write_output_files(report_payload: dict[str, Any], query: str, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = "-".join(query.strip().lower().split())[:60] or "research"
    json_path = output_dir / f"{timestamp}_{slug}.json"
    md_path = output_dir / f"{timestamp}_{slug}.md"

    json_path.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    markdown = report_payload.get("report", {}).get("markdown")
    if not isinstance(markdown, str) or not markdown.strip():
        markdown = json.dumps(report_payload.get("report", {}), ensure_ascii=False, indent=2)
    md_path.write_text(markdown, encoding="utf-8")

    return {
        "json": str(json_path),
        "markdown": str(md_path),
    }


async def run_mock_test(query: str) -> int:
    service = ResearchService(build_mock_settings())
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
                        "arguments": json.dumps({"query": query, "top_k": 3}, ensure_ascii=False),
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
                        "arguments": json.dumps({"arxiv_id": "1706.03762"}, ensure_ascii=False),
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
        return json.dumps(
            {
                "title": "Mock Research Report",
                "executive_summary": "Transformers remain dominant but face efficiency bottlenecks.",
                "key_findings": ["Transformers remain dominant.", "Efficiency is a bottleneck."],
                "sections": [
                    {
                        "heading": "Landscape",
                        "content": "Transformers dominate the area because attention-based sequence modeling has become the standard baseline across many modern systems.",
                    },
                    {
                        "heading": "Evidence",
                        "content": "Attention Is All You Need is treated as a representative reference point in this mocked run, and the brief inspection confirms its central role in replacing recurrence with attention mechanisms.",
                    },
                    {
                        "heading": "Implications",
                        "content": "The practical implication is that any serious analysis of transformer-era retrieval or reasoning systems still needs to anchor itself in this architectural shift.",
                    },
                ],
                "notable_papers": [
                    {
                        "arxiv_id": "1706.03762",
                        "title": "Attention Is All You Need",
                        "contribution": "Introduced the Transformer.",
                        "evidence": ["Transformer replaces recurrence with attention."],
                    }
                ],
                "limitations": ["Limited to mocked evidence."],
                "follow_up_questions": ["How do scaling laws differ across domains?"],
                "markdown": "# Mock Research Report\n\n## Landscape\nTransformers dominate the area because attention-based sequence modeling has become the standard baseline across many modern systems.\n\n## Evidence\nAttention Is All You Need is treated as a representative reference point in this mocked run, and the brief inspection confirms its central role in replacing recurrence with attention mechanisms.\n\n## Implications\nThe practical implication is that any serious analysis of transformer-era retrieval or reasoning systems still needs to anchor itself in this architectural shift.\n\n## Recommendation\nUse this mocked report only as a structural validation of the ReACT flow rather than as a substantive literature review.",
            },
            ensure_ascii=False,
        )

    async def fake_search_papers(search_query_args: dict[str, Any]):
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
        return {
            "arxiv_id": arxiv_id,
            "title": "Attention Is All You Need",
            "tldr": "Transformer replaces recurrence with attention mechanisms.",
        }

    service._chat_completion = fake_chat_completion  # type: ignore[method-assign]
    service._chat_completion_text = fake_chat_completion_text  # type: ignore[method-assign]
    service._search_papers = fake_search_papers  # type: ignore[method-assign]
    service._inspect_paper = fake_inspect_paper  # type: ignore[method-assign]

    result = await service.run(ResearchRequest(query=query))
    ok = (
        result.status == "success"
        and isinstance(result.report, dict)
        and isinstance(result.report.get("title"), str)
        and bool(result.report.get("title"))
        and isinstance(result.report.get("tool_trace"), list)
        and isinstance(result.report.get("markdown"), str)
        and len(result.report.get("markdown", "")) > 300
    )
    print_result(
        "mock",
        {
            "ok": ok,
            "status": result.status,
            "message": result.message,
            "title": (result.report or {}).get("title"),
            "tool_trace_steps": len((result.report or {}).get("tool_trace", [])),
            "papers_considered": len((result.report or {}).get("papers_considered", [])),
        },
    )
    return 0 if ok else 1


async def run_live_test(query: str, base_url: str, timeout_sec: float, output_dir: Path) -> int:
    payload = {
        "query": query,
        "max_iterations": 2,
        "search_top_k": 3,
        "include_trace": True,
    }
    async with httpx.AsyncClient(timeout=timeout_sec) as client:
        response = await client.post(f"{base_url.rstrip('/')}/v1/research", json=payload)
    response.raise_for_status()
    data = response.json()
    report = data.get("report") or {}
    ok = data.get("status") == "success" and isinstance(report.get("title"), str) and bool(report.get("title"))
    output_paths = write_output_files(data, query, output_dir)
    print_result(
        "live",
        {
            "ok": ok,
            "http_status": response.status_code,
            "status": data.get("status"),
            "message": data.get("message"),
            "title": report.get("title"),
            "tool_trace_steps": len(report.get("tool_trace", [])) if isinstance(report.get("tool_trace"), list) else 0,
            "papers_considered": len(report.get("papers_considered", [])) if isinstance(report.get("papers_considered"), list) else 0,
            "output_json": output_paths["json"],
            "output_markdown": output_paths["markdown"],
        },
    )
    return 0 if ok else 1


async def main() -> int:
    parser = argparse.ArgumentParser(description="Test the research flow.")
    parser.add_argument("--query", default="Please help me find papers that propose new reinforcement learning algorithms which are direct, further optimizations of GRPO itself, rather than algorithms that apply the idea of GRPO to other scenarios or tasks.")
    parser.add_argument("--live", action="store_true", help="Call the running local API instead of the mocked service.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--output-dir", default=str(ROOT / "outputs" / "research_tests"))
    parser.add_argument("--print-config", action="store_true")
    args = parser.parse_args()

    if args.print_config:
        settings = get_settings()
        print_result(
            "config",
            {
                "search_api_url": settings.search_api_url,
                "rag_api_base_url": settings.rag_api_base_url,
                "research_llm_base_url": settings.research_llm_base_url,
                "research_llm_model": settings.research_llm_model,
            },
        )

    if args.live:
        try:
            return await run_live_test(args.query, args.base_url, args.timeout, Path(args.output_dir))
        except Exception as exc:
            print_result("live", {"ok": False, "error": f"{type(exc).__name__}: {exc}"})
            return 1

    try:
        return await run_mock_test(args.query)
    except Exception as exc:
        print_result("mock", {"ok": False, "error": f"{type(exc).__name__}: {exc}"})
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
