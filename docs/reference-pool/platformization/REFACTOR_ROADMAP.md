# Refactor Roadmap (Platformization)

目标：在不一次性推翻现有业务逻辑的前提下，把关键链路升级为“可复用、可观测、可治理”的平台能力。

决策入口：[`PLATFORMIZATION_CONVERGED.md`](./PLATFORMIZATION_CONVERGED.md)

## Phase 0: 基线冻结（1-2 周）

1. 冻结现有接口与核心 IO 行为（search/ingest/crawler/config/process）。
2. 补齐最小观测基线（P95、错误率、任务成功率、队列积压）。
3. 对 7 条链路建立 smoke 用例，作为迁移后回归集。

交付：
- 兼容基线报告
- 基线指标看板

## Phase 1: 低侵入平台化（2-4 周）

1. Search 链路先做 Shadow Read（不切流量，仅对比结果）。
2. Ingest 链路先把“调度/重试/重放”抽到 workflow 层（可先保留现有执行器）。
3. Contracts 治理先上 CI 非阻断门禁（schema lint、openapi diff、pact verify）。

交付：
- 双读对比报告（召回、P95、成本）
- 新编排链路 PoC 跑通

## Phase 2: 中侵入替换（4-8 周）

1. 多租户与配置平台化（身份/权限/密钥外置），下线关键明文配置路径。
2. Crawler/Source runtime 引入 artifact/run/lineage 统一模型。
3. Frontend 采用页面级绞杀：legacy 路由逐页迁移到 modern 子应用。

交付：
- 权限与配置目标架构落地
- crawler runbook 与回滚机制
- legacy 页面迁移批次清单

## Phase 3: 平台收敛（持续）

1. Observability 完整化：metrics + traces + logs 三栈贯通。
2. 发布回滚升级为 progressive delivery（canary + 自动回滚阈值）。
3. 门禁从“建议”转为“required checks”。

交付：
- 平台 SLO/告警规则集
- 发布策略模板（蓝绿/金丝雀）

## 优先级建议（按收益/风险比）

1. Search/Index（最快看到性能与稳定性收益）
2. Ingest/Workflow（降低任务失败与补偿成本）
3. Contracts/Governance（减少重构破坏面）
4. Observability/Ops（放大运维效率）
5. Multi-tenant/Config（架构收益高但改造面大）
6. Crawler/Source（可与数据采集业务节奏同步推进）
7. Frontend（按页面业务价值滚动迁移）

## 入口

- 参考池总索引：[`README.md`](./README.md)
- 链路文档：`chains/*.md`
- 开源快照：`snapshots/*`
