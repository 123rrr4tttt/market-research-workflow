# 搜索链与来源库挂载路径系统调查报告（2026-03-14）

## 1. 调查目标

本报告用于确认当前仓库内“搜索链 + 来源库搜索链”在代码层的真实挂载关系，避免继续以历史文档口径推进实现。

调查范围：

1. API 主入口与路由挂载。
2. 来源库运行主链（同步与异步）。
3. 通用搜索链（market）与来源库链的交点。
4. 前端调用路径、agent-batch 调度路径、skill runtime 路径。
5. 与现有开发文档中的潜在不一致项。

## 2. 方法与证据口径

本次为仓内静态与链路核查（不改业务代码），证据仅引用当前代码文件与行号。

关键证据来源：

1. `main/backend/app/main.py`
2. `main/backend/app/api/*.py`
3. `main/backend/app/services/collect_runtime/*`
4. `main/backend/app/services/source_library/*`
5. `main/backend/app/services/resource_pool/unified_search.py`
6. `main/backend/app/services/skill_runtime.py`
7. `main/frontend-modern/src/lib/api/*` 与 `pages/*`

## 3. 总体结论

当前系统已形成“单主入口 + 多调度入口”的结构：

1. 对用户侧来源库运行，主入口是 `POST /api/v1/ingest/source-library/run`。
2. 对批量与自动化任务，`/api/v1/agent-batch/jobs` 与 `skill_runtime` 形成异步并行入口。
3. `resource_pool/unified-search` 目前是能力接口，不是前端默认主运行入口。
4. 来源库三车道（`protocol_search/provider_harvest/site_search/url_execution`）已落在 `ItemResolver + run_item_payload`。

## 4. 实际挂载路径（后端）

### 4.1 API 主挂载

1. 主路由挂载：`app.include_router(api_router, prefix="/api/v1")`。
2. 说明：所有后端业务入口均在 `/api/v1/*` 下统一暴露。

证据：

- `main/backend/app/main.py:497`

### 4.2 搜索链（market）

链路：

1. `POST /api/v1/ingest/market`
2. `ingest_market`
3. `collect_request_from_market_api`（`channel="search.market"`）
4. `run_collect`
5. `SearchMarketAdapter.run`
6. `collect_market_info`

关键证据：

- `main/backend/app/api/ingest.py:352`
- `main/backend/app/services/collect_runtime/runtime.py:300`
- `main/backend/app/services/collect_runtime/adapters/search_market.py:8`

### 4.3 来源库主链（同步模式）

链路：

1. `POST /api/v1/ingest/source-library/run`
2. `_run_single_source_library_entry`
3. `run_source_library_item_compat`
4. `run_collect`
5. `SourceLibraryAdapter.run`
6. `run_item_payload`
7. `ItemResolver.resolve`（确定 `source_mode`）
8. `*_orchestrator`
9. `run_channel`
10. `handler_registry` 对应 adapter

关键证据：

- `main/backend/app/api/ingest.py:712`
- `main/backend/app/services/collect_runtime/runtime.py:378`
- `main/backend/app/services/collect_runtime/adapters/source_library.py:102`
- `main/backend/app/services/source_library/resolver.py:1618`
- `main/backend/app/services/source_library/item_resolver.py:68`
- `main/backend/app/services/source_library/runner.py:270`

### 4.4 来源库异步链（agent-batch/skill）

链路：

1. `POST /api/v1/agent-batch/jobs` 或 `nl-command/direct`
2. `_submit_batch_item`（`channel=source_library`）
3. `_submit_source_item`
4. `invoke_skill("agent_batch.dispatch.source_library_item")`
5. `_skill_dispatch_source_library_item`
6. `task_run_source_library_item`
7. 回落到来源库主链执行（同 4.3）

关键证据：

- `main/backend/app/api/agent_batch.py:628`
- `main/backend/app/api/agent_batch.py:434`
- `main/backend/app/api/agent_batch.py:504`
- `main/backend/app/services/skill_runtime.py:343`
- `main/backend/app/services/tasks.py:566`

### 4.5 车道分流与站点搜索收敛现状

`ItemResolver` 分流规则：

1. 有 `candidate_urls` 优先 `url_execution`。
2. handler cluster 或 `site_entries` 走 `site_search`。
3. `provider_type in {scrapy,crawlee,meltano}` 走 `provider_harvest`。
4. 其他默认 `protocol_search`。

关键证据：

- `main/backend/app/services/source_library/item_resolver.py:68`

`site_search` 目前落实为：

1. `handler.cluster`
2. 调 `unified_search_by_item_payload`
3. 合并候选 URL
4. 再进 URL 路由执行

关键证据：

- `main/backend/app/services/source_library/resolver.py:1329`

## 5. 实际挂载路径（前端与调度）

### 5.1 前端默认调用路径

来源库运行：

1. 页面触发 `runSourceLibrary`
2. domain 调用 `endpoints.ingest.sourceLibraryRun`
3. 命中 `/api/v1/ingest/source-library/run`

关键证据：

- `main/frontend-modern/src/lib/api/domains/resource-source.ts:247`
- `main/frontend-modern/src/lib/api/endpoints.ts:103`

### 5.2 agent-batch 调度路径

1. 前端批量提交命中 `/api/v1/agent-batch/jobs`
2. 后端对 `source_library` 默认分配 `lane=subagent`
3. queue 由 `settings.agent_batch_lane_subagent_queue` 决定

关键证据：

- `main/frontend-modern/src/lib/api/endpoints.ts:76`
- `main/backend/app/api/agent_batch.py:382`
- `main/backend/app/api/agent_batch.py:390`

### 5.3 project_key 注入行为

前端拦截器会给 `/api/*` 自动追加 `project_key` query 与 `X-Project-Key` header。

关键证据：

- `main/frontend-modern/src/lib/api/client.ts:73`

## 6. 与现有文档口径的偏差

### 6.1 历史运行入口偏差

仍有历史文档提及 `/source_library/items/{item_key}/run`；当前代码主运行入口是 `/ingest/source-library/run`，`source_library` 模块主要是元数据管理与 refresh/sync。

证据：

- `main/backend/app/api/ingest.py:712`
- `main/backend/app/api/source_library.py:537`
- `docs/reference-pool/platformization/chains/04_crawler_source_platformization.md:40`

### 6.2 “挂载路径字段”缺失

当前开发计划文档虽有 API/链路描述，但尚未形成统一“挂载路径章节模板”（如：主入口、调度入口、旁路入口、禁用入口、迁移状态）。

## 7. 风险分级（当前）

### 7.1 P1：双入口与旁路风险

1. `ingest/source-library/run`（同步）与 `agent-batch`（异步）并存。
2. `process retry` 可直接走 `agent_batch.dispatch.source_library_item`，绕开 jobs 主入口策略面。

证据：

- `main/backend/app/api/ingest.py:702`
- `main/backend/app/api/agent_batch.py:504`
- `main/backend/app/api/process.py:727`

### 7.2 P1：默认回落风险

`run_collect` 的 adapter workflow 受配置影响，错误配置会让路径回到 legacy 行为，导致“设计已升级、运行仍旧链”的偏差。

证据：

- `main/backend/app/services/collect_runtime/runtime.py:61`

### 7.3 P2：语义漂移风险

`source_mode` 同时受自动推断与显式 override 影响，若调用方缺少约束，运行车道可能与产品预期不一致。

证据：

- `main/backend/app/services/source_library/item_resolver.py:76`
- `main/backend/app/services/source_library/resolver.py:1669`

### 7.4 P2：URL 路由默认回落

`url_router` 默认 `_DEFAULT_CHANNEL = "url_pool"`，在路由规则缺失时会把未命中流量回落到 url_pool 执行语义。

证据：

- `main/backend/app/services/source_library/url_router.py:9`

### 7.5 P3：文档契约老化

`API接口文档` 与代码参数模型存在偏差，容易造成联调误判。

证据：

- `main/backend/API接口文档.md:163`
- `main/backend/app/api/ingest.py:285`

## 8. 建议的“挂载路径标准章节”（用于后续所有计划文档）

建议新增固定章节：`Mount Path Contract`，至少包含：

1. 主入口（authoritative）
2. 调度入口（async orchestration）
3. 能力入口（capability endpoint）
4. 旁路入口（bypass path）
5. 禁用/废弃入口（deprecated path）
6. 入口优先级（resolve order）
7. 版本与回滚策略

## 9. 最小改造清单（不改业务逻辑，先稳边界）

1. 为 `source_library` 体系增加统一“入口优先级声明”文档字段。
2. 在 `agent-batch/process-retry/ingest-sync` 三条入口加入一致的 `entrypoint` 标记写入日志与任务元数据。
3. 对 `url_router` 默认回落增加显式告警（unknown route -> fallback）。
4. 将 `docs/reference-pool/...` 历史运行入口说明更新为当前主入口。

## 10. 本次调查产出

1. 完整核对了后端、前端、调度三类挂载路径。
2. 明确了当前 authoritative path：`/api/v1/ingest/source-library/run`。
3. 明确了并行入口与旁路入口的风险边界。
4. 给出了可直接落地的文档与治理改造最小集。
