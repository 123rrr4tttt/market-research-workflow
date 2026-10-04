from __future__ import annotations

from collections.abc import Callable
import hashlib
import importlib
import inspect
import json
import os
from typing import Any

from functorial_kit import Failure

from app.services.agent_runtime.structured_data_quality import audit_project_structured_data_quality
from app.services.agent_runtime.structured_data_search import query_project_structured_data
from app.services.agent_sessions.service import AgentSessionService
from app.services.search.candidate_contracts import Candidate, CandidateSearchRequest
from app.services.search.candidate_search import discover_candidates
from app.services.search.vector_contracts import (
    AGENT_MATRIX_SEARCH_EVIDENCE_CONTRACT_VERSION,
    GLOBAL_VECTOR_OBJECT_CONTRACT_VERSION,
    SEARCH_EVIDENCE_HIT_CONTRACT_VERSION,
    SEARCH_RETRIEVAL_RUN_CONTRACT_VERSION,
    build_agent_matrix_evidence_hits,
    build_retrieval_run_record,
)
from app.services.source_library.source_candidate_trust import build_source_candidate_plan
from app.services.skill_runtime import list_registered_skills
from app.settings.config import settings

from .contracts import AgentCoreRequest, CoreEvent, CoreToolCall, CoreToolResult, CoreToolSpec
from .registry import CoreToolRegistry
from .tool_support import (
    _compact_json_value,
    _compact_skill_meta,
    _missing_project_result,
    _normalize_string_list,
    _resolve_project_key,
    _stable_hash,
    _utcnow_iso,
)
from .tool_contribution import (
    ProjectToolAuthorSource,
    register_project_tool_contributions,
)


SourceLibraryLister = Callable[[str | None], list[dict[str, Any]]]
StructuredDataSearcher = Callable[..., dict[str, Any]]


def query_project_tool_sources(
    *,
    service: AgentSessionService,
    source_library_lister: SourceLibraryLister | None = None,
    structured_data_searcher: StructuredDataSearcher | None = None,
) -> tuple[ProjectToolAuthorSource, ...]:
    """Build the query/discovery catalog from one authored semantic source each."""

    searcher = structured_data_searcher or query_project_structured_data
    return (
        ProjectToolAuthorSource(
            binding_id="facility.project.graph.search",
            version="1",
            tool_spec=_project_graph_search_spec(),
            handler=_project_graph_search_handler(searcher),
            executor_ref="project.graph.search",
            scope_source="AgentCoreRequest.project_key plus query and limit arguments",
            permission_source="CoreToolSpec.permission and project structured-data search boundary",
            failure_family="CoreToolResult.status/error from the original graph search handler",
            readback_semantics="read-only projection of already-stored graph-node search results",
        ),
        ProjectToolAuthorSource(
            binding_id="facility.project.structured_graph.query",
            version="1",
            tool_spec=_project_structured_graph_query_spec(),
            handler=_project_structured_graph_query_handler(searcher),
            executor_ref="project.structured_graph.query",
            scope_source="AgentCoreRequest.project_key plus query, datasets, and limit arguments",
            permission_source="CoreToolSpec.permission and project structured-data search boundary",
            failure_family="CoreToolResult.status/error from the original structured/graph query handler",
            readback_semantics="read-only combined structured-data and graph query projection",
        ),
        ProjectToolAuthorSource(
            binding_id="facility.project.structured_data.quality_audit",
            version="1",
            tool_spec=_project_structured_data_quality_audit_spec(),
            handler=_project_structured_data_quality_audit_handler(),
            executor_ref="project.structured_data.quality_audit",
            scope_source="AgentCoreRequest.project_key plus scan and sample limits",
            permission_source="CoreToolSpec.permission and read-only structured-data audit boundary",
            failure_family="CoreToolResult.status/error from the original structured-data audit handler",
            readback_semantics="read-only affected samples and cleaning recommendations; raw evidence remains unchanged",
        ),
        ProjectToolAuthorSource(
            binding_id="facility.chain.expand",
            version="1",
            tool_spec=_clue_chain_expand_spec(),
            handler=_clue_chain_expand_handler(service),
            executor_ref="chain.expand",
            scope_source="AgentCoreRequest project/session identity plus chain, frontier, mode, and query arguments",
            permission_source="CoreToolSpec.permission and session expansion-request write boundary",
            failure_family="CoreToolResult.status/error from clue-chain service adapter or session artifact write",
            readback_semantics="expansion requests, hops, and review candidates persist in the session artifact and remain pending review",
        ),
        ProjectToolAuthorSource(
            binding_id="facility.source.web.search",
            version="1",
            tool_spec=_source_web_search_spec(),
            handler=_source_web_search_handler(),
            executor_ref="source.web.search",
            scope_source="AgentCoreRequest.project_key plus bounded provider/query matrix arguments",
            permission_source="CoreToolSpec.permission and CandidateSearchRequest provider boundary",
            failure_family="CandidateSearchRequest provider failure plus CoreToolResult.status/error projection",
            readback_semantics="external provider candidates, observations, trust assessments, and retrieval-run evidence; no ingest or project write",
        ),
        ProjectToolAuthorSource(
            binding_id="facility.source.candidate.review",
            version="1",
            tool_spec=_source_candidate_review_spec(),
            handler=_source_candidate_review_handler(service),
            executor_ref="source.candidate.review",
            scope_source="AgentCoreRequest project/session identity plus one candidate review decision",
            permission_source="CoreToolSpec.permission and session candidate-review artifact write boundary",
            failure_family="CoreToolResult.status/error from candidate normalization or session artifact write",
            readback_semantics="review decision and next ingest payload persist in the session artifact with idempotent replay",
        ),
        ProjectToolAuthorSource(
            binding_id="facility.skill.search",
            version="1",
            tool_spec=_skill_search_spec(),
            handler=_skill_search_handler(),
            executor_ref="skill.search",
            scope_source="registered backend skill catalog plus public search filters",
            permission_source="CoreToolSpec.permission and registered skill catalog read boundary",
            failure_family="CoreToolResult.status/error from the original skill search handler",
            readback_semantics="registered read-only or explicitly included skill metadata",
        ),
        ProjectToolAuthorSource(
            binding_id="facility.source.discovery.plan",
            version="1",
            tool_spec=_source_discovery_plan_spec(),
            handler=_source_discovery_plan_handler(source_library_lister),
            executor_ref="source.discovery.plan",
            scope_source="AgentCoreRequest.project_key plus source-discovery planning arguments and source catalog read",
            permission_source="CoreToolSpec.permission and source trust planner read boundary",
            failure_family="CoreToolResult.status/error from the original source discovery handler",
            readback_semantics="derived no-fetch/no-write source candidate and trust plan",
        ),
        ProjectToolAuthorSource(
            binding_id="facility.skill.load",
            version="1",
            tool_spec=_skill_load_spec(),
            handler=_skill_load_handler(),
            executor_ref="skill.load",
            scope_source="registered backend skill catalog and model-authored skill_id",
            permission_source="CoreToolSpec.permission and registered skill catalog read boundary",
            failure_family="CoreToolResult.status/error from the original skill metadata handler",
            readback_semantics="registered skill metadata only; no skill invocation",
        ),
    )


def register_query_project_tools(
    *,
    registry: CoreToolRegistry,
    service: AgentSessionService,
    source_library_lister: SourceLibraryLister | None = None,
    structured_data_searcher: StructuredDataSearcher | None = None,
) -> Failure | None:
    """Register the whole query/discovery catalog before mutating the registry."""

    return register_project_tool_contributions(
        registry,
        query_project_tool_sources(
            service=service,
            source_library_lister=source_library_lister,
            structured_data_searcher=structured_data_searcher,
        ),
    )


def _skill_search_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="skill.search",
        title="Search Backend Skills",
        description_for_model=(
            "Search backend skills available to AgentCore. "
            "Use this before loading or invoking a specialized workflow/agent_batch/ingest skill when the exact skill id is unclear."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                "owner": {"type": "string"},
                "include_write_skills": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        source="skill",
        risk="read_only",
        permission="allow",
        concurrency="parallel",
        timeout_seconds=10,
        result_budget=8000,
        project_service_id="skill.search",
        metadata={"contract_version": "skill.search.v1", "implemented": True},
    )


def _skill_search_handler() -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        query = str(tool_call.arguments.get("query") or "").strip().lower()
        owner = str(tool_call.arguments.get("owner") or "").strip().lower()
        limit = max(1, min(50, int(tool_call.arguments.get("limit") or 12)))
        include_write = bool(tool_call.arguments.get("include_write_skills"))
        matches: list[dict[str, Any]] = []
        for skill in list_registered_skills():
            meta = _compact_skill_meta(dict(skill or {}))
            if not include_write and str(meta.get("concurrency_class") or "read_only") != "read_only":
                continue
            haystack = json.dumps(meta, ensure_ascii=False, sort_keys=True, default=str).lower()
            if query and query not in haystack:
                continue
            if owner and owner not in str(meta.get("owner") or "").lower():
                continue
            matches.append(meta)
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=f"Found {len(matches)} matching backend skill(s).",
            structured_content={
                "contract_version": "skill.search.v1",
                "query": query,
                "owner": owner or None,
                "include_write_skills": include_write,
                "items": matches[:limit],
                "total_matches": len(matches),
                "total_registered": len(list_registered_skills()),
            },
        )

    return handler


def _skill_load_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="skill.load",
        title="Load Backend Skill Metadata",
        description_for_model=(
            "Load full metadata for one backend skill id, including permissions and invocation contract hints. "
            "This is read-only and does not execute the skill."
        ),
        input_schema={
            "type": "object",
            "required": ["skill_id"],
            "properties": {"skill_id": {"type": "string"}},
            "additionalProperties": False,
        },
        source="skill",
        risk="read_only",
        permission="allow",
        concurrency="parallel",
        timeout_seconds=10,
        result_budget=8000,
        project_service_id="skill.load",
        metadata={"contract_version": "skill.load.v1", "implemented": True},
    )


def _skill_load_handler() -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        skill_id = str(tool_call.arguments.get("skill_id") or "").strip()
        if not skill_id:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary="skill_id is required.",
                error={"code": "missing_skill_id", "message": "skill_id is required"},
            )
        for skill in list_registered_skills():
            if str(skill.get("skill_id") or "").strip() != skill_id:
                continue
            meta = _compact_skill_meta(dict(skill or {}))
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="completed",
                model_summary=f"Loaded backend skill {skill_id}.",
                structured_content={
                    "contract_version": "skill.load.v1",
                    "skill": meta,
                    "tool_name": f"skill.{skill_id}",
                    "invocation": {
                        "payload_field": "payload",
                        "direct_tool_arguments_allowed": True,
                        "approval_required": str(meta.get("concurrency_class") or "read_only") != "read_only",
                    },
                },
            )
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="failed",
            model_summary=f"Backend skill not found: {skill_id}",
            error={"code": "skill_not_found", "message": f"skill not found: {skill_id}"},
        )

    return handler


def _project_graph_search_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="project.graph.search",
        title="Search Project Graph Nodes",
        description_for_model=(
            "Search already-stored graph nodes for the current project. "
            "Use this for entity, relation, clue tracing, graph, graph_nodes, and knowledge-graph questions. "
            "This is read-only and never triggers graph rebuild or source collection."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "additionalProperties": False,
        },
        source="project",
        risk="read_only",
        permission="allow",
        concurrency="parallel",
        timeout_seconds=15,
        result_budget=5000,
        project_service_id="project.graph.search",
    )


def _project_graph_search_handler(
    searcher: StructuredDataSearcher,
) -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        project_key = _resolve_project_key(tool_call, request)
        if not project_key:
            return _missing_project_result(tool_call)
        query = str(tool_call.arguments.get("query") or request.message or "").strip()
        limit = max(1, min(50, int(tool_call.arguments.get("limit") or 12)))
        try:
            result = searcher(project_key=project_key, query=query, limit=limit, datasets=["graph_nodes"])
        except Exception as exc:  # noqa: BLE001
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary=f"Project graph search failed: {exc}",
                error={"code": exc.__class__.__name__, "message": str(exc)},
            )
        items = list(result.get("items") or [])
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=f"Found {len(items)} graph node result(s) for query '{query}'.",
            structured_content={
                "contract_version": "project.graph.search.v1",
                "project_key": project_key,
                "query": query,
                "total_matches": result.get("total_matches"),
                "total_stored_rows": result.get("total_stored_rows"),
                "inventory": _compact_json_value(result.get("inventory"), max_items=8, max_depth=3),
                "graph_nodes": _compact_json_value(items, max_items=limit, max_depth=5),
                "errors": _compact_json_value(result.get("errors"), max_items=6, max_depth=3),
            },
        )

    return handler


def _project_structured_graph_query_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="project.structured_graph.query",
        title="Query Structured Data And Graph",
        description_for_model=(
            "Read a combined investigation view over stored documents, graph nodes, sources, resource-pool entries, and keyword/search memory. "
            "Use this for multi-round investigation, clue tracing, writing research context, and questions that require both structured data and graph evidence."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                "datasets": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "documents",
                            "graph_nodes",
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
        source="project",
        risk="read_only",
        permission="allow",
        concurrency="parallel",
        timeout_seconds=15,
        result_budget=7000,
        project_service_id="project.structured_graph.query",
    )


def _project_structured_graph_query_handler(
    searcher: StructuredDataSearcher,
) -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    default_datasets = [
        "documents",
        "graph_nodes",
        "resource_pool_urls",
        "resource_pool_sites",
        "keyword_history",
        "keyword_priors",
        "search_history",
        "sources",
    ]

    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        project_key = _resolve_project_key(tool_call, request)
        if not project_key:
            return _missing_project_result(tool_call)
        query = str(tool_call.arguments.get("query") or request.message or "").strip()
        limit = max(1, min(50, int(tool_call.arguments.get("limit") or 12)))
        datasets = [
            str(item or "").strip()
            for item in list(tool_call.arguments.get("datasets") or default_datasets)
            if str(item or "").strip()
        ]
        try:
            result = searcher(project_key=project_key, query=query, limit=limit, datasets=datasets)
        except Exception as exc:  # noqa: BLE001
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary=f"Structured/graph project query failed: {exc}",
                error={"code": exc.__class__.__name__, "message": str(exc)},
            )
        grouped = _group_items_by_dataset(list(result.get("items") or []))
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=(
                f"Read structured/graph investigation context: matches={result.get('total_matches')}, "
                f"stored_rows={result.get('total_stored_rows')}."
            ),
            structured_content={
                "contract_version": "project.structured_graph.query.v1",
                "project_key": project_key,
                "query": query,
                "query_mode": result.get("query_mode"),
                "datasets_requested": datasets,
                "inventory": _compact_json_value(result.get("inventory"), max_items=20, max_depth=3),
                "dataset_total_rows": dict(result.get("dataset_total_rows") or {}),
                "total_stored_rows": result.get("total_stored_rows"),
                "total_matches": result.get("total_matches"),
                "items_by_dataset": _compact_json_value(grouped, max_items=12, max_depth=5),
                "items": _compact_json_value(result.get("items"), max_items=limit, max_depth=5),
                "errors": _compact_json_value(result.get("errors"), max_items=8, max_depth=3),
            },
        )

    return handler


def _project_structured_data_quality_audit_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="project.structured_data.quality_audit",
        title="Audit Structured Data Quality",
        description_for_model=(
            "Audit already-stored documents and graph nodes for web-shell noise such as script, CSS, ads, or navigation text. "
            "Use this when the user asks why project data looks noisy, asks to clean stored data, or needs confidence in local data quality. "
            "This is read-only: it returns affected record samples and recommended cleaning actions without deleting or overwriting raw evidence."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "scan_limit": {"type": "integer", "minimum": 1, "maximum": 5000},
                "sample_limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "additionalProperties": False,
        },
        source="project",
        risk="read_only",
        permission="allow",
        concurrency="parallel",
        timeout_seconds=20,
        result_budget=7000,
        project_service_id="project.structured_data.quality_audit",
    )


def _project_structured_data_quality_audit_handler() -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        project_key = _resolve_project_key(tool_call, request)
        if not project_key:
            return _missing_project_result(tool_call)
        scan_limit = max(1, min(5000, int(tool_call.arguments.get("scan_limit") or 500)))
        sample_limit = max(1, min(100, int(tool_call.arguments.get("sample_limit") or 20)))
        try:
            result = audit_project_structured_data_quality(
                project_key=project_key,
                scan_limit=scan_limit,
                sample_limit=sample_limit,
            )
        except Exception as exc:  # noqa: BLE001
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary=f"Structured data quality audit failed: {exc}",
                error={"code": exc.__class__.__name__, "message": str(exc)},
            )
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status=str(result.get("status") or "completed"),
            model_summary=(
                f"Audited structured data quality: scanned={result.get('scanned')}, "
                f"noisy_records={result.get('noisy_record_count')}, by_dataset={result.get('by_dataset')}."
            ),
            structured_content=result,
        )

    return handler


def _group_items_by_dataset(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        dataset = str(item.get("dataset") or "unknown").strip() or "unknown"
        grouped.setdefault(dataset, []).append(item)
    return grouped


def _source_discovery_plan_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="source.discovery.plan",
        title="Plan Source Discovery",
        description_for_model=(
            "Plan autonomous source discovery for an investigation without fetching, collecting, or writing anything. "
            "Use this before external research or source-library ingestion. It returns search queries, candidate source directions, "
            "URL trust checks, dedupe keys, source-quality signals, and follow-up actions."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "query_terms": {"type": "array", "items": {"type": "string"}},
                "candidate_urls": {"type": "array", "items": {"type": "string"}},
                "domains": {"type": "array", "items": {"type": "string"}},
                "source_kinds": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["official", "market", "academic", "news", "regulatory", "company", "database"]},
                },
                "max_candidates": {"type": "integer", "minimum": 1, "maximum": 30},
                "min_trust_score": {"type": "number", "minimum": 0, "maximum": 100},
                "matrix_mode": {"type": "boolean", "description": "Default true. Return intent/query/tool/evidence/verification matrix metadata."},
            },
            "additionalProperties": False,
        },
        source="project",
        risk="read_only",
        permission="allow",
        concurrency="parallel",
        timeout_seconds=10,
        result_budget=7000,
        project_service_id="source.discovery.plan",
        metadata={"contract_version": "source.discovery.plan.v1", "no_external_io": True},
    )


def _source_discovery_plan_handler(
    source_library_lister: SourceLibraryLister | None = None,
) -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        project_key = _resolve_project_key(tool_call, request)
        if not project_key:
            return _missing_project_result(tool_call)
        topic = str(tool_call.arguments.get("topic") or request.message or "").strip()
        query_terms = _normalize_string_list(tool_call.arguments.get("query_terms"))
        if not query_terms and topic:
            query_terms = _derive_query_terms(topic)
        source_kinds = _normalize_string_list(tool_call.arguments.get("source_kinds")) or ["official", "regulatory", "company", "news", "database"]
        max_candidates = max(1, min(30, int(tool_call.arguments.get("max_candidates") or 12)))
        candidate_urls = _normalize_string_list(tool_call.arguments.get("candidate_urls"))
        domains = _normalize_string_list(tool_call.arguments.get("domains"))
        min_trust_score = float(tool_call.arguments.get("min_trust_score") or 60)
        matrix_mode = bool(tool_call.arguments.get("matrix_mode", True))
        source_items: list[dict[str, Any]] = []
        source_lister_error: dict[str, str] | None = None
        if source_library_lister is not None:
            try:
                source_items = [dict(item or {}) for item in list(source_library_lister(project_key) or [])]
            except Exception as exc:  # noqa: BLE001
                source_lister_error = {"code": exc.__class__.__name__, "message": str(exc)}

        trust_plan = build_source_candidate_plan(
            project_key=project_key,
            query=" ".join(query_terms) or topic,
            urls=candidate_urls,
            domains=domains,
            source_library_items=source_items,
            max_candidates=max_candidates,
            min_trust_score=min_trust_score,
        )
        url_assessments = (
            list(trust_plan.get("candidate_urls") or [])
            + list(trust_plan.get("rejected_urls") or [])
            + list(trust_plan.get("duplicate_urls") or [])
        )
        search_queries = _build_source_search_queries(topic=topic, query_terms=query_terms, source_kinds=source_kinds, limit=max_candidates)
        for query in trust_plan.get("search_queries") or []:
            if isinstance(query, str) and query and all(item.get("query") != query for item in search_queries):
                search_queries.append(
                    {
                        "query": query,
                        "source_kind": "candidate",
                        "purpose": "candidate discovery query from trust planner",
                        "write_policy": "plan_only_no_fetch",
                    }
                )
            if len(search_queries) >= max_candidates:
                break
        source_directions = _build_source_directions(topic=topic, query_terms=query_terms, source_kinds=source_kinds)
        capability_matrix = (
            _build_source_capability_matrix(
                topic=topic,
                query_terms=query_terms,
                source_kinds=source_kinds,
                domains=domains,
                search_queries=search_queries,
                provider_diagnostics=_source_web_search_provider_diagnostics(provider="auto", result_count=0),
                source_item_count=len(source_items),
                max_candidates=max_candidates,
            )
            if matrix_mode
            else None
        )
        rejected = [item for item in url_assessments if item["status"] == "rejected"]
        accepted = [item for item in url_assessments if item["status"] == "accepted"]
        model_summary = (
            f"Planned {len(search_queries)} source search querie(s), "
            f"{len(source_directions)} source direction(s), accepted_urls={len(accepted)}, rejected_urls={len(rejected)}, "
            f"candidate_source_items={len(list(trust_plan.get('candidate_source_items') or []))}."
        )
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=model_summary,
            structured_content={
                "contract_version": "source.discovery.plan.v1",
                "project_key": project_key,
                "topic": topic,
                "query_terms": query_terms,
                "domains": domains,
                "source_kinds": source_kinds,
                "search_queries": search_queries,
                "capability_matrix": capability_matrix,
                "matrix_summary": _compact_json_value((capability_matrix or {}).get("summary"), max_items=20, max_depth=4),
                "source_directions": source_directions,
                "candidate_urls": url_assessments,
                "candidate_source_items": _compact_json_value(trust_plan.get("candidate_source_items"), max_items=max_candidates, max_depth=4),
                "source_lister_error": source_lister_error,
                "quality_gates": {
                    "external_write_performed": False,
                    "network_fetch_performed": False,
                    "requires_review_before_ingest": True,
                    "minimum_score_for_auto_candidate": min_trust_score,
                    "reject_private_or_local_networks": True,
                    "dedupe_key": "normalized_url_sha256",
                    "pre_ingest_required_checks": list((trust_plan.get("trust_policy") or {}).get("pre_ingest_required_checks") or []),
                    "next_tool_after_candidate_review": "source.candidate.review, then ingest.source_library.run or ingest.url_pool.submit when approved",
                },
                "trust_pipeline": trust_plan.get("trust_policy"),
                "trust_counts": trust_plan.get("counts"),
                "follow_up_tasks": [
                    "Review accepted source candidates and pick source-library item keys or external project registrations.",
                    "Run source-library collection only after candidate review.",
                    "Store followed/rejected leads in the investigation artifact trail.",
                ],
            },
        )

    return handler


def _derive_query_terms(topic: str) -> list[str]:
    cleaned = str(topic or "").replace("，", " ").replace("。", " ").replace(",", " ")
    tokens = [item.strip("`'\"：:；;。()[]{}").strip() for item in cleaned.split() if item.strip()]
    out: list[str] = []
    for token in tokens:
        if len(token) < 2:
            continue
        lowered = token.lower()
        if lowered in {"the", "and", "for", "with", "that", "this", "项目", "调查", "写作", "资料", "数据"}:
            continue
        if token not in out:
            out.append(token)
        if len(out) >= 8:
            break
    return out


def _build_source_search_queries(*, topic: str, query_terms: list[str], source_kinds: list[str], limit: int) -> list[dict[str, Any]]:
    terms = " ".join(query_terms[:6]) or topic
    templates = {
        "official": ['"{terms}" official data', '"{terms}" site:.gov OR site:.org'],
        "regulatory": ['"{terms}" regulation report', '"{terms}" filing policy data'],
        "company": ['"{terms}" company annual report', '"{terms}" investor presentation'],
        "market": ['"{terms}" market size data', '"{terms}" price demand supply data'],
        "academic": ['"{terms}" working paper dataset', '"{terms}" survey evidence'],
        "news": ['"{terms}" recent news evidence', '"{terms}" investigation report'],
        "database": ['"{terms}" database statistics', '"{terms}" API dataset'],
    }
    out: list[dict[str, Any]] = []
    for kind in source_kinds:
        for template in templates.get(kind, [f'"{{terms}}" {kind} evidence']):
            query = template.format(terms=terms).strip()
            if query and all(item.get("query") != query for item in out):
                out.append(
                    {
                        "query": query,
                        "source_kind": kind,
                        "purpose": _source_kind_purpose(kind),
                        "write_policy": "plan_only_no_fetch",
                    }
                )
            if len(out) >= limit:
                return out
    return out


def _build_source_directions(*, topic: str, query_terms: list[str], source_kinds: list[str]) -> list[dict[str, Any]]:
    directions: list[dict[str, Any]] = []
    for kind in source_kinds:
        directions.append(
            {
                "source_kind": kind,
                "target": _source_kind_target(kind),
                "why": _source_kind_purpose(kind),
                "candidate_terms": query_terms[:6],
                "trust_notes": _source_kind_trust_notes(kind),
                "ingest_boundary": "candidate only; source-library execution remains explicit-request governed",
            }
        )
    return directions


def _source_kind_target(kind: str) -> str:
    return {
        "official": "official portals, public agency pages, authoritative project pages",
        "regulatory": "filings, policy databases, regulator publications",
        "company": "company reports, investor relations, product documentation",
        "market": "market datasets, price/volume trackers, industry statistics",
        "academic": "papers with empirical datasets, working papers, bibliographies",
        "news": "named outlets with source links and dates",
        "database": "public databases, APIs, data catalogs",
    }.get(kind, "domain-specific sources")


def _source_kind_purpose(kind: str) -> str:
    return {
        "official": "anchor facts in primary or authoritative sources",
        "regulatory": "verify policy/legal constraints and official record changes",
        "company": "capture actor-specific claims and financial/product evidence",
        "market": "quantify market size, price, supply, demand, and trend claims",
        "academic": "collect definitions, mechanisms, and empirical support",
        "news": "trace recent events and named leads",
        "database": "find reusable structured evidence",
    }.get(kind, "expand evidence coverage")


def _source_kind_trust_notes(kind: str) -> list[str]:
    base = ["dedupe by normalized URL", "record publication date when available", "preserve source title and locator"]
    if kind in {"official", "regulatory", "database"}:
        return base + ["prefer primary record over commentary"]
    if kind == "news":
        return base + ["require named publisher and date", "treat syndication duplicates as lower priority"]
    if kind == "academic":
        return base + ["do not over-rank papers when user asks for commercialization or market evidence"]
    return base


def _clue_chain_expand_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="chain.expand",
        title="Request Clue Chain Expansion",
        description_for_model=(
            "Request a governed clue-chain expansion hop from graph frontier nodes, source-library search, or fixture-backed external search. "
            "This tool may create expansion requests, hops, and review candidates only. It must never promote candidates into the workflow graph. "
            "Return candidates to the user for ChainDecision review before any graph node or edge is created."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "chain_id": {"type": "string", "description": "Existing clue chain id to expand."},
                "project_key": {"type": "string"},
                "query": {"type": "string", "description": "Search or expansion query for the next hop."},
                "frontier_node_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Graph frontier node ids selected by the user or graph UI.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["source_library_search", "external_search_fixture"],
                    "description": "Expansion provider mode. external_search_fixture must stay fixture-gated and offline in tests.",
                },
                "provider": {
                    "type": "string",
                    "enum": ["source_library_search", "external_search_fixture"],
                    "description": "Alias for mode, accepted for provider-style callers.",
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                "idempotency_key": {"type": "string"},
            },
            "additionalProperties": False,
        },
        source="project",
        risk="write_shared",
        permission="allow",
        concurrency="serial",
        timeout_seconds=20,
        result_budget=9000,
        project_service_id="chain.expand",
        metadata={
            "contract_version": "chain.expand.v1",
            "auto_allow_session_write": True,
            "requires_review": True,
            "no_silent_promote": True,
            "no_graph_write": True,
            "fixture_gated_external_search": True,
        },
    )


def _clue_chain_expand_handler(
    service: AgentSessionService,
) -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        project_key = _resolve_project_key(tool_call, request)
        if not project_key:
            return _missing_project_result(tool_call)
        chain_id = str(tool_call.arguments.get("chain_id") or "").strip()
        if not chain_id:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary="chain_id is required for chain.expand.",
                error={"code": "missing_chain_id", "message": "chain_id is required"},
                retry_hint="Pass the clue chain id selected in the graph UI or returned by the clue-chain API.",
            )
        mode = _normalize_clue_chain_expand_mode(tool_call.arguments.get("mode") or tool_call.arguments.get("provider"))
        if mode is None:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary="chain.expand mode must be source_library_search or external_search_fixture.",
                error={
                    "code": "invalid_chain_expand_mode",
                    "message": "mode/provider must be one of: source_library_search, external_search_fixture",
                },
            )
        frontier_node_ids = _normalize_string_list(tool_call.arguments.get("frontier_node_ids"))
        query = str(tool_call.arguments.get("query") or request.message or "").strip()
        limit = max(1, min(20, int(tool_call.arguments.get("limit") or 5)))
        idempotency_key = str(tool_call.arguments.get("idempotency_key") or "").strip()
        payload = {
            "project_key": project_key,
            "chain_id": chain_id,
            "query": query,
            "frontier_node_ids": frontier_node_ids,
            "mode": mode,
            "provider": mode,
            "limit": limit,
            "idempotency_key": idempotency_key or None,
            "session_id": request.session_id,
            "turn_id": request.turn_id,
            "call_id": tool_call.call_id,
            "actor": "agent_core",
            "requires_review": True,
            "auto_promote": False,
            "promote": False,
        }

        service_result, service_status = _try_clue_chain_service_expand(payload)
        if service_result is not None:
            return _clue_chain_expand_result_from_service(
                tool_call=tool_call,
                project_key=project_key,
                chain_id=chain_id,
                query=query,
                frontier_node_ids=frontier_node_ids,
                mode=mode,
                limit=limit,
                service_result=service_result,
                service_status=service_status,
            )

        fallback = _record_clue_chain_expand_request_artifact(
            service=service,
            request=request,
            tool_call=tool_call,
            project_key=project_key,
            chain_id=chain_id,
            query=query,
            frontier_node_ids=frontier_node_ids,
            mode=mode,
            limit=limit,
            idempotency_key=idempotency_key,
            service_status=service_status,
        )
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=(
                f"Requested clue chain expansion for chain={chain_id}; "
                f"mode={mode}; candidates={len(fallback['candidates'])}; requires_review=True; promoted_to_graph=False."
            ),
            structured_content=fallback,
            artifact_refs=(str((fallback.get("artifact") or {}).get("artifact_id") or "clue_chain_expansions.json"),),
        )

    return handler


def _normalize_clue_chain_expand_mode(value: Any) -> str | None:
    mode = str(value or "source_library_search").strip().lower() or "source_library_search"
    aliases = {
        "source_library": "source_library_search",
        "source-library": "source_library_search",
        "source-library-search": "source_library_search",
        "source_library_search": "source_library_search",
        "external_search": "external_search_fixture",
        "external-fixture": "external_search_fixture",
        "external_search_fixture": "external_search_fixture",
        "fixture": "external_search_fixture",
    }
    return aliases.get(mode)


def _try_clue_chain_service_expand(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    try:
        module = importlib.import_module("app.services.clue_chains.service")
    except Exception as exc:  # noqa: BLE001
        return None, {
            "service_adapter": "app.services.clue_chains.service",
            "status": "unavailable",
            "code": exc.__class__.__name__,
            "message": str(exc),
        }
    for name in ("expand_chain", "request_chain_expansion", "create_expansion_request"):
        handler = getattr(module, name, None)
        if not callable(handler):
            continue
        try:
            result = handler(**_filter_kwargs_for_callable(handler, payload))
        except Exception as exc:  # noqa: BLE001
            return None, {
                "service_adapter": "app.services.clue_chains.service",
                "handler": name,
                "status": "failed",
                "code": exc.__class__.__name__,
                "message": str(exc),
            }
        return dict(result or {}), {
            "service_adapter": "app.services.clue_chains.service",
            "handler": name,
            "status": "completed",
        }
    return None, {
        "service_adapter": "app.services.clue_chains.service",
        "status": "handler_missing",
        "expected_handlers": ["expand_chain", "request_chain_expansion", "create_expansion_request"],
    }


def _filter_kwargs_for_callable(handler: Callable[..., Any], payload: dict[str, Any]) -> dict[str, Any]:
    try:
        signature = inspect.signature(handler)
    except Exception:  # noqa: BLE001
        return dict(payload)
    params = signature.parameters
    if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values()):
        return dict(payload)
    return {key: value for key, value in payload.items() if key in params}


def _clue_chain_expand_result_from_service(
    *,
    tool_call: CoreToolCall,
    project_key: str,
    chain_id: str,
    query: str,
    frontier_node_ids: list[str],
    mode: str,
    limit: int,
    service_result: dict[str, Any],
    service_status: dict[str, Any],
) -> CoreToolResult:
    candidates = list(service_result.get("candidates") or [])
    if not candidates and isinstance(service_result.get("hop"), dict):
        candidates = list(dict(service_result.get("hop") or {}).get("candidates") or [])
    normalized = {
        **service_result,
        "contract_version": "chain.expand.v1",
        "project_key": service_result.get("project_key") or project_key,
        "chain_id": service_result.get("chain_id") or chain_id,
        "query": service_result.get("query") or query,
        "frontier_node_ids": list(service_result.get("frontier_node_ids") or frontier_node_ids),
        "mode": service_result.get("mode") or mode,
        "provider": service_result.get("provider") or service_result.get("mode") or mode,
        "limit": service_result.get("limit") or limit,
        "candidates": _compact_json_value(candidates, max_items=max(30, limit), max_depth=6),
        "candidate_count": len(candidates),
        "requires_review": True,
        "review_status": "pending_review",
        "promoted_to_graph": False,
        "graph_mutation_performed": False,
        "no_silent_promote": True,
        "decision_gate": _clue_chain_decision_gate(chain_id),
        "service_status": service_status,
    }
    return CoreToolResult(
        call_id=tool_call.call_id,
        tool_name=tool_call.tool_name,
        status="completed",
        model_summary=(
            f"Requested clue chain expansion for chain={chain_id}; "
            f"mode={mode}; candidates={len(candidates)}; requires_review=True; promoted_to_graph=False."
        ),
        structured_content=normalized,
    )


def _record_clue_chain_expand_request_artifact(
    *,
    service: AgentSessionService,
    request: AgentCoreRequest,
    tool_call: CoreToolCall,
    project_key: str,
    chain_id: str,
    query: str,
    frontier_node_ids: list[str],
    mode: str,
    limit: int,
    idempotency_key: str,
    service_status: dict[str, Any],
) -> dict[str, Any]:
    artifact_name = "clue_chain_expansions.json"
    existing_artifact = next((item for item in service.list_artifacts(request.session_id) if item.get("name") == artifact_name), None)
    existing_content = dict((existing_artifact or {}).get("content_json") or {})
    replay_keys = [str(item or "") for item in list(existing_content.get("replay_keys") or []) if str(item or "").strip()]
    request_key = idempotency_key or _stable_hash(
        {
            "project_key": project_key,
            "chain_id": chain_id,
            "query": query,
            "frontier_node_ids": frontier_node_ids,
            "mode": mode,
            "limit": limit,
            "call_id": tool_call.call_id,
        },
    )
    replayed = bool(idempotency_key and idempotency_key in replay_keys)
    requests = [dict(item) for item in list(existing_content.get("requests") or []) if isinstance(item, dict)]
    hops = [dict(item) for item in list(existing_content.get("hops") or []) if isinstance(item, dict)]
    candidates = [dict(item) for item in list(existing_content.get("candidates") or []) if isinstance(item, dict)]

    if replayed:
        expansion_request = next((item for item in requests if str(item.get("request_key") or "") == request_key), {})
        hop = next((item for item in hops if str(item.get("expansion_request_id") or "") == expansion_request.get("expansion_request_id")), {})
        selected_candidates = [
            item
            for item in candidates
            if str(item.get("hop_id") or "") == str(hop.get("hop_id") or "")
        ]
    else:
        expansion_request_id = f"chain-exp-{_stable_hash({'request_key': request_key, 'chain_id': chain_id})[:16]}"
        hop_id = f"chain-hop-{_stable_hash({'expansion_request_id': expansion_request_id, 'mode': mode})[:16]}"
        now = _utcnow_iso()
        expansion_request = {
            "expansion_request_id": expansion_request_id,
            "request_key": request_key,
            "chain_id": chain_id,
            "project_key": project_key,
            "query": query,
            "frontier_node_ids": frontier_node_ids,
            "mode": mode,
            "provider": mode,
            "limit": limit,
            "status": "requested",
            "requires_review": True,
            "created_by": "agent_core",
            "created_at": now,
            "session_id": request.session_id,
            "turn_id": request.turn_id,
            "call_id": tool_call.call_id,
        }
        hop = {
            "hop_id": hop_id,
            "expansion_request_id": expansion_request_id,
            "chain_id": chain_id,
            "project_key": project_key,
            "query": query,
            "frontier_node_ids": frontier_node_ids,
            "mode": mode,
            "provider": mode,
            "status": "pending_review",
            "requires_review": True,
            "promoted_to_graph": False,
            "graph_mutation_performed": False,
            "created_at": now,
        }
        selected_candidates = _build_clue_chain_review_candidates(
            project_key=project_key,
            chain_id=chain_id,
            hop_id=hop_id,
            expansion_request_id=expansion_request_id,
            query=query,
            frontier_node_ids=frontier_node_ids,
            mode=mode,
            limit=limit,
        )
        hop["candidate_ids"] = [item["candidate_id"] for item in selected_candidates]
        requests = [item for item in requests if str(item.get("request_key") or "") != request_key]
        hops = [item for item in hops if str(item.get("hop_id") or "") != hop_id]
        candidates = [
            item
            for item in candidates
            if str(item.get("expansion_request_id") or "") != expansion_request_id
        ]
        requests.append(expansion_request)
        hops.append(hop)
        candidates.extend(selected_candidates)
        if idempotency_key:
            replay_keys.append(idempotency_key)

    content = {
        **existing_content,
        "contract_version": "chain.expand.v1",
        "project_key": project_key,
        "updated_at": _utcnow_iso(),
        "replay_keys": replay_keys[-50:],
        "requests": requests[-100:],
        "hops": hops[-100:],
        "candidates": candidates[-200:],
        "counts": {
            "requests": len(requests),
            "hops": len(hops),
            "candidates": len(candidates),
            "pending_review": sum(1 for item in candidates if bool(item.get("requires_review"))),
            "promoted": 0,
        },
        "guardrails": {
            "requires_review": True,
            "silent_promote_allowed": False,
            "graph_mutation_performed": False,
            "decision_contract": "ChainDecision",
        },
    }
    artifact = service.store.upsert_artifact(
        {
            "session_id": request.session_id,
            "name": artifact_name,
            "artifact_type": "clue_chain_expansion_request_state",
            "mime_type": "application/json",
            "content_text": json.dumps(content, ensure_ascii=False, sort_keys=True, default=str),
            "content_json": content,
            "metadata": {
                "project_key": project_key,
                "contract_version": "chain.expand.v1",
                "auto_written_by": "agent_core",
                "requires_review": True,
                "no_silent_promote": True,
                "replayed": replayed,
            },
        }
    )
    return {
        "contract_version": "chain.expand.v1",
        "project_key": project_key,
        "chain_id": chain_id,
        "query": query,
        "frontier_node_ids": frontier_node_ids,
        "mode": mode,
        "provider": mode,
        "limit": limit,
        "expansion_request": _compact_json_value(expansion_request, max_items=24, max_depth=5),
        "hop": _compact_json_value(hop, max_items=24, max_depth=5),
        "candidates": _compact_json_value(selected_candidates, max_items=max(30, limit), max_depth=6),
        "candidate_count": len(selected_candidates),
        "requires_review": True,
        "review_status": "pending_review",
        "promoted_to_graph": False,
        "graph_mutation_performed": False,
        "external_network_io": False,
        "fixture_gated": mode == "external_search_fixture",
        "no_silent_promote": True,
        "decision_gate": _clue_chain_decision_gate(chain_id),
        "service_status": service_status,
        "artifact": _compact_json_value(artifact, max_items=18, max_depth=4),
        "replayed": replayed,
    }


def _build_clue_chain_review_candidates(
    *,
    project_key: str,
    chain_id: str,
    hop_id: str,
    expansion_request_id: str,
    query: str,
    frontier_node_ids: list[str],
    mode: str,
    limit: int,
) -> list[dict[str, Any]]:
    seed_labels = frontier_node_ids[:limit] or [query or chain_id]
    candidates: list[dict[str, Any]] = []
    for index, seed in enumerate(seed_labels[:limit], start=1):
        candidate_id = f"chain-cand-{_stable_hash({'hop_id': hop_id, 'seed': seed, 'index': index})[:16]}"
        candidates.append(
            {
                "candidate_id": candidate_id,
                "chain_id": chain_id,
                "project_key": project_key,
                "hop_id": hop_id,
                "expansion_request_id": expansion_request_id,
                "rank": index,
                "mode": mode,
                "provider": mode,
                "title": _clue_chain_candidate_title(mode=mode, query=query, seed=seed),
                "query": query,
                "frontier_node_ids": frontier_node_ids,
                "frontier_seed": seed,
                "candidate_type": "source_library_lead" if mode == "source_library_search" else "external_search_fixture_lead",
                "review_status": "pending_review",
                "requires_review": True,
                "promote_allowed": False,
                "promoted_to_graph": False,
                "graph_mutation_performed": False,
                "evidence_refs": [],
                "proposed_graph_nodes": [],
                "proposed_graph_edges": [],
                "decision": None,
            }
        )
    return candidates


def _clue_chain_candidate_title(*, mode: str, query: str, seed: str) -> str:
    label = query or seed or "next clue"
    if mode == "external_search_fixture":
        return f"Fixture external-search lead for {label}"
    return f"Source-library search lead for {label}"


def _clue_chain_decision_gate(chain_id: str) -> dict[str, Any]:
    return {
        "gate": "ChainDecision",
        "chain_id": chain_id,
        "allowed_decisions": ["approve", "defer", "reject"],
        "required_context": ["candidate_id", "hop_id", "expansion_request_id"],
        "future_tool": "chain.decision",
        "message": "Review candidates before any graph node or edge promotion; chain.expand never promotes silently.",
    }


def _source_web_search_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="source.web.search",
        title="Search External Source Candidates",
        description_for_model=(
            "Run a bounded external web/search-provider query for source candidates after internal project context and source.discovery.plan. "
            "This returns titles, URLs, snippets, provider metadata, and trust assessments only. It does not fetch article bodies, ingest sources, or write project data. "
            "Use it when the user explicitly asks for external/web/new material or when an internal-first pass exposes a missing-evidence gap."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "query_terms": {"type": "array", "items": {"type": "string"}},
                "language": {"type": "string", "enum": ["en", "zh", "bi", "bilingual", "zh-en", "zh_en", "both", "multi", "multilingual"]},
                "provider": {"type": "string", "enum": ["auto", "ddg", "google", "serper", "serpstack", "serpapi", "searxng", "yacy"]},
                "providers": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["auto", "ddg", "google", "serper", "serpstack", "serpapi", "searxng", "yacy"]},
                    "description": "Optional provider branches for matrix mode. Capped to a small safe fanout.",
                },
                "query_variants": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional keyword/query branches for matrix mode.",
                },
                "matrix_mode": {"type": "boolean", "description": "Run a bounded query/provider matrix and merge/rank candidates."},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 20},
                "days_back": {"type": "integer", "minimum": 1, "maximum": 3650},
                "domains": {"type": "array", "items": {"type": "string"}},
                "min_trust_score": {"type": "number", "minimum": 0, "maximum": 100},
            },
            "additionalProperties": False,
        },
        source="project",
        risk="read_only",
        permission="allow",
        concurrency="serial",
        timeout_seconds=30,
        result_budget=9000,
        project_service_id="source.web.search",
        metadata={"contract_version": "source.web.search.v1", "external_network_io": True, "no_ingest": True, "no_project_write": True},
    )


def _source_web_search_handler() -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        project_key = _resolve_project_key(tool_call, request)
        if not project_key:
            return _missing_project_result(tool_call)
        query_terms = _normalize_string_list(tool_call.arguments.get("query_terms"))
        query = str(tool_call.arguments.get("query") or " ".join(query_terms) or request.message or "").strip()
        domains = _normalize_string_list(tool_call.arguments.get("domains"))
        language = str(tool_call.arguments.get("language") or "en").strip() or "en"
        provider = str(tool_call.arguments.get("provider") or "auto").strip() or "auto"
        providers = _normalize_source_search_providers(tool_call.arguments.get("providers"), default_provider=provider)
        query_variants = _normalize_string_list(tool_call.arguments.get("query_variants"))
        matrix_mode = bool(tool_call.arguments.get("matrix_mode", False) or len(providers) > 1 or len(query_variants) > 1)
        if not query_variants:
            query_variants = _build_query_matrix_variants(query=query, query_terms=query_terms, domains=domains, matrix_mode=matrix_mode)
        if not matrix_mode:
            query_variants = query_variants[:1]
            providers = providers[:1]
        max_results = max(1, min(20, int(tool_call.arguments.get("max_results") or 8)))
        days_back_raw = tool_call.arguments.get("days_back")
        days_back = None if days_back_raw in (None, "") else max(1, min(3650, int(days_back_raw)))
        min_trust_score = float(tool_call.arguments.get("min_trust_score") or 40)
        search_branches: list[dict[str, Any]] = []
        all_candidates: list[dict[str, Any]] = []
        branch_limit = max(1, min(5, max_results))
        branch_specs = _build_source_search_branch_specs(
            query_variants=query_variants,
            providers=providers,
            max_branches=8 if matrix_mode else 1,
        )
        for branch_index, branch in enumerate(branch_specs, start=1):
            branch_query = _apply_domain_clause(str(branch.get("query") or ""), domains)
            branch_provider = str(branch.get("provider") or provider)
            branch_observations = ()
            try:
                candidate_request = CandidateSearchRequest(
                    topic=branch_query,
                    keywords=(branch_query,),
                    language=language,
                    max_results=branch_limit if matrix_mode else max_results,
                    provider=branch_provider,
                    days_back=days_back,
                    exclude_existing=True,
                    project_ref=project_key,
                )
                candidate_bundle = discover_candidates(candidate_request)
                branch_observations = candidate_bundle.observations
                raw_results = [dict(candidate.raw) for candidate in candidate_bundle.candidates]
            except Exception as exc:  # noqa: BLE001
                if matrix_mode:
                    diagnostics = _source_web_search_provider_diagnostics(provider=branch_provider, result_count=0)
                    search_branches.append(
                        {
                            "branch_id": f"b{branch_index}",
                            "query": branch_query,
                            "provider": branch_provider,
                            "status": "failed",
                            "error": {"code": exc.__class__.__name__, "message": str(exc)},
                            "provider_diagnostics": diagnostics,
                            "result_count": 0,
                            "accepted_candidate_count": 0,
                        }
                    )
                    continue
                return CoreToolResult(
                    call_id=tool_call.call_id,
                    tool_name=tool_call.tool_name,
                    status="failed",
                    model_summary=f"External source search failed: {exc}",
                    error={"code": exc.__class__.__name__, "message": str(exc)},
                    structured_content={
                        "contract_version": "source.web.search.v1",
                        "project_key": project_key,
                        "query": branch_query,
                        "provider": branch_provider,
                        "external_network_io": True,
                        "project_write_performed": False,
                        "ingest_performed": False,
                    },
                )
            normalized_branch_results = _normalize_web_search_results(raw_results, query=branch_query, min_trust_score=min_trust_score)
            accepted_branch_count = sum(1 for item in normalized_branch_results if str((item.get("trust") or {}).get("status") or "") == "accepted")
            diagnostics = _source_web_search_provider_diagnostics(provider=branch_provider, result_count=len(normalized_branch_results))
            for candidate in normalized_branch_results:
                candidate["_matrix_branch"] = {
                    "branch_id": f"b{branch_index}",
                    "query": branch_query,
                    "provider": branch_provider,
                    "query_purpose": branch.get("purpose"),
                }
            all_candidates.extend(normalized_branch_results)
            observed_failures = [item for item in branch_observations if item.status != "completed"]
            search_branches.append(
                {
                    "branch_id": f"b{branch_index}",
                    "query": branch_query,
                    "provider": branch_provider,
                    "purpose": branch.get("purpose"),
                    "status": "partial" if observed_failures and normalized_branch_results else ("failed" if observed_failures else "completed"),
                    "observations": [
                        {
                            "provider": item.provider,
                            "route": item.route,
                            "keyword": item.keyword,
                            "status": item.status,
                            "returned_count": item.returned_count,
                            "failure_kind": item.failure_kind,
                            "error_type": item.error_type,
                            "error_message": item.error_message,
                        }
                        for item in branch_observations
                    ],
                    "result_count": len(normalized_branch_results),
                    "accepted_candidate_count": accepted_branch_count,
                    "provider_diagnostics": diagnostics,
                }
            )
        normalized_results = _merge_rank_web_search_candidates(all_candidates, max_results=max_results)
        accepted_count = sum(1 for item in normalized_results if str((item.get("trust") or {}).get("status") or "") == "accepted")
        provider_diagnostics = _source_web_search_provider_diagnostics(provider=provider, result_count=len(normalized_results))
        matrix_summary = _build_web_search_matrix_summary(
            matrix_mode=matrix_mode,
            query_variants=query_variants,
            providers=providers,
            branches=search_branches,
            candidates=normalized_results,
        )
        query_group_id, evidence_hits = build_agent_matrix_evidence_hits(
            normalized_results,
            query=query,
            project_key=project_key,
            rank_mode="matrix",
            top_k=max_results,
        )
        retrieval_run = build_retrieval_run_record(
            query=query,
            query_group_id=query_group_id,
            evidence_hits=evidence_hits,
            project_key=project_key,
            rank_mode="matrix",
            top_k=max_results,
            retrieval_family="agent_matrix",
        )
        model_summary = (
            f"External source search returned {len(normalized_results)} candidate(s), "
            f"accepted_by_trust={accepted_count}, provider={provider}, branches={len(search_branches)}."
        )
        if not normalized_results:
            model_summary += (
                " No candidates were returned; treat this as provider/config/rate-limit uncertainty, "
                "not as evidence that the source does not exist."
            )
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=model_summary,
            structured_content={
                "contract_version": "source.web.search.v1",
                "project_key": project_key,
                "query": query,
                "query_variants": query_variants,
                "query_terms": query_terms,
                "domains": domains,
                "language": language,
                "provider": provider,
                "providers": providers,
                "days_back": days_back,
                "matrix_mode": matrix_mode,
                "external_network_io": True,
                "project_write_performed": False,
                "ingest_performed": False,
                "candidate_count": len(normalized_results),
                "accepted_candidate_count": accepted_count,
                "candidates": _compact_json_value(normalized_results, max_items=max(12, max_results), max_depth=5),
                "search_branches": _compact_json_value(search_branches, max_items=12, max_depth=5),
                "matrix_summary": matrix_summary,
                "agent_matrix_evidence_contract_version": AGENT_MATRIX_SEARCH_EVIDENCE_CONTRACT_VERSION,
                "global_vector_object_contract_version": GLOBAL_VECTOR_OBJECT_CONTRACT_VERSION,
                "evidence_hit_contract_version": SEARCH_EVIDENCE_HIT_CONTRACT_VERSION,
                "retrieval_run_contract_version": SEARCH_RETRIEVAL_RUN_CONTRACT_VERSION,
                "query_group_id": query_group_id,
                "evidence_hits": _compact_json_value(evidence_hits, max_items=max(30, max_results), max_depth=6),
                "retrieval_run": _compact_json_value(retrieval_run, max_items=max(30, max_results), max_depth=6),
                "provider_diagnostics": provider_diagnostics,
                "empty_result_guidance": (
                    "No live candidates returned. Do not conclude absence of evidence; retry with a configured provider, "
                    "narrow domains, or ask for/manual candidate URLs before ingest."
                    if not normalized_results
                    else ""
                ),
                "next_gate": "review_candidates_then_source_library_or_url_pool_ingest"
                if normalized_results
                else "retry_configured_provider_or_manual_candidate_urls",
            },
        )

    return handler


def _source_web_search_provider_diagnostics(*, provider: str, result_count: int) -> dict[str, Any]:
    google_api_key_configured = bool(os.getenv("GOOGLE_SEARCH_API_KEY") or getattr(settings, "google_search_api_key", None))
    google_cse_configured = bool(os.getenv("GOOGLE_SEARCH_CSE_ID") or getattr(settings, "google_search_cse_id", None))
    google_oauth_path = str(os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    google_oauth_configured = bool(google_oauth_path and os.path.isfile(os.path.expanduser(google_oauth_path)))
    google_configured = bool(google_cse_configured and (google_api_key_configured or google_oauth_configured))
    serper_configured = bool(os.getenv("SERPER_API_KEY") or getattr(settings, "serper_api_key", None))
    serpstack_configured = bool(os.getenv("SERPSTACK_KEY") or getattr(settings, "serpstack_key", None))
    serpapi_configured = bool(os.getenv("SERPAPI_KEY") or os.getenv("SERPAPI_API_KEY") or getattr(settings, "serpapi_key", None))
    searxng_base_url = str(os.getenv("SEARXNG_BASE_URL") or "http://127.0.0.1:8088").strip()
    yacy_base_url = str(os.getenv("YACY_BASE_URL") or "http://127.0.0.1:8090").strip()
    provider_readiness = {
        "google": {
            "configured": google_configured,
            "cse_configured": google_cse_configured,
            "api_key_configured": google_api_key_configured,
            "oauth_credentials_file_configured": google_oauth_configured,
            "required": "GOOGLE_SEARCH_CSE_ID plus GOOGLE_SEARCH_API_KEY or a valid GOOGLE_APPLICATION_CREDENTIALS file",
        },
        "serper": {"configured": serper_configured, "required": "SERPER_API_KEY"},
        "serpstack": {"configured": serpstack_configured, "required": "SERPSTACK_KEY"},
        "serpapi": {"configured": serpapi_configured, "required": "SERPAPI_KEY or SERPAPI_API_KEY"},
        "ddg": {"configured": True, "required": "no key; public endpoint may rate-limit"},
        "searxng": {"configured": bool(searxng_base_url), "required": "SEARXNG_BASE_URL; defaults to http://127.0.0.1:8088"},
        "yacy": {"configured": bool(yacy_base_url), "required": "YACY_BASE_URL; defaults to http://127.0.0.1:8090"},
    }
    configured_paid_providers = [
        name
        for name, enabled in (
            ("serper", serper_configured),
            ("google", google_configured),
            ("serpstack", serpstack_configured),
            ("serpapi", serpapi_configured),
        )
        if enabled
    ]
    requested_provider = str(provider or "auto").strip().lower() or "auto"
    selected_provider_configured = True
    if requested_provider in provider_readiness:
        selected_provider_configured = bool(provider_readiness[requested_provider].get("configured"))
    missing_config = [
        name
        for name, meta in provider_readiness.items()
        if name != "ddg" and not bool(meta.get("configured"))
    ]
    empty_causes = []
    if result_count == 0:
        if requested_provider != "auto" and not selected_provider_configured:
            empty_causes.append(f"{requested_provider}_not_configured")
        if not configured_paid_providers:
            empty_causes.append("provider_not_configured")
        empty_causes.extend(["provider_rate_limited", "query_too_broad_or_too_narrow"])
    return {
        "provider": provider,
        "result_count": result_count,
        "ddg_requires_no_key": True,
        "configured_paid_providers": configured_paid_providers,
        "provider_readiness": provider_readiness,
        "selected_provider_configured": selected_provider_configured,
        "missing_configured_paid_providers": missing_config,
        "recommended_provider_order": ["serper", "google", "serpstack", "serpapi", "ddg"],
        "explicit_experimental_providers": ["searxng", "yacy"],
        "searxng_base_url": searxng_base_url,
        "yacy_base_url": yacy_base_url,
        "google_configured": google_configured,
        "google_api_key_configured": google_api_key_configured,
        "google_cse_configured": google_cse_configured,
        "google_oauth_credentials_file_configured": google_oauth_configured,
        "serper_configured": serper_configured,
        "serpstack_configured": serpstack_configured,
        "serpapi_configured": serpapi_configured,
        "empty_result_likely_causes": empty_causes,
    }


def _build_source_capability_matrix(
    *,
    topic: str,
    query_terms: list[str],
    source_kinds: list[str],
    domains: list[str],
    search_queries: list[dict[str, Any]],
    provider_diagnostics: dict[str, Any],
    source_item_count: int,
    max_candidates: int,
) -> dict[str, Any]:
    keyword_variants = _build_query_matrix_variants(
        query=" ".join(query_terms) or topic,
        query_terms=query_terms,
        domains=domains,
        matrix_mode=True,
    )
    provider_routes = []
    readiness = dict(provider_diagnostics.get("provider_readiness") or {})
    for provider_name in ["serper", "google", "serpstack", "serpapi", "ddg", "searxng", "yacy"]:
        meta = dict(readiness.get(provider_name) or {})
        provider_routes.append(
            {
                "provider": provider_name,
                "configured": bool(meta.get("configured")),
                "route_class": "paid_search" if provider_name in {"serper", "google", "serpstack", "serpapi"} else "fallback_or_local",
                "use_when": (
                    "preferred configured provider for live candidate retrieval"
                    if bool(meta.get("configured")) and provider_name in set(provider_diagnostics.get("configured_paid_providers") or [])
                    else "fallback branch; preserve diagnostics and do not claim absence from zero results"
                ),
            }
        )
    internal_routes = [
        {"tool": "project.context.bundle", "scope": "internal_existing", "purpose": "project-local evidence inventory first"},
        {"tool": "project.structured_data.search", "scope": "internal_existing", "purpose": "stored structured/project data"},
        {"tool": "project.structured_graph.query", "scope": "internal_existing", "purpose": "entity/relation/clue graph evidence"},
        {"tool": "source.history.read", "scope": "session_existing", "purpose": "recover prior candidate reviews and URL-pool submissions"},
        {"tool": "source_library.item.list", "scope": "source_catalog", "purpose": "collection entrypoints, not already ingested evidence"},
    ]
    external_routes = [
        {"tool": "source.discovery.plan", "scope": "external_candidate_plan", "purpose": "no-fetch/no-write query and trust plan"},
        {"tool": "source.web.search", "scope": "external_live_candidate", "purpose": "bounded live provider candidate retrieval"},
        {"tool": "source.candidate.review", "scope": "governed_decision", "purpose": "approve/defer/reject before ingest"},
        {"tool": "ingest.url_pool.submit", "scope": "governed_ingest", "purpose": "explicit collection boundary after review"},
    ]
    return {
        "contract_version": "agent_core.source_capability_matrix.v1",
        "summary": {
            "topic": topic,
            "intent_facets": ["internal evidence", "external candidates", "source quality", "freshness", "writing/answer fit"],
            "keyword_variant_count": len(keyword_variants),
            "planned_search_query_count": len(search_queries),
            "provider_route_count": len(provider_routes),
            "source_item_count": source_item_count,
            "max_candidates": max_candidates,
            "merge_rank_required": True,
        },
        "intent_facets": [
            {"facet": "internal_project_evidence", "first_tools": ["project.context.bundle", "project.structured_data.search", "project.structured_graph.query"]},
            {"facet": "source_catalog_entrypoints", "first_tools": ["source_library.item.list"], "catalog_items_available": source_item_count},
            {"facet": "external_live_candidates", "first_tools": ["source.discovery.plan", "source.web.search"]},
            {"facet": "quality_and_trust", "first_tools": ["source.discovery.plan", "source.candidate.review"]},
            {"facet": "writing_or_answer_integration", "first_tools": ["writing.document.read", "writing.document.insert_paragraph", "agent_investigation.leads.append"]},
        ],
        "keyword_matrix": [
            {"variant": item, "purpose": _query_variant_purpose(item)}
            for item in keyword_variants
        ],
        "tool_provider_matrix": {
            "internal_routes": internal_routes,
            "external_routes": external_routes,
            "provider_routes": provider_routes,
        },
        "scope_matrix": [
            {"scope": "internal_existing", "rule": "prefer for project facts and writing unless external/new/outside material is explicit or a gap is proven"},
            {"scope": "generated_project_artifacts", "rule": "usable as project context but preserve provenance"},
            {"scope": "source_catalog", "rule": "entrypoint for collection; not treated as already available evidence"},
            {"scope": "external_candidate", "rule": "search result only until candidate review and ingest complete"},
            {"scope": "external_ingested", "rule": "answer-grade only after task/status/readback evidence confirms availability"},
        ],
        "evidence_matrix": [
            "candidate title/snippet/url",
            "trust score and blocked reason",
            "provider diagnostics",
            "stored document or dataset path",
            "source-history review/submission state",
            "URL-pool task event/status readback",
        ],
        "verification_matrix": [
            "provider readiness check",
            "dedupe by normalized URL/checksum",
            "candidate review before ingest",
            "status/readback before replacing pending writing evidence",
            "zero-result branches remain uncertainty unless matrix coverage is adequate",
        ],
        "merge_rank_policy": {
            "dedupe_key": "normalized_url_or_checksum",
            "rank_order": ["accepted trust status", "trust_score", "configured provider", "official/regulatory domains", "branch diversity"],
            "absence_claim_rule": "blocked unless multiple query/provider/internal branches have been verified or explicitly unavailable",
        },
    }


def _normalize_source_search_providers(raw: Any, *, default_provider: str) -> list[str]:
    allowed = {"auto", "ddg", "google", "serper", "serpstack", "serpapi", "searxng", "yacy"}
    providers: list[str] = []
    for item in _normalize_string_list(raw):
        provider = item.lower()
        if provider in allowed and provider not in providers:
            providers.append(provider)
    default = str(default_provider or "auto").strip().lower() or "auto"
    if default not in allowed:
        default = "auto"
    if not providers:
        providers = [default]
    elif default not in providers and len(providers) < 3:
        providers.insert(0, default)
    return providers[:3]


def _build_query_matrix_variants(*, query: str, query_terms: list[str], domains: list[str], matrix_mode: bool) -> list[str]:
    base = str(query or " ".join(query_terms) or "").strip()
    terms = " ".join(query_terms[:6]).strip() or base
    variants: list[str] = []
    for candidate in [
        base,
        f"{terms} official report data".strip(),
        f"{terms} policy regulation evidence".strip(),
        f"{terms} market statistics dataset".strip(),
        f"{terms} academic working paper empirical evidence".strip(),
    ]:
        cleaned = " ".join(candidate.split())
        if cleaned and cleaned not in variants:
            variants.append(cleaned)
    if domains and base:
        domain_hint = " OR ".join(f"site:{domain}" for domain in domains[:3])
        candidate = f"({domain_hint}) {base}".strip()
        if candidate not in variants:
            variants.append(candidate)
    return variants[:4] if matrix_mode else variants[:1]


def _apply_domain_clause(query: str, domains: list[str]) -> str:
    if not domains:
        return query
    if "site:" in query:
        return query
    domain_clause = " OR ".join(f"site:{domain}" for domain in domains[:5])
    return f"({domain_clause}) {query}" if query else domain_clause


def _build_source_search_branch_specs(
    *,
    query_variants: list[str],
    providers: list[str],
    max_branches: int,
) -> list[dict[str, Any]]:
    branches: list[dict[str, Any]] = []
    for query_index, query in enumerate(query_variants, start=1):
        for provider in providers:
            branch = {
                "query": query,
                "provider": provider,
                "purpose": _query_variant_purpose(query),
                "query_index": query_index,
            }
            if branch not in branches:
                branches.append(branch)
            if len(branches) >= max_branches:
                return branches
    return branches


def _query_variant_purpose(query: str) -> str:
    lowered = str(query or "").lower()
    if "site:" in lowered:
        return "domain constrained verification branch"
    if "official" in lowered or "report" in lowered:
        return "authoritative/official source branch"
    if "policy" in lowered or "regulation" in lowered:
        return "policy/regulatory evidence branch"
    if "market" in lowered or "statistics" in lowered or "dataset" in lowered:
        return "quantitative market/data branch"
    if "academic" in lowered or "working paper" in lowered:
        return "academic/empirical branch"
    return "base semantic query branch"


def _merge_rank_web_search_candidates(candidates: list[dict[str, Any]], *, max_results: int) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in candidates:
        trust = dict(item.get("trust") or {})
        key = str(item.get("url") or trust.get("url_checksum") or item.get("title") or "").strip()
        if not key:
            continue
        existing = merged.get(key)
        branch = dict(item.pop("_matrix_branch", {}) or {})
        if existing is None:
            item["matrix_branches"] = [branch] if branch else []
            merged[key] = item
            continue
        existing_score = float((existing.get("trust") or {}).get("trust_score") or 0)
        item_score = float(trust.get("trust_score") or 0)
        if branch:
            branches = list(existing.get("matrix_branches") or [])
            if all(existing_branch.get("branch_id") != branch.get("branch_id") for existing_branch in branches):
                branches.append(branch)
            existing["matrix_branches"] = branches[:8]
        if item_score > existing_score:
            item["matrix_branches"] = existing.get("matrix_branches") or ([branch] if branch else [])
            merged[key] = item
    ranked = sorted(
        merged.values(),
        key=lambda item: (
            str((item.get("trust") or {}).get("status") or "") != "accepted",
            -float((item.get("trust") or {}).get("trust_score") or 0),
            str(item.get("url") or ""),
        ),
    )
    for index, item in enumerate(ranked[:max_results], start=1):
        item["matrix_rank"] = index
        item["branch_count"] = len(list(item.get("matrix_branches") or []))
    return ranked[:max_results]


def _build_web_search_matrix_summary(
    *,
    matrix_mode: bool,
    query_variants: list[str],
    providers: list[str],
    branches: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    completed = [item for item in branches if item.get("status") == "completed"]
    failed = [item for item in branches if item.get("status") == "failed"]
    zero_result = [item for item in completed if int(item.get("result_count") or 0) == 0]
    provider_names = sorted({str(item.get("provider") or "") for item in branches if item.get("provider")})
    return {
        "contract_version": "agent_core.source_web_search_matrix.v1",
        "matrix_mode": matrix_mode,
        "query_variant_count": len(query_variants),
        "provider_count": len(providers),
        "branch_count": len(branches),
        "completed_branch_count": len(completed),
        "failed_branch_count": len(failed),
        "zero_result_branch_count": len(zero_result),
        "merged_candidate_count": len(candidates),
        "accepted_candidate_count": sum(1 for item in candidates if str((item.get("trust") or {}).get("status") or "") == "accepted"),
        "providers_considered": provider_names,
        "merge_rank_applied": True,
        "dedupe_policy": "normalized_url_or_checksum",
        "absence_claim_allowed": False if not candidates else None,
        "absence_claim_rule": "A zero-result branch is provider/query uncertainty, not evidence absence, unless the matrix has verified enough independent routes.",
    }


def _normalize_web_search_results(raw_results: Any, *, query: str, min_trust_score: float) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(list(raw_results or []), start=1):
        if not isinstance(raw, dict):
            continue
        url = str(raw.get("canonical_link") or raw.get("link") or raw.get("url") or raw.get("href") or "").strip()
        if not url:
            continue
        trust = build_source_candidate_plan(
            project_key="-",
            query=query,
            urls=[url],
            max_candidates=1,
            min_trust_score=min_trust_score,
        )
        assessments = list(trust.get("candidate_urls") or []) + list(trust.get("rejected_urls") or []) + list(trust.get("duplicate_urls") or [])
        assessment = dict(assessments[0] if assessments else {})
        normalized_url = str(assessment.get("normalized_url") or url).strip()
        dedupe_key = normalized_url or url
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        candidates.append(
            {
                "rank": index,
                "title": str(raw.get("title") or "").strip(),
                "url": normalized_url,
                "snippet": str(raw.get("snippet") or raw.get("body") or "").strip(),
                "source_provider": str(raw.get("source") or raw.get("provider") or "").strip(),
                "keyword": str(raw.get("keyword") or "").strip(),
                "published_at": raw.get("published_at") or raw.get("date"),
                "trust": {
                    "status": assessment.get("status") or "rejected",
                    "trust_score": assessment.get("trust_score"),
                    "trust_level": assessment.get("trust_level"),
                    "domain": assessment.get("domain"),
                    "blocked_reason": assessment.get("blocked_reason"),
                    "url_checksum": assessment.get("url_checksum"),
                    "pre_ingest_required_checks": assessment.get("pre_ingest_required_checks") or [],
                },
            }
        )
    return candidates


def _source_candidate_review_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="source.candidate.review",
        title="Review Source Candidate",
        description_for_model=(
            "Record a user/model review decision for a concrete external source candidate. "
            "Use this when a searched source candidate is approved, deferred, or rejected. "
            "The tool writes only the current agent session artifact and returns a concrete next-step payload: "
            "approved source-library item keys become ingest.source_library.run payloads; approved URLs become URL-pool ingest payloads for the next collection boundary."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "project_key": {"type": "string"},
                "artifact_name": {"type": "string"},
                "decision": {"type": "string", "enum": ["approved", "approve", "采集", "deferred", "defer", "暂缓", "rejected", "reject", "拒绝"]},
                "reason": {"type": "string"},
                "preferred_ingest": {"type": "string", "enum": ["auto", "url_pool", "source_library", "manual"]},
                "source_library_item_key": {"type": "string"},
                "idempotency_key": {"type": "string"},
                "candidate": {"type": "object", "additionalProperties": True},
            },
            "required": ["decision", "candidate"],
            "additionalProperties": False,
        },
        source="project",
        risk="write_shared",
        permission="allow",
        concurrency="serial",
        timeout_seconds=10,
        result_budget=7000,
        project_service_id="source.candidate.review",
        metadata={"contract_version": "source.candidate.review.v1", "auto_allow_session_write": True, "no_external_io": True},
    )


def _source_candidate_review_handler(
    service: AgentSessionService,
) -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        project_key = _resolve_project_key(tool_call, request)
        if not project_key:
            return _missing_project_result(tool_call)
        candidate = _normalize_source_candidate(_candidate_review_input(tool_call.arguments.get("candidate")))
        decision = _normalize_source_candidate_decision(tool_call.arguments.get("decision"))
        artifact_name = str(tool_call.arguments.get("artifact_name") or "source.candidate_reviews.json").strip() or "source.candidate_reviews.json"
        preferred_ingest = str(tool_call.arguments.get("preferred_ingest") or "auto").strip() or "auto"
        if preferred_ingest not in {"auto", "url_pool", "source_library", "manual"}:
            preferred_ingest = "auto"
        source_library_item_key = str(tool_call.arguments.get("source_library_item_key") or candidate.get("item_key") or "").strip()
        reason = str(tool_call.arguments.get("reason") or "").strip()
        idempotency_key = str(tool_call.arguments.get("idempotency_key") or "").strip()
        review_key = idempotency_key or _source_candidate_review_key(project_key=project_key, decision=decision, candidate=candidate)
        ingest_payload = _build_source_candidate_ingest_payload(
            project_key=project_key,
            candidate=candidate,
            decision=decision,
            preferred_ingest=preferred_ingest,
            source_library_item_key=source_library_item_key,
        )
        review = {
            "review_key": review_key,
            "decision": decision,
            "reason": reason,
            "candidate": candidate,
            "preferred_ingest": preferred_ingest,
            "source_library_item_key": source_library_item_key,
            "ingest_payload": ingest_payload,
            "next_gate": _source_candidate_next_gate(decision=decision, ingest_payload=ingest_payload),
            "reviewed_at": _utcnow_iso(),
            "source_call_id": tool_call.call_id,
        }

        existing_artifact = next((item for item in service.list_artifacts(request.session_id) if item.get("name") == artifact_name), None)
        existing_content = dict((existing_artifact or {}).get("content_json") or {})
        replay_keys = [str(item or "") for item in list(existing_content.get("replay_keys") or []) if str(item or "").strip()]
        replayed = bool(idempotency_key and idempotency_key in replay_keys)
        reviews = [dict(item) for item in list(existing_content.get("reviews") or []) if isinstance(item, dict)]
        if not replayed:
            reviews = [item for item in reviews if str(item.get("review_key") or "") != review_key]
            reviews.append(review)
            if idempotency_key:
                replay_keys.append(idempotency_key)
        counts = {
            "approved": sum(1 for item in reviews if str(item.get("decision") or "") == "approved"),
            "deferred": sum(1 for item in reviews if str(item.get("decision") or "") == "deferred"),
            "rejected": sum(1 for item in reviews if str(item.get("decision") or "") == "rejected"),
        }
        updated_content = {
            **existing_content,
            "contract_version": "source.candidate.review.v1",
            "project_key": project_key,
            "updated_at": _utcnow_iso(),
            "source_call_id": tool_call.call_id,
            "replay_keys": replay_keys[-50:],
            "reviews": reviews[-100:],
            "counts": counts,
        }
        artifact = service.store.upsert_artifact(
            {
                "session_id": request.session_id,
                "name": artifact_name,
                "artifact_type": "source_candidate_review_state",
                "mime_type": "application/json",
                "content_text": json.dumps(updated_content, ensure_ascii=False, sort_keys=True, default=str),
                "content_json": updated_content,
                "metadata": {
                    "project_key": project_key,
                    "contract_version": "source.candidate.review.v1",
                    "auto_written_by": "agent_core",
                    "replayed": replayed,
                },
            }
        )
        payload_type = str((ingest_payload or {}).get("type") or "none")
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=(
                f"Reviewed source candidate as {decision}; "
                f"ingest_payload_type={payload_type}; artifact={artifact_name}; counts={counts}."
            ),
            structured_content={
                "contract_version": "source.candidate.review.v1",
                "project_key": project_key,
                "artifact": _compact_json_value(artifact, max_items=16, max_depth=4),
                "review": _compact_json_value(review, max_items=18, max_depth=5),
                "decision": decision,
                "ingest_payload": ingest_payload,
                "next_gate": review["next_gate"],
                "counts": counts,
                "replayed": replayed,
            },
            artifact_refs=(str(artifact.get("artifact_id") or artifact_name),),
        )

    return handler


def _normalize_source_candidate(value: Any) -> dict[str, Any]:
    raw = dict(value or {}) if isinstance(value, dict) else {}
    trust = dict(raw.get("trust") or {}) if isinstance(raw.get("trust"), dict) else {}
    url = str(raw.get("url") or raw.get("normalized_url") or raw.get("original_url") or raw.get("link") or "").strip()
    title = str(raw.get("title") or raw.get("name") or trust.get("domain") or url or "source candidate").strip()
    snippet = str(raw.get("snippet") or raw.get("summary") or raw.get("body") or "").strip()
    provider = str(raw.get("provider") or raw.get("source_provider") or raw.get("source") or "").strip()
    item_key = str(raw.get("item_key") or raw.get("source_library_item_key") or "").strip()
    return {
        **raw,
        "title": title,
        "url": url,
        "snippet": snippet,
        "provider": provider,
        "item_key": item_key,
        "trust": trust,
    }


def _candidate_review_input(value: Any) -> dict[str, Any]:
    """Pure projection from a shared candidate to the established review payload."""
    if isinstance(value, Candidate):
        return {
            **dict(value.raw),
            "url": value.resource_uri,
            "title": value.title,
            "snippet": value.snippet,
            "source": value.source,
            "keyword": value.keyword,
            "rank": value.original_rank,
            "result_rank": value.result_rank,
        }
    return dict(value) if isinstance(value, dict) else {}


def _normalize_source_candidate_decision(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"approved", "approve", "accept", "accepted", "采集", "通过", "采用", "批准"}:
        return "approved"
    if text in {"deferred", "defer", "later", "pending", "暂缓", "稍后", "保留"}:
        return "deferred"
    return "rejected"


def _source_candidate_review_key(*, project_key: str, decision: str, candidate: dict[str, Any]) -> str:
    trust = dict(candidate.get("trust") or {}) if isinstance(candidate.get("trust"), dict) else {}
    raw = "|".join(
        [
            project_key,
            decision,
            str(candidate.get("url") or ""),
            str(candidate.get("item_key") or ""),
            str(candidate.get("title") or ""),
            str(trust.get("url_checksum") or ""),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _build_source_candidate_ingest_payload(
    *,
    project_key: str,
    candidate: dict[str, Any],
    decision: str,
    preferred_ingest: str,
    source_library_item_key: str,
) -> dict[str, Any] | None:
    if decision != "approved":
        return None
    url = str(candidate.get("url") or "").strip()
    if source_library_item_key and preferred_ingest != "url_pool":
        return {
            "type": "source_library",
            "project_key": project_key,
            "items": [source_library_item_key],
            "async_mode": True,
            "override_params": {"source_mode": "agent_candidate_review"},
        }
    if url and preferred_ingest != "source_library":
        trust = dict(candidate.get("trust") or {}) if isinstance(candidate.get("trust"), dict) else {}
        return {
            "type": "url_pool",
            "project_key": project_key,
            "url": url,
            "source_name": str(candidate.get("title") or trust.get("domain") or url),
            "metadata": {
                "source": "agent_candidate_review",
                "title": candidate.get("title"),
                "snippet": candidate.get("snippet"),
                "provider": candidate.get("provider"),
                "trust": trust,
            },
        }
    return {
        "type": "manual",
        "project_key": project_key,
        "reason": "approved candidate lacks URL or source-library item key",
    }


def _source_candidate_next_gate(*, decision: str, ingest_payload: dict[str, Any] | None) -> str:
    if decision == "approved" and ingest_payload:
        payload_type = str(ingest_payload.get("type") or "manual")
        if payload_type == "source_library":
            return "run_ingest.source_library.run_with_payload"
        if payload_type == "url_pool":
            return "run_ingest.url_pool.submit_with_payload"
        return "manual_source_registration_required"
    if decision == "deferred":
        return "keep_candidate_in_review_queue"
    return "candidate_rejected_no_ingest"


__all__ = [
    "query_project_tool_sources",
    "register_query_project_tools",
]
