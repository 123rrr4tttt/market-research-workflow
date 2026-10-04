"""Shared request scope, result and cancellation helpers for project tools.

These functions retain the original service/contract authority. They neither
register tools nor create a second session or permission state.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from functorial_kit import Failure
from app.services.agent_sessions.service import AgentSessionService
from .contracts import AgentCoreRequest, CoreEvent, CoreToolCall, CoreToolResult



def _resolve_project_key(tool_call: CoreToolCall, request: AgentCoreRequest) -> str:
    return str(tool_call.arguments.get("project_key") or request.project_key or "").strip()



def _missing_project_result(tool_call: CoreToolCall) -> CoreToolResult:
    return CoreToolResult(
        call_id=tool_call.call_id,
        tool_name=tool_call.tool_name,
        status="failed",
        model_summary="project_key is required for this project tool.",
        error={"code": "missing_project_key", "message": "project_key is required"},
    )



def _runtime_failure_result(tool_call: CoreToolCall, failure: Failure) -> CoreToolResult:
    """Project-tool error projection for the closed agent runtime family."""

    legacy_code = "invalid_writing_operation" if failure.code.startswith("writing_") else failure.code
    failure_payload = {
        "family": failure.family,
        "code": failure.code,
        "message": failure.message,
        "context": dict(failure.context or {}),
    }
    return CoreToolResult(
        call_id=tool_call.call_id,
        tool_name=tool_call.tool_name,
        status="failed",
        model_summary=failure.message,
        error={
            "code": legacy_code,
            "message": failure.message,
            "failure_family": failure.family,
            "failure_code": failure.code,
            "failure": failure_payload,
        },
    )



def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]



def _safe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed > 0 else None



def _safe_nonnegative_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed >= 0 else None



def _normalize_string_list(values: Any) -> list[str]:
    if isinstance(values, str):
        values = [values]
    out: list[str] = []
    for value in values or []:
        item = str(value or "").strip()
        if item and item not in out:
            out.append(item)
    return out



def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()



def _session_abort_requested(*, service: AgentSessionService, session_id: str) -> bool:
    try:
        session = service.get_session(session_id)
    except Exception:  # noqa: BLE001
        return False
    return str(session.get("status") or "").strip().lower() == "canceled"



def _abort_requested_result(
    *,
    service: AgentSessionService,
    request: AgentCoreRequest,
    tool_call: CoreToolCall,
    emit: Callable[[CoreEvent], None],
    skipped_items: list[str] | tuple[str, ...] = (),
    dispatched_count: int = 0,
    structured_content: dict[str, Any] | None = None,
) -> CoreToolResult:
    skipped = [str(item) for item in skipped_items if str(item).strip()]
    payload = {
        "contract_version": "agent_core.cooperative_abort.v1",
        "tool_name": tool_call.tool_name,
        "status": "abort_requested",
        "dispatched_count": int(dispatched_count),
        "skipped_items": skipped,
    }
    emit(
        CoreEvent(
            event_type="tool_progress",
            session_id=request.session_id,
            turn_id=request.turn_id,
            call_id=tool_call.call_id,
            payload=payload,
        )
    )
    content = {
        **(structured_content or {}),
        "abort_requested": True,
        "session_status": str((service.get_session(request.session_id) or {}).get("status") or ""),
        "skipped_items": skipped,
        "dispatched_count": int(dispatched_count),
    }
    return CoreToolResult(
        call_id=tool_call.call_id,
        tool_name=tool_call.tool_name,
        status="canceled",
        model_summary=f"Tool {tool_call.tool_name} did not continue because the session was canceled.",
        ui_summary=f"{tool_call.tool_name} stopped after session cancellation.",
        structured_content=content,
        error={"code": "session_canceled", "message": "session is canceled"},
        retry_hint="Use task.continue or task.retry after confirming the session should resume.",
    )



def _compact_session(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": session.get("session_id"),
        "project_key": session.get("project_key"),
        "entrypoint_type": session.get("entrypoint_type"),
        "goal": session.get("goal"),
        "status": session.get("status"),
        "current_phase": session.get("current_phase"),
        "root_task_id": session.get("root_task_id"),
        "task_count": session.get("task_count"),
    }



def _compact_skill_meta(skill: dict[str, Any]) -> dict[str, Any]:
    manifest = dict(skill.get("agent_batch_task_manifest") or {})
    return {
        "skill_id": str(skill.get("skill_id") or "").strip(),
        "owner": skill.get("owner"),
        "execution_profile": skill.get("execution_profile") or "default",
        "concurrency_class": skill.get("concurrency_class") or "read_only",
        "required_permissions": list(skill.get("required_permissions") or []),
        "allowed_actor_roles": list(skill.get("allowed_actor_roles") or []),
        "approval_policy": dict(skill.get("approval_policy") or {}),
        "agent_batch_task_manifest": _compact_json_value(manifest, max_items=20, max_depth=4) if manifest else {},
    }


def _compact_json_value(value: Any, *, max_items: int = 30, max_depth: int = 5, max_string: int = 500) -> Any:
    if max_depth <= 0:
        if isinstance(value, (dict, list, tuple)):
            return "[truncated]"
        return value
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= max_items:
                out["_truncated"] = True
                out["_omitted_count"] = max(0, len(value) - max_items)
                break
            out[str(key)] = _compact_json_value(item, max_items=max_items, max_depth=max_depth - 1, max_string=max_string)
        return out
    if isinstance(value, (list, tuple)):
        items = list(value)
        out = [_compact_json_value(item, max_items=max_items, max_depth=max_depth - 1, max_string=max_string) for item in items[:max_items]]
        if len(items) > max_items:
            out.append({"_truncated": True, "_omitted_count": len(items) - max_items})
        return out
    if isinstance(value, str) and len(value) > max_string:
        return f"{value[:max_string]}..."
    return value


def _permission_from_approval(approval_level: str) -> str:
    value = str(approval_level or "none").strip().lower()
    if value == "none":
        return "allow"
    if value == "explicit_user_request":
        return "explicit_user_request"
    return "ask"


def _risk_from_metadata(
    *,
    approval_level: str,
    concurrency_class: str,
    risks: list[Any],
) -> str:
    approval = str(approval_level or "none").strip().lower()
    concurrency = str(concurrency_class or "read_only").strip().lower()
    risk_text = " ".join(str(item or "").lower() for item in risks)
    if approval == "none" and concurrency == "read_only":
        return "read_only"
    if "privileged" in risk_text:
        return "privileged"
    if concurrency == "write_external" or "external" in risk_text or "network" in risk_text:
        return "write_external"
    return "write_shared"


def _concurrency_from_class(concurrency_class: str) -> str:
    value = str(concurrency_class or "read_only").strip().lower()
    if value == "read_only":
        return "parallel"
    if value == "write_shared":
        return "serial"
    return "exclusive"
