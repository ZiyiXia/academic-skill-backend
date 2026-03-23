# academic-skill-backend

独立的 `FastAPI` 后端，面向 agent 提供 4 类学术能力：

- paper search
- research 占位接口
- paper blog generation
- paper ppt generation

不使用数据库。任务状态和结果索引都存 S3。

## Endpoints

- `POST /v1/search/papers`
- `POST /v1/research`
- `POST /v1/blog/jobs`
- `GET /v1/blog/jobs/{job_id}`
- `GET /v1/blog/jobs/{job_id}/result`
- `POST /v1/ppt/jobs`
- `GET /v1/ppt/jobs/{job_id}`
- `GET /v1/ppt/jobs/{job_id}/result`
- `GET /healthz`
- `GET /readyz`

## Quick Start

```bash
cd academic-skill-backend
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
cp .env.example .env
./run_server.sh
```

默认端口是 `8010`。

改端口：

```bash
./run_server.sh 8020
```

日志：

- `academic-skill-backend/logs/latest.log`
- `academic-skill-backend/logs/server_<timestamp>.log`

## Required Env

最少要配这些：

- `SEARCH_API_URL`
- `PPT_CREATE_URL`
- `ARXIV_PDF_BASE_URL`
- `S3_BUCKET`
- `S3_REGION`
- `S3_ENDPOINT`
- `S3_ACCESS_KEY`
- `S3_SECRET_KEY`
- `BLOG_S3_PREFIX`
- `BLOG_IMAGE_GEN_URL`
- `BLOG_LLM_API_KEY`
- `BLOG_LLM_BASE_URL`
- `BLOG_LLM_MODEL`
- `RAG_API_BASE_URL`
- `RAG_API_TOKEN`

`research` 默认优先读取：

- `RESEARCH_LLM_API_KEY`
- `RESEARCH_LLM_BASE_URL`
- `RESEARCH_LLM_MODEL`

如果没配，会回退到 `BLOG_LLM_*`。

可参考本地示例：

- [academic-skill-backend/.env](/Users/baai/Desktop/Projects/demo_serve/academic-skill-backend/.env)

Research 快速测试：

```bash
python scripts/test_research.py
python scripts/test_research.py --live
python scripts/test_research.py --live --timeout 600
```

`--live` 成功后会把完整结果写到：

- `outputs/research_tests/<timestamp>_<query>.json`
- `outputs/research_tests/<timestamp>_<query>.md`

当前测试脚本默认 `timeout` 是 `600` 秒。

## Agent Contract

`blog` 和 `ppt` 都是异步 job 模式。agent 不应该把 `POST` 的返回当最终结果。

统一调用方式：

1. 调创建接口
2. 拿到 `job_id`
3. 轮询 job 状态接口
4. `status == succeeded` 后再调 result 接口
5. `status == failed` 时读取 `error_message`

## I/O Formats

### `POST /v1/search/papers`

输入：

```json
{
  "query": "world model",
  "top_k": 3
}
```

常用输入字段：

- `query`: string
- `top_k`: integer, optional, default `20`
- `authors`: string[], optional
- `orgs`: string[], optional
- `date_from`: string, optional
- `date_to`: string, optional
- `date_search_type`: string, optional
- `date_str`: string | string[], optional

输出：

返回规范化后的论文列表。顶层包含：

- `query`
- `total`
- `items`

其中 `items[*]` 常见字段包括：

- `paper_id`
- `title`
- `abstract`
- `authors`
- `url`
- `date`
- `score`

### `POST /v1/research`

输入：

```json
{
  "query": "multimodal world model papers",
  "context": {},
  "history": [],
  "max_iterations": 4,
  "search_top_k": 5,
  "include_trace": true
}
```

当前输出：

```json
{
  "status": "not_implemented",
  "message": "Research workflow is reserved for a future multi-step implementation.",
  "report": null
}
```

### Blog

创建：

```bash
curl -X POST http://127.0.0.1:8010/v1/blog/jobs \
  -H 'Content-Type: application/json' \
  -d '{"paper_id":"1706.03762","force":false}'
```

输入：

```json
{
  "paper_id": "1706.03762",
  "force": false
}
```

- `force`: boolean, optional, default `false`
- `force=false` 时如果 S3 已有 blog 结果会直接复用
- `force=true` 时会忽略缓存，重新生成并覆盖同一路径结果

返回：

```json
{
  "job_id": "xxx",
  "job_type": "blog",
  "status": "queued",
  "progress": 0,
  "stage": null,
  "message": null,
  "upstream_progress": null
}
```

查状态：

```bash
curl http://127.0.0.1:8010/v1/blog/jobs/<job_id>
```

完整状态返回格式：

```json
{
  "job_id": "xxx",
  "job_type": "blog",
  "paper_id": "1706.03762",
  "status": "running",
  "progress": 5,
  "stage": "blog_generate",
  "message": "Generating blog markdown",
  "upstream_progress": null,
  "error_message": null,
  "result": null,
  "created_at": "2026-03-22T00:00:00+00:00",
  "updated_at": "2026-03-22T00:00:10+00:00"
}
```

返回字段：

- `status`: `queued | running | succeeded | failed`
- `progress`
- `stage`
- `message`
- `upstream_progress`
- `error_message`
- `result`

拿最终结果：

```bash
curl http://127.0.0.1:8010/v1/blog/jobs/<job_id>/result
```

最终结果结构：

```json
{
  "paper_id": "1706.03762",
  "markdown": "# ...",
  "generated_at": "2026-03-20T00:00:00+00:00",
  "markdown_s3_key": "deepxiv/blogs/1706.03762/blog/blog.md",
  "meta_s3_key": "deepxiv/blogs/1706.03762/blog/blog_meta.json"
}
```

agent 应直接消费：

- `markdown`

可选持久引用：

- `markdown_s3_key`

### PPT

创建：

```bash
curl -X POST http://127.0.0.1:8010/v1/ppt/jobs \
  -H 'Content-Type: application/json' \
  -d '{"paper_id":"1706.03762","slide_count":5,"force":false}'
```

如果没传 `slide_count`，默认是 `5`。

输入：

```json
{
  "paper_id": "1706.03762",
  "force": false,
  "slide_count": 5,
  "language": "en"
}
```

输入字段：

- `paper_id`: string
- `force`: boolean, optional, default `false`
- `slide_count`: integer, optional, default `5`
- `language`: string, optional
- `force=false` 时如果 S3 已有足够页数的 PPT 会直接复用
- `force=true` 时会忽略缓存，重新生成并覆盖同一路径结果

返回：

```json
{
  "job_id": "xxx",
  "job_type": "ppt",
  "status": "queued",
  "progress": 0,
  "stage": null,
  "message": null,
  "upstream_progress": null
}
```

查状态：

```bash
curl http://127.0.0.1:8010/v1/ppt/jobs/<job_id>
```

完整状态返回格式：

```json
{
  "job_id": "xxx",
  "job_type": "ppt",
  "paper_id": "1706.03762",
  "status": "running",
  "progress": 5,
  "stage": "prepare",
  "message": "正在生成参考页 (Slide 2)...",
  "upstream_progress": 15.0,
  "error_message": null,
  "result": null,
  "created_at": "2026-03-22T00:00:00+00:00",
  "updated_at": "2026-03-22T00:00:10+00:00"
}
```

拿最终结果：

```bash
curl http://127.0.0.1:8010/v1/ppt/jobs/<job_id>/result
```

最终结果结构：

```json
{
  "paper_id": "1706.03762",
  "generated_at": "2026-03-20T00:00:00+00:00",
  "slides_prefix": "deepxiv/blogs/1706.03762/slides",
  "slides": [
    { "index": 1, "s3_key": "deepxiv/blogs/1706.03762/slides/slide_1.png" },
    { "index": 2, "s3_key": "deepxiv/blogs/1706.03762/slides/slide_2.png" }
  ],
  "style_content_s3_key": "deepxiv/blogs/1706.03762/slides/style_content_filled.json"
}
```

agent 应直接消费：

- `slides`

可选持久引用：

- `slides_prefix`
- `style_content_s3_key`

## Search / Research

search 示例：

```bash
curl -X POST http://127.0.0.1:8010/v1/search/papers \
  -H 'Content-Type: application/json' \
  -d '{"query":"world model","top_k":3}'
```

research 当前只是占位：

```bash
curl -X POST http://127.0.0.1:8010/v1/research \
  -H 'Content-Type: application/json' \
  -d '{"query":"multimodal world model papers"}'
```

返回 `status=not_implemented`。

## Current Status

- `blog` 未命中生成可用
- `ppt` 命中缓存可用
- `ppt` 前置 `gen/content.json` / `gen/style_content.json` 补全已打通
- `ppt` 未命中完整出图还不稳定，剩余风险在上游 `createSlides`
