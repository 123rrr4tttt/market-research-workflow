# Wave27 OSS Node Vectorization Closure Decision

- Status: `retain_current_dev`
- Decision date: 2026-05-23
- Evidence: [wave27-vectorization-closure/2026-05-23](../../../automation-runs/wave27-vectorization-closure/2026-05-23/README.md)
- Checker: `ops/search-lab/scripts/wave27_vectorization_closure_gate.py`
- Unit gate: `main/backend/tests/unit/test_wave27_vectorization_closure_gate_unittest.py`
- Archive patch prepared: `false`

## Result

The OSS-node vectorization provider manifest is consumable and the provider/quality/readback gate passes. This does not close the whole OSS node platform IO directory.

Wave27 keeps this topic in `CURRENT_DEV` because the original directory scope still includes node schema, runtime, persistence, and live replay surfaces that are not closed by a provider manifest.

## Repo-Local Blockers

- `node_schema_runtime_persistence_platformization_scope_not_closed`
- `vector_search_node_manifest_consumption_not_live_replayed`

The second blocker is intentionally repo-local at this stage: a node-level fixture/readback can still be added before any live provider or tenant runtime is required.

## External Conditions Still Open

- `external_embedding_provider_live_not_verified`
- `local_open_search_live_quality_not_sealed`
- `semantic_embedding_quality_not_proven`
- `live_scheduler_tenant_db_ui_sla_not_proven`

## Verification

```bash
PYTHONPATH=main/backend python3 ops/search-lab/scripts/wave27_vectorization_closure_gate.py --out-dir development/latest-dev-docs/automation-runs/wave27-vectorization-closure/2026-05-23
PYTHONPATH=main/backend python3 -m pytest -q main/backend/tests/unit/test_wave27_vectorization_closure_gate_unittest.py
```
