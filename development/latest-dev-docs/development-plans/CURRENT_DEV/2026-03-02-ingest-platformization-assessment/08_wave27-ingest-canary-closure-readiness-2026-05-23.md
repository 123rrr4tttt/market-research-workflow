# Wave27 Ingest Canary Closure Readiness

Date: 2026-05-23

Scope: `2026-03-02-ingest-platformization-assessment`

Decision marker:
`wave27_retain_current_dev_repo_local_blockers_open`

## Decision

Do not migrate this directory to `ARCHIVE_EXTERNAL_BLOCKED` in Wave27.

The repo-local canary slice is sufficient: Wave17 validates deterministic canary metrics readback, and Wave19 validates the deterministic 24h metrics artifact while keeping `live_production_canary_claim=false`, `metric_24h_live_readback_claim=false`, and `closure_claim=false`.

Directory-level migration is still blocked by repo-local platformization work recorded in the Wave22 decision:

- broader fetch-router decomposition
- shared GateService/rule-source consolidation
- default propagation drift control
- replay/SLO observability
- frontend/ops entry closure

## Evidence

- `main/backend/scripts/check_ingest_canary_closure_readiness.py`
- `development/latest-dev-docs/automation-runs/wave27-ingest-canary-closure-readiness/2026-05-23/closure_readiness.json`
- `development/latest-dev-docs/automation-runs/wave27-ingest-canary-closure-readiness/2026-05-23/README.md`
- `07_wave22-external-blocked-migration-decision-2026-05-22.md`
- `05_wave17-ingest-canary-metrics-readback-2026-05-22.md`
- `06_wave19-ingest-canary-24h-metrics-artifact-2026-05-22.md`

## Remaining Boundary

External/live conditions remain open: configured-service `demo_proj` canary execution, production 24h rejection-rate readback, production 24h inserted-valid ratio readback, and operations approval before any all-project strict-gate promotion.

These live conditions are not the only remaining conditions for the directory, so the correct state is still `retained_partial`, not `external_blocked`.

## Validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_canary_closure_readiness.py --write-output development/latest-dev-docs/automation-runs/wave27-ingest-canary-closure-readiness/2026-05-23/closure_readiness.json
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_ingest_canary_closure_readiness_unittest.py
```

Result: passed.
