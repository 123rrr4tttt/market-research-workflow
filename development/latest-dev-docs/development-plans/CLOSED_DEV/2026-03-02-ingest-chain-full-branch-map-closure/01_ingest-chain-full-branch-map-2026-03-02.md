# 信息采集全链路现状与分支地图（2026-03-02）

## 0. 目标与范围

本文基于并行多 Agent 调研，梳理当前“从前端输入任务参数到最终文档可见”的完整后端链路现状，覆盖：

- 前端入口（Ingest / Graph / Ops）
- API 路由层（ingest / discovery / resource_pool / process / admin）
- 运行时编排层（collect_runtime / source_library）
- 资源池检索与候选过滤层（resource_pool.unified_search）
- URL 采集执行层（single_url + crawler_pool fallback）
- 质量闸门与入库层（policy/content gate、去重、job logger）
- 文档可见性层（admin documents list/detail + project schema）

结论先行：

1. `search_template` 最新链条**已集成到采集系统**，并可由 `source-library/run` 触发。  
2. 当前存在“同名能力多执行路径”的现状：
   - `source-library/run` 同步路径可走 legacy `run_item_by_key`；
   - `collect_runtime` 路径对 `handler.cluster` 有专门 batched unified-search 逻辑。  
3. `search_template` 批次出现 `candidates=0` 的主因不是“未集成”，而是前置候选过滤过严（默认 `allow_term_fallback=false` 于 handler-cluster 调用场景）+ 某些站点被反爬阻断。

平台化约束（本轮）：

4. 平台化语义上仅保留 `single_url` 为唯一入库工作流；其他链路作为候选生产与调度层，最终写入决策统一回流 `single_url`。

---

## 1. 全局总图（从入口到可见）

```mermaid
flowchart TD
  A[Frontend Entry\nIngestPage / GraphPage / OpsPage] --> B[API Endpoints]
  B --> C[Collect Runtime / Direct Service]
  C --> D[Search / Source Library / Unified Search]
  D --> E[URL Execution\nsingle_url / crawler_pool fallback]
  E --> F[Quality Gates\nurl policy / page type / content quality / strict mode]
  F --> G[Persistence\nDocument + EtlJobRun.params]
  G --> H[Process APIs\n/history /{task_id} /logs]
  G --> I[Admin APIs\n/documents/list /documents/{id}]
  I --> J[Ops UI visibility\n(project_key/schema scoped)]
```

---

## 2. 前端入口层（当前真实调用路径）

## 2.1 IngestPage

- 历史：`listIngestHistory` -> `GET /api/v1/ingest/history` -> `app/api/ingest.py:356`
- 关键词建议：`generateKeywords` -> `POST /api/v1/discovery/generate-keywords` -> `app/api/discovery.py:224`
- 来源库同步：`syncSourceLibrary` -> `POST /api/v1/ingest/source-library/sync` -> `app/api/ingest.py:541`
- 来源项执行：`runSourceLibrary` -> `POST /api/v1/ingest/source-library/run` -> `app/api/ingest.py:494`
  - async: `task_run_source_library_item.delay`
  - sync: `run_source_library_item_compat`
- 市场采集：`ingestMarket` -> `POST /api/v1/ingest/market` -> `app/api/ingest.py:261`
- 其他（policy/social/commodity/ecom）均为 ingest API 下入口
- 新增前端 API 客户端能力：`ingestSingleUrl(payload)`（`main/frontend-modern/src/lib/api.ts`），支持将 single-url 搜索展开参数从前端外部输入到后端。

关键文件：
- `main/frontend-modern/src/pages/IngestPage.tsx`
- `main/frontend-modern/src/lib/api.ts`
- `main/frontend-modern/src/lib/api/endpoints.ts`

## 2.2 GraphPage

- 图查询：`/admin/policy-graph`、`/admin/content-graph`、`/admin/market-graph`
- 结构化任务提交：`POST /api/v1/ingest/graph/structured-search`（`app/api/ingest.py:1197`）
  - `flow_type=collect`: 走 policy/social/market collect
  - `flow_type=source_collect`: 走 source-library 兼容执行（可异步）

## 2.3 OpsPage

- 文档列表：`POST /api/v1/admin/documents/list`（不是 `GET /admin/documents`）
- 文档详情：`GET /api/v1/admin/documents/{doc_id}`

关键文件：
- `main/frontend-modern/src/pages/OpsPage.tsx`
- `main/backend/app/api/admin.py:737,887`

---

## 3. API 路由与执行模式矩阵

| 能力 | API | 同步/异步 | 任务日志落点 |
|---|---|---|---|
| 单 URL 采集 | `/api/v1/ingest/url/single` | 支持 sync/async | async 有 task_id；sync 写 DB job（pseudo）；支持 `search_expand/search_expand_limit/search_provider/search_fallback_provider/fallback_on_insufficient/target_candidates/min_results_required/decode_redirect_wrappers/filter_low_value_candidates` |
| 来源项执行 | `/api/v1/ingest/source-library/run` | 支持 sync/async | async 有 Celery task；sync 也写 source_library_run job |
| 资源池统一搜索 | `/api/v1/resource_pool/unified-search` | sync | 无 Celery task_id，返回即时结果 |
| 市场采集 | `/api/v1/ingest/market` | 支持 sync/async | `market_info` job |
| 发现搜索 | `/api/v1/discovery/search` | sync | `discovery_search` job |
| 文档列表 | `/api/v1/admin/documents/list` | sync | 查询接口 |
| 文档详情 | `/api/v1/admin/documents/{id}` | sync | 查询接口 |
| 任务历史 | `/api/v1/process/history` | sync | 从 `EtlJobRun` 聚合 |
| 任务日志 | `/api/v1/process/{task_id}/logs` | sync | Celery worker log + DB pseudo summary |

---

## 4. Source Library + Collect Runtime 分支图

```mermaid
flowchart TD
  A[/ingest/source-library/run] --> B{async_mode?}
  B -->|true| C[task_run_source_library_item]
  C --> D[run_source_library_item_compat]
  B -->|false| D

  D --> E[run_collect(channel=source_library)]
  E --> F[SourceLibraryAdapter.run]
  F --> G{is_handler_cluster_item?}

  G -->|yes| H[batched unified_search_by_item_payload]
  H --> I[merge site_entries/candidates/errors]
  I --> J[written + ingest_result counters]

  G -->|no| K[run_item_by_key legacy adapter path]
```

判定点（`main/backend/app/services/collect_runtime/adapters/source_library.py`）：

- `is_handler_cluster_item`：
  - `item.extra.stable_handler_cluster = true` 或
  - `item.extra.creation_handler` 以 `handler.entry_type` 开头
- query terms 取值优先级：`query_terms -> keywords -> search_keywords -> base_keywords -> topic_keywords`
- 默认分批：`keyword_batch_size` 缺省为 `4`

关键默认值（仅 handler-cluster 分支）：

- `write_to_pool = bool(override_params.get("write_to_pool", True))`
- `auto_ingest = bool(override_params.get("auto_ingest", True))`
- `allow_term_fallback = bool(override_params.get("allow_term_fallback", False))`  
  这是 `search_template candidates=0` 高频触发点。

---

## 5. `resource_pool.unified_search` 分支图（search_template 核心）

```mermaid
flowchart TD
  A[unified_search_by_item_payload] --> B[resolve item.params.site_entries]
  B --> C{entry_type}
  C -->|rss| D[fetch rss + extract links]
  C -->|sitemap| E[collect sitemap locs]
  C -->|search_template| F[template must contain {{q}} -> fetch result page -> extract links]

  D --> G[_filter_urls_by_terms_with_fallback]
  E --> G
  F --> G

  G --> H[domain check for sitemap/search_template]
  H --> I[dedup + max_candidates]
  I --> J[drop low-value candidate urls]

  J --> K{write_to_pool && candidates?}
  K -->|yes| L[append_url to resource_pool_urls]
  K -->|no| M[skip write]

  L --> N{auto_ingest && (written or candidates)}
  M --> N
  N -->|yes| O[collect_urls_from_pool]
  N -->|no| P[finish]
```

`candidates=0` 典型原因：

1. `expected_entry_type` 不匹配被过滤
2. 站点返回页面可抽取链接为空
3. `allow_term_fallback=false` 且 URL 不含 query 词，严格过滤后空
4. `sitemap/search_template` 域名一致性过滤后空
5. 低价值候选过滤后空
6. 部分源被反爬阻断（例如 `reddit search` 403）

关键文件：
- `main/backend/app/services/resource_pool/unified_search.py`

---

## 6. `single_url` 执行与 crawler_pool 兜底分配

## 6.1 分配逻辑

`single_url` 主路径：

1. URL 能力画像：`entry_type/render_mode/anti_bot_risk`
2. 先规划 `planned_handler`（多数仍是 `native_http`）
3. 拉取 HTML 与解析
4. 关键条件下尝试 `_try_crawler_pool`
5. 质量闸门通过才写入

关键点：

- 普通 `detail` 页默认不触发 crawler_pool（除非 `anti_bot_risk=high` 或强制域名）
- `search_template` 当结果不足时会触发 crawler_pool fallback
- fetch 失败也会尝试 crawler_pool（前提满足条件）
- `search_template` 支持可配置 search fan-out：当候选满足阈值时可展开抓取 top-N 结果 URL（`search_expand=true`）
- `search_template` 支持可配置搜索兜底：结果不足时可切换 `search_fallback_provider=ddg_html`

关键文件：
- `main/backend/app/services/ingest/single_url.py`

## 6.2 质量闸门（入库前）

主要 gate：

1. URL policy gate（预抓取拦截）
2. search_template results insufficient gate
3. 低价值页 gate（nav/list/home/search shell）
4. content quality gate（正文质量）
5. strict_mode gate（分数阈值）

未通过 gate 时：

- `inserted_valid=0`
- `rejected_count` 增加
- `rejection_breakdown` 记录原因
- 任务状态常为 `degraded_success` 或 `failed`

---

## 7. 持久化与可见性链路

## 7.1 Document 写入点

- `ingest_single_url`
- `ingest/raw_import`
- `discovery/store`
- `news/social/policy` 等部分入口

去重策略：URI / text_hash（不同入口略有差异）。

## 7.2 Job 指标回传链

- 各服务把 `result` 写给 `complete_job`
- `job_logger.complete_job` 合并到 `EtlJobRun.params`
- `process` API `_extract_quality_fields` 读取：
  - `inserted_valid`
  - `rejected_count`
  - `rejection_breakdown`

关键文件：
- `main/backend/app/services/job_logger.py`
- `main/backend/app/api/process.py`

## 7.3 文档可见性（为什么“看不到”）

高优先根因：

1. `project_key/schema` 不一致（最常见）
2. 去重命中（任务成功但 `inserted=0 skipped=1`）
3. 写入并非 `Document` 通道（如 market/ecom 某些数据）
4. 列表过滤条件导致 0 条
5. 误把 task id 当 doc id

关键机制：

- 前端通过 axios 拦截器注入 `X-Project-Key` + `?project_key=`
- 后端中间件 `bind_project` 后通过 `search_path` 隔离 schema

关键文件：
- `main/frontend-modern/src/lib/api/client.ts`
- `main/backend/app/main.py`
- `main/backend/app/models/base.py`
- `main/backend/app/api/admin.py`

---

## 8. “search template 是否集成到采集”现状判定

判定：**已集成，但存在分支默认值导致的“看似未生效”现象**。

证据链：

1. `source-library/run` -> `collect_runtime SourceLibraryAdapter`
2. handler-cluster 条目进入 `unified_search_by_item_payload`
3. `write_to_pool/auto_ingest` 默认打开（handler-cluster 路径）
4. 但 `allow_term_fallback` 默认关闭，导致 query-URL strict filter 易把 candidates 清空

因此：

- 不是“链路没接上”
- 是“链路接上但默认分支选择偏严格，在某些关键词/站点组合下产出为 0”

---

## 9. 当前链路分支清单（便于排障）

## 9.1 入口分支

- `ingest/market`
- `discovery/search`
- `ingest/source-library/run`
- `resource_pool/unified-search`
- `ingest/url/single`

## 9.2 source-library/run 分支

- `async_mode=true`（Celery）
- `async_mode=false`（同步）
- `is_handler_cluster_item=true`（batched unified-search）
- `is_handler_cluster_item=false`（legacy run_item_by_key）

## 9.3 unified_search 分支

- `entry_type`：rss / sitemap / search_template
- `allow_term_fallback`: false / true
- `write_to_pool`: false / true
- `auto_ingest`: false / true
- `expected_entry_type` mismatch / match

## 9.4 single_url 分支

- native fetch success / fail
- `entry_type=search_template` result_count >= `min_results_required` / < `min_results_required`
- search fallback off / on（例如 `ddg_html`）
- search expand off / on（top-N fan-out）
- crawler_pool fallback success / no output / low-quality output / dispatch failed
- gate pass / gate reject

## 9.5 可见性分支

- correct project schema / wrong project schema
- dedup skip / inserted
- admin list filters matched / filtered out

---

## 10. 代码索引（核心）

- `main/frontend-modern/src/pages/IngestPage.tsx`
- `main/frontend-modern/src/pages/GraphPage.tsx`
- `main/frontend-modern/src/pages/OpsPage.tsx`
- `main/frontend-modern/src/lib/api.ts`
- `main/frontend-modern/src/lib/api/client.ts`
- `main/backend/app/api/ingest.py`
- `main/backend/app/api/discovery.py`
- `main/backend/app/api/resource_pool.py`
- `main/backend/app/api/process.py`
- `main/backend/app/api/admin.py`
- `main/backend/app/services/collect_runtime/runtime.py`
- `main/backend/app/services/collect_runtime/adapters/source_library.py`
- `main/backend/app/services/resource_pool/unified_search.py`
- `main/backend/app/services/ingest/single_url.py`
- `main/backend/app/services/job_logger.py`
- `main/backend/app/main.py`
- `main/backend/app/models/base.py`

