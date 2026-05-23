# Wave27 Ingest Canary Closure Readiness

Date: 2026-05-23

Scope: `2026-03-02-meaningful-ingest-guardrails-plan`

Decision marker:
`wave27_retain_current_dev_policy_tuning_successor_not_split`

## Decision

Do not migrate this directory to `ARCHIVE_EXTERNAL_BLOCKED` in Wave27.

The repo-local canary slice is sufficient: Wave17 validates deterministic canary metrics readback, and Wave19 validates the deterministic 24h metrics artifact while keeping `live_production_canary_claim=false`, `metric_24h_live_readback_claim=false`, and `closure_claim=false`.

Directory-level migration is still blocked because source-policy tuning remains attached to the same topic after live canary feedback. That follow-up has not been implemented or split into a successor topic, so this directory should not be counted as only external/live blocked.

## Evidence

- `main/backend/scripts/check_ingest_canary_closure_readiness.py`
- `development/latest-dev-docs/automation-runs/wave27-ingest-canary-closure-readiness/2026-05-23/closure_readiness.json`
- `development/latest-dev-docs/automation-runs/wave27-ingest-canary-closure-readiness/2026-05-23/README.md`
- `08_wave22-external-blocked-migration-decision-2026-05-22.md`
- `06_wave17-meaningful-ingest-canary-metrics-readback-2026-05-22.md`
- `07_wave19-meaningful-ingest-canary-24h-metrics-artifact-2026-05-22.md`

## Remaining Boundary

External/live conditions remain open: live guardrail rollout canary against configured services, production 24h rejection-rate readback, production 24h inserted-valid ratio readback, production guardrail rollout counts readback, and operations-owned strict-gate promotion.

These live conditions are not enough for archive migration while the attached source-policy tuning work remains in this topic.

## Validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_canary_closure_readiness.py --write-output development/latest-dev-docs/automation-runs/wave27-ingest-canary-closure-readiness/2026-05-23/closure_readiness.json
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_ingest_canary_closure_readiness_unittest.py
```

Result: passed.
