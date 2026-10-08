from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import TYPE_CHECKING, Any

from .capability_registry import list_interactive_agent_capabilities
from .external_tool_status import list_external_service_statuses
from .tool_contract import build_tool_definition

if TYPE_CHECKING:
    from app.services.agent_sessions.service import AgentSessionService

CORE_PRESENTATION_EXCEPTIONS = {
    "ingest.url_pool.submit",
    "source.candidate.review",
}

FEATURE_FLAGGED_TOOL_IDS = {
    "agent_batch.submit": "agent_batch_as_tool_enabled",
}

@dataclass(frozen=True)
class ToolPoolRequest:
    project_key: str | None = None
    user: str | None = None
    permissions: tuple[str, ...] = ()
    agent_mode: str = "read_only"
    feature_flags: dict[str, bool] = field(default_factory=dict)


def default_agent_runtime_feature_flags() -> dict[str, bool]:
    try:
        from app.settings.config import settings

        return {
            "agent_stream_enabled": bool(getattr(settings, "agent_stream_enabled", True)),
            "agent_batch_as_tool_enabled": bool(getattr(settings, "agent_batch_as_tool_enabled", True)),
        }
    except Exception:  # noqa: BLE001
        return {
            "agent_stream_enabled": True,
            "agent_batch_as_tool_enabled": True,
        }


def _risk_level(capability: dict[str, Any]) -> str:
    approval_level = str(capability.get("approval_level") or "none")
    risks = list(capability.get("risks") or [])
    if approval_level in {"high", "explicit_user_request"}:
        return "high"
    if approval_level == "medium" or risks:
        return "medium"
    return "low"


def _tool_group(capability: dict[str, Any]) -> str:
    if capability.get("tool_group"):
        return str(capability.get("tool_group"))
    if capability.get("capability_id") in CORE_PRESENTATION_EXCEPTIONS:
        return "core"
    if capability.get("approval_level") == "none" and capability.get("concurrency_class") == "read_only":
        return "core"
    return "deferred"


def _search_text(tool: dict[str, Any]) -> str:
    return json.dumps(
        {
            "capability_id": tool.get("capability_id"),
            "name": tool.get("name"),
            "description": tool.get("description"),
            "domain": tool.get("domain"),
            "required_input": tool.get("required_input"),
            "risks": tool.get("risks"),
            "entrypoints": tool.get("entrypoints"),
            "approval_level": tool.get("approval_level"),
            "concurrency_class": tool.get("concurrency_class"),
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    ).lower()


def _query_tokens(query: str) -> list[str]:
    stop_words = {
        "搜索",
        "查找",
        "匹配",
        "工具",
        "能力",
        "tool",
        "tools",
        "search",
        "find",
        "lookup",
    }
    return [
        token
        for token in str(query or "").lower().replace("，", " ").replace(",", " ").split()
        if token and token not in stop_words
    ]


class AgentToolPoolAssembler:
    """Project-aware tool catalogue for model planning and user-facing discovery."""

    def __init__(self, *, service: AgentSessionService | None = None) -> None:
        self._service = service

    def assemble(self, request: ToolPoolRequest | None = None) -> dict[str, Any]:
        resolved_request = request or ToolPoolRequest()
        flags = {**default_agent_runtime_feature_flags(), **dict(resolved_request.feature_flags or {})}
        tools: list[dict[str, Any]] = []
        capabilities = [
            *_registered_core_tool_capabilities(self._service),
            *list_interactive_agent_capabilities(),
            *_external_mcp_service_capabilities(),
        ]
        seen_capability_ids: set[str] = set()
        for capability in capabilities:
            capability_id = str(capability.get("capability_id") or "")
            if not capability_id or capability_id in seen_capability_ids:
                continue
            seen_capability_ids.add(capability_id)
            item = self._capability_to_tool(capability, request=resolved_request, feature_flags=flags)
            tools.append(item)

        groups: dict[str, list[dict[str, Any]]] = {"core": [], "deferred": [], "disabled": []}
        for tool in tools:
            group = "disabled" if not tool.get("enabled", True) else str(tool.get("tool_group") or "deferred")
            groups.setdefault(group, []).append(tool)

        return {
            "project_key": resolved_request.project_key,
            "agent_mode": resolved_request.agent_mode,
            "feature_flags": flags,
            "tools": tools,
            "groups": groups,
            "counts": {
                "total": len(tools),
                "core": len(groups.get("core") or []),
                "deferred": len(groups.get("deferred") or []),
                "disabled": len(groups.get("disabled") or []),
                "approval_required": sum(1 for tool in tools if str(tool.get("approval_level") or "none") != "none"),
            },
        }

    def search(self, *, query: str, request: ToolPoolRequest | None = None, limit: int = 12) -> dict[str, Any]:
        pool = self.assemble(request)
        tokens = _query_tokens(query)
        matches: list[dict[str, Any]] = []
        for tool in list(pool.get("tools") or []):
            haystack = _search_text(tool)
            if not tokens or any(token in haystack for token in tokens):
                matches.append(tool)
        return {
            "query": query,
            "items": matches[: max(1, int(limit or 12))],
            "total": len(matches),
            "source_total": len(list(pool.get("tools") or [])),
            "feature_flags": dict(pool.get("feature_flags") or {}),
            "project_key": pool.get("project_key"),
        }

    def _capability_to_tool(
        self,
        capability: dict[str, Any],
        *,
        request: ToolPoolRequest,
        feature_flags: dict[str, bool],
    ) -> dict[str, Any]:
        capability_id = str(capability.get("capability_id") or "")
        flag_name = FEATURE_FLAGGED_TOOL_IDS.get(capability_id)
        enabled = bool(capability.get("enabled", True))
        disabled_reason = (
            str(capability.get("disabled_reason") or "") or None
        )
        if flag_name and not bool(feature_flags.get(flag_name, True)):
            enabled = False
            disabled_reason = f"feature flag {flag_name} is disabled"
        if capability_id == "agent_session.stream" and not bool(feature_flags.get("agent_stream_enabled", True)):
            enabled = False
            disabled_reason = "feature flag agent_stream_enabled is disabled"

        input_schema_value = capability.get("input_schema")
        input_schema = (
            dict(input_schema_value)
            if isinstance(input_schema_value, dict)
            else {
                "type": "object",
                "required": list(capability.get("required_input") or []),
                "properties": {
                    key: {"type": "string"}
                    for key in list(capability.get("required_input") or [])
                },
                "additionalProperties": True,
            }
        )
        tool_definition = build_tool_definition(
            name=capability_id,
            capability_id=capability_id,
            description=str(capability.get("description") or capability.get("name") or capability_id),
            input_schema=input_schema,
            output_schema=(
                dict(capability["output_schema"])
                if isinstance(capability.get("output_schema"), dict)
                else None
            ),
            risk_level=str(capability.get("risk_level") or _risk_level(capability)),
            concurrency_class=str(capability.get("concurrency_class") or "read_only"),
            approval_level=str(capability.get("approval_level") or "none"),
            timeout_seconds=int(capability.get("timeout_seconds") or 10),
            result_budget=int(capability.get("result_budget") or 4000),
        )
        group = _tool_group(capability)
        implemented = bool(capability.get("implemented"))
        implementation_state = str(capability.get("implementation_state") or ("implemented" if implemented else "not_mounted"))
        if implementation_state == "implemented" and not implemented:
            implementation_state = "not_mounted"
        return {
            **tool_definition,
            "name": capability.get("name") or capability_id,
            "tool_name": capability_id,
            "capability_id": capability_id,
            "domain": capability.get("domain"),
            "call_pattern": capability.get("call_pattern"),
            "required_input": list(capability.get("required_input") or []),
            "risks": list(capability.get("risks") or []),
            "entrypoints": list(capability.get("entrypoints") or []),
            "tool_group": group,
            "deferred": group == "deferred",
            "implemented": implemented,
            "implementation_state": implementation_state,
            "enabled": enabled,
            "disabled_reason": disabled_reason,
            "configured": capability.get("configured"),
            "reachable": capability.get("reachable"),
            "auth_ok": capability.get("auth_ok"),
            "server_error": capability.get("server_error"),
            "service_status": capability.get("service_status"),
            "mounted_tool_count": capability.get("mounted_tool_count"),
            "mounted_tools": capability.get("mounted_tools"),
            "project_key": request.project_key,
            "permission_state": "available" if enabled else "disabled",
            "loading_hint": (
                "core"
                if group == "core"
                else "implemented but governed by explicit model selection or approval"
                if implemented
                else "registered in catalogue but not mounted in AgentCore"
            ),
        }


def _registered_core_tool_capabilities(
    service: AgentSessionService | None,
) -> list[dict[str, Any]]:
    """Project registered Core tools into the existing discovery envelope.

    ``CoreToolRegistry.register`` accepts a spec and its handler together, so a
    spec returned by ``list_specs`` represents a mounted handler rather than a
    declaration of intended future support.
    """

    from app.services.agent_core.project_tools import build_project_core_tool_registry
    from app.services.agent_sessions.service import get_agent_session_service

    resolved_service = service if service is not None else get_agent_session_service()
    registry = build_project_core_tool_registry(service=resolved_service)
    capabilities: list[dict[str, Any]] = []
    for spec in registry.list_specs():
        metadata = dict(spec.metadata or {})
        legacy_value = metadata.get("legacy_tool_definition")
        legacy = dict(legacy_value) if isinstance(legacy_value, dict) else {}
        required_value = spec.input_schema.get("required")
        required = (
            [str(item) for item in required_value]
            if isinstance(required_value, list)
            else []
        )
        approval_level = {
            "allow": "none",
            "ask": "high",
            "deny": "high",
            "explicit_user_request": "explicit_user_request",
        }[spec.permission]
        concurrency_class = (
            "write_external" if spec.risk == "privileged" else spec.risk
        )
        risks_value = legacy.get("risks")
        risks = (
            [str(item) for item in risks_value]
            if isinstance(risks_value, list)
            else ([] if spec.risk == "read_only" else [spec.risk])
        )
        domain = str(
            legacy.get("domain")
            or metadata.get("domain")
            or spec.project_service_id
            or spec.name.split(".", 1)[0]
        )
        capabilities.append(
            {
                "capability_id": spec.name,
                "name": spec.title or spec.name,
                "description": spec.description_for_model,
                "domain": domain,
                "call_pattern": str(
                    legacy.get("call_pattern")
                    or metadata.get("call_pattern")
                    or "sync"
                ),
                "approval_level": approval_level,
                "concurrency_class": concurrency_class,
                "entrypoints": [
                    {"type": "agent_core_tool", "id": spec.name}
                ],
                "required_input": required,
                "risks": risks,
                "input_schema": dict(spec.input_schema or {}),
                "output_schema": dict(spec.output_schema or {}),
                "risk_level": {
                    "read_only": "low",
                    "write_shared": "medium",
                    "write_external": "high",
                    "privileged": "high",
                }[spec.risk],
                "timeout_seconds": spec.timeout_seconds,
                "result_budget": spec.result_budget,
                "implemented": True,
                "implementation_state": "implemented",
                "enabled": spec.permission != "deny",
                "disabled_reason": (
                    "CoreToolSpec permission denies this tool"
                    if spec.permission == "deny"
                    else None
                ),
                "tool_group": metadata.get("tool_group"),
                "core_source": spec.source,
                "core_concurrency": spec.concurrency,
            }
        )
    return capabilities


def _external_mcp_service_capabilities() -> list[dict[str, Any]]:
    capabilities: list[dict[str, Any]] = []
    for service in list_external_service_statuses():
        if str(service.get("fit") or "") != "external_mcp":
            continue
        service_id = str(service.get("service_id") or "").strip()
        if not service_id:
            continue
        capabilities.append(
            {
                "capability_id": f"mcp.service.{service_id}",
                "name": f"MCP service: {service_id}",
                "description": str(service.get("reason") or f"{service_id} external MCP service"),
                "domain": "mcp",
                "call_pattern": "sync",
                "approval_level": "none",
                "concurrency_class": "read_only",
                "entrypoints": [{"type": "mcp_service", "id": service_id}],
                "required_input": [],
                "risks": [],
                "tool_group": "core" if service.get("enabled") else "disabled",
                "implemented": bool(service.get("implemented")),
                "implementation_state": service.get("implementation_state"),
                "enabled": bool(service.get("enabled")),
                "disabled_reason": service.get("reason"),
                "configured": service.get("configured"),
                "reachable": service.get("reachable"),
                "auth_ok": service.get("auth_ok"),
                "server_error": service.get("server_error"),
                "service_status": service.get("status"),
                "mounted_tool_count": service.get("mounted_tool_count"),
                "mounted_tools": service.get("mounted_tools"),
            }
        )
    return capabilities
