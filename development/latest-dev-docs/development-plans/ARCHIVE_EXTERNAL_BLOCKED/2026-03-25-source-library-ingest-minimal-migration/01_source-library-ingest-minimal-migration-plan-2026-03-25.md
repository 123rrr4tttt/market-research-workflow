# Source-Library / Ingest 最小迁移计划

Updated: 2026-03-25 PST

## 目的

基于下面两份最新澄清材料，给出一条“尽可能小改动、不丢功能、不打断现有链路”的迁移计划：

- [2026-03-25-ingest-structure-clarification-log.md](./references/2026-03-25-ingest-structure-clarification-log.md)
- [2026-03-25-source-library-to-db-service-flow-investigation.md](./references/2026-03-25-source-library-to-db-service-flow-investigation.md)
- [02_source-library-ingest-node-mapping-and-preservation-checklist-2026-03-26.md](./references/02_source-library-ingest-node-mapping-and-preservation-checklist-2026-03-26.md)

目标不是一次性重构成“理想架构”，而是：

1. 先把 batch URL 主路径摆正。
2. 再把 frontdoor 前的真实 contract 和 middle outputs 显式固定下来。
3. 整个过程中保留现有入口、兼容层、调试口径、统计口径和落库链。

## 参考资料包

本主题的调查、澄清、图和保全清单已打包到：

- [references/INDEX.md](./references/INDEX.md)

## 配套执行文档

- [02_wave0-freeze-and-acceptance-contract-2026-03-26.md](./02_wave0-freeze-and-acceptance-contract-2026-03-26.md)
- [03_atomic-tasklist-source-library-ingest-minimal-migration-2026-03-26.md](./03_atomic-tasklist-source-library-ingest-minimal-migration-2026-03-26.md)
- [04_parallel-wave-plan-source-library-ingest-minimal-migration-2026-03-26.md](./04_parallel-wave-plan-source-library-ingest-minimal-migration-2026-03-26.md)
- [references/2026-03-26-batch-helper-input-boundary-and-runtime-target-contract.md](./references/2026-03-26-batch-helper-input-boundary-and-runtime-target-contract.md)
- [references/2026-03-26-batch-switch-rollout-dispatch-precedence-matrix.md](./references/2026-03-26-batch-switch-rollout-dispatch-precedence-matrix.md)

## 迁移原则

### 总原则

- 优先保留现有运行面，再收敛结构表达。
- 先抽“可复用 primitive”，再改调用关系。
- 先增加新路径，后切换默认路径，最后再考虑降级旧路径。
- 所有阶段都必须可回退。
- 所有阶段都必须保留同等级别的 observability。

### 非目标

这轮迁移不做下面这些大动作：

- 不删除 `collect_urls_from_list(...)`
- 不删除 `ingest_url_via_source_library_frontdoor(...)`
- 不删除 `source_mode`
- 不删除 `terminal_output`、`frontdoor_ingress`、`postprocess_frontdoor` 兼容输出
- 不删除 `handler.cluster` / `url_pool` / `generic_web.*` 现有 channel 暴露面
- 不重写 API / Celery / collect runtime 边界

## 节点保全执行规则

执行这份计划时，必须同时遵守：

- [02_source-library-ingest-node-mapping-and-preservation-checklist-2026-03-26.md](./references/02_source-library-ingest-node-mapping-and-preservation-checklist-2026-03-26.md)

核心规则不是“新结构概念上覆盖了旧结构”，而是：

1. 每个当前节点都必须能映射到：
   - 原节点保留
   - 新 owner layer
   - 显式 compatibility path
2. 每条当前调用链都必须还能被追溯。
3. 任何函数、输出字段、side effect、observability 钩子都不能无声消失。

### 全局 Gate

在任一阶段开始前，都必须满足：

- 本阶段涉及的节点已在保全清单中登记。
- 本阶段涉及的旧 caller 和新 caller 已写明。
- 若有替换，替换节点名称必须明确写出，不能只写“归并到某层”。
- 若没有精确替换节点，则视为信息丢失，阶段不得开始。

## 必须保留的能力

### 入口与边界

- `loader.py / sync.py -> shared_ingest_channels / shared_source_library_items`
- 项目级 `ingest_channels / source_library_items`
- `/api/v1/ingest/source-library/run`
- `run_source_library_item_compat`
- `run_collect`
- `SourceLibraryAdapter.run`
- `task_run_source_library_item`
- `task_ingest_url_via_source_library`
- `task_ingest_market`
- `task_collect_policy_regulation`
- `task_collect_data_api`

### 执行与分流

- `ItemResolver.resolve(...)`
- `source_mode` 现有语义和统计口径
- `run_channel(...)`
- `handler.cluster -> unified_search_by_item_payload(...)`
- `run_item_with_url_routing(...)`
- `google_news / reddit / market / policy` 现有 provider 跳转链
- `generic_web / official_access` 候选生成与资源池 side effects

### middle outputs / side effects

- `candidates`
- `records`
- `by_url`
- `stats`
- `legacy_counts`
- `rejection_breakdown`
- `diagnostics`
- `append_url / upsert_site_entry`
- `resource_pool_urls / resource_pool_site_entries`

### frontdoor / writer / compat

- `ingress_envelope` 统一 contract
- `document_candidate -> accept`
- `records-only -> defer`
- `run_postprocess_frontdoor(...)`
- `persist_terminal_document(...)`
- `terminal_output`
- `frontdoor_ingress / postprocess_frontdoor` 兼容输出

### observability

- `start_job / complete_job / fail_job`
- `etl_job_runs`
- trace/debug/metrics
- batch 聚合结果：`inserted / updated / skipped / inserted_valid / rejected_count / degradation_flags`

## 迁移总策略

### 结构修改 1 与结构修改 2 的落地关系

- `结构修改 2` 是总框架：
  `definition/runtime -> execution line -> binding -> engine -> middle outputs + side effects -> ingress_envelope -> frontdoor/output -> compat/observability`
- `结构修改 1` 是其中 batch URL specialized path 的局部收敛：
  `collect_urls_from_list -> run_item_with_url_routing -> middle outputs -> ingress_envelope -> aggregate output`

落地时应始终按这个顺序理解：

1. 先把 batch URL 主链从 single-url wrapper 里剥出来。
2. 但 frontdoor 前仍然统一收敛到 `ingress_envelope`。
3. 同时保留 single-url compatibility path。
4. 最后才逐步让文档、图和命名收敛到新分层。

## 分阶段迁移计划

## 阶段 0

### 名称

Freeze current contracts and verification baselines.

### 目标

在任何代码改动之前，先把当前必须保留的 contract 和验证面固定下来。

### 改动范围

- 文档
- 轻量测试补充
- 不改主执行逻辑

### 最小动作

1. 明确当前稳定 contract：
   - `run_item_with_url_routing(...)` 返回结构
   - `ingest_url_via_source_library_frontdoor(...)` 返回结构
   - `collect_urls_from_list(...)` 返回结构
   - `build_source_library_ingress_envelope(...)` / `run_postprocess_frontdoor(...)` 对 `records-only` 的行为
   - batch helper 输入边界固定为 `runtime_targets`，而不是 raw `urls`
   - batch switch / dispatch / frontdoor rollout 的优先级矩阵
   - 节点保全基线：`02_source-library-ingest-node-mapping-and-preservation-checklist-2026-03-26.md`
2. 为现有返回结构补回归测试或快照测试。
3. 固定 `terminal_output` 统计口径。

### 验收

- 现有调用方不改代码也能通过全部回归。
- 文档能明确回答“这一轮不能动什么”。
- 本阶段涉及节点全部进入保全清单，状态至少标成 `unchanged` 或 `moved`。
- 不能再出现“节点只存在于图里、不存在于计划或清单里”的情况。

## 阶段 1

### 名称

Extract batch routing primitive without changing default call graph.

### 目标

把 batch URL 路由能力从“single-url wrapper 的重复调用结果”提升成显式 primitive，但不改变默认行为。

### 改动范围

- `main/backend/app/services/source_library/resolver.py`
- `main/backend/app/services/ingest/url_pool.py`

### 最小动作

1. 固化 `run_item_with_url_routing(...)` 的 batch 入口地位。
2. 在 `ingest/url_pool.py` 增加内部 bulk handoff helper，但默认仍可走旧路径。
3. `collect_urls_from_list(...)` 先支持 feature-flag 或 internal switch，允许：
   - 旧路径：逐条 URL 走 `ingest_url_via_source_library_frontdoor(...)`
   - 新路径：一次 batch 调 `run_item_with_url_routing(...)`
   - 两条路径都以同一份 `runtime_targets` 作为执行输入
4. single-url 入口不动。

### 必须保持不变

- `ingest_url_via_source_library_frontdoor(...)` 的对外 contract
- `collect_urls_from_list(...)` 的对外返回字段
- `rejection_breakdown / degradation_flags / debug`

### 验收

- 关闭开关时行为与当前一致。
- 打开开关后 batch URL 能拿到同等级别的 `by_url / records / stats / diagnostics`。
- `run_item_with_url_routing(...)`、`collect_urls_from_list(...)`、`ingest_url_via_source_library_frontdoor(...)` 的 caller 映射已更新到保全清单。
- 旧路径和新路径对应输出字段一一可对照，不能用“batch result”之类摘要替代。

## 阶段 2

### 名称

Introduce explicit batch frontdoor handoff.

### 目标

让 batch URL 路径在 frontdoor 前显式经过统一 handoff，而不是隐含在 single-url wrapper 里。

### 改动范围

- `main/backend/app/services/ingest/url_pool.py`
- `main/backend/app/services/ingest/frontdoor_ingress.py`
- `main/backend/app/services/ingest/postprocess_frontdoor.py`

### 最小动作

1. 增加 `record -> document_candidate` 的 bulk handoff helper。
2. 明确 batch 路径里两种合法入口：
   - `document_candidate` 批量或逐条 accept path
   - `records-only` defer path
3. 不改 `run_postprocess_frontdoor(...)` 现有 admission 语义，只把 caller 关系变清楚。

### 必须保持不变

- `ingress_envelope` contract version
- `records-only -> defer`
- `document_candidate -> accept`
- writer 行为与 dedup 行为

### 验收

- batch URL 新路径不再依赖 single-url wrapper 作为主中心。
- frontdoor admission 行为无回归。
- `build_source_library_ingress_envelope(...)`、`build_frontdoor_ingress_envelope(...)`、`ingress_envelope`、`run_postprocess_frontdoor(...)` 的节点映射保持完整。
- `document_candidate -> accept` 与 `records-only -> defer` 仍然能在测试和文档里被单独定位。

## 阶段 3

### 名称

Switch batch default, preserve compatibility path.

### 目标

把 `collect_urls_from_list(...)` 默认切到 batch routing path，但保留旧兼容入口用于回退和特殊调用方。

### 改动范围

- `main/backend/app/services/ingest/url_pool.py`
- 直接依赖 `collect_urls_from_list(...)` 的 provider / ingest service

### 最小动作

1. 让 `collect_urls_from_list(...)` 默认先走 batch routing primitive。
2. 保留 `ingest_url_via_source_library_frontdoor(...)`：
   - 作为 single-url compatibility path
   - 作为紧急回退路径
3. provider 调用侧不改 contract，只切底层默认实现。
4. 默认开关与回退开关遵守同一份 precedence matrix，不能复用 frontdoor rollout 开关代替 batch rollback。

### 必须保持不变

- provider -> existing ingest service 调用链
- `collect_urls_from_list(...)` 返回 envelope
- debug 与 metrics 字段

### 验收

- 现有 provider 无需改 payload shape。
- 批量路径性能和可观测性不低于旧路径。
- `google_news -> collect_google_news`、`reddit -> collect_reddit_discussions`、`market -> collect_market_info` 这三条 compat 函数链仍能逐条追溯。
- `job_logger -> etl_job_runs`、`terminal_output`、`legacy_result` 没有因为默认路径切换而失联。

## 阶段 4

### 名称

Align docs, naming, and internal layering.

### 目标

在不动外部 contract 的前提下，让内部命名和文档逐步接近预期总图。

### 改动范围

- 文档
- 内部 helper 命名
- 少量内部结构重命名

### 最小动作

1. 把文档主口径切到预期总图。
2. 把 `source_mode` 定位明确成 runtime projection。
3. 把 `run_channel(...)` / orchestrator / engine / middle outputs 的边界写清楚。
4. 仅在内部 helper 层重命名，外部 contract 保持兼容。

### 必须保持不变

- API 名称
- task 名称
- 兼容输出字段
- channel/item 配置面

### 验收

- 新文档能解释现状代码和目标结构。
- 旧调用方不感知内部命名变化。
- 文档中的每个摘要层都能回指到保全清单里的节点级条目。
- 不允许再用大盒子覆盖掉现有函数对、side effects 或 compat 链名称。

## 阶段 5

### 名称

Optional cleanup after long-tail validation.

### 目标

只在长尾验证充分后，才考虑真正降级旧路径。

### 改动范围

- 仅在阶段 0-4 稳定运行一段时间后考虑

### 最小动作

1. 统计 single-url compatibility path 的真实调用量。
2. 只有确认没有关键依赖后，才考虑把它进一步降级为 thin wrapper。
3. 不直接删除旧入口，先发 deprecation 文档。

### 验收

- 回退路径仍然存在。
- 没有隐藏调用方被切断。
- 任一准备删除的 compat 路径，必须先在保全清单里把所有 caller 标完并给出 replacement node。
- 若 replacement node 不是函数级名称，而只是概念层名称，则不允许进入删除阶段。

## 最小代码改动顺序

推荐严格按下面顺序推进：

1. 补 contract / regression tests
2. 增加 batch routing internal helper
3. 增加 batch frontdoor handoff helper
4. 给 `collect_urls_from_list(...)` 加 internal switch
5. 小流量或默认开关切换到 batch path
6. 补齐文档与图
7. 长尾观察后再考虑降级旧实现

不要倒过来做：

- 不要先删 single-url path
- 不要先改 `source_mode`
- 不要先动 provider 调用面
- 不要先改 writer contract

## 阶段执行记录模板

每一波实际执行都建议在任务说明或 PR 描述里带下面四项：

1. touched nodes
- 从保全清单里列出本次涉及的节点名

2. node status
- `unchanged`
- `moved`
- `wrapped`
- `replaced`

3. replacement mapping
- 只有 `replaced` 时填写
- 必须写精确 replacement node name

4. verification
- contract
- path
- observability

如果某项写不出来，说明这一波还没有准备好执行。

## 文件级建议改动面

### 第一波

- `main/backend/app/services/source_library/resolver.py`
- `main/backend/app/services/ingest/url_pool.py`
- `main/backend/tests/...` 相关回归测试

### 第二波

- `main/backend/app/services/ingest/frontdoor_ingress.py`
- `main/backend/app/services/ingest/postprocess_frontdoor.py`
- `main/backend/app/services/source_library/terminal_output.py`

### 暂缓

- `main/backend/app/services/source_library/item_resolver.py`
- `main/backend/app/services/source_library/runner.py`
- orchestrators 命名层
- provider / generic_web 入口重命名

## 风险与控制

### 风险 1

batch path 切换后丢失 `by_url / diagnostics / rejection_breakdown`

控制：

- 阶段 0 先固化 contract
- 阶段 1-3 每阶段都对比旧新输出

### 风险 2

frontdoor handoff 重写时把 `records-only -> defer` 误改成直接写库

控制：

- admission 语义单独做回归测试
- `run_postprocess_frontdoor(...)` contract 不改，只改 caller

### 风险 3

provider 跳转链断裂

控制：

- provider 层 contract 不先改
- 先只换 `collect_urls_from_list(...)` 内部默认实现

### 风险 4

observability 下降，问题难排查

控制：

- `terminal_output`
- `frontdoor_ingress / postprocess_frontdoor`
- `debug`
- `etl_job_runs`
- batch aggregate 字段

全部视为必须保留面。

## 回退策略

每一阶段都必须支持下面的回退：

1. 通过开关切回旧 batch path。
2. 保留 `ingest_url_via_source_library_frontdoor(...)` 作为单 URL 回退。
3. 保留 `collect_urls_from_list(...)` 对外接口不变。
4. 保留旧 debug / metrics / compat 输出字段。
5. 回退只允许通过 batch-path knob 或 repo-level default，不通过 `ingest_frontdoor_rollout_mode` 伪装回退。

## 最小验证矩阵

### 合同验证

- `run_item_with_url_routing(...)` 返回结构
- `collect_urls_from_list(...)` 返回结构
- `ingest_url_via_source_library_frontdoor(...)` 返回结构
- `build_source_library_ingress_envelope(...)`
- `run_postprocess_frontdoor(...)`

### 路径验证

- `handler.cluster -> candidates -> url routing -> frontdoor`
- `url_pool direct URL -> frontdoor`
- `google_news -> collect_urls_from_list(...)`
- `reddit -> collect_urls_from_list(...)`
- `market -> collect_urls_from_list(...)`
- `policy -> direct/frontdoor special path`
- `generic_web / official_access -> resource_pool writes`

### 可观测性验证

- `terminal_output` 统计
- `rejection_breakdown`
- `degradation_flags`
- `debug`
- `etl_job_runs`

### 建议门禁命令

实际命令以仓库当时可用测试集为准，至少覆盖：

1. `pytest` 针对 `postprocess_frontdoor` / `frontdoor_ingress` / `source_library` / `url_pool` 的相关单测
2. `pytest` 针对 provider 到 `collect_urls_from_list(...)` 的集成回归
3. 若有契约快照测试，必须同时比较旧新路径输出字段

## 推荐结论

推荐采用：

- `阶段 0 -> 阶段 1 -> 阶段 2 -> 阶段 3`

作为当前主迁移顺序。

`阶段 4` 只在结构稳定后推进。  
`阶段 5` 只有在兼容路径长期低风险时才进入。

这条方案的核心不是“改得快”，而是：

- 先固定 contract
- 再抽 primitive
- 再切 batch 主路径
- 全程保留 compatibility
- 全程保留 observability

这样最符合当前项目“最小改动、不丢功能、不打断链路”的要求。
