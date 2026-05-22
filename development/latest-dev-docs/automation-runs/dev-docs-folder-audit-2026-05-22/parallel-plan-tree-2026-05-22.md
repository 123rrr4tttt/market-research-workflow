# Parallel Plan Tree For Dev-Docs Landing

Run date: 2026-05-22 PST

This tree is the merge-ready execution map for turning the current development documents into project changes. It separates completed landings, still-open blockers, and the next agent wave.

## Root Goal

`development/latest-dev-docs` is the source of truth for current development plans. Each folder/topic must have one of four states:

- `closed`: enough repo evidence exists, docs moved or linked from `ARCHIVE_CLOSED`.
- `not_closed`: current implementation is partial and the blocker is explicit.
- `outdated`: the document still points at stale paths, stale assumptions, or old contracts.
- `needs_update`: the topic is current enough to keep, but requires refreshed evidence, tests, or index updates.

Code landing rule: a plan counts as landed only when it has a repo diff plus a focused gate. Documentation-only status updates do not mark a topic closed unless the existing implementation evidence is strong enough.

## Wave 0: Integration Baseline

Status: merged into `codex/devdocs-integration-2026-05-22`.

- Seed branch: `codex/devdocs-supervisor-seed`
- Purpose: record the folder audit, repair top-level navigation, add missing category indexes, and land first search/local-index contract slices.
- Main artifacts:
  - `automation-runs/dev-docs-folder-audit-2026-05-22/README.md`
  - `automation-runs/dev-docs-folder-audit-2026-05-22/worktree-branch-plan.md`
  - `development-plans/A_ARCHITECTURE` through `F_PLAN` index files
  - `frontend-modern` standard entry files

## Wave 1: Folder And Topic Lanes

Status: all 10 lanes were committed locally and merged into `codex/devdocs-integration-2026-05-22`.

| Lane | Branch | State | Code landing | Gate evidence | Remaining blocker |
|---|---|---|---|---|---|
| 1 | `codex/devdocs-backend-core-refresh` | merged | Added runtime API route drift contract test | `42 passed` across route/project/ingest gates | future route changes must refresh snapshot |
| 2 | `codex/devdocs-backend-docs-route-map` | merged | docs-only route map refresh | route AST count: 250 routes / 30 modules; docs links OK | AST map does not prove response schema |
| 3 | `codex/devdocs-ops-frontend-closure` | merged | docs-only ops/frontend status matrix | F_PLAN link check OK | frontend runtime gates blocked by missing `node_modules` |
| 4 | `codex/devdocs-frontend-modern-index` | merged | docs-only frontend-modern entry normalization | docs links OK | frontend runtime gates not executed |
| 5 | `codex/devdocs-graph-plan-refresh` | merged | docs-only graph status refresh | backend graph/workflow/writing tests: 51 passed in lane | GraphPage frontend e2e and visual canvas proof still missing |
| 6 | `codex/devdocs-ingest-frontdoor-refresh` | merged | Added ingest/frontdoor legacy mapping test | `3 passed` in integration; lane also ran broader ingest/source_library gates | broader fetch-router and frontend tri-state still open |
| 7 | `codex/devdocs-source-library-capability` | merged | Added search-template fallback diagnostics and source_library assertions | `56 passed` in integration; lane ran 160 targeted tests | real anti-bot/site-entry probes still need stable fixture |
| 8 | `codex/devdocs-agent-migration-split` | merged | docs-only archive move | changed-doc links OK | future active diagnostics must start as a new D48+ topic |
| 9 | `codex/devdocs-local-index-runtime` | merged | Added `keyword|vector|hybrid` local_index mode contract | `7 passed` in integration | real LanceDB optional runtime smoke still blocked by missing dependency |
| 10 | `codex/devdocs-search-provider-replay` | merged | Added SearXNG/YaCy explicit provider trace contract | `4 passed` in integration | real container replay still not rerun |

## Current Closed/Not-Closed Decisions

Closed or archived in this wave:

- `2026-04-02-claude-agent-high-fidelity-migration`: moved from `CURRENT_DEV` to `ARCHIVE_CLOSED` because the active diagnostics are no longer current-entry material.

Not closed, but advanced by code/tests:

- `2026-05-14-global-vectorization-general-foundation`: local_index mode contract landed; real vector/hybrid runtime benchmark remains open.
- `2026-05-14-local-open-search-provider-isolation`: explicit provider trace contract landed; real SearXNG/YaCy replay remains open.
- `2026-03-02-single-url-first-ingest-allocation-plan`: legacy single-url mapping now has a focused frontdoor test; broader fetch-router items remain open.
- `2026-03-14-source-library-adapter-capability-remediation`: capability/fallback assertions landed; real site-entry probes remain open.
- `backend-core`: route drift guard landed; future route changes must refresh snapshot and docs.

Not closed, evidence refreshed only:

- graph 3D / node standardization / graph editing topics.
- ops-frontend graph/API/Storybook/launcher topics.
- backend-docs route/API snapshot topics.

## Next Agent Wave

Run these as separate branches only after `codex/devdocs-integration-2026-05-22` is accepted as the new baseline.

1. `codex/devdocs-lancedb-runtime-smoke`
   - Scope: install or use optional LanceDB runtime, replay local_index keyword/vector/hybrid with real table behavior.
   - Gate: `test_local_index_service_unittest.py` plus a recorded runtime smoke artifact.

2. `codex/devdocs-search-provider-container-replay`
   - Scope: rerun SearXNG/YaCy container smoke and prove explicit trace fields in real replay output.
   - Gate: search provider adapter tests plus replay artifact under `automation-runs/search-provider-replay/`.

3. `codex/devdocs-graph-frontend-e2e`
   - Scope: provide current GraphPage e2e/visual evidence for force3d and curated graph handoff paths.
   - Gate: frontend Playwright graph spec, or explicit environment blocker with screenshot/log evidence.

4. `codex/devdocs-storybook-launcher-gates`
   - Scope: run `storybook:build`, verify Storybook MCP configuration, and refresh launcher-first ops flow.
   - Gate: frontend build/storybook evidence or documented dependency blocker.

5. `codex/devdocs-source-library-real-probes`
   - Scope: stable fixture for source_library real site-entry probe and anti-bot/transport resilience.
   - Gate: source_library targeted pytest plus recorded fixture input/output.

6. `codex/devdocs-backend-schema-contracts`
   - Scope: extend backend-docs route map from route existence to request/response schema surface.
   - Gate: generated schema inventory plus contract tests.

## Merge Policy

- Merge docs-only branches first unless they move files out of `CURRENT_DEV`; archive moves require explicit evidence.
- Merge code-bearing branches only with a focused test gate.
- After each merge, rerun:
  - `git diff --check main...HEAD`
  - changed-doc Markdown link check
  - the lane-specific pytest or frontend gate
- If a lane only refreshes evidence, keep the topic in `CURRENT_DEV` and record the blocker instead of archiving.
