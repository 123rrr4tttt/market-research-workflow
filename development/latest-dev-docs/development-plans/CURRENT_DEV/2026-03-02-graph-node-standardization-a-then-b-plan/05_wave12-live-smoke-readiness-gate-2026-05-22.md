# Wave12 Graph Live Smoke Readiness Gate (2026-05-22)

Status: `readiness gate landed / live DB rollout remains open`.

This Wave12 worker turns the remaining Graph Node Standardization A/B live DB gap into an explicit tri-state readiness gate instead of treating no-DB or pre-live checks as closure.

## Evidence Added

- `main/backend/app/services/graph/persistence/graph_live_smoke_readiness.py`
  - consumes the no-DB projection dry-run and pre-live DB rollout readiness reports;
  - records live DB as `configured_not_run` unless explicit evidence proves migration, backfill dry-run, backend graph endpoint smoke, and B-read parity;
  - keeps `closure_claim=false`.
- `main/backend/scripts/check_graph_live_smoke_readiness.py`
  - reports the configured database URL as a scheduling signal only;
  - does not open a DB session and does not promote `b_primary`;
  - preserves the live gaps for Alembic, backfill, backend-data endpoint smoke, and B-read parity.
- `main/backend/tests/unit/test_graph_live_smoke_readiness_unittest.py`
  - blocks incomplete live evidence;
  - isolates frontend/backend-data readiness failures from the backend projection fixture stage.

## Current Gate Output

Command:

```bash
/Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_graph_live_smoke_readiness.py --format text
```

Observed status:

```text
status=ok
closure_claim=False
live_db_validated=False
no_db_fixture_smoke=passed
pre_live_db_dry_run_readiness=ready
live_db_backend_data_smoke=configured_not_run
```

## Remaining Topic Gap

- `alembic current/upgrade` still must run against the configured tenant schema.
- `backfill_graph_nodes.py --dry-run` still must run against live tenant data.
- `b_canary` or `b_primary` read-mode parity still must be compared against seeded projection data.
- `graph_node_projection_read_mode=b_primary` remains out of scope for this branch.

Do not archive this topic from this slice. It is now better gated, but the live DB proof remains unrun.
