# URL 资源池：提取与捕获接口

请求字段与完整响应见[路由定义](../app/api/resource_pool.py)和运行服务的 OpenAPI。路由存在不表示每种执行配置均允许写入；实际准入见[路由效果绑定](../app/composition/production_route_bindings.json)。下文示例使用项目 `demo_proj`；请替换为实际项目键。

## 1. 总库/子项目库贯穿原则

**所有资源池相关行为必须贯穿总库/子项目库二分**：

| 维度 | 总库 (shared) | 子项目库 (project) |
|------|---------------|---------------------|
| 存储位置 | `public` schema | 项目 schema |
| 可见性 | 跨项目共享 | 仅当前项目 |
| scope 取值 | `shared` | `project` |
| 合并视图 | `effective` = shared ∪ project（project 覆盖 shared 同 key） |

- 写操作接受 `scope: "shared" | "project"`，缺省 `project`。
- URL 列表支持 `shared | project | effective`，缺省 `effective`。

## 2. 概念区分

项目中存在两类「资源池」概念，均遵循总库/子项目库二分：

| 概念 | 已实现位置 | 职责 |
|------|------------|------|
| **News resource pool**（采集资源池） | `project_customization.get_news_resource_handlers()` | `resource_id` → 采集 handler。总库：通用源（如 google_news）；子项目库：项目专有源（如 calottery） |
| **Resource pool extraction**（URL 资源池） | 本文档 | 从材料、任务中提取 URL 并持久化。总库/子项目库分别存储 |

本文档描述的是 **URL 资源池提取**，与采集资源池互补：采集 handler 执行时产生的 URL 可被本模块捕获入库。

## 3. 模块定位

资源池提取模块（Resource Pool Extraction）负责从多种来源收集 URL，形成可复用的 URL 资源池，**贯穿总库/子项目库**：

- **子项目库**：按 `project_key` 隔离，数据落在项目 schema
- **总库**：跨项目共享，数据落在 `public` schema（与 source_library 的 shared 模式一致）

## 4. 两个入口

| 入口 | 说明 | 数据来源 |
|------|------|----------|
| **材料提取** | 从已有 `Material` 的 `uri`、`content`、`extracted_data` 中提取 URL | `materials` 表 |
| **任务捕获** | 正在进行的任务（ingest/discovery/source_library）中自动捕获 URL + 爬取机制适配 | EtlJobRun、store、adapter 等 |

## 5. 接口模式

### 5.1 路由前缀与租户

- **前缀**：`/api/v1/resource_pool`
- **项目作用域**：提取和捕获写入需要项目上下文，可从请求体 `project_key` 或路由识别的 `X-Project-Key` / `project_key` 查询参数提供。即使写入总库，提取仍从所选项目读取材料或任务。
- **Scope**：`scope: shared | project | effective`，与 source_library 一致

### 5.2 入口一：从材料提取 URL

#### POST `/api/v1/resource_pool/extract/from-materials`

从已有材料中提取 URL 并写入资源池。

**请求体**：

```json
{
  "project_key": "demo_proj",
  "scope": "project",
  "filters": {
    "material_type": ["policy", "market"],
    "state": ["CA"],
    "material_ids": [1, 2, 3],
    "limit": 500
  },
  "async_mode": false
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| project_key | string | 见作用域 | `shared` 列表无需选择项目；提取、捕获和项目列表需要项目上下文 |
| scope | "project" \| "shared" | 否 | 默认 `project`。`shared` 写入总库 |
| filters | object | 否 | 材料过滤条件 |
| filters.material_type | string[] | 否 | 材料类型 |
| filters.state | string[] | 否 | 州/地区 |
| filters.material_ids | int[] | 否 | 非空时按材料 ID 筛选，不再应用材料类型和地区过滤 |
| filters.limit | int | 否 | 最多扫描的材料数，范围 1–5000，默认 500 |
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
      "materials_scanned": 3,
      "urls_extracted": 45,
      "urls_new": 32,
      "urls_duplicate": 13,
      "scope": "project"
    }
  },
  "error": null,
  "meta": {"trace_id": null, "pagination": null, "project_key": "demo_proj", "deprecated": null}
}
```

**响应**（异步）：`task_id` 非空，`async: true`，`status: "queued"`，`result: null`。

---

#### GET `/api/v1/resource_pool/urls`

分页查询资源池中的 URL 列表。

**Query**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| project_key | string | 见作用域 | `shared` 列表无需选择项目；提取、捕获和项目列表需要项目上下文 |
| scope | "shared" \| "project" \| "effective" | 否 | 默认 `effective` |
| page | int | 否 | 默认 1 |
| page_size | int | 否 | 默认 20，最大 100 |
| source | string | 否 | 来源值精确过滤，如 `material` 或 `task` |
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
        "source": "material",
        "source_ref": {"material_id": 42},
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
  "project_key": "demo_proj",
  "scope": "project",
  "job_types": ["google_news"],
  "enabled": true
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| project_key | string | 见作用域 | `shared` 列表无需选择项目；提取、捕获和项目列表需要项目上下文 |
| scope | "project" \| "shared" | 否 | 默认 `project` |
| job_types | string[] | 是 | 非空列表；配置值须匹配对应生产者传给捕获适配器的任务类型 |
| enabled | bool | 否 | 默认 true |

**说明**：此为配置接口，实际捕获逻辑在服务层/适配器层通过 hook 或中间件实现，不在此接口内执行抓取。

---

#### POST `/api/v1/resource_pool/capture/from-tasks`

从已完成任务的记录中提取 URL（不抓取网页）。

**请求体**：

```json
{
  "project_key": "demo_proj",
  "scope": "project",
  "task_ids": [101, 102],
  "job_type": "google_news",
  "since": "2026-02-01T00:00:00Z",
  "limit": 100,
  "async_mode": false
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| project_key | string | 见作用域 | `shared` 列表无需选择项目；提取、捕获和项目列表需要项目上下文 |
| scope | "project" \| "shared" | 否 | 默认 `project` |
| task_ids | int[] | 否 | 已完成记录的持久 `EtlJobRun.id`，不是 Celery 任务标识 |
| job_type | string | 否 | 按 job_type 过滤 EtlJobRun |
| since | string | 否 | 任务开始时间下限；无法解析时忽略该筛选并返回 `warning` |
| limit | int | 否 | 最多扫描的任务数，范围 1–500，默认 100 |
| async_mode | bool | 否 | 默认 false |

**响应**：与 `from-materials` 使用相同的任务响应结构。同步 `result` 含 `tasks_scanned`、`urls_extracted`、`urls_new`、`urls_duplicate`、`scope` 和 `dedupe_hit_reason`。未匹配记录时返回零扫描数，而不是逐条报 404。

---

### 5.4 爬取机制适配

爬取机制适配不单独暴露 HTTP 接口，而是：

1. **适配器层**：在 `discovery/store.py`、ingest adapters 等抓取流程中，将遇到的 URL 通过统一 Port 写入资源池
2. **配置驱动**：由 `resource_pool/capture/enable` 的配置决定是否写入、写入 `project` 还是 `shared`
3. **去重**：项目表和总库表各自按 `url` 唯一，合并列表优先使用项目中的同 URL 条目。

提取与捕获由[资源池服务](../app/services/resource_pool)执行。

---

## 6. 数据模型（概要）

当前存储见[实体定义](../app/models/entities.py)：

- **项目级**：项目 schema 内的 `resource_pool_urls`（与 `materials` 同 schema）。
- **总库**：`public.shared_resource_pool_urls`。

主要字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| url | text | 规范化后的 URL |
| domain | varchar(255) | 域名，便于过滤 |
| source | varchar(32) | 生产者提供的来源值，如 `material`、`task` |
| source_ref | jsonb | 如 `material_id`、`task_id`、`job_type` |
| project_key | varchar(64) | 仅 project scope 时有值 |
| created_at | timestamptz | 创建时间 |

`scope` 是列表按存储位置导出的字段，不是 URL 表的列。

---

## 7. 错误码

遵循 [API 合同](API_CONTRACT_STANDARD.md)：

| 错误码 | HTTP | 场景 |
|--------|------|------|
| INVALID_INPUT | 400/422 | 业务输入或请求字段校验失败 |
| PROJECT_KEY_REQUIRED | 400 | 提取或捕获缺少可用项目上下文 |

---

## 8. 与其他模块的关系

| 模块 | 关系（均贯穿总库/子项目库） |
|------|---------------------------|
| project_customization | `get_shared_news_resource_handlers()` 和 `get_news_resource_handlers()` 分别提供共享与项目采集处理器；有捕获接线时按捕获配置写入 URL 池 |
| ingest | 摄取流程中的 URL 通过 hook 写入资源池，写入 scope 由 capture 配置决定 |
| source_library | 复用 scope（shared/project/effective）；channel/item 均区分总库与子项目库 |
| discovery/store | store 落库时的 link 可同步写入资源池，scope 由配置决定 |
| projects | 依赖 project_key、bind_project 做租户隔离；总库用 bind_schema("public") |

---

## 9. 查询采集资源

`GET /api/v1/ingest/news-resources` 列出可由当前项目使用的新闻采集处理器；它不查询 URL 池。

- Query: `project_key`（必填）、`scope`（`shared`|`project`|`effective`，默认 `effective`）
- 响应：标准 Envelope 的 `data` 含 `items` 和 `scope`；每个条目提供 `resource_id`、`name` 和 `scope`。
- 实现：`scope=effective` 时合并总库 + 子项目库（子项目同 key 覆盖总库）

便于前端动态发现当前项目支持的新闻采集源，且贯穿总库/子项目库二分。
