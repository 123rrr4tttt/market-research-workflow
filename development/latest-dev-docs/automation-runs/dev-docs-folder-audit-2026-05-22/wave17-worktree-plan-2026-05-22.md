# Wave17 Worktree Plan And Integration Status

日期：2026-05-22（PST）

## 当前状态审计

| 状态 | 数量 | 本轮处理策略 |
|---|---:|---|
| `partial` | 33 | 继续主动推进仓内开发、门禁、文档闭合和必要归档；若仍保留为 `partial`，必须写清剩余 live / 外部 / 生产条件。 |
| `not_closed` | 0 | 暂无单独 `not_closed` 入口。 |
| `no_closure_claim` | 0 | 暂无单独 `no_closure_claim` 入口。 |

重点风险标签：`doc_drift`、`external_gap`、`external_blocked`、`live DB/API/UI gap`、`public replay gap`、`production data gap`、`archive candidate`、`active development`。Wave17 的默认方向是继续落地代码和收口证据；外部公网、外部 OpenClaw、真实 provider 与生产租户条件不在本轮伪封口。

## 共享索引边界

Worker 分支不得直接修改下列共享索引；这些文件由集成分支在合并后统一同步：

- `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/STATUS_AUDIT_2026-04-07.md`
- `development/latest-dev-docs/development-plans/INDEX.md`
- `development/latest-dev-docs/README.md`
- `development/latest-dev-docs/MERGED_OVERVIEW.md`

Worker 分支也不得修改当前主工作树已有脏项：

- `main/backend/scripts/workflow_graph_smoke_local.py`

## 9 个并行工作树任务

| # | 分支 | 目标 | 输入 | 输出 | 验收 |
|---:|---|---|---|---|---|
| 1 | `codex/devdocs-wave17-source-time-production-sample-gate` | 推进 Source Time / Time Density 的生产语义链，从 deterministic contract 走到可重复的 sample readback gate。 | Wave10 source-time contract、Wave12 decision log、Wave15 production readiness、time statistics/current-state checker。 | backend checker/test 与 Wave17 evidence，证明 sample-level semantic-chain readback；生产数据仍未满足时保留边界。 | checker/test 通过；不声明真实生产闭环。 |
| 2 | `codex/devdocs-wave17-ingest-canary-metrics-readback` | 推进 ingest platformization / meaningful ingest / single-url 的 canary metrics readback，补 24h 指标的仓内可复现替代证据。 | Wave12 canary handoff、Wave14 metrics readiness、ingest/frontdoor services。 | canary metrics readback checker/test、三 topic evidence。 | 能读回 deterministic metrics snapshot；真实 live canary 仍按事实保留。 |
| 3 | `codex/devdocs-wave17-graph-visual-runtime-pixel-gate` | 推进 Graph 3D / graph visual live smoke，补非空渲染或数据投影的前端 runtime pixel/shape gate。 | Wave10 engine switch、Wave12 live-smoke readiness、Wave14 graph visual data smoke、GraphPage code。 | frontend e2e/checker 或 visual fixture gate、Wave17 evidence。 | frontend check 可跑；不依赖外部 GPU / 真实 tenant DB。 |
| 4 | `codex/devdocs-wave17-graph-node-rollout-readback` | 推进 Graph Node Standardization 的 rollout readback，从 dry-run/live-smoke readiness 到可复查 rollout manifest。 | Wave7 canonical id、Wave10 DB rollout readiness、Wave14 live DB rollout gate、graph node services。 | rollout manifest checker/test、Wave17 evidence。 | 仓内 rollout manifest 可机检；真实 tenant DB rollout 不误封。 |
| 5 | `codex/devdocs-wave17-typed-knowledge-durable-readback` | 推进 Typed Knowledge live DB/API/UI 边界，新增 durable repository 或 sqlite-like readback contract。 | Wave12 persistence boundary、Wave15 live boundary、Wave16 public API route contract。 | durable persistence adapter/checker/test、Wave17 evidence。 | API/service readback 可测；真实 production DB 仍保留为 live boundary。 |
| 6 | `codex/devdocs-wave17-writing-persisted-card-ui-readback` | 推进 Writing Workbench persisted typed cards 的 UI readback，补前端 consumer 对 persisted card 状态的可测路径。 | Wave16 typed fetch/readback、writing keyword-card service、WritingWorkbench UI。 | frontend/backend test 或 checker、Wave17 evidence。 | persisted-card consumer 路径可测；live persisted UI 仍不误封。 |
| 7 | `codex/devdocs-wave17-frontend-page-i18n-slice` | 继续 Dual Frontend / I18N Theme / Three-Layer 的页面级业务字符串迁移，选取非 Agent Chat 的第二个页面切片。 | Wave12 business-string audit、Wave14 migration boundary、Wave16 Agent Chat slice、frontend catalog/pages。 | i18n catalog/page code、checker更新、三 topic evidence。 | frontend check/lint 通过；全量页面迁移剩余范围具体化。 |
| 8 | `codex/devdocs-wave17-structured-consumer-query-boundary` | 推进 Data Structured Service 与 Consumer-Side Modularization 的非 admin/dashboard query boundary，继续迁移 DB statement builder / consumer predicate。 | Wave15 SQL/helper migration、consumer predicate facade、document query services。 | backend helper/facade code/test、两个 topic evidence。 | focused pytest 通过；live DB/API smoke 仍按事实保留。 |
| 9 | `codex/devdocs-wave17-docs-root-content-move-batch2` | 对 Docs Root Restructuring 执行第二个真实 content move / navigation batch，继续降低 broad content move 的剩余范围。 | Wave16 first content move batch、migration manifest、content-plan checker。 | 小批量内容迁移、manifest更新、Wave17 evidence。 | latest-dev-docs link gate 与 docs-root checkers 通过。 |

## 集成策略

1. 每个 worker 只改自己的代码面、测试、主题证据文档，避免触碰共享索引。
2. 集成分支优先合并低冲突契约项：source-time、graph-node、typed/writing，再合并前端和 docs-root 批次。
3. 合并后由 supervisor 统一更新 `CURRENT_DEV/INDEX.md`、`STATUS_AUDIT_2026-04-07.md`、`development-plans/INDEX.md`、`README.md`、`MERGED_OVERVIEW.md`，必要时新增 `wave17_verified` / `wave17_checked` 标签说明。
4. 最小门禁：Wave17 plan gate、CURRENT_DEV status evidence、latest-dev-docs link gate、每个 worker 的 checker/test、`git diff --check`。
