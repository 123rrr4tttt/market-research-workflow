# Wave14 Worktree Plan And Integration Status

日期：2026-05-22（PST）

## 当前状态审计

| 状态 | 数量 | 本轮处理策略 |
|---|---:|---|
| `partial` | 35 | 继续逐目录推进，优先落仓内代码、契约、门禁和证据，不把外部依赖误判为封口。 |
| `not_closed` | 0 | 暂无单独 `not_closed` 入口。 |
| `no_closure_claim` | 0 | 暂无单独 `no_closure_claim` 入口。 |

重点风险标签：`doc_stale`、`doc_drift`、`external_gap`、`external_blocked`、`live runtime gap`。Wave14 不直接迁档；只有在当前代码事实和门禁能证明闭环时，才允许后续集成阶段调整状态。

## 共享索引边界

Worker 分支不得直接修改下列共享索引；这些文件由集成分支在合并后统一同步：

- `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/STATUS_AUDIT_2026-04-07.md`
- `development/latest-dev-docs/development-plans/INDEX.md`
- `development/latest-dev-docs/README.md`
- `development/latest-dev-docs/MERGED_OVERVIEW.md`

## 9 个并行工作树任务

| # | 分支 | 目标 | 输入 | 输出 | 验收 |
|---:|---|---|---|---|---|
| 1 | `codex/devdocs-wave14-vectorization-provider-capability` | 推进 open-source/global/OSS vectorization 的 provider capability 判定，明确本地可验证能力与外部 provider 缺口。 | Wave12 provider readiness、`main/backend/app/services/search/*`、vector tests。 | 新增或增强 vectorization capability checker、单测、CURRENT_DEV 主题证据。 | checker 通过；相关 vector/search 单测通过；不声称 live provider 封口。 |
| 2 | `codex/devdocs-wave14-graph-visual-data-smoke` | 回补 Graph 3D Force Engine 的 `doc_drift`：用仓内数据/fixture 证明可视化数据 smoke 边界。 | Graph projection/live-smoke readiness、workflow graph/graph API。 | 图数据 smoke gate、单测、Graph 3D Wave14 证据。 | gate 能区分 fixture smoke 与真实 backend-data visual smoke；测试通过。 |
| 3 | `codex/devdocs-wave14-graph-node-live-db-readiness` | 推进 Graph Node Standardization 的 live DB rollout 边界，避免把 dry-run 当 live closure。 | graph node reader/writer/backfill/readiness 文件。 | live DB rollout readiness checker、单测、Graph Node Wave14 证据。 | checker 通过；明确 live DB 未验证或已验证证据。 |
| 4 | `codex/devdocs-wave14-ingest-canary-metrics` | 推进 ingest / meaningful ingest / single-url canary 的 24h metrics 与 demo_proj live-canary 边界。 | canary handoff、guardrail rollout、ingest metrics payload。 | canary metrics readiness gate、单测、对应 CURRENT_DEV 证据。 | gate 通过；保留 live demo/24h metrics 缺口，不误封口。 |
| 5 | `codex/devdocs-wave14-time-density-doc-refresh` | 回补 Time Statistics 的 `doc_stale`，把当前决策日志/时间密度证据与代码事实对齐。 | time-density Wave10/Wave12 证据、相关 scripts/services。 | stale-doc refresh gate 或 provenance checker、单测、Time Statistics Wave14 证据。 | checker 通过；文档改为当前状态说明。 |
| 6 | `codex/devdocs-wave14-source-library-taxonomy-review` | 推进 source-library 三线架构 / search mounting / adapter capability 的 taxonomy 与 human-review 队列边界。 | source_library relevance review、search governance、adapter capability。 | taxonomy/review readiness checker、单测、source-library Wave14 证据。 | checker 通过；区分 deterministic review queue 与已完成人工 review。 |
| 7 | `codex/devdocs-wave14-frontend-migration-boundary` | 推进 dual frontend / i18n theme / three-layer rewrite 的 full migration 边界，用静态 contract 覆盖剩余页面/业务字符串风险。 | frontend-modern、frontend topology/i18n/theme 证据、business-string audit。 | frontend migration boundary checker、必要测试、三主题 Wave14 证据。 | checker 或 lint 通过；不要求启动完整前端。 |
| 8 | `codex/devdocs-wave14-abstract-content-gaps` | 关闭 `后续安排` 下游 content gap 清单中的仓内文档结构缺口。 | `scripts/check_abstract_planning_folderization.py` 输出的 5 个 content gaps。 | 补齐缺失的 `module_boundary` / `scope_non_goals`、Wave14 证据。 | `python3 scripts/check_abstract_planning_folderization.py` 输出 `hard_failures=0` 且 `content_gaps=0`。 |
| 9 | `codex/devdocs-wave14-agentcore-tool-calling-quality` | 推进 AgentCore native tool-calling production-quality 边界，补 deterministic quality gate。 | agent_core provider readiness、platform contract、native/json providers。 | native tool-calling quality checker、单测、AgentCore Wave14 证据。 | checker 通过；真实外部 provider call 仍按 live gap 记录。 |

## 集成策略

1. 每个 worker 只改自己的代码面、测试、主题证据文档，避免触碰共享索引。
2. 集成分支按低冲突顺序合并：vector/search、graph、ingest/time、source-library/frontend、abstract、agentcore。
3. 合并后统一更新 `CURRENT_DEV/INDEX.md`、`STATUS_AUDIT_2026-04-07.md`、`development-plans/INDEX.md`、`README.md`、`MERGED_OVERVIEW.md` 和状态证据报告。
4. 最小门禁：Wave14 plan gate、CURRENT_DEV status evidence、latest-dev-docs link gate、每个 worker 的 checker/test、`git diff --check`。
