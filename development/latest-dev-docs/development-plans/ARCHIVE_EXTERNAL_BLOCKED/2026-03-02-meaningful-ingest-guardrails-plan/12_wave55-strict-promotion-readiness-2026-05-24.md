# Wave55 Strict Promotion Readiness

Date: 2026-05-24
Scope: `2026-03-02-meaningful-ingest-guardrails-plan`

## status

`repo_local_strict_promotion_preflight_passed_production_ops_external`

Contract markers:

- `repo_local_preflight_passed=true`
- `repo_local_live_canary_validated=true`
- `repo_local_metric_24h_shape_validated=true`
- `production_24h_metrics_satisfied=false`
- `strict_gate_promotion_satisfied=false`
- `closure_claim=false`

## what changed

This slice adds a strict-promotion readiness gate instead of leaving the
production 24h / all-project strict-gate blocker as prose only.

The checker executes the existing repo-local API/DB canary, validates the local
24h metrics artifact shape, and then refuses to treat those local facts as a
production rollout claim.

## evidence

- `main/backend/app/services/ingest/canary_strict_promotion.py`
- `main/backend/scripts/check_ingest_canary_strict_promotion_readiness.py`
- `main/backend/tests/unit/test_ingest_canary_strict_promotion_readiness_unittest.py`
- `development/latest-dev-docs/automation-runs/wave55-meaningful-ingest-strict-promotion-readiness/2026-05-24/strict_promotion_readiness.json`

## boundary result

Closed locally:

- repo-local accepted/rejected strict-gate API/DB canary validation
- repo-local 24h metrics shape validation for rejection rate, inserted-valid
  ratio, and guardrail rollout counts
- machine-readable promotion preflight classification

Still external/live-operational:

- production 24h rejection-rate readback
- production 24h inserted-valid ratio readback
- production guardrail rollout counts readback
- operations-owned all-project strict-gate promotion decision
- operations-owned global default enablement

The target remains `ARCHIVE_EXTERNAL_BLOCKED`. The remaining blocker is now
precise: local code can prove the promotion preflight, but cannot honestly
claim production 24h metrics or an operations promotion decision.

## validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_canary_strict_promotion_readiness.py --output development/latest-dev-docs/automation-runs/wave55-meaningful-ingest-strict-promotion-readiness/2026-05-24/strict_promotion_readiness.json
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_ingest_canary_strict_promotion_readiness_unittest.py
git diff --check
```
