# Wave27 Open Source Platform Vectorization Closure Decision

- Status: `retain_current_dev`
- Decision date: 2026-05-23
- Evidence: [wave27-vectorization-closure/2026-05-23](../../../automation-runs/wave27-vectorization-closure/2026-05-23/README.md)
- Checker: `ops/search-lab/scripts/wave27_vectorization_closure_gate.py`
- Unit gate: `main/backend/tests/unit/test_wave27_vectorization_closure_gate_unittest.py`
- Archive patch prepared: `false`

## Result

The open-source platform integration vectorization/provider slice is repo-local green, but the directory is not eligible for `ARCHIVE_EXTERNAL_BLOCKED` migration in Wave27.

The Wave27 gate reads the existing Wave10 quality, Wave14 provider capability, Wave18 hybrid readback, Wave19 provider manifest, LanceDB runtime smoke, and LanceDB benchmark artifacts. That provider/quality/readback surface passes and keeps `closure_claim_allowed=false`.

## Repo-Local Blockers

The directory still depends on active repo-local work owned by adjacent CURRENT_DEV topics:

- `directory_scope_still_depends_on_retained_global_vector_contract`
- `directory_scope_still_depends_on_oss_node_platform_io_boundary`

This topic should not move out of `CURRENT_DEV` just because the provider slice is sealed. Moving it now would hide the still-active global vector schema and OSS-node IO boundaries.

## External Conditions Still Open

- `external_embedding_provider_live_not_verified`
- `local_open_search_live_quality_not_sealed`
- `semantic_embedding_quality_not_proven`
- `oss_node_platform_io_sla_not_closed`

## Verification

```bash
PYTHONPATH=main/backend python3 ops/search-lab/scripts/wave27_vectorization_closure_gate.py --out-dir development/latest-dev-docs/automation-runs/wave27-vectorization-closure/2026-05-23
PYTHONPATH=main/backend python3 -m pytest -q main/backend/tests/unit/test_wave27_vectorization_closure_gate_unittest.py
```
