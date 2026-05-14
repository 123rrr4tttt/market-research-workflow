from __future__ import annotations

from collections.abc import Callable
import json
import re
from typing import Any

from app.services.agent_sessions.service import AgentSessionService

from .capability_registry import list_interactive_agent_capabilities
from .material_ontology import (
    EXTERNAL_DISCOVERY,
    INTERNAL_EXISTING,
    INTERNAL_GENERATED,
    SOURCE_CATALOG,
    category_label,
    classify_material_intent,
)
from .structured_data_search import (
    build_structured_data_model_evidence_manifest,
    query_project_structured_data,
    read_project_context_resource,
    read_project_structured_data_item,
    read_project_structured_data_items,
)
from .tool_contract import READ_ONLY_TOOL_PROTOCOL, build_capability_call, build_tool_definition
from .tool_pool import AgentToolPoolAssembler, ToolPoolRequest, default_agent_runtime_feature_flags


SourceLibraryLister = Callable[[str | None], list[dict[str, Any]]]
StructuredDataSearcher = Callable[..., dict[str, Any]]


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _compact_source_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "item_key": item.get("item_key"),
        "name": item.get("name"),
        "channel_key": item.get("channel_key"),
        "enabled": item.get("enabled"),
        "item_type": item.get("item_type"),
        "scope": item.get("scope"),
        "managed_by": item.get("managed_by"),
        "description": item.get("description"),
        "tags": item.get("tags") if isinstance(item.get("tags"), list) else [],
    }


def _matches_query(item: dict[str, Any], query: str) -> bool:
    if not query:
        return True
    haystack = " ".join(
        _as_text(item.get(key)).lower()
        for key in ("item_key", "name", "channel_key", "item_type", "description", "managed_by")
    )
    tags = " ".join(_as_text(tag).lower() for tag in item.get("tags") or [])
    return query.lower() in f"{haystack} {tags}"


def _extract_source_item_key(command: str) -> str | None:
    for token in str(command or "").replace("，", " ").replace(",", " ").split():
        cleaned = token.strip("`'\"：:；;。()[]{}")
        if "." in cleaned and len(cleaned) >= 3:
            return cleaned
    return None


def _extract_graph_id(command: str) -> str | None:
    skip = {"workflow", "workflow_graph", "graph", "run", "运行", "执行", "查看", "检查", "inspect"}
    for token in str(command or "").replace("，", " ").replace(",", " ").split():
        cleaned = token.strip("`'\"：:；;。()[]{}")
        if not cleaned or cleaned.lower() in skip:
            continue
        if any(marker in cleaned.lower() for marker in ("graph", "workflow", "_")) or len(cleaned) >= 4:
            return cleaned
    return None


def _parse_structured_read_ref(
    *,
    dataset: Any | None = None,
    record_id: Any | None = None,
    item_id: Any | None = None,
    resource_uri: Any | None = None,
) -> tuple[str, str]:
    dataset_text = _as_text(dataset)
    record_text = _as_text(record_id)
    item_text = _as_text(item_id)
    uri_text = _as_text(resource_uri)
    if uri_text.startswith("project://structured/"):
        parts = uri_text.removeprefix("project://structured/").split("/", 2)
        if len(parts) == 3:
            dataset_text = dataset_text or parts[1]
            record_text = record_text or parts[2]
    if item_text.startswith("structured:"):
        parts = item_text.split(":", 2)
        if len(parts) == 3:
            dataset_text = dataset_text or parts[1]
            record_text = record_text or parts[2]
    return dataset_text, record_text


def _query_tokens(query: str) -> list[str]:
    tokens = [
        token.strip().lower()
        for token in re.split(r"[\s,，。；;:：/|()（）\[\]{}]+", str(query or ""))
        if token.strip()
    ]
    return [token for token in tokens if len(token) >= 2]


def _compact_workflow_graph(record: dict[str, Any]) -> dict[str, Any]:
    nodes = dict(record.get("nodes") or {})
    return {
        "graph_id": record.get("graph_id"),
        "version": record.get("version"),
        "checksum": record.get("checksum"),
        "node_count": len(nodes),
        "topo_order": list(record.get("topo_order") or [])[:20],
        "input_keys": sorted({key for node in nodes.values() for key in dict(node.get("params") or {}).keys()})[:20],
    }


class ReadOnlyAgentToolRuntime:
    """Read-only tools that can answer fast chat turns without agent_batch."""

    def __init__(
        self,
        *,
        service: AgentSessionService,
        source_library_lister: SourceLibraryLister | None = None,
        structured_data_searcher: StructuredDataSearcher | None = None,
    ) -> None:
        self.service = service
        self.source_library_lister = source_library_lister
        self.structured_data_searcher = structured_data_searcher or query_project_structured_data

    def supported_tool_names(self) -> set[str]:
        return {str(item["name"]) for item in self.list_tool_definitions()}

    def list_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            build_tool_definition(
                name="agent_runtime.capability.catalog",
                capability_id="agent_runtime.capability.catalog",
                description="List available agent capabilities and risk metadata.",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            ),
            build_tool_definition(
                name="agent_runtime.tool_pool.list",
                capability_id="agent_runtime.tool_pool.list",
                description="List the dynamically assembled tool pool grouped by core, deferred, disabled, and approval-required tools.",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            ),
            build_tool_definition(
                name="agent_runtime.tool.search",
                capability_id="agent_runtime.tool.search",
                description="Search the full agent tool pool and lazily discover tools by name, domain, risk, or description.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                    },
                    "additionalProperties": False,
                },
            ),
            build_tool_definition(
                name="agent_session.context.read",
                capability_id="agent_session.context.read",
                description="Read the current agent session ledger, messages, tasks, events, artifacts, and approvals.",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            ),
            build_tool_definition(
                name="project.summary.read",
                capability_id="project.summary.read",
                description="Read the local project database and summarize project-scoped data, source-library coverage, and session counters without mutating state.",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            ),
            build_tool_definition(
                name="project.structured_data.search",
                capability_id="project.structured_data.search",
                description=(
                    "Search or inventory already-stored structured project data across documents/extracted JSON, graph nodes, "
                    "market metrics, products, prices, resource-pool entries, keyword memory, search history, and sources. "
                    "This is read-only and never starts collection."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Optional search text. Leave empty for a project data inventory.",
                        },
                        "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                        "datasets": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": [
                                    "documents",
                                    "graph_nodes",
                                    "market_stats",
                                    "metric_points",
                                    "products",
                                    "price_observations",
                                    "resource_pool_urls",
                                    "resource_pool_sites",
                                    "keyword_history",
                                    "keyword_priors",
                                    "search_history",
                                    "sources",
                                ],
                            },
                        },
                    },
                    "additionalProperties": False,
                },
            ),
            build_tool_definition(
                name="project.structured_data.item.read",
                capability_id="project.structured_data.item.read",
                description=(
                    "Read one concrete already-stored structured project record returned by project.structured_data.search. "
                    "Use dataset+record_id, item_id, or resource_uri from model_evidence_manifest. This is read-only."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "project_key": {"type": "string"},
                        "dataset": {"type": "string"},
                        "record_id": {"type": "string"},
                        "item_id": {"type": "string"},
                        "resource_uri": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            ),
            build_tool_definition(
                name="project.structured_data.items.read",
                capability_id="project.structured_data.items.read",
                description="Read several concrete structured project records by manifest handles. This is read-only.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "project_key": {"type": "string"},
                        "items": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "project_key": {"type": "string"},
                                    "dataset": {"type": "string"},
                                    "record_id": {"type": "string"},
                                    "item_id": {"type": "string"},
                                    "resource_uri": {"type": "string"},
                                },
                                "additionalProperties": False,
                            },
                        },
                        "limit": {"type": "integer", "minimum": 1, "maximum": 25},
                    },
                    "additionalProperties": False,
                },
            ),
            build_tool_definition(
                name="project.context.resource.read",
                capability_id="project.context.resource.read",
                description="Read one concrete project context resource by resource_uri from project.context.bundle/model_evidence_manifest. This is read-only.",
                input_schema={
                    "type": "object",
                    "required": ["resource_uri"],
                    "properties": {
                        "project_key": {"type": "string"},
                        "resource_uri": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            ),
            build_tool_definition(
                name="project.context.bundle",
                capability_id="project.context.bundle",
                description=(
                    "Build a compact material context bundle across internal existing project data, generated artifacts, "
                    "writing documents, and source-library catalog entries. This is read-only and labels source catalog "
                    "items as collection entrypoints rather than existing evidence."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                    },
                    "additionalProperties": False,
                },
            ),
            build_tool_definition(
                name="source_library.item.list",
                capability_id="source_library.item.list",
                description="List effective project and shared source-library data-source items from the database without running collection or expanding execution plans.",
                input_schema={
                    "type": "object",
                    "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50}},
                    "additionalProperties": False,
                },
            ),
            build_tool_definition(
                name="source_library.item.search",
                capability_id="source_library.item.search",
                description="Search source-library items by query text.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                    },
                    "additionalProperties": False,
                },
            ),
            build_tool_definition(
                name="source_library.item.inspect",
                capability_id="source_library.item.inspect",
                description="Inspect one source-library item definition by item_key.",
                input_schema={
                    "type": "object",
                    "properties": {"item_key": {"type": "string"}},
                    "additionalProperties": False,
                },
            ),
            build_tool_definition(
                name="agent_artifact.search",
                capability_id="agent_artifact.search",
                description="Search artifacts in the current session.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                    },
                    "additionalProperties": False,
                },
            ),
            build_tool_definition(
                name="agent_artifact.read",
                capability_id="agent_artifact.read",
                description="Read the latest or explicitly named artifact in the current session.",
                input_schema={
                    "type": "object",
                    "properties": {"artifact_ref": {"type": "string"}},
                    "additionalProperties": False,
                },
            ),
            build_tool_definition(
                name="workflow_graph.list",
                capability_id="workflow_graph.list",
                description="List recently compiled workflow graphs and workflow graph templates without running them.",
                input_schema={
                    "type": "object",
                    "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50}},
                    "additionalProperties": False,
                },
            ),
            build_tool_definition(
                name="workflow_graph.inspect",
                capability_id="workflow_graph.inspect",
                description="Inspect one compiled workflow graph, including nodes, order, checksum, and expected input shape.",
                input_schema={
                    "type": "object",
                    "properties": {"graph_id": {"type": "string"}},
                    "additionalProperties": False,
                },
            ),
            build_tool_definition(
                name="ingest.status.read",
                capability_id="ingest.status.read",
                description="Read recent ingest and source-library job status without starting new collection.",
                input_schema={
                    "type": "object",
                    "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50}},
                    "additionalProperties": False,
                },
            ),
        ]

    def execute(
        self,
        *,
        tool_name: str,
        turn_id: str,
        session_id: str,
        project_key: str | None,
        command: str,
        input_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = dict(input_payload or {})
        name = _as_text(tool_name)
        if name == "agent_runtime.capability.catalog":
            return self.capability_catalog(turn_id=turn_id)
        if name == "agent_runtime.tool_pool.list":
            return self.tool_pool_list(turn_id=turn_id, project_key=project_key)
        if name == "agent_runtime.tool.search":
            return self.tool_search(
                turn_id=turn_id,
                project_key=project_key,
                query=_as_text(payload.get("query")) or command,
                limit=int(payload.get("limit") or 12),
            )
        if name == "agent_session.context.read":
            return self.session_context(session_id=session_id, turn_id=turn_id)
        if name == "project.summary.read":
            return self.project_summary(project_key=project_key, session_id=session_id, turn_id=turn_id)
        if name == "project.structured_data.search":
            return self.project_structured_data_search(
                project_key=project_key,
                turn_id=turn_id,
                query=_as_text(payload.get("query")) or command,
                limit=int(payload.get("limit") or 12),
                datasets=list(payload.get("datasets") or []) if isinstance(payload.get("datasets"), list) else None,
            )
        if name == "project.structured_data.item.read":
            return self.project_structured_data_item_read(
                project_key=_as_text(payload.get("project_key")) or project_key,
                turn_id=turn_id,
                dataset=_as_text(payload.get("dataset")) or None,
                record_id=_as_text(payload.get("record_id")) or None,
                item_id=_as_text(payload.get("item_id")) or None,
                resource_uri=_as_text(payload.get("resource_uri")) or None,
            )
        if name == "project.structured_data.items.read":
            return self.project_structured_data_items_read(
                project_key=_as_text(payload.get("project_key")) or project_key,
                turn_id=turn_id,
                items=list(payload.get("items") or []) if isinstance(payload.get("items"), list) else [],
                limit=int(payload.get("limit") or 8),
            )
        if name == "project.context.resource.read":
            return self.project_context_resource_read(
                project_key=_as_text(payload.get("project_key")) or project_key,
                turn_id=turn_id,
                resource_uri=_as_text(payload.get("resource_uri")),
            )
        if name == "project.context.bundle":
            return self.project_context_bundle(
                project_key=project_key,
                session_id=session_id,
                turn_id=turn_id,
                query=_as_text(payload.get("query")) or command,
                limit=int(payload.get("limit") or 8),
            )
        if name == "source_library.item.list":
            return self.source_library_list(project_key=project_key, turn_id=turn_id, limit=int(payload.get("limit") or 12))
        if name == "source_library.item.search":
            return self.source_library_search(
                project_key=project_key,
                turn_id=turn_id,
                query=_as_text(payload.get("query")) or command,
                limit=int(payload.get("limit") or 12),
            )
        if name == "source_library.item.inspect":
            return self.source_library_inspect(
                project_key=project_key,
                turn_id=turn_id,
                item_key=_as_text(payload.get("item_key")) or _extract_source_item_key(command),
            )
        if name == "agent_artifact.search":
            return self.artifact_search(
                session_id=session_id,
                turn_id=turn_id,
                query=_as_text(payload.get("query")) or command,
                limit=int(payload.get("limit") or 8),
            )
        if name == "agent_artifact.read":
            return self.artifact_read(
                session_id=session_id,
                turn_id=turn_id,
                artifact_ref=_as_text(payload.get("artifact_ref")) or None,
            )
        if name == "workflow_graph.list":
            return self.workflow_graph_list(turn_id=turn_id, limit=int(payload.get("limit") or 12))
        if name == "workflow_graph.inspect":
            return self.workflow_graph_inspect(
                turn_id=turn_id,
                graph_id=_as_text(payload.get("graph_id")) or _extract_graph_id(command),
            )
        if name == "ingest.status.read":
            return self.ingest_status_read(session_id=session_id, turn_id=turn_id, limit=int(payload.get("limit") or 12))
        return build_capability_call(
            turn_id=turn_id,
            capability_id=name or "unknown",
            protocol=READ_ONLY_TOOL_PROTOCOL,
            status="skipped",
            summary="read-only tool is not available in this runtime",
            result={"tool_name": name},
        )

    def capability_catalog(self, *, turn_id: str) -> dict[str, Any]:
        items = [
            {
                "capability_id": item.get("capability_id"),
                "name": item.get("name"),
                "domain": item.get("domain"),
                "approval_level": item.get("approval_level"),
                "concurrency_class": item.get("concurrency_class"),
                "description": item.get("description"),
            }
            for item in list_interactive_agent_capabilities()
        ]
        return build_capability_call(
            turn_id=turn_id,
            capability_id="agent_runtime.capability.catalog",
            protocol=READ_ONLY_TOOL_PROTOCOL,
            status="completed",
            summary=f"listed {len(items)} available agent capabilities",
            result={"items": items, "total": len(items)},
        )

    def tool_pool_list(self, *, turn_id: str, project_key: str | None) -> dict[str, Any]:
        pool = AgentToolPoolAssembler().assemble(
            ToolPoolRequest(
                project_key=project_key,
                agent_mode="read_only",
                feature_flags=default_agent_runtime_feature_flags(),
            )
        )
        counts = dict(pool.get("counts") or {})
        return build_capability_call(
            turn_id=turn_id,
            capability_id="agent_runtime.tool_pool.list",
            protocol=READ_ONLY_TOOL_PROTOCOL,
            status="completed",
            summary=(
                "assembled tool pool: "
                f"core={counts.get('core') or 0}, deferred={counts.get('deferred') or 0}, "
                f"disabled={counts.get('disabled') or 0}, approval_required={counts.get('approval_required') or 0}"
            ),
            result=pool,
        )

    def tool_search(self, *, turn_id: str, project_key: str | None, query: str, limit: int = 12) -> dict[str, Any]:
        result = AgentToolPoolAssembler().search(
            query=query,
            request=ToolPoolRequest(
                project_key=project_key,
                agent_mode="read_only",
                feature_flags=default_agent_runtime_feature_flags(),
            ),
            limit=limit,
        )
        return build_capability_call(
            turn_id=turn_id,
            capability_id="agent_runtime.tool.search",
            protocol=READ_ONLY_TOOL_PROTOCOL,
            status="completed",
            summary=f"matched {result.get('total') or 0} agent tools for query",
            result=result,
        )

    def session_context(self, *, session_id: str, turn_id: str) -> dict[str, Any]:
        bundle = self.service.get_session_bundle(session_id)
        tasks = list(bundle.get("tasks") or [])
        events = list(bundle.get("events") or [])
        artifacts = list(bundle.get("artifacts") or [])
        messages = list(bundle.get("messages") or [])
        recent_tool_results = self._recent_tool_results(events)
        return build_capability_call(
            turn_id=turn_id,
            capability_id="agent_session.context.read",
            protocol=READ_ONLY_TOOL_PROTOCOL,
            status="completed",
            summary=(
                f"read session context: tasks={len(tasks)}, events={len(events)}, "
                f"artifacts={len(artifacts)}, tool_results={len(recent_tool_results)}"
            ),
            result={
                "session": bundle.get("session"),
                "task_count": len(tasks),
                "event_count": len(events),
                "artifact_count": len(artifacts),
                "approval_count": len(list(bundle.get("approvals") or [])),
                "recent_tasks": tasks[-5:],
                "recent_events": events[-8:],
                "recent_messages": messages[-4:],
                "recent_tool_results": recent_tool_results,
            },
        )

    def project_summary(self, *, project_key: str | None, session_id: str, turn_id: str) -> dict[str, Any]:
        source_summary = self._list_source_library_items(project_key=project_key, limit=200)
        bundle = self.service.get_session_bundle(session_id)
        channels: dict[str, int] = {}
        enabled_count = 0
        for item in source_summary["items"]:
            channel_key = _as_text(item.get("channel_key")) or "unknown"
            channels[channel_key] = channels.get(channel_key, 0) + 1
            if item.get("enabled") is True:
                enabled_count += 1
        return build_capability_call(
            turn_id=turn_id,
            capability_id="project.summary.read",
            protocol=READ_ONLY_TOOL_PROTOCOL,
            status="completed",
            summary=f"read project summary for {project_key or '-'}",
            result={
                "project_key": project_key,
                "session": bundle.get("session"),
                "session_counts": {
                    "tasks": len(list(bundle.get("tasks") or [])),
                    "events": len(list(bundle.get("events") or [])),
                    "artifacts": len(list(bundle.get("artifacts") or [])),
                    "messages": len(list(bundle.get("messages") or [])),
                },
                "source_library": {
                    "total": source_summary["total"],
                    "enabled": enabled_count,
                    "channels": channels,
                    "sample": source_summary["items"][:8],
                },
            },
        )

    def source_library_list(self, *, project_key: str | None, turn_id: str, limit: int = 12) -> dict[str, Any]:
        listed = self._list_source_library_items(project_key=project_key, limit=limit)
        return build_capability_call(
            turn_id=turn_id,
            capability_id="source_library.item.list",
            protocol=READ_ONLY_TOOL_PROTOCOL,
            status=listed["status"],
            summary=listed["summary"],
            result={"items": listed["items"], "total": listed["total"], "project_key": project_key},
            error=listed.get("error"),
        )

    def project_structured_data_search(
        self,
        *,
        project_key: str | None,
        turn_id: str,
        query: str | None,
        limit: int = 12,
        datasets: list[str] | None = None,
    ) -> dict[str, Any]:
        try:
            result = self.structured_data_searcher(
                project_key=project_key,
                query=query,
                limit=max(1, min(50, int(limit or 12))),
                datasets=datasets,
            )
        except Exception as exc:  # noqa: BLE001
            return build_capability_call(
                turn_id=turn_id,
                capability_id="project.structured_data.search",
                protocol=READ_ONLY_TOOL_PROTOCOL,
                status="failed",
                summary=f"structured project data search failed: {exc}",
                result={"project_key": project_key, "query": query, "items": [], "dataset_results": []},
                error={"type": exc.__class__.__name__, "message": str(exc)},
            )
        if "model_evidence_manifest" not in result:
            result["model_evidence_manifest"] = build_structured_data_model_evidence_manifest(
                project_key=project_key,
                query=query,
                items=[item for item in list(result.get("items") or []) if isinstance(item, dict)],
                limit=max(12, int(limit or 12)),
            )
        mode = str(result.get("query_mode") or "search")
        total_matches = int(result.get("total_matches") or 0)
        total_stored_rows = int(result.get("total_stored_rows") or 0)
        error_count = len(list(result.get("errors") or []))
        summary = (
            f"read structured project data inventory: datasets={len(list(result.get('inventory') or []))}, samples={total_matches}, stored_rows={total_stored_rows}"
            if mode == "inventory"
            else f"searched structured project data: matches={total_matches}, datasets={len(list(result.get('dataset_results') or []))}, stored_rows={total_stored_rows}"
        )
        if result.get("fallback_used"):
            summary = f"{summary}, returned_inventory_fallback={len(list(result.get('items') or []))}"
        if error_count:
            summary = f"{summary}, dataset_errors={error_count}"
        status = "completed" if str(result.get("project_key") or "").strip() else "failed"
        return build_capability_call(
            turn_id=turn_id,
            capability_id="project.structured_data.search",
            protocol=READ_ONLY_TOOL_PROTOCOL,
            status=status,
            summary=summary,
            result=result,
            error={"type": "dataset_errors", "items": list(result.get("errors") or [])} if status == "failed" and error_count else None,
        )

    def project_structured_data_item_read(
        self,
        *,
        project_key: str | None,
        turn_id: str,
        dataset: str | None = None,
        record_id: str | None = None,
        item_id: str | None = None,
        resource_uri: str | None = None,
    ) -> dict[str, Any]:
        result = read_project_structured_data_item(
            project_key=project_key,
            dataset=dataset,
            record_id=record_id,
            item_id=item_id,
            resource_uri=resource_uri,
        )
        if not result.get("item"):
            fallback = self._read_structured_item_via_searcher(
                project_key=project_key,
                dataset=dataset,
                record_id=record_id,
                item_id=item_id,
                resource_uri=resource_uri,
            )
            if fallback.get("item"):
                result = fallback
        errors = [item for item in list(result.get("errors") or []) if isinstance(item, dict)]
        item = result.get("item") if isinstance(result.get("item"), dict) else None
        status = "completed" if item else "failed"
        title = item.get("title") if item else None
        return build_capability_call(
            turn_id=turn_id,
            capability_id="project.structured_data.item.read",
            protocol=READ_ONLY_TOOL_PROTOCOL,
            status=status,
            summary=f"read structured project record {result.get('dataset')}/{result.get('record_id')}{f': {title}' if title else ''}" if item else "structured project record was not readable",
            result=result,
            error={"type": "structured_item_read_failed", "items": errors} if status == "failed" else None,
        )

    def project_structured_data_items_read(
        self,
        *,
        project_key: str | None,
        turn_id: str,
        items: list[dict[str, Any]],
        limit: int = 8,
    ) -> dict[str, Any]:
        result = read_project_structured_data_items(project_key=project_key, items=items, limit=limit)
        recovered: list[dict[str, Any]] = []
        if not result.get("items"):
            for ref in items[: max(1, min(25, int(limit or 8)))]:
                if not isinstance(ref, dict):
                    continue
                candidate = self._read_structured_item_via_searcher(
                    project_key=ref.get("project_key") or project_key,
                    dataset=ref.get("dataset"),
                    record_id=ref.get("record_id"),
                    item_id=ref.get("item_id"),
                    resource_uri=ref.get("resource_uri"),
                )
                if candidate.get("item"):
                    recovered.append(candidate)
        if recovered:
            result["items"] = recovered
            manifest: list[dict[str, Any]] = []
            for candidate in recovered:
                manifest.extend([item for item in list(candidate.get("model_evidence_manifest") or []) if isinstance(item, dict)])
            result["model_evidence_manifest"] = manifest
            result["total_returned"] = len(recovered)
        total = int(result.get("total_returned") or len(list(result.get("items") or [])))
        status = "completed" if total else "failed"
        return build_capability_call(
            turn_id=turn_id,
            capability_id="project.structured_data.items.read",
            protocol=READ_ONLY_TOOL_PROTOCOL,
            status=status,
            summary=f"read {total} structured project record(s)",
            result=result,
            error={"type": "structured_items_read_failed", "items": list(result.get("errors") or [])} if status == "failed" else None,
        )

    def project_context_resource_read(self, *, project_key: str | None, turn_id: str, resource_uri: str) -> dict[str, Any]:
        result = read_project_context_resource(project_key=project_key, resource_uri=resource_uri)
        if not result.get("item") and str(resource_uri or "").startswith("project://structured/"):
            result = self._read_structured_item_via_searcher(project_key=project_key, resource_uri=resource_uri)
        status = "completed" if result.get("item") else "failed"
        return build_capability_call(
            turn_id=turn_id,
            capability_id="project.context.resource.read",
            protocol=READ_ONLY_TOOL_PROTOCOL,
            status=status,
            summary="read project context resource" if status == "completed" else "project context resource was not readable",
            result=result,
            error={"type": "context_resource_read_failed", "items": list(result.get("errors") or [])} if status == "failed" else None,
        )

    def _read_structured_item_via_searcher(
        self,
        *,
        project_key: str | None,
        dataset: str | None = None,
        record_id: Any | None = None,
        item_id: str | None = None,
        resource_uri: str | None = None,
    ) -> dict[str, Any]:
        dataset_text, record_text = _parse_structured_read_ref(dataset=dataset, record_id=record_id, item_id=item_id, resource_uri=resource_uri)
        if not dataset_text or not record_text:
            return {"item": None, "errors": [{"type": "missing_record_ref", "message": "dataset and record_id are required"}]}
        try:
            searched = self.structured_data_searcher(
                project_key=project_key,
                query=record_text,
                limit=50,
                datasets=[dataset_text],
            )
        except Exception as exc:  # noqa: BLE001
            return {"item": None, "errors": [{"type": exc.__class__.__name__, "message": str(exc)}]}
        candidates = [item for item in list(searched.get("items") or []) if isinstance(item, dict)]
        item = next((candidate for candidate in candidates if str(candidate.get("record_id") or candidate.get("id") or "") == record_text), None)
        if item is None and candidates:
            item = candidates[0]
        manifest = build_structured_data_model_evidence_manifest(
            project_key=project_key,
            query=None,
            items=[item] if item else [],
            limit=1,
        )
        return {
            "contract_version": "project.structured_data.item.read.v1",
            "project_key": project_key,
            "dataset": dataset_text,
            "record_id": record_text,
            "item": item,
            "model_evidence_manifest": manifest,
            "resource_uri": manifest[0]["resource_uri"] if manifest else resource_uri,
            "cleaned_text": item.get("summary") if isinstance(item, dict) else "",
            "source_ref": item.get("source_uri") if isinstance(item, dict) else None,
            "errors": [] if item else [{"type": "record_not_found", "message": "structured record was not found"}],
        }

    def project_context_bundle(
        self,
        *,
        project_key: str | None,
        session_id: str,
        turn_id: str,
        query: str | None,
        limit: int = 8,
    ) -> dict[str, Any]:
        query_text = _as_text(query)
        material_intent = classify_material_intent(query_text)
        safe_limit = max(1, min(50, int(limit or 8)))
        summary_call = self.project_summary(project_key=project_key, session_id=session_id, turn_id=turn_id)
        structured_call = self.project_structured_data_search(
            project_key=project_key,
            turn_id=turn_id,
            query=query_text,
            limit=safe_limit,
        )
        artifact_call = self.artifact_search(session_id=session_id, turn_id=turn_id, query=query_text, limit=safe_limit)
        source_call = self.source_library_list(project_key=project_key, turn_id=turn_id, limit=safe_limit)
        writing_documents = self._list_writing_documents(project_key=project_key, limit=safe_limit)

        summary = dict(summary_call.get("result") or {})
        structured = dict(structured_call.get("result") or {})
        artifacts = dict(artifact_call.get("result") or {})
        source_catalog = dict(source_call.get("result") or {})
        inventory = [item for item in list(structured.get("inventory") or []) if isinstance(item, dict)]
        structured_items = [item for item in list(structured.get("items") or []) if isinstance(item, dict)]
        artifact_items = [item for item in list(artifacts.get("items") or []) if isinstance(item, dict)]
        source_items = [item for item in list(source_catalog.get("items") or []) if isinstance(item, dict)]
        writing_items = [item for item in list(writing_documents.get("items") or []) if isinstance(item, dict)]

        internal_existing_count = int(structured.get("total_stored_rows") or 0) + len(writing_items)
        internal_generated_count = int(artifacts.get("total") or len(artifact_items))
        source_catalog_count = int(source_catalog.get("total") or len(source_items))
        missing_evidence: list[str] = []
        if query_text and not structured_items and not artifact_items and not writing_items:
            missing_evidence.append("No matching internal material was found for the current query.")
        if query_text and source_catalog_count == 0 and material_intent.scope in {"external", "mixed"}:
            missing_evidence.append("No source-catalog entry is currently available for the external collection direction.")

        evidence = []
        for item in inventory[:safe_limit]:
            evidence.append(
                {
                    "category": INTERNAL_EXISTING,
                    "label": category_label(INTERNAL_EXISTING),
                    "kind": "structured_dataset",
                    "title": item.get("dataset") or item.get("label"),
                    "count": item.get("total_rows") if item.get("total_rows") is not None else item.get("sample_count"),
                }
            )
        for item in structured_items[:safe_limit]:
            evidence.append(
                {
                    "category": INTERNAL_EXISTING,
                    "label": category_label(INTERNAL_EXISTING),
                    "kind": "structured_record",
                    "title": item.get("title") or item.get("record_id"),
                    "dataset": item.get("dataset"),
                    "summary": item.get("summary"),
                }
            )
        for item in writing_items[:safe_limit]:
            evidence.append(
                {
                    "category": INTERNAL_EXISTING,
                    "label": category_label(INTERNAL_EXISTING),
                    "kind": "writing_document",
                    "title": item.get("title") or item.get("doc_id"),
                    "version": item.get("version") or item.get("head_version"),
                }
            )
        for item in artifact_items[:safe_limit]:
            evidence.append(
                {
                    "category": INTERNAL_GENERATED,
                    "label": category_label(INTERNAL_GENERATED),
                    "kind": "agent_artifact",
                    "title": item.get("name") or item.get("artifact_type") or item.get("artifact_id"),
                    "summary": item.get("summary"),
                }
            )
        for item in source_items[:safe_limit]:
            evidence.append(
                {
                    "category": SOURCE_CATALOG,
                    "label": category_label(SOURCE_CATALOG),
                    "kind": "source_catalog_item",
                    "title": item.get("item_key") or item.get("name"),
                    "channel_key": item.get("channel_key"),
                    "enabled": item.get("enabled"),
                    "note": "collection entrypoint, not already ingested evidence",
                }
            )
        model_evidence_manifest = [
            item
            for item in list(structured.get("model_evidence_manifest") or [])
            if isinstance(item, dict)
        ][: max(1, safe_limit * 2)]
        for item in writing_items[:safe_limit]:
            doc_id = item.get("doc_id") or item.get("id")
            if doc_id is None:
                continue
            model_evidence_manifest.append(
                {
                    "item_id": f"writing_document:{doc_id}",
                    "resource_uri": f"project://writing/{project_key or ''}/document/{doc_id}",
                    "project_key": project_key,
                    "kind": "writing_document",
                    "category": INTERNAL_EXISTING,
                    "title": item.get("title") or f"document:{doc_id}",
                    "short_snippet": item.get("summary") or "",
                    "read_tool": "writing.document.read",
                    "read_arguments": {"project_key": project_key, "doc_id": doc_id},
                    "is_source_catalog_entry": False,
                }
            )
        for item in artifact_items[:safe_limit]:
            artifact_ref = item.get("artifact_id") or item.get("name")
            if not artifact_ref:
                continue
            model_evidence_manifest.append(
                {
                    "item_id": f"agent_artifact:{artifact_ref}",
                    "resource_uri": f"agent://artifact/{artifact_ref}",
                    "project_key": project_key,
                    "kind": "agent_artifact",
                    "category": INTERNAL_GENERATED,
                    "title": item.get("name") or item.get("artifact_type") or artifact_ref,
                    "short_snippet": item.get("summary") or "",
                    "read_tool": "agent_artifact.read",
                    "read_arguments": {"artifact_ref": artifact_ref},
                    "is_source_catalog_entry": False,
                }
            )
        for item in source_items[:safe_limit]:
            item_key = item.get("item_key") or item.get("name")
            if not item_key:
                continue
            model_evidence_manifest.append(
                {
                    "item_id": f"source_catalog:{item_key}",
                    "resource_uri": f"project://source-catalog/{project_key or ''}/{item_key}",
                    "project_key": project_key,
                    "kind": "source_catalog_item",
                    "category": SOURCE_CATALOG,
                    "title": item.get("name") or item_key,
                    "short_snippet": item.get("description") or "",
                    "read_tool": "source_library.item.inspect",
                    "read_arguments": {"item_key": item_key},
                    "is_source_catalog_entry": True,
                    "note": "collection entrypoint, not already ingested evidence",
                }
            )

        material_categories = {
            INTERNAL_EXISTING: {
                "label": category_label(INTERNAL_EXISTING),
                "structured_datasets": len(inventory),
                "stored_rows": int(structured.get("total_stored_rows") or 0),
                "writing_documents": len(writing_items),
            },
            INTERNAL_GENERATED: {
                "label": category_label(INTERNAL_GENERATED),
                "artifacts": internal_generated_count,
            },
            SOURCE_CATALOG: {
                "label": category_label(SOURCE_CATALOG),
                "items": source_catalog_count,
                "enabled": int(dict(summary.get("source_library") or {}).get("enabled") or 0),
            },
            EXTERNAL_DISCOVERY: {
                "label": category_label(EXTERNAL_DISCOVERY),
                "suggested": bool(missing_evidence and material_intent.scope in {"external", "mixed"}),
            },
        }

        result = {
            "contract_version": "project.context.bundle.v1",
            "project_key": project_key,
            "query": query_text,
            "material_intent": material_intent.to_dict(),
            "material_categories": material_categories,
            "model_evidence_manifest": model_evidence_manifest[: max(1, safe_limit * 4)],
            "evidence": evidence[: max(1, safe_limit * 4)],
            "missing_evidence": missing_evidence,
            "source_catalog_note": "source-library items are collection/data-source entrypoints, not already ingested project materials.",
            "components": {
                "project_summary": summary,
                "structured_data": structured,
                "artifacts": artifacts,
                "writing_documents": writing_documents,
                "source_catalog": source_catalog,
            },
        }
        return build_capability_call(
            turn_id=turn_id,
            capability_id="project.context.bundle",
            protocol=READ_ONLY_TOOL_PROTOCOL,
            status="completed",
            summary=(
                "built project material context bundle: "
                f"internal_existing={internal_existing_count}, generated_artifacts={internal_generated_count}, "
                f"source_catalog_items={source_catalog_count}, missing={len(missing_evidence)}"
            ),
            result=result,
        )

    def source_library_search(self, *, project_key: str | None, turn_id: str, query: str, limit: int = 12) -> dict[str, Any]:
        listed = self._list_source_library_items(project_key=project_key, limit=200)
        query_text = _as_text(query)
        matches = [item for item in listed["items"] if _matches_query(item, query_text)]
        return build_capability_call(
            turn_id=turn_id,
            capability_id="source_library.item.search",
            protocol=READ_ONLY_TOOL_PROTOCOL,
            status=listed["status"],
            summary=f"matched {len(matches)} source-library items for query",
            result={
                "query": query_text,
                "items": matches[: max(1, limit)],
                "total": len(matches),
                "source_total": listed["total"],
                "project_key": project_key,
            },
            error=listed.get("error"),
        )

    def source_library_inspect(self, *, project_key: str | None, turn_id: str, item_key: str | None) -> dict[str, Any]:
        key = _as_text(item_key)
        if not key:
            return build_capability_call(
                turn_id=turn_id,
                capability_id="source_library.item.inspect",
                protocol=READ_ONLY_TOOL_PROTOCOL,
                status="skipped",
                summary="source-library inspect skipped because no item_key was supplied",
                result={"item": None, "project_key": project_key},
            )
        listed = self._list_source_library_items(project_key=project_key, limit=500)
        item = next((candidate for candidate in listed["raw_items"] if _as_text(candidate.get("item_key")) == key), None)
        status = "completed" if item else "skipped"
        summary = f"inspected source-library item {key}" if item else f"source-library item {key} not found"
        return build_capability_call(
            turn_id=turn_id,
            capability_id="source_library.item.inspect",
            protocol=READ_ONLY_TOOL_PROTOCOL,
            status=status,
            summary=summary,
            result={"item": item, "project_key": project_key},
        )

    def artifact_search(self, *, session_id: str, turn_id: str, query: str | None = None, limit: int = 8) -> dict[str, Any]:
        query_text = _as_text(query).lower()
        query_tokens = _query_tokens(query_text)
        bundle = self.service.get_session_bundle(session_id)
        artifacts = list(bundle.get("artifacts") or [])
        matches: list[dict[str, Any]] = []
        for artifact in artifacts:
            haystack = " ".join(
                _as_text(artifact.get(key)).lower()
                for key in ("artifact_id", "artifact_type", "name", "path", "summary", "mime_type")
            )
            if not query_text or query_text in haystack or any(token in haystack for token in query_tokens):
                matches.append(artifact)
        return build_capability_call(
            turn_id=turn_id,
            capability_id="agent_artifact.search",
            protocol=READ_ONLY_TOOL_PROTOCOL,
            status="completed",
            summary=f"matched {len(matches)} session artifacts",
            result={"query": query, "items": matches[: max(1, limit)], "total": len(matches)},
        )

    def artifact_read(self, *, session_id: str, turn_id: str, artifact_ref: str | None = None) -> dict[str, Any]:
        ref = _as_text(artifact_ref)
        bundle = self.service.get_session_bundle(session_id)
        artifacts = list(bundle.get("artifacts") or [])
        artifact = None
        if ref:
            ref_lower = ref.lower()
            artifact = next(
                (
                    candidate
                    for candidate in artifacts
                    if ref in {_as_text(candidate.get("artifact_id")), _as_text(candidate.get("name"))}
                    or ref_lower
                    in " ".join(
                        _as_text(candidate.get(key)).lower()
                        for key in ("artifact_id", "artifact_type", "name", "path", "summary", "mime_type")
                    )
                ),
                None,
            )
        if not artifact and artifacts:
            artifact = artifacts[-1]
        return build_capability_call(
            turn_id=turn_id,
            capability_id="agent_artifact.read",
            protocol=READ_ONLY_TOOL_PROTOCOL,
            status="completed" if artifact else "skipped",
            summary="read session artifact" if artifact else "no session artifact was available to read",
            result={"artifact": artifact},
        )

    def workflow_graph_list(self, *, turn_id: str, limit: int = 12) -> dict[str, Any]:
        try:
            from app.services.workflow_graph import compiler

            compiled = [_compact_workflow_graph(dict(row or {})) for row in compiler.list_compiled(limit=limit)]
            templates = compiler.list_templates()
            template_items = list(templates.get("items") or []) if isinstance(templates, dict) else []
            return build_capability_call(
                turn_id=turn_id,
                capability_id="workflow_graph.list",
                protocol=READ_ONLY_TOOL_PROTOCOL,
                status="completed",
                summary=f"listed {len(compiled)} compiled workflow graphs and {len(template_items)} templates",
                result={
                    "compiled_graphs": compiled,
                    "templates": template_items[: max(1, limit)],
                    "total_compiled": len(compiled),
                    "total_templates": len(template_items),
                },
            )
        except Exception as exc:  # noqa: BLE001
            return build_capability_call(
                turn_id=turn_id,
                capability_id="workflow_graph.list",
                protocol=READ_ONLY_TOOL_PROTOCOL,
                status="failed",
                summary=f"workflow graph list failed: {exc}",
                result={"compiled_graphs": [], "templates": []},
                error={"type": exc.__class__.__name__, "message": str(exc)},
            )

    def workflow_graph_inspect(self, *, turn_id: str, graph_id: str | None) -> dict[str, Any]:
        resolved_graph_id = _as_text(graph_id)
        if not resolved_graph_id:
            return build_capability_call(
                turn_id=turn_id,
                capability_id="workflow_graph.inspect",
                protocol=READ_ONLY_TOOL_PROTOCOL,
                status="skipped",
                summary="workflow graph inspect skipped because no graph_id was supplied",
                result={"graph": None},
            )
        try:
            from app.services.workflow_graph import compiler

            graph = dict(compiler.get_compiled(resolved_graph_id))
            compact = _compact_workflow_graph(graph)
            nodes = dict(graph.get("nodes") or {})
            return build_capability_call(
                turn_id=turn_id,
                capability_id="workflow_graph.inspect",
                protocol=READ_ONLY_TOOL_PROTOCOL,
                status="completed",
                summary=f"inspected workflow graph {resolved_graph_id}",
                result={
                    "graph": compact,
                    "nodes": nodes,
                    "edges": {
                        "incoming": dict(graph.get("incoming_edges") or {}),
                        "outgoing": dict(graph.get("outgoing_edges") or {}),
                    },
                    "options": dict(graph.get("options") or {}),
                },
            )
        except Exception as exc:  # noqa: BLE001
            return build_capability_call(
                turn_id=turn_id,
                capability_id="workflow_graph.inspect",
                protocol=READ_ONLY_TOOL_PROTOCOL,
                status="failed",
                summary=f"workflow graph inspect failed for {resolved_graph_id}: {exc}",
                result={"graph_id": resolved_graph_id},
                error={"type": exc.__class__.__name__, "message": str(exc)},
            )

    def ingest_status_read(self, *, session_id: str, turn_id: str, limit: int = 12) -> dict[str, Any]:
        try:
            from app.services.job_logger import list_jobs

            jobs = [
                item
                for item in list_jobs(limit=max(20, limit * 3))
                if "ingest" in _as_text(item.get("job_type")).lower()
                or "source_library" in _as_text(item.get("job_type")).lower()
                or "source_library" in json.dumps(item.get("params") or {}, ensure_ascii=False, default=str).lower()
            ]
        except Exception as exc:  # noqa: BLE001
            jobs = []
            job_error = {"type": exc.__class__.__name__, "message": str(exc)}
        else:
            job_error = None

        bundle = self.service.get_session_bundle(session_id)
        recent_tasks = [
            task
            for task in list(bundle.get("tasks") or [])
            if "ingest" in _as_text(task.get("task_type")).lower()
            or "source" in _as_text(task.get("subject")).lower()
            or "采集" in _as_text(task.get("subject"))
        ][-limit:]
        status_counts: dict[str, int] = {}
        for job in jobs:
            status = _as_text(job.get("status")) or "unknown"
            status_counts[status] = status_counts.get(status, 0) + 1
        status = "completed" if job_error is None else "failed"
        return build_capability_call(
            turn_id=turn_id,
            capability_id="ingest.status.read",
            protocol=READ_ONLY_TOOL_PROTOCOL,
            status=status,
            summary=f"read ingest status: recent_jobs={len(jobs[:limit])}, session_tasks={len(recent_tasks)}",
            result={
                "recent_jobs": jobs[: max(1, limit)],
                "job_status_counts": status_counts,
                "recent_session_tasks": recent_tasks,
                "session_id": session_id,
            },
            error=job_error,
        )

    def _list_writing_documents(self, *, project_key: str | None, limit: int) -> dict[str, Any]:
        key = _as_text(project_key)
        if not key:
            return {"status": "skipped", "items": [], "total": 0, "error": {"type": "missing_project_key", "message": "project_key is required"}}
        try:
            from app.services.projects import bind_project
            from app.services.writing.document_service import list_documents

            with bind_project(key):
                raw_items = list_documents(project_key=key, limit=max(1, limit))
        except Exception as exc:  # noqa: BLE001
            return {"status": "failed", "items": [], "total": 0, "error": {"type": exc.__class__.__name__, "message": str(exc)}}
        items = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            items.append(
                {
                    "doc_id": item.get("doc_id") or item.get("id"),
                    "title": item.get("title"),
                    "version": item.get("version") or item.get("head_version"),
                    "updated_at": item.get("updated_at"),
                    "status": item.get("status"),
                    "body_preview": _as_text(item.get("body_md"))[:240],
                }
            )
        return {"status": "completed", "items": items[: max(1, limit)], "total": len(raw_items)}

    def _list_source_library_items(self, *, project_key: str | None, limit: int) -> dict[str, Any]:
        if self.source_library_lister is None:
            return {
                "status": "skipped",
                "summary": "source-library discovery unavailable in this runtime",
                "items": [],
                "raw_items": [],
                "total": 0,
            }
        try:
            raw_items = list(self.source_library_lister(project_key) or [])
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "failed",
                "summary": f"source-library discovery failed: {exc}",
                "items": [],
                "raw_items": [],
                "total": 0,
                "error": {"type": exc.__class__.__name__, "message": str(exc)},
            }
        compact = [_compact_source_item(dict(item or {})) for item in raw_items]
        return {
            "status": "completed",
            "summary": f"discovered {len(raw_items)} source-library items for project {project_key or '-'}",
            "items": compact[: max(1, limit)],
            "raw_items": raw_items,
            "total": len(raw_items),
        }

    @staticmethod
    def _recent_tool_results(events: list[dict[str, Any]], *, limit: int = 8) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for event in events:
            if str(event.get("event_type") or "") != "interactive_agent.tool_call_result":
                continue
            payload = dict(event.get("payload") or {})
            out.append(
                {
                    "event_id": event.get("event_id"),
                    "seq": event.get("seq"),
                    "created_at": event.get("created_at"),
                    "capability_id": payload.get("capability_id") or payload.get("tool_name"),
                    "tool_name": payload.get("tool_name") or payload.get("capability_id"),
                    "status": payload.get("status") or payload.get("stream_state"),
                    "summary": payload.get("summary"),
                    "error": payload.get("error"),
                }
            )
        return out[-limit:]
