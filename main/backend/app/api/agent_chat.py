from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from ..contracts import ApiEnvelope, ErrorCode, error_response
from ..contracts.errors import map_exception_to_error
from ..contracts.responses import ok
from ..models.base import SessionLocal
from ..models.entities import Project
from ..services.agent_runtime.tool_pool import AgentToolPoolAssembler, ToolPoolRequest
from ..services.agent_sessions.service import get_agent_session_service
from ..services.projects import bind_schema
from ..settings.config import settings
from .agent_batch import _resolve_project_key

router = APIRouter(prefix="/agent-chat", tags=["agent_chat"])
AgentChatEnvelope = ApiEnvelope[dict[str, Any]]


class AgentChatTurnRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    message: str = Field(..., min_length=1, max_length=8000)
    project_key: str | None = Field(default=None, max_length=128)
    session_id: str | None = Field(default=None, max_length=64)
    idempotency_key: str | None = Field(default=None, max_length=128)
    runtime_variant: str | None = Field(default=None, max_length=32)


class AgentChatApprovalContinueRequest(BaseModel):
    approved_by: str = Field(default="user", min_length=1, max_length=128)
    binding_payload_overrides: dict[str, Any] = Field(default_factory=dict)


_RESERVED_AGENT_PROJECT_KEYS = {"", "default", "public"}
_RETIRED_AGENT_CONTROL_OPTIONS = (
    "dry_run",
    "enable_bounded_retry",
    "enable_limited_branching",
    "enable_model_tool_loop",
    "require_high_risk_approval",
)


def _lookup_active_agent_project_key() -> str | None:
    """Resolve the user-facing chat project to the active tenant when the UI sends a reserved default key."""

    try:
        with bind_schema("public"), SessionLocal() as session:
            row = (
                session.execute(
                    select(Project)
                    .where(Project.enabled.is_(True), Project.is_active.is_(True))
                    .order_by(Project.id.asc())
                )
                .scalars()
                .first()
            )
            if row and str(row.project_key or "").strip():
                return str(row.project_key).strip()
            row = (
                session.execute(
                    select(Project)
                    .where(Project.enabled.is_(True))
                    .order_by(Project.id.asc())
                )
                .scalars()
                .first()
            )
            if row and str(row.project_key or "").strip():
                return str(row.project_key).strip()
    except SQLAlchemyError:
        return None
    return None


def _resolve_agent_chat_project_key(project_key: str | None) -> str | None:
    raw = str(project_key or "").strip()
    if raw.lower() not in _RESERVED_AGENT_PROJECT_KEYS:
        return _resolve_project_key(raw)
    active = _lookup_active_agent_project_key()
    if active:
        return active
    return _resolve_project_key(None)


def _agent_chat_requires_explicit_project_key(payload: AgentChatTurnRequest) -> bool:
    raw = str(payload.project_key or "").strip().lower()
    return not payload.session_id and raw in _RESERVED_AGENT_PROJECT_KEYS


def _raise_invalid_input(message: str) -> None:
    raise HTTPException(
        status_code=400,
        detail=error_response(
            ErrorCode.INVALID_INPUT,
            message,
        ),
    )


def _unsupported_agent_control_options(payload: AgentChatTurnRequest) -> list[str]:
    return [
        option
        for option in _RETIRED_AGENT_CONTROL_OPTIONS
        if option in (payload.model_extra or {})
    ]


def _reject_retired_agent_control_options(payload: AgentChatTurnRequest) -> None:
    options = _unsupported_agent_control_options(payload)
    if not options:
        return
    detail = error_response(
        ErrorCode.INVALID_INPUT,
        "unsupported agent chat option(s): "
        + ", ".join(options)
        + "; remove the retired control option(s) and retry",
        details={"options": options},
    )
    detail["error"]["code"] = "unsupported_agent_chat_option"
    raise HTTPException(status_code=400, detail=detail)


def _raise_agent_runtime_retired(runtime_variant: str) -> None:
    detail = error_response(
        ErrorCode.INVALID_INPUT,
        f"agent runtime {runtime_variant} is retired; select an explicit native binding",
        details={"runtime_variant": runtime_variant},
    )
    detail["error"]["code"] = "agent_runtime_retired"
    raise HTTPException(
        status_code=410,
        detail=detail,
    )


def _raise_mapped_error(exc: Exception) -> None:
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, ValueError):
        _raise_invalid_input(str(exc) or "invalid agent chat request")
    code, message, details = map_exception_to_error(exc)
    status_code = (
        404
        if code == ErrorCode.NOT_FOUND
        else 429
        if code == ErrorCode.RATE_LIMITED
        else 502
        if code in {ErrorCode.UPSTREAM_ERROR, ErrorCode.PARSE_ERROR}
        else 500
    )
    raise HTTPException(
        status_code=status_code,
        detail=error_response(code, message, details=details),
    ) from exc


def _agent_runtime_feature_flags() -> dict[str, bool]:
    return {
        "agent_stream_enabled": bool(getattr(settings, "agent_stream_enabled", True)),
        "agent_batch_as_tool_enabled": bool(
            getattr(settings, "agent_batch_as_tool_enabled", True)
        ),
    }


def _resolve_runtime_variant(payload: AgentChatTurnRequest) -> str:
    requested = str(payload.runtime_variant or "").strip().lower()
    if not requested:
        raise ValueError(
            "runtime_variant is required; use agent_macro_native or agent_macro_rapid_native"
        )
    if requested in {
        "native",
        "native_agent",
        "native-agent",
        "agent_macro_native",
    }:
        return "agent_macro_native"
    if requested in {
        "rapid_native",
        "rapid-native",
        "agent_macro_rapid_native",
        "agent_rapid_native",
    }:
        return "agent_macro_rapid_native"
    if requested in {"core", "agent_core", "agent_core_v3", "v3"}:
        return "agent_core_v3"
    if requested in {"legacy", "legacy_batch", "agent_batch"}:
        return "legacy_batch"
    if requested in {"v2", "runtime_v2", "agent_runtime_v2"}:
        return "agent_runtime_v2"
    raise ValueError(f"unsupported runtime_variant: {requested}")


def _require_runtime_variant(payload: AgentChatTurnRequest) -> str:
    runtime_variant = _resolve_runtime_variant(payload)
    if runtime_variant in {"agent_core_v3", "agent_runtime_v2", "legacy_batch"}:
        _raise_agent_runtime_retired(runtime_variant)
    return runtime_variant


def _prepare_agent_core_session(
    payload: AgentChatTurnRequest,
    *,
    command: str,
    project_key: str | None,
    runtime_variant: str,
) -> tuple[Any, dict[str, Any], str, str | None]:
    service = get_agent_session_service()
    if payload.session_id:
        session = service.get_session(payload.session_id)
        project_key = _validate_agent_core_session_project(
            session=session, project_key=project_key
        )
        session_id = str(session["session_id"])
        service.create_message(
            session_id,
            role="user",
            actor="agent_core_user",
            content=command,
            metadata={"project_key": project_key, "runtime_variant": runtime_variant},
        )
    else:
        source = "user"
        bundle = service.create_session(
            source=source,
            entrypoint_type="agent_core",
            goal=command,
            project_key=project_key,
            initial_context={"message": command, "runtime_variant": runtime_variant},
            metadata={
                "agent_core": {"contract_version": "agent_core.turn.v1"},
                "runtime_variant": runtime_variant,
            },
            task_blueprints=[
                {
                    "subject": "Agent Core Turn",
                    "description": "Conversation-first agent-core turn with model-owned tool selection.",
                    "task_type": "agent_core_turn",
                    "phase": "conversation",
                    "execution_mode": "coordinator",
                    "priority": 1,
                    "write_set": [],
                    "read_set": ["project:context"],
                    "task_spec": {
                        "task_type": "agent_core_turn",
                        "goal": command,
                        "context": {
                            "runtime_variant": runtime_variant,
                            "project_key": project_key,
                        },
                        "target_scope": "session",
                        "write_set": [],
                        "completion_criteria": [
                            "Answer directly or call project tools selected by the model.",
                        ],
                        "verification_steps": [
                            "Persist core events and tool results for frontend replay.",
                        ],
                        "artifact_targets": [],
                    },
                    "metadata": {"agent_core": True, "mechanical_plan": False},
                }
            ],
        )
        session = dict(bundle["session"])
        session_id = str(session["session_id"])
    return service, session, session_id, project_key


def _native_macro_observation(invocation: Any, *, binding: Any) -> dict[str, Any]:
    """Project host observations without promoting an answer to delivery."""

    tool_calls: list[dict[str, Any]] = []
    for raw in invocation.tool_calls:
        namespace = str(raw.get("namespace") or "").strip()
        tool = str(raw.get("tool") or "").strip()
        tool_name = f"{namespace}.{tool}" if namespace else tool
        success = bool(raw.get("success"))
        tool_calls.append(
            {
                "thread_id": invocation.thread_id,
                "turn_id": invocation.turn_id,
                "call_id": str(raw.get("call_id") or ""),
                "tool_name": tool_name,
                "status": "completed" if success else "failed",
                "success": success,
                "result_status": "returned_to_native_turn",
            }
        )
    return {
        "outcome": "answered",
        "delivery_ready": False,
        "delivery_status": "not_observed",
        "thread_id": invocation.thread_id,
        "turn_id": invocation.turn_id,
        "tool_call_count": invocation.tool_call_count,
        "tool_calls": tool_calls,
        "tool_call_identity_status": "observed" if tool_calls else "not_applicable",
        "skill_mount_status": "observed",
        "mounted_skills": [
            {
                "name": skill.name,
                "path": skill.path,
                "content_digest": skill.content_digest,
            }
            for skill in binding.skills
        ],
    }


def _run_agent_macro_native_turn(
    payload: AgentChatTurnRequest, *, command: str, project_key: str | None
) -> dict[str, Any]:
    """Run the explicitly selected Codex native macro pilot without fallback."""

    if not project_key:
        raise ValueError("project_key is required for native Agent macro turns")
    if not bool(getattr(settings, "codex_cli_llm_persistent_enabled", True)):
        raise RuntimeError("native Agent macro requires the persistent Codex app-server core")

    from ..services.llm.codex_app_server import get_persistent_codex_core
    from ..services.llm.codex_cli import (
        _disabled_features,
        _resolve_codex_bin,
        _resolve_codex_workdir,
    )
    from ..services.llm.codex_macro_binding import build_agent_macro_pilot_binding

    service, session, session_id, project_key = _prepare_agent_core_session(
        payload,
        command=command,
        project_key=project_key,
        runtime_variant="agent_macro_native",
    )
    binding = build_agent_macro_pilot_binding(
        project_key=project_key, scope_id=session_id
    )
    core = get_persistent_codex_core(
        codex_bin_resolver=lambda: _resolve_codex_bin(
            str(getattr(settings, "codex_cli_llm_command", "codex") or "codex")
        ),
        workdir_resolver=_resolve_codex_workdir,
        disabled_features_resolver=_disabled_features,
    )
    invocation = core.invoke_native(command, binding=binding)
    observation = _native_macro_observation(invocation, binding=binding)
    root_task_id = str(session.get("root_task_id") or "").strip() or None
    service.create_message(
        session_id,
        role="assistant",
        actor="codex_native_agent",
        task_id=root_task_id,
        content=invocation.content,
        metadata={
            "runtime_variant": "agent_macro_native",
            "binding_id": binding.binding_id,
            "environment_digest": invocation.environment_digest,
            **observation,
        },
    )
    service.store.append_event(
        session_id,
        event_type="agent_macro.native_turn_observed",
        task_id=root_task_id,
        payload={
            "binding_id": binding.binding_id,
            "environment_digest": invocation.environment_digest,
            **observation,
        },
    )
    bundle = service.get_session_bundle(session_id)
    return {
        "contract_version": "agent_macro.native_turn.v1",
        "runtime_variant": "agent_macro_native",
        "core_mode": "native-agent",
        "binding": {
            "binding_id": binding.binding_id,
            "project_key": binding.project_key,
            "scope_id": binding.scope_id,
            "environment_digest": invocation.environment_digest,
            "skill_roots": list(binding.skill_roots),
            "capability_status": dict(invocation.capability_status),
        },
        "macro_cell": {
            "declaration_status": "blocked",
            "blocked_by": "MacroCellDefinition production instance is not authored",
        },
        "observation": observation,
        "session": bundle["session"],
        "tasks": bundle["tasks"],
        "messages": bundle["messages"],
        "events": bundle["events"],
        "artifacts": bundle["artifacts"],
        "approvals": bundle["approvals"],
        "final_answer": invocation.content,
    }


def _run_agent_macro_rapid_native_turn(
    payload: AgentChatTurnRequest, *, command: str, project_key: str | None
) -> dict[str, Any]:
    """Run Rapid with the project effects mounted as native dynamic tools."""

    if not project_key:
        raise ValueError("project_key is required for native Rapid turns")
    if not bool(getattr(settings, "codex_cli_llm_persistent_enabled", True)):
        raise RuntimeError("native Rapid requires the persistent Codex app-server core")

    from ..services.llm.codex_app_server import get_persistent_codex_core
    from ..services.llm.codex_cli import (
        _disabled_features,
        _resolve_codex_bin,
        _resolve_codex_workdir,
    )
    from ..services.llm.codex_macro_binding import build_agent_macro_rapid_binding

    service, session, session_id, project_key = _prepare_agent_core_session(
        payload,
        command=command,
        project_key=project_key,
        runtime_variant="agent_macro_rapid_native",
    )
    binding = build_agent_macro_rapid_binding(
        project_key=project_key, scope_id=session_id, service=service, session_id=session_id
    )
    core = get_persistent_codex_core(
        codex_bin_resolver=lambda: _resolve_codex_bin(
            str(getattr(settings, "codex_cli_llm_command", "codex") or "codex")
        ),
        workdir_resolver=_resolve_codex_workdir,
        disabled_features_resolver=_disabled_features,
    )
    invocation = core.invoke_native(command, binding=binding)
    observation = {
        **_native_macro_observation(invocation, binding=binding),
        "rapid_effects": [tool.logical_name for tool in binding.tools],
    }
    root_task_id = str(session.get("root_task_id") or "").strip() or None
    service.create_message(
        session_id,
        role="assistant",
        actor="codex_native_rapid",
        task_id=root_task_id,
        content=invocation.content,
        metadata={"runtime_variant": "agent_macro_rapid_native", "binding_id": binding.binding_id, **observation},
    )
    service.store.append_event(
        session_id,
        event_type="agent_macro.rapid_native_turn_observed",
        task_id=root_task_id,
        payload={"binding_id": binding.binding_id, **observation},
    )
    bundle = service.get_session_bundle(session_id)
    return {
        "contract_version": "agent_macro.rapid_native_turn.v1",
        "runtime_variant": "agent_macro_rapid_native",
        "core_mode": "native-agent",
        "binding": {"binding_id": binding.binding_id, "project_key": binding.project_key, "scope_id": binding.scope_id},
        "invocation": {"content": invocation.content, **observation},
        "session": bundle,
    }


def _validate_agent_core_session_project(
    *, session: dict[str, Any], project_key: str | None
) -> str | None:
    session_project_key = str(session.get("project_key") or "").strip() or None
    requested_project_key = str(project_key or "").strip() or None
    if (
        session_project_key
        and requested_project_key
        and session_project_key != requested_project_key
    ):
        raise ValueError(
            "session_id belongs to a different project; start a new agent session or use the session project_key"
        )
    return requested_project_key or session_project_key


def _run_agent_chat_turn_payload(payload: AgentChatTurnRequest) -> dict[str, Any]:
    command = str(payload.message or "").strip()
    if not command:
        _raise_invalid_input("message is required")
    runtime_variant = _require_runtime_variant(payload)
    _reject_retired_agent_control_options(payload)
    if _agent_chat_requires_explicit_project_key(payload):
        raise ValueError(
            "project_key is required for a new agent chat turn; do not rely on default project fallback"
        )
    project_key = (
        None
        if payload.session_id
        and str(payload.project_key or "").strip().lower()
        in _RESERVED_AGENT_PROJECT_KEYS
        else _resolve_agent_chat_project_key(payload.project_key)
    )
    if runtime_variant == "agent_macro_native":
        return _run_agent_macro_native_turn(
            payload, command=command, project_key=project_key
        )
    return _run_agent_macro_rapid_native_turn(
        payload, command=command, project_key=project_key
    )


def _sse(event: str, data: dict[str, Any]) -> str:
    encoded = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {encoded}\n\n"


@router.get("/capabilities", response_model=AgentChatEnvelope)
def list_agent_chat_capabilities(project_key: str | None = None) -> dict[str, Any]:
    from ..services.agent_runtime.capability_registry import (
        list_interactive_agent_capabilities,
    )

    flags = _agent_runtime_feature_flags()
    resolved_project_key = str(project_key or "").strip() or None
    tool_pool = AgentToolPoolAssembler().assemble(
        ToolPoolRequest(
            project_key=resolved_project_key,
            agent_mode="read_only",
            feature_flags=flags,
        )
    )
    return ok(
        {
            "items": list_interactive_agent_capabilities(),
            "feature_flags": flags,
            "tool_pool": tool_pool,
        }
    )


@router.post("/turn", response_model=AgentChatEnvelope)
def run_agent_chat_turn(payload: AgentChatTurnRequest) -> dict[str, Any]:
    try:
        out = _run_agent_chat_turn_payload(payload)
    except Exception as exc:  # noqa: BLE001
        _raise_mapped_error(exc)
    return ok(out)


@router.post(
    "/turn/stream",
    response_class=StreamingResponse,
    response_model=None,
    responses={
        200: {
            "description": (
                "Server-sent native agent chat turn events. A start event is sent "
                "first; accumulated session events and the final answer are sent "
                "after the native turn completes."
            ),
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        }
    },
)
def stream_agent_chat_turn(payload: AgentChatTurnRequest) -> StreamingResponse:
    _require_runtime_variant(payload)
    _reject_retired_agent_control_options(payload)

    def _iter():
        runtime_variant = _require_runtime_variant(payload)
        yield _sse(
            "interactive_agent.stream_started", {"runtime_variant": runtime_variant}
        )
        try:
            out = _run_agent_chat_turn_payload(payload)
        except Exception as exc:  # noqa: BLE001
            code, message, details = map_exception_to_error(exc)
            yield _sse(
                "interactive_agent.error",
                {
                    "status": "error",
                    "error": error_response(code, message, details=details),
                },
            )
            return
        for event in list(out.get("events") or []):
            if isinstance(event, dict):
                yield _sse(
                    str(event.get("event_type") or "interactive_agent.event"), event
                )
        yield _sse(
            "interactive_agent.final_answer",
            {
                "status": "ok",
                "runtime_variant": out.get("runtime_variant"),
                "session": out.get("session"),
                "final_answer": out.get("final_answer"),
                "stream": out.get("stream"),
                "result": out,
            },
        )

    return StreamingResponse(_iter(), media_type="text/event-stream")


@router.post("/approvals/{approval_id}/continue", response_model=AgentChatEnvelope)
def continue_agent_chat_approval(
    approval_id: str, payload: AgentChatApprovalContinueRequest
) -> dict[str, Any]:
    _raise_agent_runtime_retired("legacy_approval_continue")
    raise AssertionError("unreachable retired agent runtime")
