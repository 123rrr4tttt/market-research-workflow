# Wave15 Worktree Plan And Integration Status

日期：2026-05-22（PST）

## 当前状态审计

| 状态 | 数量 | 本轮处理策略 |
|---|---:|---|
| `partial` | 35 | 继续逐目录推进，优先落仓内代码、契约、门禁和证据，不把外部依赖误判为封口。 |
| `not_closed` | 0 | 暂无单独 `not_closed` 入口。 |
| `no_closure_claim` | 0 | 暂无单独 `no_closure_claim` 入口。 |

重点风险标签：`doc_stale`、`doc_drift`、`external_gap`、`external_blocked`、`live runtime gap`、`worker runtime gap`、`sql predicate gap`、`high-JS replay gap`。Wave15 不直接迁档；只有在当前代码事实和门禁能证明闭环时，才允许后续集成阶段调整状态。

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
| 1 | `codex/devdocs-wave15-open-search-runtime-boundary` | 推进 SearXNG / YaCy isolated provider 的 runtime boundary，明确配置存在、服务不可达、live 查询未封口三种状态。 | Wave6/Wave12 provider isolation evidence、open search provider 配置与 search service。 | runtime boundary checker、单测、open-search Wave15 证据。 | checker 通过；保留真实 SearXNG / YaCy runtime gap，不声称外部封口。 |
| 2 | `codex/devdocs-wave15-source-time-production-readiness` | 推进 Source Time Window 的生产数据语义链边界，把 deterministic contract 与生产验证缺口拆开。 | Wave10 source-time contract、Wave12 decision-log provenance、time-density scripts/services。 | production readiness checker、单测、source-time Wave15 证据。 | checker 通过；明确 production data semantic chain 仍待 live 数据验证。 |
| 3 | `codex/devdocs-wave15-openclaw-runtime-handoff` | 推进 R41 OpenClaw Autodispatch 的 repo-local handoff 和外部 runtime 缺口。 | Wave12 R41 mirror gate、OpenClaw autodispatch implementation 文档与脚本。 | runtime handoff checker、单测或文档结构门禁、R41 Wave15 证据。 | gate 通过；不把外部 OpenClaw runtime 当作已验证。 |
| 4 | `codex/devdocs-wave15-llm-crawler-replay-manifest` | 推进 LLM Crawler Unified FrontDoor 的 high-JS/public replay manifest，给真实浏览器 replay 留出 opt-in 边界。 | Wave13 high-JS readiness、fetch router、crawler replay artifacts。 | replay manifest/schema checker、单测、LLM crawler Wave15 证据。 | checker 通过；高 JS 真实公网 replay 仍按 `high-JS replay gap` 保留。 |
| 5 | `codex/devdocs-wave15-symbolic-live-quality-threshold` | 推进 Agent Symbolic Batch Search 的 live provider quality threshold，把 fixture uplift 与 live provider 质量判定分离。 | Wave11 quality replay、Wave13 provider quality readiness、agent_batch/search quality code。 | live quality threshold contract/checker、单测、symbolic search Wave15 证据。 | checker 通过；真实 provider quality 仍需 live replay。 |
| 6 | `codex/devdocs-wave15-structured-sql-helper-migration` | 推进 Data Structured Service Modularization 的 SQL / query helper 迁移边界。 | Wave9/Wave13 structured data API migration、document query services。 | 一个可复用 SQL/query helper 或 migration inventory checker、单测、structured data Wave15 证据。 | 测试通过；未迁移端点仍列为后续边界。 |
| 7 | `codex/devdocs-wave15-consumer-sql-predicate-facade` | 推进 Consumer Side Modularization 的 SQL JSON predicate gap，给 admin/dashboard/document-view 查询补 facade 或门禁。 | Wave11 consumer query extraction、Wave13 dashboard extraction、consumer/document view code。 | predicate facade 或 checker、单测、consumer-side Wave15 证据。 | 测试通过；剩余复杂 SQL JSON predicate 明确记录。 |
| 8 | `codex/devdocs-wave15-graph-editing-audit-durability` | 推进 Graph Editing And Reporting 的 audit durability/readback 边界，避免依赖 dirty smoke 脚本。 | Wave11 audit rollback、Wave12 live-smoke readiness、graph editing/reporting services。 | audit durability checker、单测、Graph Editing Wave15 证据。 | checker 通过；不修改 `main/backend/scripts/workflow_graph_smoke_local.py`。 |
| 9 | `codex/devdocs-wave15-typed-writing-live-boundary` | 推进 Typed Knowledge Organization 与 Writing Workbench 的 live DB/API/UI 边界。 | Wave10/Wave12 typed-knowledge persistence/API evidence、writing workbench services。 | live boundary inventory checker、单测、typed/writing Wave15 证据。 | checker 通过；真实 live DB/API/UI 验证仍保留为目录级边界。 |

## 集成策略

1. 每个 worker 只改自己的代码面、测试、主题证据文档，避免触碰共享索引。
2. 集成分支按低冲突顺序合并：open-search、time/OpenClaw、crawler/symbolic、structured/consumer、graph、typed-writing。
3. 合并后统一更新 `CURRENT_DEV/INDEX.md`、`STATUS_AUDIT_2026-04-07.md`、`development-plans/INDEX.md`、`README.md`、`MERGED_OVERVIEW.md` 和状态证据报告。
4. 最小门禁：Wave15 plan gate、CURRENT_DEV status evidence、latest-dev-docs link gate、每个 worker 的 checker/test、`git diff --check`。
