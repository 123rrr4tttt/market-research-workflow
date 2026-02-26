# 资源池提取模块 - 接口设计

> 最后更新：2026-02 | 文档索引：`docs/README.md`

## 1. 总库/子项目库贯穿原则

**所有资源池相关行为必须贯穿总库/子项目库二分**：

| 维度 | 总库 (shared) | 子项目库 (project) |
|------|---------------|---------------------|
| 存储位置 | `public` schema | `project_{key}` schema |
| 可见性 | 跨项目共享 | 仅当前项目 |
| scope 取值 | `shared` | `project` |
| 合并视图 | `effective` = shared ∪ project（project 覆盖 shared 同 key） |

- 写操作：必须显式指定 `scope: "shared" | "project"`，决定落库位置
- 读操作：必须支持 `scope: "shared" | "project" | "effective"`
- 配置/列表：所有接口均需 `scope` 参数，缺省 `effective`

## 2. 概念区分

项目中存在两类「资源池」概念，均遵循总库/子项目库二分：

| 概念 | 已实现位置 | 职责 |
|------|------------|------|
| **News resource pool**（采集资源池） | `project_customization.get_news_resource_handlers()` | `resource_id` → 采集 handler。总库：通用源（如 google_news）；子项目库：项目专有源（如 calottery） |
| **Resource pool extraction**（URL 资源池） | 本文档 | 从文档、任务中提取 URL 并持久化。总库/子项目库分别存储 |

本文档描述的是 **URL 资源池提取**，与采集资源池互补：采集 handler 执行时产生的 URL 可被本模块捕获入库。

## 3. 模块定位

资源池提取模块（Resource Pool Extraction）负责从多种来源收集 URL，形成可复用的 URL 资源池，**贯穿总库/子项目库**：

- **子项目库**：按 `project_key` 隔离，数据落在项目 schema
- **总库**：跨项目共享，数据落在 `public` schema（与 source_library 的 shared 模式一致）

## 4. 两个入口

| 入口 | 说明 | 数据来源 |
|------|------|----------|
| **文档提取** | 从已有 Document 的 content/extracted_data 中提取 URL | `documents` 表 |
| **任务捕获** | 正在进行的任务（ingest/discovery/source_library）中自动捕获 URL + 爬取机制适配 | EtlJobRun、store、adapter 等 |

## 5. 接口模式

### 5.1 路由前缀与租户

- **前缀**：`/api/v1/resource_pool`
- **租户**：所有写操作需 `project_key`（header `X-Project-Key` 或 query `project_key`）
- **Scope**：`scope: shared | project | effective`，与 source_library 一致

### 5.2 入口一：从文档提取 URL

#### POST `/api/v1/resource_pool/extract/from-documents`

从已有文档中提取 URL 并写入资源池。

**请求体**：

```json
{
  "project_key": "online_lottery",
  "scope": "project",
  "filters": {
    "doc_type": ["policy", "market"],
    "state": ["CA"],
    "document_ids": [1, 2, 3],
    "limit": 500
  },
  "async_mode": false
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| project_key | string | 是 | 项目标识 |
| scope | "project" \| "shared" | 否 | 默认 `project`。`shared` 写入总库 |
| filters | object | 否 | 文档过滤条件 |
| filters.doc_type | string[] | 否 | 文档类型 |
| filters.state | string[] | 否 | 州/地区 |
| filters.document_ids | int[] | 否 | 指定文档 ID，与其它 filter 互斥优先 |
| filters.limit | int | 否 | 最多处理文档数，默认 500 |
| async_mode | bool | 否 | 默认 false，true 时走 Celery |

**响应**（同步）：

```json
{
  "status": "ok",
  "data": {
    "task_id": null,
    "async": false,
    "status": "finished",
    "result": {
      "documents_scanned": 120,
      "urls_extracted": 45,
      "urls_new": 32,
      "urls_duplicate": 13,
      "scope": "project"
    }
  },
  "error": null,
  "meta": {}
}
```

**响应**（异步）：`task_id` 非空，`async: true`，`status: "queued"`，`result: null`。

---

#### GET `/api/v1/resource_pool/urls`

分页查询资源池中的 URL 列表。

**Query**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| project_key | string | 是 | 项目标识 |
| scope | "shared" \| "project" \| "effective" | 否 | 默认 `effective` |
| page | int | 否 | 默认 1 |
| page_size | int | 否 | 默认 20，最大 100 |
| source | "document" \| "task" | 否 | 来源过滤 |
| domain | string | 否 | 域名过滤（模糊） |

**响应**：

```json
{
  "status": "ok",
  "data": {
    "items": [
      {
        "id": 1,
        "url": "https://example.com/article",
        "domain": "example.com",
        "source": "document",
        "source_ref": {"document_id": 42},
        "scope": "project",
        "created_at": "2026-02-26T10:00:00Z"
      }
    ]
  },
  "error": null,
  "meta": {
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total": 156,
      "total_pages": 8
    }
  }
}
```

---

### 5.3 入口二：任务中自动捕获 URL

#### POST `/api/v1/resource_pool/capture/enable`

启用指定任务类型的 URL 自动捕获。

**请求体**：

```json
{
  "project_key": "online_lottery",
  "scope": "project",
  "job_types": ["ingest_policy", "calottery_news", "discovery_search", "market_info"],
  "enabled": true
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| project_key | string | 是 | 项目标识 |
| scope | "project" \| "shared" | 否 | 默认 `project` |
| job_types | string[] | 是 | 要启用的任务类型，需与 EtlJobRun.job_type 一致。示例：`ingest_policy`、`calottery_news`、`calottery_retailer_news`、`discovery_search`、`market_info`、`google_news` 等 |
| enabled | bool | 否 | 默认 true |

**说明**：此为配置接口，实际捕获逻辑在服务层/适配器层通过 hook 或中间件实现，不在此接口内执行抓取。

---

#### POST `/api/v1/resource_pool/capture/from-tasks`

从已完成任务的历史记录中回溯提取 URL（一次性补采）。

**请求体**：

```json
{
  "project_key": "online_lottery",
  "scope": "project",
  "task_ids": ["celery-task-uuid-1", "celery-task-uuid-2"],
  "job_type": "discovery_store",
  "since": "2026-02-01T00:00:00Z",
  "limit": 100,
  "async_mode": false
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| project_key | string | 是 | 项目标识 |
| scope | "project" \| "shared" | 否 | 默认 `project` |
| task_ids | string[] | 否 | 指定 Celery task_id |
| job_type | string | 否 | 按 job_type 过滤 EtlJobRun |
| since | datetime | 否 | 任务开始时间下限 |
| limit | int | 否 | 最多处理任务数，默认 100 |
| async_mode | bool | 否 | 默认 false |

**响应**：与 `from-documents` 类似，`result` 含 `tasks_scanned`、`urls_extracted`、`urls_new`、`urls_duplicate`。

---

### 5.4 爬取机制适配

爬取机制适配不单独暴露 HTTP 接口，而是：

1. **适配器层**：在 `discovery/store.py`、ingest adapters 等抓取流程中，将遇到的 URL 通过统一 Port 写入资源池
2. **配置驱动**：由 `resource_pool/capture/enable` 的配置决定是否写入、写入 `project` 还是 `shared`
3. **去重**：资源池表按 `(url, scope)` 或 `(url, project_key)` 去重

具体实现落在 `app/services/resource_pool/` 服务层，API 仅负责配置与查询。

---

## 6. 数据模型（概要）

资源池 URL 存储需新增表，建议：

- **项目级**：`project_{key}.resource_pool_urls`（与 documents 同 schema）
- **总库**：`public.resource_pool_urls`（shared  scope）

字段建议：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| url | text | 规范化后的 URL |
| domain | varchar(255) | 域名，便于过滤 |
| source | varchar(32) | "document" \| "task" |
| source_ref | jsonb | 如 document_id、task_id、job_type |
| scope | varchar(16) | "project" \| "shared" |
| project_key | varchar(64) | 仅 project scope 时有值 |
| created_at | timestamptz | 创建时间 |

唯一约束：`(url, scope)` 或 `(url, project_key)` 视最终 schema 设计而定。

---

## 7. 错误码

遵循 `API_CONTRACT_STANDARD.md`：

| 错误码 | HTTP | 场景 |
|--------|------|------|
| INVALID_INPUT | 400 | 参数校验失败 |
| NOT_FOUND | 404 | 指定 document_id/task_id 不存在 |
| RATE_LIMITED | 429 | 提取/捕获频率超限 |

---

## 8. 实现顺序建议

1. **Phase 1**：文档提取入口 + 资源池 URL 表 + 列表查询接口
2. **Phase 2**：任务捕获配置接口 + 从历史任务回溯提取
3. **Phase 3**：在 ingest/discovery 流程中接入自动捕获 hook

---

## 9. 与现有模块关系

| 模块 | 关系（均贯穿总库/子项目库） |
|------|---------------------------|
| project_customization | `get_news_resource_handlers(scope)` 或 `get_shared_news_resource_handlers()` + `get_news_resource_handlers()` 分别定义总库/子项目库采集源；执行时产生的 URL 按 scope 写入对应库 |
| ingest | 摄取流程中的 URL 通过 hook 写入资源池，写入 scope 由 capture 配置决定 |
| source_library | 复用 scope（shared/project/effective）；channel/item 均区分总库与子项目库 |
| discovery/store | store 落库时的 link 可同步写入资源池，scope 由配置决定 |
| projects | 依赖 project_key、bind_project 做租户隔离；总库用 bind_schema("public") |

---

## 10. 采集资源池接口补充（建议）

当前 News resource pool 已通过 `get_news_resource_handlers()` 实现（目前仅子项目库），建议：

1. **扩展接口支持总库**：`get_shared_news_resource_handlers()` 或 `get_news_resource_handlers(scope="shared"|"project"|"effective")`，与 source_library 模式一致

2. **新增 GET `/api/v1/ingest/news-resources`**

- Query: `project_key`（必填）、`scope`（`shared`|`project`|`effective`，默认 `effective`）
- 响应: `{"items": [{"resource_id": "calottery", "name": "CA Lottery News", "scope": "project"}, ...], "scope": "effective"}`
- 实现：`scope=effective` 时合并总库 + 子项目库（子项目同 key 覆盖总库）

便于前端动态发现当前项目支持的新闻采集源，且贯穿总库/子项目库二分。
