# Wave8-5 Projection Rollout Contract Note (2026-05-22)

## Scope

This note connects the backend projection rollout closure slice to the graph editing and reporting topic. It does not add GraphPage controls, reporting navigation, audit UI, rollback UI, or writing handoff UI.

## Result

Status: `related backend contract evidence added / product workflow gaps retained`.

Wave8-5 added deterministic no-DB evidence for projected graph storage:

- canonical storage ids are stable after normalization and casefolding;
- edge endpoint resolution uses normalized storage keys;
- missing endpoints are surfaced as explicit dry-run rollout signals;
- the checker output marks `live_db_validated=false`.

Relevant files:

- `main/backend/app/services/graph/persistence/graph_projection_contract.py`
- `main/backend/scripts/check_graph_projection_contract.py`
- `main/backend/tests/unit/test_graph_persistence_writer_unittest.py`

## Boundary

This is not evidence for the remaining graph editing/reporting product gaps:

- GraphPage audit and rollback controls are still not exposed.
- Writing handoff UI remains unproven.
- Clue-chain graph output is still not mapped as curated graph input.
- Live tenant `b_primary` projection read-mode parity remains unrun.

Closure impact:

- Reporting and editing flows now have a deterministic backend projection contract checker to reuse before live rollout.
- The topic remains in `CURRENT_DEV` until the product workflow gaps above are addressed or explicitly waived.
