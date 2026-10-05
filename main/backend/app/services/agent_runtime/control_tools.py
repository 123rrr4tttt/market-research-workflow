from __future__ import annotations

from typing import Any

from functorial_kit import Failure

from app.services.agent_sessions.service import AgentSessionService

from .tool_contract import build_capability_call, build_tool_definition


CONTROL_TOOL_PROTOCOL = "session_control"


def _as_text(value: Any) -> str:
    return str(value or "").strip()


class AgentControlToolRuntime:
    """Session control tools that mutate the current agent ledger."""

    def __init__(self, *, service: AgentSessionService) -> None:
        self.service = service

    def list_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            build_tool_definition(
                name="task.cancel",
                capability_id="task.cancel",
                description="Cancel the current agent session and mark unfinished tasks as canceled.",
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
                name="task.retry",
                capability_id="task.retry",
                description="Retry a failed, canceled, or expired task in the current agent session.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "task_id": {"type": "string"},
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
        if name == "task.retry":
            return self.task_retry(
                turn_id=turn_id,
                session_id=target_session_id,
                task_id=_as_text(payload.get("task_id")) or None,
            )
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
            session = self.service.cancel_session(session_id)
            return build_capability_call(
                turn_id=turn_id,
                capability_id="task.cancel",
                protocol=CONTROL_TOOL_PROTOCOL,
                status="completed",
                summary=f"canceled session {session_id}",
                result={"session": session, "session_id": session_id},
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

    def task_retry(self, *, turn_id: str, session_id: str, task_id: str | None = None) -> dict[str, Any]:
        resolved_task_id = _as_text(task_id)
        if not resolved_task_id:
            tasks = self.service.list_tasks(session_id)
            if isinstance(tasks, Failure):
                return self._failure_call(
                    capability_id="task.retry",
                    turn_id=turn_id,
                    summary=f"retry failed for session {session_id}",
                    session_id=session_id,
                    failure=tasks,
                )
            resolved_task_id = self._find_retryable_task_id(tasks=tasks)
        if not resolved_task_id:
            return build_capability_call(
                turn_id=turn_id,
                capability_id="task.retry",
                protocol=CONTROL_TOOL_PROTOCOL,
                status="skipped",
                summary="task retry skipped because no failed, canceled, or expired task was found",
                result={"session_id": session_id, "task_id": None},
            )
        try:
            task = self.service.retry_task(session_id, resolved_task_id)
            if isinstance(task, Failure):
                return self._failure_call(
                    capability_id="task.retry",
                    turn_id=turn_id,
                    summary=f"retry failed for task {resolved_task_id}",
                    session_id=session_id,
                    task_id=resolved_task_id,
                    failure=task,
                )
            return build_capability_call(
                turn_id=turn_id,
                capability_id="task.retry",
                protocol=CONTROL_TOOL_PROTOCOL,
                status="completed",
                summary=f"retried task {resolved_task_id}",
                result={"session_id": session_id, "task": task, "task_id": resolved_task_id},
            )
        except Exception as exc:  # noqa: BLE001
            return build_capability_call(
                turn_id=turn_id,
                capability_id="task.retry",
                protocol=CONTROL_TOOL_PROTOCOL,
                status="failed",
                summary=f"retry failed for task {resolved_task_id}: {exc}",
                result={"session_id": session_id, "task_id": resolved_task_id},
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
