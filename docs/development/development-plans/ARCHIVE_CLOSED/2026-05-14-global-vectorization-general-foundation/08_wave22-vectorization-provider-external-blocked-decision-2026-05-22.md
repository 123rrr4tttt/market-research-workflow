# Wave22 Vectorization Provider External-Blocked Decision

- Status: not eligible for paired `ARCHIVE_EXTERNAL_BLOCKED` migration yet
- Decision date: 2026-05-22
- Scope checked: Wave18 hybrid readback, Wave19 provider manifest, local_index/LanceDB runtime and benchmark evidence, related scripts/checkers
- Shared index changes: none

## Result

The provider/runtime slice is repo-local green, but the global vectorization foundation topic still has repo-local blockers in its own stated scope.

Do not migrate this topic together with `2026-03-01-open-source-platform-integration` yet. The Wave18/Wave19 gates prove deterministic provider manifest and local_index readback boundaries; they do not close the global vector contract, retrieval schema, persistence, or main search evidence-hit alignment that this topic owns.

## Provider Slice Evidence

| Evidence | Path | State |
|---|---|---|
| Wave18 hybrid readback | `development/latest-dev-docs/automation-runs/wave18-vectorization-hybrid-readback/2026-05-22/hybrid_readback_contract.json` | `status=passed`, `closure_claim_allowed=false`, keyword/vector/hybrid mode identity read back |
| Wave19 provider manifest | `development/latest-dev-docs/automation-runs/wave19-vectorization-provider-manifest/2026-05-22/provider_manifest_readback.json` | `status=passed`, `manifest_state=partial`, `closure_claim_allowed=false` |
| LanceDB runtime smoke | `development/latest-dev-docs/automation-runs/local-index-lancedb-runtime-smoke/2026-05-22/runtime_smoke_results.json` | `status=passed`, keyword/vector/hybrid runtime paths returned expected top rows |
| LanceDB benchmark quality | `development/latest-dev-docs/automation-runs/local-index-lancedb-benchmark/2026-05-22/benchmark_quality_results.json` | `status=passed`, controlled top-k and filter guards passed |

## Repo-Local Blockers

The following blockers are repo-local to the global foundation scope and are not resolved by the provider manifest:

- unified vector object contract is not frozen across `project_key`, `chunk_id`, `source_id`, `document_id`, model/version/provenance, and matrix branch fields;
- `retrieval_runs`, `retrieval_branches`, and `retrieval_hits` persistence is not implemented;
- `Embedding` / Qdrant / pgvector payloads do not yet share the full chunk-level provenance contract;
- `/api/v1/search` and any future vector search API do not yet return the unified evidence-hit fields such as `evidence_class`, `verification_state`, `rank_features`, `provenance`, `query_group_id`, and `matrix_branch_id`;
- Agent matrix retrieval and the main search/vector/hybrid result contract are not yet joined under one reusable schema;
- LanceDB remains a local material prototype and is intentionally not a main search fallback or production embedding quality proof.

The LanceDB benchmark output also keeps `global_vector_contract_not_closed` as a remaining blocker.

## Checker Boundary

The related checker set is present and repo-local:

- `ops/search-lab/scripts/wave18_vectorization_hybrid_readback.py`
- `ops/search-lab/scripts/wave19_vectorization_provider_manifest_readback.py`
- `ops/search-lab/scripts/local_index_lancedb_runtime_smoke.py`
- `ops/search-lab/scripts/local_index_lancedb_benchmark_quality.py`
- `main/backend/tests/unit/test_wave18_vectorization_hybrid_readback_unittest.py`
- `main/backend/tests/unit/test_wave19_vectorization_provider_manifest_readback_unittest.py`

Wave19 is useful as a provider manifest readback gate, but its own contract stays `manifest_state=partial` and `closure_claim_allowed=false`.

## Decision

Do not move this topic to `ARCHIVE_EXTERNAL_BLOCKED` as part of the Wave22 paired candidate group.

Next repo-local closure work should target a narrow contract slice for unified vector object/evidence-hit schema alignment before this topic is reconsidered for archive migration.

## Verification

```bash
PYTHONPATH=main/backend python3 ops/search-lab/scripts/wave19_vectorization_provider_manifest_readback.py --out-dir development/latest-dev-docs/automation-runs/wave19-vectorization-provider-manifest/2026-05-22
PYTHONPATH=main/backend python3 -m pytest -q main/backend/tests/unit/test_wave19_vectorization_provider_manifest_readback_unittest.py
main/backend/.venv311/bin/python ops/search-lab/scripts/local_index_lancedb_runtime_smoke.py --out-dir development/latest-dev-docs/automation-runs/local-index-lancedb-runtime-smoke/2026-05-22
main/backend/.venv311/bin/python ops/search-lab/scripts/local_index_lancedb_benchmark_quality.py --out-dir development/latest-dev-docs/automation-runs/local-index-lancedb-benchmark/2026-05-22
```
