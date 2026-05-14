from __future__ import annotations

from typing import Any


_DEFAULT_SERVICE_STATUS: tuple[dict[str, Any], ...] = (
    {
        "service_id": "project-database",
        "fit": "project_tool",
        "configured": True,
        "reachable": True,
        "auth_ok": True,
        "reason": "Low-latency project/session/source-library reads are already in-process project tools.",
    },
    {
        "service_id": "workflow-graph",
        "fit": "skill_orchestrator",
        "configured": True,
        "reachable": True,
        "auth_ok": True,
        "reason": "Workflow graph operations encode project policy and should remain skill-backed.",
    },
    {
        "service_id": "source-library-ingest",
        "fit": "skill_orchestrator",
        "configured": True,
        "reachable": True,
        "auth_ok": True,
        "reason": "Collection mutates project/external state and stays behind explicit tool-call, budget, and source-scope boundaries.",
    },
    {
        "service_id": "browser-playwright",
        "fit": "external_mcp",
        "configured": False,
        "reachable": False,
        "auth_ok": None,
        "reason": "Browser automation requires a concrete local MCP/browser server before it is executable.",
    },
    {
        "service_id": "external-search",
        "fit": "external_mcp",
        "configured": False,
        "reachable": False,
        "auth_ok": None,
        "reason": "External search is available as source-discovery planning until a concrete search MCP service is mounted.",
    },
)

_SERVICE_STATUS_OVERRIDES: dict[str, dict[str, Any]] = {}
_MOUNTED_MCP_TOOLS_BY_SERVICE: dict[str, set[str]] = {}


def register_external_service_state(
    *,
    service_id: str,
    fit: str | None = None,
    configured: bool | None = None,
    reachable: bool | None = None,
    auth_ok: bool | None = None,
    server_error: str | None = None,
    status: str | None = None,
    reason: str | None = None,
) -> None:
    normalized_service_id = _normalize_service_id(service_id)
    if not normalized_service_id:
        raise ValueError("service_id is required")
    override: dict[str, Any] = {"service_id": normalized_service_id}
    for key, value in {
        "fit": fit,
        "configured": configured,
        "reachable": reachable,
        "auth_ok": auth_ok,
        "server_error": server_error,
        "status": status,
        "reason": reason,
    }.items():
        if value is not None:
            override[key] = value
    _SERVICE_STATUS_OVERRIDES[normalized_service_id] = override


def clear_external_service_states() -> None:
    _SERVICE_STATUS_OVERRIDES.clear()


def mark_mcp_tool_mounted(*, service_id: str, tool_name: str) -> None:
    normalized_service_id = _normalize_service_id(service_id) or "project-internal-catalog"
    normalized_tool_name = str(tool_name or "").strip()
    if not normalized_tool_name:
        return
    _MOUNTED_MCP_TOOLS_BY_SERVICE.setdefault(normalized_service_id, set()).add(normalized_tool_name)


def clear_mounted_mcp_tools() -> None:
    _MOUNTED_MCP_TOOLS_BY_SERVICE.clear()


def list_external_service_statuses() -> list[dict[str, Any]]:
    defaults = {str(item["service_id"]): dict(item) for item in _DEFAULT_SERVICE_STATUS}
    default_order = [str(item["service_id"]) for item in _DEFAULT_SERVICE_STATUS]
    extra_ids = sorted((set(_SERVICE_STATUS_OVERRIDES) | set(_MOUNTED_MCP_TOOLS_BY_SERVICE)) - set(default_order))
    service_ids = [*default_order, *extra_ids]
    statuses = [
        _resolve_service_status(
            {**defaults.get(service_id, {"service_id": service_id, "fit": "external_mcp"}), **_SERVICE_STATUS_OVERRIDES.get(service_id, {})},
            mounted_tools=sorted(_MOUNTED_MCP_TOOLS_BY_SERVICE.get(service_id, set())),
        )
        for service_id in service_ids
    ]
    return statuses


def get_external_service_status(service_id: str | None) -> dict[str, Any] | None:
    normalized = _normalize_service_id(service_id)
    if not normalized:
        return None
    return next(
        (item for item in list_external_service_statuses() if item.get("service_id") == normalized),
        _resolve_service_status(
            {
                "service_id": normalized,
                "fit": "external_mcp",
                "configured": False,
                "reachable": False,
                "reason": f"{normalized} is not registered or mounted.",
            },
            mounted_tools=[],
        ),
    )


def _resolve_service_status(raw: dict[str, Any], *, mounted_tools: list[str]) -> dict[str, Any]:
    service_id = _normalize_service_id(raw.get("service_id"))
    fit = str(raw.get("fit") or "external_mcp").strip() or "external_mcp"
    mounted_tool_count = len(mounted_tools)
    configured = bool(raw.get("configured")) or mounted_tool_count > 0 or fit in {"project_tool", "skill_orchestrator"}
    reachable = raw.get("reachable")
    auth_ok = raw.get("auth_ok")
    server_error = str(raw.get("server_error") or "").strip()
    status = str(raw.get("status") or "").strip()
    if not status:
        if server_error:
            status = "server_error"
        elif auth_ok is False:
            status = "auth_failed"
        elif not configured:
            status = "not_configured"
        elif fit == "external_mcp" and mounted_tool_count == 0:
            status = "not_mounted"
        elif reachable is False:
            status = "unreachable"
        else:
            status = "available"
    implementation_state = _implementation_state_for_status(status)
    enabled = status == "available"
    return {
        **raw,
        "service_id": service_id,
        "fit": fit,
        "status": status,
        "implementation_state": implementation_state,
        "configured": configured,
        "mounted": mounted_tool_count > 0,
        "mounted_tool_count": mounted_tool_count,
        "mounted_tools": mounted_tools,
        "reachable": reachable if reachable is not None else enabled,
        "auth_ok": auth_ok if auth_ok is not None else (True if enabled else None),
        "server_error": server_error or None,
        "enabled": enabled,
        "implemented": enabled,
        "reason": str(raw.get("reason") or _default_reason_for_status(status, service_id)).strip(),
    }


def _implementation_state_for_status(status: str) -> str:
    if status == "available":
        return "implemented"
    if status in {"not_configured", "not_mounted", "auth_failed", "server_error", "unreachable"}:
        return status
    return "unavailable"


def _default_reason_for_status(status: str, service_id: str) -> str:
    if status == "not_configured":
        return f"{service_id} is known but not configured."
    if status == "not_mounted":
        return f"{service_id} is configured but has no mounted AgentCore tool."
    if status == "auth_failed":
        return f"{service_id} is configured but authentication is not valid."
    if status in {"server_error", "unreachable"}:
        return f"{service_id} is configured but not reachable."
    return f"{service_id} is available."


def _normalize_service_id(value: Any) -> str:
    return str(value or "").strip()
