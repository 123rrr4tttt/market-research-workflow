from __future__ import annotations
from dataclasses import asdict
from app.services.document_queries.contracts import coerce_material_query_result_row
from .structured_data_search import StructuredRecord
from typing import Protocol, Callable, cast
from functorial_kit import Failure
from dataclasses import dataclass
from functools import partial
import json
import re
from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_core.contracts import AgentCoreRequest, CoreToolCall, CoreToolResult, JSONObject, ToolStatus
from app.services.agent_core.tool_support import (
    SourceLibraryLister,
    StructuredDataSearcher,
    compact_json_value,
    compact_session,
    core_status,
    json_list,
    json_object,
    runtime_failure_result,
)
from app.services.agent_core.tool_contribution import ProjectToolAuthorSource, ProjectToolOperation
from .capability_registry import list_interactive_agent_capabilities
from .control_tools import project_tool_sources, project_tool_declaration
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
from .tool_pool import AgentToolPoolAssembler, ToolPoolRequest, default_agent_runtime_feature_flags
from .system_projection_contracts import (
    SYSTEM_INSPECT_DESCRIPTION,
    SYSTEM_INSPECT_TOOL_NAME,
    system_inspect_input_schema,
)
from .system_projection import (
    SystemProjection,
    SystemProjectionError,
    inspect_system_projection_with_budget,
)


_SOURCE_LIBRARY_DISPATCH_ARTIFACT_NAME = "ingest.source_library_dispatches.json"
_SOURCE_LIBRARY_DISPATCH_CONTRACT = "ingest.source_library.dispatch_state.v1"
_SOURCE_LIBRARY_DISPATCH_SKILL = "ingest.dispatch.source_library_item"
_SOURCE_LIBRARY_TASK_READ_LIMIT = 5
_SOURCE_LIBRARY_RECORD_BODY_BUDGET = 4000


class _AsyncResultView(Protocol):
    @property
    def status(self) -> object: ...

    @property
    def result(self) -> object: ...

    def ready(self) -> bool: ...

    def successful(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class ReadOnlyToolContext:
    service: AgentSessionService
    source_library_lister: SourceLibraryLister | None
    structured_data_searcher: StructuredDataSearcher
    system_projection_provider: Callable[[], SystemProjection] | None = None


class ReadToolOperation(Protocol):
    def __call__(
        self, tool_call: CoreToolCall, request: AgentCoreRequest, *, context: ReadOnlyToolContext
    ) -> CoreToolResult: ...


def _read_tool_declaration(
    context: ReadOnlyToolContext,
    operation: ReadToolOperation,
    *,
    name: str,
    description: str,
    input_schema: JSONObject,
    result_budget: int = 4000,
) -> tuple[JSONObject, ProjectToolOperation]:
    return project_tool_declaration(
        name=name, description=description, input_schema=input_schema, operation=partial(operation, context=context)
        , result_budget=result_budget
    )


@dataclass(frozen=True, slots=True)
class StructuredDataRead:
    status: ToolStatus
    summary: str
    result: JSONObject
    error: JSONObject | None = None


def _objects(value: object) -> list[JSONObject]:
    return [json_object(item) for item in json_list(value) if isinstance(item, dict)]


def _datasets(value: object) -> list[str] | None:
    items = json_list(value)
    return [str(item) for item in items] if isinstance(value, list) else None


def _limit(call: CoreToolCall, default: int) -> int:
    value = call.arguments.get("limit") or default
    if not isinstance(value, (str, int, float)):
        raise TypeError("limit must be an integer")
    return _integer(value)


def _read_result(
    call: CoreToolCall, *, status: ToolStatus, summary: str, result: JSONObject, error: JSONObject | None = None
) -> CoreToolResult:
    return CoreToolResult(
        call_id=call.call_id,
        tool_name=call.tool_name,
        status=status,
        model_summary=summary,
        ui_summary=summary,
        structured_content={"result": _compact_result_for_core(call.tool_name, result)},
        error=error,
    )


def _as_text(value: object) -> str:
    return str(value or "").strip()


def _compact_source_item(item: JSONObject) -> JSONObject:
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


def _matches_query(item: JSONObject, query: str) -> bool:
    if not query:
        return True
    haystack = " ".join(
        (
            _as_text(item.get(key)).lower()
            for key in ("item_key", "name", "channel_key", "item_type", "description", "managed_by")
        )
    )
    tags = " ".join(_as_text(tag).lower() for tag in json_list(item.get("tags")))
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
        if any((marker in cleaned.lower() for marker in ("graph", "workflow", "_"))) or len(cleaned) >= 4:
            return cleaned
    return None


def _parse_structured_read_ref(
    *,
    dataset: object | None = None,
    record_id: object | None = None,
    item_id: object | None = None,
    resource_uri: object | None = None,
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
    return (dataset_text, record_text)


def _query_tokens(query: str) -> list[str]:
    tokens = [
        token.strip().lower()
        for token in re.split("[\\s,，。；;:：/|()（）\\[\\]{}]+", str(query or ""))
        if token.strip()
    ]
    return [token for token in tokens if len(token) >= 2]


def _compact_workflow_graph(record: JSONObject) -> JSONObject:
    nodes = json_object(record.get("nodes") or {})
    return {
        "graph_id": record.get("graph_id"),
        "version": record.get("version"),
        "checksum": record.get("checksum"),
        "node_count": len(nodes),
        "topo_order": json_list(record.get("topo_order") or [])[:20],
        "input_keys": sorted(
            {key for node in nodes.values() for key in json_object(json_object(node).get("params") or {}).keys()}
        )[:20],
    }


def _read_tool_declarations(context: ReadOnlyToolContext) -> tuple[tuple[JSONObject, ProjectToolOperation], ...]:
    declarations = (
        _read_tool_declaration(
            context,
            capability_catalog,
            name="agent_runtime.capability.catalog",
            description="List available agent capabilities and risk metadata.",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        _read_tool_declaration(
            context,
            tool_pool_list,
            name="agent_runtime.tool_pool.list",
            description="List the dynamically assembled tool pool grouped by core, deferred, disabled, and approval-required tools.",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        _read_tool_declaration(
            context,
            tool_search,
            name="agent_runtime.tool.search",
            description="Search the full agent tool pool and lazily discover tools by name, domain, risk, or description.",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 50}},
                "additionalProperties": False,
            },
        ),
        _read_tool_declaration(
            context,
            session_context,
            name="agent_session.context.read",
            description="Read the current agent session ledger, messages, tasks, events, artifacts, and approvals.",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        _read_tool_declaration(
            context,
            project_summary,
            name="project.summary.read",
            description="Read the local project database and summarize project-scoped data, source-library coverage, and session counters without mutating state.",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        _read_tool_declaration(
            context,
            project_structured_data_search,
            name="project.structured_data.search",
            description="Search or inventory already-stored structured project data across materials/extracted JSON, graph nodes, market metrics, products, prices, resource-pool entries, keyword memory, search history, and sources. This is read-only and never starts collection.",
            input_schema={
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["search", "inventory"],
                        "description": "Use inventory to read dataset totals without search text; search preserves optional query text.",
                    },
                    "query": {
                        "type": "string",
                        "description": "Optional search text in search mode. Set mode=inventory to ignore search text and read dataset totals.",
                    },
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                    "datasets": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "materials",
                                "documents",
                                "graph_nodes",
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
        _read_tool_declaration(
            context,
            project_structured_data_item_read,
            name="project.structured_data.item.read",
            description="Read one concrete already-stored structured project record returned by project.structured_data.search. Use dataset+record_id, item_id, or resource_uri from model_evidence_manifest. This is read-only.",
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
        _read_tool_declaration(
            context,
            project_structured_data_items_read,
            name="project.structured_data.items.read",
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
        _read_tool_declaration(
            context,
            project_context_resource_read,
            name="project.context.resource.read",
            description="Read one concrete project context resource by resource_uri from project.context.bundle/model_evidence_manifest. This is read-only.",
            input_schema={
                "type": "object",
                "required": ["resource_uri"],
                "properties": {"project_key": {"type": "string"}, "resource_uri": {"type": "string"}},
                "additionalProperties": False,
            },
        ),
        _read_tool_declaration(
            context,
            project_context_bundle,
            name="project.context.bundle",
            description="Build a compact material context bundle across internal existing project data, generated artifacts, writing documents, and source-library catalog entries. This is read-only and labels source catalog items as collection entrypoints rather than existing evidence.",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 50}},
                "additionalProperties": False,
            },
        ),
        _read_tool_declaration(
            context,
            source_library_list,
            name="source_library.item.list",
            description="List effective project and shared source-library data-source items from the database without running collection or expanding execution plans.",
            input_schema={
                "type": "object",
                "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50}},
                "additionalProperties": False,
            },
        ),
        _read_tool_declaration(
            context,
            source_library_search,
            name="source_library.item.search",
            description="Search source-library items by query text.",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 50}},
                "additionalProperties": False,
            },
        ),
        _read_tool_declaration(
            context,
            source_library_inspect,
            name="source_library.item.inspect",
            description="Inspect one source-library item definition by item_key.",
            input_schema={
                "type": "object",
                "properties": {"item_key": {"type": "string"}},
                "additionalProperties": False,
            },
        ),
        _read_tool_declaration(
            context,
            artifact_search,
            name="agent_artifact.search",
            description="Search artifacts in the current session.",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 50}},
                "additionalProperties": False,
            },
        ),
        _read_tool_declaration(
            context,
            artifact_read,
            name="agent_artifact.read",
            description="Read the latest or explicitly named artifact in the current session.",
            input_schema={
                "type": "object",
                "properties": {"artifact_ref": {"type": "string"}},
                "additionalProperties": False,
            },
        ),
        _read_tool_declaration(
            context,
            workflow_graph_list,
            name="workflow_graph.list",
            description="List recently compiled workflow graphs and workflow graph templates without running them.",
            input_schema={
                "type": "object",
                "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50}},
                "additionalProperties": False,
            },
        ),
        _read_tool_declaration(
            context,
            workflow_graph_inspect,
            name="workflow_graph.inspect",
            description="Inspect one compiled workflow graph, including nodes, order, checksum, and expected input shape.",
            input_schema={
                "type": "object",
                "properties": {"graph_id": {"type": "string"}},
                "additionalProperties": False,
            },
        ),
        _read_tool_declaration(
            context,
            ingest_status_read,
            name="ingest.status.read",
            description="Read recent ingest and source-library job status without starting new collection.",
            input_schema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                    "task_id": {
                        "oneOf": [
                            {"type": "string", "minLength": 1},
                            {
                                "type": "array",
                                "items": {"type": "string", "minLength": 1},
                                "minItems": 1,
                                "maxItems": 5,
                            },
                        ],
                        "description": "Optional Celery task ids already recorded in this session's source-library dispatch artifact.",
                    },
                },
                "additionalProperties": False,
            },
            result_budget=24000,
        ),
    )
    return declarations


def read_only_project_tool_sources(
    *,
    service: AgentSessionService,
    source_library_lister: SourceLibraryLister | None = None,
    structured_data_searcher: StructuredDataSearcher | None = None,
    system_projection_provider: Callable[[], SystemProjection] | None = None,
) -> tuple[ProjectToolAuthorSource, ...]:
    context = ReadOnlyToolContext(
        service,
        source_library_lister,
        structured_data_searcher or query_project_structured_data,
        system_projection_provider,
    )
    return project_tool_sources(
        _read_tool_declarations(context),
        scope_source="original read-only request scope and per-tool explicit manifest handles",
        permission_source="CoreToolSpec.permission and original read-only service boundaries",
        failure_family="original read-only observation status, dataset errors, and exceptions",
        readback_semantics="compact projection of already-stored data; no dispatch or writer",
    )


def system_projection_project_tool_source(
    *,
    service: AgentSessionService,
    system_projection_provider: Callable[[], SystemProjection],
) -> ProjectToolAuthorSource:
    context = ReadOnlyToolContext(
        service,
        None,
        query_project_structured_data,
        system_projection_provider,
    )
    return project_tool_sources(
        (
            _read_tool_declaration(
                context,
                system_projection_inspect,
                name=SYSTEM_INSPECT_TOOL_NAME,
                description=SYSTEM_INSPECT_DESCRIPTION,
                input_schema=system_inspect_input_schema(),
            ),
        ),
        scope_source="read-only MRW system semantic projection; project_key is observation context only",
        permission_source="CoreToolSpec.permission plus original read-only projection boundary",
        failure_family="system_projection_input_invalid, system_ref_not_found, stale_projection, and item budget failures",
        readback_semantics="one bounded immutable system projection page; referenced tools remain owned by their original registry handlers",
    )[0]

def _core_envelope_bytes(result: JSONObject, *, call_id: str, summary: str) -> int:
    envelope = CoreToolResult(
        call_id=call_id,
        tool_name=SYSTEM_INSPECT_TOOL_NAME,
        status="completed",
        model_summary=summary,
        ui_summary=summary,
        structured_content={"result": result},
    )
    return len(json.dumps(asdict(envelope), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _core_failure_bytes(result: CoreToolResult) -> int:
    return len(json.dumps(asdict(result), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def system_projection_inspect(
    tool_call: CoreToolCall, request: AgentCoreRequest, *, context: ReadOnlyToolContext
) -> CoreToolResult:
    provider = context.system_projection_provider
    if provider is None:
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="failed",
            model_summary="System projection provider is not configured.",
            error={"code": "system_projection_unavailable", "message": "System projection provider is not configured."},
        )
    try:
        result = inspect_system_projection_with_budget(
            provider(),
            tool_call.arguments,
            request.project_key,
            byte_budget=8192 if tool_call.arguments.get("limit", 8) == 8 else 16384,
            measure=lambda value: _core_envelope_bytes(
                value,
                call_id=tool_call.call_id,
                summary="read MRW system projection",
            ),
        )
    except SystemProjectionError as exc:
        failure = CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="failed",
            model_summary=str(exc),
            error={"code": exc.code, "message": str(exc)},
        )
        budget = 8192 if tool_call.arguments.get("limit", 8) == 8 else 16384
        if exc.code == "system_projection_item_too_large" and _core_failure_bytes(failure) > budget:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary="System projection caller identity exceeds the transport envelope budget.",
                error={
                    "code": "system_projection_transport_too_large",
                    "message": "caller identity exceeds the transport envelope budget",
                },
            )
        return failure
    return CoreToolResult(
        call_id=tool_call.call_id,
        tool_name=tool_call.tool_name,
        status="completed",
        model_summary="read MRW system projection",
        ui_summary="read MRW system projection",
        structured_content={"result": result},
    )


def capability_catalog(
    tool_call: CoreToolCall, request: AgentCoreRequest, *, context: ReadOnlyToolContext
) -> CoreToolResult:
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
    if context.system_projection_provider is not None:
        projection = context.system_projection_provider()
        for item in items:
            identity = str(item.get("tool_name") or item.get("capability_id") or item.get("name") or "")
            item["system_refs"] = list(projection.system_refs_for_tool(identity))
    return _read_result(
        tool_call,
        status=core_status("completed"),
        summary=f"listed {len(items)} available agent capabilities",
        result={"items": items, "total": len(items)},
    )


def tool_pool_list(
    tool_call: CoreToolCall, request: AgentCoreRequest, *, context: ReadOnlyToolContext
) -> CoreToolResult:
    project_key = request.project_key
    pool = AgentToolPoolAssembler(service=context.service).assemble(
        ToolPoolRequest(
            project_key=project_key, agent_mode="read_only", feature_flags=default_agent_runtime_feature_flags()
        )
    )
    counts = json_object(pool.get("counts") or {})
    return _read_result(
        tool_call,
        status=core_status("completed"),
        summary=f"assembled tool pool: core={counts.get('core') or 0}, deferred={counts.get('deferred') or 0}, disabled={counts.get('disabled') or 0}, approval_required={counts.get('approval_required') or 0}",
        result=pool,
    )


def tool_search(tool_call: CoreToolCall, request: AgentCoreRequest, *, context: ReadOnlyToolContext) -> CoreToolResult:
    project_key = request.project_key
    query = _as_text(tool_call.arguments.get("query")) or request.message
    limit = _limit(tool_call, 12)
    result = AgentToolPoolAssembler(service=context.service).search(
        query=query,
        request=ToolPoolRequest(
            project_key=project_key, agent_mode="read_only", feature_flags=default_agent_runtime_feature_flags()
        ),
        limit=limit,
    )
    if context.system_projection_provider is not None:
        projection = context.system_projection_provider()
        projected_items = _objects(result.get("items"))
        for item in projected_items:
            identity = str(item.get("tool_name") or item.get("capability_id") or item.get("name") or "")
            item["system_refs"] = list(projection.system_refs_for_tool(identity))
        result["items"] = projected_items
    return _read_result(
        tool_call,
        status=core_status("completed"),
        summary=f"matched {result.get('total') or 0} agent tools for query",
        result=result,
    )


def session_context(
    tool_call: CoreToolCall, request: AgentCoreRequest, *, context: ReadOnlyToolContext
) -> CoreToolResult:
    session_id = request.session_id
    bundle = _session_bundle(context, session_id)
    if isinstance(bundle, Failure):
        return runtime_failure_result(tool_call, bundle)
    tasks = _objects(bundle.get("tasks") or [])
    events = _objects(bundle.get("events") or [])
    artifacts = _objects(bundle.get("artifacts") or [])
    messages = _objects(bundle.get("messages") or [])
    recent_tool_results = _recent_tool_results(events)
    return _read_result(
        tool_call,
        status=core_status("completed"),
        summary=f"read session context: tasks={len(tasks)}, events={len(events)}, artifacts={len(artifacts)}, tool_results={len(recent_tool_results)}",
        result={
            "session": bundle.get("session"),
            "task_count": len(tasks),
            "event_count": len(events),
            "artifact_count": len(artifacts),
            "approval_count": len(json_list(bundle.get("approvals") or [])),
            "recent_tasks": tasks[-5:],
            "recent_events": events[-8:],
            "recent_messages": messages[-4:],
            "recent_tool_results": recent_tool_results,
        },
    )


def _project_summary_payload(
    context: ReadOnlyToolContext, *, project_key: str | None, session_id: str
) -> JSONObject | Failure:
    source_summary = _list_source_library_items(context=context, project_key=project_key, limit=200)
    bundle = _session_bundle(context, session_id)
    if isinstance(bundle, Failure):
        return bundle
    channels: dict[str, int] = {}
    enabled_count = 0
    for item in _objects(source_summary["items"]):
        channel_key = _as_text(item.get("channel_key")) or "unknown"
        channels[channel_key] = channels.get(channel_key, 0) + 1
        if item.get("enabled") is True:
            enabled_count += 1
    return {
        "project_key": project_key,
        "session": bundle.get("session"),
        "session_counts": {
            "tasks": len(json_list(bundle.get("tasks") or [])),
            "events": len(json_list(bundle.get("events") or [])),
            "artifacts": len(json_list(bundle.get("artifacts") or [])),
            "messages": len(json_list(bundle.get("messages") or [])),
        },
        "source_library": {
            "total": source_summary["total"],
            "enabled": enabled_count,
            "channels": channels,
            "sample": _objects(source_summary["items"])[:8],
        },
    }


def project_summary(
    tool_call: CoreToolCall, request: AgentCoreRequest, *, context: ReadOnlyToolContext
) -> CoreToolResult:
    result = _project_summary_payload(context, project_key=request.project_key, session_id=request.session_id)
    if isinstance(result, Failure):
        return runtime_failure_result(tool_call, result)
    return _read_result(
        tool_call, status="completed", summary=f"read project summary for {request.project_key or '-'}", result=result
    )


def source_library_list(
    tool_call: CoreToolCall, request: AgentCoreRequest, *, context: ReadOnlyToolContext
) -> CoreToolResult:
    project_key = request.project_key
    limit = _limit(tool_call, 12)
    listed = _list_source_library_items(context=context, project_key=project_key, limit=limit)
    return _read_result(
        tool_call,
        status=core_status(listed["status"]),
        summary=str(listed["summary"]),
        result={"items": _objects(listed["items"]), "total": listed["total"], "project_key": project_key},
        error=json_object(listed.get("error")) or None,
    )


def _search_structured_data(
    context: ReadOnlyToolContext,
    *,
    project_key: str | None,
    query: str | None,
    limit: int,
    datasets: list[str] | None = None,
) -> StructuredDataRead:
    try:
        result = json_object(
            context.structured_data_searcher(
                project_key=project_key, query=query, limit=max(1, min(50, _integer(limit or 12))), datasets=datasets
            )
        )
    except Exception as exc:
        return StructuredDataRead(
            status=core_status("failed"),
            summary=f"structured project data search failed: {exc}",
            result={"project_key": project_key, "query": query, "items": [], "dataset_results": []},
            error=json_object({"type": exc.__class__.__name__, "message": str(exc)}) or None,
        )
    if "model_evidence_manifest" not in result:
        result["model_evidence_manifest"] = build_structured_data_model_evidence_manifest(
            project_key=project_key,
            query=query,
            items=_structured_records(_objects(result.get("items") or [])),
            limit=max(12, _integer(limit or 12)),
        )
    mode = str(result.get("query_mode") or "search")
    total_matches = _integer(result.get("total_matches") or 0)
    total_stored_rows = _integer(result.get("total_stored_rows") or 0)
    error_count = len(json_list(result.get("errors") or []))
    summary = (
        f"read structured project data inventory: datasets={len(json_list(result.get('inventory') or []))}, samples={total_matches}, stored_rows={total_stored_rows}"
        if mode == "inventory"
        else f"searched structured project data: matches={total_matches}, datasets={len(json_list(result.get('dataset_results') or []))}, stored_rows={total_stored_rows}"
    )
    if result.get("fallback_used"):
        summary = f"{summary}, returned_inventory_fallback={len(json_list(result.get('items') or []))}"
    if error_count:
        summary = f"{summary}, dataset_errors={error_count}"
    status = "completed" if str(result.get("project_key") or "").strip() else "failed"
    return StructuredDataRead(
        status=core_status(status),
        summary=summary,
        result=result,
        error=json_object(
            {"type": "dataset_errors", "items": json_list(result.get("errors") or [])}
            if status == "failed" and error_count
            else None
        )
        or None,
    )


def project_structured_data_search(
    tool_call: CoreToolCall, request: AgentCoreRequest, *, context: ReadOnlyToolContext
) -> CoreToolResult:
    mode = _as_text(tool_call.arguments.get("mode")) or "search"
    query = _as_text(tool_call.arguments.get("query")) or request.message
    if mode == "inventory":
        query = None
    observation = _search_structured_data(
        context,
        project_key=request.project_key,
        query=query,
        limit=_limit(tool_call, 12),
        datasets=_datasets(tool_call.arguments.get("datasets")),
    )
    return _read_result(
        tool_call,
        status=observation.status,
        summary=observation.summary,
        result=observation.result,
        error=observation.error,
    )


def project_structured_data_item_read(
    tool_call: CoreToolCall, request: AgentCoreRequest, *, context: ReadOnlyToolContext
) -> CoreToolResult:
    project_key = _as_text(tool_call.arguments.get("project_key")) or request.project_key
    dataset = _as_text(tool_call.arguments.get("dataset")) or None
    record_id = _as_text(tool_call.arguments.get("record_id")) or None
    item_id = _as_text(tool_call.arguments.get("item_id")) or None
    resource_uri = _as_text(tool_call.arguments.get("resource_uri")) or None
    try:
        result = json_object(
            read_project_structured_data_item(
                project_key=project_key,
                dataset=dataset,
                record_id=record_id,
                item_id=item_id,
                resource_uri=resource_uri,
            )
        )
    except Exception as exc:
        dataset_text, record_text = _parse_structured_read_ref(
            dataset=dataset, record_id=record_id, item_id=item_id, resource_uri=resource_uri
        )
        result: JSONObject = {
            "contract_version": "project.structured_data.item.read.v1",
            "project_key": project_key,
            "dataset": dataset_text,
            "record_id": record_text,
            "item": None,
            "model_evidence_manifest": [],
            "resource_uri": resource_uri,
            "cleaned_text": "",
            "source_ref": None,
            "quality_flags": {},
            "errors": [{"type": exc.__class__.__name__, "message": str(exc)}],
        }
    if not result.get("item"):
        fallback = _read_structured_item_via_searcher(
            context=context,
            project_key=project_key,
            dataset=dataset,
            record_id=record_id,
            item_id=item_id,
            resource_uri=resource_uri,
        )
        if fallback.get("item"):
            result = fallback
    errors = _objects(result.get("errors") or [])
    item = json_object(result.get("item")) or None
    status = "completed" if item else "failed"
    title = item.get("title") if item else None
    return _read_result(
        tool_call,
        status=core_status(status),
        summary=f"read structured project record {result.get('dataset')}/{result.get('record_id')}{(f': {title}' if title else '')}"
        if item
        else "structured project record was not readable",
        result=result,
        error=json_object({"type": "structured_item_read_failed", "items": errors} if status == "failed" else None)
        or None,
    )


def project_structured_data_items_read(
    tool_call: CoreToolCall, request: AgentCoreRequest, *, context: ReadOnlyToolContext
) -> CoreToolResult:
    project_key = _as_text(tool_call.arguments.get("project_key")) or request.project_key
    items = _structured_records(tool_call.arguments.get("items"))
    limit = _limit(tool_call, 8)
    result = json_object(read_project_structured_data_items(project_key=project_key, items=items, limit=limit))
    recovered: list[JSONObject] = []
    if not result.get("items"):
        for ref in items[: max(1, min(25, _integer(limit or 8)))]:
            candidate = _read_structured_item_via_searcher(
                context=context,
                project_key=_as_text(ref.get("project_key")) or project_key,
                dataset=_as_text(ref.get("dataset")) or None,
                record_id=ref.get("record_id"),
                item_id=_as_text(ref.get("item_id")) or None,
                resource_uri=_as_text(ref.get("resource_uri")) or None,
            )
            if candidate.get("item"):
                recovered.append(candidate)
    if recovered:
        result["items"] = recovered
        manifest: list[JSONObject] = []
        for candidate in recovered:
            manifest.extend(_objects(candidate.get("model_evidence_manifest") or []))
        result["model_evidence_manifest"] = manifest
        result["total_returned"] = len(recovered)
    total = _integer(result.get("total_returned") or len(json_list(result.get("items") or [])))
    status = "completed" if total else "failed"
    return _read_result(
        tool_call,
        status=core_status(status),
        summary=f"read {total} structured project record(s)",
        result=result,
        error=json_object(
            {"type": "structured_items_read_failed", "items": json_list(result.get("errors") or [])}
            if status == "failed"
            else None
        )
        or None,
    )


def project_context_resource_read(
    tool_call: CoreToolCall, request: AgentCoreRequest, *, context: ReadOnlyToolContext
) -> CoreToolResult:
    project_key = _as_text(tool_call.arguments.get("project_key")) or request.project_key
    resource_uri = _as_text(tool_call.arguments.get("resource_uri"))
    result = json_object(read_project_context_resource(project_key=project_key, resource_uri=resource_uri))
    if not result.get("item") and str(resource_uri or "").startswith("project://structured/"):
        result = _read_structured_item_via_searcher(context=context, project_key=project_key, resource_uri=resource_uri)
    status = "completed" if result.get("item") else "failed"
    return _read_result(
        tool_call,
        status=core_status(status),
        summary="read project context resource"
        if status == "completed"
        else "project context resource was not readable",
        result=result,
        error=json_object(
            {"type": "context_resource_read_failed", "items": json_list(result.get("errors") or [])}
            if status == "failed"
            else None
        )
        or None,
    )


def _read_structured_item_via_searcher(
    *,
    context: ReadOnlyToolContext,
    project_key: str | None,
    dataset: str | None = None,
    record_id: object | None = None,
    item_id: str | None = None,
    resource_uri: str | None = None,
) -> JSONObject:
    dataset_text, record_text = _parse_structured_read_ref(
        dataset=dataset, record_id=record_id, item_id=item_id, resource_uri=resource_uri
    )
    if not dataset_text or not record_text:
        return {
            "item": None,
            "errors": [{"type": "missing_record_ref", "message": "dataset and record_id are required"}],
        }
    try:
        searched = json_object(
            context.structured_data_searcher(
                project_key=project_key, query=record_text, limit=50, datasets=[dataset_text]
            )
        )
    except Exception as exc:
        return {"item": None, "errors": [{"type": exc.__class__.__name__, "message": str(exc)}]}
    candidates = _objects(searched.get("items") or [])
    item = next(
        (
            candidate
            for candidate in candidates
            if str(candidate.get("record_id") or candidate.get("id") or "") == record_text
        ),
        None,
    )
    if item is None and candidates:
        item = candidates[0]
    manifest = build_structured_data_model_evidence_manifest(
        project_key=project_key, query=None, items=_structured_records([item] if item else []), limit=1
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
    tool_call: CoreToolCall, request: AgentCoreRequest, *, context: ReadOnlyToolContext
) -> CoreToolResult:
    project_key = request.project_key
    session_id = request.session_id
    query = _as_text(tool_call.arguments.get("query")) or request.message
    limit = _limit(tool_call, 8)
    query_text = _as_text(query)
    material_intent = classify_material_intent(query_text)
    safe_limit = max(1, min(50, _integer(limit or 8)))
    summary = _project_summary_payload(context, project_key=project_key, session_id=session_id)
    if isinstance(summary, Failure):
        return runtime_failure_result(tool_call, summary)
    structured = _search_structured_data(context, project_key=project_key, query=query_text, limit=safe_limit).result
    artifacts = _artifact_search_payload(context, session_id=session_id, query=query_text, limit=safe_limit)
    if isinstance(artifacts, Failure):
        return runtime_failure_result(tool_call, artifacts)
    listed = _list_source_library_items(context=context, project_key=project_key, limit=safe_limit)
    source_catalog: JSONObject = {
        "items": _objects(listed["items"]),
        "total": listed["total"],
        "project_key": project_key,
    }
    writing_documents = _list_writing_documents(project_key=project_key, limit=safe_limit)
    inventory = _objects(structured.get("inventory") or [])
    structured_items = _objects(structured.get("items") or [])
    artifact_items = _objects(artifacts.get("items") or [])
    source_items = _objects(source_catalog.get("items") or [])
    writing_items = _objects(writing_documents.get("items") or [])
    internal_existing_count = _integer(structured.get("total_stored_rows") or 0) + len(writing_items)
    internal_generated_count = _integer(artifacts.get("total") or len(artifact_items))
    source_catalog_count = _integer(source_catalog.get("total") or len(source_items))
    missing_evidence: list[str] = []
    if query_text and (not structured_items) and (not artifact_items) and (not writing_items):
        missing_evidence.append("No matching internal material was found for the current query.")
    if query_text and source_catalog_count == 0 and (material_intent.scope in {"external", "mixed"}):
        missing_evidence.append("No source-catalog entry is currently available for the external collection direction.")
    evidence: list[JSONObject] = []
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
    model_evidence_manifest = _objects(structured.get("model_evidence_manifest") or [])[: max(1, safe_limit * 2)]
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
    material_categories: JSONObject = {
        INTERNAL_EXISTING: {
            "label": category_label(INTERNAL_EXISTING),
            "structured_datasets": len(inventory),
            "stored_rows": _integer(structured.get("total_stored_rows") or 0),
            "writing_documents": len(writing_items),
        },
        INTERNAL_GENERATED: {"label": category_label(INTERNAL_GENERATED), "artifacts": internal_generated_count},
        SOURCE_CATALOG: {
            "label": category_label(SOURCE_CATALOG),
            "items": source_catalog_count,
            "enabled": _integer(json_object(summary.get("source_library") or {}).get("enabled") or 0),
        },
        EXTERNAL_DISCOVERY: {
            "label": category_label(EXTERNAL_DISCOVERY),
            "suggested": bool(missing_evidence and material_intent.scope in {"external", "mixed"}),
        },
    }
    result: JSONObject = {
        "contract_version": "project.context.bundle.v1",
        "project_key": project_key,
        "query": query_text,
        "material_intent": json_object(material_intent.to_dict()),
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
    return _read_result(
        tool_call,
        status=core_status("completed"),
        summary=f"built project material context bundle: internal_existing={internal_existing_count}, generated_artifacts={internal_generated_count}, source_catalog_items={source_catalog_count}, missing={len(missing_evidence)}",
        result=result,
    )


def source_library_search(
    tool_call: CoreToolCall, request: AgentCoreRequest, *, context: ReadOnlyToolContext
) -> CoreToolResult:
    project_key = request.project_key
    query = _as_text(tool_call.arguments.get("query")) or request.message
    limit = _limit(tool_call, 12)
    listed = _list_source_library_items(context=context, project_key=project_key, limit=200)
    query_text = _as_text(query)
    matches = [item for item in _objects(listed["items"]) if _matches_query(item, query_text)]
    return _read_result(
        tool_call,
        status=core_status(listed["status"]),
        summary=f"matched {len(matches)} source-library items for query",
        result={
            "query": query_text,
            "items": matches[: max(1, limit)],
            "total": len(matches),
            "source_total": listed["total"],
            "project_key": project_key,
        },
        error=json_object(listed.get("error")) or None,
    )


def source_library_inspect(
    tool_call: CoreToolCall, request: AgentCoreRequest, *, context: ReadOnlyToolContext
) -> CoreToolResult:
    project_key = request.project_key
    item_key = _as_text(tool_call.arguments.get("item_key")) or _extract_source_item_key(request.message)
    key = _as_text(item_key)
    if not key:
        return _read_result(
            tool_call,
            status=core_status("skipped"),
            summary="source-library inspect skipped because no item_key was supplied",
            result={"item": None, "project_key": project_key},
        )
    listed = _list_source_library_items(context=context, project_key=project_key, limit=500)
    item = next(
        (candidate for candidate in _objects(listed["raw_items"]) if _as_text(candidate.get("item_key")) == key), None
    )
    status = "completed" if item else "skipped"
    summary = f"inspected source-library item {key}" if item else f"source-library item {key} not found"
    return _read_result(
        tool_call, status=core_status(status), summary=summary, result={"item": item, "project_key": project_key}
    )


def _artifact_search_payload(
    context: ReadOnlyToolContext, *, session_id: str, query: str | None, limit: int
) -> JSONObject | Failure:
    query_text = _as_text(query).lower()
    query_tokens = _query_tokens(query_text)
    bundle = _session_bundle(context, session_id)
    if isinstance(bundle, Failure):
        return bundle
    artifacts = _objects(bundle.get("artifacts") or [])
    matches: list[JSONObject] = []
    for artifact in artifacts:
        haystack = " ".join(
            (
                _as_text(artifact.get(key)).lower()
                for key in ("artifact_id", "artifact_type", "name", "path", "summary", "mime_type")
            )
        )
        if not query_text or query_text in haystack or any((token in haystack for token in query_tokens)):
            matches.append(artifact)
    return {"query": query, "items": matches[: max(1, limit)], "total": len(matches)}


def artifact_search(
    tool_call: CoreToolCall, request: AgentCoreRequest, *, context: ReadOnlyToolContext
) -> CoreToolResult:
    query = _as_text(tool_call.arguments.get("query")) or request.message
    result = _artifact_search_payload(context, session_id=request.session_id, query=query, limit=_limit(tool_call, 8))
    if isinstance(result, Failure):
        return runtime_failure_result(tool_call, result)
    return _read_result(
        tool_call, status="completed", summary=f"matched {result['total']} session artifacts", result=result
    )


def artifact_read(
    tool_call: CoreToolCall, request: AgentCoreRequest, *, context: ReadOnlyToolContext
) -> CoreToolResult:
    session_id = request.session_id
    artifact_ref = _as_text(tool_call.arguments.get("artifact_ref")) or None
    ref = _as_text(artifact_ref)
    bundle = _session_bundle(context, session_id)
    if isinstance(bundle, Failure):
        return runtime_failure_result(tool_call, bundle)
    artifacts = _objects(bundle.get("artifacts") or [])
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
                    (
                        _as_text(candidate.get(key)).lower()
                        for key in ("artifact_id", "artifact_type", "name", "path", "summary", "mime_type")
                    )
                )
            ),
            None,
        )
    if not artifact and artifacts:
        artifact = artifacts[-1]
    return _read_result(
        tool_call,
        status=core_status("completed" if artifact else "skipped"),
        summary="read session artifact" if artifact else "no session artifact was available to read",
        result={"artifact": artifact},
    )


def workflow_graph_list(
    tool_call: CoreToolCall, request: AgentCoreRequest, *, context: ReadOnlyToolContext
) -> CoreToolResult:
    limit = _limit(tool_call, 12)
    try:
        from app.services.workflow_graph import compiler

        compiled = [_compact_workflow_graph(json_object(row or {})) for row in compiler.list_compiled(limit=limit)]
        templates = json_object(compiler.list_templates())
        template_items = json_list(templates.get("items"))
        return _read_result(
            tool_call,
            status=core_status("completed"),
            summary=f"listed {len(compiled)} compiled workflow graphs and {len(template_items)} templates",
            result={
                "compiled_graphs": compiled,
                "templates": template_items[: max(1, limit)],
                "total_compiled": len(compiled),
                "total_templates": len(template_items),
            },
        )
    except Exception as exc:
        return _read_result(
            tool_call,
            status=core_status("failed"),
            summary=f"workflow graph list failed: {exc}",
            result={"compiled_graphs": [], "templates": []},
            error=json_object({"type": exc.__class__.__name__, "message": str(exc)}) or None,
        )


def workflow_graph_inspect(
    tool_call: CoreToolCall, request: AgentCoreRequest, *, context: ReadOnlyToolContext
) -> CoreToolResult:
    graph_id = _as_text(tool_call.arguments.get("graph_id")) or _extract_graph_id(request.message)
    resolved_graph_id = _as_text(graph_id)
    if not resolved_graph_id:
        return _read_result(
            tool_call,
            status=core_status("skipped"),
            summary="workflow graph inspect skipped because no graph_id was supplied",
            result={"graph": None},
        )
    try:
        from app.services.workflow_graph import compiler

        graph = json_object(compiler.get_compiled(resolved_graph_id))
        compact = _compact_workflow_graph(graph)
        nodes = json_object(graph.get("nodes") or {})
        return _read_result(
            tool_call,
            status=core_status("completed"),
            summary=f"inspected workflow graph {resolved_graph_id}",
            result={
                "graph": compact,
                "nodes": nodes,
                "edges": {
                    "incoming": json_object(graph.get("incoming_edges") or {}),
                    "outgoing": json_object(graph.get("outgoing_edges") or {}),
                },
                "options": json_object(graph.get("options") or {}),
            },
        )
    except Exception as exc:
        return _read_result(
            tool_call,
            status=core_status("failed"),
            summary=f"workflow graph inspect failed for {resolved_graph_id}: {exc}",
            result={"graph_id": resolved_graph_id},
            error=json_object({"type": exc.__class__.__name__, "message": str(exc)}) or None,
        )


def ingest_status_read(
    tool_call: CoreToolCall, request: AgentCoreRequest, *, context: ReadOnlyToolContext
) -> CoreToolResult:
    session_id = request.session_id
    limit = _limit(tool_call, 12)
    explicit_task_ids = _source_library_task_ids(tool_call.arguments.get("task_id"))
    if explicit_task_ids is None:
        return _read_result(
            tool_call,
            status=core_status("failed"),
            summary="task_id must be a task id string or array of task id strings",
            result={"session_id": session_id},
            error={"type": "invalid_task_id", "message": "task_id must be a string or array of strings"},
        )
    try:
        from app.services.job_logger import list_jobs

        jobs = [
            item
            for item in list_jobs(limit=max(20, limit * 3))
            if "ingest" in _as_text(item.get("job_type")).lower()
            or "source_library" in _as_text(item.get("job_type")).lower()
            or "source_library" in json.dumps(item.get("params") or {}, ensure_ascii=False, default=str).lower()
        ]
    except Exception as exc:
        jobs = []
        job_error = {"type": exc.__class__.__name__, "message": str(exc)}
    else:
        job_error = None
    bundle = _session_bundle(context, session_id)
    if isinstance(bundle, Failure):
        return runtime_failure_result(tool_call, bundle)
    dispatch_error: JSONObject | None = None
    dispatched_tasks: list[JSONObject] = []
    dispatched_tasks, dispatch_error = _read_source_library_dispatch_tasks(
        context=context,
        request=request,
        bundle=bundle,
        requested_task_ids=explicit_task_ids,
    )
    recent_tasks = [
        task
        for task in _objects(bundle.get("tasks"))
        if "ingest" in _as_text(task.get("task_type")).lower()
        or "source" in _as_text(task.get("subject")).lower()
        or "采集" in _as_text(task.get("subject"))
    ][-limit:]
    status_counts: dict[str, int] = {}
    for job in jobs:
        status = _as_text(job.get("status")) or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1
    status = "completed"
    if (not explicit_task_ids and job_error is not None) or dispatch_error is not None:
        status = "failed"
    return _read_result(
        tool_call,
        status=core_status(status),
        summary=(
            f"read ingest status: recent_jobs={len(jobs[:limit])}, session_tasks={len(recent_tasks)}, "
            f"dispatched_tasks={len(dispatched_tasks)}"
        ),
        result={
            "recent_jobs": jobs[: max(1, limit)],
            "job_status_counts": status_counts,
            "recent_session_tasks": recent_tasks,
            "dispatched_tasks": dispatched_tasks,
            "recent_jobs_error": job_error,
            "session_id": session_id,
        },
        error=json_object(dispatch_error or (job_error if not explicit_task_ids else None)) or None,
    )


def _source_library_task_ids(value: object) -> list[str] | None:
    if value is None:
        return []
    values: list[object] | None = [value] if isinstance(value, str) else (
        cast(list[object], value) if isinstance(value, list) else None
    )
    if values is None:
        return None
    task_ids: list[str] = []
    if len(values) > _SOURCE_LIBRARY_TASK_READ_LIMIT:
        return None
    for item in values:
        if not isinstance(item, str) or not item.strip():
            return None
        task_id = item.strip()
        if task_id not in task_ids:
            task_ids.append(task_id)
    return task_ids


def _authorized_source_library_dispatches(
    bundle: JSONObject, *, session_id: str, project_key: str | None
) -> dict[str, JSONObject]:
    authorized: dict[str, JSONObject] = {}
    artifacts = [
        item
        for item in _objects(bundle.get("artifacts"))
        if _as_text(item.get("name")) == _SOURCE_LIBRARY_DISPATCH_ARTIFACT_NAME
    ]
    requested_project = _as_text(project_key)
    for artifact in reversed(artifacts):
        metadata = json_object(artifact.get("metadata"))
        content = json_object(artifact.get("content_json"))
        if (
            _as_text(artifact.get("session_id")) != session_id
            or _as_text(content.get("session_id")) != session_id
            or _as_text(content.get("project_key")) != requested_project
            or _as_text(metadata.get("project_key")) != requested_project
            or _as_text(content.get("contract_version")) != _SOURCE_LIBRARY_DISPATCH_CONTRACT
        ):
            continue
        for record_value in reversed(json_list(content.get("dispatches"))):
            record = json_object(record_value)
            if (
                _as_text(record.get("session_id")) != session_id
                or _as_text(record.get("project_key")) != requested_project
            ):
                continue
            for item_value in reversed(json_list(record.get("items"))):
                item = json_object(item_value)
                task_id = _as_text(item.get("task_id"))
                item_key = _as_text(item.get("item_key"))
                if not task_id or not item_key or _as_text(item.get("skill_id")) != _SOURCE_LIBRARY_DISPATCH_SKILL:
                    continue
                authorized.setdefault(
                    task_id,
                    {"task_id": task_id, "item_key": item_key, "project_key": requested_project},
                )
    return authorized


def _read_source_library_dispatch_tasks(
    *,
    context: ReadOnlyToolContext,
    request: AgentCoreRequest,
    bundle: JSONObject,
    requested_task_ids: list[str],
) -> tuple[list[JSONObject], JSONObject | None]:
    project_key = _as_text(request.project_key)
    if not project_key and requested_task_ids:
        return [], {"type": "task_not_in_session", "message": "project_key is required to read a session dispatch"}
    if not project_key:
        return [], None
    authorized = _authorized_source_library_dispatches(
        bundle, session_id=request.session_id, project_key=project_key
    )
    for task_id in requested_task_ids:
        if task_id not in authorized:
            return [], {
                "type": "task_not_in_session",
                "message": f"task_id {task_id} is not an authorized dispatch item in this session/project",
            }
    task_ids = requested_task_ids or list(authorized)[:_SOURCE_LIBRARY_TASK_READ_LIMIT]
    if not task_ids:
        return [], None
    from app.celery_app import celery_app

    try:
        return [
            _source_library_task_readback(celery_app.AsyncResult, authorized[task_id])
            for task_id in task_ids
        ], None
    except Exception as exc:
        return [], {"type": exc.__class__.__name__, "message": str(exc)}


def _source_library_task_readback(
    read_result: Callable[[str], _AsyncResultView], dispatch: JSONObject
) -> JSONObject:
    from app.successor_runtime.runtime.process_observation import normalize_observed_status

    result = read_result(_as_text(dispatch.get("task_id")))
    raw_state = _as_text(getattr(result, "status", None)) or "UNKNOWN"
    ready = bool(result.ready())
    raw_state_lower = raw_state.lower()
    state_observed = ready or raw_state_lower not in {"pending", "unknown"}
    status = "unknown"
    if state_observed:
        status = normalize_observed_status(raw_state).lower()
    successful = bool(result.successful()) if ready else None
    readback: JSONObject = {
        **dispatch,
        "state": raw_state,
        "status": status,
        "state_observed": state_observed,
        "ready": ready,
        "successful": successful,
    }
    if not ready:
        return readback
    if successful:
        payload = json_object(result.result)
        terminal = json_object(payload.get("terminal_output"))
        if not terminal:
            from app.services.source_library.terminal_output import to_terminal_output_dto

            raw_payload: dict[str, object] = dict(payload)
            terminal = json_object(to_terminal_output_dto(raw_payload))
        if not _source_library_result_identity_matches(payload, terminal, dispatch):
            raise ValueError("source-library task result project/item does not match its dispatch record")
        readback["terminal_output"] = _bounded_source_library_terminal_output(
            terminal, _source_library_original_result(payload)
        )
    else:
        failure = result.result
        readback["error"] = (
            {"type": failure.__class__.__name__, "message": str(failure)}
            if isinstance(failure, BaseException)
            else {"type": "task_failed", "message": str(failure or "task failed")}
        )
    return readback


def _source_library_original_result(payload: JSONObject) -> JSONObject:
    for value in (
        payload.get("result"),
        json_object(payload.get("legacy_result")).get("result"),
        json_object(json_object(payload.get("terminal_output")).get("raw_snapshot")).get("result"),
    ):
        candidate = json_object(value)
        if candidate and ("candidate_pipeline" in candidate or "query_contract" in candidate):
            return candidate
    return {}


def _source_library_result_identity_matches(
    payload: JSONObject, terminal: JSONObject, dispatch: JSONObject
) -> bool:
    expected_project = _as_text(dispatch.get("project_key"))
    expected_item = _as_text(dispatch.get("item_key"))
    request = json_object(terminal.get("request"))
    terminal_item = json_object(terminal.get("item"))
    original_result = _source_library_original_result(payload)
    execution_request = json_object(original_result.get("execution_request"))
    if not execution_request:
        execution_request = json_object(
            json_object(json_object(payload.get("legacy_result")).get("result")).get("execution_request")
        )
    observed_project = [
        _as_text(payload.get("project_key")),
        _as_text(request.get("project_key")),
        _as_text(execution_request.get("project_key")),
    ]
    observed_item = [
        _as_text(payload.get("item_key")),
        _as_text(terminal_item.get("item_key")),
        _as_text(execution_request.get("item_key")),
    ]
    project_values = [value for value in observed_project if value]
    item_values = [value for value in observed_item if value]
    return (
        bool(project_values)
        and all(value == expected_project for value in project_values)
        and bool(item_values)
        and all(value == expected_item for value in item_values)
    )


def _bounded_source_library_terminal_output(terminal: JSONObject, original_result: JSONObject) -> JSONObject:
    results = json_object(terminal.get("results"))
    records = [json_object(item) for item in json_list(results.get("records"))]
    pipeline = json_object(
        original_result.get("candidate_pipeline")
        or json_object(terminal.get("raw_snapshot")).get("candidate_pipeline")
        or terminal.get("candidate_pipeline")
    )
    query_contract = json_object(pipeline.get("query_contract"))
    if not query_contract:
        query_contract = json_object(original_result.get("query_contract"))
    bounded_pipeline: JSONObject = {
        key: pipeline[key]
        for key in ("detail_fetch", "search_route")
        if key in pipeline
    }
    bounded_pipeline["query_contract"] = {
        "statuses": query_contract.get("statuses"),
        "reason_codes": query_contract.get("reason_codes"),
        "discovery_budget": json_object(query_contract.get("discovery_budget")),
        "exploration_requests": [
            json_object(item)
            for item in json_list(query_contract.get("exploration_requests"))[:_SOURCE_LIBRARY_TASK_READ_LIMIT]
        ],
        "exploration_attempts": [
            json_object(item)
            for item in json_list(query_contract.get("exploration_attempts"))[:_SOURCE_LIBRARY_TASK_READ_LIMIT]
        ],
    }
    return {
        "status": terminal.get("status"),
        "source_mode": terminal.get("source_mode"),
        "item": json_object(terminal.get("item")),
        "request": json_object(terminal.get("request")),
        "results": {
            "records": [
                _bounded_source_library_record(item)
                for item in records[:_SOURCE_LIBRARY_TASK_READ_LIMIT]
            ],
            "record_count": len(records),
            "stats": json_object(results.get("stats")),
        },
        "errors": [json_object(item) for item in json_list(terminal.get("errors"))[:_SOURCE_LIBRARY_TASK_READ_LIMIT]],
        "candidate_pipeline": bounded_pipeline,
    }


def _bounded_source_library_record(record: JSONObject) -> JSONObject:
    bounded = dict(record)
    for field in ("content_text", "summary"):
        value = _as_text(record.get(field))
        if value and len(value) > _SOURCE_LIBRARY_RECORD_BODY_BUDGET:
            bounded[field] = value[:_SOURCE_LIBRARY_RECORD_BODY_BUDGET]
            bounded[f"{field}_truncated"] = True
    return bounded


def _list_writing_documents(*, project_key: str | None, limit: int) -> JSONObject:
    key = _as_text(project_key)
    if not key:
        return {
            "status": "skipped",
            "items": [],
            "total": 0,
            "error": {"type": "missing_project_key", "message": "project_key is required"},
        }
    try:
        from app.services.projects import bind_project
        from app.services.writing.document_service import list_documents

        with bind_project(key):
            raw_items = list_documents(project_key=key, limit=max(1, limit))
    except Exception as exc:
        return {
            "status": "failed",
            "items": [],
            "total": 0,
            "error": {"type": exc.__class__.__name__, "message": str(exc)},
        }
    items: list[JSONObject] = []
    for item in _objects(raw_items):
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


def _list_source_library_items(*, context: ReadOnlyToolContext, project_key: str | None, limit: int) -> JSONObject:
    if context.source_library_lister is None:
        return {
            "status": "skipped",
            "summary": "source-library discovery unavailable in this runtime",
            "items": [],
            "raw_items": [],
            "total": 0,
        }
    try:
        raw_items = json_list(context.source_library_lister(project_key) or [])
    except Exception as exc:
        return {
            "status": "failed",
            "summary": f"source-library discovery failed: {exc}",
            "items": [],
            "raw_items": [],
            "total": 0,
            "error": {"type": exc.__class__.__name__, "message": str(exc)},
        }
    compact = [_compact_source_item(json_object(item or {})) for item in raw_items]
    return {
        "status": "completed",
        "summary": f"discovered {len(raw_items)} source-library items for project {project_key or '-'}",
        "items": compact[: max(1, limit)],
        "raw_items": [json_object(item) for item in raw_items],
        "total": len(raw_items),
    }


def _recent_tool_results(events: list[JSONObject], *, limit: int = 8) -> list[JSONObject]:
    out: list[JSONObject] = []
    for event in events:
        if str(event.get("event_type") or "") != "interactive_agent.tool_call_result":
            continue
        payload = json_object(event.get("payload") or {})
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


def _compact_result_for_core(tool_name: str, result: JSONObject) -> JSONObject:
    """Keep tool results useful for the model/UI without replaying legacy envelopes."""
    name = str(tool_name or "").strip()
    payload = result
    if name == "agent_runtime.tool.search":
        raw_items = _objects(payload.get("items"))
        compact_items = [
            json_object(compact_json_value(item, max_items=20, max_depth=4))
            for item in raw_items[:12]
        ]
        if len(raw_items) > 12:
            compact_items.append({"_truncated": True, "_omitted_count": len(raw_items) - 12})
        for raw_item, compact_item in zip(raw_items[:12], compact_items):
            compact_item["system_refs"] = list(
                value for value in json_list(raw_item.get("system_refs"))
            )
        return {
            "query": payload.get("query"),
            "items": compact_items,
            "total": payload.get("total"),
            "source_total": payload.get("source_total"),
            "project_key": payload.get("project_key"),
        }
    if name == "project.summary.read":
        session = json_object(payload.get("session"))
        return {
            "project_key": payload.get("project_key"),
            "session": compact_session(session),
            "session_counts": json_object(payload.get("session_counts")),
            "source_library": compact_json_value(payload.get("source_library"), max_items=10, max_depth=4),
        }
    if name == "project.structured_data.search":
        return {
            "project_key": payload.get("project_key"),
            "query": payload.get("query"),
            "query_mode": payload.get("query_mode"),
            "model_evidence_manifest": compact_json_value(
                payload.get("model_evidence_manifest"), max_items=16, max_depth=4
            ),
            "items": compact_json_value(payload.get("items"), max_items=12, max_depth=4),
            "inventory": compact_json_value(payload.get("inventory"), max_items=20, max_depth=3),
            "dataset_counts": json_object(payload.get("dataset_counts")),
            "dataset_total_rows": json_object(payload.get("dataset_total_rows")),
            "total_stored_rows": payload.get("total_stored_rows"),
            "total_matches": payload.get("total_matches"),
            "fallback_used": payload.get("fallback_used"),
            "errors": compact_json_value(payload.get("errors"), max_items=8, max_depth=3),
        }
    if name in {"project.structured_data.item.read", "project.context.resource.read"}:
        return {
            "project_key": payload.get("project_key"),
            "dataset": payload.get("dataset"),
            "record_id": payload.get("record_id"),
            "resource_uri": payload.get("resource_uri"),
            "item": compact_json_value(payload.get("item"), max_items=18, max_depth=5),
            "model_evidence_manifest": compact_json_value(
                payload.get("model_evidence_manifest"), max_items=12, max_depth=4
            ),
            "cleaned_text": compact_json_value(payload.get("cleaned_text"), max_items=6, max_depth=2),
            "source_ref": payload.get("source_ref"),
            "quality_flags": compact_json_value(payload.get("quality_flags"), max_items=8, max_depth=3),
            "errors": compact_json_value(payload.get("errors"), max_items=8, max_depth=3),
        }
    if name == "project.structured_data.items.read":
        return {
            "project_key": payload.get("project_key"),
            "items": compact_json_value(payload.get("items"), max_items=8, max_depth=5),
            "model_evidence_manifest": compact_json_value(
                payload.get("model_evidence_manifest"), max_items=12, max_depth=4
            ),
            "total_returned": payload.get("total_returned"),
            "errors": compact_json_value(payload.get("errors"), max_items=8, max_depth=3),
        }
    if name == "project.context.bundle":
        return {
            "project_key": payload.get("project_key"),
            "query": payload.get("query"),
            "material_intent": compact_json_value(payload.get("material_intent"), max_items=8, max_depth=4),
            "material_categories": compact_json_value(payload.get("material_categories"), max_items=8, max_depth=4),
            "model_evidence_manifest": compact_json_value(
                payload.get("model_evidence_manifest"), max_items=18, max_depth=4
            ),
            "evidence": compact_json_value(payload.get("evidence"), max_items=18, max_depth=4),
            "missing_evidence": compact_json_value(payload.get("missing_evidence"), max_items=8, max_depth=3),
            "source_catalog_note": payload.get("source_catalog_note"),
            "components": {
                "structured_data": compact_json_value(
                    json_object(json_object(payload.get("components")).get("structured_data")),
                    max_items=12,
                    max_depth=4,
                ),
                "writing_documents": compact_json_value(
                    json_object(json_object(payload.get("components")).get("writing_documents")),
                    max_items=8,
                    max_depth=4,
                ),
                "artifacts": compact_json_value(
                    json_object(json_object(payload.get("components")).get("artifacts")), max_items=8, max_depth=4
                ),
                "source_catalog": compact_json_value(
                    json_object(json_object(payload.get("components")).get("source_catalog")), max_items=8, max_depth=4
                ),
            },
        }
    if name == "writing.document.section.read":
        return {
            "project_key": payload.get("project_key"),
            "document": compact_json_value(payload.get("document"), max_items=12, max_depth=4),
            "section": compact_json_value(payload.get("section"), max_items=12, max_depth=4),
        }
    if name == "agent_session.context.read":
        return {
            "session": compact_session(json_object(payload.get("session"))),
            "task_count": payload.get("task_count"),
            "event_count": payload.get("event_count"),
            "artifact_count": payload.get("artifact_count"),
            "approval_count": payload.get("approval_count"),
            "recent_tasks": compact_json_value(payload.get("recent_tasks"), max_items=8, max_depth=4),
            "recent_messages": compact_json_value(payload.get("recent_messages"), max_items=6, max_depth=4),
            "recent_tool_results": compact_json_value(payload.get("recent_tool_results"), max_items=8, max_depth=4),
        }
    if name in {"source_library.item.list", "source_library.item.search"}:
        return {
            "project_key": payload.get("project_key"),
            "query": payload.get("query"),
            "total": payload.get("total"),
            "source_total": payload.get("source_total"),
            "items": compact_json_value(payload.get("items"), max_items=12, max_depth=3),
        }
    if name == "ingest.status.read":
        return {
            "session_id": payload.get("session_id"),
            "job_status_counts": json_object(payload.get("job_status_counts")),
            "recent_jobs": [_compact_job(json_object(item)) for item in json_list(payload.get("recent_jobs"))[:8]],
            "recent_session_tasks": compact_json_value(payload.get("recent_session_tasks"), max_items=5, max_depth=3),
            "dispatched_tasks": payload.get("dispatched_tasks"),
        }
    return json_object(compact_json_value(payload, max_items=20, max_depth=4))


def _compact_job(job: JSONObject) -> JSONObject:
    params = json_object(job.get("params"))
    display_meta = json_object(params.get("display_meta"))
    return {
        "id": job.get("id"),
        "job_type": job.get("job_type"),
        "status": job.get("status"),
        "item_key": params.get("item_key"),
        "project_key": params.get("project_key"),
        "summary": display_meta.get("summary"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "error": job.get("error"),
    }


def _session_bundle(context: ReadOnlyToolContext, session_id: str) -> JSONObject | Failure:
    bundle = context.service.get_session_bundle(session_id)
    if isinstance(bundle, Failure):
        return bundle
    return json_object(bundle)


def _integer(value: object) -> int:
    if not isinstance(value, (str, int, float)):
        raise TypeError("integer value is required")
    return int(value)


def _structured_records(value: object) -> list[StructuredRecord]:
    return [coerce_material_query_result_row(item) for item in _objects(value)]
