# Wave18 AgentCore Provider Trace Readback Evidence

Date: 2026-05-22 PST
Scope: `2026-03-07-llm-service-and-agent-platformization`
Worker: Wave18 Worker 7 / AgentCore provider trace
Status: topic-local evidence only; shared navigation indexes intentionally untouched

## Result

This pass adds `agent_core.provider_trace_readback.v1`, a deterministic
no-network readback for the AgentCore live-provider boundary left open after
Wave11, Wave13, and Wave14.

The checker result is `passed` and records:

- `deterministic_provider_trace_ready=true`
- `provider=fake_core_provider`
- `provider_calls=2`
- `status_data_error_meta=true`
- `real_external_provider_call_open=true`
- `external_model_calls=0`

The result is deliberately narrow. It proves that the fake provider trace,
tool-call event sequence, and `status/data/error/meta` envelope survive the
AgentCore runtime loop. It does not claim that OpenAI, Azure, LiteLLM, Ollama, or
another external model provider has completed a live invocation.

## Code Evidence

- `main/backend/app/services/agent_core/provider_trace.py`
  - adds `agent_core.provider_trace_readback.v1`;
  - runs a deterministic `FakeCoreProvider` turn through `AgentCore`;
  - reads back provider calls before and after tool execution;
  - validates `agent_core.tool_call_shape.v1` and the runtime
    `tool_call_requested -> tool_call_started -> tool_result` sequence;
  - validates a tool result envelope with exactly `status`, `data`, `error`,
    and `meta`;
  - records `real_external_provider_call_open=true` and `external_model_calls=0`.
- `main/backend/scripts/check_agent_core_provider_trace_readback.py`
  - validates the provider-trace readback contract and can write JSON evidence.
- `main/backend/tests/unit/test_agent_core_provider_trace_readback_unittest.py`
  - covers fake-provider trace readback, tool-call envelope readback,
    `status/data/error/meta` compatibility, Wave11/Wave13/Wave14 input
    readbacks, open live-provider gap validation, checker reuse, and deterministic
    snapshot behavior.
- `main/backend/app/services/agent_core/__init__.py`
  - exports the provider trace readback builder for direct contract reuse.

## Input Readbacks

The Wave18 contract reads the earlier gates as inputs instead of replacing them:

| Input | Readback |
|---|---|
| Wave11 provider matrix | `agent_core.provider_capability_matrix.v1`; `evaluation_mode=static_contract_not_live_probe`; `live_provider_claims=false`; `fake_core_provider_status=repo_native_supported` |
| Wave13 live-provider readiness | `agent_core.provider_live_readiness.v1`; `readiness_state=partial`; selected provider `openai`; selected live probe `blocked` in the deterministic fixture |
| Wave14 tool-calling quality | `agent_core.tool_calling_quality.v1`; `deterministic_tool_calling_ready=true`; `external_provider_live_gap=external_provider_live_gap`; `live_model_calls=0` |

Unsupported closure claims remain explicit:

- `real_external_provider_call_open`
- `fake_provider_trace_does_not_close_live_provider_quality`

## Evidence Artifact

Generated JSON:

```text
development/latest-dev-docs/automation-runs/agent-core-provider-trace-readback/2026-05-22/agent_core_provider_trace_readback.json
```

Key recorded state:

| Item | State |
|---|---|
| contract | `agent_core.provider_trace_readback.v1` |
| checker status | `passed` |
| fake provider calls | `2` |
| tool event sequence | `tool_call_requested -> tool_call_started -> tool_result` |
| status/data/error/meta compatible | `true` |
| real external provider call | `open` |
| external model calls | `0` |

## Validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_agent_core_provider_trace_readback.py --write-report development/latest-dev-docs/automation-runs/agent-core-provider-trace-readback/2026-05-22/agent_core_provider_trace_readback.json
```

Result:

```text
OK agent_core_provider_trace_readback=passed provider=fake_core_provider provider_calls=2 status_data_error_meta=true real_external_provider_call_open=true external_model_calls=0
```

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_agent_core_provider_trace_readback_unittest.py
```

Result:

```text
5 passed, 2 warnings
```

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m py_compile main/backend/app/services/agent_core/provider_trace.py main/backend/scripts/check_agent_core_provider_trace_readback.py main/backend/tests/unit/test_agent_core_provider_trace_readback_unittest.py main/backend/app/services/agent_core/__init__.py
```

Result: passed.

## Remaining Scope

- This branch does not update shared navigation indexes.
- This branch does not spend external model calls.
- This branch does not close live external provider availability or production
  tool-calling quality.
- The next closure step remains a bounded live-provider probe with timeout,
  model id, raw response shape, latency, and failure classification while
  preserving the same trace and `status/data/error/meta` readback envelope.
