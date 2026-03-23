from __future__ import annotations

import httpx

from app.core.config import Settings
from app.schemas.search import SearchPaperItem, SearchPapersRequest, SearchPapersResponse


class SearchService:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def search_papers(self, payload: SearchPapersRequest) -> SearchPapersResponse:
        upstream_payload = {
            "query": payload.query,
            "top_k": payload.top_k,
        }
        if payload.authors:
            upstream_payload["authors"] = payload.authors
        if payload.orgs:
            upstream_payload["orgs"] = payload.orgs
        if payload.date_from:
            upstream_payload["date_from"] = payload.date_from
        if payload.date_to:
            upstream_payload["date_to"] = payload.date_to
        if payload.date_search_type:
            upstream_payload["date_search_type"] = payload.date_search_type
        if payload.date_str is not None:
            upstream_payload["date_str"] = payload.date_str

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(self.settings.search_api_url, json=upstream_payload)
            response.raise_for_status()
            data = response.json()

        results = data.get("result", []) if isinstance(data, dict) else []
        items: list[SearchPaperItem] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            authors = []
            for author in item.get("authors", []) or []:
                if isinstance(author, dict):
                    name = str(author.get("name", "")).strip()
                    if name:
                        authors.append(name)
            items.append(
                SearchPaperItem(
                    paper_id=item.get("arxiv_id"),
                    title=item.get("title"),
                    abstract=item.get("abstract"),
                    score=item.get("score"),
                    url=item.get("url"),
                    date=item.get("date"),
                    authors=authors,
                )
            )

        total = data.get("total_count", len(items)) if isinstance(data, dict) else len(items)
        return SearchPapersResponse(query=payload.query, total=total, items=items)
