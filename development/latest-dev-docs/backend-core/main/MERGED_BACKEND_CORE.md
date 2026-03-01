# Backend Core Merged Draft

> Scope: consolidated from `README.md`, `README.local.md`, `API接口文档.md`, `tests/README.md`.

## 1. 运行（Run）

### 1.1 基础依赖与环境变量

核心依赖：Python 3.11+、PostgreSQL、Redis、Elasticsearch、Node.js/npm（用于 modern 前端）。

核心环境变量：
- `DATABASE_URL`
- `ES_URL`
- `REDIS_URL`

常见可选能力配置：
- LLM: `OPENAI_API_KEY`、`AZURE_*`、`OLLAMA_BASE_URL`
- 搜索: `SERPER_API_KEY`、`GOOGLE_SEARCH_API_KEY`、`GOOGLE_SEARCH_CSE_ID`、`SERPAPI_KEY`、`SERPSTACK_KEY`、`BING_SEARCH_KEY`
- 数据源: `magayo_api_key`、`lotterydata_api_key`、`reddit_client_id`、`reddit_client_secret`、`reddit_user_agent`、`twitter_*`、`rapidapi_key`

未配置相关 key 时，对应抓取/发现能力会自动跳过。

### 1.2 本地启动（推荐）

```bash
# 在 backend 目录
cp .env.example .env
./start-local.sh
```

常用变体：

```bash
./start-local.sh --low-memory
./start-local.sh --non-interactive
./start-local.sh --force
./start-local.sh --with-docker-deps
./stop-local.sh
./stop-local.sh --with-docker-deps
```

脚本会自动处理：`.venv311`、依赖安装、端口检查、本机 PostgreSQL/Redis 尝试拉起、modern 前端、以及本机 Celery worker（默认启用）。

### 1.3 手动启动

```bash
source .venv311/bin/activate
uvicorn app.main:app --reload --port 8000
# 低内存模式
uvicorn app.main:app --port 8000
```

### 1.4 健康检查

```bash
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/health/deep
```

---

## 2. 接口（API）

### 2.1 基本信息

- Base URL: `http://localhost:8000/api/v1`
- Swagger: `http://localhost:8000/docs`
- API Version: `v1`

### 2.2 响应规范（Envelope）

成功：

```json
{"status":"ok","data":{},"error":null,"meta":{}}
```

失败：

```json
{"status":"error","data":null,"error":{"code":"INVALID_INPUT","message":"...","details":{}},"meta":{}}
```

错误码与 HTTP 映射：
- `INVALID_INPUT` -> `400`
- `NOT_FOUND` -> `404`
- `RATE_LIMITED` -> `429`
- `UPSTREAM_ERROR` / `PARSE_ERROR` -> `502`
- `CONFIG_ERROR` / `INTERNAL_ERROR` -> `500`

分页约定：`data.items` + `meta.pagination`。

### 2.3 核心接口分组

健康检查：
- `GET /health`
- `GET /health/deep`

搜索：
- `GET /search`
- `POST /search/_init`

摄取（示例）：
- `POST /ingest/policy`
- `POST /ingest/market`
- `POST /ingest/reports/california`
- `POST /ingest/news/calottery`
- `POST /ingest/news/calottery/retailer`
- `POST /ingest/social/reddit`
- `POST /ingest/reports/weekly`
- `POST /ingest/reports/monthly`
- `POST /ingest/social/sentiment`

发现搜索：
- `POST /discovery/search`
- `POST /discovery/smart`
- `POST /discovery/deep`
- `POST /discovery/generate-keywords`

多数摄取/发现接口支持 `async_mode=true`，返回 `task_id` 用于异步任务跟踪。

完整参数与示例以 `API接口文档.md` 为准。

---

## 3. 测试（Testing）

### 3.1 分层策略

- `unit/`: 纯逻辑隔离测试
- `integration/`: 模块与应用装配测试
- `contract/`: API/Envelope/OpenAPI 契约稳定性测试
- `e2e/`: 端到端烟雾测试

Markers（`pytest.ini`）：
- `unit`、`integration`、`contract`、`e2e`、`slow`、`external`

### 3.2 本地命令

在 `main/backend` 目录执行：

```bash
.venv311/bin/python -m pytest -m unit -q
.venv311/bin/python -m pytest -m integration -q
.venv311/bin/python -m pytest -m contract -q
.venv311/bin/python -m pytest -m e2e -q
.venv311/bin/python -m pytest -q
```

### 3.3 CI Gate

`pull_request`：
- `unit-check`
- `integration-check`
- `docker-check`

`push(main)` / `schedule` / `workflow_dispatch`：
- `unit-check`
- `integration-check`
- `contract-check`
- `e2e-check`
- `docker-check`
