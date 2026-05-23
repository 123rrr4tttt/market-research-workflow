<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-05-22-clue-chain-investigation-tool/05_wave16_closure_split-2026-05-22.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-05-22-clue-chain-investigation-tool/05_wave16_closure_split-2026-05-22.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Wave16 Clue Chain Closure Split

Date: 2026-05-22
Status: `wave16_closure_split` / `repo_slice_closed` / `successors_required`
Branch: `codex/devdocs-wave16-clue-chain-closure-split`

This note splits the Clue Chain CURRENT_DEV entry into a closed repo-controlled implementation slice and named successor work. The entry should no longer be read as one undifferentiated `partial`: Wave5 landed and verified the warehouse-local implementation, while live provider reliability, production graph-submit conflict behavior, and broader UI regression remain separate follow-up scopes.

## Closure Decision

- Repo-controlled Wave5 slice: closed for backend service/store, typed API, deterministic source-library hop, fixture-gated external-search hop, agent no-silent-promote guard, graph handoff payload generation, frontend API/client wiring, and mocked GraphPage review flow.
- Wave16 contract guard: added an API integration test that proves the external-search API path is fixture-gated by default, review-only, and does not perform graph mutation.
- Shared index action: none in this worker branch. The supervisor/integration branch should decide whether to mark this topic as `archive candidate` or create successor rows.
- Archive candidate rule: the original Wave5 implementation entry is a topic-local archive candidate only after the successor scopes below are represented in shared indexes or in a dedicated successor directory. Do not migrate this directory from the worker branch.

## Closed Implementation Surface

| Surface | Closed evidence | Current boundary |
|---|---|---|
| Core state/store | `main/backend/app/services/clue_chains/service.py`, `store.py`, `contracts.py`; `main/backend/tests/unit/test_clue_chain_service_unittest.py` | Durable repo-local state model and transition rules are covered by unit tests. |
| Typed API | `main/backend/app/api/clue_chains.py`, `main/backend/app/contracts/schemas/clue_chains.py`; `main/backend/tests/integration/test_clue_chains_api_unittest.py` | Create/list/detail/expand/decision/close routes have explicit envelope response models. |
| Source-library hop | `main/backend/app/services/clue_chains/source_library_expansion.py`; `main/backend/tests/unit/test_clue_chain_source_library_expansion_unittest.py` | Deterministic fixture/source-item expansion is closed; broader human review remains outside this topic. |
| External-search fixture hop | `main/backend/app/services/clue_chains/external_search_expansion.py`; `main/backend/tests/unit/test_clue_chain_external_search_expansion_unittest.py` | Default path is fixture-gated and replayable. Live provider quality is not claimed. |
| Agent guard | `main/backend/tests/unit/test_agent_core_clue_chain_tool_unittest.py` | `chain.expand` may collect evidence/candidates, but promotion still requires a decision. |
| Graph handoff payload | `main/backend/app/services/clue_chains/graph_integration.py`; `main/backend/tests/unit/test_clue_chain_graph_integration_unittest.py` | Evidence-backed mutation/handoff payloads are generated; production submit conflict behavior remains successor work. |
| Frontend GraphPage mock path | `main/frontend-modern/src/pages/graph/clueChainClient.ts`, `ClueChainInspector.tsx`, `tests/e2e/graph-clue-chain.spec.ts` | Mocked create/expand/review/evidence drawer path is covered; broad visual/runtime matrix remains successor work. |

## Wave16 API Contract Guard

New focused assertion:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/integration/test_clue_chains_api_unittest.py -k fixture_gated
```

The test `test_external_search_api_contract_stays_fixture_gated_and_review_only` verifies:

- `POST /api/v1/clue-chains/{chain_id}/expand` with `mode=external_search` returns typed API data, not ad hoc route-local shape.
- Provider trace records `fixture_gate=true`, `network_allowed=false`, `live_enabled=false`, and `trace_context.api=clue_chains.expand`.
- Candidates remain `pending`, require review, and carry `promotion_allowed=false`.
- The response contains no direct graph edges and the hop trace records `graph_mutation_performed=false`.

## Successor Plans

### Successor A: Live Provider Reliability

Status: `successor_required` / `external_blocked`

Scope:

- Run explicit opt-in live provider probes for configured SearXNG / YaCy / project search adapters.
- Record provider name, query, params, retry outcome, raw count, normalized count, duplicate count, and blocked reason.
- Compare live output against fixture contract without using live provider calls in default tests.

Blocker:

- No stable live provider endpoint and public-network replay acceptance is recorded in this branch.

Minimum gate:

```bash
CLUE_CHAIN_LIVE_PROVIDER=1 PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_clue_chain_external_search_expansion_unittest.py -k live
```

The exact command may change when the live provider harness lands; the successor must keep default CI fixture-only.

### Successor B: Production Graph-Submit Conflict Handling

Status: `successor_required` / `conflict_boundary_open`

Scope:

- Decide whether Clue Chain graph output is submitted directly to curated graph, staged as a handoff, or reviewed inside Graph Editing governance.
- Carry `base_revision` / conflict token from curated graph state into any production submit path.
- Surface conflict responses in UI as sync/reload/merge choices instead of destructive retry.

Blocker:

- Wave5 closed payload generation, not production submit. Conflict-specific frontend handling belongs with the Graph Editing governance lane and must not be inferred from handoff payload tests.

Minimum gate:

- One backend or API contract test proving stale revision returns the project conflict envelope.
- One UI or client test proving conflict response is visible and does not silently retry a destructive submit.

### Successor C: Broader UI / Visual Regression

Status: `successor_required` / `ui_matrix_open`

Scope:

- Extend beyond the mocked GraphPage Clue Chain e2e into visual/runtime coverage for empty graph, dense graph, selected nodes, blocked external search, candidate reviewed, and evidence drawer states.
- Keep GraphPage Clue Chain UI componentized so future graph-editing and frontend migration branches do not reintroduce large merge conflicts.

Blocker:

- Wave5 evidence proves a mocked happy/review path, not a broad visual or live-runtime matrix.

Minimum gate:

- `main/frontend-modern/tests/e2e/graph-clue-chain.spec.ts` plus one visual/runtime route check for the blocked/provider and reviewed-candidate states.

## Supervisor Handoff

- Keep this worker branch topic-local: do not edit `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`, `STATUS_AUDIT_2026-04-07.md`, `development-plans/INDEX.md`, `README.md`, or `MERGED_OVERVIEW.md`.
- Integration branch may update shared indexes with `[wave16_verified]` and either keep this directory as `partial + successor_required` or move the closed Wave5 slice to archive after successor rows are created.
- The intended post-integration wording is: repo slice closed; residuals are `external_blocked`, `conflict_boundary_open`, and `ui_matrix_open`.

## Validation

Worker validation commands:

```bash
python3 scripts/check_current_dev_wave16_plan.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 scripts/check_current_dev_status_evidence.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/integration/test_clue_chains_api_unittest.py -k fixture_gated
git diff --check
```
