# Wave6-5 Status Evidence and Minimum Plan

Date: 2026-05-22 PST
Status: status evidence plus one minimal agent-core schema-inventory patch
Scope: `2026-03-07-llm-service-and-agent-platformization`, backend LLM platformization, AgentCore tool registry, focused unit/contract tests

## 1. Scope Boundary

This pass does not edit shared navigation surfaces:

- `development/latest-dev-docs/README.md`
- `development/latest-dev-docs/MERGED_OVERVIEW.md`
- `development/latest-dev-docs/development-plans/INDEX.md`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`

The topic should remain in `CURRENT_DEV` for now. The repo evidence closes the minimum platform contract work, but the long-horizon framework gate still needs a dedicated update before any archive or shared-index integration pass.

## 2. Status Matrix

| Task | Status | Evidence | Current action |
|---|---|---|---|
| `A1` baseline reconciliation | Closed-minimal | The anchors named by the plan exist: `main/backend/app/services/llm/*`, `main/backend/app/api/llm_config.py`, `main/backend/app/services/writing/llm_action_service.py`, `main/backend/app/api/llm_report.py`, `main/backend/app/services/workflow_graph/executors/llm_call.py`. | Marked closed-minimal in `02`. |
| `A2` shared vocabulary | Closed-minimal | `main/backend/app/services/llm/platformization.py` defines normalized capability names, request identity, route decision, consumer boundary, and agent role vocabulary. | Keep code vocabulary as the source of truth. |
| `A3` config/routing boundary | Closed-minimal | `resolve_routing_decision()` applies request override, service config, default provider/model, and field-source tracking. Workflow `llm_call`, writing actions, and report generation consume it. | Keep provider routing owned by `llm.platformization_routing`. |
| `A4` trace/audit rules | Closed-minimal | `build_trace_audit_record()` records consumer, project, trace, request, actor, service, capability, route, provider/model, status, degraded flag, and error fields. Consumer responses preserve these in observability/meta payloads. | Preserve trace/audit fields in new consumers. |
| `A5` consumer adapter map | Closed-minimal | `_CONSUMER_BOUNDARY_TABLE` maps `writing.llm_action`, `llm_report.generate`, and `workflow_graph.llm_call` to capability, validation owner, routing owner, observability owner, default agent role, allowed roles, and permissions. | New consumers should be added through this table or an equivalent typed registry. |
| `A6` agent position/permission boundary | Closed-minimal | Agent roles are split into `user_facing_assistant`, `orchestration_runtime`, and `business_capability_wrapper`; `evaluate_agent_permission_boundary()` blocks role/permission violations before LLM invocation. | Treat AgentCore as a governed consumer of platform capability, not a bypass path. |
| `A7` long-horizon framework evaluation | Needs-update | Later AgentCore work has made repo-native tool registry, session state, permission, and model-owned tool loops much more concrete than this March plan assumed. | Defer framework adoption until a written delta shows what an external framework adds beyond AgentCore plus workflow graph. |
| `A8` minimum validation pack | Closed-minimal | Existing tests cover platformization routing/permission, writing action observability, workflow `llm_call` trace/audit, and AgentCore registry behavior. This pass adds a deterministic registry schema-inventory contract. | Keep the focused validation commands below as the reusable gate. |

## 3. Outdated Items

- The original task list said all tasks were pending. That is now stale relative to the implemented `llm.platformization` contract and the three current consumers.
- The original agent discussion predates the current AgentCore/tool-registry implementation depth. Agent platformization should now start from `main/backend/app/services/agent_core/*`, not from a generic future framework story.
- The plan still treats long-horizon framework evaluation as a near-term planning task. It should become a delta test against current repo-native capabilities.

## 4. Not Sealed

- No shared index or archive move was performed in this branch.
- `A7` is not sealed: there is no current, repo-grounded framework-fit document comparing an external framework against AgentCore, workflow graph, tool schema inventory, session recovery, permission gates, and trace/audit fields.
- This pass does not claim a permanent provider matrix. Provider/model availability remains config and environment dependent.

## 5. Minimum Implementation Landed

AgentCore already had `CoreToolSpec`, `CoreToolRegistry.list_specs()`, and schema-bearing projected project tools, but there was no stable inventory envelope for audits or future framework-fit comparison.

This pass adds `CoreToolRegistry.schema_inventory()`:

- contract version: `agent_core.tool_schema_inventory.v1`
- deterministic tool ordering by name
- full spec projection via `CoreToolSpec.to_dict()`
- summary counts by source, risk, permission, and concurrency

The method is read-only and does not change tool execution behavior.

## 6. Minimum Development Plan

1. Keep this topic in `CURRENT_DEV` until a separate integration pass updates shared indexes.
2. Use `CoreToolRegistry.schema_inventory()` as the canonical AgentCore tool/schema audit surface.
3. For new LLM or agent consumers, require a consumer-boundary row with capability, validation owner, routing owner, observability owner, agent role, and permissions before adding runtime code.
4. For any external framework proposal, write one delta document that answers:
   - which AgentCore or workflow-graph capability is missing;
   - which schema/permission/session/trace contract would be delegated;
   - which existing tests would remain the acceptance gate;
   - why the framework is additive rather than duplicative.
5. Only after the A7 delta exists should an archive/shared-index pass decide whether this March topic can leave `CURRENT_DEV`.

## 7. Validation Gate

Focused commands for this topic:

```bash
git diff --check
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_llm_platformization_unittest.py main/backend/tests/unit/test_writing_llm_action_service_unittest.py main/backend/tests/unit/test_workflow_graph_runtime_unittest.py main/backend/tests/unit/test_agent_core_unittest.py::AgentCoreUnitTest::test_tool_registry_schema_inventory_is_deterministic_and_schema_complete
```

Expected coverage:

- LLM capability/routing/consumer/agent boundary contract.
- Writing action platform observability.
- Workflow `llm_call` route, trace, and blocked permission behavior.
- AgentCore deterministic tool schema inventory.

Wave6-5 run result:

- `git diff --check`: passed.
- Focused pytest gate: `23 passed, 3 warnings in 14.76s`.
- Warnings: existing Pydantic deprecation warnings from the backend test environment.
