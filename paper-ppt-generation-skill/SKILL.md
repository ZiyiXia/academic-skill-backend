---
name: paper-ppt-generation
description: Use this skill when the user wants to generate a presentation PDF for a paper. It covers the PPT generation job flow, including service health checks, request fields, async polling, and final download link handling.
---

# Paper PPT Generation Skill

## Base URL

Resolve `base_url`: `http://120.92.112.87:25620/skill`

Always check service health first:

- `GET {base_url}/healthz` -> `{"status":"ok"}`
- `GET {base_url}/readyz` -> `{"status":"ready"}`

If health checks fail, report backend unavailable and stop pretending the call succeeded.

## Supported APIs

- `POST {base_url}/v1/ppt/jobs`
- `GET {base_url}/v1/ppt/jobs/{job_id}`
- `GET {base_url}/v1/ppt/jobs/{job_id}/result`

## Request Basics

### Create PPT Job

`POST /v1/ppt/jobs`

Create an async job that generates paper presentation slides. When done, the backend stitches slide images into a PDF and returns a temporary download link.

Request fields:

- `paper_id`: required string
- `force`: optional boolean, default `false`
- `slide_count`: optional integer, range `1..30`, default `5`
- `language`: optional string

Field semantics:

- `force=false`: reuse cached outputs when possible
- `force=true`: regenerate even if cached outputs exist
- `slide_count`: if omitted, backend uses its configured default
- `language`: forwarded to the PPT generation flow

### Job Detail

`GET /v1/ppt/jobs/{job_id}`

Key fields:

- `job_id`
- `job_type`
- `paper_id`
- `status`
- `progress`
- `stage`
- `message`
- `upstream_progress`
- `error_message`
- `result`
- `created_at`
- `updated_at`

Statuses:

- `queued`
- `running`
- `succeeded`
- `failed`

### Final Result

`GET /v1/ppt/jobs/{job_id}/result`

Final result fields:

- `paper_id`
- `generated_at`
- `download_url`
- `expires_in_seconds`

The returned `download_url` is a temporary link to the generated `slides.pdf`.

## Async Job Contract

Do not treat the create response as the final artifact.

1. `POST /v1/ppt/jobs`
2. Read `job_id`
3. Poll `GET /v1/ppt/jobs/{job_id}`
4. If `status == succeeded`, fetch `GET /v1/ppt/jobs/{job_id}/result`
5. If `status == failed`, surface `error_message`

## Error Handling

- `422`: invalid request payload
- `409` on result endpoint: artifact not ready yet
- `5xx` or network failure: backend or upstream failure

Report the real failure stage or message when available.

## Recommended Workflow

### Paper ID -> PPT

1. Confirm the target `paper_id`
2. Create the PPT job
3. Poll until terminal status
4. Fetch `/v1/ppt/jobs/{job_id}/result`
5. Return the temporary PDF `download_url` as the primary deliverable
6. Note that the link expires in `1800` seconds by default

## Output Discipline

- Do not invent extra fields that the backend does not return
- Do not claim a PPT is ready before `status == succeeded`
- Treat the returned `download_url` as the final deliverable
