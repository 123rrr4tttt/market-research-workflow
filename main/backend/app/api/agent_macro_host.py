from __future__ import annotations

from typing import Any, Literal, NoReturn

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from pydantic import SecretStr
import secrets

from ..contracts import ErrorCode, error_response
from ..models.base import SessionLocal
from ..models.entities import Project
from ..services.agent_core.macro_host import AgentMacroHostService, MacroHostError
from ..services.agent_sessions.service import get_agent_session_service
from ..services.projects.context import bind_schema
from ..services.request_identity import (
    RequestActorContext,
    resolve_local_single_user_actor_context,
    resolve_request_actor_context,
)
from ..settings.config import settings
from sqlalchemy import select


router = APIRouter(prefix="/agent-macro-host", tags=["agent_macro_host"])


class PrepareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    projectKey: str = Field(min_length=1, max_length=128)
    packageId: str | None = Field(default=None, min_length=1, max_length=128)
    packageVersion: str | None = Field(default=None, min_length=1, max_length=128)


class BindRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bindingId: str = Field(min_length=1, max_length=80)
    threadId: str = Field(min_length=1, max_length=128)


class EnvironmentQuery(BaseModel):
    bindingId: str | None = Field(default=None, min_length=1, max_length=80)
    threadId: str | None = Field(default=None, min_length=1, max_length=128)


class RecordInputAttachment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["local_image"]
    attachmentId: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    filename: str = Field(min_length=1, max_length=255, pattern=r"^[^/\\\x00]+$")
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RecordInputRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    threadId: str = Field(min_length=1, max_length=128)
    turnId: str = Field(min_length=1, max_length=128)
    content: str = Field(default="", max_length=16000)
    admissionId: str = Field(min_length=1, max_length=80)
    attachments: list[RecordInputAttachment] = Field(default_factory=list, max_length=8)


class PrepareTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    threadId: str = Field(min_length=1, max_length=128)


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    threadId: str = Field(min_length=1, max_length=128)
    turnId: str = Field(min_length=1, max_length=128)
    actionId: str = Field(min_length=1, max_length=128)
    approved: bool
    userText: str | None = Field(default=None, max_length=4000)


class DispatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    threadId: str = Field(min_length=1, max_length=128)
    turnId: str = Field(min_length=1, max_length=128)
    callId: str = Field(min_length=1, max_length=128)
    namespace: str | None = Field(default=None, max_length=64)
    tool: str = Field(min_length=1, max_length=128)
    arguments: dict[str, Any] = Field(default_factory=dict)


class EndTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    threadId: str = Field(min_length=1, max_length=128)
    turnId: str = Field(min_length=1, max_length=128)


def _configured_server_key() -> str:
    raw = getattr(settings, "codex_webui_server_api_key", "")
    if isinstance(raw, SecretStr):
        return raw.get_secret_value().strip()
    return str(raw or "").strip()


def require_webui_server(
    request: Request,
    x_mrw_server_api_key: str | None = Header(default=None, alias="X-MRW-Server-API-Key"),
) -> None:
    del request
    configured = _configured_server_key()
    if not configured:
        _raise_host_error(MacroHostError(
            "server_api_key_unconfigured",
            "codex webui server api key is not configured",
            status_code=503,
        ))
    if x_mrw_server_api_key is None or not secrets.compare_digest(x_mrw_server_api_key, configured):
        _raise_host_error(MacroHostError(
            "invalid_server_api_key",
            "codex webui server authentication failed",
            status_code=401,
        ))


def _authenticated_actor(request: Request) -> RequestActorContext | None:
    local_actor = resolve_local_single_user_actor_context(
        request,
        enabled=bool(getattr(settings, "codex_webui_local_single_user_enabled", False)),
        server_api_key=getattr(settings, "codex_webui_server_api_key", ""),
    )
    if local_actor is not None:
        return local_actor
    actor = resolve_request_actor_context(request)
    if actor.actor_source in {
        "authenticated_oauth_token_sink",
        "authenticated_oauth_token_sink_claims",
    }:
        raise MacroHostError(
            "authenticated_host_actor_required",
            "provider credentials do not identify an authenticated MRW host user",
            status_code=401,
        )
    return actor if actor.actor_trusted else None


def _project_exists(project_key: str) -> bool:
    with SessionLocal() as session, bind_schema("public"):
        row = session.execute(
            select(Project).where(Project.project_key == project_key, Project.enabled.is_(True))
        ).scalar_one_or_none()
        return row is not None


def _raise_host_error(exc: MacroHostError) -> NoReturn:
    status_code = exc.status_code
    code = ErrorCode.INVALID_INPUT if status_code < 500 else ErrorCode.UPSTREAM_ERROR
    detail = error_response(code, exc.message, details={"category": "agent_macro_host", "reason_code": exc.code})
    detail["error"]["code"] = exc.code
    raise HTTPException(status_code=status_code, detail=detail) from exc


_service: AgentMacroHostService | None = None


def configure_agent_macro_host_service(service: AgentMacroHostService | None) -> None:
    global _service
    _service = service


def get_agent_macro_host_service() -> AgentMacroHostService:
    global _service
    if _service is None:
        _service = AgentMacroHostService(
            project_checker=_project_exists,
            agent_session_service=get_agent_session_service(),
        )
    return _service


@router.post("/prepare", dependencies=[Depends(require_webui_server)])
def prepare_macro_host(payload: PrepareRequest) -> dict[str, Any]:
    service = get_agent_macro_host_service()
    try:
        return service.prepare(
            project_key=payload.projectKey,
            package_id=payload.packageId,
            package_version=payload.packageVersion,
        )
    except MacroHostError as exc:
        _raise_host_error(exc)


@router.post("/bind", dependencies=[Depends(require_webui_server)])
def bind_macro_host(payload: BindRequest) -> dict[str, Any]:
    service = get_agent_macro_host_service()
    try:
        return service.bind(binding_id=payload.bindingId, thread_id=payload.threadId)
    except MacroHostError as exc:
        _raise_host_error(exc)


@router.get("/environment", dependencies=[Depends(require_webui_server)])
def read_macro_environment(bindingId: str | None = None, threadId: str | None = None) -> dict[str, Any]:
    service = get_agent_macro_host_service()
    try:
        return service.environment(binding_id=bindingId, thread_id=threadId)
    except MacroHostError as exc:
        _raise_host_error(exc)


@router.post("/record-input", dependencies=[Depends(require_webui_server)])
def record_macro_input(payload: RecordInputRequest, request: Request) -> dict[str, Any]:
    service = get_agent_macro_host_service()
    try:
        return service.record_input(
            thread_id=payload.threadId,
            turn_id=payload.turnId,
            content=payload.content,
            admission_id=payload.admissionId,
            attachments=[item.model_dump() for item in payload.attachments],
            actor_context=_authenticated_actor(request),
        )
    except MacroHostError as exc:
        _raise_host_error(exc)


@router.post("/prepare-turn", dependencies=[Depends(require_webui_server)])
def prepare_macro_turn(payload: PrepareTurnRequest, request: Request) -> dict[str, Any]:
    service = get_agent_macro_host_service()
    try:
        return service.prepare_turn(
            thread_id=payload.threadId,
            actor_context=_authenticated_actor(request),
        )
    except MacroHostError as exc:
        _raise_host_error(exc)


@router.post("/confirm", dependencies=[Depends(require_webui_server)])
def confirm_macro_action(payload: ConfirmRequest) -> dict[str, Any]:
    service = get_agent_macro_host_service()
    try:
        return service.confirm(
            thread_id=payload.threadId,
            turn_id=payload.turnId,
            action_id=payload.actionId,
            approved=payload.approved,
            user_text=payload.userText,
        )
    except MacroHostError as exc:
        _raise_host_error(exc)


@router.post("/dispatch", dependencies=[Depends(require_webui_server)])
def dispatch_macro_tool(payload: DispatchRequest, request: Request) -> dict[str, Any]:
    service = get_agent_macro_host_service()
    try:
        return service.dispatch(
            thread_id=payload.threadId,
            turn_id=payload.turnId,
            call_id=payload.callId,
            namespace=payload.namespace,
            tool=payload.tool,
            arguments=payload.arguments,
            actor_context=_authenticated_actor(request),
        )
    except MacroHostError as exc:
        _raise_host_error(exc)


@router.post("/end-turn", dependencies=[Depends(require_webui_server)])
def end_macro_turn(payload: EndTurnRequest) -> dict[str, Any]:
    service = get_agent_macro_host_service()
    try:
        return service.end_turn(thread_id=payload.threadId, turn_id=payload.turnId)
    except MacroHostError as exc:
        _raise_host_error(exc)
