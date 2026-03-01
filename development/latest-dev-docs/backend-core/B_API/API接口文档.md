# 市场情报系统 API 接口文档

> 最后更新：2026-02 | 交互式文档：`http://localhost:8000/docs`

## 概述

本文档描述了市场情报系统的所有 REST API 接口。所有 API 接口均以 `/api/v1` 为前缀。

**基础 URL**: `http://localhost:8000/api/v1`

**API 版本**: v1

**交互式文档**: `http://localhost:8000/docs`

---

## 0. 接口规范（API Contract）

> 规范来源：`docs/API_CONTRACT_STANDARD.md`，新接口与迁移接口须遵守。

### 0.1 统一响应 Envelope

成功：
```json
{"status": "ok", "data": {}, "error": null, "meta": {}}
```

失败（禁止 HTTP 200 表示失败）：
```json
{"status": "error", "data": null, "error": {"code": "INVALID_INPUT", "message": "xxx", "details": {}}, "meta": {}}
```

### 0.2 错误码与 HTTP 映射

| 错误码 | HTTP |
|--------|------|
| INVALID_INPUT | 400 |
| NOT_FOUND | 404 |
| RATE_LIMITED | 429 |
| UPSTREAM_ERROR, PARSE_ERROR | 502 |
| CONFIG_ERROR, INTERNAL_ERROR | 500 |

### 0.3 分页规范

分页信息在 `meta.pagination`，列表数据在 `data.items`。

### 0.4 前端调用

禁止页面内直接 `fetch(...)`，统一使用 `window.MarketApp.api.get(...)` / `getFull(...)`。白名单：`app-shell.js`（提供封装实现）。

### 0.5 规范遵守现状（2026-02）

| 类别 | 状态 | 说明 |
|------|------|------|
| 响应 Envelope | 部分 | `policies` 已用 `ok`/`ok_page`/`fail`；`ingest`/`admin`/`config`/`discovery` 等通过 `success_response`/`error_response` 间接产出 envelope |
| 未用 Envelope | 待迁移 | `projects`、`source_library` 返回裸 JSON，待迁移 |
| 错误 HTTP 码 | 遵守 | 失败时返回 4xx/5xx，未用 200 表示失败 |
| 分页 | 部分 | `policies` 使用 `meta.pagination`；其他列表接口格式不一 |
| 前端 Direct Fetch | 遗留 | 见下方「Direct Fetch 现状」 |

**Direct Fetch 现状**（仍使用 `fetch()` 的页面，待逐步迁移至 `MarketApp.api`）：

- `policy-graph.html`、`social-media-graph.html`、`market-data-visualization.html`、`graph.html`
- `project-management.html`、`app.html`、`source-library-management.html`
- `backend-dashboard.html`、`data-dashboard.html`、`policy-dashboard.html`、`policy-visualization.html`、`social-media-visualization.html`

已使用 `MarketApp.api`：`settings.html`、`policy-state-detail.html`、`policy-tracking.html`、`policy-api.js`。

---

## 通用说明

### 请求格式
- Content-Type: `application/json`
- 所有日期格式：`YYYY-MM-DD`

### 响应格式
- 成功响应：HTTP 200
- 错误响应：HTTP 4xx/5xx，包含错误详情

### 异步任务
部分接口支持异步执行（`async_mode=true`），将返回 `task_id`，可通过任务ID查询执行状态。

---

## 1. 健康检查

### 1.1 基础健康检查
**GET** `/api/v1/health`

检查服务基本状态。

**响应示例**:
```json
{
  "status": "ok",
  "provider": "openai",
  "env": "development"
}
```

### 1.2 深度健康检查
**GET** `/api/v1/health/deep`

检查数据库和 Elasticsearch 连接状态。

**响应示例**:
```json
{
  "status": "ok",
  "database": "ok",
  "elasticsearch": "ok"
}
```

---

## 2. 搜索接口

### 2.1 混合搜索
**GET** `/api/v1/search`

执行混合检索（支持 Elasticsearch）。

**查询参数**:
- `q` (string, 必需): 搜索关键词，默认 "lottery"
- `state` (string, 可选): 州代码过滤，如 "CA"
- `modality` (string): 模式，默认 "any"
- `rank` (string): 排序方式，默认 "hybrid"
- `top_k` (int): 返回结果数量，范围 1-100，默认 10

**响应示例**:
```json
{
  "query": "lottery",
  "state": null,
  "modality": "any",
  "rank": "hybrid",
  "top_k": 10,
  "results": [...]
}
```

### 2.2 初始化搜索索引
**POST** `/api/v1/search/_init`

创建 Elasticsearch 索引（幂等操作）。

**响应示例**:
```json
{
  "created": ["policy_index", "market_index"]
}
```

---

## 3. 数据摄取接口

### 3.1 政策文档摄取
**POST** `/api/v1/ingest/policy`

摄取指定州的政策文档。

**请求体**:
```json
{
  "state": "CA",
  "source_hint": "legiscan",
  "async_mode": false
}
```

**参数说明**:
- `state` (string, 必需): 州代码，如 "CA"
- `source_hint` (string, 可选): 数据源标识
- `async_mode` (bool): 是否异步执行，默认 false

**响应示例**:
```json
{
  "state": "CA",
  "ingested": 15,
  "sources": ["legiscan", "official_site"]
}
```

### 3.2 市场数据摄取
**POST** `/api/v1/ingest/market`

摄取市场数据。

**请求体**:
```json
{
  "state": "CA",
  "source_hint": "magayo",
  "async_mode": false,
  "game": "Powerball",
  "limit": 100
}
```

**参数说明**:
- `state` (string, 必需): 州代码
- `source_hint` (string, 可选): 数据源标识
- `async_mode` (bool): 是否异步执行
- `game` (string, 可选): 玩法过滤，如 "SuperLotto Plus"
- `limit` (int, 可选): 抓取条数上限

### 3.3 加州报告摄取
**POST** `/api/v1/ingest/reports/california`

摄取加州销售报告（PDF）。

**请求体**:
```json
{
  "limit": 3
}
```

**参数说明**:
- `limit` (int): PDF 报告数量上限，范围 1-20，默认 3

### 3.4 加州彩票新闻摄取
**POST** `/api/v1/ingest/news/calottery`

摄取加州彩票官网新闻。

**请求体**:
```json
{
  "limit": 10,
  "async_mode": false
}
```

**参数说明**:
- `limit` (int): 抓取条数，范围 1-50，默认 10
- `async_mode` (bool): 是否异步执行

### 3.5 加州零售商更新摄取
**POST** `/api/v1/ingest/news/calottery/retailer`

摄取加州零售商公告。

**请求体**:
```json
{
  "limit": 10,
  "async_mode": false
}
```

### 3.6 Reddit 讨论摄取
**POST** `/api/v1/ingest/social/reddit`

摄取 Reddit 讨论内容。

**请求体**:
```json
{
  "subreddit": "Lottery",
  "limit": 20,
  "async_mode": false
}
```

**参数说明**:
- `subreddit` (string): 子论坛名称，默认 "Lottery"
- `limit` (int): 抓取贴文数，范围 1-100，默认 20
- `async_mode` (bool): 是否异步执行

### 3.7 周度报告摄取
**POST** `/api/v1/ingest/reports/weekly`

摄取周度市场报告。

**请求体**:
```json
{
  "limit": 10,
  "async_mode": false
}
```

### 3.8 月度报告摄取
**POST** `/api/v1/ingest/reports/monthly`

摄取月度财务报告。

**请求体**:
```json
{
  "limit": 10,
  "async_mode": false
}
```

### 3.9 社交媒体情感数据摄取
**POST** `/api/v1/ingest/social/sentiment`

收集社交媒体情感数据。

**请求体**:
```json
{
  "keywords": ["lottery", "powerball"],
  "platforms": ["reddit"],
  "limit": 20,
  "enable_extraction": true,
  "async_mode": false
}
```

**参数说明**:
- `keywords` (array[string], 必需): 搜索关键词列表
- `platforms` (array[string]): 平台列表，默认 ["reddit"]
- `limit` (int): 每个关键词的结果数量限制，范围 1-100，默认 20
- `enable_extraction` (bool): 是否启用 LLM 结构化提取，默认 true
- `async_mode` (bool): 是否异步执行

### 3.10 政策法规新闻摄取
**POST** `/api/v1/ingest/policy/regulation`

收集政策法规相关新闻。

**请求体**:
```json
{
  "keywords": ["lottery regulation", "gambling law"],
  "limit": 20,
  "enable_extraction": true,
  "async_mode": false
}
```

**参数说明**:
- `keywords` (array[string], 必需): 搜索关键词列表
- `limit` (int): 每个关键词的结果数量限制，范围 1-100，默认 20
- `enable_extraction` (bool): 是否启用 LLM 结构化提取，默认 true
- `async_mode` (bool): 是否异步执行

### 3.11 摄取历史记录
**GET** `/api/v1/ingest/history`

获取数据摄取历史记录。

**查询参数**:
- `limit` (int): 返回记录数，默认 20

**响应示例**:
```json
{
  "jobs": [
    {
      "id": 1,
      "job_type": "ingest_policy",
      "status": "completed",
      "started_at": "2024-01-01T10:00:00",
      "finished_at": "2024-01-01T10:05:00"
    }
  ]
}
```

---

## 4. 市场数据接口

### 4.1 市场统计数据
**GET** `/api/v1/market`

获取市场统计数据。

**查询参数**:
- `state` (string, 必需): 州代码，如 "CA"
- `period` (string): 统计周期，可选 "daily" 或 "monthly"，默认 "daily"
- `game` (string, 可选): 玩法过滤，如 "SuperLotto Plus"

**响应示例**:
```json
{
  "state": "CA",
  "period": "daily",
  "series": [
    {
      "date": "2024-01-01",
      "revenue": 1000000.0,
      "sales_volume": 500000.0,
      "jackpot": 50000000.0,
      "ticket_price": 2.0,
      "game": "Powerball",
      "source_name": "magayo",
      "source_uri": "https://..."
    }
  ]
}
```

### 4.2 获取游戏列表
**GET** `/api/v1/market/games`

获取指定州的游戏列表。

**查询参数**:
- `state` (string, 必需): 州代码

**响应示例**:
```json
{
  "state": "CA",
  "games": ["Powerball", "Mega Millions", "SuperLotto Plus"]
}
```

---

## 5. 政策接口

### 5.1 政策列表
**GET** `/api/v1/policies`

获取政策列表（支持分页和过滤）。

**查询参数**:
- `state` (string, 可选): 州代码，如 "CA"
- `policy_type` (string, 可选): 政策类型
- `status` (string, 可选): 政策状态
- `start` (string, 可选): 开始日期 YYYY-MM-DD
- `end` (string, 可选): 结束日期 YYYY-MM-DD
- `page` (int): 页码，默认 1
- `page_size` (int): 每页数量，范围 1-100，默认 20
- `sort_by` (string): 排序字段，默认 "publish_date"
- `sort_order` (string): 排序方向，可选 "asc" 或 "desc"，默认 "desc"

**响应示例**:
```json
{
  "items": [
    {
      "id": 1,
      "title": "California Lottery Act",
      "state": "CA",
      "status": "active",
      "publish_date": "2024-01-01",
      "effective_date": "2024-01-15",
      "policy_type": "regulation",
      "key_points": ["...", "..."],
      "summary": "...",
      "uri": "https://...",
      "created_at": "2024-01-01T10:00:00"
    }
  ],
  "total": 100,
  "page": 1,
  "page_size": 20,
  "total_pages": 5
}
```

### 5.2 政策统计
**GET** `/api/v1/policies/stats`

获取政策统计数据。

**查询参数**:
- `start` (string, 可选): 开始日期 YYYY-MM-DD
- `end` (string, 可选): 结束日期 YYYY-MM-DD

**响应示例**:
```json
{
  "total": 150,
  "active_count": 120,
  "states_count": 10,
  "state_distribution": [
    {"state": "CA", "count": 50},
    {"state": "NY", "count": 30}
  ],
  "type_distribution": [
    {"policy_type": "regulation", "count": 80},
    {"policy_type": "law", "count": 70}
  ],
  "status_distribution": [
    {"status": "active", "count": 120},
    {"status": "pending", "count": 30}
  ],
  "trend_series": [
    {"date": "2024-01-01", "count": 5},
    {"date": "2024-02-01", "count": 8}
  ]
}
```

### 5.3 州级政策详情
**GET** `/api/v1/policies/state/{state}`

获取指定州的政策详情和统计。

**路径参数**:
- `state` (string, 必需): 州代码，如 "CA"

**查询参数**:
- `start` (string, 可选): 开始日期 YYYY-MM-DD
- `end` (string, 可选): 结束日期 YYYY-MM-DD

**响应示例**:
```json
{
  "state": "CA",
  "policies": [...],
  "statistics": {
    "total": 50,
    "active_count": 40,
    "most_common_type": "regulation",
    "type_distribution": [...],
    "entity_distribution": [...],
    "relation_distribution": [...],
    "key_points_count": 200
  }
}
```

### 5.4 政策详情
**GET** `/api/v1/policies/{policy_id}`

获取单个政策的详细信息。

**路径参数**:
- `policy_id` (int, 必需): 政策ID

**响应示例**:
```json
{
  "id": 1,
  "title": "California Lottery Act",
  "state": "CA",
  "status": "active",
  "publish_date": "2024-01-01",
  "effective_date": "2024-01-15",
  "policy_type": "regulation",
  "key_points": ["...", "..."],
  "summary": "...",
  "content": "...",
  "uri": "https://...",
  "source_id": 1,
  "created_at": "2024-01-01T10:00:00",
  "updated_at": "2024-01-01T10:00:00",
  "entities": [...],
  "relations": [...]
}
```

---

## 6. 报告接口

### 6.1 生成报告
**POST** `/api/v1/reports`

生成 HTML 或 CSV 格式的报告。

**请求体**:
```json
{
  "states": ["CA", "NY"],
  "start": "2024-01-01",
  "end": "2024-12-31",
  "format": "html"
}
```

**参数说明**:
- `states` (array[string]): 州代码列表，默认 ["CA"]
- `start` (string, 可选): 开始日期 YYYY-MM-DD
- `end` (string, 可选): 结束日期 YYYY-MM-DD
- `format` (string): 报告格式，可选 "html" 或 "csv"，默认 "html"

**响应**:
- HTML 格式：返回 JSON，包含 `data` 字段（HTML 内容）
- CSV 格式：返回文件下载

---

## 7. 配置接口

### 7.1 获取配置
**GET** `/api/v1/config`

获取运行时配置（安全子集）。

**响应示例**:
```json
{
  "env": "development",
  "llm_provider": "openai",
  "embedding_model": "text-embedding-ada-002",
  "es_url": "http://localhost:9200"
}
```

### 7.2 获取环境变量设置
**GET** `/api/v1/config/env`

获取所有环境变量配置。

**响应示例**:
```json
{
  "DATABASE_URL": "postgresql://...",
  "ES_URL": "http://localhost:9200",
  "LLM_PROVIDER": "openai",
  ...
}
```

### 7.3 更新环境变量设置
**POST** `/api/v1/config/env`

更新环境变量配置。

**请求体**:
```json
{
  "DATABASE_URL": "postgresql://...",
  "ES_URL": "http://localhost:9200",
  "OPENAI_API_KEY": "...",
  ...
}
```

**响应示例**:
```json
{
  "updated": ["DATABASE_URL", "ES_URL"]
}
```

### 7.4 重新加载配置
**POST** `/api/v1/config/reload`

重新加载环境变量配置。

**响应示例**:
```json
{
  "status": "reloaded"
}
```

---

## 8. 管理接口

### 8.1 获取统计信息
**GET** `/api/v1/admin/stats`

获取数据库统计信息。

**响应示例**:
```json
{
  "documents": {
    "total": 1000,
    "recent_today": 50
  },
  "sources": {
    "total": 20
  },
  "market_stats": {
    "total": 5000
  },
  "search_history": {
    "total": 200
  }
}
```

### 8.2 文档列表
**POST** `/api/v1/admin/documents/list`

列出文档（支持分页和搜索）。

**请求体**:
```json
{
  "page": 1,
  "page_size": 20,
  "state": "CA",
  "doc_type": "policy",
  "search": "lottery"
}
```

**参数说明**:
- `page` (int): 页码，默认 1
- `page_size` (int): 每页数量，范围 1-100，默认 20
- `state` (string, 可选): 州代码过滤
- `doc_type` (string, 可选): 文档类型过滤
- `search` (string, 可选): 搜索关键词（标题、摘要、URI）

**响应示例**:
```json
{
  "items": [
    {
      "id": 1,
      "title": "...",
      "doc_type": "policy",
      "state": "CA",
      "source_id": 1,
      "created_at": "2024-01-01T10:00:00",
      "publish_date": "2024-01-01",
      "has_extracted_data": true
    }
  ],
  "total": 100,
  "page": 1,
  "page_size": 20
}
```

### 8.3 获取文档详情
**GET** `/api/v1/admin/documents/{doc_id}`

获取单个文档的详细信息。

**路径参数**:
- `doc_id` (int, 必需): 文档ID

**响应示例**:
```json
{
  "id": 1,
  "title": "...",
  "doc_type": "policy",
  "state": "CA",
  "status": "active",
  "publish_date": "2024-01-01",
  "content": "...",
  "summary": "...",
  "uri": "https://...",
  "extracted_data": {...},
  "source_id": 1,
  "created_at": "2024-01-01T10:00:00",
  "updated_at": "2024-01-01T10:00:00"
}
```

### 8.4 删除文档
**POST** `/api/v1/admin/documents/delete`

批量删除文档。

**请求体**:
```json
{
  "ids": [1, 2, 3]
}
```

**响应示例**:
```json
{
  "deleted": 3
}
```

### 8.5 重新提取文档
**POST** `/api/v1/admin/documents/re-extract`

重新提取文档的结构化数据。

**请求体**:
```json
{
  "doc_ids": [1, 2, 3],
  "force": false
}
```

**参数说明**:
- `doc_ids` (array[int], 可选): 文档ID列表，如果为空则提取所有政策/市场文档
- `force` (bool): 是否强制重新提取已有数据的文档，默认 false

**响应示例**:
```json
{
  "total": 10,
  "success": 8,
  "error": 1,
  "skipped": 1
}
```

### 8.6 数据源列表
**POST** `/api/v1/admin/sources/list`

列出数据源。

**请求体**:
```json
{
  "page": 1,
  "page_size": 20,
  "kind": "official",
  "enabled": true
}
```

**参数说明**:
- `page` (int): 页码
- `page_size` (int): 每页数量
- `kind` (string, 可选): 数据源类型过滤
- `enabled` (bool, 可选): 是否启用过滤

**响应示例**:
```json
{
  "items": [
    {
      "id": 1,
      "name": "California Lottery Official",
      "kind": "official",
      "base_url": "https://...",
      "enabled": true,
      "document_count": 100,
      "created_at": "2024-01-01T10:00:00"
    }
  ],
  "total": 20,
  "page": 1,
  "page_size": 20
}
```

### 8.7 市场数据列表
**POST** `/api/v1/admin/market-stats/list`

列出市场数据。

**请求体**:
```json
{
  "page": 1,
  "page_size": 20,
  "state": "CA",
  "game": "Powerball",
  "start_date": "2024-01-01",
  "end_date": "2024-12-31"
}
```

**响应示例**:
```json
{
  "items": [
    {
      "id": 1,
      "state": "CA",
      "game": "Powerball",
      "date": "2024-01-01",
      "sales_volume": 500000.0,
      "revenue": 1000000.0,
      "jackpot": 50000000.0,
      "ticket_price": 2.0,
      "source_name": "magayo",
      "source_uri": "https://..."
    }
  ],
  "total": 1000,
  "page": 1,
  "page_size": 20
}
```

### 8.8 搜索历史
**GET** `/api/v1/admin/search-history`

获取搜索历史记录。

**查询参数**:
- `page` (int): 页码，范围 >=1，默认 1
- `page_size` (int): 每页数量，范围 1-1000，默认 100

**响应示例**:
```json
{
  "items": [
    {
      "id": 1,
      "topic": "California lottery",
      "last_search_time": "2024-01-01T10:00:00"
    }
  ],
  "total": 120,
  "page": 1,
  "page_size": 100
}
```

---

## 9. 仪表盘接口

### 9.1 仪表盘统计
**GET** `/api/v1/dashboard/stats`

获取仪表盘概览统计数据。

**响应示例**:
```json
{
  "documents": {
    "total": 1000,
    "recent_today": 50,
    "recent_7d": 300,
    "type_distribution": {
      "policy": 500,
      "market": 300,
      "social_sentiment": 200
    },
    "extraction_rate": 85.5
  },
  "sources": {
    "total": 20,
    "enabled": 18
  },
  "market_stats": {
    "total": 5000,
    "states_count": 10
  },
  "search_history": {
    "total": 200
  },
  "tasks": {
    "total": 100,
    "running": 2,
    "completed": 95,
    "failed": 3
  }
}
```

### 9.2 市场趋势
**GET** `/api/v1/dashboard/market-trends`

获取市场趋势数据。

**查询参数**:
- `state` (string, 可选): 州过滤
- `game` (string, 可选): 游戏类型过滤
- `start_date` (string, 可选): 开始日期 YYYY-MM-DD
- `end_date` (string, 可选): 结束日期 YYYY-MM-DD
- `period` (string): 聚合周期，可选 "daily" 或 "monthly"，默认 "daily"

**响应示例**:
```json
{
  "series": [...],
  "state_distribution": [
    {
      "state": "CA",
      "count": 1000,
      "total_revenue": 100000000.0
    }
  ],
  "game_distribution": [
    {
      "game": "Powerball",
      "count": 500,
      "avg_revenue": 2000000.0
    }
  ],
  "period": "daily"
}
```

### 9.3 文档分析
**GET** `/api/v1/dashboard/document-analysis`

获取文档分析数据。

**查询参数**:
- `start_date` (string, 可选): 开始日期 YYYY-MM-DD
- `end_date` (string, 可选): 结束日期 YYYY-MM-DD

**响应示例**:
```json
{
  "type_distribution": [
    {"type": "policy", "count": 500}
  ],
  "growth_trend": [
    {"date": "2024-01-01", "count": 10}
  ],
  "state_distribution": [
    {"state": "CA", "count": 300}
  ],
  "source_contribution": [
    {"source_name": "Official Site", "count": 200}
  ],
  "extraction_by_type": [
    {
      "type": "policy",
      "total": 500,
      "with_extracted": 450,
      "rate": 90.0
    }
  ]
}
```

### 9.4 情感分析
**GET** `/api/v1/dashboard/sentiment-analysis`

获取社交媒体情感分析数据。

**查询参数**:
- `start_date` (string, 可选): 开始日期 YYYY-MM-DD
- `end_date` (string, 可选): 结束日期 YYYY-MM-DD

**响应示例**:
```json
{
  "sentiment_distribution": {
    "positive": 100,
    "negative": 50,
    "neutral": 150,
    "unknown": 10
  },
  "platform_distribution": [
    {
      "platform": "reddit",
      "count": 200,
      "positive": 80,
      "negative": 40,
      "neutral": 80
    }
  ],
  "sentiment_trend": [
    {
      "date": "2024-01-01",
      "positive": 10,
      "negative": 5,
      "neutral": 15
    }
  ],
  "keyword_ranking": [
    {"keyword": "lottery", "count": 50}
  ],
  "total_documents": 310
}
```

### 9.5 情感数据源
**GET** `/api/v1/dashboard/sentiment-sources`

根据筛选条件获取情感数据源列表。

**查询参数**:
- `sentiment` (string, 可选): 情感类型，可选 "positive", "negative", "neutral", "unknown"
- `platform` (string, 可选): 平台名称
- `start_date` (string, 可选): 开始日期 YYYY-MM-DD
- `end_date` (string, 可选): 结束日期 YYYY-MM-DD
- `limit` (int): 返回数量限制，范围 1-200，默认 50

**响应示例**:
```json
{
  "sources": [
    {
      "id": 1,
      "title": "...",
      "uri": "https://...",
      "platform": "reddit",
      "sentiment": "positive",
      "created_at": "2024-01-01T10:00:00",
      "publish_date": "2024-01-01",
      "summary": "..."
    }
  ],
  "total": 50,
  "filters": {
    "sentiment": "positive",
    "platform": "reddit",
    "start_date": "2024-01-01",
    "end_date": "2024-12-31"
  }
}
```

### 9.6 任务监控
**GET** `/api/v1/dashboard/task-monitoring`

获取任务监控数据。

**查询参数**:
- `limit` (int): 返回数量限制，范围 1-500，默认 50
- `status` (string, 可选): 任务状态过滤

**响应示例**:
```json
{
  "recent_tasks": [
    {
      "id": 1,
      "job_type": "ingest_policy",
      "status": "completed",
      "started_at": "2024-01-01T10:00:00",
      "finished_at": "2024-01-01T10:05:00",
      "duration_seconds": 300,
      "error": null
    }
  ],
  "type_distribution": [
    {
      "job_type": "ingest_policy",
      "count": 50,
      "completed": 48,
      "failed": 2
    }
  ]
}
```

### 9.7 搜索分析
**GET** `/api/v1/dashboard/search-analytics`

获取搜索行为分析数据。

**查询参数**:
- `limit` (int): 返回数量限制，范围 1-500，默认 50

**响应示例**:
```json
{
  "popular_topics": [
    {"topic": "California lottery", "count": 50}
  ],
  "search_trend": [
    {"date": "2024-01-01", "count": 10}
  ]
}
```

---

## 10. 发现接口

### 10.1 发现搜索
**POST** `/api/v1/discovery/search`

执行数据源发现搜索。

**请求体**:
```json
{
  "topic": "California lottery",
  "language": "en",
  "max_results": 10,
  "provider": "auto",
  "days_back": 30,
  "exclude_existing": true
}
```

**查询参数**:
- `debug` (bool): 是否返回调试信息，默认 false
- `persist` (bool): 是否持久化结果，默认 true

**参数说明**:
- `topic` (string, 必需): 搜索主题或关键词
- `language` (string): 关键词语言，可选 "zh" 或 "en"，默认 "en"
- `max_results` (int): 最大结果数，范围 1-50，默认 10
- `provider` (string): 搜索服务提供商，可选 "auto", "ddg", "google", "serpstack", "serpapi"，默认 "auto"
- `days_back` (int, 可选): 只搜索最近N天的内容，范围 1-365
- `exclude_existing` (bool): 是否排除已入库的文档，默认 true

**响应示例**:
```json
{
  "keywords": ["California lottery", "lottery CA"],
  "results": [
    {
      "title": "...",
      "uri": "https://...",
      "source": "google",
      "keyword": "California lottery"
    }
  ],
  "provider_used": "google",
  "stored": {
    "saved": 5,
    "skipped": 3
  }
}
```

### 10.2 智能发现
**POST** `/api/v1/discovery/smart`

智能搜索：自动增量搜索，只返回新信息。

**请求体**:
```json
{
  "topic": "California lottery",
  "language": "en",
  "max_results": 10,
  "provider": "auto",
  "days_back": 30
}
```

**查询参数**:
- `persist` (bool): 是否持久化结果，默认 true

**响应示例**:
```json
{
  "topic": "California lottery",
  "results": [...],
  "count": 5,
  "provider_used": "google",
  "stored": {
    "saved": 3,
    "skipped": 2
  }
}
```

### 10.3 深度发现
**POST** `/api/v1/discovery/deep`

执行深度搜索（多轮迭代搜索）。

**请求体**:
```json
{
  "topic": "California lottery",
  "language": "en",
  "iterations": 2,
  "breadth": 2,
  "max_results": 20
}
```

**查询参数**:
- `persist` (bool): 是否持久化结果，默认 true

**参数说明**:
- `topic` (string, 必需): 搜索主题或关键词
- `language` (string): 关键词语言，默认 "en"
- `iterations` (int): 迭代次数，范围 1-5，默认 2
- `breadth` (int): 每轮搜索广度，范围 1-10，默认 2
- `max_results` (int): 最大结果数，范围 1-100，默认 20

**响应示例**:
```json
{
  "topic": "California lottery",
  "results": [...],
  "iterations": 2,
  "total_found": 15,
  "stored": {
    "saved": 10,
    "skipped": 5
  }
}
```

---

## 11. 索引接口

### 11.1 重新索引政策文档
**POST** `/api/v1/indexer/policy`

重新索引政策文档（生成嵌入向量）。

**请求体**:
```json
{
  "document_ids": [1, 2, 3],
  "state": "CA"
}
```

**参数说明**:
- `document_ids` (array[int], 可选): 文档ID列表，如果为空则索引所有政策文档
- `state` (string, 可选): 州代码过滤

**响应示例**:
```json
{
  "indexed": 10,
  "failed": 0,
  "skipped": 2
}
```

---

## 12. 监控接口

### 12.1 Prometheus 指标
**GET** `/metrics`

获取 Prometheus 格式的监控指标。

**响应**: Prometheus 格式的指标数据

---

## 13. 补充接口（项目/主题/进程/信息源库/LLM 配置/治理）

以下接口详见 OpenAPI (`/docs`)，此处仅列路径与用途。

### 13.1 项目与租户 (`/projects`)

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/v1/projects` | 项目列表 |
| POST | `/api/v1/projects` | 创建项目 |
| PATCH | `/api/v1/projects/{project_key}` | 更新项目 |
| POST | `/api/v1/projects/{project_key}/activate` | 激活项目 |
| POST | `/api/v1/projects/{project_key}/archive` | 归档 |
| POST | `/api/v1/projects/{project_key}/restore` | 恢复 |
| DELETE | `/api/v1/projects/{project_key}` | 删除项目 |

### 13.2 主题 (`/topics`)

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/v1/topics` | 主题列表 |
| POST | `/api/v1/topics` | 创建主题 |
| PUT | `/api/v1/topics/{topic_id}` | 更新主题 |
| DELETE | `/api/v1/topics/{topic_id}` | 删除主题 |

### 13.3 商品 (`/products`)

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/v1/products` | 商品列表 |
| POST | `/api/v1/products` | 创建商品 |
| PUT | `/api/v1/products/{product_id}` | 更新商品 |
| DELETE | `/api/v1/products/{product_id}` | 删除商品 |

### 13.4 进程与任务 (`/process`)

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/v1/process/list` | 任务列表 |
| GET | `/api/v1/process/stats` | 任务统计 |
| GET | `/api/v1/process/history` | 任务历史 |
| GET | `/api/v1/process/{task_id}` | 任务详情 |
| GET | `/api/v1/process/{task_id}/logs` | 任务日志 |
| POST | `/api/v1/process/{task_id}/cancel` | 取消任务 |

### 13.5 信息源库 (`/source_library`)

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/v1/source_library/channels` | 频道列表 |
| GET | `/api/v1/source_library/items` | 条目列表 |
| POST | `/api/v1/source_library/items` | 创建条目 |
| POST | `/api/v1/source_library/items/{item_key}/run` | 执行条目 |
| POST | `/api/v1/source_library/sync_shared_from_files` | 从文件同步共享配置 |

### 13.6 项目定制 (`/project-customization`)

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/v1/project-customization/menu` | 菜单配置 |
| GET | `/api/v1/project-customization/workflows` | 工作流列表 |
| GET | `/api/v1/project-customization/llm-mapping` | LLM 映射 |
| GET | `/api/v1/project-customization/graph-config` | 图谱配置 |
| POST | `/api/v1/project-customization/workflows/{workflow_name}/run` | 执行工作流 |

### 13.7 LLM 配置 (`/llm-config`)

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/v1/llm-config` | 全局配置列表 |
| GET | `/api/v1/llm-config/service/{service_name}` | 单服务配置 |
| POST | `/api/v1/llm-config` | 创建配置 |
| PUT | `/api/v1/llm-config/service/{service_name}` | 更新配置 |
| DELETE | `/api/v1/llm-config/service/{service_name}` | 删除配置 |
| GET | `/api/v1/llm-config/projects/{project_key}` | 项目级配置列表 |
| POST | `/api/v1/llm-config/projects/{project_key}/copy-from` | 从其他项目复制 |

### 13.8 治理 (`/governance`)

| Method | Path | 说明 |
|--------|------|------|
| POST | `/api/v1/governance/cleanup` | 数据清理（保留策略） |
| POST | `/api/v1/governance/aggregator/sync` | 聚合同步触发 |

### 13.9 发现扩展

| Method | Path | 说明 |
|--------|------|------|
| POST | `/api/v1/discovery/generate-keywords` | 关键词生成 |
| POST | `/api/v1/discovery/generate-subreddit-keywords` | Reddit 子版关键词生成 |

### 13.10 仪表盘扩展

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/v1/dashboard/global/stats` | 全局统计 |
| GET | `/api/v1/dashboard/commodity-trends` | 商品趋势 |
| GET | `/api/v1/dashboard/ecom-price-trends` | 电商价格趋势 |

### 13.11 管理扩展（图谱导出）

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/v1/admin/export-graph` | 导出图谱 |
| GET | `/api/v1/admin/content-graph` | 内容图谱 |
| GET | `/api/v1/admin/market-graph` | 市场图谱 |
| GET | `/api/v1/admin/policy-graph` | 政策图谱 |
| POST | `/api/v1/admin/social-data/list` | 社交数据列表 |

---

## 错误码说明

### HTTP 状态码
- `200 OK`: 请求成功
- `400 Bad Request`: 请求参数错误
- `404 Not Found`: 资源不存在
- `500 Internal Server Error`: 服务器内部错误
- `503 Service Unavailable`: 服务不可用（通常是数据库或 Elasticsearch 连接失败）

### 错误响应格式

新接口使用 envelope：`{"status":"error","error":{"code":"...","message":"..."}}`。部分历史接口仍返回 FastAPI 默认 `{"detail":"..."}`，逐步迁移中。

---

## 注意事项

1. **异步任务**: 当 `async_mode=true` 时，接口会立即返回 `task_id`，实际任务在后台执行。可通过任务监控接口查询执行状态。

2. **分页**: 所有列表接口都支持分页，默认每页 20 条记录。

3. **日期格式**: 所有日期参数和响应均使用 `YYYY-MM-DD` 格式。

4. **数据库连接**: 如果数据库服务不可用，相关接口会返回 503 错误。

5. **Elasticsearch**: 搜索相关功能需要 Elasticsearch 服务正常运行。

6. **API Key**: 部分功能（如 LLM 提取、搜索 API）需要配置相应的 API Key，详见配置接口。

---

## 更新日志

- **2026-02**: 补充规范遵守现状（0.5）、Direct Fetch 现状；修正 project-customization 路径（下划线→连字符）
- **2026-02**: 合并 API 规范（第 0 节），补充项目/主题/进程/信息源库/LLM 配置/治理等接口（第 13 节）
- **2024-01**: 初始版本，包含所有基础接口
