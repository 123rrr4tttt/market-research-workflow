from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.services.agent_core import (
    AgentCore,
    AgentCoreRequest,
    CoreModelStep,
    CoreToolCall,
    CoreToolRegistry,
    CoreToolResult,
    CoreToolSpec,
    FakeCoreProvider,
    build_agent_core_platform_contract,
)


def build_contract_snapshot() -> dict[str, Any]:
    registry = CoreToolRegistry()
    spec = CoreToolSpec(
        name="agent.platform_contract.echo",
        title="Agent platform contract echo",
        description_for_model="Deterministic read-only probe for AgentCore platform dispatch.",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "contract_version": {"type": "string"},
                "echo": {"type": "string"},
                "project_key": {"type": ["string", "null"]},
            },
            "required": ["contract_version", "echo", "project_key"],
            "additionalProperties": False,
        },
        source="project",
        risk="read_only",
        permission="allow",
        concurrency="serial",
        project_service_id="agent.platform_contract.echo",
        metadata={"contract_version": "agent.platform_contract.echo.v1"},
    )

    def handler(tool_call, tool_spec, request, emit):  # noqa: ANN001, ANN202
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary="AgentCore platform contract probe completed.",
            structured_content={
                "contract_version": "agent.platform_contract.echo.result.v1",
                "echo": str(tool_call.arguments.get("query") or ""),
                "project_key": request.project_key,
            },
        )

    registry.register(spec, handler)
    tool_call = CoreToolCall(
        tool_name="agent.platform_contract.echo",
        arguments={"query": "agent-core-platform-contract"},
        call_id="call-agent-core-platform-contract",
        reason="deterministic platform contract probe",
    )
    provider = FakeCoreProvider(
        [
            CoreModelStep.tools(tool_call, model_path="fake_core_provider"),
            CoreModelStep.final("AgentCore platform contract dispatched.", model_path="fake_core_provider"),
        ]
    )
    request = AgentCoreRequest(
        message="Run the AgentCore platform contract probe.",
        session_id="agent-core-platform-contract-session",
        project_key="demo_proj",
        turn_id="turn-agent-core-platform-contract",
        context={
            "trace_id": "trace-agent-core-platform-contract",
            "request_id": "req-agent-core-platform-contract",
            "actor_id": "wave9-worker-7",
            "agent_role": "orchestration_runtime",
            "requested_permissions": ["llm.invoke", "project.read"],
            "default_provider": "fake",
            "default_model": "fake-core-provider",
        },
    )
    result = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs()).run(request)
    return build_agent_core_platform_contract(request=request, registry=registry, result=result)


def validate_contract_snapshot(snapshot: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    _expect(snapshot.get("contract_version") == "agent_core.platform_contract.v1", errors, "unexpected platform contract version")
    _expect(snapshot.get("consumer") == "agent_core.tool_dispatch", errors, "unexpected consumer")
    _expect(snapshot.get("consumer_boundary", {}).get("routing_owner") == "agent_core.runtime_dispatcher", errors, "routing owner drift")
    _expect(snapshot.get("consumer_boundary", {}).get("capability") == "agent_tool_dispatch", errors, "capability drift")
    _expect(snapshot.get("agent_permission_boundary", {}).get("allowed") is True, errors, "agent permission boundary not allowed")

    inventory = snapshot.get("tool_schema_inventory") or {}
    _expect(inventory.get("contract_version") == "agent_core.tool_schema_inventory.v1", errors, "schema inventory version drift")
    _expect(inventory.get("tool_count") == 1, errors, "schema inventory tool count drift")
    tools = inventory.get("tools") or []
    first_tool = tools[0] if tools and isinstance(tools[0], dict) else {}
    _expect(first_tool.get("name") == "agent.platform_contract.echo", errors, "contract probe tool missing from inventory")
    _expect(first_tool.get("input_schema", {}).get("additionalProperties") is False, errors, "input schema is not closed")

    runtime = snapshot.get("runtime_dispatch") or {}
    _expect(runtime.get("contract_version") == "agent_core.runtime_dispatch.v1", errors, "runtime dispatch version drift")
    _expect(runtime.get("stop_reason") == "final_answer", errors, "runtime did not reach final_answer")
    event_types = [item.get("event_type") for item in runtime.get("tool_event_sequence") or [] if isinstance(item, dict)]
    _expect(
        event_types == ["tool_call_requested", "tool_call_started", "tool_result"],
        errors,
        f"unexpected tool event sequence: {event_types}",
    )
    tool_results = runtime.get("tool_results") or []
    first_result = tool_results[0] if tool_results and isinstance(tool_results[0], dict) else {}
    _expect(first_result.get("status") == "completed", errors, "tool result was not completed")
    _expect(
        first_result.get("structured_content", {}).get("contract_version") == "agent.platform_contract.echo.result.v1",
        errors,
        "tool result evidence contract missing",
    )

    evidence = snapshot.get("evidence_envelope") or {}
    trace_audit = evidence.get("trace_audit") or {}
    _expect(evidence.get("contract_version") == "agent_core.platform_evidence.v1", errors, "evidence envelope version drift")
    _expect(trace_audit.get("trace_id") == "trace-agent-core-platform-contract", errors, "trace_id not preserved")
    _expect(trace_audit.get("status") == "ok", errors, "trace audit did not finish ok")
    _expect(trace_audit.get("capability") == "agent_tool_dispatch", errors, "trace audit capability drift")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the deterministic AgentCore platform contract.")
    parser.add_argument("--json", action="store_true", help="Print the full contract snapshot as JSON.")
    parser.add_argument("--write-report", type=Path, help="Write the full contract snapshot to a JSON file.")
    args = parser.parse_args()

    snapshot = build_contract_snapshot()
    errors = validate_contract_snapshot(snapshot)
    if args.write_report:
        args.write_report.parent.mkdir(parents=True, exist_ok=True)
        args.write_report.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps({"status": "failed" if errors else "ok", "errors": errors, "contract": snapshot}, ensure_ascii=False, indent=2, sort_keys=True))
    elif errors:
        print(json.dumps({"status": "failed", "errors": errors}, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "OK agent_core_platform_contract=passed "
            f"tools={snapshot['tool_schema_inventory']['tool_count']} "
            f"events={len(snapshot['runtime_dispatch']['tool_event_sequence'])} "
            f"trace_id={snapshot['evidence_envelope']['trace_audit']['trace_id']}"
        )
    return 1 if errors else 0


def _expect(condition: bool, errors: list[str], message: str) -> None:
    if not condition:
        errors.append(message)


if __name__ == "__main__":
    raise SystemExit(main())
