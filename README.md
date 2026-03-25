# academic-skill-backend

独立的 FastAPI 后端，提供 4 类能力：

- 论文搜索（`/v1/search/papers`）
- 多步 research 报告生成（`/v1/research`）
- 论文 blog 异步生成（`/v1/blog/jobs*`）
- 论文 PPT 异步生成（`/v1/ppt/jobs*`）

后端不依赖数据库，任务状态与结果索引存储在 S3。

## API 概览

- `GET /healthz`
- `GET /readyz`
- `POST /v1/search/papers`
- `POST /v1/research`
- `POST /v1/blog/jobs`
- `GET /v1/blog/jobs/{job_id}`
- `GET /v1/blog/jobs/{job_id}/result`
- `POST /v1/ppt/jobs`
- `GET /v1/ppt/jobs/{job_id}`
- `GET /v1/ppt/jobs/{job_id}/result`

## 快速启动

```bash
cd academic-skill-backend
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
cp .env.example .env
./run_server.sh
```

默认端口 `8010`。指定端口：

```bash
./run_server.sh 8020
```

日志文件：

- `logs/latest.log`
- `logs/server_<timestamp>.log`

## 接口说明

默认本地基址：

```text
http://127.0.0.1:8010
```

所有写接口都使用：

```text
Content-Type: application/json
```

### 0) 健康检查

#### `GET /healthz`

用途：

- 存活检查

返回：

```json
{
  "status": "ok"
}
```

#### `GET /readyz`

用途：

- 就绪检查

返回：

```json
{
  "status": "ready"
}
```

### 1) 搜索论文

#### `POST /v1/search/papers`

用途：

- 根据自然语言 query 检索论文
- 支持作者、机构、日期过滤

请求体：

```json
{
  "query": "world model",
  "top_k": 3,
  "authors": ["Kaiming He"],
  "orgs": ["MIT"],
  "date_from": "2025-01-01",
  "date_to": "2025-12-31",
  "date_search_type": "strict",
  "date_str": ["2025"]
}
```

字段说明：

- `query`: `string`, 必填, 最短 1 个字符
- `top_k`: `int`, 可选, 默认 `20`, 取值范围 `1..100`
- `authors`: `list[string]`, 可选
- `orgs`: `list[string]`, 可选
- `date_from`: `string`, 可选, 建议 `YYYY-MM-DD`
- `date_to`: `string`, 可选, 建议 `YYYY-MM-DD`
- `date_search_type`: `string`, 可选
- `date_str`: `string | list[string]`, 可选

返回体：

```json
{
  "status": "success",
  "query": "world model",
  "total": 123,
  "items": [
    {
      "paper_id": "2401.12345",
      "title": "Example Title",
      "abstract": "Example abstract",
      "score": 0.91,
      "url": "https://arxiv.org/abs/2401.12345",
      "date": "2024-01-20",
      "authors": ["A", "B"]
    }
  ]
}
```

返回字段说明：

- `status`: 固定为 `"success"`
- `query`: 回显原始 query
- `total`: 命中总数
- `items`: 检索结果数组，最多包含请求的top_k个结果
- `items[].paper_id`: 论文 ID，通常是 arXiv ID
- `items[].title`: 标题
- `items[].abstract`: 摘要
- `items[].score`: 检索分数
- `items[].url`: 论文 URL
- `items[].date`: 日期字符串
- `items[].authors`: 作者名数组

示例：

```bash
curl -X POST http://127.0.0.1:8010/v1/search/papers \
  -H 'Content-Type: application/json' \
  -d '{"query":"world model","top_k":3}'
```

### 2) 生成 research 报告

#### `POST /v1/research`

用途：

- 对研究问题做多步检索、阅读和综合
- 返回结构化 `report`（建议markdown渲染）

请求体：

```json
{
  "query": "multimodal world model papers",
  "context": {
    "audience": "ML engineer"
  },
  "history": [
    {
      "role": "user",
      "content": "Focus on 2025 work."
    }
  ],
  "max_iterations": 5,
  "search_top_k": 5,
  "include_trace": true
}
```

字段说明：

- `query`: `string`, 必填, 最短 1 个字符
- `context`: `object`, 可选, 额外上下文
- `history`: `list[{role, content}]`, 可选, 默认空数组
- `history[].role`: `"system" | "user" | "assistant"`
- `history[].content`: `string`, 必填
- `max_iterations`: `int`, 可选, 默认 `5`, 范围 `1..8`
- `search_top_k`: `int`, 可选, 默认 `5`, 范围 `1..10`
- `include_trace`: `bool`, 可选, 默认 `true`

返回体：

```json
{
  "status": "success",
  "message": "Generated research report for query: multimodal world model papers",
  "report": {
    "title": "Example report title",
    "markdown": "# Example report",
    "tool_trace": [],
    "papers_considered": []
  }
}
```

返回字段说明：

- `status`: 当前成功路径下为 `"success"`
- `message`: 人类可读描述
- `report`: 结构化报告对象；具体子字段由 research 生成逻辑决定
- 常见可用字段包括：`title`、`markdown`、`tool_trace`、`papers_considered`

调用建议：

- 直接优先消费 `report.markdown`
- 如果需要调试 agent 行为，再读取 `tool_trace`

示例：

```bash
curl -X POST http://127.0.0.1:8010/v1/research \
  -H 'Content-Type: application/json' \
  -d '{"query":"multimodal world model papers","max_iterations":5,"search_top_k":5,"include_trace":true}'
```

### 3) 生成论文 blog

#### `POST /v1/blog/jobs`

用途：

- 根据选定论文创建一个异步 blog 生成任务

请求体：

```json
{
  "paper_id": "1706.03762",
  "force": false
}
```

字段说明：

- `paper_id`: `string`, 必填, 最短 1 个字符
- `force`: `bool`, 可选, 默认 `false`
  - `false`: 命中缓存则直接复用
  - `true`: 忽略缓存，重新生成

返回体：

```json
{
  "job_id": "c8b8f7...",
  "job_type": "blog",
  "status": "queued",
  "progress": 0,
  "stage": null,
  "message": null,
  "upstream_progress": null
}
```

返回字段说明：

- `job_id`: 后续轮询用的任务 ID
- `job_type`: 固定为 `"blog"`
- `status`: `queued | running | succeeded | failed`
- `progress`: `0..100`
- `stage`: 当前阶段，可为空
- `message`: 当前状态描述，可为空
- `upstream_progress`: 上游任务进度，可为空

#### `GET /v1/blog/jobs/{job_id}`

用途：

- 查询 blog 任务状态

返回体：

```json
{
  "job_id": "c8b8f7...",
  "job_type": "blog",
  "paper_id": "1706.03762",
  "status": "running",
  "progress": 5,
  "stage": "blog_generate",
  "message": "Generating blog markdown",
  "upstream_progress": null,
  "error_message": null,
  "result": null,
  "created_at": "2026-03-23T03:00:00Z",
  "updated_at": "2026-03-23T03:01:00Z"
}
```

返回字段说明：

- `error_message`: 失败时可读错误
- `result`: 任务成功后会包含内部结果索引
- `created_at` / `updated_at`: ISO 时间

#### `GET /v1/blog/jobs/{job_id}/result`

用途：

- 在任务成功后获取最终可下载产物

返回体：

```json
{
  "paper_id": "1706.03762",
  "generated_at": "2026-03-23T03:05:00Z",
  "download_url": "https://...",
  "expires_in_seconds": 1800
}
```

返回字段说明：

- `paper_id`: 论文 ID
- `generated_at`: 生成时间
- `download_url`: 临时下载链接
- `expires_in_seconds`: 默认 `1800`

产物语义：

- 默认返回的是 `blog_inline.md` 的下载链接

异步调用顺序：

1. `POST /v1/blog/jobs`
2. 轮询 `GET /v1/blog/jobs/{job_id}`
3. `status == succeeded` 后调用 `GET /v1/blog/jobs/{job_id}/result`
4. `status == failed` 时读取 `error_message`

示例：

```bash
curl -X POST http://127.0.0.1:8010/v1/blog/jobs \
  -H 'Content-Type: application/json' \
  -d '{"paper_id":"1706.03762","force":false}'
```

### 4) 生成论文 PPT

#### `POST /v1/ppt/jobs`

用途：

- 创建一个异步 PPT 生成任务

请求体：

```json
{
  "paper_id": "1706.03762",
  "force": false,
  "slide_count": 5,
  "language": "en"
}
```

字段说明：

- `paper_id`: `string`, 必填, 最短 1 个字符
- `force`: `bool`, 可选, 默认 `false`
- `slide_count`: `int`, 可选, 范围 `1..30`
- `language`: `string`, 可选

返回体：

```json
{
  "job_id": "f2d1a1...",
  "job_type": "ppt",
  "status": "queued",
  "progress": 0,
  "stage": null,
  "message": null,
  "upstream_progress": null
}
```

#### `GET /v1/ppt/jobs/{job_id}`

用途：

- 查询 PPT 任务状态

返回结构与 blog job detail 相同，只是 `job_type` 为 `"ppt"`。

#### `GET /v1/ppt/jobs/{job_id}/result`

用途：

- 在任务成功后获取最终可下载产物

返回体：

```json
{
  "paper_id": "1706.03762",
  "generated_at": "2026-03-24T12:00:00Z",
  "download_url": "https://...",
  "expires_in_seconds": 1800
}
```

返回字段说明：

- `download_url`: 按顺序拼好的 `slides.pdf` 临时下载链接
- `expires_in_seconds`: 默认 `1800`

产物语义：

- 如果 S3 中已有 slide 图片但还没有 PDF，`/result` 会自动补建 PDF 再返回下载链接

异步调用顺序：

1. `POST /v1/ppt/jobs`
2. 轮询 `GET /v1/ppt/jobs/{job_id}`
3. `status == succeeded` 后调用 `GET /v1/ppt/jobs/{job_id}/result`
4. `status == failed` 时读取 `error_message`

示例：

```bash
curl -X POST http://127.0.0.1:8010/v1/ppt/jobs \
  -H 'Content-Type: application/json' \
  -d '{"paper_id":"1706.03762","slide_count":5,"language":"en","force":false}'
```

## 本地测试脚本

- Research：`python scripts/test_research.py`
- Research live：`python scripts/test_research.py --live --timeout 600`
- Research live 默认使用：`max_iterations=5`、`search_top_k=5`
- Blog job：`python scripts/test_blog_job.py --paper-id 2603.10165 --force`
- Blog job 成功后会通过 `/result` 返回 `blog_inline.md` 的临时下载链接
- PPT job：`python scripts/test_ppt_job.py --paper-id 2603.10165 --slide-count 5 --force`
- PPT job 成功后会通过 `/result` 返回的临时下载链接拉取 `slides.pdf` 到本地
- S3 大对象探测：`python scripts/test_s3_large_upload.py --size-mb 20`

输出目录：

- `outputs/research_tests/`
- `outputs/blog_tests/`
- `outputs/ppt_tests/`
