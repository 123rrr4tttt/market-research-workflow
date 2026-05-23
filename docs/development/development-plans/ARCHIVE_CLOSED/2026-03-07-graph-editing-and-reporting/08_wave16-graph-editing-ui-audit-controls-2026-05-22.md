# Wave16 Graph Editing UI Audit Controls (2026-05-22)

Status: `mocked UI controls landed / live audit durability remains open`.

This Wave16 worker adds a product-facing, testable GraphPage control surface for the audit readback and rollback gap identified by Wave11, Wave12, and Wave15. It does not claim live tenant audit-log durability or production graph edit closure.

No shared navigation indexes were edited in this lane. `main/backend/scripts/workflow_graph_smoke_local.py` was not touched.

## Code Added

- `main/frontend-modern/src/lib/api/endpoints.ts`
  - adds workflow graph endpoints for curated rollback, curated audit listing, and handoff replay.
- `main/frontend-modern/src/lib/api/domains/graph-workflow.ts`
  - adds typed wrappers for `rollbackWorkflowGraphCuratedState`, `listWorkflowGraphCuratedAudits`, and `replayWorkflowGraphHandoff`.
- `main/frontend-modern/src/pages/GraphPage.tsx`
  - adds `读取 Audit`, rollback target/reason inputs, `执行 Rollback`, audit list readback, and handoff replay controls.
  - audit readback can fill a rollback target from the latest submit audit record.
  - rollback re-reads audits after submit so the UI has a visible audit readback after rollback.
- `main/frontend-modern/tests/e2e/graphpage.spec.ts`
  - extends the mocked GraphPage workflow through submit, audit list, rollback, second audit readback, reporting handoff, and handoff replay.
- `main/backend/tests/integration/test_workflow_graph_api_unittest.py`
  - adds API contract coverage for curated rollback and curated audit readback.
- `main/backend/tests/unit/test_graph_editing_audit_durability_unittest.py`
  - updates the Wave15 gate expectation now that static UI controls exist: complete UI evidence can be recorded, but live DB evidence remains required for closure.

## Validation

Commands run from `/Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave16-graph-editing-ui-audit-controls`:

```bash
npm ci
```

Observed result:

```text
added 381 packages, and audited 382 packages
2 moderate severity vulnerabilities reported by npm audit
```

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_graph_editing_audit_durability_unittest.py main/backend/tests/integration/test_workflow_graph_api_unittest.py
```

Observed result:

```text
33 passed, 11 warnings, 28 subtests passed
```

```bash
npm --prefix main/frontend-modern run lint -- --quiet
npm --prefix main/frontend-modern run test:e2e -- tests/e2e/graphpage.spec.ts --reporter=line
```

Observed result:

```text
lint: passed with no output
graphpage e2e: 5 passed
```

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_graph_editing_audit_durability.py --format text
```

Observed result:

```text
status=passed
readiness_state=repo_local_validated_live_gaps_open
closure_claim=False
repo_local_audit_readback_validated=True
graphpage_audit_controls_validated=False
live_db_audit_durability_validated=False
graphpage_audit_rollback_readback_ui=ready_not_run passed=True validated=False
```

```bash
python3 scripts/check_current_dev_wave16_plan.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 scripts/check_current_dev_status_evidence.py
git diff --check
```

Observed result:

```text
wave16 plan: OK wave16_current_dev_plan=passed
CURRENT_DEV evidence: OK current_dev_status_evidence=passed entries=34 counts=partial:34,not_closed:0,no_closure_claim:0
git diff --check: passed with no output
```

## Remaining Boundary

- GraphPage live-backend evidence is still not recorded: the new controls are covered by mocked E2E only.
- Live tenant DB audit durability remains open: submit, rollback, audit list, and handoff replay still need readback from persistent tenant storage.
- Production graph edit operations and tenant/project audit scoping remain outside this worker lane.

Do not archive this topic from this slice. The UI control surface is now present and testable, but live UI and live DB evidence are still required before final Graph Editing and Reporting closure.
