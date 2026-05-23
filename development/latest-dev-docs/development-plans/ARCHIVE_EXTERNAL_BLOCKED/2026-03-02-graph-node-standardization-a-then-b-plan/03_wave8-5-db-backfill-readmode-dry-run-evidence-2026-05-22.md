# Wave8-5 DB Backfill Read-Mode Dry-Run Evidence (2026-05-22)

## Scope

This slice follows the Wave7 canonical id fix and closes one deterministic rollout gap without requiring a configured tenant DB.

Covered target:

- `2026-03-02-graph-node-standardization-a-then-b-plan`

Related topics:

- `2026-03-02-graph-3d-force-engine-parallel-migration`
- `2026-03-07-graph-editing-and-reporting`

## Result

Status: `deterministic no-DB closure slice landed`.

Implemented evidence gate:

- `main/backend/app/services/graph/persistence/graph_projection_contract.py`
- `main/backend/scripts/check_graph_projection_contract.py`
- `main/backend/tests/unit/test_graph_persistence_writer_unittest.py`

The new checker builds a fixture graph and validates the storage projection contract without opening a DB session:

- canonical storage ids use NFKC, zero-width removal, whitespace normalization, and casefold behavior;
- duplicate canonical node attempts collapse to a unique storage key in the dry-run plan;
- edge endpoint resolution compares normalized storage keys, so display/raw endpoint variants resolve deterministically;
- missing endpoints are reported as explicit rollout signals instead of being treated as successful writes;
- output keeps `live_db_validated=false`.

## Checker Result

Command:

```bash
/Users/wangyiliang/market-research-workflow/main/backend/.venv311/bin/python \
  main/backend/scripts/check_graph_projection_contract.py --format json
```

Observed summary:

- `status`: `ok`
- `mode`: `no_db_dry_run`
- `live_db_validated`: `false`
- `attempted_node_count`: `4`
- `unique_node_count`: `3`
- `duplicate_node_attempts`: `1`
- `candidate_edge_count`: `3`
- `writeable_edge_count`: `2`
- `unresolved_edge_count`: `1`

Resolved fixture edges:

- `Post:42 -> Entity:acme corp`
- `Post:42 -> Keyword:lottery ai`

The retained unresolved fixture edge is intentional and proves that the dry-run path surfaces `missing_to_endpoint` instead of claiming the edge is writeable.

## Unit Coverage

Added tests:

- `test_projection_dry_run_resolves_canonical_edge_endpoints_without_db`
- `test_projection_dry_run_marks_missing_edge_endpoint_as_rollout_signal`

Focused command:

```bash
/Users/wangyiliang/market-research-workflow/main/backend/.venv311/bin/python -m pytest -q \
  main/backend/tests/unit/test_graph_persistence_writer_unittest.py \
  main/backend/tests/unit/test_graph_projection_unittest.py
```

Observed result:

- `8 passed, 2 warnings`
- warnings are existing Pydantic deprecation warnings.

## Boundary

This slice does not claim live DB rollout completion.

Retained live gaps:

- Alembic `current` / `upgrade head` was not run against a configured tenant schema.
- `scripts/backfill_graph_nodes.py --dry-run --limit 10` was not run against a live tenant DB.
- `b_primary` read-mode parity was not run against seeded tenant data.

Closure impact:

- The no-DB deterministic contract now covers canonical storage and edge endpoint resolution.
- Live tenant migration and read-mode parity remain required before this topic can be archived.
