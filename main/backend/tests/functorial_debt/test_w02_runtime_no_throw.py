"""W02 runtime failure-family and no-throw witnesses."""

from __future__ import annotations

from pathlib import Path

from functorial_kit import Failure
from functorial_kit.arch.gates import scan_project

from app.services.agent_runtime.external_tool_status import (
    get_external_service_status,
    mark_mcp_tool_mounted,
    register_external_service_state,
)
from app.services.agent_runtime.failures import runtime_failure
from app.services.agent_runtime.task_bus import assert_no_write_conflict


ROOT = Path(__file__).resolve().parents[4]
OWNED_RUNTIME_FILES = {
    f"main/backend/app/services/agent_runtime/{name}"
    for name in ("failures.py", "external_tool_status.py", "task_bus.py")
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
