# Frontend Modernization API Map (2026-02-27)

目标：在前端换栈前，固定与后端通信的最小契约，避免 UI 重做后接口反复返工。

## 1. 全局约定

- API 前缀：`/api/v1`
- 项目隔离：
  - Query 参数：`project_key=<key>`
  - Header：`X-Project-Key: <key>`
- 响应外层（主流接口）：`ApiEnvelope`

```json
{
  "status": "ok | error",
  "data": {},
  "error": { "code": "...", "message": "...", "details": {} },
  "meta": { "trace_id": null, "project_key": "demo_proj", "pagination": null }
}
```

## 2. 路由总览来源

- 全量路由盘点：`main/backend/docs/API_ROUTE_INVENTORY_2026-02-27.md`（自动解析，135 条）
- 路由源码目录：`main/backend/app/api/*.py`

## 3. 前端换栈优先接入（P0）

### 3.1 基础与项目

- `GET /api/v1/health`
- `GET /api/v1/projects`
- `POST /api/v1/projects`
- `POST /api/v1/projects/{project_key}/activate`

用途：应用启动、项目切换、创建项目。

### 3.2 采集工作台

- `POST /api/v1/ingest/policy`
- `POST /api/v1/ingest/policy/regulation`
- `POST /api/v1/ingest/market`
- `POST /api/v1/ingest/social/sentiment`
- `POST /api/v1/ingest/commodity/metrics`
- `POST /api/v1/ingest/ecom/prices`
- `GET /api/v1/ingest/history`
- `POST /api/v1/ingest/source-library/sync`
- `POST /api/v1/ingest/source-library/run`

用途：核心业务入口与历史任务回看。

### 3.3 来源库/资源池（采集前置）

- `GET /api/v1/source_library/items`
- `GET /api/v1/source_library/items/grouped`
- `GET /api/v1/source_library/channels`
- `GET /api/v1/resource_pool/site_entries/grouped`

用途：来源项选择、按 handler 聚类运行。

### 3.4 流程与任务

- `GET /api/v1/process/list`
- `GET /api/v1/process/history`
- `GET /api/v1/process/{task_id}`
- `GET /api/v1/process/{task_id}/logs`
- `POST /api/v1/process/{task_id}/cancel`

用途：异步任务监控页。

### 3.5 看板

- `GET /api/v1/dashboard/stats`
- `GET /api/v1/dashboard/market-trends`
- `GET /api/v1/dashboard/sentiment-analysis`
- `GET /api/v1/dashboard/search-analytics`
- `GET /api/v1/dashboard/task-monitoring`

用途：首页可视化核心指标。

## 4. 建议迁移节奏

- Phase A（先活）：只接入 P0 路由，保证主链路可用。
- Phase B（再全）：补 admin / policy 详情 / graph 相关 API。
- Phase C（收口）：引入自动类型生成（OpenAPI -> TS types）替代手写类型。

## 5. 风险与注意

- 部分历史接口可能返回“裸 JSON”而非标准 envelope，前端 client 需做双格式兼容。
- 任务触发接口常支持 `async_mode=true`，前端需统一处理 `task_id` 与轮询逻辑。
- 新前端必须保留项目维度传参（query + header），否则会落到错误 schema 或默认项目。
