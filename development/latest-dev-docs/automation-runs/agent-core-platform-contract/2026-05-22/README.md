# AgentCore Platform Contract Check

Date: 2026-05-22 PST

## Command

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_agent_core_platform_contract.py --write-report development/latest-dev-docs/automation-runs/agent-core-platform-contract/2026-05-22/agent_core_platform_contract.json
```

## Result

```text
OK agent_core_platform_contract=passed tools=1 events=3 trace_id=trace-agent-core-platform-contract
```

## Artifact

- `agent_core_platform_contract.json`

## Scope Boundary

This run uses a deterministic read-only probe tool and `FakeCoreProvider`. It does not claim live provider availability or external framework readiness.
