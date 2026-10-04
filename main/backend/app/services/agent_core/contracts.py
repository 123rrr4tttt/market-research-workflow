from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4


CoreEventType = Literal["tool_progress"]
ToolRisk = Literal["read_only", "write_shared", "write_external", "privileged"]
ToolPermission = Literal["allow", "ask", "deny", "explicit_user_request"]
ToolConcurrency = Literal["parallel", "serial", "exclusive"]
ToolSource = Literal["builtin", "project", "skill", "mcp", "legacy_adapter"]
ToolStatus = Literal["completed", "failed", "canceled", "needs_approval", "deferred"]
AGENT_CORE_TOOL_CALL_CONTRACT_VERSION = "agent_core.tool_call_shape.v1"
CORE_TOOL_CALL_REQUIRED_KEYS = ("call_id", "tool_name", "arguments", "reason")


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


def core_tool_call_contract_shape(
    tool_call: CoreToolCall,
    *,
    provider_key: str | None = None,
) -> dict[str, Any]:
    """Return the stable model-to-runtime tool-call shape used by provider gates."""

    payload = tool_call.to_dict()
    missing = [key for key in CORE_TOOL_CALL_REQUIRED_KEYS if key not in payload]
    return {
        "contract_version": AGENT_CORE_TOOL_CALL_CONTRACT_VERSION,
        "provider_key": provider_key,
        "required_keys": list(CORE_TOOL_CALL_REQUIRED_KEYS),
        "present_keys": sorted(payload),
        "missing_keys": missing,
        "call_id": str(payload.get("call_id") or ""),
        "tool_name": str(payload.get("tool_name") or ""),
        "arguments_type": "object" if isinstance(payload.get("arguments"), dict) else type(payload.get("arguments")).__name__,
        "arguments": dict(payload.get("arguments") or {}) if isinstance(payload.get("arguments"), dict) else {},
        "reason_present": bool(str(payload.get("reason") or "").strip()),
        "shape_status": "valid"
        if not missing
        and bool(str(payload.get("call_id") or "").strip())
        and bool(str(payload.get("tool_name") or "").strip())
        and isinstance(payload.get("arguments"), dict)
        else "invalid",
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
class AgentCoreRequest:
    message: str
    session_id: str
    project_key: str | None = None
    turn_id: str = field(default_factory=lambda: new_core_id("turn"))
    context: dict[str, Any] = field(default_factory=dict)
