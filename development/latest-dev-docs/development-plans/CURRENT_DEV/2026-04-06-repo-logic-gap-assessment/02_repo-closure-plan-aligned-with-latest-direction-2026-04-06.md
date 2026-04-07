# Repo Closure Plan Aligned With Latest Direction (2026-04-06)

> 日期：2026-04-06
> 范围：`main/backend`、`main/frontend-modern`、`development/latest-dev-docs`、质量门禁与兼容层收口
> 状态：current dev closure plan
> 目的：基于最新开发文档预期、最新开发方向，以及近期 Codex 对话中重复出现的治理结论，给出一条可执行的仓库级收口计划

## 1. 计划定位

这份计划不是重新发明一套 roadmap，而是对当前已经出现的三类输入做统一收敛：

1. 最新开发文档预期
2. 最新开发方向
3. 近期 Codex 对话中重复出现的闭环建议

因此，这份文档的目标不是“再列一份大而全理想架构”，而是定义：

1. 当前应先收什么口
2. 每个收口阶段的最低输出是什么
3. 哪些兼容层必须暂时保留
4. 哪些门禁必须转为 fail-closed
5. 什么条件下才算可以从 `CURRENT_DEV` 走向封口归档

## 2. 输入依据

### 2.1 最新开发文档预期

当前 `development/latest-dev-docs` 的事实入口已经明确偏向“未封口任务的状态评估 + 执行清单 + 验证闭环”模式，而不是单纯方案堆积。

代表性依据：

1. [01_repo-logic-gap-assessment-2026-04-06.md](./01_repo-logic-gap-assessment-2026-04-06.md)
2. [01_claude-agent-high-fidelity-migration-mapping-2026-04-02.md](../2026-04-02-claude-agent-high-fidelity-migration/01_claude-agent-high-fidelity-migration-mapping-2026-04-02.md)
3. [03_frontend-three-layer-rewrite-closure-gap-assessment-and-rollout-2026-04-02.md](../2026-03-15-frontend-three-layer-rewrite/03_frontend-three-layer-rewrite-closure-gap-assessment-and-rollout-2026-04-02.md)
4. [01_source-library-ingest-minimal-migration-plan-2026-03-25.md](../2026-03-25-source-library-ingest-minimal-migration/01_source-library-ingest-minimal-migration-plan-2026-03-25.md)
5. [05_validation-closure-source-library-ingest-minimal-migration-2026-03-26.md](../2026-03-25-source-library-ingest-minimal-migration/05_validation-closure-source-library-ingest-minimal-migration-2026-03-26.md)
6. [README.md](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/development/latest-dev-docs/README.md)
7. [MERGED_OVERVIEW.md](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/development/latest-dev-docs/MERGED_OVERVIEW.md)

这些文档共同给出的预期是：

1. 先做 gap assessment，再做 atomic task list，再做 validation closure。
2. 允许兼容层保留，但必须显式登记，不能“口头说兼容”。
3. 计划必须带回退旋钮、contract freeze 和最小验证包。
4. `CURRENT_DEV` 文档的价值不只是排期，还要承担事实口径。

### 2.2 最新开发方向

最近几批文档叠加后的主方向已经比较清楚：

1. agent runtime 要从临时编排迁移到 session/task/event ledger 式核心。
2. workflow graph 要从进程内编译态走向持久化 runtime。
3. source-library 要坚持“最小迁移 + compatibility retention + validation closure”。
4. frontend 要从半重构态收敛到单一 render/shell 事实源、兼容 adapter 下沉、分层 shell 完整。
5. 多项目隔离、API guardrail、required checks、PR evidence 要从“建议”逐步转成硬门禁。

### 2.3 近期 Codex 对话重复结论

近期本地 Codex 会话中重复出现的建议，与文档方向基本一致：

1. 质量门禁要 fail-closed，不能只保留为说明性脚本。
2. PR 交付必须包含 `Scope / Risk / Test Evidence / Rollback`。
3. API 边界要继续通过静态检查和 allowlist 收紧。
4. 文档路径漂移本身就是风险，索引与证据链需要持续维护。
5. 回归验证应尽量可见化，避免“实现完成但闭环证据缺失”。

相关仓库内约束面：

1. [PULL_REQUEST_TEMPLATE.md](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/.github/PULL_REQUEST_TEMPLATE.md)
2. [branch-protection-required-checks.json](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/.github/branch-protection-required-checks.json)
3. [check_api_layer_imports.py](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/scripts/check_api_layer_imports.py)

补充说明：

1. 上述 Codex 对话结论主要来自本地 `~/.codex/session_index.jsonl`、`~/.codex/history.jsonl` 与 2026-03-25、2026-04-01 附近归档会话。
2. 这些对话不应成为唯一依据，但可作为“最近反复出现的治理共识”。

## 3. 本轮收口原则

### 3.1 先补平台底座，再继续扩能力

当前最危险的状态不是“功能少”，而是“平台语义强于 runtime 现实”。因此先收：

1. runtime durability
2. capability truthfulness
3. isolation hardening
4. single render/shell source of truth
5. regression visibility

### 3.2 默认保留兼容面，但必须显式登记

对现有兼容层的策略应是：

1. 允许暂留
2. 必须写明 owner、替代路径、下线条件
3. 必须有回归覆盖或 smoke 证据

### 3.3 每个阶段都要可回退

所有收口阶段都必须有：

1. 明确 feature flag / selector / default knob
2. 回退窗口
3. 回退责任人或责任模块

### 3.4 文档闭环与代码闭环同步推进

不能再接受“代码已进入半完成，但文档还停在 pending”的状态。每个阶段完成后，至少要同步：

1. 当前专题文档
2. `CURRENT_DEV/INDEX.md`
3. 顶层 `README.md` 与 `MERGED_OVERVIEW.md`

## 4. 收口目标

本轮收口不追求一次性完成全部理想架构，而是以以下 5 个目标为准：

1. `workflow graph` 成为可恢复、可回取、可跨进程的 runtime 入口。
2. agent runtime 明确以 session/task/event ledger 为主核，旧入口降为 adapter。
3. source-library 与 ingest 兼容面保留但边界冻结，权威 contract 清晰。
4. frontend 渲染/路由/shell ownership 收敛，模块 metadata 继续以单一 manifest 派生。
5. 质量门禁从“文档化”转向“默认执行并阻断合并”。

## 5. 分阶段收口计划

## 阶段 0

### 名称

Freeze closure scope, gates, and compatibility inventory.

### 目标

先冻结这一轮收口范围、门禁和兼容清单，避免边做边改口径。

### 最小输出

1. 本文档作为主收口计划。
2. 为每个重点流建立 owner 与验收项：
   - workflow graph
   - agent runtime
   - source-library / ingest
   - frontend kernel / shell
   - project isolation / API gate
3. 建立兼容清单：
   - `agent_batch`
   - `workflow_graph` 旧编译态路径
   - `legacy_result`
   - `terminal_output`
   - `frontdoor_ingress`
   - `postprocess_frontdoor`
   - frontend legacy hash / old `AppShell`

### 门禁

1. 所有阶段任务必须带 `目标/输入/输出/验收/回退`。
2. 所有兼容层必须写明“保留原因”和“下线条件”。
3. 新增文档必须进入 `development/latest-dev-docs` 索引。

### 验收

1. 收口对象清单明确。
2. 兼容面清单明确。
3. 后续阶段不再出现“讨论的是 A，落地成 B”的口径漂移。

## 阶段 1

### 名称

Close runtime foundations first.

### 目标

优先收掉真正影响平台真实性的底座缺口。

### 范围

1. workflow graph durability
2. agent session runtime canonical path
3. project isolation hardening
4. LLM capability truthfulness

### 最小动作

1. 为 `workflow graph` 增加 compiled artifact store / registry，并定义 compile、load、run、resume 的标识语义；现有 run store / handoff store 继续作为 run-event 与 handoff 的持久化底座，而不是被重复实现。
2. 将 agent 主执行链收敛到 session/task/event/accounting 核心，现有 `agent_batch`、`skill_runtime`、`workflow_graph` 保留 adapter 入口。
3. 将 `project_key` enforcement 至少在非开发环境切到 `require`，并保留清晰 fallback telemetry。
4. 将“真实 LLM 路径”与“模板/规则 fallback 路径”在命名、返回字段、文档里拆开。

### 必须保持不变

1. 现有 API envelope 基本结构。
2. 兼容入口短期可调用性。
3. 与外部调用方约定的主要 URL / endpoint 面。

### 门禁

1. 至少新增一组 compile -> persist -> reload -> run 的真实测试。
2. 至少新增一组 session/task/event 主核 smoke。
3. `project_key` require 路径必须有 integration 级验证。
4. API 层静态边界检查继续通过：
   - [check_api_layer_imports.py](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/main/backend/scripts/check_api_layer_imports.py)

### 验收

1. workflow graph 不再依赖单进程 `_compiled` 生存。
2. agent runtime 的 canonical path 可以被明确画出，不再依赖“兼容入口即事实入口”。
3. `project_key` 硬隔离可以在目标环境打开。
4. 文档不再误把 fallback 能力当作已完成 LLM 能力。

## 阶段 2

### 名称

Converge compatibility layers without breaking callers.

### 目标

在不打断现有链路的前提下，收紧 source-library / ingest 的权威 contract。

### 范围

1. source-library adapter output
2. ingest frontdoor shared handoff
3. compatibility fields lifecycle

### 最小动作

1. 维持 `legacy_result` 等兼容输出，但明确标出“权威输出字段”。
2. 继续以 `ingress_envelope -> frontdoor` 作为共享 handoff。
3. 为 `legacy_result`、旧 batch override、legacy per-URL routing 写下线前提，而不是无限期保留。
4. 将 source-library / ingest 当前保留 contract 和 smoke 包写成统一 closure note。

### 必须保持不变

1. 当前保留的兼容字段不无声消失。
2. 现有 frontdoor writer 链不被重写。
3. observability 不退化。

### 门禁

1. 至少保留现有 source-library 最小回归包。
2. 对权威输出字段新增 contract 测试。
3. 对兼容字段新增 deprecation note 或状态标记。

### 验收

1. 调用方能区分“权威输出”和“兼容输出”。
2. source-library 收口后仍可回退。
3. 兼容面不再作为默认语义中心。

## 阶段 3

### 名称

Unify frontend facts and compatibility routing.

### 目标

将 frontend 从“新旧共存的双中心”收敛到“kernel 为主、compatibility adapter 下沉、render/shell ownership 单一”。

### 范围

1. `FrontendKernelApp`
2. `ModuleRenderer`
3. `AppShell`
4. legacy hash routing
5. layer shell completeness

### 最小动作

1. 明确哪一处是 render ownership / shell dispatch 的唯一事实源，并保持模块 metadata 继续从 manifest 派生。
2. 将 unknown route fallback 和 legacy hash 兼容收敛为 adapter 层，而不是继续放大 `AppShell`。
3. 补 B 层 visualization shell 或等价容器，结束 A/C 有 shell、B 层悬空的状态。
4. 把页面重型副作用继续下沉到 container / service boundary，而不是继续堆 page 文件。

### 必须保持不变

1. 现有页面可访问性。
2. 旧 hash 的基本兼容性。
3. 前端项目切换和核心工作台可用性。

### 门禁

1. 新旧路由映射必须有清单。
2. 至少有一组 frontend smoke 或最小 Storybook / integration 证据。
3. 关键选择器逐步摆脱纯文案耦合，降低 flaky 风险。

### 验收

1. 页面渲染与 shell dispatch 只剩一处权威入口。
2. `AppShell` 不再承担双份分发职责。
3. B 层容器语义完整。

## 阶段 4

### 名称

Turn validation and release governance into default gates.

### 目标

把“收口文档里写着要验证”变成“默认必须执行并留下证据”。

### 范围

1. required checks
2. PR evidence
3. smoke / regression visibility
4. docs navigation maintenance

### 最小动作

1. 对齐 required checks 与实际工作流：
   - [branch-protection-required-checks.json](/Users/wangyiliang/market-research-workflow-parallel-20260303-215619/.github/branch-protection-required-checks.json)
2. PR 必须填写：
   - scope
   - risk
   - test evidence
   - rollback
3. 将最关键的 runtime、frontend、source-library smoke 固化成可重复执行命令。
4. 每次阶段性收口完成后，更新 `CURRENT_DEV` 主题索引和顶层导航。

### 门禁

1. 无测试证据的 PR 不视为收口完成。
2. 无 rollback 描述的结构改动不视为可合并。
3. 无索引更新的文档新增不视为文档闭环。

### 验收

1. Required checks 与 repo 实际门禁一致。
2. PR 模板中的四块信息成为常态，而非形式项。
3. 关键收口主题有固定 smoke 包和固定文档入口。

## 阶段 5

### 名称

Archive only after closure evidence is complete.

### 目标

定义 `CURRENT_DEV -> ARCHIVE_CLOSED` 的真正退出标准。

### 退出标准

一个主题只有同时满足下面条件，才允许归档：

1. 权威 runtime / contract 已明确。
2. 兼容层状态已标注：
   - retained
   - deprecated
   - removed
3. 最小自动化验证包已固定并跑通。
4. 文档索引和 closure note 已完成。
5. 回退路径已明确，且 owner 清晰。

## 6. 推荐执行顺序

按当前最新方向，推荐顺序如下：

1. 先做阶段 0，冻结口径和兼容清单。
2. 再做阶段 1，优先补 runtime foundations。
3. 然后做阶段 2，收 source-library / ingest 的权威 contract。
4. 再做阶段 3，统一 frontend 事实源。
5. 最后做阶段 4，把验证和发布治理变成默认门禁。
6. 满足退出标准后再做阶段 5 归档。

这个顺序与最近文档和对话共识一致，因为：

1. 不先补 runtime 底座，后续功能都只是叠在不稳的抽象上。
2. 不先冻结 compat inventory，迁移会不断丢失真实边界。
3. 不把验证改成默认门禁，收口计划会继续停留在文档层。

## 7. 本轮非目标

本轮明确不做以下事情：

1. 不一次性删除所有兼容层。
2. 不一口气重写 source-library、ingest、frontend 全链。
3. 不把所有研究专题都并入单一 mega-plan。
4. 不在没有回退开关的情况下切默认行为。

## 8. 一句话收口策略

本仓库下一阶段最合理的收口策略不是“继续铺新能力”，而是：

“以 runtime 真实性、兼容层清单、单一事实源和 fail-closed 验证门禁为主线，把已经进入主链的平台化术语真正补成平台化闭环。”
