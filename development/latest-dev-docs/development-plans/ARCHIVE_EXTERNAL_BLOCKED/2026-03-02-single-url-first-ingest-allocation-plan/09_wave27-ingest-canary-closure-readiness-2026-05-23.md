# Wave27 Ingest Canary Closure Readiness

Date: 2026-05-23

Scope: `2026-03-02-single-url-first-ingest-allocation-plan`

Decision marker:
`wave27_retain_current_dev_fetch_router_dashboard_blockers_open`

## Decision

Do not migrate this directory to `ARCHIVE_EXTERNAL_BLOCKED` in Wave27.

The repo-local canary slice is sufficient: Wave17 validates deterministic single-URL/frontdoor canary metrics readback, and Wave19 validates the deterministic 24h metrics artifact while keeping `live_production_canary_claim=false`, `metric_24h_live_readback_claim=false`, and `closure_claim=false`.

Directory-level migration is still blocked by repo-local or attached plan work recorded in the Wave22 decision:

- broader browser/crawler-first fetch-router coverage
- official API adapter maturity
- frontend/dashboard tri-state alignment

`frontdoor-router-hardening` closed a backend status projection and high-JS route-intent slice, but it does not close live browser runtime, adapter maturity, or UI binding.

## Evidence

- `main/backend/scripts/check_ingest_canary_closure_readiness.py`
- `development/latest-dev-docs/automation-runs/wave27-ingest-canary-closure-readiness/2026-05-23/closure_readiness.json`
- `development/latest-dev-docs/automation-runs/wave27-ingest-canary-closure-readiness/2026-05-23/README.md`
- `08_wave22-external-blocked-migration-decision-2026-05-22.md`
- `06_wave17-single-url-canary-metrics-readback-2026-05-22.md`
- `07_wave19-single-url-canary-24h-metrics-artifact-2026-05-22.md`
- `development/latest-dev-docs/automation-runs/frontdoor-router-hardening/2026-05-22/README.md`

## Remaining Boundary

External/live conditions remain open: configured-service single-URL canary for `demo_proj`, production 24h metrics from URL pool output, and operations-owned all-project strict-gate promotion.

These live conditions are not the only remaining conditions for the directory, so the correct state is still `retained_partial`, not `external_blocked`.

## Validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_canary_closure_readiness.py --write-output development/latest-dev-docs/automation-runs/wave27-ingest-canary-closure-readiness/2026-05-23/closure_readiness.json
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_ingest_canary_closure_readiness_unittest.py
```

Result: passed.
