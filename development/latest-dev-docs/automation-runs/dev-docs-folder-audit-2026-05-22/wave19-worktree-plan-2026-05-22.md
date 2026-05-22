# Wave19 Worktree Plan And Integration Status

日期：2026-05-22（PST）

## 当前状态重判

| 状态 | 数量 | 本轮处理策略 |
|---|---:|---|
| `partial` | 33 | 继续把仓内还能验证的计划切片落到代码、脚本、测试与主题证据文档；若仍保留为 `partial`，必须写清剩余 live / 外部 / 生产条件。 |
| `not_closed` | 0 | 暂无单独 `not_closed` 入口；不得为了制造进度而重开已归并状态。 |
| `no_closure_claim` | 0 | 暂无单独 `no_closure_claim` 入口；若发现新无主文档，必须先补 topic-local 证据与 blocker。 |

Wave19 继续处理 Wave18 后仍能仓内推进的边界：provider/vectorization deterministic manifest、open-search health artifact schema、graph rollout readback、ingest 24h canary metrics、crawler public replay shard manifest、AgentCore provider trace redaction、source-library review batch、frontend i18n page slice、docs-root content move、typed-knowledge / writing persisted UI boundary。真实外部 provider、公网 replay、live scheduler、live tenant DB/API/UI、production data、human review 不在本轮伪封口。

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
| 1 | `codex/devdocs-wave19-vectorization-provider-manifest` | 推进 open-source / global vectorization / OSS node 的 provider manifest readback，把 keyword/vector/hybrid 的能力、fallback、quality trace 固化成可审计 manifest。 | Wave18 hybrid readback、Wave14 provider capability、local index/search scripts。 | 后端 checker/test 与三 topic evidence；真实 embedding/provider 质量仍保留边界。 | checker/test 通过；不声明 live provider closure。 |
| 2 | `codex/devdocs-wave19-open-search-health-schema` | 推进 SearXNG / YaCy health artifact，从单次状态 artifact 提升到 schema/readback gate，区分 config、service_not_started、live probe。 | Wave18 open-search health artifact、provider isolation docs、search provider code。 | artifact schema checker/test 与 topic evidence。 | schema/readback 可重复；未启动服务仍 external_blocked。 |
| 3 | `codex/devdocs-wave19-graph-rollout-readback` | 推进 graph node standardization / 3D force engine 的 live DB rollout 前置 readback，补 deterministic manifest、projection shape 和 rollback-ready trace。 | Wave17 rollout manifest、Wave17 runtime pixel/shape gate、graph projection tests。 | graph rollout readback checker/test 与两个 topic evidence。 | deterministic readback 通过；real tenant DB visual smoke 仍 open。 |
| 4 | `codex/devdocs-wave19-ingest-canary-24h-metrics` | 推进 ingest platformization / meaningful guardrails / single-url canary，从 deterministic readback 扩到 24h metrics artifact contract。 | Wave17 canary metrics readback、ingest/frontdoor services、task metrics docs。 | 24h metrics fixture/checker/test 与三 topic evidence。 | fixture metrics gate 通过；live 24h demo/prod metrics 不误封。 |
| 5 | `codex/devdocs-wave19-crawler-public-replay-shards` | 推进 crawler source expansion / LLM crawler frontdoor 的 public replay，把 45-site replay 拆成 shard manifest 和 missing-output readback。 | Wave13 public replay gate、Wave18 browser replay fixture、crawler scripts。 | shard manifest checker/test 与 two-topic evidence。 | repo-local shard gate 通过；real public browser fleet replay 仍 open。 |
| 6 | `codex/devdocs-wave19-agentcore-provider-redaction` | 推进 LLM Service / AgentCore provider boundary，补 provider trace redaction 和 tool-call envelope replay，避免把敏感请求体写入证据。 | Wave18 provider trace readback、Wave14 tool-calling quality、AgentCore services。 | redaction checker/test 与 topic evidence。 | deterministic fake provider replay 通过；real external provider call remains open。 |
| 7 | `codex/devdocs-wave19-source-library-review-batch3` | 推进 source-library 三车道 / mounting / adapter / minimal migration 的 deterministic review closure batch 3。 | Wave12 review queue、Wave16/18 review batches、source_library tests。 | batch3 fixture/checker/test 与四 topic evidence。 | review batch 3 可机检；人工 review/public replay 仍 open。 |
| 8 | `codex/devdocs-wave19-frontend-i18n-dashboard-slice` | 继续 frontend three-layer / i18n/theme / dual topology，把 Dashboard 或同级页面的业务字符串迁到 catalog。 | Wave18 Catalog page i18n slice、business-string audit、frontend i18n catalog。 | frontend code/checker/test 与三 topic evidence。 | i18n slice checker、lint/build 相关检查通过；全量 page refactor remains partial。 |
| 9 | `codex/devdocs-wave19-docs-root-content-move-batch4` | 对 docs-root restructuring 执行第四个真实 content move batch，继续降低 unsafe moves。 | Wave18 unsafe moves=7、manifest、content-plan checker。 | 小批量内容迁移、manifest更新、topic evidence。 | docs-root manifest/content-plan/link gate 通过，unsafe moves 下降或明确 no-op 原因。 |
| 10 | `codex/devdocs-wave19-typed-writing-ui-boundary` | 推进 typed knowledge / writing workbench 的 persisted UI boundary，补 repo-local persisted-card request/response readback。 | Wave17 typed durable readback、Wave17 persisted typed-card UI readback、typed knowledge API/frontend code。 | checker/test 与两个 topic evidence。 | deterministic persisted UI/API boundary 通过；live DB/API/UI 仍 open。 |

## 集成策略

1. 每个 worker 只改自己的代码面、测试、主题证据文档，避免触碰共享索引。
2. 集成分支按低冲突顺序合并：后端 checker/test、frontend slice、docs-root move，最后同步 shared indexes。
3. 合并后由 supervisor 统一更新 `CURRENT_DEV/INDEX.md`、`STATUS_AUDIT_2026-04-07.md`、`development-plans/INDEX.md`、`README.md`、`MERGED_OVERVIEW.md`，必要时新增 `wave19_verified` / `wave19_checked` 标签说明。
4. 最小门禁：Wave19 plan gate、CURRENT_DEV status evidence、latest-dev-docs touched-file link gate、每个 worker 的 checker/test、`git diff --check`。

## 集成结果

- 10 个 worker 分支已合并到 `codex/devdocs-wave19-integration-2026-05-22`。
- 10 个完成子 agent 已在 roster 中标记为 `closed`。
- 本轮新增 provider manifest readback、open-search health schema/readback、graph rollout readback、ingest 24h metrics artifact、crawler public replay shards、AgentCore provider trace redaction、source-library review closure batch 3、Dashboard page i18n slice、docs-root content move batch 4、typed/writing persisted-card API boundary。
- `CURRENT_DEV` 仍保持 `partial:33`、`not_closed:0`、`no_closure_claim:0`；所有 live provider、public replay、live scheduler、live DB/API/UI、production data、human review 和全量迁移边界仍显式保留。
- Docs-root content-plan unsafe moves 从 `7` 降到 `6`，剩余 `development-plans-architecture-tree` 仍需后续批次处理。
