# Wave17 Graph Node Rollout Manifest Readback (2026-05-22)

Status: `deterministic manifest/readback gate landed; live tenant DB closure remains open`.

Worker branch:

- `codex/devdocs-wave17-graph-node-rollout-readback`

Target topic:

- `2026-03-02-graph-node-standardization-a-then-b-plan`

## Result

This slice adds a machine-checkable rollout manifest that reads back the prior Graph Node rollout evidence in a deterministic order:

1. Wave7 canonical storage id fixture evidence.
2. Wave10 pre-live DB dry-run readiness.
3. Wave14 live DB rollout gate.

Implemented files:

- `main/backend/app/services/graph/persistence/graph_node_rollout_manifest.py`
- `main/backend/scripts/check_graph_node_rollout_manifest.py`
- `main/backend/tests/unit/test_graph_node_rollout_manifest_unittest.py`

The checker builds the manifest twice, canonicalizes JSON with sorted keys, compares the SHA-256 digest, and fails if any stage attempts to turn dry-run evidence into a closure claim.

Default dry-run/readback output keeps:

- `deterministic_readback=true`
- `live_db_validated=false`
- `live_db_closure_ready=false`
- `closure_claim=false`

## Machine Gate

Default local command:

```bash
cd main/backend
/Users/wangyiliang/.local/bin/python3.11 scripts/check_graph_node_rollout_manifest.py --format text
```

Expected default status:

```text
status=ok
deterministic_readback=True
live_db_validated=False
live_db_closure_ready=False
closure_claim=False
```

Focused test:

```bash
cd main/backend
/Users/wangyiliang/.local/bin/python3.11 -m pytest -q tests/unit/test_graph_node_rollout_manifest_unittest.py
```

## Boundary

This manifest is a readback/dry-run gate only. It does not:

- open a tenant DB connection;
- run Alembic against a configured tenant schema;
- run `scripts/backfill_graph_nodes.py --dry-run --limit 10` against tenant data;
- compare `b_canary` or `b_primary` read parity against seeded projection rows;
- claim this CURRENT_DEV topic is closed.

Shared navigation indexes remain untouched for the Wave17 integration lane.
