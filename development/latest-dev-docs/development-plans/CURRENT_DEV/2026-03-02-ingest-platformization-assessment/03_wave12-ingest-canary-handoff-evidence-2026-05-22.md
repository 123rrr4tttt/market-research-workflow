# Wave12 Ingest Canary Handoff Evidence

Date: 2026-05-22
Scope: `2026-03-02-ingest-platformization-assessment`

## status

`partial_canary_handoff_contract_landed`

## contract advanced

This slice adds a bounded repository-level handoff for the platformized ingest frontdoor:

- `main/backend/app/services/ingest/canary_handoff.py` defines `ingest.single_url_canary_handoff.v1`.
- `postprocess_frontdoor` attaches `data.canary_handoff` after strict gate evaluation for accepted, rejected, and cleanup-returned document candidates.
- `url_pool._run_source_library_frontdoor_ingress` promotes that envelope to the single URL/frontdoor result as `canary_handoff`.
- The envelope carries strict gate state, rollout channel, deterministic task-local metrics snapshot, and remaining live-run gaps.

## evidence

- Strict gate state includes `strict_gate_enabled`, `strict_gate_source`, gate result state, admission, reason code, blocked stage, and quality booleans.
- Rollout channel resolves to `canary`, `global`, `request_override`, `settings_override`, `passthrough`, or `disabled`.
- Metrics snapshot is derived from the existing ingest metrics payload shape and includes guardrail rollout sample counts.
- `main/backend/scripts/check_ingest_canary_handoff_contract.py` validates the deterministic canary handoff without opening live services.

## remaining live-run gaps

partial remains because live canary was not run in this worker slice.

- No `demo_proj` live canary execution was run against configured services.
- No 24h rejection-rate or inserted-valid ratio was inspected.
- Production all-project strict-gate enablement remains operations-owned.

## validation

```bash
python3 scripts/check_current_dev_wave12_plan.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_canary_handoff_contract.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_ingest_canary_handoff_unittest.py
git diff --check
```
