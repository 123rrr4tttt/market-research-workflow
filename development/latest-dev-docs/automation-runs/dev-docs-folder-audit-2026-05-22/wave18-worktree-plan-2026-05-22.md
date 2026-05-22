# Wave18 Worktree Plan And Integration Status

日期：2026-05-22（PST）

## 当前状态审计

| 状态 | 数量 | 本轮处理策略 |
|---|---:|---|
| `partial` | 33 | 继续主动推进仓内开发、门禁、文档闭合和必要归档；若仍保留为 `partial`，必须写清剩余 live / 外部 / 生产条件。 |
| `not_closed` | 0 | 暂无单独 `not_closed` 入口。 |
| `no_closure_claim` | 0 | 暂无单独 `no_closure_claim` 入口。 |

Wave18 重点处理尚未在 Wave17 触达或仍有明确仓内下一步的目录：vectorization/open-search、LLM crawler、symbolic search、long-cycle scheduler、graph editing audit、AgentCore provider boundary、source-library review batch、frontend i18n slice、docs-root content move，以及 `CURRENT_DEV/MERGED_OVERVIEW` drift。外部公网、真实 provider、生产租户 DB/API/UI 与人工 review 不在本轮伪封口。

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
| 1 | `codex/devdocs-wave18-vectorization-hybrid-readback` | 推进 open-source / global vectorization / OSS node 的 local hybrid readback，补 deterministic keyword/vector/hybrid identity 与 quality trace。 | Wave8 search/vector contract、Wave10 quality gate、Wave12/14 provider gates、local_index/search services。 | 后端 checker/test 与三 topic evidence；真实 embedding/provider 质量仍保留边界。 | checker/test 通过；不声明 live provider closure。 |
| 2 | `codex/devdocs-wave18-open-search-health-artifact` | 推进 SearXNG / YaCy 隔离 provider 的本地健康 artifact，区分 compose config 可审计、service not started、真实 live probe。 | Wave12 provider readiness、Wave15 runtime boundary、launcher/docker compose/search provider code。 | health artifact checker/test 与 topic evidence。 | 能机检当前服务状态；未启动服务仍明确 external_blocked。 |
| 3 | `codex/devdocs-wave18-llm-crawler-replay-fixture` | 推进 LLM Crawler high-JS/public replay，补 repo-local browser replay fixture 和 manifest readback。 | Wave10 tri-state router、Wave13 readiness、Wave15 manifest/schema、crawler/frontdoor code。 | replay fixture/checker/test 与 topic evidence。 | deterministic fixture replay 通过；真实 public browser fleet replay 不误封。 |
| 4 | `codex/devdocs-wave18-symbolic-search-quality-regression` | 推进 Agent symbolic batch search live-quality gap，补 provider-independent quality regression/evaluator。 | Wave9 contract、Wave11 fixture replay、Wave13 provider readiness、Wave15 quality threshold。 | evaluator/checker/test 与 topic evidence。 | fixture quality threshold 可重复；live provider quality 仍显式 open。 |
| 5 | `codex/devdocs-wave18-long-cycle-scheduler-handoff` | 推进 ingest digestion long-cycle automation，从 durable repository readback 到 scheduler dispatch handoff trace。 | Wave11 scheduler E2E、Wave13 readiness、Wave16 durable JSONL repository readback、long-cycle services。 | scheduler handoff trace/checker/test 与 topic evidence。 | deterministic dispatch handoff 通过；live scheduler/live DB/end-to-end automation 仍 open。 |
| 6 | `codex/devdocs-wave18-graph-editing-audit-readback` | 推进 graph editing/reporting audit durability，补 tenant-like fixture audit/readback/rollback trace。 | Wave11 audit/rollback、Wave15 audit durability、Wave16 UI audit controls、graph services。 | audit readback checker/test 与 topic evidence。 | fixture audit durability 可机检；live tenant DB audit remains open。 |
| 7 | `codex/devdocs-wave18-agentcore-provider-trace` | 推进 LLM service / AgentCore provider live boundary，补 deterministic provider trace/tool-call envelope readback。 | Wave11 provider matrix、Wave13 live-provider readiness、Wave14 tool-calling quality、AgentCore provider code。 | provider trace checker/test 与 topic evidence。 | fake provider/tool-call trace 通过；real external provider call 不误封。 |
| 8 | `codex/devdocs-wave18-source-library-review-batch2` | 推进 source-library 三车道 / mounting / adapter / ingest minimal 的 review closure batch 2。 | Wave12 review queue、Wave14 taxonomy/review readiness、Wave16 deterministic review batch、source_library code/tests。 | 第二批 deterministic review artifacts/checker/test 与多 topic evidence。 | fixture review batch 2 通过；人工 review/public replay 仍 open。 |
| 9 | `codex/devdocs-wave18-frontend-i18n-page-slice2` | 继续 frontend three-layer / i18n/theme / dual topology 的第二个非 Projects 页面业务字符串迁移。 | Wave12 business-string audit、Wave14 migration boundary、Wave16/17 page slices、frontend catalog/pages。 | i18n catalog/page code、checker更新、三 topic evidence。 | slice checker、business audit、lint/build 相关检查通过；全量 page refactor remains partial。 |
| 10 | `codex/devdocs-wave18-docs-root-content-move-batch3` | 对 docs-root restructuring 执行第三个真实 content move batch，继续降低 unsafe moves。 | Wave16/17 moved batches、manifest、content-plan checker。 | 小批量内容迁移、manifest更新、topic evidence。 | docs-root manifest/content-plan/link gate 通过。 |

## 集成策略

1. 每个 worker 只改自己的代码面、测试、主题证据文档，避免触碰共享索引。
2. 集成分支先合并低冲突后端 checker/test，再合并 frontend 与 docs-root 批次。
3. 合并后由 supervisor 统一更新 `CURRENT_DEV/INDEX.md`、`STATUS_AUDIT_2026-04-07.md`、`development-plans/INDEX.md`、`README.md`、`MERGED_OVERVIEW.md`，必要时新增 `wave18_verified` / `wave18_checked` 标签说明。
4. 最小门禁：Wave18 plan gate、CURRENT_DEV status evidence、latest-dev-docs link gate、每个 worker 的 checker/test、`git diff --check`。

## 集成结果

- 10 个 worker 分支已合并到 `codex/devdocs-wave18-integration-2026-05-22`。
- 10 个完成子 agent 已在 roster 中标记为 `closed`。
- 本轮新增 deterministic hybrid readback、open-search health artifact、LLM crawler replay fixture、symbolic quality regression、scheduler handoff trace、graph audit readback、AgentCore provider trace、source-library review batch2、Catalog page i18n slice、docs-root content move batch3。
- `CURRENT_DEV` 仍保持 `partial:33`、`not_closed:0`、`no_closure_claim:0`；所有 live provider、public replay、live scheduler、live DB/API/UI、production data、human review 和全量迁移边界仍显式保留。
