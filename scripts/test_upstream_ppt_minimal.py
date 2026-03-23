#!/usr/bin/env python
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.storage.s3 import S3Storage


async def sse_post(url: str, payload: dict[str, Any], timeout_sec: int = 1800) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    events: list[dict[str, Any]] = []
    result_event: dict[str, Any] | None = None
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream(
            "POST",
            url,
            json=payload,
            headers={"Accept": "text/event-stream", "Content-Type": "application/json"},
        ) as response:
            response.raise_for_status()
            line_iter = response.aiter_lines().__aiter__()
            while True:
                try:
                    line = await asyncio.wait_for(line_iter.__anext__(), timeout=timeout_sec)
                except StopAsyncIteration:
                    break
                if not line.startswith("data:"):
                    continue
                raw = line.replace("data:", "", 1).strip()
                if not raw:
                    continue
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                events.append(event)
                stage = event.get("stage")
                progress = event.get("progress")
                content = event.get("content") or event.get("message")
                print(json.dumps({"stage": stage, "progress": progress, "content": content}, ensure_ascii=False))
                if event.get("event") == "result" or stage == "complete":
                    result_event = event
                    break
                if event.get("event") == "error":
                    raise RuntimeError(str(content or "upstream error"))
    return events, result_event


async def download_pdf_bytes(paper_id: str, arxiv_base: str) -> bytes:
    url = f"{arxiv_base.rstrip('/')}/{paper_id}.pdf"
    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        return response.content


async def main() -> int:
    parser = argparse.ArgumentParser(description="Minimal upstream PPT probe using only S3 + initStyleJson + createSlides.")
    parser.add_argument("--paper-id", required=True)
    parser.add_argument("--slide-count", type=int, default=5)
    parser.add_argument("--language", default="English")
    parser.add_argument("--base-url", default="http://120.92.112.87:32500")
    parser.add_argument("--prefix", default="academic-skill/upstream-probes")
    args = parser.parse_args()

    settings = get_settings()
    storage = S3Storage(settings)
    task_id = f"probe-{args.paper_id.replace('/', '-')}-{uuid.uuid4().hex[:8]}"
    base = f"{args.prefix.rstrip('/')}/{task_id}"
    source_pdf = f"{base}/source/paper.pdf"
    ocr_prefix = f"{base}/ocr"
    content_json = f"{base}/gen/content.json"
    style_json = f"{base}/gen/style_content.json"
    slides_prefix = f"{base}/slides"
    slide_paths = [f"{slides_prefix}/slide_{idx + 1}.png" for idx in range(args.slide_count)]
    style_filled = f"{slides_prefix}/style_content_filled.json"

    started_all = time.time()

    pdf_started = time.time()
    pdf_bytes = await download_pdf_bytes(args.paper_id, settings.arxiv_pdf_base_url)
    await storage.upload_bytes_with_retry_async(source_pdf, pdf_bytes, "application/pdf")
    pdf_elapsed = round(time.time() - pdf_started, 3)

    init_payload = {
        "taskId": task_id,
        "version": 1,
        "paperUrls": [source_pdf],
        "textPrompt": "Academic style",
        "slideCount": args.slide_count,
        "language": args.language,
        "ocrResultToSavePath": ocr_prefix,
        "styleContentJsonToSavePath": style_json,
        "contentJsonToSavePath": content_json,
    }

    init_started = time.time()
    _, init_result = await sse_post(f"{args.base_url.rstrip('/')}/api/v1/ppt/initStyleJson", init_payload)
    init_elapsed = round(time.time() - init_started, 3)

    if init_result and isinstance(init_result.get("data"), dict):
        style_data = init_result["data"]
        style_content_raw = json.dumps(style_data, ensure_ascii=False)
    else:
        style_content_raw = await storage.read_text_async(style_json)

    create_payload = {
        "taskId": f"{task_id}-slides",
        "version": 1,
        "styleContentJson": style_content_raw,
        "textPrompt": f"{args.language} academic style",
        "slideCount": args.slide_count,
        "slideToSavePaths": slide_paths,
        "styleContentJsonToSave": style_filled,
    }

    slides_started = time.time()
    _, slides_result = await sse_post(f"{args.base_url.rstrip('/')}/api/v1/ppt/createSlides", create_payload)
    slides_elapsed = round(time.time() - slides_started, 3)

    total_elapsed = round(time.time() - started_all, 3)
    slides_existing = 0
    for slide_key in slide_paths:
        if await storage.exists_async(slide_key):
            slides_existing += 1

    print(json.dumps({
        "ok": True,
        "paper_id": args.paper_id,
        "task_id": task_id,
        "pdf_upload_seconds": pdf_elapsed,
        "init_style_json_seconds": init_elapsed,
        "create_slides_seconds": slides_elapsed,
        "total_seconds": total_elapsed,
        "slides_existing": slides_existing,
        "style_json_key": style_json,
        "style_filled_key": style_filled,
        "last_result_stage": (slides_result or {}).get("stage"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
