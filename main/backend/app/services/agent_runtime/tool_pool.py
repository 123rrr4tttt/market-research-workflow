from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any

from .capability_registry import list_interactive_agent_capabilities
from .external_tool_status import list_external_service_statuses
from .tool_contract import build_tool_definition


CORE_TOOL_IDS = {
    "agent_runtime.capability.catalog",
    "agent_runtime.tool_pool.list",
    "agent_runtime.tool.search",
    "agent_session.context.read",
    "agent_session.resume_bundle",
    "agent_long_task.stage.update",
    "agent_long_task.stage.read",
    "project.summary.read",
    "project.structured_data.search",
    "project.context.bundle",
    "project.graph.search",
    "project.structured_graph.query",
    "agent_artifact.search",
    "agent_artifact.read",
    "source.discovery.plan",
    "source.web.search",
    "source.candidate.review",
    "ingest.url_pool.submit",
    "ingest.url_pool.status",
    "source.history.read",
    "agent_investigation.trace.read",
    "writing.document.list",
    "writing.document.read",
    "source_library.item.list",
    "source_library.item.search",
    "source_library.item.inspect",
    "workflow_graph.list",
    "workflow_graph.inspect",
    "ingest.status.read",
    "agent_session.stream",
    "skill.search",
    "skill.load",
    "mcp.service.catalog",
    "mcp.tools.list",
    "mcp.tool.call",
}

FEATURE_FLAGGED_TOOL_IDS = {
    "agent_batch.nl_command.submit": "agent_batch_as_tool_enabled",
    "agent_batch.submit": "agent_batch_as_tool_enabled",
}

IMPLEMENTED_TOOL_IDS = CORE_TOOL_IDS | {
    "agent_batch.nl_command.submit",
    "agent_batch.submit",
    "agent_task.plan.append",
    "agent_investigation.leads.append",
    "writing.document.create",
    "writing.document.insert_paragraph",
    "writing.document.citations.upsert",
    "ingest.url_pool.submit",
    "ingest.url_pool.status",
    "source.history.read",
    "ingest.source_library.run",
    "workflow_graph.run",
    "report.generate",
    "task.cancel",
    "task.retry",
    "task.continue",
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
            "agent_runtime_v2_enabled": bool(getattr(settings, "agent_runtime_v2_enabled", True)),
            "agent_stream_enabled": bool(getattr(settings, "agent_stream_enabled", True)),
            "agent_batch_as_tool_enabled": bool(getattr(settings, "agent_batch_as_tool_enabled", True)),
        }
    except Exception:  # noqa: BLE001
        return {
            "agent_runtime_v2_enabled": True,
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
    if capability.get("capability_id") in CORE_TOOL_IDS:
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

    def assemble(self, request: ToolPoolRequest | None = None) -> dict[str, Any]:
        resolved_request = request or ToolPoolRequest()
        flags = {**default_agent_runtime_feature_flags(), **dict(resolved_request.feature_flags or {})}
        tools: list[dict[str, Any]] = []
        capabilities = [*list_interactive_agent_capabilities(), *_agent_core_standard_capabilities(), *_external_mcp_service_capabilities()]
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
        enabled = True
        disabled_reason = None
        if flag_name and not bool(feature_flags.get(flag_name, True)):
            enabled = False
            disabled_reason = f"feature flag {flag_name} is disabled"
        if capability_id == "agent_session.stream" and not bool(feature_flags.get("agent_stream_enabled", True)):
            enabled = False
            disabled_reason = "feature flag agent_stream_enabled is disabled"

        input_schema = {
            "type": "object",
            "required": list(capability.get("required_input") or []),
            "properties": {key: {"type": "string"} for key in list(capability.get("required_input") or [])},
            "additionalProperties": True,
        }
        tool_definition = build_tool_definition(
            name=capability_id,
            capability_id=capability_id,
            description=str(capability.get("description") or capability.get("name") or capability_id),
            input_schema=input_schema,
            risk_level=_risk_level(capability),
            concurrency_class=str(capability.get("concurrency_class") or "read_only"),
            approval_level=str(capability.get("approval_level") or "none"),
        )
        group = _tool_group(capability)
        implemented = capability_id in IMPLEMENTED_TOOL_IDS
        if "implemented" in capability:
            implemented = bool(capability.get("implemented"))
        implementation_state = str(capability.get("implementation_state") or ("implemented" if implemented else "not_mounted"))
        if implementation_state == "implemented" and not implemented:
            implementation_state = "not_mounted"
        if "enabled" in capability:
            enabled = bool(capability.get("enabled"))
        if capability.get("disabled_reason"):
            disabled_reason = str(capability.get("disabled_reason") or "")
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


def _agent_core_standard_capabilities() -> list[dict[str, Any]]:
    return [
        {
            "capability_id": "agent_batch.submit",
            "name": "Agent batch submit",
            "description": "Submit governed background agent_batch work from a command or structured jobs.",
            "domain": "agent_batch",
            "call_pattern": "async",
            "approval_level": "high",
            "concurrency_class": "write_external",
            "entrypoints": [{"type": "agent_core_tool", "id": "agent_batch.submit"}],
            "required_input": ["command|jobs", "project_key"],
            "risks": ["external_collection", "cost", "data_mutation"],
        },
        {
            "capability_id": "agent_session.resume_bundle",
            "name": "Agent session resume bundle",
            "description": "Read compact session memory, recent tasks, events, artifacts, and pending approvals for follow-up turns.",
            "domain": "agent_sessions",
            "call_pattern": "sync",
            "approval_level": "none",
            "concurrency_class": "read_only",
            "entrypoints": [{"type": "agent_core_tool", "id": "agent_session.resume_bundle"}],
            "required_input": ["session_id"],
            "risks": [],
        },
        {
            "capability_id": "source.discovery.plan",
            "name": "Source discovery plan",
            "description": "Plan trustworthy source directions and candidate URLs without external I/O or ingestion side effects.",
            "domain": "source_library",
            "call_pattern": "sync",
            "approval_level": "none",
            "concurrency_class": "read_only",
            "entrypoints": [{"type": "agent_core_tool", "id": "source.discovery.plan"}],
            "required_input": ["topic"],
            "risks": [],
        },
        {
            "capability_id": "source.web.search",
            "name": "External source candidate search",
            "description": "Search external providers for candidate titles, URLs, snippets, and trust labels without article fetch, ingest, or project writes.",
            "domain": "source_library",
            "call_pattern": "sync",
            "approval_level": "none",
            "concurrency_class": "read_only",
            "entrypoints": [{"type": "agent_core_tool", "id": "source.web.search"}],
            "required_input": ["query"],
            "risks": ["external_network_io"],
        },
        {
            "capability_id": "source.candidate.review",
            "name": "Source candidate review",
            "description": "Record approve, defer, or reject decisions for searched source candidates and return a concrete source-library or URL-pool ingest payload.",
            "domain": "source_library",
            "call_pattern": "sync",
            "approval_level": "none",
            "concurrency_class": "write_shared",
            "entrypoints": [{"type": "agent_core_tool", "id": "source.candidate.review"}],
            "required_input": ["decision", "candidate"],
            "risks": ["session_artifact_write", "candidate_review_boundary"],
        },
        {
            "capability_id": "ingest.url_pool.submit",
            "name": "URL-pool ingest submit",
            "description": "Submit an approved external URL candidate to the existing URL-pool/source-library ingestion frontdoor and return the queued task boundary.",
            "domain": "source_library",
            "call_pattern": "async",
            "approval_level": "none",
            "concurrency_class": "write_external",
            "entrypoints": [{"type": "agent_core_tool", "id": "ingest.url_pool.submit"}],
            "required_input": ["url", "project_key"],
            "risks": ["external_collection", "project_data_mutation", "queued_ingest_task"],
        },
        {
            "capability_id": "ingest.url_pool.status",
            "name": "URL-pool ingest status",
            "description": "Read URL-pool submission status and check whether stored project documents or sources now contain verified evidence for the submitted URL.",
            "domain": "source_library",
            "call_pattern": "sync",
            "approval_level": "none",
            "concurrency_class": "read_only",
            "entrypoints": [{"type": "agent_core_tool", "id": "ingest.url_pool.status"}],
            "required_input": ["project_key"],
            "risks": [],
        },
        {
            "capability_id": "source.history.read",
            "name": "Source candidate history",
            "description": "Read recent source candidate reviews and URL-pool submissions from the current session and optionally same-project recent sessions.",
            "domain": "source_library",
            "call_pattern": "sync",
            "approval_level": "none",
            "concurrency_class": "read_only",
            "entrypoints": [{"type": "agent_core_tool", "id": "source.history.read"}],
            "required_input": ["project_key"],
            "risks": [],
        },
        {
            "capability_id": "agent_investigation.trace.read",
            "name": "Investigation trace reader",
            "description": "Read a bounded multi-hop investigation trace from session artifacts for follow-up research or writing.",
            "domain": "agent_sessions",
            "call_pattern": "sync",
            "approval_level": "none",
            "concurrency_class": "read_only",
            "entrypoints": [{"type": "agent_core_tool", "id": "agent_investigation.trace.read"}],
            "required_input": ["session_id"],
            "risks": [],
        },
        {
            "capability_id": "agent_task.plan.append",
            "name": "Session task planner",
            "description": "Append resumable task plan items to the current session for long-running work.",
            "domain": "agent_sessions",
            "call_pattern": "sync",
            "approval_level": "none",
            "concurrency_class": "write_shared",
            "entrypoints": [{"type": "agent_core_tool", "id": "agent_task.plan.append"}],
            "required_input": ["tasks"],
            "risks": ["session_state_mutation"],
        },
        {
            "capability_id": "agent_long_task.stage.update",
            "name": "Long task stage updater",
            "description": "Persist durable long writing/investigation stage state for page-switch and hard-refresh recovery.",
            "domain": "agent_sessions",
            "call_pattern": "sync",
            "approval_level": "none",
            "concurrency_class": "write_shared",
            "entrypoints": [{"type": "agent_core_tool", "id": "agent_long_task.stage.update"}],
            "required_input": ["stage"],
            "risks": ["session_state_mutation"],
        },
        {
            "capability_id": "agent_long_task.stage.read",
            "name": "Long task stage reader",
            "description": "Read durable long writing/investigation stage state before continuing after page switch or refresh.",
            "domain": "agent_sessions",
            "call_pattern": "sync",
            "approval_level": "none",
            "concurrency_class": "read_only",
            "entrypoints": [{"type": "agent_core_tool", "id": "agent_long_task.stage.read"}],
            "required_input": ["session_id"],
            "risks": [],
        },
        {
            "capability_id": "agent_investigation.leads.append",
            "name": "Investigation lead recorder",
            "description": "Append clue nodes, edges, pending questions, followed leads, and citations to the session investigation state.",
            "domain": "agent_sessions",
            "call_pattern": "sync",
            "approval_level": "none",
            "concurrency_class": "write_shared",
            "entrypoints": [{"type": "agent_core_tool", "id": "agent_investigation.leads.append"}],
            "required_input": ["session_id"],
            "risks": ["session_state_mutation"],
        },
        {
            "capability_id": "writing.document.list",
            "name": "Writing document list",
            "description": "List writing workbench documents for the current project before choosing a draft to read or edit.",
            "domain": "writing",
            "call_pattern": "sync",
            "approval_level": "none",
            "concurrency_class": "read_only",
            "entrypoints": [{"type": "agent_core_tool", "id": "writing.document.list"}],
            "required_input": ["project_key"],
            "risks": [],
        },
        {
            "capability_id": "writing.document.read",
            "name": "Writing document read",
            "description": "Read a writing workbench document with markdown body, version, etag, and block anchors for precise canvas edits.",
            "domain": "writing",
            "call_pattern": "sync",
            "approval_level": "none",
            "concurrency_class": "read_only",
            "entrypoints": [{"type": "agent_core_tool", "id": "writing.document.read"}],
            "required_input": ["doc_id"],
            "risks": [],
        },
        {
            "capability_id": "writing.document.create",
            "name": "Writing document create",
            "description": "Create/register a formal writing workbench document from a title and markdown body.",
            "domain": "writing",
            "call_pattern": "sync",
            "approval_level": "high",
            "concurrency_class": "write_shared",
            "entrypoints": [{"type": "agent_core_tool", "id": "writing.document.create"}],
            "required_input": ["title"],
            "risks": ["document_mutation"],
        },
        {
            "capability_id": "writing.document.insert_paragraph",
            "name": "Writing document paragraph insert",
            "description": "Insert or append model-produced prose into a writing workbench draft behind the AgentCore write boundary.",
            "domain": "writing",
            "call_pattern": "sync",
            "approval_level": "high",
            "concurrency_class": "write_shared",
            "entrypoints": [{"type": "agent_core_tool", "id": "writing.document.insert_paragraph"}],
            "required_input": ["content_md"],
            "risks": ["document_mutation"],
        },
        {
            "capability_id": "writing.document.citations.upsert",
            "name": "Writing document citation attach",
            "description": "Attach material-card citations to the formal writing workbench citation table for a document.",
            "domain": "writing",
            "call_pattern": "sync",
            "approval_level": "high",
            "concurrency_class": "write_shared",
            "entrypoints": [{"type": "agent_core_tool", "id": "writing.document.citations.upsert"}],
            "required_input": ["doc_id"],
            "risks": ["document_mutation", "citation_mutation"],
        },
        {
            "capability_id": "skill.search",
            "name": "Skill search",
            "description": "Search backend skills available to AgentCore.",
            "domain": "skills",
            "call_pattern": "sync",
            "approval_level": "none",
            "concurrency_class": "read_only",
            "entrypoints": [{"type": "agent_core_tool", "id": "skill.search"}],
            "required_input": ["query"],
            "risks": [],
        },
        {
            "capability_id": "skill.load",
            "name": "Skill metadata loader",
            "description": "Load metadata for one backend skill without executing it.",
            "domain": "skills",
            "call_pattern": "sync",
            "approval_level": "none",
            "concurrency_class": "read_only",
            "entrypoints": [{"type": "agent_core_tool", "id": "skill.load"}],
            "required_input": ["skill_id"],
            "risks": [],
        },
        {
            "capability_id": "mcp.service.catalog",
            "name": "MCP service catalog",
            "description": "List MCP-suitable project service surfaces.",
            "domain": "mcp",
            "call_pattern": "sync",
            "approval_level": "none",
            "concurrency_class": "read_only",
            "entrypoints": [{"type": "agent_core_tool", "id": "mcp.service.catalog"}],
            "required_input": [],
            "risks": [],
        },
        {
            "capability_id": "mcp.tools.list",
            "name": "MCP tool list",
            "description": "List currently mounted MCP-compatible tools.",
            "domain": "mcp",
            "call_pattern": "sync",
            "approval_level": "none",
            "concurrency_class": "read_only",
            "entrypoints": [{"type": "agent_core_tool", "id": "mcp.tools.list"}],
            "required_input": [],
            "risks": [],
        },
        {
            "capability_id": "mcp.tool.call",
            "name": "MCP tool call",
            "description": "Call one mounted MCP-compatible tool or return a clear not-configured error.",
            "domain": "mcp",
            "call_pattern": "sync",
            "approval_level": "none",
            "concurrency_class": "read_only",
            "entrypoints": [{"type": "agent_core_tool", "id": "mcp.tool.call"}],
            "required_input": ["tool_name"],
            "risks": [],
        },
    ]
