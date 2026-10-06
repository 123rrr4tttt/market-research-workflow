"""Shared request scope, result and cancellation helpers for project tools.

These functions retain the original service/contract authority. They neither
register tools nor create a second session or permission state.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
from typing import Protocol, TypeGuard, runtime_checkable

from functorial_kit import Failure
from app.services.agent_sessions.service import AgentSessionService
from .contracts import (
    AgentCoreRequest,
    compact_json_value,
    CoreEvent,
    CoreToolCall,
    CoreToolResult,
    JSONObject,
    JSONValue,
    json_list,
    json_object,
    json_strings,
    ToolConcurrency,
    ToolPermission,
    ToolRisk,
    ToolStatus,
)


SourceLibraryLister = Callable[[str | None], Sequence[Mapping[str, object]]]


class StructuredDataSearcher(Protocol):
    def __call__(
        self,
        *,
        project_key: str | None,
        query: str | None = None,
        limit: int = 12,
        datasets: list[str] | tuple[str, ...] | None = None,
    ) -> Mapping[str, JSONValue]: ...


@runtime_checkable
class AgentArtifactStore(Protocol):
    def upsert_artifact(self, payload: Mapping[str, object]) -> object: ...

    def append_event(
        self,
        session_id: str,
        *,
        event_type: str,
        task_id: str | None = None,
        payload: Mapping[str, object] | None = None,
    ) -> object: ...


def agent_artifact_store(value: object) -> AgentArtifactStore | None:
    """Narrow the dynamic session-store boundary once for tool handlers."""

    return value if isinstance(value, AgentArtifactStore) else None


def _text(value: object) -> str:
    return str(value or "").strip()


def _is_json_sequence(value: object) -> TypeGuard[Sequence[object]]:
    return isinstance(value, (list, tuple))


def resolve_project_key(tool_call: CoreToolCall, request: AgentCoreRequest) -> str:
    project_key: object = tool_call.arguments.get("project_key")
    return _text(project_key if project_key is not None else request.project_key)


def missing_project_result(tool_call: CoreToolCall) -> CoreToolResult:
    return CoreToolResult(
        call_id=tool_call.call_id,
        tool_name=tool_call.tool_name,
        status="failed",
        model_summary="project_key is required for this project tool.",
        error={"code": "missing_project_key", "message": "project_key is required"},
    )


def runtime_failure_result(tool_call: CoreToolCall, failure: Failure) -> CoreToolResult:
    """Project-tool error projection for the closed agent runtime family."""

    legacy_code = "invalid_writing_operation" if failure.code.startswith("writing_") else failure.code
    failure_payload: JSONObject = {
        "family": failure.family,
        "code": failure.code,
        "message": failure.message,
        "context": compact_json_value(failure.context),
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


def stable_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def safe_int(value: object) -> int | None:
    if not isinstance(value, (str, int, float)) or value == "":
        return None
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed > 0 else None


def safe_nonnegative_int(value: object) -> int | None:
    if not isinstance(value, (str, int, float)) or value == "":
        return None
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed >= 0 else None


def normalize_string_list(values: object) -> list[str]:
    if isinstance(values, str):
        values = [values]
    out: list[str] = []
    candidates: Sequence[object]
    if _is_json_sequence(values):
        candidates = values
    else:
        candidates = ()
    for value in candidates:
        item = _text(value)
        if item and item not in out:
            out.append(item)
    return out


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def session_abort_requested(*, service: AgentSessionService, session_id: str) -> bool:
    try:
        session = service.get_session(session_id)
    except Exception:  # noqa: BLE001
        return False
    if isinstance(session, Failure):
        return False
    status: object = session.get("status")
    return _text(status).lower() == "canceled"


def abort_requested_result(
    *,
    service: AgentSessionService,
    request: AgentCoreRequest,
    tool_call: CoreToolCall,
    emit: Callable[[CoreEvent], None],
    skipped_items: Sequence[str] = (),
    dispatched_count: int = 0,
    structured_content: JSONObject | None = None,
) -> CoreToolResult:
    skipped: list[JSONValue] = [_text(item) for item in skipped_items if _text(item)]
    payload: JSONObject = {
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
    session = service.get_session(request.session_id)
    session_status = "" if isinstance(session, Failure) else _text(session.get("status"))
    content: JSONObject = {
        **(structured_content or {}),
        "abort_requested": True,
        "session_status": session_status,
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
        retry_hint="Read task.summary first; use task.retry only when the user wants the task to run again.",
    )


def compact_session(session: Mapping[str, object]) -> JSONObject:
    return {
        "session_id": compact_json_value(session.get("session_id")),
        "project_key": compact_json_value(session.get("project_key")),
        "entrypoint_type": compact_json_value(session.get("entrypoint_type")),
        "goal": compact_json_value(session.get("goal")),
        "status": compact_json_value(session.get("status")),
        "current_phase": compact_json_value(session.get("current_phase")),
        "root_task_id": compact_json_value(session.get("root_task_id")),
        "task_count": compact_json_value(session.get("task_count")),
    }


def compact_skill_meta(skill: Mapping[str, object]) -> JSONObject:
    manifest_value = compact_json_value(skill.get("agent_batch_task_manifest"), max_items=20, max_depth=4)
    manifest = manifest_value if isinstance(manifest_value, dict) else {}
    return {
        "skill_id": _text(skill.get("skill_id")),
        "owner": compact_json_value(skill.get("owner")),
        "execution_profile": compact_json_value(skill.get("execution_profile")) or "default",
        "concurrency_class": compact_json_value(skill.get("concurrency_class")) or "read_only",
        "required_permissions": compact_json_value(skill.get("required_permissions"), max_items=50),
        "allowed_actor_roles": compact_json_value(skill.get("allowed_actor_roles"), max_items=50),
        "approval_policy": compact_json_value(skill.get("approval_policy"), max_items=20, max_depth=4),
        "agent_batch_task_manifest": manifest,
    }


def permission_from_approval(approval_level: str) -> ToolPermission:
    value = str(approval_level or "none").strip().lower()
    if value == "none":
        return "allow"
    if value == "explicit_user_request":
        return "explicit_user_request"
    return "ask"


def risk_from_metadata(
    *,
    approval_level: str,
    concurrency_class: str,
    risks: Sequence[object],
) -> ToolRisk:
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


def concurrency_from_class(concurrency_class: str) -> ToolConcurrency:
    value = str(concurrency_class or "read_only").strip().lower()
    if value == "read_only":
        return "parallel"
    if value == "write_shared":
        return "serial"
    return "exclusive"


def core_status(status: object) -> ToolStatus:
    normalized = str(status or "").strip().lower()
    if normalized in {"completed", "success", "ok", "delegated"}:
        return "completed"
    if normalized in {"canceled", "cancelled"}:
        return "canceled"
    if normalized in {"needs_approval", "approval_waiting"}:
        return "needs_approval"
    if normalized in {"skipped", "deferred"}:
        return "deferred"
    return "failed"


# Compatibility aliases for already-loaded backend workers. New code imports the public names.
_abort_requested_result = abort_requested_result
_compact_json_value = compact_json_value
_compact_session = compact_session
_compact_skill_meta = compact_skill_meta
_concurrency_from_class = concurrency_from_class
_missing_project_result = missing_project_result
_normalize_string_list = normalize_string_list
_permission_from_approval = permission_from_approval
_resolve_project_key = resolve_project_key
_risk_from_metadata = risk_from_metadata
_runtime_failure_result = runtime_failure_result
_safe_int = safe_int
_safe_nonnegative_int = safe_nonnegative_int
_session_abort_requested = session_abort_requested
_stable_hash = stable_hash
_utcnow_iso = utcnow_iso


__all__ = [
    "AgentArtifactStore",
    "JSONValue",
    "JSONObject",
    "abort_requested_result",
    "compact_json_value",
    "compact_session",
    "compact_skill_meta",
    "concurrency_from_class",
    "json_list",
    "json_object",
    "json_strings",
    "missing_project_result",
    "normalize_string_list",
    "permission_from_approval",
    "resolve_project_key",
    "risk_from_metadata",
    "runtime_failure_result",
    "safe_int",
    "safe_nonnegative_int",
    "session_abort_requested",
    "stable_hash",
    "utcnow_iso",
]
