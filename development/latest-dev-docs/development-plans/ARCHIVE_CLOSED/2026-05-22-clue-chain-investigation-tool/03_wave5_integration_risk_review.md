# Wave5 Clue Chain Integration Risk Review

Date: 2026-05-22
Status: `pre_merge_review` / docs-only sidecar

This review is for the supervisor merge of the Wave5 Clue Chain branches. It does not implement Clue Chain behavior and should not be treated as closure evidence by itself.

## Inputs Reviewed

- [01_clue-chain-investigation-tool-plan-2026-05-22.md](./01_clue-chain-investigation-tool-plan-2026-05-22.md)
- `main/backend/app/contracts/api.py`
- `main/backend/app/main.py`
- `main/backend/app/api/__init__.py`
- `main/backend/app/api/workflow_graph.py`
- `main/backend/app/api/source_library.py`
- `main/backend/app/api/agent_sessions.py`
- `main/backend/app/api/agent_batch.py`
- `main/backend/app/services/workflow_graph/curated_service.py`
- `main/backend/app/services/workflow_graph/edit_contract.py`
- `main/backend/app/services/agent_runtime/capability_registry.py`
- `main/backend/app/services/agent_runtime/read_only_tools.py`
- `main/frontend-modern/src/lib/api/endpoints.ts`
- `main/frontend-modern/src/lib/api/domains/graph-workflow.ts`
- `main/frontend-modern/src/lib/api.ts`
- `main/frontend-modern/src/pages/GraphPage.tsx`

## Current Contract Baseline

| Surface | Current pattern | Clue Chain implication |
|---|---|---|
| API envelope | Newer routes should return `ok(...)` / `ApiEnvelope[...]`; `success_response(...)` is transitional. `/api/v1` JSON responses can be wrapped at runtime, but OpenAPI closure still requires typed `response_model`. | Every `/api/v1/clue-chains*` route needs explicit Pydantic request/response models. Do not rely on middleware wrapping as schema closure. |
| Router wiring | API routers are imported and included in `main/backend/app/api/__init__.py`, then mounted once in `main/backend/app/main.py`. | A new `clue_chains.py` router must be registered in `api/__init__.py`; otherwise tests that call app routes and OpenAPI inventory will miss it. |
| Schema inventory | `test_api_schema_inventory_contract_unittest.py` pins generated docs and summary counts, including zero untyped OpenAPI 200 operations. | Any new route changes operation counts. Regenerate `API_SCHEMA_INVENTORY_2026-05-22.md` after all backend API branches land, and update the pinned counts in the contract test intentionally. |
| Workflow graph provenance | Curated graph evidence packs preserve `source_uri` and a free-form `provenance` object. The edit contract rejects system-managed fields and bad graph shape, but does not require evidence-backed provenance. | Clue Chain promotion must enforce `chain_id`, `hop_id`, `evidence_id`, and `decision_id` before sending node/edge drafts into curated graph submit. Do not assume existing graph validation proves this requirement. |
| Source library search | Agent runtime `source_library.item.search` searches source-library item definitions and is read-only. Collection remains a higher-risk ingest/source-library path. | A `source_library_search` hop that claims evidence must either record catalog hits as `lead` evidence with explicit source scope, or call a bounded collection/index surface behind approval and fixtures. Catalog matches alone are not corroborated evidence. |
| Agent runtime tools | Current capabilities distinguish read-only tools, write/external collection, and approval-required workflow execution. | `chain.expand` should be modeled as a governed capability, not a generic read tool, because it writes hops/evidence/candidates and may start external search. |
| Frontend API | Endpoints are centralized in `endpoints.ts`; domain functions are re-exported from `lib/api.ts`. Graph workflow types and calls live in `domains/graph-workflow.ts`. | Prefer a new `domains/clue-chains.ts` and explicit exports from `lib/api.ts` to reduce merge conflicts with graph-workflow changes. |
| GraphPage UI | GraphPage already owns selected-node state, structured task submission, Curated graph draft/submit/sync controls, and a node inspector. | Clue Chain UI will conflict around selected-node actions, toolbar buttons, floating controls, and selected node card. Keep UI code small and componentized before supervisor merge. |

## Integration Risks

| Risk | Severity | Why it matters | Merge guard |
|---|---:|---|---|
| Service/API model boundary collapses into route-local dicts | High | Clue Chain has durable objects: chain, hop, evidence, candidate, decision, edge. Route-local dicts will make status transitions, replay, and provenance tests brittle. | Backend core branch should land a service and typed contract models before API/UI branches depend on it. API routes should be thin. |
| API schema inventory regresses to raw JSON or stale counts | High | Wave4 closed untyped 200 routes. New Clue Chain endpoints can silently reopen the same closure if they use `response_model=ApiEnvelope[dict[str, Any]]` everywhere or omit models. | Regenerate inventory once after all API branches merge; run the inventory contract and assert `untyped_openapi_200_operations == 0`. |
| Source-library hop overclaims evidence | High | The existing read-only search is catalog-level item matching. The plan requires source refs, document/chunk IDs, query text, and parser/search-template profile when available. | Tests must distinguish `lead` catalog evidence from collected/indexed evidence. Acceptance should require stored `ChainEvidence.source_ref` fields, not just a matched item title. |
| External search uses public network during default tests | High | The plan requires replayable evidence and fixture-gated provider tests. Network-dependent tests will be flaky and hard to review in parallel worktrees. | Default tests must use fixture providers and no public network. Live provider tests require an explicit opt-in env flag and must skip by default. |
| Agent can promote candidates without `ChainDecision` | High | The acceptance criteria explicitly forbid silent graph mutation by the agent runtime. Existing agent capabilities include high-risk write paths. | `chain.expand` may create hops/evidence/candidates only. Promotion to graph/frontier must go through the candidate decision endpoint and persist actor/reason. |
| Graph provenance is attached but not enforced | High | Existing workflow graph evidence packs preserve provenance if present, but current edit contract validates shape, not Clue Chain evidence ownership. | Promotion service must reject any node/edge promotion missing `ChainEvidence` provenance. Add tests for both accepted and rejected promotion payloads. |
| Curated graph revision conflicts during promotion | Medium | GraphPage and backend graph integration may save/submit curated drafts concurrently with `base_revision`. | Use explicit revision reads and conflict errors. In UI, surface conflict and sync instead of retrying destructive submit. |
| Frontend API/UI merge conflicts | Medium | `GraphPage.tsx`, `endpoints.ts`, `lib/api.ts`, and graph domain exports are likely touched by multiple branches. | Merge frontend API domain before GraphPage UI. Keep GraphPage changes limited to wiring and delegate inspector/review queue to new components. |
| Docs status moves to closed too early | Medium | This review is not implementation evidence. Multiple branches will create partial evidence. | Docs-status branch must merge last and keep status `需更新` or `not_closed` until all acceptance gates are linked. |
| Storage backend drift | Medium | The plan allows JSON/SQLite. Workflow graph curated state uses ingest config storage, while other parts use SQL models. Parallel branches may choose incompatible stores. | Supervisor should pick one first-cut store and normalize IDs/timestamps/statuses in one service before merging expansion branches. |
| Event naming fragments | Medium | Agent sessions, agent_batch, workflow graph handoff, and Clue Chain hops all emit events. Different branches may invent incompatible event names. | Reserve a minimal event vocabulary: `chain.planned`, `chain.search_started`, `chain.evidence_collected`, `chain.candidate_created`, `chain.decision_recorded`, `chain.blocked`, `chain.closed`. |

## Recommended Merge Order

1. Core storage and domain contracts: service, ID/status normalization, transition rules, and unit tests.
2. API contract branch: registered router, typed request/response models, create/list/detail/close/decision endpoints.
3. Source-library hop branch: bounded read/collection adapter, evidence persistence, dedupe behavior, fixture tests.
4. External-search hop branch: fixture provider, provider trace, no-network default gate.
5. Agent tool branch: `chain.expand` capability, event emission, no-silent-promote guard.
6. Graph integration branch: evidence-backed promotion into curated graph or handoff contract, with revision conflict handling.
7. Frontend API branch: endpoints, domain functions, exported types.
8. GraphPage UI branch: Create Chain action, inspector, candidate queue, evidence drawer, mocked e2e.
9. Docs status branch: reconcile all evidence links and residual blockers last.
10. Supervisor-only finalization: regenerate schema inventory once, resolve generated docs, run full validation matrix, then update status language.

## Conflict Resolution Strategy

- `API_SCHEMA_INVENTORY_2026-05-22.md` is generated. Prefer the supervisor-regenerated version after all API changes, not any individual branch copy.
- `main/backend/app/api/__init__.py` should be resolved by union of imports and `include_router(...)` lines, preserving existing router order where possible.
- `main/frontend-modern/src/lib/api/endpoints.ts` should keep Clue Chain under a new `clueChains` key rather than mixing into `workflowGraph`.
- `main/frontend-modern/src/lib/api.ts` should re-export Clue Chain domain functions and types as one contiguous block.
- `main/frontend-modern/src/pages/GraphPage.tsx` should not absorb all inspector markup. If branches conflict, keep state and handlers in GraphPage, but move reusable panels into `components` or a local subcomponent file.
- Documentation conflicts in `README.md`, `MERGED_OVERVIEW.md`, and `CURRENT_DEV/INDEX.md` should resolve by union and conservative status wording. Do not replace earlier Wave3/Wave4 evidence links.

## Minimal Validation Matrix

| Category | Required checks before supervisor closure |
|---|---|
| Backend unit | `cd main/backend && ./.venv311/bin/python -m pytest tests/unit/test_clue_chain*_unittest.py tests/unit/test_workflow_graph_edit_contract_unittest.py tests/unit/test_workflow_graph_curated_service_unittest.py tests/unit/test_agent_sessions_service_unittest.py` |
| Backend integration | `cd main/backend && ./.venv311/bin/python -m pytest tests/integration/test_clue_chain*_unittest.py tests/integration/test_workflow_graph_api_unittest.py tests/integration/test_agent_sessions_api_unittest.py` |
| Source/external gates | Run the Clue Chain source-library and external-provider tests with public network disabled by default; run any live/public probe only when explicitly opt-in and record skip/pass evidence. |
| Agent contract | Test that `chain.expand` creates a hop/evidence/candidate event trail but cannot write graph nodes or edges unless a `ChainDecision` exists. Include a negative bypass test. |
| API contract | `cd main/backend && ./.venv311/bin/python scripts/generate_api_schema_inventory.py`, then `cd main/backend && ./.venv311/bin/python -m pytest tests/contract/test_api_schema_inventory_contract_unittest.py`; assert zero untyped 200 operations and visible Clue Chain schemas. |
| Python compile | Compile changed Python files or run the repo's changed-file compile helper if present. At minimum, include the new API/service/contracts/tests. |
| Frontend lint | `cd main/frontend-modern && npm run lint` after all API/UI exports are merged. |
| Frontend topology | `cd main/frontend-modern && npm run check:topology-platform` if GraphPage or platform placement changed. |
| Frontend e2e | Add and run a mocked GraphPage Clue Chain e2e covering selected node to create chain, source-library hop result, candidate decision, and evidence drawer. Rerun `tests/e2e/frontend-runtime-visual.spec.ts` if GraphPage layout changes. |
| Docs links | Run changed Markdown link check for this plan directory plus top-level latest-dev-docs navigation after docs-status merge. |
| Diff hygiene | Run `git diff --check` after conflict resolution and after generated docs are refreshed. |

## Closure Rules

- Do not mark Clue Chain `已封口` until create/list/detail/expand/decision/close APIs, source-library hop, external-search fixture hop, agent no-silent-promote guard, graph provenance enforcement, frontend UI, and docs evidence all pass.
- A source-library catalog match can close only the `lead discovery` part, not the `evidence replay` part, unless it stores source refs and document/chunk or equivalent provenance.
- An external-search fixture pass does not prove live provider reliability. It only proves deterministic replay and contract handling.
- Graph promotion is not closed unless every promoted node and edge can be traced back to `ChainEvidence` and `ChainDecision`.
- Frontend closure needs a user-visible flow, not only API client exports.
- This review file should be linked as risk guidance, not as implementation evidence.
