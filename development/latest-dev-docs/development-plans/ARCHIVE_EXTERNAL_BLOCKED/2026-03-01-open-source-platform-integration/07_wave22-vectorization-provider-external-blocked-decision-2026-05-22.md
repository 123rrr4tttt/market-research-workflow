# Wave22 Vectorization Provider Retention Decision

- Status: `retain_current_dev` for the directory; provider slice is externally blocked but not enough for directory migration
- Decision date: 2026-05-22
- Scope checked: Wave18 hybrid readback, Wave19 provider manifest, local_index/LanceDB runtime and benchmark evidence, related scripts/checkers
- Shared index changes: none

## Result

The open-source platform integration topic has no remaining repo-local blocker in the vectorization/provider slice, but this is not sufficient to move the whole directory out of `CURRENT_DEV`.

The provider slice itself is explicitly external/live-provider gated:

- external embedding provider live probes are not verified;
- SearXNG/YaCy local-open-search live quality is not sealed;
- `provider=auto` promotion remains forbidden;
- semantic embedding quality is not proven by deterministic fixtures;
- OSS-node platform IO live/SLA evidence remains outside the repo-local gate.

This decision does not claim `ARCHIVE_CLOSED`, and it does not promote any provider into default platform capability.

## Evidence Checked

| Evidence | Path | State |
|---|---|---|
| Wave18 hybrid readback | `development/latest-dev-docs/automation-runs/wave18-vectorization-hybrid-readback/2026-05-22/hybrid_readback_contract.json` | `status=passed`, `closure_claim_allowed=false`, keyword/vector/hybrid mode identity read back |
| Wave19 provider manifest | `development/latest-dev-docs/automation-runs/wave19-vectorization-provider-manifest/2026-05-22/provider_manifest_readback.json` | `status=passed`, `manifest_state=partial`, `closure_claim_allowed=false` |
| LanceDB runtime smoke | `development/latest-dev-docs/automation-runs/local-index-lancedb-runtime-smoke/2026-05-22/runtime_smoke_results.json` | `status=passed`, keyword/vector/hybrid runtime paths returned expected top rows |
| LanceDB benchmark quality | `development/latest-dev-docs/automation-runs/local-index-lancedb-benchmark/2026-05-22/benchmark_quality_results.json` | `status=passed`, controlled top-k and filter guards passed |

## Checker Boundary

The related checker set is present and repo-local:

- `ops/search-lab/scripts/wave18_vectorization_hybrid_readback.py`
- `ops/search-lab/scripts/wave19_vectorization_provider_manifest_readback.py`
- `ops/search-lab/scripts/local_index_lancedb_runtime_smoke.py`
- `ops/search-lab/scripts/local_index_lancedb_benchmark_quality.py`
- `main/backend/tests/unit/test_wave18_vectorization_hybrid_readback_unittest.py`
- `main/backend/tests/unit/test_wave19_vectorization_provider_manifest_readback_unittest.py`

Wave19 reads Wave14 and Wave18 artifacts, requires the target topics to exist, records the `local_index.keyword`, `local_index.vector`, and `local_index.hybrid` manifest rows, and fails if source traces claim live provider verification.

## Decision

Do not move this topic to `ARCHIVE_EXTERNAL_BLOCKED` in Wave22.

Reason: the evidence is slice-level, while the directory is still the broader open-source platform integration entry. Its remaining boundary overlaps global vector object/schema closure and OSS-node platform IO live/SLA work. Those boundaries need either a separate successor split or a repo-local closure gate before this directory can be archived without hiding active internal work.

Recommended next step: split the provider/live runtime residual into its owning topic, then reassess whether the parent open-source platform integration directory can be retired or archived.

## Verification

```bash
PYTHONPATH=main/backend python3 ops/search-lab/scripts/wave19_vectorization_provider_manifest_readback.py --out-dir development/latest-dev-docs/automation-runs/wave19-vectorization-provider-manifest/2026-05-22
PYTHONPATH=main/backend python3 -m pytest -q main/backend/tests/unit/test_wave19_vectorization_provider_manifest_readback_unittest.py
main/backend/.venv311/bin/python ops/search-lab/scripts/local_index_lancedb_runtime_smoke.py --out-dir development/latest-dev-docs/automation-runs/local-index-lancedb-runtime-smoke/2026-05-22
main/backend/.venv311/bin/python ops/search-lab/scripts/local_index_lancedb_benchmark_quality.py --out-dir development/latest-dev-docs/automation-runs/local-index-lancedb-benchmark/2026-05-22
```
