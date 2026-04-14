# API Contract Standard (Phase 1)

> 最后更新：2026-03 | 规范已并入 `../API接口文档.md` 第 0 节，此为独立副本

## 1. 统一响应 Envelope

所有新接口和已迁移接口必须返回：

```json
{
  "status": "ok",
  "data": {},
  "error": null,
  "meta": {}
}
```

错误时（标准形态）：

```json
{
  "status": "error",
  "data": null,
  "error": {
    "code": "INVALID_INPUT",
    "message": "xxx",
    "details": {}
  },
  "meta": {}
}
```

兼容期（过渡别名）：
- 错误响应在 `error` 外，暂时额外提供 `detail.error` 与 `detail.message`
- 用于兼容仍读取 `body.detail.error` 的旧调用方，后续版本将移除

实现入口：
- `app.contracts.responses.ok(...)`
- `app.contracts.responses.fail(...)`
- `app.contracts.responses.ok_page(...)`

## 2. 全局异常包装（main.py）

- 作用范围：`/api/v1/**`
- 豁免路径：`/api/v1/health`、`/api/v1/health/deep`（保持轻量/深度健康检查原样返回）
- `HTTPException` 与未处理 `Exception` 统一包装为标准 envelope 错误体
- 所有错误响应写入响应头：`X-Error-Code: <ErrorCode>`

## 3. HTTP 状态码与错误码映射

- `422` -> `INVALID_INPUT`
- `INVALID_INPUT` -> `400`
- `NOT_FOUND` -> `404`
- `RATE_LIMITED` -> `429`
- `UPSTREAM_ERROR` -> `502/503/504`
- `PARSE_ERROR` -> `502`
- `CONFIG_ERROR` -> `500`（Phase 1）
- `INTERNAL_ERROR` -> `500`

禁止使用 `HTTP 200` 表示失败。

## 4. 分页规范

分页信息统一放在 `meta.pagination`：

```json
{
  "meta": {
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total": 123,
      "total_pages": 7
    }
  }
}
```

业务列表数据放在 `data.items`。

## 5. 新接口模板（复制即用）

### 5.1 列表接口（分页）

```python
from ..contracts import ApiEnvelope, ErrorCode, ok_page, fail
from fastapi.responses import JSONResponse

ItemsEnvelope = ApiEnvelope[ItemsListData]

@router.get(\"\", response_model=ItemsEnvelope)
def list_items(page: int = 1, page_size: int = 20):
    try:
        items, total = service_list_items(page=page, page_size=page_size)
        total_pages = (total + page_size - 1) // page_size
        return ok_page({\"items\": items}, page=page, page_size=page_size, total=total, total_pages=total_pages)
    except ValueError as exc:
        return JSONResponse(status_code=400, content=fail(ErrorCode.INVALID_INPUT, str(exc)))
    except Exception as exc:
        return JSONResponse(status_code=500, content=fail(ErrorCode.INTERNAL_ERROR, str(exc)))
```

### 5.2 详情接口

```python
DetailEnvelope = ApiEnvelope[ItemDetail]

@router.get(\"/{item_id}\", response_model=DetailEnvelope)
def get_item(item_id: int):
    row = service_get_item(item_id)
    if row is None:
        return JSONResponse(status_code=404, content=fail(ErrorCode.NOT_FOUND, \"不存在\"))
    return ok(row)
```

### 5.3 任务接口（同步/异步）

```python
TaskEnvelope = ApiEnvelope[TaskResultData]

@router.post(\"/run\", response_model=TaskEnvelope)
def run_task(async_mode: bool = False):
    if async_mode:
        return ok({\"task_id\": \"job-1\", \"async\": True, \"status\": \"queued\", \"result\": None})
    result = run_now()
    return ok({\"task_id\": None, \"async\": False, \"status\": \"finished\", \"result\": result})
```

## 6. 前端调用规范（统一客户端）

页面内禁止直接 `fetch(...)`，统一使用：

```js
const data = await window.MarketApp.api.get(\"/api/v1/xxx\");
const envelope = await window.MarketApp.api.getFull(\"/api/v1/xxx?page=1\"); // 需要 meta 时
```

兼容期规则：
- API Client 自动兼容 envelope 和旧裸 JSON
- 页面不自行处理 `response.json()`

## 7. 禁止 Direct Fetch 规则

- 扫描范围：`main/frontend/templates/**/*.html`、`main/frontend/static/js/**/*.js`
- 允许直连 `fetch` 的文件：`main/frontend/static/js/app-shell.js`（提供 `MarketApp.api` 封装）

**当前遗留**（2026-03）：以下页面仍使用 `fetch()`，待迁移至 `MarketApp.api`：
- `market-data-visualization.html`、`graph.html`
- `project-management.html`、`app.html`、`source-library-management.html`
- `backend-dashboard.html`、`data-dashboard.html`、`policy-dashboard.html`、`policy-visualization.html`、`social-media-visualization.html`

**已封存（不再开发）**：`policy-graph.html`、`social-media-graph.html`

**已迁移**：`settings.html`、`policy-state-detail.html`、`policy-tracking.html`

## 8. 规范遵守现状（2026-03）

| 模块 | Envelope | 说明 |
|------|----------|------|
| policies | ✅ | 使用 ok/ok_page/fail |
| ingest, admin, config, discovery, llm_config, project_customization | ✅ | 通过 success_response/error_response 产出 envelope |
| resource_pool, search, governance, indexer | ✅ | 已迁移到 envelope；异常由全局处理统一包装并附带 `X-Error-Code` |
| process, projects, source_library | ✅ | 成功响应已迁移到 `ok(...)`；错误由全局异常处理包装为 envelope（含 `X-Error-Code`、`detail.error` 兼容别名） |
| dashboard, market, products, topics | ✅ | 成功响应已迁移到 `ok(...)`；错误走 `HTTPException` 并由全局异常处理统一包络 |
