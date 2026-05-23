# Wave9-1 Meaningful Ingest Guardrails Contract Evidence (2026-05-22)

status: `closed_narrow_runtime_contract`

scope:
- topic: `2026-03-02-meaningful-ingest-guardrails-plan`
- worker: `wave9-1-meaningful-ingest-guardrails`
- code slice: request-level meaningful gate switch, response visibility, and deterministic contract evidence

## Closed In This Slice

1. `strict_mode` now reaches the shared `frontdoor_ingress -> postprocess_frontdoor -> meaningful_gate` write path.
   - `main/backend/app/services/ingest/url_pool.py` adds `terminal_context.strict_mode = bool(strict_mode)` before `run_postprocess_frontdoor`.
   - `main/backend/app/services/ingest/postprocess_frontdoor.py` treats `terminal_context.strict_mode=true` as a request-level strict meaningful gate override even when `settings.ingest_enable_strict_gate=false`.

2. Response detail now exposes the gate switch that was actually used.
   - `quality_assessment.strict_gate_enabled`
   - `quality_assessment.strict_gate_source`
   - `quality_gates.gate_config.enable_strict_gate`
   - `quality_gates.gate_config.strict_gate_source`
   - `quality_gates.gate_config.min_semantic_len`

3. URL policy rejection is now deterministic under request strict mode.
   - With global strict gate disabled and `strict_mode=false`, a low-value `/search` URL can still pass as a rollout-compatible disabled gate.
   - With global strict gate disabled and `strict_mode=true`, the same `/search` URL rejects before write with `url_gate.reason=url_policy_low_value_endpoint`, projected response `reason_code=domain_blocked`, and `admission=reject`.

## Evidence

code:
- `main/backend/app/services/ingest/url_pool.py`
- `main/backend/app/services/ingest/postprocess_frontdoor.py`

tests:
- `main/backend/tests/unit/test_postprocess_frontdoor_unittest.py::test_frontdoor_quality_gate_strict_mode_forces_request_level_gate`
- `main/backend/tests/unit/test_postprocess_frontdoor_unittest.py::test_frontdoor_quality_gate_reads_runtime_settings`
- `main/backend/tests/unit/test_ingest_frontdoor_context_unittest.py::test_ingest_url_via_source_library_frontdoor_uses_source_library_bridge_and_postprocess_writer`

checker:
- `main/backend/scripts/check_meaningful_ingest_guardrails_contract.py`

validation commands:
- `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_meaningful_gate_unittest.py main/backend/tests/unit/test_postprocess_frontdoor_unittest.py main/backend/tests/unit/test_ingest_frontdoor_context_unittest.py main/backend/tests/unit/test_ingest_metrics_payload_unittest.py main/backend/tests/contract/test_ingest_response_contract_unittest.py`
- `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_meaningful_ingest_guardrails_contract.py --json`
- `python3 -m py_compile main/backend/app/services/ingest/postprocess_frontdoor.py main/backend/app/services/ingest/url_pool.py main/backend/scripts/check_meaningful_ingest_guardrails_contract.py`
- `git diff --check`

## Remaining Gap

remaining_gap:
- This slice does not flip `settings.ingest_enable_strict_gate` to global default `true`; rollout default remains settings-owned.
- This slice does not run a live `demo_proj` canary or inspect production-like 24h rejection metrics.
- This slice does not change source-library adapter auto-ingest beyond the existing `source_library_frontdoor` handoff path.

The topic should remain `partial` until global rollout/canary evidence exists, but the documented "开关与响应细节未完全对齐" gap is closed for the current single-URL/frontdoor write contract.
