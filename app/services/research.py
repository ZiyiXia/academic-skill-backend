from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Optional

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI, RateLimitError

from app.core.config import Settings
from app.schemas.research import ResearchRequest, ResearchResponse
from app.schemas.search import SearchPapersRequest
from app.services.search import SearchService


class ResearchService:
    MAX_PREVIEW_CHARS = 8000
    MAX_SECTION_CHARS = 6000
    MAX_REPORT_RETRIES = 2
    MIN_REPORT_MARKDOWN_CHARS = 1200

    def __init__(self, settings: Settings):
        self.settings = settings
        self.search = SearchService(settings)
        self.llm_client = AsyncOpenAI(
            api_key=settings.research_llm_api_key,
            base_url=settings.research_llm_base_url.rstrip("/"),
        )

    async def run(self, payload: ResearchRequest) -> ResearchResponse:
        trace: list[dict[str, Any]] = []
        papers: dict[str, dict[str, Any]] = {}
        evidence_bank: list[dict[str, Any]] = []

        messages = self._build_react_messages(payload)
        tool_defs = self._build_tool_definitions()

        for step_idx in range(payload.max_iterations):
            try:
                assistant_message = await self._chat_completion(messages=messages, tools=tool_defs, tool_choice="auto")
            except Exception as exc:
                trace.append(self._error_trace(len(trace) + 1, "react_llm", {"iteration": step_idx + 1}, exc))
                break

            normalized_assistant = self._normalize_assistant_message(assistant_message)
            messages.append(normalized_assistant)

            tool_calls = normalized_assistant.get("tool_calls") or []
            if not tool_calls:
                if papers and not self._has_reading_evidence(papers) and step_idx < payload.max_iterations - 1:
                    reminder = (
                        "Search results alone are not enough for a rigorous research report. "
                        "Before concluding, read paper content using the paper-reading tools. "
                        "At minimum, inspect 2-3 strong candidate papers via brief/head/preview/section and then continue."
                    )
                    messages.append({"role": "user", "content": reminder})
                    trace.append({
                        "step": len(trace) + 1,
                        "type": "assistant_reminder",
                        "summary": "Prompted the model to read papers before concluding",
                    })
                    continue
                trace.append({
                    "step": len(trace) + 1,
                    "type": "assistant",
                    "summary": "Assistant finished tool-use loop",
                    "content": (normalized_assistant.get("content") or "")[:800],
                })
                break

            for tool_call in tool_calls:
                tool_name = tool_call["function"]["name"]
                raw_args = tool_call["function"].get("arguments") or "{}"
                args = self._parse_args(raw_args)
                try:
                    result = await self._execute_tool(tool_name, args, papers, evidence_bank)
                    trace.append({
                        "step": len(trace) + 1,
                        "type": "tool",
                        "tool": tool_name,
                        "summary": f"Executed {tool_name}",
                        "input": args,
                        "output": self._summarize_tool_result(tool_name, result),
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": json.dumps(result, ensure_ascii=False),
                    })
                except Exception as exc:
                    trace.append(self._error_trace(len(trace) + 1, tool_name, args, exc))
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": json.dumps({"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:400]}"}, ensure_ascii=False),
                    })

        self._apply_query_constraints(papers, payload.query)
        plan = self._fallback_plan(payload.query)
        catalog = self._paper_catalog_for_report(papers)
        report = await self._generate_report(payload, messages, plan, catalog, evidence_bank, trace)

        return ResearchResponse(
            status="success",
            message=f"Generated research report for query: {payload.query}",
            report=report,
        )

    def _build_react_messages(self, payload: ResearchRequest) -> list[dict[str, Any]]:
        system_prompt = (
            "You are a research agent following a standard ReACT workflow. "
            "Your job is to answer the user's research question by iteratively deciding what to inspect, calling tools explicitly, "
            "and only then synthesizing a report. "
            "Important rules:\n"
            "1. Use tools whenever evidence is missing.\n"
            "2. Search is only for discovering candidate papers; it is not sufficient evidence by itself.\n"
            "3. Before writing a substantive report, read paper content from at least 2-3 relevant papers using brief/head/preview/section tools whenever possible.\n"
            "4. Prefer concrete paper inspection over vague guessing.\n"
            "5. When the user asks for datasets, methods, or benchmarks, compare candidates directly.\n"
            "6. Respect hard constraints in the question such as date ranges or exclusions.\n"
            "7. Stop calling tools once you have enough evidence for a substantive report."
        )
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        if payload.context:
            messages.append({
                "role": "system",
                "content": f"Additional context:\n{json.dumps(payload.context, ensure_ascii=False)}",
            })
        for item in payload.history:
            messages.append({"role": item.role, "content": item.content})
        messages.append({"role": "user", "content": payload.query})
        return messages

    def _build_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_papers",
                    "description": (
                        "Search for relevant arXiv papers. Use this first to build candidate sets. "
                        "Best for finding datasets, methods, benchmarks, and related work. "
                        "This is a discovery tool, not a substitute for reading paper content."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "top_k": {"type": "integer", "default": 5},
                            "authors": {"type": "array", "items": {"type": "string"}},
                            "orgs": {"type": "array", "items": {"type": "string"}},
                            "date_from": {"type": "string"},
                            "date_to": {"type": "string"},
                            "date_search_type": {"type": "string"},
                            "date_str": {
                                "oneOf": [
                                    {"type": "string"},
                                    {"type": "array", "items": {"type": "string"}},
                                ]
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_paper_brief",
                    "description": "Read a concise paper brief including TLDR, keywords, publish time, and citations for an arXiv paper. Use this to quickly assess candidate relevance.",
                    "parameters": {
                        "type": "object",
                        "properties": {"arxiv_id": {"type": "string"}},
                        "required": ["arxiv_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_paper_head",
                    "description": "Read paper metadata including title, abstract, authors, and source URL for an arXiv paper. Use this to verify scope and filtering constraints.",
                    "parameters": {
                        "type": "object",
                        "properties": {"arxiv_id": {"type": "string"}},
                        "required": ["arxiv_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_paper_preview",
                    "description": "Read the first part of the paper markdown. Useful for understanding task framing, abstract, early sections, and whether the paper truly matches the query.",
                    "parameters": {
                        "type": "object",
                        "properties": {"arxiv_id": {"type": "string"}},
                        "required": ["arxiv_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_paper_section",
                    "description": "Read a named section from a paper, for example Introduction, Dataset, Experiments, Method, or Conclusion. Use this for precise evidence before making recommendations.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "arxiv_id": {"type": "string"},
                            "section_name": {"type": "string"},
                        },
                        "required": ["arxiv_id", "section_name"],
                    },
                },
            },
        ]

    async def _execute_tool(
        self,
        tool_name: str,
        args: dict[str, Any],
        papers: dict[str, dict[str, Any]],
        evidence_bank: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if tool_name == "search_papers":
            query = str(args.get("query") or "").strip()
            if not query:
                raise ValueError("query is required")
            result = await self._search_papers(args)
            self._merge_search_results(papers, result, source_query=query)
            return {"ok": True, **result}

        if tool_name == "get_paper_brief":
            arxiv_id = str(args.get("arxiv_id") or "").strip()
            result = await self._inspect_paper(arxiv_id, "brief")
            self._merge_inspection(papers, arxiv_id, "brief", result)
            evidence_bank.extend(self._extract_evidence(arxiv_id, "brief", result))
            return {"ok": True, "arxiv_id": arxiv_id, "result": result}

        if tool_name == "get_paper_head":
            arxiv_id = str(args.get("arxiv_id") or "").strip()
            result = await self._inspect_paper(arxiv_id, "head")
            self._merge_inspection(papers, arxiv_id, "head", result)
            evidence_bank.extend(self._extract_evidence(arxiv_id, "head", result))
            return {"ok": True, "arxiv_id": arxiv_id, "result": result}

        if tool_name == "get_paper_preview":
            arxiv_id = str(args.get("arxiv_id") or "").strip()
            result = await self._inspect_paper(arxiv_id, "preview")
            self._merge_inspection(papers, arxiv_id, "preview", result)
            evidence_bank.extend(self._extract_evidence(arxiv_id, "preview", result))
            return {"ok": True, "arxiv_id": arxiv_id, "result": self._compress_tool_output(result, "preview")}

        if tool_name == "get_paper_section":
            arxiv_id = str(args.get("arxiv_id") or "").strip()
            section_name = str(args.get("section_name") or "").strip()
            result = await self._inspect_paper(arxiv_id, "section", section_name=section_name)
            self._merge_inspection(papers, arxiv_id, "section", result, section_name=section_name)
            evidence_bank.extend(self._extract_evidence(arxiv_id, "section", result, section_name=section_name))
            return {
                "ok": True,
                "arxiv_id": arxiv_id,
                "section_name": section_name,
                "result": self._compress_tool_output(result, "section"),
            }

        raise ValueError(f"Unsupported tool: {tool_name}")

    async def _generate_report(
        self,
        payload: ResearchRequest,
        messages: list[dict[str, Any]],
        plan: dict[str, Any],
        catalog: list[dict[str, Any]],
        evidence_bank: list[dict[str, Any]],
        trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        report_instruction = (
            "Now write the final research report. "
            "Return JSON with keys: title and markdown. You may also include notable_papers and follow_up_questions if useful. "
            "Requirements:\n"
            "- The markdown must be a real analytical report, not a rigid template.\n"
            "- Prefer 1200-2200 words when evidence allows.\n"
            "- Use your own structure if it fits the evidence; you do not need to force fixed headings.\n"
            "- If the user asks for datasets or recommendations, explicitly recommend the best options and explain exclusions.\n"
            "- Ground claims in the tool results already present in the conversation.\n"
            "- Do not call tools anymore."
        )

        attempt_messages = list(messages) + [{"role": "user", "content": report_instruction}]
        result: Optional[dict[str, Any]] = None
        last_exc: Optional[Exception] = None

        for attempt in range(self.MAX_REPORT_RETRIES):
            try:
                raw = await self._chat_completion_text(attempt_messages)
                result = self._parse_json_object(raw)
                if isinstance(result, dict):
                    break
            except Exception as exc:
                last_exc = exc
                trace.append(self._error_trace(len(trace) + 1, "research_report_llm", {"attempt": attempt + 1}, exc))

        if not isinstance(result, dict):
            if last_exc is not None:
                trace.append({
                    "step": len(trace) + 1,
                    "type": "report_fallback",
                    "summary": "Fell back to deterministic report rendering after report generation failure",
                })
            return await self._fallback_report(
                payload.query,
                plan,
                catalog,
                evidence_bank,
                trace,
                include_trace=payload.include_trace,
            )

        report = self._finalize_report_shape(result, payload.query, plan, catalog, evidence_bank)
        report["query"] = payload.query
        report["plan"] = plan
        report["papers_considered"] = catalog
        if payload.include_trace:
            report["tool_trace"] = trace
        return report

    async def _search_papers(self, args: dict[str, Any]) -> dict[str, Any]:
        request = SearchPapersRequest(
            query=str(args.get("query") or "").strip(),
            top_k=max(1, min(int(args.get("top_k", 5)), 10)),
            authors=args.get("authors") if isinstance(args.get("authors"), list) else None,
            orgs=args.get("orgs") if isinstance(args.get("orgs"), list) else None,
            date_from=args.get("date_from"),
            date_to=args.get("date_to"),
            date_search_type=args.get("date_search_type"),
            date_str=args.get("date_str"),
        )
        response = await self.search.search_papers(request)
        data = response.model_dump()
        return data

    async def _inspect_paper(self, arxiv_id: str, inspect_type: str, *, section_name: Optional[str] = None) -> Any:
        if not arxiv_id:
            raise ValueError("arxiv_id is required")

        params: dict[str, Any] = {
            "arxiv_id": arxiv_id,
            "type": inspect_type,
            "token": self.settings.rag_api_token,
        }
        if inspect_type == "preview":
            params["characters"] = self.MAX_PREVIEW_CHARS
        if inspect_type == "section":
            if not section_name:
                raise ValueError("section_name is required for section retrieval")
            params["section"] = section_name

        headers: dict[str, str] = {}
        if self.settings.rag_api_token:
            headers["Authorization"] = f"Bearer {self.settings.rag_api_token}"

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                f"{self.settings.rag_api_base_url.rstrip('/')}/arxiv/",
                params=params,
                headers=headers,
            )
            response.raise_for_status()
            if "application/json" in response.headers.get("content-type", ""):
                return response.json()
            return response.text

    async def _chat_completion(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
    ) -> dict[str, Any]:
        last_error: Optional[Exception] = None
        for attempt in range(3):
            try:
                params: dict[str, Any] = {
                    "model": self.settings.research_llm_model,
                    "temperature": 0.2,
                    "messages": messages,
                }
                if tools:
                    params["tools"] = tools
                    params["tool_choice"] = tool_choice or "auto"
                response = await self.llm_client.chat.completions.create(**params)
                break
            except (APIConnectionError, APITimeoutError, RateLimitError, APIStatusError) as exc:
                last_error = exc
                if attempt == 2:
                    raise RuntimeError(f"Research LLM request failed after 3 attempts: {type(exc).__name__}") from exc
                await asyncio.sleep(2 * (attempt + 1))
        else:
            raise RuntimeError(f"Research LLM request failed: {repr(last_error)}")

        if not response.choices:
            raise RuntimeError("LLM response missing message")
        message = response.choices[0].message.model_dump(exclude_none=True)
        if not isinstance(message, dict):
            raise RuntimeError("LLM response missing message")
        return message

    async def _chat_completion_text(self, messages: list[dict[str, Any]]) -> str:
        message = await self._chat_completion(messages=messages)
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Research LLM returned empty content")
        return content.strip()

    def _normalize_assistant_message(self, message: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {
            "role": "assistant",
            "content": message.get("content") or "",
        }
        raw_tool_calls = message.get("tool_calls") or []
        if isinstance(raw_tool_calls, list) and raw_tool_calls:
            normalized["tool_calls"] = raw_tool_calls
        return normalized

    def _parse_args(self, raw_args: Any) -> dict[str, Any]:
        if isinstance(raw_args, dict):
            return raw_args
        if isinstance(raw_args, str):
            try:
                parsed = json.loads(raw_args)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return {}
        return {}

    def _merge_search_results(self, papers: dict[str, dict[str, Any]], result: dict[str, Any], *, source_query: str) -> None:
        for item in result.get("items", []):
            if not isinstance(item, dict):
                continue
            arxiv_id = str(item.get("paper_id") or "").strip()
            if not arxiv_id:
                continue
            paper = papers.setdefault(
                arxiv_id,
                {
                    "arxiv_id": arxiv_id,
                    "title": item.get("title"),
                    "abstract": item.get("abstract"),
                    "authors": item.get("authors") or [],
                    "date": item.get("date"),
                    "url": item.get("url"),
                    "score": item.get("score"),
                    "search_queries": [],
                    "inspections": {},
                },
            )
            if source_query not in paper["search_queries"]:
                paper["search_queries"].append(source_query)
            if item.get("title"):
                paper["title"] = item.get("title")
            if item.get("abstract"):
                paper["abstract"] = item.get("abstract")
            if item.get("authors"):
                paper["authors"] = item.get("authors")
            if item.get("date"):
                paper["date"] = item.get("date")
            if item.get("url"):
                paper["url"] = item.get("url")
            if isinstance(item.get("score"), (int, float)):
                paper["score"] = max(float(item["score"]), float(paper.get("score") or 0))

    def _merge_inspection(
        self,
        papers: dict[str, dict[str, Any]],
        arxiv_id: str,
        inspect_type: str,
        result: Any,
        *,
        section_name: Optional[str] = None,
    ) -> None:
        paper = papers.setdefault(arxiv_id, {"arxiv_id": arxiv_id, "search_queries": [], "inspections": {}})
        key = inspect_type if inspect_type != "section" or not section_name else f"section:{section_name}"
        paper.setdefault("inspections", {})[key] = self._compress_tool_output(result, inspect_type)
        if isinstance(result, dict):
            if result.get("title"):
                paper["title"] = result.get("title")
            if result.get("abstract"):
                paper["abstract"] = result.get("abstract")
            if result.get("authors"):
                paper["authors"] = result.get("authors")
            if result.get("publish_at"):
                paper["date"] = result.get("publish_at")
            elif result.get("date"):
                paper["date"] = result.get("date")

    def _extract_evidence(
        self,
        arxiv_id: str,
        inspect_type: str,
        result: Any,
        *,
        section_name: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        snippets: list[dict[str, Any]] = []
        if inspect_type == "brief" and isinstance(result, dict):
            text = str(result.get("tldr") or "").strip()
            if text:
                snippets.append({"arxiv_id": arxiv_id, "source": "brief", "section": None, "snippet": text[:800]})
        elif inspect_type == "head" and isinstance(result, dict):
            text = str(result.get("abstract") or "").strip()
            if text:
                snippets.append({"arxiv_id": arxiv_id, "source": "head", "section": "abstract", "snippet": text[:1000]})
        elif inspect_type == "preview" and isinstance(result, dict):
            text = str(result.get("preview") or "").strip()
            if text:
                snippets.append({"arxiv_id": arxiv_id, "source": "preview", "section": None, "snippet": text[:1000]})
        elif inspect_type == "section" and isinstance(result, dict):
            text = str(result.get("content") or "").strip()
            if text:
                snippets.append({"arxiv_id": arxiv_id, "source": "section", "section": section_name, "snippet": text[:1000]})
        return snippets

    def _compress_tool_output(self, value: Any, inspect_type: str) -> Any:
        if not isinstance(value, dict):
            return value
        compact = dict(value)
        if inspect_type == "preview" and isinstance(compact.get("preview"), str):
            compact["preview"] = compact["preview"][: self.MAX_PREVIEW_CHARS]
        if inspect_type == "section" and isinstance(compact.get("content"), str):
            compact["content"] = compact["content"][: self.MAX_SECTION_CHARS]
        return compact

    def _summarize_tool_result(self, tool_name: str, result: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "search_papers":
            return {
                "query": result.get("query"),
                "total": result.get("total"),
                "items": (result.get("items") or [])[:5],
            }
        return {
            "ok": result.get("ok"),
            "arxiv_id": result.get("arxiv_id"),
            "section_name": result.get("section_name"),
        }

    def _paper_catalog_for_report(self, papers: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        ranked = sorted(
            papers.values(),
            key=lambda item: (len(item.get("inspections", {})), item.get("score") or 0),
            reverse=True,
        )
        return [
            {
                "arxiv_id": paper.get("arxiv_id"),
                "title": paper.get("title"),
                "abstract": (paper.get("abstract") or "")[:1000],
                "authors": paper.get("authors") or [],
                "date": paper.get("date"),
                "score": paper.get("score"),
                "search_queries": paper.get("search_queries") or [],
                "inspections": paper.get("inspections") or {},
            }
            for paper in ranked[:12]
        ]

    def _has_reading_evidence(self, papers: dict[str, dict[str, Any]]) -> bool:
        for paper in papers.values():
            inspections = paper.get("inspections") or {}
            if inspections:
                return True
        return False

    def _fallback_plan(self, query: str) -> dict[str, Any]:
        return {
            "goal": f"Investigate the research question: {query}",
            "angle": "Survey main approaches, evidence, tradeoffs, exclusions, and open questions.",
            "sub_questions": [
                f"What are the strongest candidate answers for {query}?",
                f"What evidence supports or weakens each candidate for {query}?",
                f"What important caveats or exclusions should be stated for {query}?",
            ],
            "focus_aspects": ["methods", "evaluation", "limitations", "recommendations"],
        }

    async def _generate_fallback_markdown_from_llm(
        self,
        query: str,
        catalog: list[dict[str, Any]],
        evidence_bank: list[dict[str, Any]],
    ) -> Optional[str]:
        if not self.settings.research_llm_api_key:
            return None
        system = (
            "You are writing a fallback research report from structured evidence. "
            "Write a useful, prose-heavy markdown report. Do not use a rigid canned template. Do not return JSON."
        )
        user = (
            f"Question: {query}\n"
            "Write a substantial report that uses whatever structure best fits the evidence. "
            "If evidence is weak, say so explicitly, but still analyze the candidates that were retrieved and discuss likely fit, exclusions, and uncertainty.\n"
            f"Papers: {json.dumps(catalog[:8], ensure_ascii=False)}\n"
            f"Evidence: {json.dumps(evidence_bank[:16], ensure_ascii=False)}"
        )
        try:
            markdown = await self._chat_completion_text(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ]
            )
        except Exception:
            return None
        return markdown if len(markdown.strip()) >= self.MIN_REPORT_MARKDOWN_CHARS else None

    async def _fallback_report(
        self,
        query: str,
        plan: dict[str, Any],
        catalog: list[dict[str, Any]],
        evidence_bank: list[dict[str, Any]],
        trace: list[dict[str, Any]],
        *,
        include_trace: bool,
    ) -> dict[str, Any]:
        key_findings = self._build_key_findings(catalog, evidence_bank)
        notable = self._build_notable_papers(catalog, evidence_bank)
        llm_markdown = await self._generate_fallback_markdown_from_llm(query, catalog, evidence_bank)
        if llm_markdown:
            sections = self._sections_from_markdown(llm_markdown)
            markdown = llm_markdown
        else:
            sections = self._build_deterministic_sections(query, plan, catalog, evidence_bank, notable)
            markdown = self._render_sections_to_markdown(query, sections)

        report = {
            "query": query,
            "title": f"Research Report: {query}",
            "executive_summary": key_findings[0] if key_findings else "The current run retrieved partial evidence but final report synthesis had to fall back.",
            "key_findings": key_findings,
            "sections": sections,
            "notable_papers": notable,
            "limitations": [
                "The final report generator did not complete normally, so this report was assembled from collected evidence and fallback synthesis.",
                "Results remain bounded by the papers surfaced and inspected in this run.",
            ],
            "follow_up_questions": plan.get("sub_questions") or [],
            "markdown": markdown,
            "plan": plan,
            "papers_considered": catalog,
        }
        if include_trace:
            report["tool_trace"] = trace
        return report

    def _build_key_findings(self, catalog: list[dict[str, Any]], evidence_bank: list[dict[str, Any]]) -> list[str]:
        findings: list[str] = []
        for evidence in evidence_bank[:8]:
            snippet = str(evidence.get("snippet") or "").strip()
            if snippet:
                findings.append(f"{evidence.get('arxiv_id')}: {snippet[:220]}")
        if findings:
            return findings[:8]
        for paper in catalog[:6]:
            abstract = str(paper.get("abstract") or "").strip()
            if abstract:
                findings.append(f"{paper.get('arxiv_id')}: {abstract[:220]}")
        return findings[:8]

    def _build_notable_papers(self, catalog: list[dict[str, Any]], evidence_bank: list[dict[str, Any]]) -> list[dict[str, Any]]:
        notable = []
        for paper in catalog[:6]:
            paper_id = paper.get("arxiv_id")
            evidence = [item["snippet"] for item in evidence_bank if item.get("arxiv_id") == paper_id][:3]
            notable.append(
                {
                    "arxiv_id": paper_id,
                    "title": paper.get("title"),
                    "contribution": ((paper.get("inspections") or {}).get("brief") or {}).get("tldr") or (paper.get("abstract") or "")[:320],
                    "evidence": evidence,
                }
            )
        return notable

    def _build_deterministic_sections(
        self,
        query: str,
        plan: dict[str, Any],
        catalog: list[dict[str, Any]],
        evidence_bank: list[dict[str, Any]],
        notable: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        candidate_lines = []
        for paper in catalog[:8]:
            brief = ((paper.get("inspections") or {}).get("brief") or {}).get("tldr")
            abstract = paper.get("abstract") or ""
            evidence = brief or abstract[:360] or "No detailed evidence was extracted for this paper."
            candidate_lines.append(
                f"{paper.get('title')} ({paper.get('arxiv_id')}, {paper.get('date') or 'n.d.'}) is relevant because {evidence}"
            )

        evidence_lines = []
        for item in evidence_bank[:12]:
            section = f" [{item.get('section')}]" if item.get("section") else ""
            evidence_lines.append(f"- {item.get('arxiv_id')}{section}: {item.get('snippet')}")

        recommendation_lines = []
        for item in notable[:5]:
            recommendation_lines.append(
                f"{item.get('title')} ({item.get('arxiv_id')}) should be treated as a priority candidate because {item.get('contribution')}"
            )

        return [
            {
                "heading": "Question and Scope",
                "content": (
                    f"The user asks: {query}\n\n"
                    f"The working goal for this run is: {plan.get('goal')}. "
                    "The analysis below uses retrieved papers and any successful paper inspections to identify the strongest candidates, "
                    "explain why they matter, and separate promising options from weaker or older alternatives."
                ),
            },
            {
                "heading": "Candidate Landscape",
                "content": "\n\n".join(candidate_lines) if candidate_lines else "No strong candidate papers survived this run.",
            },
            {
                "heading": "Evidence Review",
                "content": "\n".join(evidence_lines) if evidence_lines else "No direct paper-level evidence was captured beyond search metadata.",
            },
            {
                "heading": "Recommendations",
                "content": "\n\n".join(recommendation_lines) if recommendation_lines else "There is not yet enough direct evidence to make high-confidence recommendations.",
            },
            {
                "heading": "Caveats and Next Steps",
                "content": (
                    "This report was assembled from partial evidence. "
                    "If a production decision depends on it, the next step should be to read more recent candidate papers in depth, "
                    "verify year and task formulation directly, and compare annotation schema, evaluation protocol, and licensing."
                ),
            },
        ]

    def _render_sections_to_markdown(self, query: str, sections: list[dict[str, str]]) -> str:
        lines = [f"# {query}"]
        for section in sections:
            heading = str(section.get("heading") or "").strip()
            content = str(section.get("content") or "").strip()
            if heading and content:
                lines.extend(["", f"## {heading}", content])
        return "\n".join(lines).strip()

    def _sections_from_markdown(self, markdown: str) -> list[dict[str, str]]:
        sections: list[dict[str, str]] = []
        current_heading: Optional[str] = None
        current_lines: list[str] = []
        for line in markdown.splitlines():
            if line.startswith("## "):
                if current_heading:
                    sections.append({"heading": current_heading, "content": "\n".join(current_lines).strip()})
                current_heading = line[3:].strip()
                current_lines = []
            elif current_heading:
                current_lines.append(line)
        if current_heading:
            sections.append({"heading": current_heading, "content": "\n".join(current_lines).strip()})
        return sections

    def _finalize_report_shape(
        self,
        report: dict[str, Any],
        query: str,
        plan: dict[str, Any],
        catalog: list[dict[str, Any]],
        evidence_bank: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not isinstance(report.get("title"), str) or not report.get("title"):
            report["title"] = f"Research Report: {query}"
        if not isinstance(report.get("notable_papers"), list):
            report["notable_papers"] = self._build_notable_papers(catalog, evidence_bank)
        markdown = report.get("markdown")
        if not isinstance(markdown, str) or len(markdown.strip()) < self.MIN_REPORT_MARKDOWN_CHARS:
            sections = report.get("sections")
            if not isinstance(sections, list) or not sections:
                sections = self._build_deterministic_sections(query, plan, catalog, evidence_bank, report["notable_papers"])
                report["sections"] = sections
            report["markdown"] = self._render_sections_to_markdown(query, report["sections"])
        elif not isinstance(report.get("sections"), list) or not report.get("sections"):
            report["sections"] = self._sections_from_markdown(report["markdown"])
        if not isinstance(report.get("key_findings"), list):
            report["key_findings"] = self._build_key_findings(catalog, evidence_bank)
        if not isinstance(report.get("executive_summary"), str) or not report.get("executive_summary"):
            report["executive_summary"] = (report.get("key_findings") or [""])[0]
        if not isinstance(report.get("follow_up_questions"), list):
            report["follow_up_questions"] = plan.get("sub_questions") or []
        return report

    def _apply_query_constraints(self, papers: dict[str, dict[str, Any]], query: str) -> None:
        rule = self._infer_year_constraint(query)
        if not rule:
            return
        to_remove = []
        for paper_id, paper in papers.items():
            year = self._extract_year(paper.get("date"))
            if year is None:
                continue
            if rule["op"] == "gt" and year <= rule["year"]:
                to_remove.append(paper_id)
            elif rule["op"] == "ge" and year < rule["year"]:
                to_remove.append(paper_id)
            elif rule["op"] == "lt" and year >= rule["year"]:
                to_remove.append(paper_id)
        for paper_id in to_remove:
            papers.pop(paper_id, None)

    def _infer_year_constraint(self, query: str) -> Optional[dict[str, Any]]:
        text = query.lower()
        match = re.search(r"(19|20)\d{2}", text)
        if not match:
            return None
        year = int(match.group(0))
        if re.search(r"(not want|don't want|do not want|exclude|without).{0,50}(before|older than|earlier than).{0,10}" + str(year), text):
            return {"op": "gt", "year": year}
        if re.search(r"(after|post[- ]?|newer than|later than)\s*" + str(year), text):
            return {"op": "gt", "year": year}
        if re.search(r"(since|from)\s*" + str(year), text):
            return {"op": "ge", "year": year}
        if re.search(r"(before|older than|earlier than)\s*" + str(year), text):
            return {"op": "lt", "year": year}
        return None

    def _extract_year(self, value: Any) -> Optional[int]:
        if value is None:
            return None
        match = re.search(r"(19|20)\d{2}", str(value))
        if not match:
            return None
        return int(match.group(0))

    def _parse_json_object(self, raw: str) -> Optional[dict[str, Any]]:
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            parsed = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    def _error_trace(self, step: int, tool_name: str, tool_input: dict[str, Any], exc: Exception) -> dict[str, Any]:
        return {
            "step": step,
            "type": "tool_error",
            "tool": tool_name,
            "input": tool_input,
            "summary": f"{tool_name} failed",
            "error": f"{type(exc).__name__}: {str(exc)[:500]}",
        }
