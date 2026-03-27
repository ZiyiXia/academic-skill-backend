---
name: academic-research
description: Useful functionalitiess for academic research. Including APIs for paper search, research reports, blog generation jobs, and PPT generation jobs. Follow the real async job contract and report runtime results only.
---

# Academic Research Skill

## Base URL

Resolve `base_url`: `http://120.92.112.87:25620/skill`

Always check health first:

- `GET {base_url}/healthz` -> `{"status":"ok"}`
- `GET {base_url}/readyz` -> `{"status":"ready"}`

If health checks fail, report backend unavailable and stop pretending the call succeeded.

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

This is a paper search sub-agent that can understand complex natural language query and search for most relevant results. More intelligent than traditional search engine. Add optional author/org/date filters to specify the search range.

`POST /v1/search/papers`

- Required: `query`
- Optional: `top_k` (1..100, default 20), `authors`, `orgs`, `date_from`, `date_to`, `date_search_type`, `date_str`

### Research

Generate a backend-produced mini research report based on input query such as a research question or a topic. When `report.markdown` is present, use it as the canonical report body unless the user explicitly asks for a rewrite.

`POST /v1/research`

- Required: `query`
- Optional: `context`, `history`, `max_iterations` (1..8, default 5), `search_top_k` (1..10, default 5), `include_trace`
- Response includes: `status`, `message`, `report`

### Blog Job

Create an async job that generates a paper blog markdown artifact and exposes it via returned temporary download link `download_url`.

`POST /v1/blog/jobs`

- Required: `paper_id`
- Optional: `force` (default `false`)

`GET /v1/blog/jobs/{job_id}/result`

Final result fields:

- `paper_id`
- `generated_at`
- `download_url`
- `expires_in_seconds`

### PPT Job

Create an async job that generates paper presentation slides. When done, the backend stitches all slide images into a PDF and returns it through a temporary download link `download_url`.

`POST /v1/ppt/jobs`

- Required: `paper_id`
- Optional: `force` (default `false`), `slide_count` (1..30), `language`

`GET /v1/ppt/jobs/{job_id}/result`

Final result fields:

- `paper_id`
- `generated_at`
- `download_url`
- `expires_in_seconds`

## Async Job Contract (Blog/PPT)

Do not treat the create response as the final artifact.

For blog:

1. `POST /v1/blog/jobs`
2. Read `job_id`
3. Poll `GET /v1/blog/jobs/{job_id}`
4. If `status == succeeded`, fetch `GET /v1/blog/jobs/{job_id}/result`
5. If `status == failed`, surface `error_message`

For ppt:

1. `POST /v1/ppt/jobs`
2. Read `job_id`
3. Poll `GET /v1/ppt/jobs/{job_id}`
4. If `status == succeeded`, fetch `GET /v1/ppt/jobs/{job_id}/result`
5. If `status == failed`, surface `error_message`

Statuses: `queued | running | succeeded | failed`

## Error Handling

- `422`: invalid request payload
- `409` on result endpoints: artifact not ready yet
- `5xx` or network failure: backend or upstream failure

Report the real failure stage or message when available.

## Recommended Workflows

### Topic/Query -> Candidate Papers

1. Call `/v1/search/papers`
2. List top items with their core metadata in a decent and neat way (better if there's a frontend in cooperation with)

### Topic/Research Question -> Backend Research

1. Call `/v1/research`
2. Report actual runtime output from `report`
3. Prefer directly use `report.markdown` as the primary answer body when present to user

### Paper ID -> Blog

1. Create blog job
2. Poll until terminal status
3. Fetch `/v1/blog/jobs/{job_id}/result`
4. Return the temporary `download_url` as the primary deliverable
5. Note the link expires in `1800` seconds by default

### Paper ID -> PPT

1. Create PPT job
2. Poll until terminal status
3. Fetch `/v1/ppt/jobs/{job_id}/result`
4. Return the temporary PDF `download_url` as the primary deliverable
5. Note the link expires in `1800` seconds by default
