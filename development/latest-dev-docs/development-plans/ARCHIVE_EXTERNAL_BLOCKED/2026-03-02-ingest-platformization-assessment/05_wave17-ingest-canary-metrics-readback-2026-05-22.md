# Wave17 Ingest Canary Metrics Readback

Date: 2026-05-22

Scope: `2026-03-02-ingest-platformization-assessment`

Status marker:
`partial_deterministic_canary_metrics_readback_landed`

## Evidence

Wave17 adds a deterministic write/read/validate gate for the canary metrics snapshot emitted by the Wave12 handoff and classified by the Wave14 readiness checker.

- contract_version: ingest.canary_metrics_readback.v1
- deterministic_readback: true
- live_production_canary_claim: false
- metric_24h_live_readback_claim: false
- closure_claim: false

The gate writes a canonical JSON readback record, reads it from disk, and validates the digest plus canary status fields. It proves the repository can preserve the deterministic snapshot for canary status review without relying on a live 24h canary run.

## Landed Surface

- `main/backend/app/services/ingest/canary_metrics_readback.py`
- `main/backend/scripts/check_ingest_canary_metrics_readback.py`
- `main/backend/tests/unit/test_ingest_canary_metrics_readback_unittest.py`

## Remaining Boundary

`partial` remains because this worker did not execute a live production canary.

- No configured-service `demo_proj` canary was run.
- No live 24h rejection-rate or inserted-valid ratio readback was inspected.
- The deterministic readback gate stands in for the still-open 24h live canary only as warehouse-local evidence.

## Validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_canary_metrics_readback.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_ingest_canary_metrics_readback_unittest.py
```
