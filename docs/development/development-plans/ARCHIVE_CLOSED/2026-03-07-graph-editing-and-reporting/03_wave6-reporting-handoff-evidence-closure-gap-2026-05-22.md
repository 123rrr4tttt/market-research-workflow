# Wave6 Reporting Handoff Evidence and Closure Gap (2026-05-22)

## Result

Status: `partial closure / reporting handoff UI trigger proven`.

This Wave6 lane updates the Graph Editing and Reporting topic after the Wave4 GraphPage curated consumer and the Wave5 clue-chain graph UI landed. The old status that treated GraphPage as having no curated workflow bridge is now stale.

Implemented in this worktree:

- `GraphPage.tsx` keeps the existing local draft -> curated draft -> curated submit flow.
- The frontend API domain now exposes evidence-pack, reporting handoff, and writing handoff wrappers for `/api/v1/workflow-graph/curated/{graph_id}`.
- GraphPage builder mode now includes a reporting topic input and a reporting handoff trigger.
- The focused GraphPage e2e verifies that the UI sends `topic` to `/curated/{graph_id}/handoff/reporting` and receives a `graph_handoff.v1` payload backed by `workflow_graph.run_store`.

## State Matrix

| Layer | Wave6 state | Evidence | Remaining gap |
| --- | --- | --- | --- |
| Editable object boundary | `needs update / partial` | Backend object kinds exist; GraphPage owns a narrow curated bridge | Full GraphPage data-source migration remains out of scope |
| Draft and sync contract | `needs update / partial` | GraphPage e2e covers local draft -> curated draft -> submit | Conflict-category UX still falls back to generic error handling |
| Audit, rollback, version | `not sealed` | Backend audit/rollback/revision APIs exist | GraphPage audit and rollback controls are not exposed |
| Evidence pack | `backend sealed / UI indirect` | Backend route tests prove `graph_evidence_pack.v1`; reporting handoff routes through that pack | No standalone GraphPage evidence-pack preview |
| Reporting handoff | `Wave6 proven` | GraphPage e2e covers reporting handoff trigger and payload | No full report-generation page navigation from this button |
| Writing handoff | `backend/API-client only` | Backend route tests and frontend wrapper exist | No GraphPage writing handoff button or writing-page pull evidence |
| Clue-chain graph | `adjacent` | Clue-chain GraphPage UI exists | Not yet mapped as curated graph input or downstream evidence attachment |

## Minimal Plan

1. Keep GraphPage as the narrow owner for local draft -> curated graph submit -> reporting handoff.
2. Treat report handoff generation as a prepared backend bridge, not as raw UI graph export.
3. Do not archive this topic yet. The next closure pass should choose one of:
   - add audit/rollback UI and conflict-specific messaging;
   - add writing handoff UI or prove writing-page pull ownership;
   - explicitly document clue-chain graph output as separate from curated graph governance.
4. Leave shared indexes unchanged in this lane to avoid cross-worktree conflicts.

## Validation

Commands run from `/Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave6-graph-editing-reporting`:

```bash
npm --prefix main/frontend-modern ci
npm --prefix main/frontend-modern run lint
npm --prefix main/frontend-modern run test:e2e -- tests/e2e/graphpage.spec.ts -g "graph builder submits"
npm --prefix main/frontend-modern run build
main/backend/.venv311/bin/python -m pytest -q main/backend/tests/integration/test_workflow_graph_api_unittest.py::WorkflowGraphApiIntegrationTestCase::test_curated_api_handoff_round_trip_uses_service_pack_and_run_store
```

Observed results:

- frontend install: `381 packages`, `2 moderate severity vulnerabilities` reported by `npm audit`.
- frontend lint: passed.
- focused GraphPage e2e: `1 passed`.
- frontend build: passed.
- backend handoff round-trip integration test: `1 passed`, with existing FastAPI/Pydantic deprecation warnings.

## Closure Decision

Do not archive. Wave6 closes the reporting handoff trigger gap, but the topic remains in `CURRENT_DEV` because governance UX, writing handoff ownership, and clue-chain-to-curated mapping are not sealed.
