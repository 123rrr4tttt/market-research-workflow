from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Protocol
from uuid import uuid4


CoreEventType = Literal[
    "session_started",
    "user_message",
    "assistant_delta",
    "assistant_message",
    "tool_call_requested",
    "permission_requested",
    "tool_call_started",
    "tool_progress",
    "tool_result",
    "artifact_created",
    "approval_resolved",
    "run_interrupted",
    "run_resumed",
    "run_compacted",
    "turn_state",
    "final_answer",
    "error",
]
ToolRisk = Literal["read_only", "write_shared", "write_external", "privileged"]
ToolPermission = Literal["allow", "ask", "deny", "explicit_user_request"]
ToolConcurrency = Literal["parallel", "serial", "exclusive"]
ToolSource = Literal["builtin", "project", "skill", "mcp", "legacy_adapter"]
ToolStatus = Literal["completed", "failed", "canceled", "needs_approval", "deferred"]
ModelStepType = Literal["assistant_delta", "final_answer", "tool_calls"]


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_core_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:16]}"


@dataclass(frozen=True)
class CoreEvent:
    event_type: CoreEventType
    session_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: new_core_id("evt"))
    turn_id: str | None = None
    call_id: str | None = None
    actor: str = "agent_core"
    created_at: str = field(default_factory=utcnow_iso)
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        out = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "session_id": self.session_id,
            "actor": self.actor,
            "created_at": self.created_at,
            "version": self.version,
            "payload": dict(self.payload or {}),
        }
        if self.turn_id:
            out["turn_id"] = self.turn_id
        if self.call_id:
            out["call_id"] = self.call_id
        return out


@dataclass(frozen=True)
class CoreToolSpec:
    name: str
    description_for_model: str
    title: str | None = None
    input_schema: dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})
    output_schema: dict[str, Any] = field(default_factory=lambda: {"type": "object", "additionalProperties": True})
    source: ToolSource = "project"
    risk: ToolRisk = "read_only"
    permission: ToolPermission = "allow"
    concurrency: ToolConcurrency = "parallel"
    timeout_seconds: int = 10
    result_budget: int = 4000
    mcp_server: str | None = None
    skill_id: str | None = None
    project_service_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_model_tool(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title or self.name,
            "description": self.description_for_model,
            "input_schema": dict(self.input_schema or {}),
            "risk": self.risk,
            "permission": self.permission,
            "source": self.source,
            "concurrency": self.concurrency,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title or self.name,
            "description_for_model": self.description_for_model,
            "input_schema": dict(self.input_schema or {}),
            "output_schema": dict(self.output_schema or {}),
            "source": self.source,
            "risk": self.risk,
            "permission": self.permission,
            "concurrency": self.concurrency,
            "timeout_seconds": int(self.timeout_seconds),
            "result_budget": int(self.result_budget),
            "mcp_server": self.mcp_server,
            "skill_id": self.skill_id,
            "project_service_id": self.project_service_id,
            "metadata": dict(self.metadata or {}),
        }


@dataclass(frozen=True)
class CoreToolCall:
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    call_id: str = field(default_factory=lambda: new_core_id("call"))
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "arguments": dict(self.arguments or {}),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class CoreToolResult:
    call_id: str
    tool_name: str
    status: ToolStatus
    model_summary: str
    ui_summary: str | None = None
    structured_content: dict[str, Any] = field(default_factory=dict)
    artifact_refs: tuple[str, ...] = ()
    error: dict[str, Any] | None = None
    retry_hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out = {
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "status": self.status,
            "model_summary": self.model_summary,
            "ui_summary": self.ui_summary or self.model_summary,
            "structured_content": dict(self.structured_content or {}),
            "artifact_refs": list(self.artifact_refs or ()),
        }
        if self.error:
            out["error"] = dict(self.error)
        if self.retry_hint:
            out["retry_hint"] = self.retry_hint
        return out


@dataclass(frozen=True)
class CorePermissionRequest:
    approval_id: str
    session_id: str
    turn_id: str
    tool_call: CoreToolCall
    tool_spec: CoreToolSpec
    reason: str
    created_at: str = field(default_factory=utcnow_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "tool_call": self.tool_call.to_dict(),
            "tool_spec": self.tool_spec.to_dict(),
            "reason": self.reason,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class CoreApprovalResume:
    approval_id: str
    tool_call: CoreToolCall
    approved: bool
    approved_by: str = "user"
    updated_arguments: dict[str, Any] | None = None

    def resolved_tool_call(self) -> CoreToolCall:
        if self.updated_arguments is None:
            return self.tool_call
        return CoreToolCall(
            tool_name=self.tool_call.tool_name,
            arguments=dict(self.updated_arguments),
            call_id=self.tool_call.call_id,
            reason=self.tool_call.reason,
        )


@dataclass(frozen=True)
class CoreModelStep:
    step_type: ModelStepType
    content: str = ""
    tool_calls: tuple[CoreToolCall, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def final(cls, answer: str, **metadata: Any) -> "CoreModelStep":
        return cls(step_type="final_answer", content=answer, metadata=dict(metadata))

    @classmethod
    def tools(cls, *tool_calls: CoreToolCall, **metadata: Any) -> "CoreModelStep":
        return cls(step_type="tool_calls", tool_calls=tuple(tool_calls), metadata=dict(metadata))

    @classmethod
    def delta(cls, content: str, **metadata: Any) -> "CoreModelStep":
        return cls(step_type="assistant_delta", content=content, metadata=dict(metadata))


@dataclass(frozen=True)
class AgentCoreRequest:
    message: str
    session_id: str
    project_key: str | None = None
    turn_id: str = field(default_factory=lambda: new_core_id("turn"))
    context: dict[str, Any] = field(default_factory=dict)
    max_iterations: int = 6
    max_tool_calls: int = 12
    resume: CoreApprovalResume | None = None
    approved_call_ids: tuple[str, ...] = ()
    approval_policy: Literal["frozen", "enabled"] = "frozen"


@dataclass(frozen=True)
class AgentCoreRunResult:
    session_id: str
    turn_id: str
    events: tuple[CoreEvent, ...]
    final_answer: str
    tool_results: tuple[CoreToolResult, ...] = ()
    permission_request: CorePermissionRequest | None = None
    stop_reason: str = "final_answer"

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "events": [event.to_dict() for event in self.events],
            "final_answer": self.final_answer,
            "tool_results": [result.to_dict() for result in self.tool_results],
            "permission_request": self.permission_request.to_dict() if self.permission_request else None,
            "stop_reason": self.stop_reason,
        }


class CoreProvider(Protocol):
    def next_step(
        self,
        *,
        request: AgentCoreRequest,
        tools: list[CoreToolSpec],
        transcript: list[dict[str, Any]],
        remaining_budget: dict[str, Any],
    ) -> CoreModelStep:
        ...


class CoreToolExecutor(Protocol):
    def execute_tool(
        self,
        *,
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        ...
