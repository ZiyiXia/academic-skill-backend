---
name: academic-research
description: Call the `academic-skill-backend` APIs for paper search, backend research reports, blog generation jobs, and PPT generation jobs. Follow the real async job contract and report runtime results only.
---

# Academic Research Backend

## Use This Skill When

- The user wants to call this backend.
- The task is one of: paper search, backend research report, paper blog generation, paper PPT generation.

Do not invent fields or claim success without backend responses.

## Base URL

Resolve `base_url` in order:

1. User-provided URL
2. Project-configured URL
3. `http://127.0.0.1:8010`

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

- Required: `query`
- Optional: `top_k` (1..100, default 20), `authors`, `orgs`, `date_from`, `date_to`, `date_search_type`, `date_str`

### Research

`POST /v1/research`

- Required: `query`
- Optional: `context`, `history`, `max_iterations` (1..8), `search_top_k` (1..10), `include_trace`
- Response includes: `status`, `message`, `report`
- Treat `report` as runtime truth (for example `title`, `markdown`, `tool_trace`, `papers_considered`)

### Blog Job

`POST /v1/blog/jobs`

- Required: `paper_id`
- Optional: `force` (default `false`)

Final result key fields:

- `markdown`
- `markdown_s3_key`

### PPT Job

`POST /v1/ppt/jobs`

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

### Topic -> Backend Research

1. Call `/v1/research`
2. Report actual runtime output (`report.markdown`, `tool_trace`, etc.)
3. If output is weak/failed, say so and switch to search-based manual synthesis if user still wants an answer
