# Wave22 Retained-Partial Migration Decision

Date: 2026-05-22

Scope: `2026-03-02-single-url-first-ingest-allocation-plan`

Decision marker:
`wave22_retain_current_dev_fetch_router_dashboard_blockers_open`

## Decision

This topic is not eligible to migrate from `CURRENT_DEV` to `ARCHIVE_EXTERNAL_BLOCKED` in Wave22.

Wave17 and Wave19 closed the repo-local single-URL canary metrics path:

- Wave17 `ingest.canary_metrics_readback.v1` validates the deterministic single-URL/frontdoor metrics snapshot and keeps live canary status open.
- Wave19 `ingest.canary_24h_metrics_artifact.v1` binds `ingest.url_pool`, `source_mode=url_execution`, and `allocation_policy=single_url_first` into the deterministic 24h metrics artifact.
- Both gates preserve `live_production_canary_claim=false`, `metric_24h_live_readback_claim=false`, and `closure_claim=false`.

The canary metrics slice is green, but the directory-level plan still has repo-local blockers. The main document keeps broader browser/crawler-first fetch-router coverage, official API adapter maturity, and frontend/dashboard tri-state alignment open before full closure.

## Evidence Readback

- `06_wave17-single-url-canary-metrics-readback-2026-05-22.md`
- `07_wave19-single-url-canary-24h-metrics-artifact-2026-05-22.md`
- `main/backend/app/services/ingest/canary_metrics_readback.py`
- `main/backend/scripts/check_ingest_canary_metrics_readback.py`
- `main/backend/scripts/check_ingest_canary_24h_metrics_artifact.py`
- `main/backend/tests/unit/test_ingest_canary_metrics_readback_unittest.py`
- `main/backend/tests/unit/test_ingest_canary_24h_metrics_artifact_unittest.py`

Related automation evidence:

- `development/latest-dev-docs/automation-runs/ingest-frontdoor-closure/2026-05-22/README.md`
- `development/latest-dev-docs/automation-runs/frontdoor-router-hardening/2026-05-22/README.md`

## Remaining Boundary

The live canary and production metrics work is external/live-operational:

- Run a configured-service single-URL canary for `demo_proj`.
- Read back production 24h metrics from URL pool output, not deterministic fixture events.
- Keep all-project strict-gate promotion blocked until operations supplies live evidence.

These conditions do not justify archive migration while the repo-local fetch-router/API/dashboard blockers remain in the same topic.

## Validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_canary_metrics_readback.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_canary_24h_metrics_artifact.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_ingest_canary_metrics_readback_unittest.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_ingest_canary_24h_metrics_artifact_unittest.py
```

Result: passed.
