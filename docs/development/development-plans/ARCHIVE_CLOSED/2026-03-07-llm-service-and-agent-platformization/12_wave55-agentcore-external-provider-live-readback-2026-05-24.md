# Wave55 AgentCore External Provider Live Readback

Date: 2026-05-24 PST
Scope: `2026-03-07-llm-service-and-agent-platformization`
Worker: T4 / AgentCore external provider live readback
Status: closed; parent integration moved the topic to `ARCHIVE_CLOSED` and removed it from the external-blocker manifest

## Result

This pass closes the previously external-only selected-provider blocker for
AgentCore:

- selected provider: `openai`;
- model: `gpt-4o-mini`;
- external provider/API/account/network invocation: closed by bounded live call;
- external model calls: `2`;
- native tool-call readback: valid;
- `status/data/error/meta` readback: compatible;
- reviewer readback: `accepted`;
- remaining blockers in this gate: `[]`.

The closure evidence is:

```text
development/latest-dev-docs/automation-runs/wave55-agentcore-external-provider-live-readback/2026-05-24/live_readback.json
```

## Code Evidence

- `main/backend/app/services/agent_core/external_provider_live_readback.py`
  - adds `agent_core.external_provider_live_readback.v1`;
  - requires explicit `allow_external_network` before spending provider calls;
  - records exact blocked states for missing provider config or disabled network;
  - runs `NativeToolCallingCoreProvider` through `AgentCore` against the selected
    configured provider when credentials are present;
  - records provider, model id, endpoint, account state, network scope, latency,
    response shape classification, tool-call readback, `status/data/error/meta`
    readback, reviewer assertions, and redaction state.
- `main/backend/scripts/check_agent_core_external_provider_live_readback.py`
  - exposes the gate with `--allow-external-network`, `--require-closed`,
    `--write-report`, and `--timeout-ms`.
- `main/backend/tests/unit/test_agent_core_external_provider_live_readback_unittest.py`
  - covers successful native tool-call readback, missing config blocker
    classification, and the explicit external-network opt-in guard.

## Validation

```bash
PYTHONPATH=main/backend PYTHONDONTWRITEBYTECODE=1 /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_agent_core_external_provider_live_readback.py --allow-external-network --require-closed --timeout-ms 30000 --write-report development/latest-dev-docs/automation-runs/wave55-agentcore-external-provider-live-readback/2026-05-24/live_readback.json
```

Result:

```text
OK agent_core_external_provider_live_readback=validated closed=true provider=openai model=gpt-4o-mini external_model_calls=2 latency_status=within_timeout remaining_blockers=0
```

```bash
PYTHONPATH=main/backend PYTHONDONTWRITEBYTECODE=1 /Users/wangyiliang/.local/bin/python3.11 -m pytest -q -p no:cacheprovider main/backend/tests/unit/test_agent_core_external_provider_live_readback_unittest.py main/backend/tests/unit/test_agent_core_provider_live_readiness_unittest.py main/backend/tests/unit/test_agent_core_tool_calling_quality_unittest.py
```

Result:

```text
16 passed, 2 warnings
```

## Closure Note

This supersedes the Wave23/Wave55 repo-local-only limitation for the selected
provider. Parent integration moved the directory out of
`ARCHIVE_EXTERNAL_BLOCKED` and into `ARCHIVE_CLOSED`.

This pass does not claim that every non-selected provider is live-ready, and it
does not adopt an external agent framework.
