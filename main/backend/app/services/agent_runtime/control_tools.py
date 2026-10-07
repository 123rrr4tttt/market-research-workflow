from __future__ import annotations

from typing import Any

from functorial_kit import Failure
from sqlalchemy.engine import Engine

from app.services.agent_sessions.service import AgentSessionService

from .tool_contract import build_capability_call, build_tool_definition


CONTROL_TOOL_PROTOCOL = "session_control"


def _as_text(value: Any) -> str:
    return str(value or "").strip()


class AgentControlToolRuntime:
    """Control tools that act on canonical runtime runs or read session projections."""

    def __init__(
        self, *, service: AgentSessionService, engine: Engine | None = None
    ) -> None:
        self.service = service
        self._engine = engine

    def _runtime_engine(self) -> Engine:
        if self._engine is not None:
            return self._engine
        from app.models.base import engine

        return engine

    def list_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            build_tool_definition(
                name="task.cancel",
                capability_id="task.cancel",
                description="Request cancellation of the canonical runtime run associated with this session.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                output_schema={"type": "object", "additionalProperties": True},
                risk_level="medium",
                concurrency_class="write_shared",
                approval_level="explicit_user_request",
                timeout_seconds=10,
                result_budget=4000,
            ),
            build_tool_definition(
                name="task.summary",
                capability_id="task.summary",
                description="Read the current session summary without dispatching work or changing task state.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                output_schema={"type": "object", "additionalProperties": True},
                risk_level="low",
                concurrency_class="read_only",
                approval_level="none",
                timeout_seconds=10,
                result_budget=4000,
            ),
        ]

    def supported_tool_names(self) -> set[str]:
        return {str(item["name"]) for item in self.list_tool_definitions()}

    def execute(self, name: str, *, session_id: str, turn_id: str, input_payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = dict(input_payload or {})
        target_session_id = _as_text(payload.get("session_id")) or session_id
        if name == "task.cancel":
            return self.task_cancel(turn_id=turn_id, session_id=target_session_id)
        if name == "task.summary":
            return self.task_summary(turn_id=turn_id, session_id=target_session_id)
        return build_capability_call(
            turn_id=turn_id,
            capability_id=name,
            protocol=CONTROL_TOOL_PROTOCOL,
            status="failed",
            summary=f"unsupported control tool: {name}",
            result={},
            error={"type": "UnsupportedTool", "message": f"unsupported control tool: {name}"},
        )

    def task_cancel(self, *, turn_id: str, session_id: str) -> dict[str, Any]:
        try:
            from app.services.agent_core.host_authorization import (
                current_verified_host_authorization,
            )

            authorization = current_verified_host_authorization()
            if authorization is None:
                return build_capability_call(
                    turn_id=turn_id,
                    capability_id="task.cancel",
                    protocol=CONTROL_TOOL_PROTOCOL,
                    status="failed",
                    summary="task cancel requires a verified host authorization",
                    result={"session_id": session_id},
                    error={
                        "type": "Failure",
                        "code": "host_authorization_missing",
                        "message": "no verified host authorization for task cancel",
                    },
                )
            context = authorization.context
            if context.session_id != session_id:
                return build_capability_call(
                    turn_id=turn_id,
                    capability_id="task.cancel",
                    protocol=CONTROL_TOOL_PROTOCOL,
                    status="failed",
                    summary="trusted host context does not match the cancel target",
                    result={"session_id": session_id},
                    error={
                        "type": "Failure",
                        "code": "host_context_session_mismatch",
                        "message": "verified host session differs from cancel target",
                    },
                )
            session = self.service.get_session(session_id)
            if isinstance(session, Failure):
                return self._failure_call(
                    capability_id="task.cancel",
                    turn_id=turn_id,
                    summary=f"cancel failed for session {session_id}",
                    session_id=session_id,
                    failure=session,
                )
            run_id = _as_text(session.get("compat_job_id"))
            if not run_id:
                return build_capability_call(
                    turn_id=turn_id,
                    capability_id="task.cancel",
                    protocol=CONTROL_TOOL_PROTOCOL,
                    status="failed",
                    summary="session has no platform run to cancel",
                    result={"session_id": session_id},
                    error={
                        "type": "Failure",
                        "code": "run_id_missing",
                        "message": "session compat_job_id is absent",
                    },
                )
            actor_context = authorization.actor_context
            if actor_context is None or not actor_context.actor_trusted or not actor_context.actor_id:
                return build_capability_call(
                    turn_id=turn_id,
                    capability_id="task.cancel",
                    protocol=CONTROL_TOOL_PROTOCOL,
                    status="failed",
                    summary="task cancel requires an authenticated request actor",
                    result={"session_id": session_id},
                    error={
                        "type": "Failure",
                        "code": "trusted_actor_missing",
                        "message": "verified host authorization has no authenticated request actor",
                    },
                )
            result = self.service.cancel_run(
                run_id,
                actor_id=actor_context.actor_id,
                project_key=context.project_key,
                engine=self._runtime_engine(),
            )
            if isinstance(result, Failure):
                return self._failure_call(
                    capability_id="task.cancel",
                    turn_id=turn_id,
                    summary=f"cancel failed for run {run_id}",
                    session_id=session_id,
                    failure=result,
                )
            return build_capability_call(
                turn_id=turn_id,
                capability_id="task.cancel",
                protocol=CONTROL_TOOL_PROTOCOL,
                status="completed",
                summary=f"cancel requested for run {run_id}",
                result={
                    "session_id": session_id,
                    "run_id": run_id,
                    "state": result["state"],
                },
            )
        except Exception as exc:  # noqa: BLE001
            return build_capability_call(
                turn_id=turn_id,
                capability_id="task.cancel",
                protocol=CONTROL_TOOL_PROTOCOL,
                status="failed",
                summary=f"cancel failed for session {session_id}: {exc}",
                result={"session_id": session_id},
                error={"type": exc.__class__.__name__, "message": str(exc)},
            )

    def task_summary(self, *, turn_id: str, session_id: str) -> dict[str, Any]:
        try:
            summary = self.service.get_session_summary(session_id)
            if isinstance(summary, Failure):
                return self._failure_call(
                    capability_id="task.summary",
                    turn_id=turn_id,
                    summary=f"summary failed for session {session_id}",
                    session_id=session_id,
                    failure=summary,
                )
            return build_capability_call(
                turn_id=turn_id,
                capability_id="task.summary",
                protocol=CONTROL_TOOL_PROTOCOL,
                status="completed",
                summary=f"read session summary {session_id}",
                result={"session_id": session_id, "summary": summary},
            )
        except Exception as exc:  # noqa: BLE001
            return build_capability_call(
                turn_id=turn_id,
                capability_id="task.summary",
                protocol=CONTROL_TOOL_PROTOCOL,
                status="failed",
                summary=f"summary failed for session {session_id}: {exc}",
                result={"session_id": session_id},
                error={"type": exc.__class__.__name__, "message": str(exc)},
            )

    def _failure_call(
        self,
        *,
        capability_id: str,
        turn_id: str,
        summary: str,
        session_id: str,
        failure: Failure,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {"session_id": session_id}
        if task_id:
            result["task_id"] = task_id
        return build_capability_call(
            turn_id=turn_id,
            capability_id=capability_id,
            protocol=CONTROL_TOOL_PROTOCOL,
            status="failed",
            summary=summary,
            result=result,
            error={
                "type": "Failure",
                "code": failure.code,
                "message": failure.message,
                "context": dict(failure.context or {}),
            },
        )

    def _find_retryable_task_id(self, *, tasks: list[dict[str, Any]]) -> str | None:
        for task in reversed(tasks):
            if _as_text(task.get("status")) in {"failed", "canceled", "expired"}:
                return _as_text(task.get("task_id")) or None
        return None
