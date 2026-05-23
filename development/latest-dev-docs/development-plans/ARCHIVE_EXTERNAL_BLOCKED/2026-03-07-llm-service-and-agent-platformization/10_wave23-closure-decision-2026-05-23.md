# Wave23 Closure Decision: LLM Service And Agent Platformization

Date: 2026-05-23 PST
Decision: `archive_external_blocked_candidate`
Scope: `development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-03-07-llm-service-and-agent-platformization`

## Decision

This topic can leave `CURRENT_DEV` as an `ARCHIVE_EXTERNAL_BLOCKED` candidate.

Repo-local deterministic work is closed at the current boundary:

- A1-A8 are `closed-minimal` in `02_atomic-tasklist-llm-service-and-agent-platformization-2026-03-07.md`.
- Wave9/Wave11 establish the AgentCore platform contract, provider matrix, and external-framework deferral boundary through `main/backend/scripts/check_agent_core_platform_contract.py`.
- Wave13/Wave14/Wave18/Wave19 establish deterministic provider readiness, tool-calling quality, provider trace readback, and redaction replay.

The only remaining closure condition is external/non-repo-local: a bounded live provider invocation with real credentials/network/account state, recording model id, timeout, raw response or tool-call shape classification, latency, failure taxonomy, and the same redacted `status/data/error/meta` trace envelope.

## Evidence Checked

- Topic docs:
  - `01_llm-service-and-agent-platformization-plan-2026-03-07.md`
  - `02_atomic-tasklist-llm-service-and-agent-platformization-2026-03-07.md`
  - `03_wave6-5-status-evidence-and-min-plan-2026-05-22.md`
  - `04_wave9-7-agent-core-platform-contract-evidence-2026-05-22.md`
  - `05_wave11-agentcore-provider-matrix-evidence-2026-05-22.md`
  - `06_wave13-agentcore-live-provider-readiness-2026-05-22.md`
  - `07_wave14-agentcore-tool-calling-quality-2026-05-22.md`
  - `08_wave18-agentcore-provider-trace-readback-2026-05-22.md`
  - `09_wave19-agentcore-provider-trace-redaction-2026-05-22.md`
- Shared status surfaces:
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/STATUS_AUDIT_2026-04-07.md`
- Referenced scripts/tests:
  - `main/backend/scripts/check_agent_core_platform_contract.py`
  - `main/backend/scripts/check_agent_core_provider_live_readiness.py`
  - `main/backend/scripts/check_agent_core_tool_calling_quality.py`
  - `main/backend/scripts/check_agent_core_provider_trace_readback.py`
  - `main/backend/tests/unit/test_llm_platformization_unittest.py`
  - `main/backend/tests/unit/test_writing_llm_action_service_unittest.py`
  - `main/backend/tests/unit/test_workflow_graph_runtime_unittest.py`
  - `main/backend/tests/unit/test_agent_core_platform_contract_unittest.py`
  - `main/backend/tests/unit/test_agent_core_provider_live_readiness_unittest.py`
  - `main/backend/tests/unit/test_agent_core_tool_calling_quality_unittest.py`
  - `main/backend/tests/unit/test_agent_core_provider_trace_readback_unittest.py`
  - `main/backend/tests/unit/test_agent_core_unittest.py`
  - `scripts/check_current_dev_wave11_plan.py` was inspected as a historical Wave11 branch-plan guard; it is not a reusable closure gate for this supervisor branch.
- Existing automation artifacts:
  - `development/latest-dev-docs/automation-runs/agent-core-platform-contract/2026-05-22/agent_core_platform_contract.json`
  - `development/latest-dev-docs/automation-runs/agent-core-provider-live-readiness/2026-05-22/agent_core_provider_live_readiness.json`
  - `development/latest-dev-docs/automation-runs/agent-core-tool-calling-quality/2026-05-22/agent_core_tool_calling_quality.json`
  - `development/latest-dev-docs/automation-runs/agent-core-provider-trace-readback/2026-05-22/agent_core_provider_trace_readback.json`
  - `development/latest-dev-docs/automation-runs/agent-core-provider-trace-redaction/2026-05-22/agent_core_provider_trace_redaction.json`

## Current Deterministic Gate

Commands rerun without writing reports:

```bash
PYTHONPATH=main/backend PYTHONDONTWRITEBYTECODE=1 /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_agent_core_platform_contract.py
PYTHONPATH=main/backend PYTHONDONTWRITEBYTECODE=1 /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_agent_core_provider_live_readiness.py
PYTHONPATH=main/backend PYTHONDONTWRITEBYTECODE=1 /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_agent_core_tool_calling_quality.py
PYTHONPATH=main/backend PYTHONDONTWRITEBYTECODE=1 /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_agent_core_provider_trace_readback.py
PYTHONPATH=main/backend PYTHONDONTWRITEBYTECODE=1 /Users/wangyiliang/.local/bin/python3.11 -m pytest -q -p no:cacheprovider main/backend/tests/unit/test_llm_platformization_unittest.py main/backend/tests/unit/test_writing_llm_action_service_unittest.py main/backend/tests/unit/test_workflow_graph_runtime_unittest.py main/backend/tests/unit/test_agent_core_platform_contract_unittest.py main/backend/tests/unit/test_agent_core_provider_live_readiness_unittest.py main/backend/tests/unit/test_agent_core_tool_calling_quality_unittest.py main/backend/tests/unit/test_agent_core_provider_trace_readback_unittest.py main/backend/tests/unit/test_agent_core_unittest.py::AgentCoreUnitTest::test_tool_registry_schema_inventory_is_deterministic_and_schema_complete
```

Observed results:

- `OK agent_core_platform_contract=passed tools=1 events=3 trace_id=trace-agent-core-platform-contract`
- `OK agent_core_provider_live_readiness=passed readiness_state=partial selected_provider=openai selected_live=not_run local_fixtures=3 unsupported_claims=4`
- `OK agent_core_tool_calling_quality=passed deterministic_tool_calling_ready=true external_provider_live_gap=external_provider_live_gap providers=3 live_model_calls=0`
- `OK agent_core_provider_trace_readback=passed provider=fake_core_provider provider_calls=2 status_data_error_meta=true provider_trace_redaction=true tool_call_arguments_redacted=true real_external_provider_call_open=true external_model_calls=0`
- `43 passed, 3 warnings in 8.97s`

## Migration Recommendation

Move this directory to `development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-03-07-llm-service-and-agent-platformization/` in the parent integration pass, then update the shared indexes there. Do not label it `ARCHIVE_CLOSED`: no live external provider/API/account/network invocation has been recorded.
