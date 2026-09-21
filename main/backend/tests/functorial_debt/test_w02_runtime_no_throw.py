"""W02 runtime failure-family and no-throw witnesses."""

from __future__ import annotations

from pathlib import Path

from functorial_kit import Failure
from functorial_kit.arch.gates import scan_project

from app.services.agent_runtime.conversation import ModelConversationAnswerer
from app.services.agent_runtime.external_tool_status import (
    get_external_service_status,
    mark_mcp_tool_mounted,
    register_external_service_state,
)
from app.services.agent_runtime.interactive_agent import InteractiveAgentRuntime
from app.services.agent_runtime.task_bus import assert_no_write_conflict


ROOT = Path(__file__).resolve().parents[4]
OWNED_RUNTIME_FILES = {
    f"main/backend/app/services/agent_runtime/{name}"
    for name in ("conversation.py", "external_tool_status.py", "interactive_agent.py", "task_bus.py")
}


def _failure_code(value: object) -> str:
    assert isinstance(value, Failure)
    assert value.family == "agent.runtime.failure"
    return value.code


def test_w02_runtime_owned_files_have_no_core_throws() -> None:
    scan = scan_project(ROOT)
    assert [
        violation
        for violation in scan.violations
        if violation.file in OWNED_RUNTIME_FILES
        and violation.gate == "no-throw-in-core"
        and violation.severity == "fail"
    ] == []


def test_w02_runtime_input_failures_are_closed_and_typed() -> None:
    empty_model = ModelConversationAnswerer(
        chat_model=type("EmptyModel", (), {"invoke": lambda _self, _prompt: {"content": ""}})()
    )
    assert _failure_code(
        empty_model.answer(message="hello", project_key=None, context_summary={}, turn_decision={})
    ) == "conversation_empty_answer"
    assert _failure_code(register_external_service_state(service_id="")) == "capability_input_missing"
    assert _failure_code(mark_mcp_tool_mounted(service_id="svc", tool_name="")) == "capability_input_missing"
    assert _failure_code(get_external_service_status(None)) == "capability_input_missing"
    assert _failure_code(
        assert_no_write_conflict(
            [{"task_id": "other", "status": "claimed", "write_set": ["shared"]}],
            "current",
            ["shared"],
        )
    ) == "write_set_conflict"
    runtime = object.__new__(InteractiveAgentRuntime)
    assert _failure_code(
        runtime.run_turn(
            message=" ",
            project_key="project",
            batch_loop_runner=lambda **_: {},
            parser_fallback=lambda command: {"command": command},
            submitter=lambda *_: {},
            executor_snapshot=lambda: {},
        )
    ) == "message_required"


def test_w02_runtime_approved_capability_input_failures_are_typed() -> None:
    runtime = object.__new__(InteractiveAgentRuntime)
    common = {
        "approval": {},
        "binding_payload": {},
        "turn_id": "turn-1",
        "session_id": "session-1",
        "task_id": "task-1",
        "project_key": "project",
    }
    assert _failure_code(
        runtime._execute_approved_high_risk_capability(
            **common, capability_id="workflow_graph.run", command="run workflow"
        )
    ) == "capability_input_missing"
    assert _failure_code(
        runtime._execute_approved_high_risk_capability(
            **common, capability_id="ingest.source_library.run", command="ingest"
        )
    ) == "capability_input_missing"
    assert _failure_code(
        runtime._execute_approved_high_risk_capability(
            **common, capability_id="agent_batch.nl_command.submit", command=""
        )
    ) == "capability_input_missing"
