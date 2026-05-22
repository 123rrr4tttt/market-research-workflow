# Wave17 Ingest Canary Metrics Readback

Date: 2026-05-22

Scope: `2026-03-02-single-url-first-ingest-allocation-plan`

Status marker:
`partial_single_url_canary_metrics_readback_landed`

## Evidence

The single URL first lane now has a deterministic readback gate after the Wave12 canary handoff and Wave14 metrics readiness slice:

- contract_version: ingest.canary_metrics_readback.v1
- deterministic_readback: true
- live_production_canary_claim: false
- metric_24h_live_readback_claim: false
- closure_claim: false

The readback record preserves the single URL/frontdoor source URL, canary status booleans, deterministic metrics snapshot, and digest. Validation requires `demo_proj_live_canary_open=true` and `metric_24h_readback_open=true`, so the gate cannot be used to claim live canary closure.

## Landed Surface

- `main/backend/app/services/ingest/canary_metrics_readback.py`
- `main/backend/scripts/check_ingest_canary_metrics_readback.py`
- `main/backend/tests/unit/test_ingest_canary_metrics_readback_unittest.py`

## Remaining Boundary

`partial` remains because no live single URL canary was executed in this worker slice.

- No configured-service `demo_proj` URL canary was run.
- No 24h live metrics readback artifact was supplied.
- Promotion to all-project strict-gate behavior remains operations-owned.

## Validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_canary_metrics_readback.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_ingest_canary_metrics_readback_unittest.py
```
