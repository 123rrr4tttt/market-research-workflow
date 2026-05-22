# Graph Handoff Evidence Pack (2026-05-22)

- Worktree: `/Users/wangyiliang/market-research-workflow.worktrees/graph-handoff-e2e`
- Branch: `codex/devdocs-wave3-graph-handoff-e2e`

## Result

Status: `partial closure / API route handoff proven`.

This lane proves the backend route-level flow for curated graph evidence handoff:

1. save curated draft;
2. submit curated graph;
3. build `graph_evidence_pack.v1`;
4. build reporting and writing `graph_handoff.v1`;
5. persist the handoff into the workflow graph run store;
6. list and replay the persisted handoff.

The GraphPage UI owner remains open. No frontend files were changed in this lane, so GraphPage e2e was not rerun here.

## Contract Anchors

- API route: `main/backend/app/api/workflow_graph.py`
- Curated service: `main/backend/app/services/workflow_graph/curated_service.py`
- Handoff store: `main/backend/app/services/workflow_graph/handoff_store.py`
- API test: `main/backend/tests/integration/test_workflow_graph_api_unittest.py::WorkflowGraphApiIntegrationTestCase::test_curated_api_handoff_round_trip_uses_service_pack_and_run_store`
- Unit tests:
  - `main/backend/tests/unit/test_workflow_graph_curated_service_unittest.py`
  - `main/backend/tests/unit/test_workflow_graph_handoff_store_unittest.py`

## Proven Fields

The route-level evidence asserts these stable fields:

- evidence pack: `contract_version`, `selected_nodes`, `relations`, `provenance.source`
- handoff payload: `contract_version`, `owner`, `producer`, `consumer`, `handoff_mode`, `evidence_pack`
- reporting consumer: `report_generate_request.topic`, `report_generate_request.sources`
- writing consumer: `keyword_card_request.sources`, `keyword_card_request.context.graph_context`
- persistence: `persistence.backend_marker`, run-level handoff listing, replay result, `handoff.replayed` event

## Validation

```bash
cd /Users/wangyiliang/market-research-workflow.worktrees/graph-handoff-e2e/main/backend
.venv311/bin/python -m pytest -q tests/unit/test_workflow_graph_curated_service_unittest.py tests/unit/test_workflow_graph_handoff_store_unittest.py tests/integration/test_workflow_graph_api_unittest.py
```

Result: `31 passed, 11 warnings`.

Additional gates are recorded in [`validation.json`](./validation.json).

## Remaining Risk

- This does not prove GraphPage submits its local draft into `/api/v1/workflow-graph/curated/{graph_id}/draft`.
- This does not decide whether GraphPage or a separate workflow-graph screen owns the curated submit and first-consumer trigger.
- This does not archive the graph editing/reporting CURRENT_DEV topic.
