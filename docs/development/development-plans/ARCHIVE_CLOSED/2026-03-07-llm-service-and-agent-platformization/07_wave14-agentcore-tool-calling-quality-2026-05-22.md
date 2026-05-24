# Wave14 AgentCore Tool-Calling Quality Evidence

Date: 2026-05-22 PST
Scope: `2026-03-07-llm-service-and-agent-platformization`
Worker: Wave14 Worker 9 / AgentCore native tool-calling quality
Status: topic-local evidence only; shared navigation indexes intentionally untouched

## Result

This pass adds `agent_core.tool_calling_quality.v1`, a deterministic no-network
quality gate for the AgentCore provider tool-call contract shape.

The checker result is `passed` and records:

- `deterministic_tool_calling_ready=true`
- `external_provider_live_gap=external_provider_live_gap`
- zero external model calls
- three local provider fixtures validated: `fake_core_provider`,
  `json_core_provider`, and `native_tool_calling_provider`

The production-quality boundary is deliberately split:

- deterministic provider adapters now prove the same `CoreToolCall` shape,
  schema validation, and runtime tool-event sequence;
- the native provider fixture validates OpenAI-style raw
  `additional_kwargs.tool_calls[].function.arguments` JSON-string shape and
  safe-name mapping back to the canonical tool name;
- real external provider quality is still not closed until a bounded live replay
  records model id, raw response shape, latency/failure class, and schema
  adherence counts.

## Code Evidence

- `main/backend/app/services/agent_core/contracts.py`
  - adds `agent_core.tool_call_shape.v1` and a stable
    `core_tool_call_contract_shape(...)` helper.
- `main/backend/app/services/agent_core/tool_calling_quality.py`
  - adds `agent_core.tool_calling_quality.v1`;
  - runs deterministic no-network fake/json/native provider fixtures;
  - validates tool-call shape, input schema, runtime event sequence, and tool
    result status;
  - keeps `external_provider_live_gap` and unsupported closure claims explicit.
- `main/backend/scripts/check_agent_core_tool_calling_quality.py`
  - validates the quality contract and writes JSON evidence.
- `main/backend/tests/unit/test_agent_core_tool_calling_quality_unittest.py`
  - covers provider rows, external live gap, validator drift rejection, checker
    reuse, deterministic snapshot behavior, and native OpenAI function-call raw
    shape extraction.

## Evidence Artifact

Generated JSON:

```text
development/latest-dev-docs/automation-runs/agent-core-tool-calling-quality/2026-05-22/agent_core_tool_calling_quality.json
```

Key recorded state:

| Item | State |
|---|---|
| contract | `agent_core.tool_calling_quality.v1` |
| checker status | `passed` |
| deterministic gate | `deterministic_tool_calling_ready=true` |
| external live gap | `external_provider_live_gap` |
| live model calls | `0` |
| local fixtures | `3 ready` |
| unsupported closure claims | `2` |

Unsupported closure claims remain explicit:

- `deterministic_fixture_proves_external_provider_quality`
- `native_tool_calling_quality_closed_without_live_replay`

## Validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_agent_core_tool_calling_quality.py --write-report development/latest-dev-docs/automation-runs/agent-core-tool-calling-quality/2026-05-22/agent_core_tool_calling_quality.json
```

Result:

```text
OK agent_core_tool_calling_quality=passed deterministic_tool_calling_ready=true external_provider_live_gap=external_provider_live_gap providers=3 live_model_calls=0
```

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_agent_core_tool_calling_quality_unittest.py
```

Result:

```text
5 passed, 2 warnings
```

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m py_compile main/backend/app/services/agent_core/contracts.py main/backend/app/services/agent_core/tool_calling_quality.py main/backend/scripts/check_agent_core_tool_calling_quality.py main/backend/tests/unit/test_agent_core_tool_calling_quality_unittest.py
```

Result: passed.

## Remaining Scope

- This branch does not update shared navigation indexes.
- This branch does not spend OpenAI, Azure, LiteLLM, Ollama, or other external
  provider calls.
- This branch does not claim native tool-calling production quality for a live
  model; it only closes the deterministic adapter shape gate.
- A later live-provider quality closure still needs bounded live replay evidence
  with timeout, model id, raw tool-call response shape, schema-adherence counts,
  latency, and failure classification.
