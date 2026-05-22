# Wave10 Worktree Plan (2026-05-22)

Status: seeded by supervisor after Wave9 integration.

Wave9 left `CURRENT_DEV` at `partial=35`, `not_closed=0`, `no_closure_claim=0`. Wave10 targets the next repo-controlled closure slices without pretending that externally blocked or broad productionization topics are fully sealed.

Worker branches must not edit shared navigation indexes; the supervisor integration lane owns final status/index sync.

Forbidden shared indexes for workers:

- `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`
- `development/latest-dev-docs/development-plans/INDEX.md`
- `development/latest-dev-docs/README.md`
- `development/latest-dev-docs/MERGED_OVERVIEW.md`

## Branch Matrix

| Branch | Worktree | Topic Slice | Owned Write Scope |
|---|---|---|---|
| `codex/devdocs-wave10-graph-frontend-visual` | `devdocs-wave10-graph-frontend-visual` | Graph 3D frontend visual / engine-switch smoke | graph frontend visual contract code/tests, Graph 3D topic-local evidence |
| `codex/devdocs-wave10-graph-node-db-rollout` | `devdocs-wave10-graph-node-db-rollout` | Graph node DB rollout readiness | graph storage/readmode/backfill guard code/tests, graph-node topic-local evidence |
| `codex/devdocs-wave10-time-semantics-ope` | `devdocs-wave10-time-semantics-ope` | time semantics OPE / statistics freshness | prompt time-density / source-time-window contract code/tests, time topic-local evidence |
| `codex/devdocs-wave10-llm-crawler-tristate` | `devdocs-wave10-llm-crawler-tristate` | LLM crawler high-JS/router/tri-state gap | crawler/frontdoor router state code/tests, LLM crawler topic-local evidence |
| `codex/devdocs-wave10-source-library-governance` | `devdocs-wave10-source-library-governance` | search chain source-library mounting and adapter governance | source-library routing/governance checker/tests, topic-local evidence |
| `codex/devdocs-wave10-vectorization-quality` | `devdocs-wave10-vectorization-quality` | open-source platform / global vectorization quality gate | local_index/search provider quality contract code/tests, vector/search topic-local evidence |
| `codex/devdocs-wave10-writing-typed-knowledge` | `devdocs-wave10-writing-typed-knowledge` | typed knowledge / writing workbench closure slice | writing and typed-knowledge handoff contract code/tests, topic-local evidence |
| `codex/devdocs-wave10-docs-root-content-shim` | `devdocs-wave10-docs-root-content-shim` | docs root content shim batch | `docs/development`, `docs/architecture`, manifest checker, docs-root topic-local evidence |
| `codex/devdocs-wave10-parallel-runtime-contract` | `devdocs-wave10-parallel-runtime-contract` | parallel agent runtime contract refresh | parallel orchestration checker/docs, topic-local evidence |

## Integration Rule

Workers return:

- `结果`
- `改动文件`
- `验证状态`
- `风险`

The supervisor merges clean worker branches, updates shared indexes once, then reruns status evidence and focused gates.

