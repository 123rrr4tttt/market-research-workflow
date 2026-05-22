# Development Docs Folder Audit And Landing Report

Run date: 2026-05-22 PST
Scope: `development/latest-dev-docs`, with emphasis on folder status, stale/current closure state, and development-plan landing candidates.

Related execution plans:

- [worktree-branch-plan.md](./worktree-branch-plan.md)
- [parallel-plan-tree-2026-05-22.md](./parallel-plan-tree-2026-05-22.md)

## Summary

This run used 10 parallel read-only subaudits plus one integration pass.

Status counts:

- `CURRENT_DEV` topics checked: 36.
- Fully closed inside `CURRENT_DEV`: 0.
- Not closed / partial current work: 21.
- Outdated or drifted: 11.
- Needs update / no closure claim / external gap: 3.
- Evidence insufficient: 1.

Landing completed in this run:

- Added standard `frontend-modern` documentation entry files.
- Added missing `development-plans/A_ARCHITECTURE` through `F_PLAN` index files.
- Added `CURRENT_DEV/main/index.md` compatibility entry for scanners that expect the `main/index.md` convention.
- Repaired obvious development-plan navigation drift and dead links.
- Added explicit SearXNG / YaCy provider trace metadata to search results and unit coverage.
- Added the first local-index `mode=keyword|vector|hybrid` contract slice across schema, service normalization, LanceDB adapter routing, and unit coverage.

## Folder Status

| Folder | Status | Evidence | Action |
|---|---|---|---|
| `root-plans` | current | `INDEX.md` points first to `main/`; no dead current-entry issue found | keep |
| `backend-core` | needs update | review docs note API/module count drift and remaining strict-mode / DB validation follow-ups | update backend-core merged docs and run backend tests before closure |
| `backend-docs` | outdated | merged docs remain March snapshots and review docs mark route/API map decay | mark old snapshots clearly or refresh from current `main/backend/app/api` |
| `ops-frontend` | not closed | main entry exists but graph/API/storybook/launcher closure state is incomplete | add closure notes for graph/API and plans for Storybook/launcher |
| `frontend-modern` | needs update, entry repaired | directory had material but no `INDEX.md` or `main/index.md` before this run | standard entry added; future frontend work should update this folder |
| `development-plans` | needs update, partially repaired | missing A-F indexes, dead links, stale `CURRENT_DEV/main index.md`, duplicate archive links | indexes and high-signal dead links repaired; remaining duplicates can be cleaned in a follow-up |
| `development-plans/ARCHIVE_CLOSED` | closed archive | archive index exists; one empty source-library entry was misleading | removed empty entry from archive index |
| `development-plans/ARCHIVE_RETIRED` | retired archive | no new broken entry found | keep |

## CURRENT_DEV Topic Matrix

| Topic | Status | Reason | Recommended next action |
|---|---|---|---|
| `2026-03-01-open-source-platform-integration` | not closed | partial implementation, some old ops/scrapyd paths drifted | update paths and rerun standardized backend gates |
| `2026-03-02-graph-3d-force-engine-parallel-migration` | outdated | doc drift against current graph implementation | refresh graph implementation map before closure |
| `2026-03-02-graph-node-standardization-a-then-b-plan` | outdated | no closure claim and schema assumptions drifted | rebase plan on current node schema |
| `2026-03-02-ingest-platformization-assessment` | not closed | platform chain exists but no production-level closure | attach current ingest contract evidence |
| `2026-03-02-meaningful-ingest-guardrails-plan` | outdated | `single_url.py` premise no longer matches code | remap to current ingest/frontdoor/source_library path |
| `2026-03-02-single-url-first-ingest-allocation-plan` | outdated | core anchor moved from `single_url.py` to current ingest/source_library chain | update doc and tests to current entry |
| `2026-03-02-source-time-window-smart-timestamp-plan` | not closed | some stats endpoints exist, several internal route claims do not | either implement missing routes or retire the old route claims |
| `2026-03-04-r41-openclaw-autodispatch` | needs update | external evidence gap | add local evidence map or keep as external-gap reference |
| `2026-03-05-oss-node-platform-io-plan` | not closed | runtime/replay exists but platform goal not closed | add execution/closure matrix |
| `2026-03-05-time-statistics-remediation-plan` | outdated | current stats code exists, legacy template/path assumptions drifted | refresh against `api/stats.py` and frontend-modern |
| `2026-03-07-crawler-source-expansion` | not closed | planning/tasklist state | execute or archive as deferred |
| `2026-03-07-docs-root-restructuring` | not closed | migration intent without closure | close with actual migration map |
| `2026-03-07-dual-frontend-workbench-topology` | outdated | code partially implements topology, docs remain pending | write closure evidence for current topology |
| `2026-03-07-frontend-i18n-theme-modularization` | outdated | i18n/theme code exists, docs still pending | add i18n/theme closure checklist |
| `2026-03-07-graph-editing-and-reporting` | not closed | graph draft/edit code exists but no closure | add graph evidence/reporting handoff test |
| `2026-03-07-ingest-digestion-and-long-cycle-automation` | needs update | no closure claim | add execution record before using as current plan |
| `2026-03-07-llm-service-and-agent-platformization` | outdated | platform code advanced beyond task docs | refresh with current agent/LLM routes |
| `2026-03-07-typed-knowledge-organization` | not closed | object model not fully closed | add schema/serialization contract evidence |
| `2026-03-07-writing-workbench-evolution` | outdated | workbench exists, old evolution tasks remain pending | separate implemented surface from future evolution |
| `2026-03-07-后续安排` | not closed | abstract planning split only | keep as planning or close after migration |
| `2026-03-08-llm-crawler-unified-frontdoor` | outdated | closure claims incomplete for current code | verify AT items against current frontdoor |
| `2026-03-09-agent-symbolic-batch-search-architecture` | not closed | brief/critic/retry work exists but not fully closed | add batch/search-mode idempotency tests |
| `2026-03-11-source-library-three-lane-architecture` | outdated | lane design mostly landed, legacy fallback evidence unclear | add final lane/fallback closure note |
| `2026-03-12-data-structured-service-modularization` | not closed | modularization partial | split remaining structured ingest boundary or document blocker |
| `2026-03-14-consumer-side-modularization` | not closed | consumer-side service layer incomplete | extract/read-only view service where safe |
| `2026-03-14-search-chain-source-library-mounting-audit` | not closed | mounting relation exists, governance not closed | add mounting priority regression |
| `2026-03-14-source-library-adapter-capability-remediation` | outdated | capability map still has pending AC items | finish capability/fallback assertions |
| `2026-03-14-time-semantics-density-merged-plan` | not closed | main entry valid but OPE/overlap gates remain | add closure doc for remaining gates |
| `2026-03-15-frontend-three-layer-rewrite` | not closed | partial three-layer rewrite with known AppShell/kernel gaps | close T1-T5 or keep blockers explicit |
| `2026-03-24-frontend-visual-layering` | evidence insufficient | placeholder/empty topic | add README/status or retire |
| `2026-03-25-source-library-ingest-minimal-migration` | not closed | AT-SLIM/AT-ITEM evidence exists, AT-EXT remains pending | finish AT-EXT or document deferral |
| `2026-04-02-claude-agent-high-fidelity-migration` | needs update | implemented evidence exists but topic still mixes current entry and closure material | split active diagnostics from completed records |
| `2026-04-07-parallel-agent-wave-orchestration` | not closed | execution framework, not closure | keep as active orchestration entry |
| `2026-05-14-global-vectorization-general-foundation` | not closed | first local-index mode contract slice landed; full vector/hybrid foundation still needs runtime validation | expand real LanceDB vector/hybrid runtime evidence next |
| `2026-05-14-local-open-search-provider-isolation` | needs update | much is implemented; explicit provider trace/regression evidence now landed | use provider trace in next closure replay |
| `MERGED_OVERVIEW` | outdated | summary-level drift | keep as navigation only or refresh from topic matrix |

## Landed Code-Or-Project Changes

Search provider trace:

- SearXNG and YaCy results now include:
  - `provider_route`
  - `provider_family`
  - `provider_auto_included`
  - `backend_trace`
- The fields explicitly mark SearXNG / YaCy as explicit local open-search providers and not part of `provider=auto`.

Local index mode contract:

- `LocalIndexQuery.mode` is normalized to `keyword`, `vector`, or `hybrid`.
- `LocalIndexSearchResult.to_dict()` now exposes `retrieval_mode`, `retrieval_family`, and `trace`.
- The LanceDB adapter now routes keyword to FTS, vector to vector search, and hybrid to hybrid/vector with keyword fallback.
- Unit coverage verifies supported mode preservation and unknown-mode normalization.

Documentation navigation:

- `frontend-modern/INDEX.md`
- `frontend-modern/main/index.md`
- `frontend-modern/main/MERGED_FRONTEND_MODERN.md`
- `development-plans/A_ARCHITECTURE/INDEX.md`
- `development-plans/B_API/INDEX.md`
- `development-plans/C_INGEST/INDEX.md`
- `development-plans/D_TEST/INDEX.md`
- `development-plans/E_OPS/INDEX.md`
- `development-plans/F_PLAN/INDEX.md`
- `development-plans/CURRENT_DEV/main/index.md`

## Next Landing Queue

1. Validate LanceDB vector/hybrid against a real optional-dependency runtime and record benchmark evidence.
2. Refresh backend-core API/route/project-key follow-ups against current code.
3. Add frontend graph/API/Storybook/launcher closure notes under `ops-frontend/F_PLAN`.
4. Split `2026-04-02-claude-agent-high-fidelity-migration` into completed records versus active diagnostics.
5. For broad implementation follow-up, use worktree branches per lane and merge through the supervisor worktree after each lane's gate passes.
