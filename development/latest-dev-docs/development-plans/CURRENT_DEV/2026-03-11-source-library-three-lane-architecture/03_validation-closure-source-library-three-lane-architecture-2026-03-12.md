# Validation Closure: Source Library Three-Lane Architecture (2026-03-12)

## 1. Scope

本次闭环对应原子任务单：

- `AT-02/AT-09`: DB 两类 item 迁移与回填
- `AT-03/AT-04`: API 读写约束
- `AT-05/AT-07`: `ItemResolver -> ExecutionRequest` 与 `source_mode` 分流
- `AT-08`: 新增来源接入链统一约束（避免绕过 resolver 主干）

## 2. Implementation Result

已完成关键改动：

1. DB + ORM
   - 新增 migration `20260312_000007_add_item_taxonomy_to_source_library_items.py`
   - 为 `shared_source_library_items` 与 `source_library_items` 增加 `item_type`、`managed_by`
   - 回填规则已按计划落地，补充 check 约束
2. API
   - `GET /source_library/items` 默认仅返回 `user_defined`
   - `include_system=true` 可返回 `service_aggregated`
   - 用户 API 禁止写 `service_aggregated`
   - 新增 `PUT /source_library/items/{item_key}`（与 POST 同约束）
   - 禁止用户新建 `generic_web.*` 的 `user_defined` item（内部适配器不作为新入口）
3. Execution Mainline
   - resolver 新增 `ExecutionRequest`
   - `run_item_payload` 分流为 `source_mode`（`protocol_search/provider_harvest/site_search/url_execution`）
   - `site_search` 强制 `handler.cluster + unified_search`
   - `urls` 明确归入 `url_execution`
4. Onboarding Chain
   - sync/read/write 链路均补齐 `item_type/managed_by` 一等字段语义
   - 默认将 shared 同步项规范为系统聚合项

## 3. Runtime Validation

### 3.1 Migration Execution

已执行：

```bash
cd main/backend
python3 -m alembic current
python3 -m alembic upgrade head
python3 -m alembic current
```

结果：

- 升级前：`20260303_000006`
- 升级后：`20260312_000007 (head)`

### 3.2 SQL Sampling

抽样结果（`localhost:5432/postgres`）：

1. `public.shared_source_library_items`
   - `item_type/managed_by` 列存在
   - 分布：`user_defined/user = 4`
2. `project_demo_proj.source_library_items`
   - `item_type/managed_by` 列存在
   - 分布：
     - `service_aggregated/system = 10`
     - `user_defined/user = 1`
   - 样本符合预期：
     - `handler.cluster.*`、`crawler.*`、`url_pool.default` => `service_aggregated/system`
     - `iso_check_*` => `user_defined/user`

## 4. Test Status

已执行：

```bash
cd main/backend
python3.11 -m pytest -q \
  tests/integration/test_project_key_policy_unittest.py \
  tests/unit/test_source_library_resolver_unittest.py \
  tests/core_business/test_source_library_core_contract.py \
  tests/unit/test_resource_pool_unified_search_unittest.py \
  tests/unit/test_source_library_market_adapter_unittest.py \
  tests/unit/test_ingest_news_reddit_terms_unittest.py
```

结果：`46 passed, 0 failed`

## 5. Residual Risks

1. `item` 兼容层仍保留 `channel_key` 字段（用于存量兼容），长期终态收敛需在下一阶段统一抽象模型。
2. `shared` 侧是否全量统一为 `service_aggregated/system` 仍取决于产品口径。

## 6. 收敛结果（对齐 01/02/03）

### 6.1 01 定义收敛状态

1. `source_mode` + `ExecutionRequest` 分流已落地。
2. `generic_web.*` 直跑入口已封禁（仅作为内部插件能力保留）。
3. `item_type/managed_by` 两类模型与约束已落地。
4. 来源库旧运行入口 `POST /api/v1/source_library/items/{item_key}/run` 已收口为 `410 deprecated`，统一至 `POST /api/v1/ingest/source-library/run`。

### 6.2 02 任务定义收敛状态

1. `AT-07` 收敛完成：`site_search` 强制 `handler.cluster + unified_search`，并禁止 `generic_web.*` 直跑。
2. `AT-10` 收敛完成：核心契约与参数适配用例已通过本轮门禁。

### 6.3 03 封口条件

1. 核心契约漂移（`/source_library/items` 返回字段）已修复为新口径兼容断言。
2. 本轮按项目定义判定为“可封口”。

## 7. Next Actions

1. 下一阶段推进 `item` 抽象层去执行字段化（逐步下沉 `channel_key` 兼容层）。
2. 依据产品策略决定 `shared` 项是否全量系统聚合化，并补充一次数据治理迁移。

## 8. 2026-03-14 Follow-up Implementation Status

本节补充 2026-03-14 的实际代码状态，覆盖本文件完成后继续落地的三车道与边界收敛工作。

### 8.1 三车道执行层

已补齐独立 orchestrator 模块：

- `protocol_search`
- `provider_harvest`
- `site_search`
- `url_execution`

当前 resolver 主干职责已进一步收敛为：

1. `item + params` 归一
2. `ExecutionRequest` 编译
3. 按 `source_mode` dispatch 到 lane orchestrator

其中第 2 步已进一步从 `resolver.py` 内联逻辑抽为独立 `ItemResolver` 模块，`ExecutionRequest` 也已迁入独立文件维护。

### 8.1.1 ItemResolver 模块化

当前职责分层已变为：

1. `ItemResolver` 负责 `item -> ExecutionRequest`
2. `resolver` 负责主干路由与运行分发
3. lane orchestrator 负责各自执行路径的轻量编排

这意味着 `resolver` 不再同时承担“编译器 + 分发器 + 执行器”三种角色。

### 8.2 末端输出边界

来源库对外 terminal output 已转为 clean terminal contract，主语义为：

- `results.records`
- `results.stats`
- `errors`
- `meta`
- `raw_snapshot`

`inserted/updated/skipped` 不再是对外权威结果语义。

### 8.3 site_search / url_execution 运行结果

1. `url_execution` 的 `terminal_output_only` 已从占位规划改为真实 fetch-only 执行。
2. `site_search` 主结果已转为 `records + stats + fetch_diagnostics`。
3. `protocol_search` 与 `provider_harvest` 已增加 lane 自己的 orchestrator metadata，不再只是零行为透传。
4. 旧 ingest 风格字段已下沉到兼容位或诊断位，不再是主结果结构。

### 8.4 兼容策略现状

1. `legacy_result` 仍保留，以兼容 collect runtime 与旧消费链。
2. `legacy_result` 已降级为废弃兼容位，不再是来源库正式输出边界。
3. 低风险 legacy helper `_plan_single_routed_url` 已删除。
4. `run_item_by_key` stub 已正式移除，当前来源库内部主入口仅保留 `run_item_payload` 与 ingest/collect runtime 前门。
5. 历史 `single_url.py` 已物理移除；来源库主链、`/api/v1/ingest/url/single` 同步/异步入口、`news/url_pool` 正式链路均不再依赖该模块。
6. 历史 `task_ingest_single_url` 与 `single_url_*` 参数兼容层也已删除。
7. 当前单 URL 与 URL 池写入主路径统一为 `url_routing/source_library -> postprocess_frontdoor`。

### 8.5 当前门禁状态

已通过本轮来源库相关回归门禁，验证点包括：

1. terminal output contract
2. collect runtime source_library adapter
3. url pool adapter
4. resolver lane dispatch
5. handler cluster frontdoor
6. source_library core contract
7. item resolver contract
