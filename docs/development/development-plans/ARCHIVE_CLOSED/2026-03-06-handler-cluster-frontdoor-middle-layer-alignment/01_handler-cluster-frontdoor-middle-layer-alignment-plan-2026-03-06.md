<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-03-06-handler-cluster-frontdoor-middle-layer-alignment/01_handler-cluster-frontdoor-middle-layer-alignment-plan-2026-03-06.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-06-handler-cluster-frontdoor-middle-layer-alignment/01_handler-cluster-frontdoor-middle-layer-alignment-plan-2026-03-06.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Handler-Cluster 前侧收敛与系统中间层对齐计划（2026-03-06）

Date: 2026-03-06 (PST)
Owner: Codex + parallel agents
Scope: source library front-door routing, resource-pool search convergence, URL ingest orchestration, crawler fallback layering

## 1. 背景

当前资源库 `handler-cluster/site_entries` 相关链路已经能产出候选 URL，也已经具备中段机械采集失败后转爬虫采集的能力，但真实运行口径仍存在层级错位：

- 资源库搜索链与 URL 采集链没有稳定收敛到同一个系统中间层。
- `handler-cluster` 在最前侧存在特判直连中段搜索服务的情况。
- 中段 `single_url` 内部虽然具备 fallback，但前侧统一入口没有完整承接这套编排。

这会导致架构理解偏向“中段补规则”，而不是“统一入口调度”。

## 2. 问题定义

本次要解决的问题不是单个站点搜索命中率，也不是单个爬虫 provider 配置，而是两条核心链路没有对齐到同一层：

1. `search params + item/url -> 系统中间层 -> 文档产出`
2. `url -> 系统中间层 -> 搜索适配 -> 系统中间层`

如果这两条链分别落在 `resource_pool/unified_search`、`single_url/url_pool`、项目级 crawler channel 等不同层，系统就会继续出现：

- 前侧旁路
- 中段重复编排
- channel 选择被误解为架构分层
- “机械采集失败自动转爬虫”只在局部生效

## 3. 原始约束

本次计划沿用项目原始设计约束：

- 统一入口必须先于中段执行。
- `handler-cluster` 应被视为系统能力，而不是 adapter 内的特判分支。
- 机械采集与爬虫采集是同一中间层下的两种执行策略，不应拆成两套入口。
- 项目级 `crawler.*` 仅承担运行时配置职责，不承担架构分层职责。

## 4. 现状错位

### 4.1 前侧旁路

`collect_runtime/adapters/source_library.py` 曾对 `handler_cluster_item` 直接调用资源池搜索逻辑，绕开了统一的 `run_item_by_key` 路由编排。

### 4.2 fallback 主要发生在中段

`single_url` 内已经存在机械采集失败后转 crawler pool 的 fallback，但这属于执行中段能力，不等于最前侧已经完成统一收敛。

### 4.3 运行时 channel 被误读成系统层

实际运行中可能会出现某个项目级 `crawler.*` channel 被选中，但这只是配置层结果，不能代表系统中间层已经稳定建模。

## 5. 本次收敛动作

本次开发计划对应的已完成动作如下：

1. 将资源库 `handler-cluster/site-entry` 路径收回前侧统一入口，不再在 adapter 内直接旁路到中段搜索服务。
2. 统一由 `run_item_by_key` / `run_item_payload` 承担前侧入口职责。
3. 对 `handler-cluster` 产生的候选 URL，重新送回前侧 URL routing，再决定后续机械采集或 crawler fallback。
4. 保留 `unified_search` 的候选发现职责，但不再让它承担“前侧统一入口”角色。

## 6. 当前验证结果

### 6.1 定向测试

- `tests/unit/test_source_library_resolver_unittest.py` + `tests/unit/test_source_library_handler_cluster_frontdoor_unittest.py`: `13 passed`
- `tests/unit/test_resource_pool_unified_search_unittest.py` + `tests/unit/test_resource_pool_search_capabilities_unittest.py`: `6 passed`
- 本轮封口前已验证的 source-library + resource-pool 组合门禁口径仍为：`19 passed`

### 6.2 前侧链路验证

从最前侧资源库入口重放 `report1.root_site_search` 后，观察到：

- `single_write_workflow = front_door_url_routing`
- 默认 `prefer_crawler_first = false`
- `channels_used = ["url_pool", "generic_web.search_template"]`
- 静态 URL-list item 与运行时 URL 集合都进入同一前门 `url_routing` 链路
- 在 `30` 候选真实对照中，`mechanical_first_30 = 20.092s`，`crawler_first_30 = 53.529s`

这说明前侧不仅已经收敛，而且默认机械优先的吞吐策略已在真实链路上验证更快。

### 6.3 当前剩余边界

当前 live run 已不再掉入旧的 provider 注册缺口。本机 `scrapyd` 运行环境已补齐，前侧链路已经可以完成真实文档写入。

## 7. 架构边界与非目标

本计划明确排除以下误读：

- `crawler.demo_proj` 或任意 `crawler.*` channel 不是系统中间层。
- 本次不是要把项目级 channel 提升为架构主线。
- 本次不是搜索排序质量优化计划。
- 本次不是单站点模板积累计划。

本计划只处理“入口收敛”和“中间层对齐”。

## 8. 后续计划

### P1 系统中间层协议显式化

- 将 `handler.cluster` 形式化为系统级能力协议。
- 让 `resource_pool search / url routing / single_url / crawler fallback` 在同一协议下协同。

### P2 项目级 channel 降级为配置层

- 保持 `crawler.*` 只做 provider / project / runtime 配置。
- 不再让项目级 channel 反向定义系统分层。

### P3 运行态 provider 收口

- 单独修复 crawler provider 注册与执行兼容问题。
- 确保统一入口已经收敛后，运行态不再因为 provider_type 不一致而中断写库。
- 本机已验证 `scrapyd` 本地 daemon 启动后，front-door 写库可成功插入文档。

## 9. 相关代码入口

- `main/backend/app/services/collect_runtime/adapters/source_library.py`
- `main/backend/app/services/source_library/resolver.py`
- `main/backend/app/services/ingest/single_url.py`
- `main/backend/app/services/resource_pool/unified_search.py`

## 10. 验收标准

满足以下条件即视为本计划完成：

1. `handler-cluster/site-entry` 不再在前侧旁路中段搜索服务。
2. `search params + item/url` 与 `url` 两条链进入同一前侧中间层编排。
3. 候选 URL 文档写入流程可观察到前侧 routing 痕迹，而非直接中段直写。
4. 项目级 `crawler.*` 仅作为配置层出现，不再被文档口径误写为系统中间层。
