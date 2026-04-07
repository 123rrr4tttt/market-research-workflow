# 来源库三分入口与后端服务映射（2026-03-11）

## 1. 背景与目标

当前来源库在运行时具备多种能力，但入口语义与执行分支交织，导致 `url_pool` 与站点搜索能力边界不清。  
本方案将来源库统一为三类入口，并引入“`items` 纯抽象集合”模型，降低冗余与维护复杂度。

目标三分：

1. 特定来源搜索（API/协议型）：如 Reddit、Google News。
2. 特定来源采集（固定刷新信息提供商）：如 crawler provider 驱动的固定源。
3. 站点搜索（通用站点搜索）：如 arXiv/通用站点的 search template / RSS / sitemap。

## 2. 现状（代码事实）

### 2.1 入口事实

- 前端“来源库运行”当前主要走 `POST /api/v1/ingest/source-library/run`。
- `POST /api/v1/source_library/items/{item_key}/run` 已收口为弃用入口（`410`），统一引导到 `POST /api/v1/ingest/source-library/run`。

### 2.2 主执行事实

来源项执行核心在 `source_library.resolver.run_item_payload`，按 3 分支运行：

1. `params.urls` 存在：URL 路由分支（按 URL 选 channel）。
2. handler cluster 或 `site_entries` 存在：统一搜索后再路由分支。
3. 其他：单 channel 直连分支。

### 2.3 服务映射事实

- API/协议型来源：通过 `runner.run_channel -> handler_registry` 的 `provider/kind` 处理（如 `reddit/social`、`google_news/news`）。
- 固定刷新来源：通过 `provider_type in {scrapy,crawlee,meltano}` 进入 crawler dispatch。
- 通用站点搜索：通过 `generic_web.*` 与 `handler.cluster + unified_search`。

## 3. 问题定位（为什么会出现“URL 来源冗余”）

1. `url_router` 默认回落 `url_pool`，使“未命中路由”与“URL 采集入口”语义混合。
2. `run_item_payload` 同时承载三类职责，入口定义与执行策略未显式绑定。
3. 前后端对来源库运行默认使用单入口（ingest），进一步放大“概念层混合”。

## 4. 目标架构（三分入口 + Item 抽象层）

### 4.1 Item 抽象契约（核心）

`items` 仅作为来源抽象集合，不直接绑定后端执行实现。

- 保留字段：语义标签、来源分组、策略偏好、约束条件、可见性。
- 移除/废弃字段：`channel_key`、`provider_type`、后端执行参数直通。
- 运行原则：`item` 不能直接触发 handler/provider，仅能先被解析为标准执行请求。

Item 类型固定为两类：

1. `user_defined`（用户自主创建）
   - `managed_by=user`
   - 可创建/编辑/删除
   - 用于业务来源抽象（对用户可见）
2. `service_aggregated`（按来源服务特性自动聚合）
   - `managed_by=system`
   - 系统自动生成与维护（用户默认只读）
   - 用于执行编排与服务能力聚合（对用户默认隐藏）

### 4.2 三分入口契约（执行层）

统一在请求层引入 `source_mode`（或等价字段）：

- `protocol_search`：特定来源搜索（API/协议型）。
- `provider_harvest`：特定来源采集（固定刷新 provider）。
- `site_search`：站点搜索（仅 `handler.cluster + unified_search`）。
- `url_execution`：URL 执行入口（从站点搜索职责中剥离）。

### 4.3 后端服务映射（建议）

1. `protocol_search` -> `SourceProtocolSearchService`
   - 接收标准执行请求；内部路由到协议型 provider。
2. `provider_harvest` -> `SourceProviderHarvestService`
   - 接收标准执行请求；内部路由到 crawler provider。
3. `site_search` -> `SourceSiteSearchService`
   - 仅保留 `handler.cluster + unified_search` 作为唯一入口。
   - `generic_web.*` 仅内部插件，不再暴露为来源项入口。
4. `url_execution` -> `UrlExecutionService`
   - 仅负责 URL 路由与执行，不承担站点搜索职责。

### 4.4 ItemResolver（编译层）

新增 `ItemResolver`，职责是把 `item` 解析为标准执行请求：

- 输入：`item_id + runtime_context + user_intent`
- 输出：`ExecutionRequest{source_mode, query_terms, scope, constraints, runtime_options}`
- 约束：`ExecutionRequest` 才允许进入后端服务链，`item` 本体不可直连执行层。

### 4.5 站点搜索拓扑收敛（关键决策）

当前站点搜索相关有三条路径：

1. `handler.cluster + unified_search`（编排路径）
2. `generic_web.*` 直连（来源项可直接绑定）
3. `params.urls` URL 路由（前门 URL 执行）

收敛目标：

1. 保留路径 1 作为站点搜索唯一入口。
2. 路径 2 下沉为内部插件能力（不再直接暴露为来源项入口）。
3. 路径 3 明确归类为“URL 执行入口”，不计入站点搜索入口集合。

> 注：首阶段可复用现有函数实现，仅增加 ItemResolver 与请求契约收敛。

## 5. 服务链（当前/目标）

### 5.1 当前服务链

1. 协议型来源搜索（reddit/google_news）
   - `POST /ingest/source-library/run`
   -> `collect_runtime.run_source_library_item_compat`
   -> `source_library.resolver.run_item_payload`
   -> `source_library.runner.run_channel`
   -> `handler_registry(provider/kind)` -> adapter execute

2. 固定来源采集（crawler provider）
   - `POST /ingest/source-library/run`
   -> `collect_runtime.run_source_library_item_compat`
   -> `source_library.resolver.run_item_payload`
   -> `source_library.runner.run_channel`
   -> `provider_type in {scrapy,crawlee,meltano}`
   -> crawler provider dispatch

3. 站点搜索（现状三路径并存）
   - 路径 A：`handler.cluster` -> `resource_pool.unified_search_by_item_payload` -> URL routing -> `run_channel`
   - 路径 B：`generic_web.*` item -> `run_channel` -> `generic_web` adapter
   - 路径 C：`params.urls` -> `run_item_with_url_routing` -> `url_router.resolve_channel_for_url` -> `run_channel`

### 5.2 目标服务链（收敛后）

0. Item 解析前置链
   - `API(item_id, runtime_context, user_intent)`
   -> `ItemResolver`
   -> `ExecutionRequest`

1. `protocol_search`
   - `ExecutionRequest(source_mode=protocol_search)`
   -> `protocol_search_orchestrator`
   -> protocol provider dispatch

2. `provider_harvest`
   - `ExecutionRequest(source_mode=provider_harvest)`
   -> `provider_harvest_orchestrator`
   -> crawler provider dispatch

3. `site_search`（唯一入口）
   - `ExecutionRequest(source_mode=site_search)`
   -> `site_search_orchestrator`
   -> `handler.cluster + unified_search`
   -> URL routing
   -> `run_channel`
   - `generic_web.*` 仅内部调用，不再直接暴露来源项入口

4. `url_execution`（从 site_search 剥离）
   - `ExecutionRequest(source_mode=url_execution)`
   -> `url_execution_orchestrator`
   -> URL routing
   -> `run_channel`

### 5.3 新增来源服务统一接入链（URL/API/JSON）

新增来源能力统一遵循同一主干：

`Source Onboarding Input -> Normalization/Classification -> service_aggregated item -> ItemResolver -> ExecutionRequest -> orchestrator -> run_channel/provider dispatch`

1. 新 URL 自动洗站点（站点发现链）
   - 入口：`POST /resource_pool/discover/site-entries`
   - 流程：`discover_site_entries_from_urls` -> `classify_site_entries_batch(可选)` -> `write_discovered_site_entries`
   - 回流：`POST /source_library/handler_clusters/sync` 生成/刷新 `service_aggregated` items（`handler.cluster.*`）
   - 执行：由 `ItemResolver` 解析为 `site_search` 或 `url_execution`

2. 新 API 来源接入（协议/采集链）
   - 入口：渠道定义（`provider/kind/provider_type/param_schema`）+ handler 注册
   - 流程：`sync_shared_library_from_files`（配置入库）+ `adapters.register(provider, kind, handler)`
   - 执行：`ItemResolver` 输出 `protocol_search` 或 `provider_harvest`，再进入对应 orchestrator

3. JSON 配置来源接入（配置链）
   - 入口：`信息源库/global/*` 与 `信息源库/projects/*` JSON/YAML
   - 流程：`loader._load_single_file/_load_dir` -> `sync_shared_library_from_files`（shared）/project merge（runtime）
   - 执行：统一通过 `ItemResolver`，不允许 item 直接绑定后端执行路径

统一约束：

- 以上三条链最终都必须产出 `item_type=service_aggregated` 或 `item_type=user_defined` 的 item 抽象，并经 `ItemResolver` 编译后执行。
- 禁止“新增来源服务 -> 直接写 channel_key 后立即直跑”绕过 resolver 主干。

### 5.4 字段级映射表（Onboarding -> ExecutionRequest）

| 输入来源 | 输入字段 | ExecutionRequest 字段 | 规则 |
|---|---|---|---|
| URL 自动洗站点 `/resource_pool/discover/site-entries` | `project_key` | `project_key` | 原样透传 |
| URL 自动洗站点 | `url_scope` | `scope` | 作为发现阶段读取范围；执行阶段写入 `runtime_options.url_scope` |
| URL 自动洗站点 | `target_scope` | `runtime_options.target_scope` | 仅用于写回 `site_entries` 目标范围 |
| URL 自动洗站点 | `domain / allow_domains / deny_domains` | `constraints.domain*` | 归入域名约束集合 |
| URL 自动洗站点 | `run_auto_classify / use_llm` | `runtime_options.classify` | 归入分类策略，不直接决定 source_mode |
| URL 自动洗站点输出 | `entry_type=search_template/rss/sitemap/domain_root` | `source_mode` | 默认映射 `site_search`；若仅产出固定 URL 集可映射 `url_execution` |
| 新 API 来源（channel 配置） | `provider / kind` | `source_mode` | 由 resolver 规则映射：协议型 -> `protocol_search` |
| 新 API 来源（channel 配置） | `provider_type` | `source_mode` | `scrapy/crawlee/meltano` -> `provider_harvest` |
| 新 API 来源（channel 配置） | `param_schema` | `runtime_options.param_schema` | 仅校验用途，不直通业务语义 |
| 新 API 来源（channel 配置） | `default_params` | `runtime_options.defaults` | 作为默认值，低优先级 |
| JSON 来源文件 `items` | `item_key` | `item_id` | 作为 resolver 输入主键 |
| JSON 来源文件 `items` | `tags / extra / description` | `constraints / runtime_options / metadata` | 由 ItemResolver 归并 |
| JSON 来源文件 `items` | `params.query_terms/keywords` | `query_terms` | 归一化为 `query_terms[]` |
| JSON 来源文件 `items` | `params.site_entries` | `constraints.site_entries` | 触发 `site_search` 倾向 |
| JSON 来源文件 `items` | `params.urls` | `runtime_options.urls` | 触发 `url_execution` 倾向 |

补充优先级（高 -> 低）：

1. 用户运行时输入（`user_intent/runtime_context`）
2. ItemResolver 推导结果
3. item 抽象字段（tags/constraints/preferences）
4. channel/default 配置（兼容层）

## 6. 最小改造路径（低风险）

1. Item 模型收敛：新增 `ItemResolver`，将 `item` 解析为 `ExecutionRequest`，禁止 item 直接执行。
2. Item 二类模型落地：新增 `item_type` + `managed_by`，仅允许 `user_defined/service_aggregated`。
3. API 层收敛：运行接口从“item 直跑”改为“item -> resolver -> source_mode 分发”。
4. 编排层拆分：将现有 `run_item_payload` 抽成
   - `protocol_search_orchestrator`
   - `provider_harvest_orchestrator`
   - `site_search_orchestrator`（仅 handler.cluster 路径）
   - `url_execution_orchestrator`（承接 `params.urls`）
5. 入口收敛：禁止新建 `channel_key=generic_web.*` 的直接运行来源项，转由 `site_search_orchestrator` 间接调用。
6. URL 语义收敛：`url_pool` 仅保留 URL 执行/采集职责；站点搜索默认不再隐式回落到 `url_pool`。
7. 兼容期保留旧路径：旧 `item.channel_key/params` 只读兼容映射到 resolver，不再作为新写入模型。
8. 可见性治理：列表 API 默认只返回 `user_defined`，显式参数才返回 `service_aggregated`。

## 7. 最小验证步骤

1. Item 抽象验证：
   - 校验 item 配置不再接受 `channel_key/provider_type` 新写入。
   - 校验 item 必须经过 resolver 生成 `ExecutionRequest` 才能执行。
2. Item 类型验证：
   - 校验仅允许 `item_type in {user_defined, service_aggregated}`。
   - 校验 `service_aggregated` 不可经用户 API 修改核心字段。
   - 校验列表默认仅返回 `user_defined`。
3. 协议型来源回归（reddit/google_news）：
   - 校验 `ExecutionRequest(source_mode=protocol_search)` 仅进入协议服务。
4. 固定来源回归（crawler provider）：
   - 校验 `ExecutionRequest(source_mode=provider_harvest)` 仅进入 crawler 服务。
5. 站点搜索回归（site_entries）：
   - 校验 `ExecutionRequest(source_mode=site_search)` 仅走 `handler.cluster + unified_search`。
   - 校验直接执行 `generic_web.*` 来源项被拒绝（或标记 deprecated）。
6. URL 执行回归（urls）：
   - 校验 `ExecutionRequest(source_mode=url_execution)` 走 URL 执行链，且不计入站点搜索入口统计。
7. 兼容性回归：
   - 历史 item 可执行（通过 resolver 兼容映射），并返回 deprecation 提示字段。

## 8. 接口与迁移清单

### 8.1 接口清单（建议）

1. Item 列表
   - `GET /source_library/items?item_type=user_defined`（默认）
   - `GET /source_library/items?include_system=true`（含 `service_aggregated`）
2. Item 写接口
   - `POST/PUT /source_library/items` 仅允许 `item_type=user_defined`
   - `service_aggregated` 仅允许系统内部任务写入
3. 运行接口
   - `POST /ingest/source-library/run`
   - 输入：`item_id + runtime_context + user_intent`
   - 服务端：`ItemResolver -> ExecutionRequest -> source_mode orchestrator`

### 8.2 存量迁移规则（建议）

1. 自动标记为 `service_aggregated`
   - `item_key like 'handler.cluster.%'`
   - `item_key='url_pool.default'`
2. 默认标记为 `user_defined`
   - 除上述规则外的现有 item
3. 数据修复
   - 为 `service_aggregated` 补齐描述/标签（防止管理端混淆）
   - 对 `user_defined` 缺失描述项给出治理告警（不阻塞运行）

### 8.3 当前数据库体检（2026-03-12）

实库抽样结论（`postgresql://postgres@localhost:5432/postgres`）：

1. `public.shared_source_library_items`
   - 总量：4
   - 分布：`market.general / news.google.general / policy.general / social.reddit.general`
   - 现状：无 `managed_by` / `item_type` 字段语义。
2. `project_demo_proj.source_library_items`
   - 总量：11
   - 分布：`handler.cluster`(4) + `crawler.*`(5) + `url_pool`(1) + `search.market`(1)
   - `extra.managed_by` 全部为空（`<null>`）。
3. 混杂点（当前“不清楚”来源）
   - 自动聚合项：`handler.cluster.*`（带 `stable_handler_cluster/creation_handler`）
   - 自动服务绑定项：`crawler.*.default`（带 `crawler_provider/crawler_project_*`）
   - 运行入口项：`url_pool.default`
   - 业务/测试项：如 `iso_check_*`（e2e 隔离检查）

按“两类 item”目标的即时判定：

1. `service_aggregated`：`handler.cluster.*` + `crawler.*` + `url_pool.default`
2. `user_defined`：其余（如业务自建 `search.market.*`、临时/测试项）

### 8.4 最小迁移 SQL（两类 item）

目标：仅保留 `item_type in {user_defined, service_aggregated}`，并显式 `managed_by in {user, system}`。

```sql
-- 1) 公共表补字段
ALTER TABLE public.shared_source_library_items
  ADD COLUMN IF NOT EXISTS item_type varchar(32),
  ADD COLUMN IF NOT EXISTS managed_by varchar(32);

UPDATE public.shared_source_library_items
SET item_type = 'service_aggregated',
    managed_by = 'system'
WHERE coalesce(item_type, '') = '' OR coalesce(managed_by, '') = '';

-- 2) 项目表批量补字段（按 public.projects.schema_name）
DO $$
DECLARE sch text;
BEGIN
  FOR sch IN SELECT schema_name FROM public.projects LOOP
    EXECUTE format('
      ALTER TABLE %I.source_library_items
        ADD COLUMN IF NOT EXISTS item_type varchar(32),
        ADD COLUMN IF NOT EXISTS managed_by varchar(32);', sch);

    EXECUTE format('
      UPDATE %I.source_library_items
      SET item_type = ''user_defined'', managed_by = ''user''
      WHERE coalesce(item_type, '''') = '''' OR coalesce(managed_by, '''') = '''';', sch);

    EXECUTE format('
      UPDATE %I.source_library_items
      SET item_type = ''service_aggregated'', managed_by = ''system''
      WHERE item_key LIKE ''handler.cluster.%%''
         OR item_key = ''url_pool.default''
         OR channel_key LIKE ''crawler.%%''
         OR coalesce(extra->>''stable_handler_cluster'', '''') = ''true''
         OR coalesce(extra->>''creation_handler'', '''') LIKE ''handler.%%''
         OR coalesce(extra->>''crawler_provider'', '''') <> '''';', sch);

    EXECUTE format('
      ALTER TABLE %I.source_library_items
      ADD CONSTRAINT IF NOT EXISTS ck_source_library_items_item_type
      CHECK (item_type IN (''user_defined'', ''service_aggregated''));', sch);

    EXECUTE format('
      ALTER TABLE %I.source_library_items
      ADD CONSTRAINT IF NOT EXISTS ck_source_library_items_managed_by
      CHECK (managed_by IN (''user'', ''system''));', sch);
  END LOOP;
END $$;
```

迁移后核验 SQL：

```sql
SELECT item_type, managed_by, count(*)
FROM project_demo_proj.source_library_items
GROUP BY 1,2
ORDER BY 3 DESC;
```

### 8.5 用户使用服务（item + 搜索参数）现状链路

当前已支持“`item + 搜索参数`”调用（通过 `override_params`）：

1. 入口：`POST /api/v1/ingest/source-library/run`
2. 参数：`item_key`（或 `items[]` 批量） + `override_params`
3. 链路：`ingest.ingest_source_library_run`
   -> `collect_runtime.run_source_library_item_compat`
   -> `collect_runtime.adapters.source_library.SourceLibraryAdapter.run`
   -> `source_library.resolver.run_item_payload`
4. 说明：`override_params` 可承载运行时搜索参数（如 `query_terms`、`max_items`、时间窗等），但当前仍是“item 直跑”模型，尚未切到 `ItemResolver -> ExecutionRequest`。

## 9. 参考实现位置

- `main/backend/app/services/source_library/resolver.py`
- `main/backend/app/services/source_library/runner.py`
- `main/backend/app/services/source_library/url_router.py`
- `main/backend/app/services/resource_pool/unified_search.py`
- `main/backend/app/api/ingest.py`
- `main/backend/app/api/source_library.py`
