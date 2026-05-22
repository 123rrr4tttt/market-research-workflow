# Wave11 Worktree Plan (2026-05-22)

Status: seeded by supervisor after Wave10 integration.

Wave10 left `CURRENT_DEV` at `partial=35`, `not_closed=0`, `no_closure_claim=0`. Wave11 targets another repo-controlled batch from the remaining partial directories. The goal is to land code, deterministic contracts, and topic-local evidence without overstating externally blocked live-network, live-DB, or broad production-readiness claims.

Worker branches must not edit shared navigation indexes; the supervisor integration lane owns final status/index sync.

Forbidden shared indexes for workers:

- `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`
- `development/latest-dev-docs/development-plans/INDEX.md`
- `development/latest-dev-docs/README.md`
- `development/latest-dev-docs/MERGED_OVERVIEW.md`

## Branch Matrix

| Branch | Worktree | Topic Slice | Owned Write Scope |
|---|---|---|---|
| `codex/devdocs-wave11-ingest-guardrails-rollout` | `devdocs-wave11-ingest-guardrails-rollout` | Meaningful ingest guardrails global rollout and canary metrics | ingest guardrail config/metrics code/tests, meaningful-ingest topic-local evidence |
| `codex/devdocs-wave11-long-cycle-scheduler-e2e` | `devdocs-wave11-long-cycle-scheduler-e2e` | Ingest digestion long-cycle scheduler and persistent task E2E contract | long-cycle scheduler/persistent-task contract code/tests, ingest-digestion topic-local evidence |
| `codex/devdocs-wave11-agentcore-provider-matrix` | `devdocs-wave11-agentcore-provider-matrix` | LLM service AgentCore provider matrix and framework evaluation boundary | AgentCore provider matrix/evaluation code/tests, LLM-service topic-local evidence |
| `codex/devdocs-wave11-graph-editing-audit` | `devdocs-wave11-graph-editing-audit` | Graph editing audit, rollback, and writing handoff closure slice | graph editing audit/rollback code/tests, graph-editing topic-local evidence |
| `codex/devdocs-wave11-source-library-extraction` | `devdocs-wave11-source-library-extraction` | Source-library minimal migration article extraction runner contract | source-library extraction/runtime code/tests, minimal-migration topic-local evidence |
| `codex/devdocs-wave11-symbolic-search-quality` | `devdocs-wave11-symbolic-search-quality` | Agent symbolic batch search provider-quality replay boundary | symbolic search quality/replay contract code/tests, symbolic-search topic-local evidence |
| `codex/devdocs-wave11-structured-consumer-extraction` | `devdocs-wave11-structured-consumer-extraction` | Data structured service and consumer-side query extraction | document query / consumer facade extraction code/tests, data-structured and consumer-side topic-local evidence |
| `codex/devdocs-wave11-frontend-topology-theme` | `devdocs-wave11-frontend-topology-theme` | Frontend topology, i18n/theme, and three-layer rewrite contract | frontend topology/theme contract code/tests, frontend topic-local evidence |
| `codex/devdocs-wave11-docs-root-navigation` | `devdocs-wave11-docs-root-navigation` | Docs root shared navigation promotion batch | docs root manifests/navigation shims/checkers, docs-root topic-local evidence |

## Integration Rule

Workers return:

- `结果`
- `改动文件`
- `验证状态`
- `风险`

The supervisor merges clean worker branches, updates shared indexes once, then reruns status evidence, link checks, the Wave11 plan gate, and focused test/checker gates.
