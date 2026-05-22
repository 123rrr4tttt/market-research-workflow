# Wave19 Ingest Canary 24h Metrics Artifact

Date: 2026-05-22

Scope: `2026-03-02-single-url-first-ingest-allocation-plan`

Status marker:
`partial_single_url_canary_24h_metrics_artifact_landed`

## Evidence

Wave19 extends the single URL first lane from deterministic canary readback into a fixed 24h metrics artifact contract.

- contract_version: ingest.canary_24h_metrics_artifact.v1
- deterministic_fixture: true
- window_hours: 24
- single_url_first_allocation: true
- live_production_canary_claim: false
- metric_24h_live_readback_claim: false
- closure_claim: false

The fixture binds `ingest.url_pool`, `source_mode=url_execution`, and `allocation_policy=single_url_first` to the artifact before validating rejection-rate and inserted-valid-ratio readback.

## Landed Surface

- `main/backend/scripts/check_ingest_canary_24h_metrics_artifact.py`
- `main/backend/tests/unit/test_ingest_canary_24h_metrics_artifact_unittest.py`

## Remaining Boundary

`partial` remains because no live single URL 24h metrics readback was supplied.

- The checker uses deterministic fixture events, not production URL pool output.
- No live 24h metrics artifact was read from configured services.
- All-project strict-gate promotion remains blocked on operations-owned live evidence.

## Validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_canary_24h_metrics_artifact.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_ingest_canary_24h_metrics_artifact_unittest.py
```
