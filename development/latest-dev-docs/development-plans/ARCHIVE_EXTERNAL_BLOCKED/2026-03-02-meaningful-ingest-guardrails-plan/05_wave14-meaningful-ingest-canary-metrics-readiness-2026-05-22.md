# Wave14 Ingest Canary Metrics Readiness

Date: 2026-05-22
Scope: `2026-03-02-meaningful-ingest-guardrails-plan`

## status

`partial_guardrail_canary_metrics_readiness_landed`

## contract advanced

Meaningful Ingest Guardrails now has a focused canary metrics readiness boundary:

- The report keeps deterministic guardrail metrics separate from live rollout proof.
- `deterministic_metrics_ready=true` means the repository can expose canary strict-gate samples from the handoff fixture.
- `demo_proj_live_canary_open=true` means configured-service canary evidence is still absent.
- `metric_24h_readback_open=true` means 24h rejection-rate and inserted-valid ratio evidence is still absent.

## evidence

- `main/backend/app/services/ingest/canary_metrics.py`
- `main/backend/scripts/check_ingest_canary_metrics_readiness.py`
- `main/backend/tests/unit/test_ingest_canary_metrics_readiness_unittest.py`

The default gate passes only as a deterministic readiness gate. It preserves `closure_claim=false` and records the live/readback stages as open.

## remaining live gaps

partial remains for production rollout:

- `demo_proj` live canary still needs configured-service execution and handoff readback evidence.
- 24h metric readback still needs rejection-rate, inserted-valid ratio, and guardrail rollout count inspection.
- All-project strict gate enablement remains outside this deterministic repository gate.

## validation

```bash
python3 scripts/check_current_dev_wave14_plan.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_canary_metrics_readiness.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_ingest_canary_metrics_readiness_unittest.py
git diff --check
```
