# Wave5 Clue Chain Worktree Execution Plan

Date: 2026-05-22
Status: `not_closed` / `executing`
Scope: docs-status sync for Wave5 Clue Chain implementation.

This file is a planning and status-sync document. It does not claim code implementation has passed. Final pass/fail evidence must be filled by the supervisor after the implementation worktrees are merged and the relevant gates are rerun.

## Inputs

- [Clue Chain investigation tool plan](./01_clue-chain-investigation-tool-plan-2026-05-22.md)
- [CURRENT_DEV index](../INDEX.md)
- [latest-dev-docs README](../../../README.md)
- [MERGED_OVERVIEW](../../../MERGED_OVERVIEW.md)
- [Wave3 worktree plan and integration status](../../../automation-runs/dev-docs-folder-audit-2026-05-22/wave3-worktree-plan-2026-05-22.md)
- [Wave4 worktree plan and integration status](../../../automation-runs/dev-docs-folder-audit-2026-05-22/wave4-worktree-plan-2026-05-22.md)
- [Wave4 integration risk review](../../../automation-runs/dev-docs-folder-audit-2026-05-22/wave4-integration-risk-review-2026-05-22.md)

## Folder Status Sync

| Folder | Current state | Clue Chain / Wave5 action | Evidence rule |
|---|---|---|---|
| `root-plans` | current navigation entry; no Clue Chain ownership | no Wave5 edit expected | keep existing index as reference only |
| `backend-core` | updated, not globally closed | backend code lanes may add Clue Chain service/runtime implementation | do not mark closed until focused backend tests and compile pass after merge |
| `backend-docs` | API schema surface closed by Wave4 evidence | new Clue Chain API must update inventory only after API routes land | supervisor regenerates inventory after all API lanes merge |
| `ops-frontend` | not globally closed; runtime/frontend blockers remain explicit | no direct docs-status claim; GraphPage/agent-session evidence may later link here | runtime UI evidence must be real, not inferred from plan |
| `frontend-modern` | current entry repaired; Wave4 desktop visual gate exists | Wave5 frontend lanes add Clue Chain client and GraphPage UI | frontend lint/e2e/visual gates required after code merge |
| `development-plans` | partially closed current-plan registry | Clue Chain is `not_closed` / `executing`; Wave3/Wave4 status remains integrated evidence | keep Wave3/Wave4 closed evidence links; do not rewrite their pass/fail history |
| `automation-runs` | evidence archive for Wave2-Wave4 gates | Wave5 code lanes may add new evidence packages after implementation | branch-local notes are not closure evidence unless linked and gate-backed |
| `development-plans/ARCHIVE_CLOSED` | closed archive | no Clue Chain move | Clue Chain must stay in `CURRENT_DEV` until acceptance criteria pass |
| `development-plans/ARCHIVE_RETIRED` | retired archive | no Clue Chain move | only use for superseded historical plans |

## Wave3 / Wave4 Closure Position

The Wave3 and Wave4 documents are treated as closed execution records for those waves:

- Wave3 integrated status: [wave3-worktree-plan-2026-05-22.md](../../../automation-runs/dev-docs-folder-audit-2026-05-22/wave3-worktree-plan-2026-05-22.md)
- Wave4 integrated status: [wave4-worktree-plan-2026-05-22.md](../../../automation-runs/dev-docs-folder-audit-2026-05-22/wave4-worktree-plan-2026-05-22.md)
- Wave4 risk review: [wave4-integration-risk-review-2026-05-22.md](../../../automation-runs/dev-docs-folder-audit-2026-05-22/wave4-integration-risk-review-2026-05-22.md)

This Wave5 docs-status branch does not reopen their gate results. It only links to them as prior evidence and keeps their residual blockers visible where Clue Chain depends on graph, source-library, agent runtime, or frontend surfaces.

## Wave5 Branch Plan Tree

| Lane | Branch | Goal | Inputs | Outputs | Acceptance | Dependencies | Merge order |
|---|---|---|---|---|---|---|---|
| A | `codex/devdocs-wave5-clue-chain-core-storage` | Add durable Clue Chain domain models, storage service, status transitions, evidence/candidate/decision records. | Clue Chain plan sections 3, 5, 6; existing backend service/storage patterns. | Backend schemas/service/storage module and focused tests. | chain create/update/list/detail service tests pass; evidence refs are stable; status transitions reject invalid moves. | none | 1 |
| B | `codex/devdocs-wave5-clue-chain-api-contract` | Add `/api/v1/clue-chains` create/list/detail/expand/decision/close API surface using project envelope conventions. | Lane A service contract; API draft section 7; existing FastAPI envelope patterns. | API router, request/response schemas, route registration, contract tests. | focused API tests pass; OpenAPI inventory includes typed Clue Chain routes after supervisor regeneration. | A | 2 |
| C | `codex/devdocs-wave5-clue-chain-source-library-hop` | Implement bounded `source_library_search` expansion mode with replayable source refs and dedupe. | Lanes A-B; plan section 4.3; source_library resolver/search contracts. | source-library hop service, evidence writer, canonicalization tests. | fixture/default source-library hop creates `ChainEvidence` and `ChainCandidate`; no public network dependency. | A, B | 3 |
| D | `codex/devdocs-wave5-clue-chain-external-search-hop` | Implement fixture-gated `external_search` expansion with provider trace, retry budget, and no public-network default. | Lanes A-B; plan section 4.2; search provider trace work from Wave3/Wave4. | external-search hop mode, fixture provider tests, trace fields. | default tests use fixtures only; live/public run is opt-in; every result is stored as lead evidence with provider/query metadata. | A, B | 4 |
| E | `codex/devdocs-wave5-clue-chain-graph-integration` | Promote accepted candidates into graph nodes/edges only through evidence-backed decisions. | Lanes A-D; graph curated/handoff APIs; plan acceptance criteria. | graph integration adapter, promotion/merge logic, tests for evidence-backed nodes/edges. | promoted graph entities reference `ChainEvidence`; duplicate aliases merge before creating new nodes. | A, B, C or D | 5 |
| F | `codex/devdocs-wave5-clue-chain-agent-tool` | Add controlled `chain.expand` agent tool/event contract and prevent silent graph promotion. | Lanes A-D; plan section 4.1; agent runtime/session patterns. | agent tool schema, runtime handler, session events, tests. | agent can request expansion; candidate promotion requires `ChainDecision`; session emits planned/search/evidence/blocked/closed events. | A, B, C, D | 6 |
| G | `codex/devdocs-wave5-clue-chain-frontend-api` | Add frontend API domain/types for Clue Chain endpoints. | Lane B API schemas; `frontend-modern` API domain conventions. | TypeScript types, API client methods, mocked contract tests where available. | type/lint gate passes; frontend API maps envelope data and errors without ad hoc shapes. | B | 7 |
| H | `codex/devdocs-wave5-clue-chain-graph-ui` | Add GraphPage create-chain action, Chain Inspector, evidence drawer, and candidate review queue. | Lanes E-G; GraphPage current consumer from Wave4; frontend UX plan section 8. | GraphPage UI additions and Playwright/mock evidence. | e2e proves seed node to chain creation/inspector/candidate decision path; no hidden uncertainty in UI states. | E, G; F for session events when surfaced | 8 |
| I | `codex/devdocs-wave5-clue-chain-docs-status` | Keep docs/index/status synchronized and mark Clue Chain as executing without fabricating code evidence. | Current docs tree; Wave3/Wave4 evidence; this plan. | Clue Chain index, Wave5 plan, updated README/MERGED_OVERVIEW/CURRENT_DEV/development-plans indexes. | changed Markdown links pass; `git diff --check` passes; commit contains docs only. | none; final reconciliation depends on all lanes | 10 |
| J | `codex/devdocs-wave5-clue-chain-integration-review` | Review integration risks, merge order, and missing gates before supervisor closure. | Lanes A-H outputs, Wave4 risk review pattern. | risk-review document and final gate checklist. | review lists blockers and required gates; it is not implementation proof. | A-H preferred | 9 |

## Supervisor Fill-In Required After Code Merge

The following fields must remain pending until the supervisor merges implementation branches and reruns gates:

| Evidence item | Filled by | Required before closure |
|---|---|---|
| final lane commit IDs | supervisor integration pass | all implementation branches merged or explicitly skipped |
| Clue Chain API OpenAPI inventory | supervisor after API merge | generated inventory and contract test pass |
| backend focused pytest counts | supervisor after backend merge | relevant clue-chain/source-library/search/graph/agent tests pass |
| Python compile result | supervisor after backend merge | changed Python files compile |
| source-library hop evidence | source-library lane plus supervisor rerun | fixture/default run stores evidence and candidates |
| external-search fixture gate | external-search lane plus supervisor rerun | public network disabled by default; live run opt-in only |
| graph promotion evidence | graph integration lane plus supervisor rerun | promoted node/edge references `ChainEvidence` |
| agent runtime safety evidence | agent-tool lane plus supervisor rerun | agent cannot bypass `ChainDecision` |
| frontend lint/e2e/visual evidence | frontend lanes plus supervisor rerun | GraphPage UI path is tested after all frontend branches merge |
| final docs link check | docs-status or supervisor final pass | changed Markdown links and `git diff --check` pass after conflicts resolve |

## Non-Closure Claims

- This document does not claim the Clue Chain API exists.
- This document does not claim the graph promotion path is implemented.
- This document does not claim external search is live-tested.
- This document does not claim frontend UI is implemented or visually verified.
- This document does not move Clue Chain to `ARCHIVE_CLOSED`.

## Canonical-Copy Rule

The Clue Chain plan and Wave5 status live under `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-05-22-clue-chain-investigation-tool/`. Any branch-specific evidence created later should be linked from this directory and from the top-level `latest-dev-docs` indexes. No Clue Chain planning document should remain as an unindexed unique copy outside `development/latest-dev-docs`.
