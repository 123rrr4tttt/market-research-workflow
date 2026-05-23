# Wave22 Retained-Partial Migration Decision

Date: 2026-05-22

Scope: `2026-03-02-meaningful-ingest-guardrails-plan`

Decision marker:
`wave22_retain_current_dev_policy_tuning_after_live_canary`

## Decision

This topic is not migrated from `CURRENT_DEV` to `ARCHIVE_EXTERNAL_BLOCKED` in Wave22.

Wave17 and Wave19 closed the repo-local meaningful-ingest guardrail metrics path:

- Wave17 `ingest.canary_metrics_readback.v1` validates deterministic canary metrics carrying guardrail rollout counts, strict-enabled samples, canary-matched samples, and live-gap flags.
- Wave19 `ingest.canary_24h_metrics_artifact.v1` validates the deterministic 24h artifact fields for rejection rate, inserted-valid ratio, reason-code counts, adapter hit rate, and guardrail rollout counts.
- Both gates preserve `live_production_canary_claim=false`, `metric_24h_live_readback_claim=false`, and `closure_claim=false`.

The canary metrics slice is green, but the directory-level closure still depends on production rollout feedback and follow-up source-policy tuning after live canary evidence. Until that follow-up is either implemented or split into a successor topic, this directory stays `retained_partial`.

## Evidence Readback

- `06_wave17-meaningful-ingest-canary-metrics-readback-2026-05-22.md`
- `07_wave19-meaningful-ingest-canary-24h-metrics-artifact-2026-05-22.md`
- `main/backend/app/services/ingest/canary_metrics.py`
- `main/backend/app/services/ingest/canary_metrics_readback.py`
- `main/backend/scripts/check_ingest_canary_metrics_readback.py`
- `main/backend/scripts/check_ingest_canary_24h_metrics_artifact.py`
- `main/backend/tests/unit/test_ingest_canary_metrics_readback_unittest.py`
- `main/backend/tests/unit/test_ingest_canary_24h_metrics_artifact_unittest.py`

Related automation evidence:

- `development/latest-dev-docs/automation-runs/ingest-frontdoor-closure/2026-05-22/README.md`
- `development/latest-dev-docs/automation-runs/frontdoor-router-hardening/2026-05-22/README.md`

## Remaining Boundary

The remaining live rollout work is external/live-operational:

- Execute a live guardrail rollout canary against configured services.
- Read back production 24h rejection-rate, inserted-valid ratio, and guardrail rollout counts.
- Treat `settings.ingest_enable_strict_gate` and all-project promotion as operations-owned decisions.

These external conditions are necessary but not sufficient for migration while source-policy tuning remains attached to the same topic.

## Validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_canary_metrics_readback.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_canary_24h_metrics_artifact.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_ingest_canary_metrics_readback_unittest.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_ingest_canary_24h_metrics_artifact_unittest.py
```

Result: passed.
