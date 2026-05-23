# Wave17 Ingest Canary Metrics Readback

Date: 2026-05-22

Scope: `2026-03-02-meaningful-ingest-guardrails-plan`

Status marker:
`partial_meaningful_ingest_canary_metrics_readback_landed`

## Evidence

Wave17 adds deterministic canary status readback for meaningful ingest guardrail rollout metrics:

- contract_version: ingest.canary_metrics_readback.v1
- deterministic_readback: true
- live_production_canary_claim: false
- metric_24h_live_readback_claim: false
- closure_claim: false

The gate writes and reads back the metrics snapshot carrying guardrail rollout counts, strict-enabled samples, canary-matched samples, and remaining live gaps. Validation fails if the record mutates, if live canary status is marked closed, or if the snapshot digest no longer matches.

## Landed Surface

- `main/backend/app/services/ingest/canary_metrics_readback.py`
- `main/backend/scripts/check_ingest_canary_metrics_readback.py`
- `main/backend/tests/unit/test_ingest_canary_metrics_readback_unittest.py`

## Remaining Boundary

`partial` remains because no live guardrail rollout canary was executed here.

- `settings.ingest_enable_strict_gate` remains a production operations decision.
- The 24h rejection-rate and inserted-valid ratio inspection remains open.
- The deterministic readback gate does not close live canary validation.

## Validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_canary_metrics_readback.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_ingest_canary_metrics_readback_unittest.py
```
