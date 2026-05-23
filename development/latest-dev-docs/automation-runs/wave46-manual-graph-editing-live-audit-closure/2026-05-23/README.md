# Wave46 manual graph editing live-audit closure

Date: 2026-05-23

Target: `development-plans/2026-03-07-graph-editing-and-reporting`

Purpose: close the remaining external blocker for live tenant DB audit durability, persistent handoff replay readback, and tenant/project scoping.

## Evidence

- Live API graph id: `cg-wave46-live-audit-20260523`
- Project: `demo_proj`
- Actor: `wave46.manual`
- Backend: `localhost:8000`
- PostgreSQL: `localhost:5432/postgres`

The live run created two submit audit records, rejected a stale rollback with a `version_conflict`, accepted a rollback to `cver-wave46-baseline`, and read the rollback back from a fresh audit/sync/get sequence.

The DB readback used the real tables declared in `main/backend/app/models/entities.py`:

- `public.ingest_config`
- `public.workflow_graph_runs`
- `public.workflow_graph_events`

The persistent readback showed:

- curated graph revision `3`
- curated audit write order `submit,submit,rollback`
- fresh audit API order `rollback,submit,submit`
- rollback project key `demo_proj`
- rollback actor `wave46.manual`
- cross-project `default` lookup had no matching graph row and returned API `NOT_FOUND`
- handoff run `handoff-cg-wave46-live-audit-20260523` had events `handoff.persisted,handoff.replayed`
- handoff audit project keys were `demo_proj,demo_proj`

## Gate

Run from repo root:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/check_graph_editing_audit_durability.py \
  --format json \
  --live-db-audit-evidence-json development/latest-dev-docs/automation-runs/wave46-manual-graph-editing-live-audit-closure/2026-05-23/live_evidence.json \
  --allow-live-closure-claim
```

Expected result after this wave: `status=passed`, `readiness_state=closed`, `closure_claim=true`, `live_tenant_db_audit_open=false`.
