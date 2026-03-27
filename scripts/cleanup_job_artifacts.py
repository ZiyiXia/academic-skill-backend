#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.schemas.jobs import JobMeta
from app.storage.s3 import S3Storage


def main() -> int:
    parser = argparse.ArgumentParser(description="Delete expired per-job temporary artifacts from S3.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    storage = S3Storage(settings)
    now = datetime.now(timezone.utc)
    job_keys = storage.list_keys(f"{settings.skill_job_prefix.rstrip('/')}/")

    cleaned: list[dict] = []
    for job_key in job_keys:
        if not job_key.endswith("/meta.json"):
            continue
        try:
            meta = JobMeta.model_validate(storage.read_json(job_key))
        except Exception as exc:
            cleaned.append({"job_key": job_key, "status": "invalid_meta", "error": str(exc)})
            continue

        if not meta.temp_prefix or not meta.cleanup_after:
            continue
        if meta.cleanup_after > now:
            continue

        deleted_count = 0
        if not args.dry_run:
            deleted_count = storage.delete_prefix(meta.temp_prefix)
            updated = meta.model_copy(update={"temp_prefix": None, "cleanup_after": None, "updated_at": now})
            storage.write_json(job_key, updated.model_dump(mode="json"))
        cleaned.append(
            {
                "job_id": meta.job_id,
                "job_type": meta.job_type,
                "paper_id": meta.paper_id,
                "temp_prefix": meta.temp_prefix,
                "deleted_count": deleted_count,
                "dry_run": args.dry_run,
            }
        )

    print(json.dumps({"cleaned": cleaned, "count": len(cleaned), "dry_run": args.dry_run}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
