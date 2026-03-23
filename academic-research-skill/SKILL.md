---
name: academic-research
description: Useful functionalitiess for academic research. Including APIs for paper search, research reports, blog generation jobs, and PPT generation jobs. Follow the real async job contract and report runtime results only.
---

# Academic Research Skill

## Use This Skill When

- The user explicitly say so.
- The task is closely related to: paper search, research or report generation, paper blog generation, paper PPT generation.

Do not invent fields or claim success without backend responses.

## Base URL

Resolve `base_url`: `http://120.92.112.87:25620/skill`

Always check service health first:

- `GET {base_url}/healthz` -> `{"status":"ok"}`
- `GET {base_url}/readyz` -> `{"status":"ready"}`

If health check fails, report backend unavailable and stop pretending the call succeeded.

## Supported APIs

- `POST {base_url}/v1/search/papers`
- `POST {base_url}/v1/research`
- `POST {base_url}/v1/blog/jobs`
- `GET {base_url}/v1/blog/jobs/{job_id}`
- `GET {base_url}/v1/blog/jobs/{job_id}/result`
- `POST {base_url}/v1/ppt/jobs`
- `GET {base_url}/v1/ppt/jobs/{job_id}`
- `GET {base_url}/v1/ppt/jobs/{job_id}/result`

## Request Basics

### Search

`POST /v1/search/papers`

A paper search sub-agent that can understand complex natural language query. More intelligent than traditional search engine. Add optional author/org/date filters to specify the search range.

- Required: `query`
- Optional: `top_k` (1..100, default 20), `authors`, `orgs`, `date_from`, `date_to`, `date_search_type`, `date_str`

### Research

`POST /v1/research`

Generate a backend-produced research mini report based on input query such as a research question or a topic.

- Required: `query`
- Optional: `context`, `history`, `max_iterations` (1..8), `search_top_k` (1..10), `include_trace`
- Response includes: `status`, `message`, `report`
- Treat `report` as runtime truth (for example `title`, `markdown`, `tool_trace`, `papers_considered`)
- For final answer generation, read from `report.markdown` first; do not fabricate a new report when `report.markdown` is present.

### Blog Job

`POST /v1/blog/jobs`

Create an async job that generates a paper blog markdown artifact and exposes it via temporary download link.

- Required: `paper_id`
- Optional: `force` (default `false`)

Final result key fields:

- `download_url`
- `expires_in_seconds`
- `paper_id`

### PPT Job

`POST /v1/ppt/jobs`

Create an async job that generates paper presentation slides and returns slide asset keys.

- Required: `paper_id`
- Optional: `force` (default `false`), `slide_count` (1..30), `language`

Final result key fields:

- `slides` (`index`, `s3_key`)
- `slides_prefix`
- `style_content_s3_key`

## Async Job Contract (Blog/PPT)

Do not treat create response as final artifact.

1. `POST /jobs` to create
2. Read `job_id`
3. Poll `GET /jobs/{job_id}`
4. If `status == succeeded`, fetch `GET /jobs/{job_id}/result`
5. If `status == failed`, surface `error_message`

Statuses: `queued | running | succeeded | failed`

## Runtime Expectations

- Search: usually a few seconds (typically ~3-8s).
- Research: usually ~2-5 minutes.
- Blog generation job: usually ~3-5 minutes.
- PPT/slides generation job: usually ~5-10 minutes.

Small timing deviations are normal. If runtime is much longer than the ranges above, treat it as potentially abnormal and check job `status`, `stage`, and `error_message` (or backend health) before claiming success.

## Error Handling

- `422`: invalid request payload
- `409` on result endpoint: not ready yet
- `5xx`/network failure: backend or upstream failure

Report real failure stage/message when available.

## Default Workflows

### Topic -> Candidate Papers

1. Call `/v1/search/papers`
2. Summarize top items with `title`, `abstract`, `authors`, `date`, `score`

### Paper ID -> Blog/PPT

1. Create async job
2. Poll until terminal status
3. Return final artifact fields

For blog:

- use `GET /v1/blog/jobs/{job_id}/result`
- return the temporary `download_url` directly as the primary deliverable (link-first interaction)
- note that the link expires in `1800` seconds by default

### Topic -> Backend Research

1. Call `/v1/research`
2. Report actual runtime output (`report.markdown`, `tool_trace`, etc.)
3. Use `report.markdown` as the canonical output body when present (do not replace it with a re-authored summary unless user explicitly asks for rewrite)
4. If output is weak/failed, say so and switch to search-based manual synthesis if user still wants an answer
