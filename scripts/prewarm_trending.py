#!/usr/bin/env python
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.deps import get_trending_service


async def main() -> int:
    parser = argparse.ArgumentParser(description="Prewarm daily trending paper artifacts.")
    parser.add_argument("--force", action="store_true", help="Regenerate existing cover/blog/slides artifacts.")
    parser.add_argument("--limit", type=int, default=None, help="Number of trending papers to fetch.")
    parser.add_argument("--top-artifact-count", type=int, default=None, help="How many top papers get blog and slides.")
    parser.add_argument("--slide-count", type=int, default=None, help="Slides per paper.")
    parser.add_argument("--language", default=None, help="Slides language, e.g. en or zh.")
    parser.add_argument("--json", action="store_true", help="Print the full result payload after the progress summary.")
    args = parser.parse_args()

    def progress(message: str) -> None:
        sys.stdout.write(f"{message}\n")
        sys.stdout.flush()

    result = await get_trending_service().prewarm(
        force=args.force,
        limit=args.limit,
        top_artifact_count=args.top_artifact_count,
        slide_count=args.slide_count,
        language=args.language,
        progress=progress,
    )
    failed = [paper for paper in result.papers if paper.error or paper.blog_status == "failed" or paper.ppt_status == "failed"]
    ready_covers = sum(1 for paper in result.papers if paper.cover_ready)
    sys.stdout.write(
        f"summary: papers={result.total_papers}, covers={ready_covers}/{result.total_papers}, "
        f"top_artifacts={result.top_artifact_count}, failed={len(failed)}\n"
    )
    if failed:
        for paper in failed[:10]:
            sys.stdout.write(f"failed: rank={paper.rank} paper_id={paper.paper_id} error={paper.error or paper.blog_status or paper.ppt_status}\n")
        if len(failed) > 10:
            sys.stdout.write(f"failed: ... {len(failed) - 10} more\n")
    if args.json:
        sys.stdout.write(result.model_dump_json(indent=2))
        sys.stdout.write("\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
