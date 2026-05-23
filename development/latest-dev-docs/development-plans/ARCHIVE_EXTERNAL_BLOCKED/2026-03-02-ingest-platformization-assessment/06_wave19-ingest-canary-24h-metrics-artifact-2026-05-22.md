# Wave19 Ingest Canary 24h Metrics Artifact

Date: 2026-05-22

Scope: `2026-03-02-ingest-platformization-assessment`

Status marker:
`partial_deterministic_canary_24h_metrics_artifact_landed`

## Evidence

Wave19 adds a deterministic 24h metrics artifact shape and write/read gate after the Wave17 canary metrics readback slice.

- contract_version: ingest.canary_24h_metrics_artifact.v1
- deterministic_fixture: true
- window_hours: 24
- single_url_first_allocation: true
- live_production_canary_claim: false
- metric_24h_live_readback_claim: false
- closure_claim: false

The checker writes a fixture artifact, reads it back, validates the snapshot digest, and verifies the expected 24h fields: rejection rate, inserted-valid ratio, reason-code counts, adapter hit rate, and guardrail rollout counts.

## Landed Surface

- `main/backend/scripts/check_ingest_canary_24h_metrics_artifact.py`
- `main/backend/tests/unit/test_ingest_canary_24h_metrics_artifact_unittest.py`

## Remaining Boundary

`partial` remains because this is not live demo/prod 24h metrics closure.

- No configured-service `demo_proj` production canary was run.
- No production 24h rejection-rate or inserted-valid ratio was inspected.
- The artifact proves repo-local shape/readback only; operations still own live canary execution and promotion.

## Validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_canary_24h_metrics_artifact.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_ingest_canary_24h_metrics_artifact_unittest.py
```
