# Wave16 Worktree Plan And Integration Status

日期：2026-05-22（PST）

## 当前状态审计

| 状态 | 数量 | 本轮处理策略 |
|---|---:|---|
| `partial` | 34 | 主动推进仓内开发、门禁、文档闭合和必要归档；若仍保留为 `partial`，必须写清剩余 live / 外部 / 生产条件。 |
| `not_closed` | 0 | 暂无单独 `not_closed` 入口。 |
| `no_closure_claim` | 0 | 暂无单独 `no_closure_claim` 入口。 |

重点风险标签：`doc_drift`、`external_gap`、`external_blocked`、`live DB/API/UI gap`、`public replay gap`、`production data gap`、`archive candidate`、`active development`。Wave16 的默认方向是落地代码和闭合证据；只有仓内事实、测试和索引都闭合时才迁档，外部条件仍未满足的目录保留为 `partial` 并写明阻塞。

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
| 1 | `codex/devdocs-wave16-parallel-runtime-closure` | 闭合 Parallel Agent Wave Orchestration 的仓内运行时边界，记录本轮父 runtime 已暴露 `multi_agent_v1.spawn_agent`；若 worker runtime 仍依赖外部环境，则拆成 successor 而不是继续泛化 partial。 | Wave7/Wave10 runtime 文档、Wave16 实际 spawn evidence、parallel-agent runtime 约定。 | topic-local Wave16 closure / successor evidence、最小 checker 或状态证据。 | 能证明仓内 runtime 入口封住；若迁档候选成立，标记 `archive candidate`。 |
| 2 | `codex/devdocs-wave16-clue-chain-closure-split` | 主动拆分 Clue Chain Investigation Tool 的已落地实现与剩余 live-provider / UI / conflict 项，减少“新项目一直 partial”。 | Wave5 Clue Chain 实现证据、后端 / 前端 clue-chain 代码、现有 INDEX。 | Wave16 closure split 文档、可运行的 conflict 或 API contract 小测试。 | 已落地功能有明确闭合面；剩余项转为 successor plan 或保留具体阻塞。 |
| 3 | `codex/devdocs-wave16-graph-editing-ui-audit-controls` | 推进 Graph Editing And Reporting 的 audit readback / rollback 控制面，补 API 或前端可测入口，不依赖 dirty smoke 脚本。 | Wave11/Wave12/Wave15 graph audit 证据、graph editing service/API/UI。 | audit controls code/test、Wave16 证据。 | 测试通过；不修改 `main/backend/scripts/workflow_graph_smoke_local.py`。 |
| 4 | `codex/devdocs-wave16-typed-knowledge-api-route` | 推进 Typed Knowledge Organization 的 API / route 边界，补公开契约或可测试 service route。 | Wave10/Wave12/Wave15 typed-knowledge evidence、backend typed knowledge services。 | API route / contract test、Wave16 证据。 | 仓内 API contract 有测试；live DB 条件若未满足，明确为剩余边界。 |
| 5 | `codex/devdocs-wave16-writing-workbench-typed-fetch` | 推进 Writing Workbench 的 typed-knowledge fetch / card readback，连接 consumer surface 与 typed knowledge contract。 | Writing Workbench evidence、typed knowledge API、frontend/backend writing code。 | fetch/readback code 或 deterministic contract test、Wave16 证据。 | 仓内 consumer fetch/readback 可测；live UI 条件不误封。 |
| 6 | `codex/devdocs-wave16-long-cycle-live-repository-readback` | 将 Ingest Digestion And Long-Cycle Automation 从 fake repository E2E 推向 durable repository readback / event contract。 | Wave11 fake repository E2E、Wave13 scheduler readiness、persistent task code。 | durable readback checker/test、Wave16 证据。 | 仓内 durable contract 可测；live scheduler/live DB 仍按事实保留。 |
| 7 | `codex/devdocs-wave16-docs-root-content-move-batch` | 对 Docs Root Restructuring 执行一个真实 content move / navigation batch，降低 broad content move 的剩余范围。 | Wave9 manifest、Wave11 navigation promotion、Wave12 content-plan gate。 | 小批量内容迁移、链接修复、Wave16 证据。 | latest-dev-docs link gate 通过；迁移批次可追踪。 |
| 8 | `codex/devdocs-wave16-frontend-business-string-migration` | 对 Dual Frontend / I18N Theme / Three-Layer Rewrite 做一个具体业务字符串或页面切片迁移，而不是只保留 audit。 | Wave12 business-string audit、Wave14 migration boundary、frontend code。 | i18n/theme/page slice code/test、Wave16 证据。 | 相关 frontend check 通过；完整页面迁移剩余范围具体化。 |
| 9 | `codex/devdocs-wave16-source-library-review-closure-batch` | 推进 Source-Library 三线、Search Chain、Adapter Capability 的 review/taxonomy batch，闭合一个确定性 review 批次。 | Wave12 review queue、Wave14 taxonomy readiness、source-library scripts/fixtures。 | review batch artifact、checker/test、Wave16 证据。 | 批次可机检；人工或公网 replay 缺口不误封。 |

## 集成策略

1. 每个 worker 只改自己的代码面、测试、主题证据文档，避免触碰共享索引。
2. 集成分支优先合并可闭合 / 可归档项：parallel runtime、clue-chain split、docs-root batch，再合并代码开发项。
3. 合并后由 supervisor 统一更新 `CURRENT_DEV/INDEX.md`、`STATUS_AUDIT_2026-04-07.md`、`development-plans/INDEX.md`、`README.md`、`MERGED_OVERVIEW.md`，并移动确证封口的目录到 `ARCHIVE_CLOSED`。
4. 最小门禁：Wave16 plan gate、CURRENT_DEV status evidence、latest-dev-docs link gate、每个 worker 的 checker/test、`git diff --check`。
