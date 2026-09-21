# 当前平台化差距复核（2026-05-26）

> 口径：本复核只使用当前 `development/latest-dev-docs` 入口、`CURRENT_DEV` 状态、external-blocker manifest 与最近 automation evidence。`docs/reference-pool/platformization/*` 仅作为历史参考，不再作为当前平台化差距判断依据。

## 结论

当前项目已经不是“脚本集合”或“单链路工作流”。按当前仓库证据，它已经进入准平台阶段：业务链路、API/worker/DB/前端、source library、local index、AgentCore、graph/workflow、report/writing 与自动化证据大多有仓内闭环。

距离规模化平台化的主要差距不在于缺少某个数据库、中间件或旧路线图里的平台组件，而在于：

1. 生产/准生产连续运行证据仍不完整。
2. external/live blocker 仍需要外部服务、合法 session、生产指标或 ops approval。
3. 控制面、租户/权限/secret、SLO、容量、告警、审计和回滚演练还没有形成统一的平台治理层。
4. 数据质量、检索质量和 source-library executability 需要从 deterministic gate 推进到长期样本、人工反馈和线上质量闭环。

## 当前状态基线

| 维度 | 当前事实 | 平台化含义 |
|---|---|---|
| `CURRENT_DEV` | [`partial:0 / not_closed:0 / no_closure_claim:0`](../CURRENT_DEV/INDEX.md) | 仓内开发入口已收敛，不应再用历史 `partial` wave 计数判断当前未完成量。 |
| target topics | [`closed:45 / external_blocked:4 / retired:6 / active_current:0`](../../MERGED_OVERVIEW.md) | 大部分目标主题已经闭合；剩余项是外部依赖或生产证据，不是普通开发待办。 |
| four-state review | `unsealed:0 / sealed:49 / outdated:6 / needs_update:0` | 结构化文档审计已基本收敛，但仍需避免把 outdated 历史文档当成现状。 |
| external blocker | [manifest 只保留 4 个 target](../EXTERNAL_BLOCKER_MANIFEST.v1.json) | 当前平台化差距应围绕这 4 个真实外部条件，而不是围绕旧方案重启大改造。 |
| automation evidence | user-flow、worker readback、capacity baseline、token-retention 等 lane 已进入 `automation-runs` | 已具备运行证据框架；下一步是生产 SLO 化和 ops-owned promotion。 |

## 平台化定义

本文中的平台化指：把当前市场研究工作流变成可托管、可配置、可观测、可治理、可扩展、可交接的运行底座。

不把以下事项单独等同于平台化：

- 换成某个新数据库或向量库。
- 强行迁移到 Temporal、Kafka、Kubernetes、Keycloak 等组件。
- 只增加一批文档、closure 文件或 replay artifact。
- 单次本地 smoke 通过。

一个能力只有同时满足以下条件，才算进入平台化口径：

1. 有稳定 API/contract/envelope。
2. 有租户/项目/权限/配置边界。
3. 有运行状态、失败原因、重试、回滚和审计。
4. 有质量指标和容量基线。
5. 有可复跑的自动化证据。
6. 有生产或准生产环境下的 owner surface。

## 成熟度判断

| 层级 | 当前估计 | 判断 |
|---|---:|---|
| 仓库内工程闭环 | 75-85% | 多数链路已经有代码、契约、测试或 automation evidence。 |
| 准平台能力 | 60-70% | 能承载多链路运行和复核，但平台控制面仍分散。 |
| 生产级平台化 | 55-65% | 最大缺口是 24h 指标、ops promotion、SLO/alert、容量和事故处理证据。 |
| 企业级平台治理 | 45-55% | tenant/secret/policy/audit/release governance 还没有统一成产品化控制层。 |

## 剩余核心差距

### 1. 生产证据与 ops promotion

`Meaningful Ingest Guardrails` 已有 repo-local API/DB canary handoff、strict-promotion readiness 与 final closure input gate，但仍缺生产 24h guardrail metrics 和 ops-owned strict-gate promotion approval。

证据入口：

- [Meaningful Ingest Guardrails external blocker](../ARCHIVE_EXTERNAL_BLOCKED/2026-03-02-meaningful-ingest-guardrails-plan/13_wave56-strict-promotion-final-gate-2026-05-24.md)
- [External blocker manifest](../EXTERNAL_BLOCKER_MANIFEST.v1.json)

### 2. 单 URL 首采与外部 provider 约束

`Single URL First Ingest Allocation` 已覆盖 Instagram/YouTube public replay、configured canary、Crossref public official API provider maturity 和 configured-only credential presence。未封口项仍是 X auth/anti-bot、production 24h readback、ops promotion、Crossref 之外的 provider-specific live quota validation。

证据入口：

- [Single URL external blocker closure](../ARCHIVE_EXTERNAL_BLOCKED/2026-03-02-single-url-first-ingest-allocation-plan/13_wave57-single-url-external-blocker-closure-2026-05-24.md)

### 3. LLM crawler 高 JS / session-aware 公网回放

`LLM Crawler Unified FrontDoor` 已有 five public replay shards、accessible high-JS public replay，以及 Instagram/YouTube session-aware replay。X 仍因 auth/anti-bot 与 lawful session 条件保持 external-blocked。

证据入口：

- [LLM crawler session-aware high-JS replay boundary](../ARCHIVE_EXTERNAL_BLOCKED/2026-03-08-llm-crawler-unified-frontdoor/13_wave56-session-aware-high-js-replay-boundary-2026-05-23.md)

### 4. 时间语义的生产语义链

`Time Semantics Density Merged Plan` 已有 repo-local release gate、source-time distribution、decision-log readback 和 configured production-like DB evidence。未封口项是 strict production/live semantic-chain evidence、production source-time coverage 和 feedback reward alignment。

证据入口：

- [Time semantics configured live semantic-chain evidence](../ARCHIVE_EXTERNAL_BLOCKED/2026-03-14-time-semantics-density-merged-plan/13_wave56-configured-live-semantic-chain-evidence-2026-05-24.md)

### 5. 控制面仍分散

当前能力分布在 FastAPI、Celery/worker、SQLAlchemy、Docker scripts、frontend-modern、automation-runs、check scripts 和 devdocs evidence 里。它们可以证明链路，但还不是统一控制面。

平台化控制面至少应覆盖：

- project / tenant / source / task / report / workflow / graph 的统一状态视图。
- 运行状态、失败原因、重试、回滚、人工接管。
- secret/config/policy 的变更审计。
- automation evidence 与生产 SLO 的统一读取。
- 每条业务线的 readiness、capacity、quality、cost 和 owner。

### 6. 数据与检索质量需要长期闭环

Source-library、local index、vector retrieval、open-search provider、public replay 已有大量 repo-local 或 live readback evidence，但平台化质量不应只看单次 closure。需要继续把 ranking、executability、semantic quality、source freshness、provider drift 与人工 review 变成长期指标。

证据入口：

- [Business-line user-flow audit](../../automation-runs/business-line-user-flow-audit/2026-05-23/README.md)
- [Business-line worker readback matrix](../../automation-runs/business-line-worker-readback-project-matrix/README.md)
- [Performance / capacity baseline](../../automation-runs/performance-capacity-baseline/2026-05-24/README.md)

## 不建议重启的方向

1. 不建议把 2026-03 的 platformization reference pool 当成当前任务板。
2. 不建议先做大规模中间件替换；当前更需要把现有链路治理化。
3. 不建议用“新增 closure 文档”替代生产证据。
4. 不建议为了降低 blocker 数量而把 external condition 改写成 repo-local condition。
5. 不建议把 source-library 的最终 source_mode / handler 选择前移到 agent_batch；该边界应保持清晰。

## 推荐推进顺序

1. **先固化平台化口径**：把本文作为当前差距入口，旧 reference-pool 文档只保留历史含义。
2. **封住 4 个 external blocker 的证据形态**：每个 blocker 只接受 manifest 指定的 external proof，不接受新的文字性 closure。
3. **把 automation-runs 提升为运行台账**：worker readback、capacity baseline、business-line user flow、token retention 等 lane 统一成可查询的 current health surface。
4. **补控制面最小闭环**：先做只读 dashboard，展示 project/task/source/report/workflow 的状态、失败、owner、evidence、SLO。
5. **再补 tenant/secret/policy**：把项目隔离、凭证注入、策略授权、审计日志作为平台治理层推进。
6. **最后考虑中间件替换**：只有当现有 Celery/SQLAlchemy/Docker/script 组合在容量、可恢复性或调度语义上成为实证瓶颈时，再做替换。

## 验收标准

下一次更新本文或关闭平台化差距时，必须同时满足：

- `CURRENT_DEV` 仍为 `partial:0 / not_closed:0 / no_closure_claim:0`。
- `EXTERNAL_BLOCKER_MANIFEST.v1.json` 中的每个剩余 target 都有明确 state 变化。
- 新增 closure 不只写文档，必须链接 run artifact、probe output、manual readback 或 production owner approval。
- 业务线 automation evidence 能回答：谁在跑、跑了什么、失败在哪里、是否可重试、是否影响交付。
- 平台控制面至少能只读展示核心运行状态，而不是要求维护者逐个打开 markdown / JSON / log。

