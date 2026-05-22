# Wave12 Ingest Canary Handoff Evidence

Date: 2026-05-22
Scope: `2026-03-02-meaningful-ingest-guardrails-plan`

## status

`partial_canary_handoff_visibility_landed`

## contract advanced

Wave11 landed deterministic guardrail rollout decisions and metrics visibility. This slice adds the handoff envelope that can be passed from a single URL/frontdoor run into the next canary step:

- `strict_gate_state` records whether strict mode was disabled, passed, blocked, or still pending.
- `rollout.channel` records whether the decision came from canary rollout, global default, request override, settings override, passthrough, or disabled state.
- `metrics_snapshot.guardrail_rollout` carries sample size, strict-enabled sample count, canary-matched sample count, rollout mode counts, and strict-gate source counts.
- `remaining_live_run_gaps` stays populated unless live canary validation and closure are explicitly true.

## evidence

- `main/backend/app/services/ingest/canary_handoff.py`
- `main/backend/app/services/ingest/postprocess_frontdoor.py`
- `main/backend/app/services/ingest/url_pool.py`
- `main/backend/scripts/check_ingest_canary_handoff_contract.py`
- `main/backend/tests/unit/test_ingest_canary_handoff_unittest.py`

## remaining live-run gaps

partial remains because live canary was not run in this worker slice.

- No live `demo_proj` canary was executed against configured services.
- No 24h rejection-rate or inserted-valid ratio was inspected.
- `settings.ingest_enable_strict_gate` remains a production operations decision.
- The envelope therefore keeps `live_canary_validated=false` and `closure_claim=false`.

## validation

```bash
python3 scripts/check_current_dev_wave12_plan.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_canary_handoff_contract.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_ingest_canary_handoff_unittest.py
git diff --check
```
