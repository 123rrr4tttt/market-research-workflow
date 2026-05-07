from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..contracts import ErrorCode, fail, map_exception_to_error
from ..contracts.responses import ok
from ..services.skill_runtime import invoke_skill, list_registered_skills


router = APIRouter(prefix="/skills", tags=["skills"])


def _error_status_code(code: ErrorCode) -> int:
    if code in {ErrorCode.INVALID_INPUT, ErrorCode.PROJECT_KEY_REQUIRED, ErrorCode.CONFIG_ERROR}:
        return 400
    if code == ErrorCode.NOT_FOUND:
        return 404
    if code == ErrorCode.RATE_LIMITED:
        return 429
    if code in {ErrorCode.UPSTREAM_ERROR, ErrorCode.PARSE_ERROR}:
        return 502
    return 500


def _error_json(status_code: int, code: ErrorCode, message: str, *, details: dict[str, Any] | None = None) -> JSONResponse:
    payload = fail(code, message, details=details)
    payload["detail"] = {"error": payload["error"], "message": payload["error"]["message"]}
    return JSONResponse(status_code=status_code, content=payload, headers={"X-Error-Code": code.value})


class SkillInvokeRequest(BaseModel):
    skill_id: str = Field(..., min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)
    actor_role: str | None = Field(default="orchestration_runtime", max_length=64)
    permissions: list[str] = Field(default_factory=list)
    session_id: str | None = Field(default=None, max_length=64)
    task_id: str | None = Field(default=None, max_length=64)
    approval_granted: bool = Field(default=False)
    trace_id: str | None = Field(default=None, max_length=128)
    consumer: str | None = Field(default="skills.api", max_length=128)


@router.get("")
def list_skills() -> dict[str, Any]:
    return ok({"items": list_registered_skills(), "total": len(list_registered_skills())})


@router.post("/invoke")
def invoke_skill_api(payload: SkillInvokeRequest) -> dict[str, Any]:
    try:
        invoked = invoke_skill(
            skill_id=payload.skill_id,
            payload=dict(payload.payload or {}),
            context={
                "actor_role": payload.actor_role,
                "permissions": payload.permissions,
                "agent_session_id": payload.session_id,
                "agent_task_id": payload.task_id,
                "approval_granted": payload.approval_granted,
                "trace_id": payload.trace_id,
                "consumer": payload.consumer,
            },
        )
        return ok(
            {
                "skill_id": invoked.get("skill_id"),
                "result": invoked.get("result"),
                "skill_meta": {
                    "trace_id": invoked.get("trace_id"),
                    "consumer": invoked.get("consumer"),
                    "actor_role": invoked.get("actor_role"),
                    "permissions": invoked.get("requested_permissions") or [],
                    "owner": invoked.get("owner"),
                    "execution_profile": invoked.get("execution_profile"),
                    "concurrency_class": invoked.get("concurrency_class"),
                    "approval_policy": invoked.get("approval_policy") or {},
                    "artifact_contract": invoked.get("artifact_contract") or {},
                    "approval_request": invoked.get("approval_request"),
                },
            }
        )
    except PermissionError as exc:
        return _error_json(
            400,
            ErrorCode.INVALID_INPUT,
            str(exc),
            details={"category": "skill_permission_denied"},
        )
    except RuntimeError as exc:
        message = str(exc)
        if "write_set_conflict" in message:
            return _error_json(
                400,
                ErrorCode.INVALID_INPUT,
                message,
                details={"category": "skill_write_conflict"},
            )
        code, mapped_message, details = map_exception_to_error(exc)
        return _error_json(_error_status_code(code), code, mapped_message, details=details)
    except Exception as exc:  # noqa: BLE001
        code, message, details = map_exception_to_error(exc)
        return _error_json(_error_status_code(code), code, message, details=details)
