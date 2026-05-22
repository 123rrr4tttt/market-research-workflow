# Wave19 Vectorization Provider Manifest Evidence

- Status: global vectorization foundation partial; deterministic provider manifest readback passed
- Branch: `codex/devdocs-wave19-vectorization-provider-manifest`
- Evidence: [wave19-vectorization-provider-manifest/2026-05-22](../../../automation-runs/wave19-vectorization-provider-manifest/2026-05-22/README.md)
- Checker: `ops/search-lab/scripts/wave19_vectorization_provider_manifest_readback.py`
- Unit gate: `main/backend/tests/unit/test_wave19_vectorization_provider_manifest_readback_unittest.py`

## Manifest Contract

`wave19-vectorization-provider-manifest.v1` records the local vectorization provider surface as deterministic repo evidence:

| provider | keyword | vector | hybrid | fallback |
|---|---:|---:|---:|---|
| `local_index.keyword` | true | false | false | none |
| `local_index.vector` | false | true | false | `keyword` / `RuntimeError` |
| `local_index.hybrid` | true | true | true | `keyword` / `RuntimeError` |

Each row also carries trace-quality readback: required score components, source case id, returned chunk order, and `provider_live_verified=false`.

## Foundation Impact

This narrows the global vectorization foundation gap from scattered capability evidence to a single manifest readback gate. It is still scoped to deterministic repo-local artifacts and does not convert the LanceDB prototype, deterministic hash vector fixture, or provider trace into production embedding quality.

## Still Open

- live external embedding provider probes;
- local open-search quality and `provider=auto` promotion;
- production semantic relevance benchmark;
- unified vector object schema and full evidence-hit contract;
- OSS-node live SLA.

## Verification

```bash
PYTHONPATH=main/backend python3 ops/search-lab/scripts/wave19_vectorization_provider_manifest_readback.py
PYTHONPATH=main/backend python3 -m pytest -q main/backend/tests/unit/test_wave19_vectorization_provider_manifest_readback_unittest.py
python3 scripts/check_current_dev_wave19_plan.py
git diff --check
```
