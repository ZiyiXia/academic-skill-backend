# academic-skill-backend

独立的 FastAPI 后端，提供 4 类能力：

- 论文搜索（`/v1/search/papers`）
- 多步 research 报告生成（`/v1/research`）
- 论文 blog 异步生成（`/v1/blog/jobs*`）
- 论文 PPT 异步生成（`/v1/ppt/jobs*`）

后端不依赖数据库，任务状态与结果索引存储在 S3。

## API 概览

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

## 环境变量

### 必填

这些变量在启动时必须存在：

- `SEARCH_API_URL`
- `PPT_CREATE_URL`
- `ARXIV_PDF_BASE_URL`
- `S3_BUCKET`

### 常用可选（有默认值或可回退）

- `APP_NAME`（默认：`academic-skill-backend`）
- `APP_ENV`（默认：`development`）
- `LOG_LEVEL`（默认：`INFO`）
- `RAG_API_BASE_URL`（默认：`https://data.rag.ac.cn`）
- `RAG_API_TOKEN`（未配置时使用内置默认值）
- `S3_REGION`（默认：`us-east-1`）
- `S3_ENDPOINT` / `S3_ACCESS_KEY` / `S3_SECRET_KEY`
- `BLOG_S3_PREFIX`（默认：`deepxiv/blogs`）
- `SLIDES_S3_SUBDIR`（默认：`slides`）
- `SKILL_JOB_PREFIX`（默认：`academic-skill/jobs`）
- `BLOG_IMAGE_GEN_URL`（默认：`http://120.92.112.87:32500`）
- `BLOG_LLM_BASE_URL`（默认：`https://api.openai.com/v1`）
- `BLOG_LLM_API_KEY`（blog 生成时必需）
- `BLOG_LLM_MODEL`（默认：`gpt-4.1`）
- `RESEARCH_LLM_BASE_URL` / `RESEARCH_LLM_API_KEY` / `RESEARCH_LLM_MODEL`
  - 未配置时会回退到 `BLOG_LLM_*`
- `SLIDES_DEFAULT_COUNT`（默认：`5`）
- `SLIDES_DEFAULT_LANG`（默认：`en`）

## Job 调用约定（blog / ppt）

`blog` 和 `ppt` 是异步任务，不要把创建接口的返回当成最终结果。

固定流程：

1. 调用创建接口拿 `job_id`
2. 轮询 `/jobs/{job_id}`
3. `status == succeeded` 后再取 `/jobs/{job_id}/result`
4. `status == failed` 时读取 `error_message`

状态枚举：`queued | running | succeeded | failed`

## 关键请求示例

### 1) 搜索论文

```bash
curl -X POST http://127.0.0.1:8010/v1/search/papers \
  -H 'Content-Type: application/json' \
  -d '{"query":"world model","top_k":3}'
```

### 2) 生成 research 报告

```bash
curl -X POST http://127.0.0.1:8010/v1/research \
  -H 'Content-Type: application/json' \
  -d '{"query":"multimodal world model papers","max_iterations":4,"search_top_k":5,"include_trace":true}'
```

### 3) 创建 blog 任务

```bash
curl -X POST http://127.0.0.1:8010/v1/blog/jobs \
  -H 'Content-Type: application/json' \
  -d '{"paper_id":"1706.03762","force":false}'
```

### 4) 创建 PPT 任务

```bash
curl -X POST http://127.0.0.1:8010/v1/ppt/jobs \
  -H 'Content-Type: application/json' \
  -d '{"paper_id":"1706.03762","slide_count":5,"language":"en","force":false}'
```

## 本地测试脚本

- Research：`python scripts/test_research.py`
- Research live：`python scripts/test_research.py --live --timeout 600`
- Blog job：`python scripts/test_blog_job.py --paper-id 2603.10165 --force`
- PPT job：`python scripts/test_ppt_job.py --paper-id 2603.10165 --slide-count 5 --force`
- S3 大对象探测：`python scripts/test_s3_large_upload.py --size-mb 20`

输出目录：

- `outputs/research_tests/`
- `outputs/blog_tests/`
- `outputs/ppt_tests/`
