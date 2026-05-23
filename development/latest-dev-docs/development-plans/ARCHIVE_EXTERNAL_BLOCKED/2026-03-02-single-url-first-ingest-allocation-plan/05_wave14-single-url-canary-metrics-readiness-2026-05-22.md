# Wave14 Ingest Canary Metrics Readiness

Date: 2026-05-22
Scope: `2026-03-02-single-url-first-ingest-allocation-plan`

## status

`partial_single_url_canary_metrics_readiness_landed`

## contract advanced

Single URL first ingest now has a deterministic canary metrics readiness gate layered after the Wave12 handoff envelope:

- The bounded fixture follows `ingest.url_pool` with `source_mode=url_execution` and `project_key=demo_proj`.
- The readiness report classifies `deterministic_canary_metrics_snapshot`, `demo_proj_live_canary`, and `metric_24h_readback` independently.
- A passing deterministic gate does not claim that a configured-service canary or 24h readback happened.

## evidence

- `demo_proj_live_canary_open=true` in the default checker output.
- `metric_24h_readback_open=true` in the default checker output.
- `closure_claim=false` remains part of the report even when future evidence validates the live/readback stages.
- The single URL handoff keeps the source URL, route hint, fetch strategy, rollout channel, and task-local metrics snapshot visible for readback.

## remaining live gaps

partial remains because no live single URL canary was executed in this worker slice.

- No configured-service `demo_proj` URL canary was run.
- No live handoff readback artifact was supplied.
- No 24h rejection-rate or inserted-valid ratio was inspected.

## validation

```bash
python3 scripts/check_current_dev_wave14_plan.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_canary_metrics_readiness.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_ingest_canary_metrics_readiness_unittest.py
git diff --check
```
