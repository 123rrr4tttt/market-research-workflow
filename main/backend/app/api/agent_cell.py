"""Read-only projection of the same cell environment resolved by the native host."""
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from functorial_kit import Failure

from app.contracts.responses import ApiEnvelope, ApiErrorModel, ApiMetaModel, ok
from app.services.agent_core.macro_environment import resolve_macro_environment, select_active_macro_identity
from app.services.agent_core.project_tools import build_project_core_tool_registry
from app.services.agent_sessions.service import get_agent_session_service
from app.services.projects.context import current_project_key

router = APIRouter(prefix="/agent-cell", tags=["agent-cell"])


def _fail(status: int, code: str, message: str, details: dict[str, Any] | None = None) -> None:
    envelope = ApiEnvelope[Any](
        status="error", data=None,
        error=ApiErrorModel(code=code, message=message, details=details or {}),
        meta=ApiMetaModel(project_key=current_project_key()),
    )
    raise HTTPException(status_code=status, detail=envelope.model_dump())


def _check(result: Any) -> Any:
    if isinstance(result, Failure):
        context = dict(result.context or {})
        raw_code = context.get("macro_environment_code", result.code)
        code = raw_code if isinstance(raw_code, str) else result.code
        status = 409 if code == "macro_environment_ambiguous" else 422
        _fail(status, code, result.message, context)
    return result


@router.get("", response_model=ApiEnvelope[dict[str, Any]])
def read_agent_cell(package_id: str | None = None, package_version: str | None = None) -> dict[str, Any]:
    project = str(current_project_key() or "").strip()
    if not project:
        _fail(400, "PROJECT_KEY_REQUIRED", "active project context is required")
    service = get_agent_session_service()
    ids, versions = _check(select_active_macro_identity(
        service, project, package_id=package_id, package_version=package_version,
    ))
    resolved = _check(resolve_macro_environment(
        service, project, ids, versions,
        (Path(__file__).resolve().parents[2] / "skills",),
        build_project_core_tool_registry(service=service),
    ))
    return ok({"environment": resolved.descriptor(), "environment_digest": resolved.environment_digest})
