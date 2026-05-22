# Wave2 Worktree Plan For Development-Docs Landing

Run date: 2026-05-22 PST

Status: planning skeleton. This file reserves the Wave2 branch map and merge order for the supervisor. It does not record other agents as complete and should be updated only after the supervisor merges each accepted branch.

## Inputs

- [development/latest-dev-docs/README.md](../../README.md)
- [development/latest-dev-docs/MERGED_OVERVIEW.md](../../MERGED_OVERVIEW.md)
- [parallel-plan-tree-2026-05-22.md](./parallel-plan-tree-2026-05-22.md)
- [worktree-branch-plan.md](./worktree-branch-plan.md)

## Baseline

- Baseline branch expected by this plan: `codex/devdocs-integration-2026-05-22` or a descendant already containing Wave0/Wave1 audit artifacts.
- Worktree root: `/Users/wangyiliang/market-research-workflow.worktrees`
- Supervisor rule: each agent edits only its assigned worktree, does not push, and returns `结果/改动文件/验证状态/风险/commit`.
- Closure rule: a lane remains `pending` until the supervisor has merged the branch and rerun the lane gate from the integration worktree.

## Wave2 Branch Matrix

| Lane | Branch | Worktree path | Target | Write range | Acceptance gate | Merge order | Status |
|---|---|---|---|---|---|---:|---|
| A | `codex/devdocs-wave2-lancedb-runtime-smoke` | `/Users/wangyiliang/market-research-workflow.worktrees/wave2-lancedb-runtime-smoke` | Prove local_index keyword/vector/hybrid behavior against a real LanceDB runtime when the optional dependency is available. | `main/backend/app/services/local_index/**`, `main/backend/tests/**/local_index*`, runtime evidence under this audit run or a dedicated local-index automation run. | local_index unit tests plus a recorded LanceDB smoke artifact, or an explicit dependency/environment blocker. | 6 | pending |
| B | `codex/devdocs-wave2-local-index-runtime-docs` | `/Users/wangyiliang/market-research-workflow.worktrees/wave2-local-index-runtime-docs` | Update local-index/global-vectorization development-doc status after Lane A evidence is known. | `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-05-14-global-vectorization-general-foundation/**`, matching `INDEX.md` files, audit run notes. | changed-doc link check; no closed wording unless Lane A evidence is merged. | 8 | pending |
| C | `codex/devdocs-wave2-search-provider-container-replay` | `/Users/wangyiliang/market-research-workflow.worktrees/wave2-search-provider-container-replay` | Rerun SearXNG/YaCy container replay and prove explicit provider trace fields in real replay output. | search provider smoke scripts/tests, replay artifact under `development/latest-dev-docs/automation-runs/search-provider-replay/`, related backend test fixtures if needed. | search provider adapter tests plus replay artifact, or explicit container/runtime blocker. | 5 | pending |
| D | `codex/devdocs-wave2-search-provider-doc-sync` | `/Users/wangyiliang/market-research-workflow.worktrees/wave2-search-provider-doc-sync` | Synchronize local-open-search provider docs after Lane C evidence is known. | `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-05-14-local-open-search-provider-isolation/**`, `development/latest-dev-docs/backend-core/**` or `backend-docs/**` references only if the provider surface changes. | changed-doc link check; status must remain pending/not_closed if Lane C is blocked. | 9 | pending |
| E | `codex/devdocs-wave2-graph-frontend-e2e` | `/Users/wangyiliang/market-research-workflow.worktrees/wave2-graph-frontend-e2e` | Provide current GraphPage e2e evidence for force3d and curated graph handoff paths. | `main/frontend-modern/**`, frontend Playwright specs, graph evidence under this audit run. | frontend Playwright graph spec, or explicit dependency blocker with logs. | 3 | pending |
| F | `codex/devdocs-wave2-graph-visual-evidence` | `/Users/wangyiliang/market-research-workflow.worktrees/wave2-graph-visual-evidence` | Capture visual/canvas evidence and sync graph-topic status without claiming closure before Lane E passes. | graph screenshots/log evidence, `development/latest-dev-docs/development-plans/CURRENT_DEV/*graph*/**`, `ops-frontend/**` graph notes. | changed-doc link check plus screenshot/log artifact reference. | 7 | pending |
| G | `codex/devdocs-wave2-storybook-launcher-gates` | `/Users/wangyiliang/market-research-workflow.worktrees/wave2-storybook-launcher-gates` | Run Storybook build, verify Storybook MCP configuration, and refresh launcher-first ops flow. | `main/frontend-modern/**`, launcher/Storybook config docs, `development/latest-dev-docs/ops-frontend/**`. | `storybook:build` or documented dependency blocker; changed-doc link check. | 4 | pending |
| H | `codex/devdocs-wave2-source-library-real-probes` | `/Users/wangyiliang/market-research-workflow.worktrees/wave2-source-library-real-probes` | Add stable source_library site-entry probe evidence and anti-bot/transport resilience fixture coverage. | `main/backend/app/services/resource_pool/**`, source_library tests/fixtures, evidence under this audit run or a source-library automation run. | source_library targeted pytest plus recorded fixture input/output. | 2 | pending |
| I | `codex/devdocs-wave2-backend-schema-contracts` | `/Users/wangyiliang/market-research-workflow.worktrees/wave2-backend-schema-contracts` | Extend backend-docs route map from route existence to request/response schema surface. | backend route/schema inventory script or artifact, `development/latest-dev-docs/backend-docs/B_API/**`, focused contract tests if schema extraction is codified. | generated schema inventory plus contract/static check; changed-doc link check. | 1 | pending |
| J | `codex/devdocs-wave2-index-sync` | `/Users/wangyiliang/market-research-workflow.worktrees/wave2-index-sync` | Prepare Wave2 top-level navigation and merge skeleton for the supervisor. | This file, `development/latest-dev-docs/README.md`, `development/latest-dev-docs/MERGED_OVERVIEW.md`. | changed-doc link check over this branch's changed Markdown files. | 0 | pending |

## Merge Sequence

0. Merge Lane J first if the supervisor wants the Wave2 navigation link present before code-bearing lanes.
1. Merge Lane I before docs sync lanes because backend schema inventory can affect backend-docs wording.
2. Merge Lane H before graph/search documentation lanes; source_library fixture changes are mostly isolated and provide early backend signal.
3. Merge Lane E, then Lane G, because frontend dependency state can affect both graph e2e and Storybook/launcher status.
4. Merge Lane C before Lane D so provider docs can reflect actual replay evidence.
5. Merge Lane A before Lane B so local-index docs do not predeclare LanceDB runtime status.
6. Merge Lane F after Lane E because visual graph evidence should describe the current e2e result.
7. Merge docs-sync lanes B and D last, then let the supervisor refresh this file's status table and the audit README.

## Supervisor Fill Slots

The supervisor should update the rows below only after merging and rerunning gates from the integration worktree.

| Lane | Merge commit | Gate rerun | Result status | Residual blocker |
|---|---|---|---|---|
| A | pending | pending | pending | pending |
| B | pending | pending | pending | pending |
| C | pending | pending | pending | pending |
| D | pending | pending | pending | pending |
| E | pending | pending | pending | pending |
| F | pending | pending | pending | pending |
| G | pending | pending | pending | pending |
| H | pending | pending | pending | pending |
| I | pending | pending | pending | pending |
| J | pending | pending | pending | pending |

## Navigation Update Rule

- `README.md` and `MERGED_OVERVIEW.md` may link to this file as a Wave2 plan entry.
- They must not say Wave2 is complete until the supervisor updates this file and the audit README after all accepted merges.
- If a lane is blocked by environment or dependencies, keep the related topic in `CURRENT_DEV` and record the blocker instead of moving it to `ARCHIVE_CLOSED`.
