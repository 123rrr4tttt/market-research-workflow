# Worktree Branch Plan For Development-Docs Landing

Run date: 2026-05-22 PST

Purpose: split the remaining development-doc landing work into independent worktree branches so subagents can implement in parallel and the supervisor can merge only branches that pass their local gates.

## Supervisor Rule

- Supervisor worktree: `/Users/wangyiliang/market-research-workflow`
- Parallel worktree root: `/Users/wangyiliang/market-research-workflow.worktrees`
- Branch prefix: `codex/`
- Each subagent owns exactly one branch and must return: `result`, `changed files`, `validation status`, `risk`.
- A branch is merge-eligible only after its lane gate passes and `git diff --check` is clean.
- Do not modify pre-existing unrelated dirty files in the supervisor worktree.

## Branch Lanes

| Lane | Branch | Worktree path | Owner role | Scope | Gate |
|---|---|---|---|---|---|
| 1 | `codex/devdocs-backend-core-refresh` | `market-research-workflow.worktrees/backend-core-refresh` | backend-core doc/code verifier | Refresh backend-core route/API/project-key drift and land only low-risk contract fixes | backend targeted pytest + docs link check |
| 2 | `codex/devdocs-backend-docs-route-map` | `market-research-workflow.worktrees/backend-docs-route-map` | backend-docs mapper | Regenerate or mark stale backend route/API docs; no runtime changes unless needed for evidence | route-map script or static check + docs link check |
| 3 | `codex/devdocs-ops-frontend-closure` | `market-research-workflow.worktrees/ops-frontend-closure` | ops/frontend closer | Add graph/API/Storybook/launcher closure notes under `ops-frontend` and sync navigation | frontend lint/test when available + docs link check |
| 4 | `codex/devdocs-frontend-modern-index` | `market-research-workflow.worktrees/frontend-modern-index` | frontend-modern verifier | Validate `frontend-modern` main docs against current workbench/code surface | docs link check + minimal frontend smoke if available |
| 5 | `codex/devdocs-graph-plan-refresh` | `market-research-workflow.worktrees/graph-plan-refresh` | graph lane verifier | Refresh graph force-engine, node standardization, editing/reporting topic status | graph-related tests or smoke scripts + docs link check |
| 6 | `codex/devdocs-ingest-frontdoor-refresh` | `market-research-workflow.worktrees/ingest-frontdoor-refresh` | ingest lane verifier | Rebase old `single_url.py`/ingest guardrail docs onto current ingest/source_library frontdoor | backend ingest tests + docs link check |
| 7 | `codex/devdocs-source-library-capability` | `market-research-workflow.worktrees/source-library-capability` | source-library verifier | Finish or mark source_library capability/fallback assertions and minimal migrations | source_library targeted pytest + docs link check |
| 8 | `codex/devdocs-agent-migration-split` | `market-research-workflow.worktrees/agent-migration-split` | agent migration curator | Split completed Claude-agent migration records from active diagnostics | agent targeted tests when changed + docs link check |
| 9 | `codex/devdocs-local-index-runtime` | `market-research-workflow.worktrees/local-index-runtime` | vector/runtime verifier | Validate LanceDB vector/hybrid runtime path and record benchmark evidence | local_index pytest + optional LanceDB smoke |
| 10 | `codex/devdocs-search-provider-replay` | `market-research-workflow.worktrees/search-provider-replay` | search provider verifier | Use explicit provider trace in closure replay and update local-open-search status | search provider pytest + replay evidence |

## Merge Order

1. Merge lanes with no code changes first: docs route-map, frontend-modern, agent migration split.
2. Merge independent frontend/graph/ingest/source-library docs lanes next, resolving navigation conflicts in the supervisor worktree.
3. Merge code-bearing backend lanes last: backend-core, local-index-runtime, search-provider-replay.
4. After each merge, run `git diff --check` and the lane's gate again from the supervisor worktree.
5. After all accepted lanes merge, update:
   - `development/latest-dev-docs/README.md`
   - `development/latest-dev-docs/MERGED_OVERVIEW.md`
   - `development/latest-dev-docs/development-plans/INDEX.md`
   - `development/latest-dev-docs/automation-runs/dev-docs-folder-audit-2026-05-22/README.md`

## Creation Command Template

```bash
mkdir -p /Users/wangyiliang/market-research-workflow.worktrees
git worktree add -b codex/devdocs-backend-core-refresh /Users/wangyiliang/market-research-workflow.worktrees/backend-core-refresh HEAD
```

Repeat the template for each lane branch, changing the branch name and path. Create worktrees only after the supervisor worktree's current integration patch is either committed, stashed, or intentionally left as the merge baseline.
