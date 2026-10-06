from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, TypeGuard
from uuid import uuid4

from app.contracts.json import JSONObject as JSONObject, JSONValue as JSONValue


CoreEventType = Literal["tool_progress"]
ToolRisk = Literal["read_only", "write_shared", "write_external", "privileged"]
ToolPermission = Literal["allow", "ask", "deny", "explicit_user_request"]
ToolConcurrency = Literal["parallel", "serial", "exclusive"]
ToolSource = Literal["builtin", "project", "skill", "mcp", "legacy_adapter"]
ToolStatus = Literal["completed", "failed", "canceled", "needs_approval", "deferred"]
AGENT_CORE_TOOL_CALL_CONTRACT_VERSION = "agent_core.tool_call_shape.v1"
CORE_TOOL_CALL_REQUIRED_KEYS = ("call_id", "tool_name", "arguments", "reason")


def _is_json_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _is_json_sequence(value: object) -> TypeGuard[Sequence[object]]:
    return isinstance(value, (list, tuple))


def _json_text(value: object) -> str:
    return str(value or "").strip()


def compact_json_value(
    value: object,
    *,
    max_items: int = 30,
    max_depth: int = 5,
    max_string: int = 500,
) -> JSONValue:
    """Project an arbitrary result into bounded model-visible JSON."""

    if max_depth <= 0:
        if _is_json_mapping(value) or _is_json_sequence(value):
            return "[truncated]"
        if value is None or isinstance(value, (str, bool, int, float)):
            return value
        return str(value)
    if _is_json_mapping(value):
        compacted_object: dict[str, JSONValue] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= max_items:
                compacted_object["_truncated"] = True
                compacted_object["_omitted_count"] = max(0, len(value) - max_items)
                break
            compacted_object[_json_text(key)] = compact_json_value(
                item,
                max_items=max_items,
                max_depth=max_depth - 1,
                max_string=max_string,
            )
        return compacted_object
    if _is_json_sequence(value):
        items = list(value)
        compacted_sequence: list[JSONValue] = [
            compact_json_value(
                item,
                max_items=max_items,
                max_depth=max_depth - 1,
                max_string=max_string,
            )
            for item in items[:max_items]
        ]
        if len(items) > max_items:
            compacted_sequence.append(
                {"_truncated": True, "_omitted_count": len(items) - max_items}
            )
        return compacted_sequence
    if isinstance(value, str):
        return value[:max_string] + "..." if len(value) > max_string else value
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def _json_value(value: object) -> JSONValue:
    """Normalize JSON without the bounded result projection used above."""

    if _is_json_mapping(value):
        return {str(key): _json_value(item) for key, item in value.items()}
    if _is_json_sequence(value):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    return str(value)


def json_object(value: object) -> JSONObject:
    normalized = _json_value(value)
    if not isinstance(normalized, Mapping):
        return {}
    return {str(key): item for key, item in normalized.items()}


def json_list(value: object) -> list[JSONValue]:
    normalized = _json_value(value)
    if isinstance(normalized, Sequence) and not isinstance(normalized, str):
        return list(normalized)
    return []


def json_strings(values: Sequence[str]) -> list[JSONValue]:
    return list[JSONValue](values)


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_core_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:16]}"


@dataclass(frozen=True)
class CoreEvent:
    event_type: CoreEventType
    session_id: str
    payload: JSONObject = field(default_factory=lambda: {})
    event_id: str = field(default_factory=lambda: new_core_id("evt"))
    turn_id: str | None = None
    call_id: str | None = None
    actor: str = "agent_core"
    created_at: str = field(default_factory=utcnow_iso)
    version: int = 1

    def to_dict(self) -> JSONObject:
        out: JSONObject = {
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
    input_schema: JSONObject = field(default_factory=lambda: {"type": "object", "properties": {}})
    output_schema: JSONObject = field(default_factory=lambda: {"type": "object", "additionalProperties": True})
    source: ToolSource = "project"
    risk: ToolRisk = "read_only"
    permission: ToolPermission = "allow"
    concurrency: ToolConcurrency = "parallel"
    timeout_seconds: int = 10
    result_budget: int = 4000
    mcp_server: str | None = None
    skill_id: str | None = None
    project_service_id: str | None = None
    metadata: JSONObject = field(default_factory=lambda: {})

    def to_model_tool(self) -> JSONObject:
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

    def to_dict(self) -> JSONObject:
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
    arguments: JSONObject = field(default_factory=lambda: {})
    call_id: str = field(default_factory=lambda: new_core_id("call"))
    reason: str | None = None

    def to_dict(self) -> JSONObject:
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
) -> JSONObject:
    """Return the stable model-to-runtime tool-call shape used by provider gates."""

    payload = tool_call.to_dict()
    missing = [key for key in CORE_TOOL_CALL_REQUIRED_KEYS if key not in payload]
    arguments_value = payload.get("arguments")
    arguments = dict(arguments_value) if isinstance(arguments_value, Mapping) else {}
    return {
        "contract_version": AGENT_CORE_TOOL_CALL_CONTRACT_VERSION,
        "provider_key": provider_key,
        "required_keys": list(CORE_TOOL_CALL_REQUIRED_KEYS),
        "present_keys": sorted(payload),
        "missing_keys": missing,
        "call_id": str(payload.get("call_id") or ""),
        "tool_name": str(payload.get("tool_name") or ""),
        "arguments_type": "object" if isinstance(arguments_value, Mapping) else type(arguments_value).__name__,
        "arguments": arguments,
        "reason_present": bool(str(payload.get("reason") or "").strip()),
        "shape_status": "valid"
        if not missing
        and bool(str(payload.get("call_id") or "").strip())
        and bool(str(payload.get("tool_name") or "").strip())
        and isinstance(arguments_value, Mapping)
        else "invalid",
    }


@dataclass(frozen=True)
class CoreToolResult:
    call_id: str
    tool_name: str
    status: ToolStatus
    model_summary: str
    ui_summary: str | None = None
    structured_content: JSONObject = field(default_factory=lambda: {})
    artifact_refs: tuple[str, ...] = ()
    error: JSONObject | None = None
    retry_hint: str | None = None

    def to_dict(self) -> JSONObject:
        out: JSONObject = {
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
    context: JSONObject = field(default_factory=lambda: {})
