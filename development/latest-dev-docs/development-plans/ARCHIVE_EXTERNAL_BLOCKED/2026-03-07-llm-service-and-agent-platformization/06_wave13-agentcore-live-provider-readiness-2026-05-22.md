# Wave13 AgentCore Live Provider Readiness Evidence

Date: 2026-05-22 PST
Scope: `2026-03-07-llm-service-and-agent-platformization`
Worker: Wave13 Worker 5 / AgentCore live provider readiness
Status: topic-local evidence only; shared navigation indexes intentionally untouched

## Result

This pass adds `agent_core.provider_live_readiness.v1`, a bounded readiness
contract for the live-provider gap left after the AgentCore schema, tool-dispatch,
and provider-matrix contracts.

The checker result is `passed`, while the readiness state remains `partial`.
That distinction is deliberate:

- local AgentCore provider fixtures are ready for `fake_core_provider`,
  `json_core_provider`, and `native_tool_calling_provider`;
- the selected configured LLM provider is `openai`;
- current OpenAI runtime configuration is recorded through the local Codex CLI
  fallback path;
- no external model call is made by this checker, so selected provider live
  availability remains `not_run`;
- Azure and LiteLLM are missing configuration, and `local` remains unsupported by
  the current `get_chat_model()` provider branch.

## Code Evidence

- `main/backend/app/services/agent_core/provider_readiness.py`
  - adds `agent_core.provider_live_readiness.v1`;
  - records configured provider rows for `openai`, `azure`, `ollama`, `litellm`,
    and `local`;
  - records Codex CLI fallback availability separately from direct OpenAI API key
    availability;
  - runs local no-network tool-dispatch fixtures through `FakeCoreProvider`,
    `JsonCoreProvider`, and `NativeToolCallingCoreProvider`;
  - records live availability gaps and unsupported closure claims without claiming
    live provider closure.
- `main/backend/scripts/check_agent_core_provider_live_readiness.py`
  - validates the readiness contract and can write the JSON evidence artifact.
- `main/backend/tests/unit/test_agent_core_provider_live_readiness_unittest.py`
  - covers missing OpenAI config, Codex CLI fallback configuration, unsupported
    `local` provider state, fixture drift validation, and checker snapshot reuse.
- `main/backend/app/services/agent_core/__init__.py`
  - exports the readiness contract builder for reuse.

## Evidence Artifact

Generated JSON:

```text
development/latest-dev-docs/automation-runs/agent-core-provider-live-readiness/2026-05-22/agent_core_provider_live_readiness.json
```

Key recorded state:

| Item | State |
|---|---|
| contract | `agent_core.provider_live_readiness.v1` |
| checker status | `passed` |
| readiness state | `partial` |
| selected provider | `openai` |
| selected live probe | `not_run` |
| local fixtures | `3 ready` |
| unsupported closure claims | `4` |

Unsupported closure claims remain explicit:

- `all_agentcore_providers_live_not_closed`
- `selected_provider_live_availability_not_closed`
- `native_tool_calling_quality_not_closed`
- `external_framework_live_adoption_not_closed`

## Validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_agent_core_provider_live_readiness.py --write-report development/latest-dev-docs/automation-runs/agent-core-provider-live-readiness/2026-05-22/agent_core_provider_live_readiness.json
```

Result:

```text
OK agent_core_provider_live_readiness=passed readiness_state=partial selected_provider=openai selected_live=not_run local_fixtures=3 unsupported_claims=4
```

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_agent_core_provider_live_readiness_unittest.py
```

Result:

```text
5 passed, 2 warnings
```

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m py_compile main/backend/app/services/agent_core/provider_readiness.py main/backend/scripts/check_agent_core_provider_live_readiness.py main/backend/app/services/agent_core/__init__.py
```

Result: passed.

## Remaining Scope

- This branch does not update shared navigation indexes.
- This branch does not spend an external OpenAI, Azure, LiteLLM, or Ollama model
  call.
- This branch does not claim native tool-calling production quality; the native
  fixture only proves local `bind_tools` dispatch shape.
- A later live-provider closure still needs a bounded live invocation probe with
  timeout, model id, response shape, and failure classification.
