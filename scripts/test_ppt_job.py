#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import boto3
import httpx


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings


def build_s3_client():
    settings = get_settings()
    kwargs: dict[str, Any] = {"service_name": "s3", "region_name": settings.s3_region}
    if settings.s3_endpoint:
        kwargs["endpoint_url"] = settings.s3_endpoint
    if settings.s3_access_key and settings.s3_secret_key:
        kwargs["aws_access_key_id"] = settings.s3_access_key
        kwargs["aws_secret_access_key"] = settings.s3_secret_key
    return boto3.client(**kwargs), settings.s3_bucket


def download_s3_bytes(key: str) -> bytes:
    client, bucket = build_s3_client()
    obj = client.get_object(Bucket=bucket, Key=key)
    return obj["Body"].read()


def download_s3_text(key: str) -> str:
    return download_s3_bytes(key).decode("utf-8")


def poll_job(base_url: str, job_id: str, interval_sec: int, timeout_sec: int) -> dict[str, Any]:
    started = time.time()
    with httpx.Client(timeout=None) as client:
        while True:
            try:
                response = client.get(f"{base_url.rstrip('/')}/v1/ppt/jobs/{job_id}")
                response.raise_for_status()
                payload = response.json()
            except httpx.TimeoutException as exc:
                now = datetime.now().strftime("%H:%M:%S")
                print(f"[{now}] poll timeout: {type(exc).__name__}. Will retry in {interval_sec}s.")
                if time.time() - started > timeout_sec:
                    raise TimeoutError(f"Polling timed out after {timeout_sec}s") from exc
                time.sleep(interval_sec)
                continue
            now = datetime.now().strftime("%H:%M:%S")
            print(f"[{now}] polled job:")
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            if payload.get("status") in {"succeeded", "failed"}:
                return payload
            if time.time() - started > timeout_sec:
                raise TimeoutError(f"Polling timed out after {timeout_sec}s")
            time.sleep(interval_sec)


def save_outputs(result_payload: dict[str, Any], output_root: Path) -> dict[str, Any]:
    paper_id = str(result_payload["paper_id"]).replace("/", "_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = output_root / f"{timestamp}_{paper_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    slide_files: list[str] = []
    for slide in result_payload.get("slides", []):
        index = int(slide["index"])
        s3_key = slide["s3_key"]
        suffix = Path(s3_key).suffix or ".png"
        local_path = output_dir / f"slide_{index}{suffix}"
        local_path.write_bytes(download_s3_bytes(s3_key))
        slide_files.append(str(local_path))

    style_path = None
    style_key = result_payload.get("style_content_s3_key")
    if style_key:
        style_path = output_dir / "style_content_filled.json"
        style_path.write_text(download_s3_text(style_key), encoding="utf-8")

    result_path = output_dir / "result.json"
    result_path.write_text(json.dumps(result_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "output_dir": str(output_dir),
        "slides": slide_files,
        "style_content": str(style_path) if style_path else "",
        "result_json": str(result_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Submit a PPT generation job and poll every 10 seconds.")
    parser.add_argument("--paper-id", required=True)
    parser.add_argument("--slide-count", type=int, default=5)
    parser.add_argument("--language", default=None)
    parser.add_argument("--force", action="store_true", help="Ignore cached S3 PPT result and regenerate.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    parser.add_argument("--poll-interval", type=int, default=10)
    parser.add_argument("--timeout", type=int, default=10800)
    parser.add_argument("--request-timeout", type=int, default=300, help="Per-request timeout in seconds for create/result HTTP calls.")
    parser.add_argument("--output-dir", default=str(ROOT / "outputs" / "ppt_tests"))
    args = parser.parse_args()

    payload = {"paper_id": args.paper_id, "slide_count": args.slide_count, "force": args.force}
    if args.language:
        payload["language"] = args.language

    with httpx.Client(timeout=args.request_timeout) as client:
        response = client.post(
            f"{args.base_url.rstrip('/')}/v1/ppt/jobs",
            json=payload,
        )
        response.raise_for_status()
        created = response.json()

    print(json.dumps({"created": created}, ensure_ascii=False, indent=2))
    job_detail = poll_job(args.base_url, created["job_id"], args.poll_interval, args.timeout)

    if job_detail["status"] != "succeeded":
        print(json.dumps({"ok": False, "job": job_detail}, ensure_ascii=False, indent=2))
        return 1

    with httpx.Client(timeout=args.request_timeout) as client:
        result_response = client.get(f"{args.base_url.rstrip('/')}/v1/ppt/jobs/{created['job_id']}/result")
        result_response.raise_for_status()
        result_payload = result_response.json()

    output_paths = save_outputs(result_payload, Path(args.output_dir))
    print(json.dumps({"ok": True, "result": result_payload, "files": output_paths}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
