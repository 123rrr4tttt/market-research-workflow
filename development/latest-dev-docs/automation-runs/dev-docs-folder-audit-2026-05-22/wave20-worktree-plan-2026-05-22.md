# Wave20 Worktree Plan And Integration Status

日期：2026-05-22（PST）

## 当前状态重判

| 状态 | 数量 | 本轮处理策略 |
|---|---:|---|
| `partial` | 33 | 继续把仓内还能验证的计划切片落到代码、脚本、测试与主题证据文档；若仍保留为 `partial`，必须写清剩余 live / 外部 / 生产条件。 |
| `not_closed` | 0 | 暂无单独 `not_closed` 入口；不得为了制造进度而重开已归并状态。 |
| `no_closure_claim` | 0 | 暂无单独 `no_closure_claim` 入口；若发现新无主文档，必须先补 topic-local 证据与 blocker。 |

Wave20 继续处理 Wave19 后仍能仓内推进的边界：time semantics deterministic provenance、OpenClaw mirror handoff、graph editing audit conflict、long-cycle scheduler queue、agent-batch quality promotion、document-query endpoint slice、consumer facade slice、source-library review batch、frontend i18n next page slice、docs-root content move。真实 production data、外部 OpenClaw runtime、live tenant DB、live scheduler、live provider quality、live DB/API smoke、public replay、human review 和全量迁移不在本轮伪封口。

## 共享索引边界

Worker 分支不得直接修改下列共享索引；这些文件由集成分支在合并后统一同步：

- `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/STATUS_AUDIT_2026-04-07.md`
- `development/latest-dev-docs/development-plans/INDEX.md`
- `development/latest-dev-docs/README.md`
- `development/latest-dev-docs/MERGED_OVERVIEW.md`

Worker 分支也不得修改当前主工作树已有脏项：

- `main/backend/scripts/workflow_graph_smoke_local.py`
- `development/latest-dev-docs/automation-runs/branch-hygiene-2026-05-15.md`

## 10 个并行工作树任务

| # | 分支 | 目标 | 输入 | 输出 | 验收 |
|---:|---|---|---|---|---|
| 1 | `codex/devdocs-wave20-time-semantics-readback` | 推进 source-time-window / time-statistics / time-semantics 的 production data 前置边界，补 deterministic sample/provenance readback。 | 三个 time semantics CURRENT_DEV topic、现有 freshness / decision-log evidence。 | checker/test、automation-run evidence、三个 topic Wave20 文档。 | deterministic readback 通过；production data semantic chain 仍 open。 |
| 2 | `codex/devdocs-wave20-openclaw-mirror-readback` | 推进 R41 OpenClaw autodispatch，补 repo-local mirror/runtime handoff manifest readback。 | R41 topic、OpenClaw mirror / handoff 代码或证据。 | checker/test、automation-run evidence、topic Wave20 文档。 | local mirror 可回读；external OpenClaw runtime 仍 unverified。 |
| 3 | `codex/devdocs-wave20-graph-editing-audit-conflict` | 推进 graph editing/reporting 的 audit conflict / rollback readback。 | graph editing topic、graph handoff evidence、audit/rollback code。 | checker/test、automation-run evidence、topic Wave20 文档。 | repo-local audit conflict/rollback gate 通过；live tenant DB audit durability 仍 open。 |
| 4 | `codex/devdocs-wave20-long-cycle-scheduler-queue` | 推进 long-cycle automation 的 scheduler queue handoff + durable repository replay。 | long-cycle topic、Wave16 durable repo readback、Wave18 scheduler handoff trace。 | checker/test、automation-run evidence、topic Wave20 文档。 | scheduler queue fixture 通过；live scheduler / live DB write 仍 open。 |
| 5 | `codex/devdocs-wave20-agent-batch-quality-promotion` | 推进 agent symbolic batch search 的 provider-independent quality promotion/readback。 | agent batch topic、brief/critic/retry/quality threshold code。 | checker/test、automation-run evidence、topic Wave20 文档。 | fixture quality promotion gate 通过；live provider quality 仍 open。 |
| 6 | `codex/devdocs-wave20-document-query-endpoint-slice` | 推进 data structured service modularization 的 document_queries endpoint slice。 | data structured topic、document_queries 与 search endpoint code。 | 低风险 endpoint/query slice、test、evidence。 | 选中 slice 通过；更多 endpoint / DB builder 仍 open。 |
| 7 | `codex/devdocs-wave20-consumer-facade-slice` | 推进 consumer-side modularization 的 facade/query boundary slice。 | consumer-side topic、consumer_predicates / graph / writing / admin consumers。 | facade/checker/test 或 consumer predicate slice、evidence。 | 选中 consumer boundary 通过；live DB/API smoke 仍 open。 |
| 8 | `codex/devdocs-wave20-source-library-review-batch4` | 推进 source-library deterministic review closure batch 4。 | source-library 三车道、mounting、adapter、minimal migration topics。 | batch4 fixture/checker/test、四个 topic evidence。 | batch4 可机检；human review / public replay 仍 open。 |
| 9 | `codex/devdocs-wave20-frontend-i18n-next-slice` | 推进 frontend i18n/theme/three-layer 的下一页面切片。 | dual frontend、i18n/theme、three-layer topics、frontend catalog。 | frontend code/catalog/check script、三个 topic evidence。 | page i18n slice checker 通过；全量 page refactor 仍 open。 |
| 10 | `codex/devdocs-wave20-docs-root-content-move-batch5` | 推进 docs-root content move batch 5，继续降低 unsafe moves。 | docs-root topic、entry manifest、content plan checker。 | moved content/shims/manifest/content-plan/topic evidence。 | docs-root gates 通过；unsafe moves 下降或 no-op 原因明确。 |

## 集成策略

1. 每个 worker 只改自己的代码面、测试、topic evidence 文档，避免触碰共享索引。
2. 集成分支按低冲突顺序合并：repo-local checker/test、frontend slice、docs-root move，最后同步 shared indexes。
3. 合并后由 supervisor 统一更新 `CURRENT_DEV/INDEX.md`、`STATUS_AUDIT_2026-04-07.md`、`development-plans/INDEX.md`、`README.md`、`MERGED_OVERVIEW.md`，必要时新增 `wave20_verified` / `wave20_checked` 标签说明。
4. 最小门禁：Wave20 plan gate、CURRENT_DEV status evidence、latest-dev-docs touched-file link gate、每个 worker 的 checker/test、`git diff --check`。

## 集成结果

待 worker 分支完成后更新。若某个 worker 没有安全代码改动，必须记录 no-op 原因、关闭 agent，并由 supervisor 判断是否纳入索引。
