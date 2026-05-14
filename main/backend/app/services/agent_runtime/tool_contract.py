from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


CAPABILITY_CALL_CONTRACT_VERSION = "interactive_agent.capability_call.v1"
TOOL_DEFINITION_CONTRACT_VERSION = "interactive_agent.tool_definition.v1"
RUN_LOOP_CONTRACT_VERSION = "interactive_agent.run_loop.v1"
READ_ONLY_TOOL_PROTOCOL = "read_only"
STREAM_PROTOCOL_VERSION = "agent_session.sse.v1"


@dataclass(frozen=True)
class ToolCallOptions:
    dry_run: bool = False
    explain_only: bool = False
    approval_required: bool = False
    resume_token: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "explain_only": self.explain_only,
            "approval_required": self.approval_required,
            "resume_token": self.resume_token,
        }


@dataclass(frozen=True)
class ToolExecutionContext:
    session_id: str
    task_id: str | None = None
    turn_id: str | None = None
    project_key: str | None = None
    user: str | None = None
    abort_signal: Any | None = None
    budget: dict[str, Any] = field(default_factory=dict)
    permissions: tuple[str, ...] = ()
    feature_flags: dict[str, bool] = field(default_factory=dict)
    options: ToolCallOptions = field(default_factory=ToolCallOptions)
    event_writer: Callable[[dict[str, Any]], None] | None = None
    artifact_writer: Callable[[dict[str, Any]], dict[str, Any]] | None = None

    def to_model_context(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "task_id": self.task_id,
            "turn_id": self.turn_id,
            "project_key": self.project_key,
            "user": self.user,
            "budget": dict(self.budget or {}),
            "permissions": list(self.permissions),
            "feature_flags": dict(self.feature_flags or {}),
            "options": self.options.to_dict(),
            "abortable": self.abort_signal is not None,
        }


def build_capability_call(
    *,
    turn_id: str,
    capability_id: str,
    status: str,
    summary: str,
    result: dict[str, Any] | None = None,
    protocol: str | None = None,
    error: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "contract_version": CAPABILITY_CALL_CONTRACT_VERSION,
        "turn_id": turn_id,
        "capability_id": capability_id,
        "tool_name": capability_id,
        "status": status,
        "summary": summary,
        "result": result or {},
    }
    if protocol:
        payload["protocol"] = protocol
        payload["stream_state"] = "completed" if status in {"completed", "delegated", "skipped"} else status
    if error:
        payload["error"] = error
    if extra:
        payload.update(extra)
    return payload


def build_tool_definition(
    *,
    name: str,
    description: str,
    input_schema: dict[str, Any] | None = None,
    output_schema: dict[str, Any] | None = None,
    risk_level: str = "low",
    concurrency_class: str = "read_only",
    approval_level: str = "none",
    timeout_seconds: int = 10,
    result_budget: int = 4000,
    capability_id: str | None = None,
) -> dict[str, Any]:
    return {
        "contract_version": TOOL_DEFINITION_CONTRACT_VERSION,
        "name": name,
        "tool_name": name,
        "capability_id": capability_id or name,
        "description": description,
        "input_schema": input_schema or {"type": "object", "properties": {}, "additionalProperties": True},
        "output_schema": output_schema or {"type": "object", "additionalProperties": True},
        "risk_level": risk_level,
        "concurrency_class": concurrency_class,
        "approval_level": approval_level,
        "timeout_seconds": int(timeout_seconds),
        "result_budget": int(result_budget),
    }


def build_stream_descriptor(*, session_id: str, since_seq: int = 0) -> dict[str, Any]:
    return {
        "protocol_version": STREAM_PROTOCOL_VERSION,
        "session_id": session_id,
        "url": f"/api/v1/agent-sessions/{session_id}/stream",
        "since_seq": max(0, int(since_seq or 0)),
        "event_format": "server_sent_events",
    }
