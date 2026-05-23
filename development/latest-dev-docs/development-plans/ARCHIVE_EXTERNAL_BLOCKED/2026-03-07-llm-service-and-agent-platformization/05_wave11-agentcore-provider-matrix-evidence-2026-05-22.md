# Wave11 AgentCore Provider Matrix Evidence

Date: 2026-05-22 PST
Scope: `2026-03-07-llm-service-and-agent-platformization`
Worker: Wave11 Worker 3 / AgentCore provider matrix
Status: topic-local evidence only; shared indexes intentionally untouched

## Result

This pass adds a deterministic AgentCore provider-capability matrix to the existing
`agent_core.platform_contract.v1` envelope.

The matrix is explicitly a static contract inventory, not a live provider probe.
It separates four boundary states:

- `repo_native_supported`: deterministic repo-native AgentCore capability that can be
  validated without external provider access.
- `missing_config`: repo-native provider adapter exists, but runtime provider/model or
  tool-calling configuration is not asserted by this branch.
- `blocked_permissions`: AgentCore permission policy blocks the requested capability.
- `deferred_external_framework`: external framework adoption remains conditional on a
  written gap delta against the repo-native AgentCore and workflow graph baseline.

No external framework dependency was added, and no row claims that every provider is
live usable.

## Code Evidence

- `main/backend/app/services/agent_core/platform_contract.py`
  - adds `agent_core.provider_capability_matrix.v1`;
  - adds `agent_core.external_framework_boundary.v1`;
  - embeds the provider matrix into the AgentCore platform contract;
  - marks the matrix as `static_contract_not_live_probe`;
  - keeps `live_provider_claims=false`;
  - records repo-native support, missing config, blocked permission, and deferred
    external-framework rows.
- `main/backend/scripts/check_agent_core_platform_contract.py`
  - validates the matrix version, static evaluation mode, no-live-claim invariant,
    and all four boundary statuses;
  - validates that `cross_consumer.invoke` remains blocked for the AgentCore provider
    baseline;
  - validates that external framework adoption is still deferred.
- `main/backend/tests/unit/test_agent_core_platform_contract_unittest.py`
  - asserts the matrix is linked from the platform contract;
  - asserts each boundary status is present and distinguishable;
  - preserves deterministic snapshot behavior.
- `main/backend/app/services/agent_core/__init__.py`
  - exports `build_provider_capability_matrix` for direct contract reuse.

## Boundary Notes

- The `fake_core_provider` row is repo-native supported because it is deterministic
  test infrastructure for the AgentCore contract. It is not a production live-provider
  claim.
- `json_core_provider` and `native_tool_calling_provider` remain `missing_config` in
  this checker because the branch does not assert provider/model/tool-calling runtime
  config.
- The permission boundary row keeps cross-consumer invocation blocked rather than
  treating it as a provider gap.
- External frameworks are represented only as evaluation candidates. They remain
  deferred unless a later written delta proves additive capability beyond:
  - schema inventory;
  - ordered runtime dispatch evidence;
  - permission checks before execution;
  - trace/audit preservation;
  - deterministic checker coverage.

## Validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_agent_core_platform_contract.py
```

Result:

```text
OK agent_core_platform_contract=passed tools=1 events=3 trace_id=trace-agent-core-platform-contract
```

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_agent_core_platform_contract_unittest.py
```

Result:

```text
3 passed, 2 warnings
```

```bash
python3 -m py_compile main/backend/app/services/agent_core/platform_contract.py main/backend/scripts/check_agent_core_platform_contract.py main/backend/app/services/agent_core/__init__.py
```

Result: passed.

```bash
python3 scripts/check_current_dev_wave11_plan.py
```

Result:

```text
OK wave11_current_dev_plan=passed mode=codex/devdocs-wave11-agentcore-provider-matrix branches=9 changed_files=5 worker_boundary_enforced=true
```

```bash
git diff --check
```

Result: passed.

## Remaining Scope

- This branch does not update shared docs indexes.
- This branch does not evaluate or adopt LangGraph, Semantic Kernel, CrewAI, or any
  other external agent framework.
- This branch does not claim live availability for all AgentCore providers.
