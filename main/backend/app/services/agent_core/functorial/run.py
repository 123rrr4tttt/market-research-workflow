"""Execute the program stored by the lightweight functorial projection.

This surface is ``PROJECTION_ONLY``. It routes ordered tool results but has no
production canonical-write, promotion, cutover, or authority-transfer authority.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, cast

from app.services.agent_core.contracts import (
    AgentCoreRequest,
    CoreToolCall,
    CoreToolResult,
)
from app.services.agent_core.project_tools import build_project_core_tool_registry
from app.services.agent_core.registry import CoreToolRegistry
from app.services.agent_sessions.service import AgentSessionService
from app.successor_runtime.language.sync import interpret_ordered_sync

from .registry import catalog as _fcatalog
from .contracts import FunctorialFailure, FunctorialFailureCode, failure

_logger = logging.getLogger(__name__)


def _resolve_session_id(service: AgentSessionService, project_key: str) -> str:
    try:
        sessions = cast(
            list[dict[str, Any]],
            service.store.list_sessions(limit=200) or [],
        )
        def matches_project(session: dict[str, Any]) -> bool:
            return str(session.get("project_key") or "") == project_key

        actives = [
            s
            for s in sessions
            if matches_project(s)
            and str(s.get("status") or "") in ("active", "pending")
        ]
        if actives:
            return str(actives[0].get("session_id") or "")
        for s in sessions:
            if matches_project(s):
                return str(s.get("session_id") or "")
    except Exception as exc:  # noqa: BLE001
        _logger.debug("failed to list sessions for project %s: %s", project_key, exc)
    return f"run-{uuid.uuid4().hex[:16]}"


def _program_operators(workflow: dict[str, Any]) -> tuple[str, ...]:
    program_value = workflow.get("program")
    if not isinstance(program_value, dict):
        raise ValueError("workflow program has no ordered nodes")
    program = cast(dict[str, Any], program_value)
    nodes_value = program.get("nodes")
    if not isinstance(nodes_value, list):
        # kit:boundary — reject malformed persisted program before execution.
        raise ValueError("workflow program has no ordered nodes")
    nodes = cast(list[Any], nodes_value)

    operators: list[str] = []
    for node_value in nodes:
        if not isinstance(node_value, dict):
            # kit:boundary — persisted programs are operator-only after build.
            raise ValueError("workflow program contains a non-operator node")
        node = cast(dict[str, Any], node_value)
        if node.get("kind") != "operator":
            # kit:boundary — persisted programs are operator-only after build.
            raise ValueError("workflow program contains a non-operator node")
        ref = str(node.get("ref") or "")
        operator_id = ref.split(":", 1)[1] if ":" in ref else ref
        if not operator_id:
            # kit:boundary — reject malformed persisted program before execution.
            raise ValueError("workflow program contains an empty operator ref")
        operators.append(operator_id)
    return tuple(operators)


def _step_record(result: CoreToolResult) -> dict[str, Any]:
    return {
        "ok": result.status == "completed",
        "status": result.status,
        "tool": result.tool_name,
        "summary": result.model_summary or "",
        "data": dict(result.structured_content or {}),
        "error": dict(result.error or {}) if result.error else None,
        "retry_hint": result.retry_hint,
    }


def _terminal_failure(status: str) -> FunctorialFailureCode:
    if status == "failed":
        return "OPERATOR_FAILED"
    if status == "canceled":
        return "OPERATOR_CANCELED"
    if status == "needs_approval":
        return "OPERATOR_NEEDS_APPROVAL"
    return "OPERATOR_DEFERRED"


def _execute_operator(
    operator_id: str,
    arguments: dict[str, Any],
    *,
    registry: CoreToolRegistry,
    request: AgentCoreRequest,
) -> CoreToolResult:
    spec = registry.get(operator_id)
    if spec is None:
        return CoreToolResult(
            call_id=f"run-{uuid.uuid4().hex[:16]}",
            tool_name=operator_id,
            status="failed",
            model_summary=f"operator not registered: {operator_id}",
            error={
                "code": "OPERATOR_NOT_REGISTERED",
                "message": f"operator not registered: {operator_id}",
            },
        )
    call = CoreToolCall(
        call_id=f"run-{uuid.uuid4().hex[:16]}",
        tool_name=operator_id,
        arguments=dict(arguments),
        reason="functorial-workflow",
    )
    return registry.execute_tool(
        tool_call=call,
        tool_spec=spec,
        request=request,
        emit=lambda _event: None,
    )


def run_workflow(
    workflow_id: str, inputs: dict[str, Any] | None, project_key: str
) -> dict[str, Any]:
    wf = _fcatalog.get("workflows", workflow_id)
    if not wf:
        not_found = failure(
            "WORKFLOW_NOT_FOUND",
            f"workflow not found: {workflow_id}",
            context={"workflow_id": workflow_id},
        )
        return {
            "workflow_id": workflow_id,
            "executed": False,
            "status": "failed",
            "failure": {
                "code": not_found.code,
                "message": not_found.message,
                "context": not_found.context,
            },
            "authority": "PROJECTION_ONLY",
            "steps": [],
        }
    try:
        operators = _program_operators(wf)
    except ValueError as exc:
        terminal = failure(
            "OPERATOR_NOT_REGISTERED",
            str(exc),
            context={"workflow_id": workflow_id},
        )
        return {
            "workflow_id": workflow_id,
            "executed": False,
            "status": "failed",
            "failure": {
                "code": terminal.code,
                "message": terminal.message,
                "context": terminal.context,
            },
            "authority": "PROJECTION_ONLY",
            "steps": [],
        }
    service = AgentSessionService()
    registry = build_project_core_tool_registry(service=service)
    session_id = _resolve_session_id(service, project_key)
    request = AgentCoreRequest(
        message="",
        session_id=session_id,
        project_key=project_key,
        turn_id=f"turn-{uuid.uuid4().hex[:16]}",
    )
    typed_results = interpret_ordered_sync(
        operators,
        initial_value=dict(inputs or {}),
        invoke=lambda operator_id, arguments: _execute_operator(
            operator_id,
            arguments,
            registry=registry,
            request=request,
        ),
        continue_after=lambda result: result.status == "completed",
        output_value=lambda result: dict(result.structured_content or {}),
    )
    results = [_step_record(result) for result in typed_results]
    terminal_result = typed_results[-1] if typed_results else None
    if terminal_result is None or terminal_result.status == "completed":
        workflow_status = "completed"
        terminal_failure: FunctorialFailure | None = None
    else:
        workflow_status = (
            "blocked"
            if terminal_result.status in {"needs_approval", "deferred"}
            else "failed"
        )
        result_error = dict(terminal_result.error or {})
        failure_code: FunctorialFailureCode = (
            "OPERATOR_NOT_REGISTERED"
            if result_error.get("code") == "OPERATOR_NOT_REGISTERED"
            else _terminal_failure(terminal_result.status)
        )
        terminal_failure = failure(
            failure_code,
            (
                f"operator {terminal_result.tool_name} ended with status "
                f"{terminal_result.status}"
            ),
            context={
                "operator": terminal_result.tool_name,
                "status": terminal_result.status,
            },
        )
    return {
        "workflow_id": workflow_id,
        "executed": workflow_status == "completed",
        "project_key": project_key,
        "status": workflow_status,
        "failure": terminal_failure
        and {
            "code": terminal_failure.code,
            "message": terminal_failure.message,
            "context": terminal_failure.context,
        },
        "authority": "PROJECTION_ONLY",
        "steps": results,
    }
