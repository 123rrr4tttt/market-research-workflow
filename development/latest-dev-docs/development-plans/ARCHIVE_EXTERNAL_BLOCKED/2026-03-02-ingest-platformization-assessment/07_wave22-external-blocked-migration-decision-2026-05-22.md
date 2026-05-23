# Wave22 Retained-Partial Migration Decision

Date: 2026-05-22

Scope: `2026-03-02-ingest-platformization-assessment`

Decision marker:
`wave22_retain_current_dev_repo_local_blockers_open`

## Decision

This topic is not eligible to migrate from `CURRENT_DEV` to `ARCHIVE_EXTERNAL_BLOCKED` in Wave22.

Wave17 and Wave19 closed the repo-local evidence path for ingest canary metrics:

- Wave17 `ingest.canary_metrics_readback.v1` writes, reads, and validates the deterministic canary metrics snapshot.
- Wave19 `ingest.canary_24h_metrics_artifact.v1` writes, reads, and validates the deterministic 24h metrics artifact shape.
- Both gates preserve `live_production_canary_claim=false`, `metric_24h_live_readback_claim=false`, and `closure_claim=false`.

That canary metrics slice is green, but it does not close the whole ingest-platformization directory. The main plan still owns repo-local platformization work: broader fetch-router decomposition, shared GateService/rule-source consolidation, default propagation drift control, replay/SLO observability, and frontend/ops entry closure.

## Evidence Readback

- `05_wave17-ingest-canary-metrics-readback-2026-05-22.md`
- `06_wave19-ingest-canary-24h-metrics-artifact-2026-05-22.md`
- `main/backend/app/services/ingest/canary_metrics_readback.py`
- `main/backend/scripts/check_ingest_canary_metrics_readback.py`
- `main/backend/scripts/check_ingest_canary_24h_metrics_artifact.py`
- `main/backend/tests/unit/test_ingest_canary_metrics_readback_unittest.py`
- `main/backend/tests/unit/test_ingest_canary_24h_metrics_artifact_unittest.py`

Related automation evidence:

- `development/latest-dev-docs/automation-runs/ingest-frontdoor-closure/2026-05-22/README.md`
- `development/latest-dev-docs/automation-runs/frontdoor-router-hardening/2026-05-22/README.md`

## Remaining Boundary

The live canary work is external/live-operational:

- Run a configured-service `demo_proj` production canary.
- Read back production 24h rejection-rate and inserted-valid ratio metrics.
- Use operations approval before any all-project strict-gate promotion.

Those live conditions are not enough to archive the whole directory while the repo-local platformization blockers above remain open.

## Validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_canary_metrics_readback.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_canary_24h_metrics_artifact.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_ingest_canary_metrics_readback_unittest.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_ingest_canary_24h_metrics_artifact_unittest.py
```

Result: passed.
