"""Execute the program stored by the lightweight functorial projection.

This surface is ``PROJECTION_ONLY``. It routes ordered tool results but has no
production canonical-write, promotion, cutover, or authority-transfer authority.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.services.agent_core.contracts import (
    AgentCoreRequest,
    CoreToolCall,
    CoreToolResult,
)
from app.services.agent_core.project_tools import build_project_core_tool_registry
from app.services.agent_sessions.service import AgentSessionService

from .registry import catalog as _fcatalog
from .contracts import FunctorialFailureCode, failure

_logger = logging.getLogger(__name__)


def _resolve_session_id(service: AgentSessionService, project_key: str) -> str:
    try:
        sessions = service.store.list_sessions(limit=200) or []
        ok = lambda s: str(s.get("project_key") or "") == project_key
        actives = [
            s
            for s in sessions
            if ok(s) and str(s.get("status") or "") in ("active", "pending")
        ]
        if actives:
            return str(actives[0].get("session_id") or "")
        for s in sessions:
            if ok(s):
                return str(s.get("session_id") or "")
    except Exception as exc:  # noqa: BLE001
        _logger.debug("failed to list sessions for project %s: %s", project_key, exc)
    return f"run-{uuid.uuid4().hex[:16]}"


def _program_operators(workflow: dict[str, Any]) -> tuple[str, ...]:
    program = workflow.get("program") if isinstance(workflow, dict) else None
    nodes = program.get("nodes") if isinstance(program, dict) else None
    if not isinstance(nodes, list):
        # kit:boundary — reject malformed persisted program before execution.
        raise ValueError("workflow program has no ordered nodes")

    operators: list[str] = []
    for node in nodes:
        if not isinstance(node, dict) or node.get("kind") != "operator":
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
    results: list[dict[str, Any]] = []
    current_arguments = dict(inputs or {})
    workflow_status = "completed"
    terminal_failure: FunctorialFailure | None = None
    for op in operators:
        spec = registry.get(op)
        if spec is None:
            terminal_failure = failure(
                "OPERATOR_NOT_REGISTERED",
                f"operator not registered: {op}",
                context={"operator": op},
            )
            results.append(
                {
                    "ok": False,
                    "status": "not_registered",
                    "tool": op,
                    "summary": "",
                    "data": {},
                    "error": {
                        "code": terminal_failure.code,
                        "message": terminal_failure.message,
                    },
                    "retry_hint": None,
                }
            )
            workflow_status = "failed"
            break
        call = CoreToolCall(
            call_id=f"run-{uuid.uuid4().hex[:16]}",
            tool_name=op,
            arguments=dict(current_arguments),
            reason="functorial-workflow",
        )
        request = AgentCoreRequest(
            message="",
            session_id=session_id,
            project_key=project_key,
            turn_id=f"turn-{uuid.uuid4().hex[:16]}",
        )
        result = registry.execute_tool(
            tool_call=call, tool_spec=spec, request=request, emit=lambda _e: None
        )
        results.append(_step_record(result))
        current_arguments = dict(result.structured_content or {})
        if result.status != "completed":
            workflow_status = "blocked" if result.status in {
                "needs_approval", "deferred"
            } else "failed"
            terminal_failure = failure(
                _terminal_failure(result.status),
                f"operator {op} ended with status {result.status}",
                context={"operator": op, "status": result.status},
            )
            break
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
