import json
import asyncio
import time
from collections.abc import Iterable
from typing import Any, Optional

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import Settings


class S3Storage:
    def __init__(self, settings: Settings):
        kwargs: dict[str, Any] = {
            "service_name": "s3",
            "region_name": settings.s3_region,
            "config": Config(
                connect_timeout=10,
                read_timeout=300,
                retries={"max_attempts": 3, "mode": "standard"},
                # Some S3-compatible gateways return non-AWS checksum headers.
                # Restrict checksum behavior to explicitly required cases to avoid
                # false mismatch errors on put/get object.
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        }
        if settings.s3_endpoint:
            kwargs["endpoint_url"] = settings.s3_endpoint
        if settings.s3_access_key and settings.s3_secret_key:
            kwargs["aws_access_key_id"] = settings.s3_access_key
            kwargs["aws_secret_access_key"] = settings.s3_secret_key
        self.bucket = settings.s3_bucket
        self.client: BaseClient = boto3.client(**kwargs)

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            code = exc.response.get("Error", {}).get("Code")
            if status == 404 or code in {"404", "NotFound", "NoSuchKey"}:
                return False
            raise

    def read_text(self, key: str) -> str:
        obj = self.client.get_object(Bucket=self.bucket, Key=key)
        return obj["Body"].read().decode("utf-8")

    def write_text(self, key: str, content: str, content_type: str = "text/plain; charset=utf-8") -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=content.encode("utf-8"), ContentType=content_type)

    def write_json(self, key: str, payload: dict[str, Any]) -> None:
        self.write_text(key, json.dumps(payload, ensure_ascii=False, indent=2), "application/json; charset=utf-8")

    def read_json(self, key: str) -> dict[str, Any]:
        return json.loads(self.read_text(key))

    def upload_bytes(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def upload_bytes_with_retry(
        self,
        key: str,
        data: bytes,
        content_type: str,
        *,
        attempts: int = 4,
        backoff_sec: float = 2.0,
    ) -> None:
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                self.upload_bytes(key, data, content_type)
                return
            except Exception as exc:
                last_error = exc
                if attempt >= attempts:
                    raise
                time.sleep(backoff_sec * attempt)
        if last_error is not None:
            raise last_error

    async def exists_async(self, key: str) -> bool:
        return await asyncio.to_thread(self.exists, key)

    async def read_text_async(self, key: str) -> str:
        return await asyncio.to_thread(self.read_text, key)

    async def write_text_async(self, key: str, content: str, content_type: str = "text/plain; charset=utf-8") -> None:
        await asyncio.to_thread(self.write_text, key, content, content_type)

    async def write_json_async(self, key: str, payload: dict[str, Any]) -> None:
        await asyncio.to_thread(self.write_json, key, payload)

    async def read_json_async(self, key: str) -> dict[str, Any]:
        return await asyncio.to_thread(self.read_json, key)

    async def upload_bytes_with_retry_async(
        self,
        key: str,
        data: bytes,
        content_type: str,
        *,
        attempts: int = 4,
        backoff_sec: float = 2.0,
    ) -> None:
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                await asyncio.to_thread(self.upload_bytes, key, data, content_type)
                return
            except Exception as exc:
                last_error = exc
                if attempt >= attempts:
                    raise
                await asyncio.sleep(backoff_sec * attempt)
        if last_error is not None:
            raise last_error

    async def list_keys_async(self, prefix: str) -> list[str]:
        return await asyncio.to_thread(self.list_keys, prefix)

    def presign_get_url(self, key: str, expires_in_seconds: int = 1800) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in_seconds,
        )

    async def presign_get_url_async(self, key: str, expires_in_seconds: int = 1800) -> str:
        return await asyncio.to_thread(self.presign_get_url, key, expires_in_seconds)

    def list_keys(self, prefix: str) -> list[str]:
        paginator = self.client.get_paginator("list_objects_v2")
        keys: list[str] = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                key = item.get("Key")
                if key:
                    keys.append(key)
        return keys

    def find_first_existing(self, keys: Iterable[str]) -> Optional[str]:
        for key in keys:
            if self.exists(key):
                return key
        return None
