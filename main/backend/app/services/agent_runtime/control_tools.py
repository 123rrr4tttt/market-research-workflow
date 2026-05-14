from __future__ import annotations

from typing import Any

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
                name="task.continue",
                capability_id="task.continue",
                description="Run a coordinator pass to continue a waiting or partially completed agent session.",
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
                timeout_seconds=20,
                result_budget=6000,
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
        if name == "task.continue":
            return self.task_continue(turn_id=turn_id, session_id=target_session_id)
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
        resolved_task_id = _as_text(task_id) or self._find_retryable_task_id(session_id)
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

    def task_continue(self, *, turn_id: str, session_id: str) -> dict[str, Any]:
        try:
            resumed_task = self._resume_canceled_task(session_id=session_id, turn_id=turn_id)
            result = self.service.run_coordinator_pass(session_id)
            if resumed_task:
                result = {**dict(result or {}), "resumed_task": resumed_task}
            return build_capability_call(
                turn_id=turn_id,
                capability_id="task.continue",
                protocol=CONTROL_TOOL_PROTOCOL,
                status="completed",
                summary=f"continued session {session_id}",
                result={"session_id": session_id, "coordinator": result},
            )
        except Exception as exc:  # noqa: BLE001
            return build_capability_call(
                turn_id=turn_id,
                capability_id="task.continue",
                protocol=CONTROL_TOOL_PROTOCOL,
                status="failed",
                summary=f"continue failed for session {session_id}: {exc}",
                result={"session_id": session_id},
                error={"type": exc.__class__.__name__, "message": str(exc)},
            )

    def _resume_canceled_task(self, *, session_id: str, turn_id: str) -> dict[str, Any] | None:
        tasks = self.service.list_tasks(session_id)
        completed = {_as_text(task.get("task_id")) for task in tasks if _as_text(task.get("status")) == "completed"}
        for task in reversed(tasks):
            if _as_text(task.get("status")) != "canceled":
                continue
            task_type = _as_text(task.get("task_type"))
            phase = _as_text(task.get("phase"))
            if task_type in {"final_answer", "interactive_plan", "approval_wait"}:
                continue
            if phase not in {"implementation", "synthesis", "verification"}:
                continue
            unresolved = [dep for dep in list(task.get("blocked_by") or []) if _as_text(dep) not in completed]
            new_status = "blocked" if unresolved else "pending"
            updated = self.service.store.update_task(
                session_id,
                _as_text(task.get("task_id")),
                {
                    "status": new_status,
                    "lease_until": None,
                    "completed_at": None,
                    "last_activity": "task continued after user cancel",
                    "recent_activities": ["task continued after user cancel"],
                },
            )
            self.service.store.append_event(
                session_id,
                event_type="task.continue_resumed_canceled",
                task_id=updated.get("task_id"),
                payload={
                    "turn_id": turn_id,
                    "task_id": updated.get("task_id"),
                    "status": new_status,
                    "unresolved_dependencies": unresolved,
                },
            )
            self.service.store.update_session(session_id, {"status": "pending"})
            return updated
        self.service.store.update_session(session_id, {"status": "pending"})
        self.service.store.append_event(
            session_id,
            event_type="task.continue_resumed_session",
            payload={"turn_id": turn_id, "reason": "no canceled worker task found"},
        )
        return None

    def _find_retryable_task_id(self, session_id: str) -> str | None:
        for task in reversed(self.service.list_tasks(session_id)):
            if _as_text(task.get("status")) in {"failed", "canceled", "expired"}:
                return _as_text(task.get("task_id")) or None
        return None
