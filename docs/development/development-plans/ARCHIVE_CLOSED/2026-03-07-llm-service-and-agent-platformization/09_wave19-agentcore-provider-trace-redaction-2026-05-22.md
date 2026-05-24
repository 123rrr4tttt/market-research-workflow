# Wave19 AgentCore Provider Trace Redaction Evidence

Date: 2026-05-22 PST
Scope: `2026-03-07-llm-service-and-agent-platformization`
Worker: Wave19 Worker 6 / AgentCore provider redaction
Status: topic-local evidence only; shared navigation indexes intentionally untouched

## Result

This pass extends the deterministic AgentCore provider trace readback with
`agent_core.provider_trace_redaction_replay.v1`. The checker still uses only
`FakeCoreProvider`, still spends `external_model_calls=0`, and still leaves
`real_external_provider_call_open=true`.

The new redaction replay records:

- `provider_trace_redaction_ready=true`
- `provider_trace_redaction=true`
- `tool_call_arguments_redacted=true`
- `raw_sensitive_values_absent=true`
- `raw_request_body_persisted=false`
- `raw_tool_arguments_persisted=false`

The provider replay now stores request and tool-call body material as redaction
metadata only: marker, type, length, and SHA-256. It keeps inspectable envelope
shape, event order, provider call count, status/data/error/meta compatibility,
and input gate readbacks without writing the fixture request body into evidence.

## Code Evidence

- `main/backend/app/services/agent_core/provider_trace.py`
  - adds `agent_core.provider_trace_redaction_replay.v1`;
  - replaces persisted provider message bodies with `[REDACTED]` plus stable
    fingerprints;
  - replaces `tool_call_contract.arguments` with key lists and value
    fingerprints instead of raw argument values;
  - replays `tool_call_requested -> tool_call_started -> tool_result` with
    redacted argument snapshots;
  - exposes redaction flags and raw-persistence checks for the deterministic
    sensitive fixture bodies;
  - keeps `real_external_provider_call_open=true` and `external_model_calls=0`.
- `main/backend/scripts/check_agent_core_provider_trace_readback.py`
  - prints redaction readiness in the focused checker OK line.
- `main/backend/tests/unit/test_agent_core_provider_trace_readback_unittest.py`
  - covers redacted provider messages, redacted tool-call envelope arguments,
    the redaction replay contract, validator rejection for raw persistence, and
    deterministic snapshot behavior.

## Evidence Artifact

Generated JSON:

```text
development/latest-dev-docs/automation-runs/agent-core-provider-trace-redaction/2026-05-22/agent_core_provider_trace_redaction.json
```

Key recorded state:

| Item | State |
|---|---|
| base contract | `agent_core.provider_trace_readback.v1` |
| redaction replay | `agent_core.provider_trace_redaction_replay.v1` |
| checker status | `passed` |
| fake provider calls | `2` |
| tool event sequence | `tool_call_requested -> tool_call_started -> tool_result` |
| request body persistence | `false` |
| tool argument raw persistence | `false` |
| raw sensitive values absent | `true` |
| real external provider call | `open` |
| external model calls | `0` |

## Validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_agent_core_provider_trace_readback_unittest.py
```

Result:

```text
7 passed, 2 warnings
```

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_agent_core_provider_trace_readback.py
```

Result:

```text
OK agent_core_provider_trace_readback=passed provider=fake_core_provider provider_calls=2 status_data_error_meta=true provider_trace_redaction=true tool_call_arguments_redacted=true real_external_provider_call_open=true external_model_calls=0
```

The unit test serializes the full contract and checks the exact deterministic
fixture bodies are absent from the persisted snapshot.

## Remaining Scope

- This branch does not update shared navigation indexes.
- This branch does not spend external model calls.
- This branch does not prove live OpenAI, Azure, LiteLLM, Ollama, or other
  external-provider behavior.
- Live provider closure still requires a bounded external invocation with model
  id, timeout, raw response shape classification, latency, and failure taxonomy,
  while preserving the same redacted trace envelope.
