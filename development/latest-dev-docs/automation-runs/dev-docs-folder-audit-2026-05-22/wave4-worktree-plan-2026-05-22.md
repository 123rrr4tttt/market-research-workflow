# Wave4 Worktree Plan And Integration Status

Run date: 2026-05-22 PST

Status: integrated. This file records the 10-agent Wave4 branch tree, merge order, supervisor reconciliation, validation state, and remaining blockers after integration.

## Inputs

- [development/latest-dev-docs/README.md](../../README.md)
- [development/latest-dev-docs/MERGED_OVERVIEW.md](../../MERGED_OVERVIEW.md)
- [audit README](./README.md)
- [wave3-worktree-plan-2026-05-22.md](./wave3-worktree-plan-2026-05-22.md)
- [wave4-integration-risk-review-2026-05-22.md](./wave4-integration-risk-review-2026-05-22.md)

## Baseline

- Baseline branch: `codex/devdocs-supervisor-seed` after Wave3 integration at `f785196`.
- Integration branch: `codex/devdocs-wave4-integration-2026-05-22`.
- Worktree root: `/Users/wangyiliang/market-research-workflow.worktrees`.
- Supervisor rule: each agent edited only its assigned worktree, did not push, ran lane gates, and returned `结果/改动文件/验证状态/风险/commit`.
- Integration result: all 10 Wave4 branches were merged into the integration branch; shared docs indexes were reconciled by preserving every landed evidence entry and residual blocker.

## Wave4 Branch Matrix

| Lane | Branch | Commit | Status | Result | Gate evidence | Residual blocker |
|---|---|---:|---|---|---|---|
| A | `codex/devdocs-wave4-schema-workflow-dynamic` | `2206d95` | integrated | Typed the remaining 17 `workflow_graph.py` dynamic JSON routes with conservative `ApiEnvelope[dict[str, Any]]`. | Agent workflow_graph suite passed; supervisor backend focused suite passed. | Payload internals remain broad dict schemas. |
| B | `codex/devdocs-wave4-schema-writing-search-small` | `98e96fc` | integrated | Typed remaining writing/search/market/reports/indexer JSON 200 schemas; kept markdown export as non-JSON. | Agent focused suite passed; supervisor backend focused suite passed. | Payload internals remain broad dict schemas for small legacy modules. |
| C | `codex/devdocs-wave4-schema-discovery-project` | `42cd7a9` | integrated | Typed discovery and project_customization 200 schemas. | Agent focused suite passed; supervisor backend focused suite passed. | Payload internals remain broad dict schemas. |
| D | `codex/devdocs-wave4-schema-auth-agent-web` | `f905794` | integrated | Typed codex_auth, agent_chat, agent_sessions, and `/api/v1/maps/usa`; stream/redirect behavior remains explicit. | Agent focused suite passed; supervisor backend focused suite passed. | OAuth/browser-flow tests still require isolated token sink settings. |
| E | `codex/devdocs-wave4-graphpage-curated-consumer` | `1a14031` | integrated | Wired GraphPage builder as the first curated workflow-graph UI consumer for save, submit, and sync. | Supervisor GraphPage e2e passed: `4 passed`. | This is a narrow builder consumer, not full GraphPage data-source migration or handoff UI. |
| F | `codex/devdocs-wave4-source-library-replay-scaleout` | `8fe44c0` | integrated | Added 45-site historical `demo_proj` replay manifest and skip-safe default replay gate. | Supervisor default replay passed with 45 targets, 40 enabled, 5 policy-skipped, public network disabled. | Public 45-site replay and relevance review still require explicit network-enabled run. |
| G | `codex/devdocs-wave4-frontdoor-router-hardening` | `39a453f` | integrated | Added high-JS/browser-render routing intent, crawler-first routing preservation, and backend tri-state projection. | Supervisor backend focused suite passed. | Real browser-render coverage across public high-JS sites is not proven; frontend dashboard UI not changed. |
| H | `codex/devdocs-wave4-frontend-runtime-visual` | `27300b7` | integrated | Added runtime visual Playwright gate and screenshot evidence for shell/theme/locale/topology. | Supervisor `check:runtime-visual` passed: `1 passed`; frontend lint passed. | Desktop mocked API evidence only; mobile visual matrix remains open. |
| I | `codex/devdocs-wave4-docs-status-sync` | `585b811` | integrated | Seeded Wave4 status skeleton and top-level navigation links. | Changed-doc link checks and `git diff --check` passed after supervisor reconciliation. | None; skeleton was replaced by this integrated status. |
| J | `codex/devdocs-wave4-integration-review` | `89062a5` | integrated | Added pre-merge integration risk review and gate checklist. | Docs-only check passed; used as supervisor checklist. | Review artifact is not implementation proof. |

## Supervisor Reconciliation

- Regenerated [API_SCHEMA_INVENTORY_2026-05-22.md](../../backend-docs/B_API/API_SCHEMA_INVENTORY_2026-05-22.md) after all schema lanes landed.
- OpenAPI `/api/v1` operations stayed at 253.
- Explicit FastAPI `response_model` operations increased from 206 after Wave3 to 248.
- Untyped OpenAPI 200 response schemas decreased from 46 after Wave3 to 0.
- Updated `main/backend/scripts/generate_api_schema_inventory.py` and its contract test wording so the inventory no longer describes untyped 200 routes as an active gap.

## Supervisor Validation

| Gate | Status | Evidence |
|---|---|---|
| `git diff --check` | passed | no whitespace/conflict-marker errors |
| changed Markdown links | passed | `ALL_CHANGED_DOC_LINKS_OK files=13` |
| Python compile | passed | `PY_COMPILE_OK files=23` |
| backend focused pytest | passed | `72 passed, 15 warnings, 40 subtests passed` |
| schema inventory contract | passed | included in backend focused pytest; untyped 200 count is 0 |
| source-library 45-site default replay | passed | no-network skip-safe run passed; 45 targets, 40 enabled, 5 policy-skipped |
| GraphPage curated consumer e2e | passed | `npm --prefix main/frontend-modern run test:e2e -- tests/e2e/graphpage.spec.ts` -> `4 passed` |
| frontend runtime visual gate | passed | `npm --prefix main/frontend-modern run check:runtime-visual` -> `1 passed` |
| frontend topology contract | passed | `check:topology-platform` returned `status: ok` |
| frontend lint | passed | `npm --prefix main/frontend-modern run lint` |

## Remaining Work Tree

Wave4 closes the schema-surface blocker and lands the first GraphPage curated consumer, but it does not claim every historical plan is fully closed. Recommended next split:

| Next lane | Scope | Reason |
|---|---|---|
| `source-library-public-replay` | opt-in 45-site public replay | collect real public pass/fail/anti-bot/relevance classifications without making CI depend on the network |
| `graphpage-handoff-ui` | reporting/writing handoff UI | backend handoff and builder submit exist; user-facing handoff actions still need UI evidence |
| `frontdoor-browser-runtime` | real browser-render high-JS probes | Wave4 proves routing intent, not cross-site browser-render runtime success |
| `frontend-mobile-visual` | mobile visual/runtime matrix | Wave4 runtime visual evidence covers desktop only |
| `schema-data-tightening` | replace broad `dict[str, Any]` / `Any` where valuable | OpenAPI surface is typed, but many legacy payload internals remain conservative |
