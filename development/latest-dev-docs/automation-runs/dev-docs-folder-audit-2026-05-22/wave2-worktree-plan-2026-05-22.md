# Wave2 Worktree Plan And Integration Status

Run date: 2026-05-22 PST

Status: integrated into `codex/devdocs-wave2-integration-2026-05-22`.

This file records the second implementation wave created from the folder audit plan. It supersedes the earlier pending skeleton from lane J.

## Inputs

- [development/latest-dev-docs/README.md](../../README.md)
- [development/latest-dev-docs/MERGED_OVERVIEW.md](../../MERGED_OVERVIEW.md)
- [parallel-plan-tree-2026-05-22.md](./parallel-plan-tree-2026-05-22.md)
- [worktree-branch-plan.md](./worktree-branch-plan.md)

## Baseline

- Baseline branch: `codex/devdocs-supervisor-seed` at `9a9bcd1`.
- Integration branch: `codex/devdocs-wave2-integration-2026-05-22`.
- Worktree root: `/Users/wangyiliang/market-research-workflow.worktrees`.
- Supervisor rule: each agent edited only its assigned worktree, did not push, and returned `结果/改动文件/验证状态/风险/commit`.

## Wave2 Branch Matrix

| Lane | Branch | Commit | Result | Gate evidence | Residual blocker |
|---|---|---:|---|---|---|
| A | `codex/devdocs-lancedb-runtime-smoke` | `954197b` | merged | LanceDB runtime smoke passed for `keyword`, `vector`, and `hybrid`; local_index unit tests `7 passed` | benchmark quality, embedding semantics, and cross-product evidence contract remain open |
| B | `codex/devdocs-local-index-runtime-artifacts` | `e053680` | merged with A/B status reconciliation | local_index unit tests `7 passed`; changed-doc links OK | B's early hybrid fallback observation is superseded by A; topic remains `CURRENT_DEV` for full vectorization foundation |
| C | `codex/devdocs-search-provider-container-replay` | `cafd926` | merged | real SearXNG/YaCy Docker replay passed; `passed_rows=2 failed_rows=0` | YaCy DATA password reset may be required in stale local lab state |
| D | `codex/devdocs-search-provider-trace-artifacts` | `8d86c16` | merged | offline trace artifact generated; search provider adapter tests `5 passed` | offline contract does not replace container replay; C supplies runtime evidence |
| E | `codex/devdocs-graph-frontend-e2e` | `1d02b0d` | merged | GraphPage Playwright e2e `3 passed`; frontend lint passed | curated graph handoff and writing-reporting evidence remain open |
| F | `codex/devdocs-graph-visual-evidence` | `04225c8` | merged | Storybook build passed; Playwright visual probe and screenshots recorded | visual probe does not replace full backend-data graph workflow closure |
| G | `codex/devdocs-storybook-launcher-gates` | `ba6738e` | merged | `storybook:build` passed; Storybook MCP endpoint checked; launcher dry-run/status gates passed | destructive macOS app bundle rebuild intentionally not run |
| H | `codex/devdocs-source-library-real-probes` | `47b6a86` | merged | local HTTP fixture probe passed; focused source_library tests `33 passed`; broader source-library/resource-pool tests `161 passed` | public anti-bot and dirty-source live replay remain environment-dependent |
| I | `codex/devdocs-backend-schema-contracts` | `2915590` | merged | route/schema/openapi contract tests `8 passed`; schema inventory generated | 170 OpenAPI 200 responses remain `untyped` and need response_model/envelope follow-up |
| J | `codex/devdocs-wave2-index-sync` | `f795dc8` | merged after result reconciliation | changed-doc links OK for plan skeleton | no blocker; skeleton was updated to this integrated status |

## Integrated Evidence Packages

- [local-index-lancedb-runtime-smoke/2026-05-22](../local-index-lancedb-runtime-smoke/2026-05-22/README.md)
- [local-index-runtime-contract/2026-05-22](../local-index-runtime-contract/2026-05-22/README.md)
- [search-provider-container-replay/2026-05-22](../search-provider-container-replay/2026-05-22/README.md)
- [search-provider-trace-artifacts/2026-05-22](../search-provider-trace-artifacts/2026-05-22/README.md)
- [graph-frontend-e2e/2026-05-22](../graph-frontend-e2e/2026-05-22/README.md)
- [graph-visual-evidence/2026-05-22](../graph-visual-evidence/2026-05-22/README.md)
- [storybook-launcher-gates/2026-05-22](../storybook-launcher-gates/2026-05-22/README.md)
- [source-library-real-probes/2026-05-22](../source-library-real-probes/2026-05-22/README.md)
- [backend-docs/B_API/API_SCHEMA_INVENTORY_2026-05-22.md](../../backend-docs/B_API/API_SCHEMA_INVENTORY_2026-05-22.md)

## Merge Notes

- A and B were reconciled so the final docs use A's canonical runtime result: true LanceDB `keyword`, `vector`, and `hybrid` runtime smoke passed without fallback.
- C and D were reconciled into two evidence layers: offline adapter trace contract plus real container replay.
- E, F, and G were reconciled as separate frontend layers: GraphPage runtime e2e, graph visual evidence, and Storybook/launcher gates.
- H and I intentionally keep topics open where the remaining work requires public-network/live-site replay or broad API response schema remediation.

## Next Wave Queue

1. Convert LanceDB runtime smoke into repeatable benchmark-quality evidence for embedding/ranking behavior.
2. Add response_model/envelope remediation for the 170 untyped OpenAPI 200 responses found by the schema inventory.
3. Close graph handoff beyond canvas/e2e: curated graph evidence pack, workflow graph, and writing/reporting handoff.
4. Run source_library public live-site probes where anti-bot/network state can be controlled and recorded.
5. Keep `CURRENT_DEV` topics in place until these blockers have repo evidence and focused gates.
