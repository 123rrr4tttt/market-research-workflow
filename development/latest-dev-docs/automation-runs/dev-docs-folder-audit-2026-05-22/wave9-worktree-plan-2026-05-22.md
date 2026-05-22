# Wave9 Worktree Plan (2026-05-22)

Status: seeded by supervisor after Wave8 integration.

Wave8 reduced `CURRENT_DEV` to `partial=35`, `not_closed=0`, `no_closure_claim=0`. Wave9 targets the next evidence-backed closure slices. Worker branches must not edit shared navigation indexes; the supervisor integration lane owns final status/index sync.

Forbidden shared indexes for workers:

- `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`
- `development/latest-dev-docs/development-plans/INDEX.md`
- `development/latest-dev-docs/README.md`
- `development/latest-dev-docs/MERGED_OVERVIEW.md`

## Branch Matrix

| Branch | Worktree | Topic Slice | Owned Write Scope |
|---|---|---|---|
| `codex/devdocs-wave9-meaningful-ingest-guardrails` | `devdocs-wave9-meaningful-ingest-guardrails` | meaningful ingest guardrails | `main/backend/app/services/ingest/*meaningful*`, focused tests, topic-local evidence |
| `codex/devdocs-wave9-agent-symbolic-batch-search` | `devdocs-wave9-agent-symbolic-batch-search` | agent symbolic batch search | `main/backend/app/services/agent_batch*`, search brief/critic/retry tests, topic-local evidence |
| `codex/devdocs-wave9-source-library-three-lane` | `devdocs-wave9-source-library-three-lane` | source-library three-lane architecture | `main/backend/app/services/source_library/*`, source-library lane checker/tests, topic-local evidence |
| `codex/devdocs-wave9-data-structured-document-queries` | `devdocs-wave9-data-structured-document-queries` | data structured service modularization | `main/backend/app/services/document_queries/*`, tests, topic-local evidence |
| `codex/devdocs-wave9-consumer-side-modularization` | `devdocs-wave9-consumer-side-modularization` | consumer-side modularization | consumer facade/query contract code/tests, topic-local evidence |
| `codex/devdocs-wave9-ingest-long-cycle-automation` | `devdocs-wave9-ingest-long-cycle-automation` | ingest digestion and long-cycle automation | scheduler/task contract code/tests, topic-local evidence |
| `codex/devdocs-wave9-llm-agent-platform-contract` | `devdocs-wave9-llm-agent-platform-contract` | LLM service and Agent platformization | AgentCore/platform contract code/tests, topic-local evidence |
| `codex/devdocs-wave9-docs-root-migration` | `devdocs-wave9-docs-root-migration` | docs root restructuring | `docs/development`, `docs/architecture`, migration checker, topic-local evidence |
| `codex/devdocs-wave9-source-library-ingest-ext` | `devdocs-wave9-source-library-ingest-ext` | source-library ingest minimal migration | `AT-EXT-*` contract/checker/tests, topic-local evidence |

## Integration Rule

Workers return:

- `结果`
- `改动文件`
- `验证状态`
- `风险`

The supervisor merges clean worker branches, updates shared indexes once, then reruns status evidence and focused gates.
