# Wave27 Graph Editing External-Blocked Decision (2026-05-23)

Status: `external_blocked`.

## Decision

Graph Editing and Reporting can leave `CURRENT_DEV` and move to `ARCHIVE_EXTERNAL_BLOCKED`.

Do not mark this topic `closed`: the repo-local backend, tenant-like fixture, conflict/rollback readback, and GraphPage UI gates are deterministic and green, but final audit durability still depends on live tenant DB evidence outside this local repo run.

## Repo-Local Evidence

- `main/backend/scripts/check_graph_editing_audit_durability.py`
  - validates curated submit, rollback, audit list, handoff persist/list/replay, and fresh service readback;
  - validates tenant-like audit trace readback and rollback metadata integrity;
  - validates stale rollback conflict marker preservation and accepted rollback readback;
  - now validates repo-local GraphPage audit readback, rollback, and handoff replay UI coverage through existing e2e anchors;
  - keeps `closure_claim=False` and `live_tenant_db_audit_open=True`.
- `main/backend/tests/unit/test_graph_editing_audit_durability_unittest.py`
  - covers the repo-local UI gate and the non-closing live evidence state.
- `main/frontend-modern/tests/e2e/graphpage.spec.ts`
  - covers submit -> audit readback -> rollback -> second audit readback -> reporting handoff -> handoff replay at the GraphPage surface.

## Current Gate Snapshot

Command:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_graph_editing_audit_durability.py --format text
```

Observed result:

```text
status=passed
readiness_state=repo_local_validated_live_gaps_open
closure_claim=False
repo_local_audit_readback_validated=True
tenant_like_fixture_audit_trace_validated=True
conflict_rollback_readback_validated=True
graphpage_audit_controls_validated=True
live_db_audit_durability_validated=False
live_tenant_db_audit_open=True
```

## External Blocker

Remaining acceptance requires live tenant DB evidence:

- run curated submit and rollback against a configured tenant DB and read audits back from a fresh session;
- run handoff persist/list/replay against persistent storage and read replay audit events back;
- verify tenant/project scoping for audit records under real persistence.

These are not repo-local deterministic blockers. They require configured tenant storage or a live backend environment, so this topic should not continue inflating `CURRENT_DEV` partial counts.

## Verification

Commands run from `/Users/wangyiliang/market-research-workflow`:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_graph_editing_audit_durability.py --format text
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_graph_editing_audit_durability_unittest.py
npm --prefix main/frontend-modern run test:e2e -- tests/e2e/graphpage.spec.ts -g "graph builder (submits|surfaces)" --reporter=line
```

Observed result:

```text
checker: status=passed, graphpage_audit_controls_validated=True, live_db_audit_durability_validated=False
pytest: 7 passed
graphpage focused e2e: 2 passed
```
