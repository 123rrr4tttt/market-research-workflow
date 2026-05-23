# Wave46 Manual Live Audit Closure

Date: 2026-05-23

Status: `closed`

## Decision

`2026-03-07-graph-editing-and-reporting` is no longer external-blocked. The remaining blocker from Wave27 was live tenant DB audit durability, persistent handoff replay readback, and tenant/project scoping. Wave46 ran the live API path against localhost backend plus PostgreSQL and produced fresh API and DB readback evidence.

## Evidence

- Automation run: `development/latest-dev-docs/automation-runs/wave46-manual-graph-editing-live-audit-closure/2026-05-23/`
- Live evidence JSON: `live_evidence.json`
- Closure gate JSON: `closure_gate.json`
- Gate decision: `status=passed`, `readiness_state=closed`, `closure_claim=true`, `live_tenant_db_audit_open=false`

## Runtime Facts

- Graph id: `cg-wave46-live-audit-20260523`
- Project key: `demo_proj`
- Actor: `wave46.manual`
- Curated graph revision after accepted rollback: `3`
- API audit list: `rollback,submit,submit`
- DB audit write order: `submit,submit,rollback`
- Stale rollback was rejected with `version_conflict`
- Handoff replay readback events: `handoff.persisted,handoff.replayed`
- Cross-project `default` lookup returned `NOT_FOUND` and DB row count `0`

## Verification

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_graph_editing_audit_durability.py --format json --live-db-audit-evidence-json development/latest-dev-docs/automation-runs/wave46-manual-graph-editing-live-audit-closure/2026-05-23/live_evidence.json --allow-live-closure-claim
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_graph_editing_audit_durability_unittest.py -q
```
