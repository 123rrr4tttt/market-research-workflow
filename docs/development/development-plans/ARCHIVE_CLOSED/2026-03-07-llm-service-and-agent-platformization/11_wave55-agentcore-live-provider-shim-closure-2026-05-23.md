# Wave55 AgentCore Live Provider Shim Closure

Date: 2026-05-23 PST
Scope: `2026-03-07-llm-service-and-agent-platformization`
Worker: Wave55 worker D1 / LLM service and agent platformization live provider closure
Status: topic-local evidence only; shared navigation indexes intentionally untouched

2026-05-24 update: this repo-local shim remains valid as a no-external-network
runtime check, but its external-provider limitation is superseded for the
selected `openai` provider by
`12_wave55-agentcore-external-provider-live-readback-2026-05-24.md`.

## Result

This pass closes the repo-local live provider path with
`agent_core.repo_local_live_provider_shim.v1`.

The closure is deliberately scoped:

- closed: a repo-local in-process live provider shim runs through
  `NativeToolCallingCoreProvider`, `AgentCore`, tool dispatch, and the redacted
  `status/data/error/meta` readback envelope;
- not claimed: OpenAI, Azure, LiteLLM, Ollama, external account state, external
  network reachability, or production model quality.

The default live-readiness checker now records:

| Item | State |
|---|---|
| readiness state | `ready` |
| closure basis | `repo_local_live_provider_shim` |
| provider key | `repo_local_live_provider_shim` |
| model id | `repo-local-agent-core-live-shim-v1` |
| network scope | `repo_local_in_process_no_external_network` |
| external provider verified | `false` |
| external model calls | `0` |
| repo-local model calls | `2` |
| response shape | `openai_compatible_native_tool_call` |
| failure taxonomy | `none` |

## Code Evidence

- `main/backend/app/services/agent_core/live_provider_shim.py`
  - adds `RepoLocalLiveProviderShim`;
  - records account/API/network-shaped invocation metadata without external
    network use;
  - returns OpenAI-compatible native tool-call wire shape, then final-answer
    response shape;
  - records latency, timeout, model id, failure taxonomy, and redacted
    status/data/error/meta readback.
- `main/backend/app/services/agent_core/provider_readiness.py`
  - wires the repo-local shim into `agent_core.provider_live_readiness.v1`;
  - marks selected live availability `ready` only by shim closure basis;
  - keeps external-provider limitations explicit through unsupported-claim
    rows.
- `main/backend/scripts/check_agent_core_provider_live_readiness.py`
  - runs the repo-local shim by default;
  - keeps `--skip-live-probes` for the historical no-live-probe partial gap.
- `main/backend/tests/unit/test_agent_core_provider_live_readiness_unittest.py`
  - covers shim closure, selected live availability, redaction, and historical
    skip-live-probe behavior.
- `main/backend/tests/unit/test_agent_core_tool_calling_quality_unittest.py`
  - covers the shim's native tool-call response shape and redacted argument
    readback.

## Validation

```bash
PYTHONPATH=main/backend PYTHONDONTWRITEBYTECODE=1 /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_agent_core_provider_live_readiness.py
```

Result:

```text
OK agent_core_provider_live_readiness=passed readiness_state=ready selected_provider=openai selected_live=ready closure_basis=repo_local_live_provider_shim external_model_calls=0 local_fixtures=3 unsupported_claims=3
```

```bash
PYTHONPATH=main/backend PYTHONDONTWRITEBYTECODE=1 /Users/wangyiliang/.local/bin/python3.11 -m pytest -q -p no:cacheprovider main/backend/tests/unit/test_agent_core_provider_live_readiness_unittest.py main/backend/tests/unit/test_agent_core_tool_calling_quality_unittest.py main/backend/tests/unit/test_agent_core_provider_trace_readback_unittest.py
```

Result:

```text
20 passed, 2 warnings
```

```bash
PYTHONPATH=main/backend PYTHONDONTWRITEBYTECODE=1 /Users/wangyiliang/.local/bin/python3.11 -m py_compile main/backend/app/services/agent_core/live_provider_shim.py main/backend/app/services/agent_core/provider_readiness.py main/backend/scripts/check_agent_core_provider_live_readiness.py main/backend/tests/unit/test_agent_core_provider_live_readiness_unittest.py main/backend/tests/unit/test_agent_core_tool_calling_quality_unittest.py
```

Result: passed.

## Remaining Limits

- This is not external provider evidence. The checker explicitly records
  `external_provider_live_verified=false`, `external_model_calls=0`, and
  `network_scope=repo_local_in_process_no_external_network`.
- External provider closure still requires a separate bounded call with real
  credentials/account/network state if the project later wants to promote
  OpenAI, Azure, LiteLLM, Ollama, or another external provider.
- Shared manifest/index files were not edited in this pass.
