# Wave9-7 AgentCore Platform Contract Evidence

Date: 2026-05-22 PST
Scope: `2026-03-07-llm-service-and-agent-platformization`
Status: topic-local evidence; no shared navigation or shared index edits in this worker branch

## Result

This pass closes the stale A7 delta at the minimum contract level. External long-horizon frameworks are still deferred, but the deferral is now grounded in a deterministic repo-native baseline rather than a generic roadmap statement.

The new baseline is:

1. `agent_core.tool_dispatch` is a first-class LLM platform consumer.
2. AgentCore tool schemas are exposed through the existing deterministic `CoreToolRegistry.schema_inventory()`.
3. Runtime dispatch is observed through stable AgentCore tool events and tool result envelopes.
4. The final evidence envelope preserves request identity, project scope, route/capability, permission boundary, and trace/audit status.

## Code Evidence

- `main/backend/app/services/llm/platformization.py`
  - adds `agent_tool_dispatch` as a normalized capability;
  - adds `agent_core.tool_dispatch` to the consumer boundary table;
  - sets routing owner to `agent_core.runtime_dispatcher`;
  - keeps role/permission governance in the existing `evaluate_agent_permission_boundary()` flow.
- `main/backend/app/services/agent_core/platform_contract.py`
  - adds `agent_core.platform_contract.v1`;
  - links request identity, consumer boundary, permission boundary, routing, schema inventory, runtime dispatch, and trace/audit evidence into one deterministic envelope;
  - intentionally omits raw event ids/timestamps so the contract can be tested as a stable artifact.
- `main/backend/scripts/check_agent_core_platform_contract.py`
  - builds a deterministic read-only probe tool;
  - runs it through `AgentCore` with `FakeCoreProvider`;
  - validates schema inventory -> dispatcher events -> tool result -> trace/audit envelope.
- `main/backend/tests/unit/test_agent_core_platform_contract_unittest.py`
  - asserts the envelope links inventory, runtime dispatch, and platform evidence;
  - asserts two independent snapshots are identical.

## Validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_agent_core_platform_contract.py --write-report development/latest-dev-docs/automation-runs/agent-core-platform-contract/2026-05-22/agent_core_platform_contract.json
```

Result:

```text
OK agent_core_platform_contract=passed tools=1 events=3 trace_id=trace-agent-core-platform-contract
```

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_agent_core_platform_contract_unittest.py main/backend/tests/unit/test_llm_platformization_unittest.py main/backend/tests/unit/test_agent_core_unittest.py::AgentCoreUnitTest::test_tool_registry_schema_inventory_is_deterministic_and_schema_complete
```

Result:

```text
10 passed, 2 warnings
```

```bash
python3 -m py_compile main/backend/app/services/agent_core/platform_contract.py main/backend/scripts/check_agent_core_platform_contract.py main/backend/app/services/llm/platformization.py
```

Result: passed.

## A7 Framework Gate Update

External framework adoption is additive only if it can prove a capability gap against this repo-native baseline:

- schema inventory: must exceed `agent_core.tool_schema_inventory.v1`, not replace it with an opaque tool catalog;
- runtime dispatcher: must preserve `tool_call_requested -> tool_call_started -> tool_result` or an equivalent inspectable sequence;
- permission boundary: must preserve `agent_core.tool_dispatch` role and permission decisions before tool execution;
- trace/audit evidence: must preserve `consumer`, `project_key`, `trace_id`, `request_id`, `capability`, `provider/model`, `status`, and degradation/error fields;
- validation: must keep this checker or an equivalent deterministic gate green.

If a framework duplicates the current schema, dispatcher, session, permission, or trace contracts without proving a missing capability, it remains deferred.

## Remaining Scope

- No provider matrix is sealed here.
- No live external framework is evaluated here.
- No shared index/archive move is performed here; an integration pass should update shared navigation after all Wave9 workers report back.
