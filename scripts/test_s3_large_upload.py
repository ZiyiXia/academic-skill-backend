#!/usr/bin/env python
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings


def build_s3_client():
    settings = get_settings()
    kwargs: dict[str, Any] = {
        "service_name": "s3",
        "region_name": settings.s3_region,
        "config": Config(connect_timeout=10, read_timeout=300, retries={"max_attempts": 2}),
    }
    if settings.s3_endpoint:
        kwargs["endpoint_url"] = settings.s3_endpoint
    if settings.s3_access_key and settings.s3_secret_key:
        kwargs["aws_access_key_id"] = settings.s3_access_key
        kwargs["aws_secret_access_key"] = settings.s3_secret_key
    return boto3.client(**kwargs), settings.s3_bucket


def make_payload(size_mb: int) -> bytes:
    chunk = b"academic-skill-s3-probe-"
    target = size_mb * 1024 * 1024
    repeats = (target // len(chunk)) + 1
    data = (chunk * repeats)[:target]
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload/download/delete a large probe object in S3.")
    parser.add_argument("--size-mb", type=int, default=20)
    parser.add_argument("--prefix", default="academic-skill/probes")
    args = parser.parse_args()

    client, bucket = build_s3_client()
    payload = make_payload(args.size_mb)
    digest = hashlib.sha256(payload).hexdigest()
    key = f"{args.prefix.rstrip('/')}/{uuid.uuid4().hex}_{args.size_mb}mb.bin"

    results: dict[str, Any] = {
        "bucket": bucket,
        "key": key,
        "size_mb": args.size_mb,
        "bytes": len(payload),
        "sha256": digest,
    }

    started = time.time()
    client.put_object(Bucket=bucket, Key=key, Body=payload, ContentType="application/octet-stream")
    results["put_object_seconds"] = round(time.time() - started, 3)

    started = time.time()
    obj = client.get_object(Bucket=bucket, Key=key)
    downloaded = obj["Body"].read()
    results["get_object_seconds"] = round(time.time() - started, 3)
    results["downloaded_sha256"] = hashlib.sha256(downloaded).hexdigest()
    results["matches"] = results["downloaded_sha256"] == digest

    started = time.time()
    client.delete_object(Bucket=bucket, Key=key)
    results["delete_object_seconds"] = round(time.time() - started, 3)

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
