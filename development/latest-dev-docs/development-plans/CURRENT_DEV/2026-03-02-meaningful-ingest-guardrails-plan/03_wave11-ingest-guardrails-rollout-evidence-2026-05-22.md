# Wave11 Ingest Guardrails Rollout Evidence (2026-05-22)

status: `closed_narrow_rollout_contract`

scope:
- topic: `2026-03-02-meaningful-ingest-guardrails-plan`
- worker: `wave11-worker-1-ingest-guardrails-rollout`
- code slice: backend guardrail rollout defaults plus deterministic canary metrics visibility

## Closed In This Slice

1. Guardrail rollout now has a bounded backend decision contract.
   - `main/backend/app/services/ingest/guardrail_rollout.py` resolves strict gate enablement from:
     - `settings.ingest_enable_strict_gate`
     - request `meaningful_gate_config.enable_strict_gate`
     - request `strict_mode`
     - repo rollout mode `ingest_guardrail_rollout_mode`
   - Default rollout mode is `canary` with `ingest_guardrail_canary_projects=demo_proj`.
   - Rollout defaults are eligible only for URL-execution/frontdoor ingest; non-URL flows such as `raw_import` are not pulled into canary strict mode unless an explicit strict override is supplied.
   - The decision payload keeps `live_canary_validated=false` and `closure_claim=false`.

2. Postprocess response visibility now includes rollout source and canary match.
   - `quality_assessment.strict_gate_enabled`
   - `quality_assessment.strict_gate_source`
   - `quality_assessment.guardrail_rollout_mode`
   - `quality_assessment.guardrail_canary_matched`
   - `quality_gates.gate_config.guardrail_rollout`

3. Canary metrics are deterministic in task-local metrics payloads.
   - `metrics_payload.guardrail_rollout.strict_enabled_samples`
   - `metrics_payload.guardrail_rollout.canary_matched_samples`
   - `metrics_payload.guardrail_rollout.global_default_samples`
   - `metrics_payload.guardrail_rollout.rollout_mode_counts`
   - `metrics_payload.guardrail_rollout.strict_gate_source_counts`
   - `metrics_payload.guardrail_rollout.live_canary_validated=false`
   - `metrics_payload.guardrail_rollout.closure_claim=false`

4. The focused checker verifies the narrow contract without opening production services.
   - `main/backend/scripts/check_meaningful_ingest_guardrails_rollout_contract.py`
   - Canary project `demo_proj` rejects a low-value `/search` URL through the rollout default.
   - Non-canary project keeps the same request accepted when no strict-mode override is present.

## Evidence

code:
- `main/backend/app/settings/config.py`
- `main/backend/app/services/ingest/guardrail_rollout.py`
- `main/backend/app/services/ingest/postprocess_frontdoor.py`
- `main/backend/app/services/ingest/url_pool.py`
- `main/backend/app/services/ingest/metrics_payload.py`

tests:
- `main/backend/tests/unit/test_ingest_frontdoor_rollout_unittest.py`
- `main/backend/tests/unit/test_postprocess_frontdoor_unittest.py`
- `main/backend/tests/unit/test_ingest_metrics_payload_unittest.py`

checker:
- `main/backend/scripts/check_meaningful_ingest_guardrails_rollout_contract.py`

validation commands:
- `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_ingest_frontdoor_rollout_unittest.py main/backend/tests/unit/test_postprocess_frontdoor_unittest.py main/backend/tests/unit/test_ingest_metrics_payload_unittest.py`
- `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_meaningful_ingest_guardrails_rollout_contract.py --json`
- `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_meaningful_ingest_guardrails_contract.py --json`
- `python3 scripts/check_current_dev_wave11_plan.py`
- `git diff --check`

## Closed Narrowly

This slice closes the repository-level deterministic contract for canary-scoped rollout defaults and response/metrics visibility. It proves that the backend can distinguish canary vs non-canary guardrail decisions and can surface the decision in both per-request quality fields and task-local metrics payloads.

## Remaining Partial

remaining_gap:
- No live `demo_proj` canary was executed against configured production-like services in this slice.
- No 24h rejection-rate or inserted-valid ratio was inspected.
- `settings.ingest_enable_strict_gate` remains default `false`; production all-project strict enablement remains partial and operations-owned.
- Source policy tuning remains future work after live canary evidence.

The topic should remain `partial` for production rollout until live canary evidence and global rollout approval exist.
