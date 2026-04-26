#!/usr/bin/env python
from __future__ import annotations

import argparse
import asyncio
import sys

from app.core.deps import get_trending_service


async def main() -> int:
    parser = argparse.ArgumentParser(description="Prewarm daily trending paper artifacts.")
    parser.add_argument("--force", action="store_true", help="Regenerate existing cover/blog/slides artifacts.")
    parser.add_argument("--limit", type=int, default=None, help="Number of trending papers to fetch.")
    parser.add_argument("--top-artifact-count", type=int, default=None, help="How many top papers get blog and slides.")
    parser.add_argument("--slide-count", type=int, default=None, help="Slides per paper.")
    parser.add_argument("--language", default=None, help="Slides language, e.g. en or zh.")
    args = parser.parse_args()

    result = await get_trending_service().prewarm(
        force=args.force,
        limit=args.limit,
        top_artifact_count=args.top_artifact_count,
        slide_count=args.slide_count,
        language=args.language,
    )
    sys.stdout.write(result.model_dump_json(indent=2))
    sys.stdout.write("\n")
    failed = [paper for paper in result.papers if paper.error or paper.blog_status == "failed" or paper.ppt_status == "failed"]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
