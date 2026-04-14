from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..contracts import ErrorCode, map_exception_to_error
from ..contracts.responses import ok
from ..services.skill_runtime import invoke_skill, list_registered_skills


router = APIRouter(prefix="/skills", tags=["skills"])


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
                },
            }
        )
    except PermissionError as exc:
        return {
            "status": "error",
            "error": {
                "code": ErrorCode.INVALID_INPUT.value,
                "message": str(exc),
                "details": {"category": "skill_permission_denied"},
            },
            "data": None,
            "meta": None,
        }
    except Exception as exc:  # noqa: BLE001
        code, message, details = map_exception_to_error(exc)
        return {
            "status": "error",
            "error": {"code": code.value, "message": message, "details": details},
            "data": None,
            "meta": None,
        }
