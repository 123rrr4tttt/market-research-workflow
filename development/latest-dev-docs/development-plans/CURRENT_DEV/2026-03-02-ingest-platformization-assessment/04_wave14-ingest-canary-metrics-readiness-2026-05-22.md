# Wave14 Ingest Canary Metrics Readiness

Date: 2026-05-22
Scope: `2026-03-02-ingest-platformization-assessment`

## status

`partial_canary_metrics_readiness_gate_landed`

## contract advanced

This slice adds a deterministic readiness gate for the platformized ingest frontdoor canary metrics boundary:

- `main/backend/app/services/ingest/canary_metrics.py` defines `ingest.canary_metrics_readiness.v1`.
- `main/backend/scripts/check_ingest_canary_metrics_readiness.py` builds a bounded `demo_proj` single URL/frontdoor canary handoff fixture and verifies canary metrics visibility.
- The gate separates repository readiness from live evidence. Deterministic metrics can pass while `demo_proj_live_canary_open=true` and `metric_24h_readback_open=true`.

## evidence

- Deterministic snapshot fields include strict gate state, canary rollout channel, sample size, strict-enabled samples, canary-matched samples, rollout mode counts, and strict-gate source counts.
- The default checker keeps `closure_claim=false`.
- `demo_proj_live_canary_open` remains true until explicit live canary evidence supplies configured-service execution and handoff readback.
- `metric_24h_readback_open` remains true until explicit 24h readback evidence supplies rejection-rate, inserted-valid ratio, and rollout-count inspection.

## remaining live gaps

partial remains because this worker did not run configured services.

- `demo_proj` live canary execution remains open.
- 24h metric readback remains open.
- Production all-project strict-gate promotion remains operations-owned.

## validation

```bash
python3 scripts/check_current_dev_wave14_plan.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_canary_metrics_readiness.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_ingest_canary_metrics_readiness_unittest.py
git diff --check
```
