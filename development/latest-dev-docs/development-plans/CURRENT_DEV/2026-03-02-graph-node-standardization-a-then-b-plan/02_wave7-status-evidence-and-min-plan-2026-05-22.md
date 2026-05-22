# Wave7-6 Status Evidence And Min Plan (2026-05-22)

## Scope

Target plan:

- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-02-graph-node-standardization-a-then-b-plan/01_graph-node-standardization-a-then-b-plan-2026-03-02.md`

Shared index status before this lane:

- `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md` still lists this topic as `[no_closure_claim][doc_drift]`.
- This lane intentionally does not edit shared indexes.

## Status Decision

Decision: keep in `CURRENT_DEV`, but downgrade the ambiguity.

The original March baseline has drifted because graph projection persistence now exists:

- `main/backend/app/models/entities.py` defines `GraphNodeRecord`, `GraphNodeAliasRecord`, and `GraphEdgeRecord`.
- `main/backend/migrations/versions/20260303_000004_add_graph_node_projection_tables.py` creates `graph_nodes` and `graph_node_aliases`.
- `main/backend/migrations/versions/20260303_000005_add_graph_edge_projection_table.py` creates `graph_edges`.
- `main/backend/app/services/graph/persistence/graph_node_writer.py` and `graph_node_reader.py` provide write/read projection paths.
- `main/backend/app/api/admin.py` gates projection write/read modes with `graph_node_projection_write_mode`, `graph_node_projection_read_mode`, and canary projects.
- `main/backend/tests/integration/test_admin_graph_standardization_unittest.py` covers admin graph interface shape, node-type subsets, shadow write, and canary read behavior.

The topic is not closure-ready because no branch-local live DB evidence was produced for:

- Alembic `current` / upgrade against a configured tenant schema.
- `scripts/backfill_graph_nodes.py --dry-run` against a configured local DB.
- `b_primary` read-mode rollout evidence beyond mocked/canary tests.

## Newer Contract Coverage

The newer curated graph and clue-chain contracts partially cover the product workflow surface, but they do not replace the older admin graph node projection plan.

Covered by newer contracts:

- `main/backend/app/services/workflow_graph/edit_contract.py` validates curated/template graph edit DSL shape, duplicate node ids, duplicate edges, missing endpoints, cycles, and temporary ids for curated business graphs.
- `main/backend/app/services/workflow_graph/curated_service.py` emits `graph_evidence_pack.v1` and `graph_handoff.v1` from curated graph snapshots.
- `main/backend/app/services/clue_chains/graph_integration.py` emits `clue_chain.graph_mutation.v1`, `graph_handoff.v1`, stable node/edge ids, alias merge evidence, and required provenance fields.
- `main/backend/tests/unit/test_workflow_graph_edit_contract_unittest.py`, `test_workflow_graph_curated_service_unittest.py`, `test_clue_chain_graph_integration_unittest.py`, and `tests/integration/test_workflow_graph_api_unittest.py` cover these contracts.

Not covered by newer contracts:

- Legacy admin graph projection storage canonicalization for `GraphNodeWriter`.
- Legacy `content-graph`, `market-graph`, and `policy-graph` A/B projection parity against a live DB.
- Backfill idempotence and tenant-schema migration evidence.

## Deterministic Gap Closed In This Lane

Gap found: `GraphNodeWriter` used the interface ID normalizer for projection `canonical_id`.

That normalizer preserves display casing for API compatibility, but the March plan requires stable canonical storage ids after NFKC, zero-width removal, whitespace normalization, and lower/casefold behavior. Clue-chain alias logic already casefolded aliases, but that did not cover old graph projection storage.

Implemented fix:

- Added `normalize_canonical_node_id` in `main/backend/app/services/graph/mapping.py`.
- Updated `main/backend/app/services/graph/persistence/graph_node_writer.py` to use storage canonical ids for node upserts and edge endpoint resolution.
- Added `test_projection_writer_casefolds_storage_canonical_id_without_changing_interface_id` in `main/backend/tests/unit/test_graph_persistence_writer_unittest.py`.

Boundary preserved:

- `normalize_node_id` remains display-preserving for exported graph interface payloads.
- Projection `canonical_id` now casefolds to reduce duplicate storage rows for case variants.

## Verification

Passed from `main/backend` in this worktree:

```bash
/Users/wangyiliang/market-research-workflow/main/backend/.venv311/bin/python -m pytest -q \
  tests/unit/test_graph_persistence_writer_unittest.py \
  tests/unit/test_graph_exporter_interface_unittest.py \
  tests/unit/test_graph_projection_unittest.py \
  tests/integration/test_admin_graph_standardization_unittest.py \
  tests/unit/test_workflow_graph_edit_contract_unittest.py \
  tests/unit/test_workflow_graph_curated_service_unittest.py \
  tests/unit/test_clue_chain_graph_integration_unittest.py \
  tests/integration/test_workflow_graph_api_unittest.py
```

Result:

- `61 passed, 13 warnings, 28 subtests passed`.
- Warnings were existing FastAPI/Pydantic deprecation warnings.

## Minimal Remaining Plan

1. Run DB-backed closure evidence in an environment with a configured tenant schema:
   - `alembic current`
   - `alembic upgrade head` if not already current
   - `python scripts/backfill_graph_nodes.py --dry-run --limit 10`
2. Run `b_canary` and `b_primary` endpoint checks against a seeded project and compare node/edge counts with A-path output.
3. Only after those checks, decide whether to move this topic out of `CURRENT_DEV`; until then keep the shared-index status conservative.
