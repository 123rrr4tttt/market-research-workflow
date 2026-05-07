from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..contracts import ErrorCode, error_response
from ..contracts.errors import map_exception_to_error
from ..contracts.responses import ok
from ..services.agent_runtime import iter_session_events
from ..services.agent_sessions import get_agent_session_service

router = APIRouter(tags=["agent_sessions"])


def _raise_invalid_input(message: str) -> None:
    raise HTTPException(
        status_code=400,
        detail=error_response(
            ErrorCode.INVALID_INPUT,
            message,
        ),
    )


def _raise_not_found(message: str) -> None:
    raise HTTPException(
        status_code=404,
        detail=error_response(
            ErrorCode.NOT_FOUND,
            message,
        ),
    )


def _raise_mapped_error(exc: Exception) -> None:
    if isinstance(exc, ValueError):
        _raise_invalid_input(str(exc) or "invalid agent session request")
    code, message, details = map_exception_to_error(exc)
    status_code = 400 if code == ErrorCode.INVALID_INPUT else 404 if code == ErrorCode.NOT_FOUND else 429 if code == ErrorCode.RATE_LIMITED else 502 if code in {ErrorCode.UPSTREAM_ERROR, ErrorCode.PARSE_ERROR} else 500
    raise HTTPException(
        status_code=status_code,
        detail=error_response(code, message, details=details),
    ) from exc


class AgentSessionTaskBlueprint(BaseModel):
    task_id: str | None = Field(default=None, max_length=64)
    parent_task_id: str | None = Field(default=None, max_length=64)
    subject: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    task_type: str = Field(..., min_length=1, max_length=64)
    phase: str = Field(default="research", min_length=1, max_length=32)
    status: str | None = Field(default=None, max_length=16)
    execution_mode: str = Field(default="worker", max_length=32)
    owner: str | None = Field(default=None, max_length=128)
    blocked_by: list[str] = Field(default_factory=list)
    blocked_by_refs: list[str] = Field(default_factory=list)
    priority: int = Field(default=5, ge=0, le=9)
    write_set: list[str] = Field(default_factory=list)
    read_set: list[str] = Field(default_factory=list)
    completion_criteria: list[str] = Field(default_factory=list)
    verification_steps: list[str] = Field(default_factory=list)
    artifact_targets: list[str] = Field(default_factory=list)
    task_spec: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    result_summary: str | None = Field(default=None, max_length=4000)
    result_payload: dict[str, Any] = Field(default_factory=dict)


class AgentSessionCreateRequest(BaseModel):
    source: str = Field(default="user", min_length=1, max_length=64)
    project_key: str | None = Field(default=None, max_length=128)
    entrypoint_type: str = Field(default="chat", min_length=1, max_length=64)
    goal: str = Field(..., min_length=1, max_length=8000)
    initial_context: dict[str, Any] = Field(default_factory=dict)
    compat_mode: bool = Field(default=False)
    logical_task_list_key: str | None = Field(default=None, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)
    task_blueprints: list[AgentSessionTaskBlueprint] = Field(default_factory=list)


class AgentTaskRetryRequest(BaseModel):
    task_id: str = Field(..., min_length=1, max_length=64)


class AgentApprovalResolveRequest(BaseModel):
    approved: bool = Field(default=True)
    approved_by: str = Field(default="user", min_length=1, max_length=128)


class AgentMessageCreateRequest(BaseModel):
    role: str = Field(default="assistant", min_length=1, max_length=32)
    actor: str | None = Field(default=None, max_length=128)
    task_id: str | None = Field(default=None, max_length=64)
    content: str = Field(..., min_length=1, max_length=16000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentApprovalRequest(BaseModel):
    task_id: str = Field(..., min_length=1, max_length=64)
    requester_actor: str = Field(default="user_facing_assistant", min_length=1, max_length=64)
    binding_payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.post("/agent-sessions")
def create_agent_session(payload: AgentSessionCreateRequest) -> dict[str, Any]:
    service = get_agent_session_service()
    try:
        out = service.create_session(
            source=payload.source,
            project_key=payload.project_key,
            entrypoint_type=payload.entrypoint_type,
            goal=payload.goal,
            initial_context=dict(payload.initial_context or {}),
            compat_mode=bool(payload.compat_mode),
            logical_task_list_key=payload.logical_task_list_key,
            metadata=dict(payload.metadata or {}),
            task_blueprints=[item.model_dump() for item in payload.task_blueprints],
        )
    except Exception as exc:  # noqa: BLE001
        _raise_mapped_error(exc)
    return ok(out)


@router.get("/agent-sessions")
def list_agent_sessions(limit: int = 50) -> dict[str, Any]:
    service = get_agent_session_service()
    return ok({"items": service.list_sessions(limit=max(1, min(limit, 200)))})


@router.get("/agent-sessions/{session_id}")
def get_agent_session(session_id: str) -> dict[str, Any]:
    service = get_agent_session_service()
    try:
        return ok(service.get_session_bundle(session_id))
    except KeyError:
        _raise_not_found("session not found")


@router.get("/agent-sessions/{session_id}/tasks")
def get_agent_session_tasks(session_id: str) -> dict[str, Any]:
    service = get_agent_session_service()
    try:
        return ok({"items": service.list_tasks(session_id)})
    except KeyError:
        _raise_not_found("session not found")


@router.get("/agent-sessions/{session_id}/events")
def get_agent_session_events(session_id: str) -> dict[str, Any]:
    service = get_agent_session_service()
    try:
        return ok({"items": service.list_events(session_id)})
    except KeyError:
        _raise_not_found("session not found")


@router.get("/agent-sessions/{session_id}/artifacts")
def get_agent_session_artifacts(session_id: str) -> dict[str, Any]:
    service = get_agent_session_service()
    try:
        return ok({"items": service.list_artifacts(session_id)})
    except KeyError:
        _raise_not_found("session not found")


@router.get("/agent-sessions/{session_id}/messages")
def get_agent_session_messages(session_id: str) -> dict[str, Any]:
    service = get_agent_session_service()
    try:
        return ok({"items": service.list_messages(session_id)})
    except KeyError:
        _raise_not_found("session not found")


@router.post("/agent-sessions/{session_id}/messages")
def create_agent_session_message(session_id: str, payload: AgentMessageCreateRequest) -> dict[str, Any]:
    service = get_agent_session_service()
    try:
        out = service.create_message(
            session_id,
            role=payload.role,
            actor=payload.actor,
            task_id=payload.task_id,
            content=payload.content,
            metadata=dict(payload.metadata or {}),
        )
    except KeyError:
        _raise_not_found("session not found")
    return ok(out)


@router.get("/agent-approvals")
def list_agent_approvals(session_id: str | None = None) -> dict[str, Any]:
    service = get_agent_session_service()
    return ok({"items": service.list_approvals(session_id=session_id)})


@router.get("/agent-sessions/{session_id}/stream")
def stream_agent_session_events(
    session_id: str,
    since_seq: int = 0,
    poll_seconds: float = 1.0,
    max_seconds: int = 30,
) -> StreamingResponse:
    service = get_agent_session_service()
    try:
        service.get_session(session_id)
    except KeyError:
        _raise_not_found("session not found")
    return StreamingResponse(
        iter_session_events(
            service=service,
            session_id=session_id,
            since_seq=since_seq,
            poll_seconds=poll_seconds,
            max_seconds=max_seconds,
        ),
        media_type="text/event-stream",
    )


@router.post("/agent-sessions/{session_id}/actions/retry-task")
def retry_agent_session_task(session_id: str, payload: AgentTaskRetryRequest) -> dict[str, Any]:
    service = get_agent_session_service()
    try:
        out = service.retry_task(session_id, payload.task_id)
    except KeyError:
        _raise_not_found("session or task not found")
    except Exception as exc:  # noqa: BLE001
        _raise_mapped_error(exc)
    return ok(out)


@router.post("/agent-sessions/{session_id}/actions/cancel")
def cancel_agent_session(session_id: str) -> dict[str, Any]:
    service = get_agent_session_service()
    try:
        out = service.cancel_session(session_id)
    except KeyError:
        _raise_not_found("session not found")
    return ok(out)


@router.post("/agent-sessions/{session_id}/actions/reclaim-expired")
def reclaim_agent_session_expired_tasks(session_id: str) -> dict[str, Any]:
    service = get_agent_session_service()
    try:
        out = service.reclaim_expired_tasks(session_id)
    except KeyError:
        _raise_not_found("session not found")
    return ok({"items": out})


@router.post("/agent-sessions/{session_id}/actions/coordinator-pass")
def run_agent_session_coordinator_pass(session_id: str) -> dict[str, Any]:
    service = get_agent_session_service()
    try:
        out = service.run_coordinator_pass(session_id)
    except KeyError:
        _raise_not_found("session not found")
    return ok(out)


@router.post("/agent-sessions/{session_id}/actions/request-approval")
def request_agent_session_approval(session_id: str, payload: AgentApprovalRequest) -> dict[str, Any]:
    service = get_agent_session_service()
    try:
        out = service.request_approval(
            session_id=session_id,
            task_id=payload.task_id,
            requester_actor=payload.requester_actor,
            binding_payload=dict(payload.binding_payload or {}),
            metadata=dict(payload.metadata or {}),
        )
    except KeyError:
        _raise_not_found("session or task not found")
    return ok(out)


@router.post("/agent-approvals/{approval_id}/resolve")
def resolve_agent_approval(approval_id: str, payload: AgentApprovalResolveRequest) -> dict[str, Any]:
    service = get_agent_session_service()
    try:
        out = service.resolve_approval(
            approval_id,
            approved=bool(payload.approved),
            approved_by=payload.approved_by,
        )
    except KeyError:
        _raise_not_found("approval not found")
    return ok(out)
