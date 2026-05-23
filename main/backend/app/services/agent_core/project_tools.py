from __future__ import annotations

from collections import deque
from collections.abc import Callable
from datetime import datetime, timezone
import difflib
import hashlib
import importlib
import inspect
import json
import os
from typing import Any

from app.services.agent_runtime.capability_registry import list_interactive_agent_capabilities
from app.services.agent_runtime.control_tools import AgentControlToolRuntime
from app.services.agent_runtime.external_tool_status import (
    clear_mounted_mcp_tools,
    get_external_service_status,
    list_external_service_statuses,
    mark_mcp_tool_mounted,
)
from app.services.agent_runtime.read_only_tools import ReadOnlyAgentToolRuntime
from app.services.agent_runtime.structured_data_quality import audit_project_structured_data_quality
from app.services.agent_runtime.structured_data_search import query_project_structured_data
from app.services.agent_sessions.service import AgentSessionService
from app.services.projects import bind_project
from app.services.search.vector_contracts import (
    AGENT_MATRIX_SEARCH_EVIDENCE_CONTRACT_VERSION,
    GLOBAL_VECTOR_OBJECT_CONTRACT_VERSION,
    SEARCH_EVIDENCE_HIT_CONTRACT_VERSION,
    SEARCH_RETRIEVAL_RUN_CONTRACT_VERSION,
    build_agent_matrix_evidence_hits,
    build_retrieval_run_record,
)
from app.services.search.web import search_sources
from app.services.source_library.source_candidate_trust import build_source_candidate_plan
from app.services.skill_runtime import invoke_skill, list_registered_skills
from app.services.writing import (
    WritingVersionConflictError,
    create_document,
    get_document,
    list_documents,
    list_citations,
    save_document_with_conflict,
    upsert_citations,
)
from app.settings.config import settings

from .contracts import AgentCoreRequest, CoreEvent, CoreToolCall, CoreToolResult, CoreToolSpec
from .registry import CoreToolRegistry


SourceLibraryLister = Callable[[str | None], list[dict[str, Any]]]
StructuredDataSearcher = Callable[..., dict[str, Any]]
MountedMcpToolHandler = Callable[[dict[str, Any], AgentCoreRequest], dict[str, Any]]

_MOUNTED_MCP_TOOLS: dict[str, tuple[dict[str, Any], MountedMcpToolHandler]] = {}


def register_agent_core_mcp_tool(
    *,
    service_id: str,
    tool_name: str,
    description: str,
    input_schema: dict[str, Any] | None = None,
    handler: MountedMcpToolHandler,
) -> None:
    """Register a mounted MCP-compatible tool for AgentCore.

    The default project ships with only the internal catalog mounted. This hook
    is the stable boundary for real MCP servers or tests to expose a concrete
    callable without pretending an unconfigured service exists.
    """

    normalized_tool_name = str(tool_name or "").strip()
    if not normalized_tool_name:
        raise ValueError("tool_name is required")
    _MOUNTED_MCP_TOOLS[normalized_tool_name] = (
        {
            "service_id": str(service_id or "project-internal-catalog").strip() or "project-internal-catalog",
            "tool_name": normalized_tool_name,
            "status": "available",
            "description": str(description or "").strip(),
            "input_schema": dict(input_schema or {"type": "object", "properties": {}, "additionalProperties": True}),
            "mounted": True,
        },
        handler,
    )
    mark_mcp_tool_mounted(service_id=str(service_id or "project-internal-catalog").strip() or "project-internal-catalog", tool_name=normalized_tool_name)


def clear_agent_core_mcp_tools() -> None:
    _MOUNTED_MCP_TOOLS.clear()
    clear_mounted_mcp_tools()


def build_project_core_tool_registry(
    *,
    service: AgentSessionService,
    source_library_lister: SourceLibraryLister | None = None,
    structured_data_searcher: StructuredDataSearcher | None = None,
) -> CoreToolRegistry:
    """Project tool projection for the model-owned core.

    Existing agent_runtime tools are adapted into CoreToolSpec/CoreToolResult so
    the model can select project abilities through schemas instead of mechanical
    capability classification.
    """

    registry = CoreToolRegistry()
    read_only_runtime = ReadOnlyAgentToolRuntime(
        service=service,
        source_library_lister=source_library_lister,
        structured_data_searcher=structured_data_searcher,
    )
    control_runtime = AgentControlToolRuntime(service=service)

    for tool_definition in read_only_runtime.list_tool_definitions():
        spec = _spec_from_tool_definition(tool_definition, source="project")

        def read_only_handler(
            tool_call: CoreToolCall,
            tool_spec: CoreToolSpec,
            request: AgentCoreRequest,
            emit: Callable[[CoreEvent], None],
            runtime: ReadOnlyAgentToolRuntime = read_only_runtime,
        ) -> CoreToolResult:
            old_call = runtime.execute(
                tool_name=tool_call.tool_name,
                turn_id=request.turn_id,
                session_id=request.session_id,
                project_key=request.project_key,
                command=request.message,
                input_payload=dict(tool_call.arguments or {}),
            )
            return _core_result_from_capability_call(tool_call, old_call)

        registry.register(spec, read_only_handler)

    for tool_definition in control_runtime.list_tool_definitions():
        spec = _spec_from_tool_definition(tool_definition, source="project")

        def control_handler(
            tool_call: CoreToolCall,
            tool_spec: CoreToolSpec,
            request: AgentCoreRequest,
            emit: Callable[[CoreEvent], None],
            runtime: AgentControlToolRuntime = control_runtime,
        ) -> CoreToolResult:
            old_call = runtime.execute(
                tool_call.tool_name,
                session_id=request.session_id,
                turn_id=request.turn_id,
                input_payload=dict(tool_call.arguments or {}),
            )
            return _core_result_from_capability_call(tool_call, old_call)

        registry.register(spec, control_handler)

    _register_deepening_tools(
        registry=registry,
        service=service,
        source_library_lister=source_library_lister,
        structured_data_searcher=structured_data_searcher,
    )

    registered = {tool.name for tool in registry.list_specs()}
    for capability in list_interactive_agent_capabilities():
        capability_id = str(capability.get("capability_id") or "").strip()
        if not capability_id or capability_id in registered or capability_id == "agent_session.stream":
            continue
        spec = _spec_from_capability(capability)
        handler = _handler_for_capability(capability_id, service=service)
        if handler is None:
            continue

        registry.register(spec, handler)
        registered.add(capability_id)

    for skill in list_registered_skills():
        skill_id = str(skill.get("skill_id") or "").strip()
        if not skill_id:
            continue
        spec = _spec_from_skill(skill)
        if spec.name in registered:
            continue

        def skill_handler(
            tool_call: CoreToolCall,
            tool_spec: CoreToolSpec,
            request: AgentCoreRequest,
            emit: Callable[[CoreEvent], None],
            skill_meta: dict[str, Any] = dict(skill),
        ) -> CoreToolResult:
            if _session_abort_requested(service=service, session_id=request.session_id):
                return _abort_requested_result(
                    service=service,
                    request=request,
                    tool_call=tool_call,
                    emit=emit,
                    skipped_items=[str(skill_meta.get("skill_id") or tool_call.tool_name)],
                    dispatched_count=0,
                )
            payload = tool_call.arguments.get("payload") if isinstance(tool_call.arguments.get("payload"), dict) else dict(tool_call.arguments or {})
            invoked = invoke_skill(
                skill_id=str(skill_meta.get("skill_id") or ""),
                payload=payload,
                context={
                    "actor_role": "orchestration_runtime",
                    "permissions": list(skill_meta.get("required_permissions") or []),
                    "agent_session_id": request.session_id,
                    "agent_task_id": str((request.context or {}).get("root_task_id") or "").strip() or None,
                    "approval_granted": True,
                    "trace_id": tool_call.call_id,
                    "consumer": "agent_core",
                },
            )
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="completed",
                model_summary=f"invoked skill {skill_meta.get('skill_id')}",
                ui_summary=f"invoked skill {skill_meta.get('skill_id')}",
                structured_content={
                    "skill_id": skill_meta.get("skill_id"),
                    "result": _compact_json_value(invoked.get("result"), max_items=30, max_depth=5),
                    "skill_meta": {
                        "owner": invoked.get("owner"),
                        "execution_profile": invoked.get("execution_profile"),
                        "concurrency_class": invoked.get("concurrency_class"),
                        "approval_policy": invoked.get("approval_policy") or {},
                    },
                },
            )

        registry.register(spec, skill_handler)
        registered.add(spec.name)

    for spec, handler in _mcp_catalog_tool_specs():
        if spec.name not in registered:
            registry.register(spec, handler)
            registered.add(spec.name)

    return registry


def _register_deepening_tools(
    *,
    registry: CoreToolRegistry,
    service: AgentSessionService,
    source_library_lister: SourceLibraryLister | None = None,
    structured_data_searcher: StructuredDataSearcher | None = None,
) -> None:
    """Register Claude Code parity tools that are not part of the legacy runtime.

    These tools are intentionally small vertical slices: durable session task
    planning, compact resume context, graph/data query composition, and
    optimistic writing workbench writeback.
    """

    searcher = structured_data_searcher or query_project_structured_data

    registry.register(_agent_task_plan_append_spec(), _agent_task_plan_append_handler(service))
    registry.register(_agent_long_task_stage_update_spec(), _agent_long_task_stage_update_handler(service))
    registry.register(_agent_long_task_stage_read_spec(), _agent_long_task_stage_read_handler(service))
    registry.register(_agent_session_resume_bundle_spec(), _agent_session_resume_bundle_handler(service))
    registry.register(_project_graph_search_spec(), _project_graph_search_handler(searcher))
    registry.register(_project_structured_graph_query_spec(), _project_structured_graph_query_handler(searcher))
    registry.register(_project_structured_data_quality_audit_spec(), _project_structured_data_quality_audit_handler())
    registry.register(_clue_chain_expand_spec(), _clue_chain_expand_handler(service))
    registry.register(_source_discovery_plan_spec(), _source_discovery_plan_handler(source_library_lister))
    registry.register(_source_web_search_spec(), _source_web_search_handler())
    registry.register(_source_candidate_review_spec(), _source_candidate_review_handler(service))
    registry.register(_ingest_url_pool_submit_spec(), _ingest_url_pool_submit_handler(service))
    registry.register(_ingest_url_pool_status_spec(), _ingest_url_pool_status_handler(service, searcher))
    registry.register(_source_history_read_spec(), _source_history_read_handler(service))
    registry.register(_agent_investigation_leads_append_spec(), _agent_investigation_leads_append_handler(service))
    registry.register(_agent_investigation_trace_read_spec(), _agent_investigation_trace_read_handler(service))
    registry.register(_writing_document_list_spec(), _writing_document_list_handler())
    registry.register(_writing_document_read_spec(), _writing_document_read_handler())
    registry.register(_writing_document_section_read_spec(), _writing_document_section_read_handler())
    registry.register(_writing_document_create_spec(), _writing_document_create_handler())
    registry.register(_writing_document_insert_paragraph_spec(), _writing_document_insert_paragraph_handler())
    registry.register(_writing_document_citations_upsert_spec(), _writing_document_citations_upsert_handler())
    registry.register(_agent_batch_submit_spec(), _agent_batch_submit_handler())
    registry.register(_skill_search_spec(), _skill_search_handler())
    registry.register(_skill_load_spec(), _skill_load_handler())


def _agent_batch_submit_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="agent_batch.submit",
        title="Submit Agent Batch Work",
        description_for_model=(
            "Submit governed background agent_batch work from either a natural-language command or structured jobs. "
            "Use this only for explicit user requests to run long project work, collect/search sources, or dispatch batch tasks."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "project_key": {"type": "string"},
                "command": {"type": "string", "description": "Natural-language work request. If present, the loop planner dispatch path is used."},
                "jobs": {
                    "type": "array",
                    "description": "Structured agent_batch jobs used when command is omitted.",
                    "items": {"type": "object", "additionalProperties": True},
                },
                "batch": {
                    "type": "object",
                    "properties": {"jobs": {"type": "array", "items": {"type": "object", "additionalProperties": True}}},
                    "additionalProperties": True,
                },
                "idempotency_key": {"type": "string"},
                "priority": {"type": "integer", "minimum": 0, "maximum": 9},
                "dry_run": {"type": "boolean"},
                "enable_bounded_retry": {"type": "boolean"},
                "enable_limited_branching": {"type": "boolean"},
                "rule_set_id": {"type": "string"},
                "rule_set": {"type": "object", "additionalProperties": True},
            },
            "additionalProperties": False,
        },
        source="project",
        risk="write_external",
        permission="ask",
        concurrency="serial",
        timeout_seconds=30,
        result_budget=8000,
        project_service_id="agent_batch.submit",
        metadata={"contract_version": "agent_batch.submit.v1", "implemented": True},
    )


def _agent_batch_submit_handler() -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        return _run_agent_batch_submit_tool(tool_call=tool_call, request=request, legacy_nl_only=False)

    return handler


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


def _agent_task_plan_append_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="agent_task.plan.append",
        title="Append Agent Task Plan",
        description_for_model=(
            "Append durable subtasks to the current agent session for long-running work. "
            "Use this when the user asks for multi-step writing, investigation, clue tracing, or work that should continue across turns. "
            "This mutates only the session task ledger and is idempotent when idempotency_key or identical task content is replayed."
        ),
        input_schema={
            "type": "object",
            "required": ["tasks"],
            "properties": {
                "goal": {"type": "string", "description": "Optional refined goal for the appended plan."},
                "idempotency_key": {"type": "string", "description": "Stable key for replay-safe task creation."},
                "sequential": {"type": "boolean", "description": "When true, later tasks depend on the previous task unless dependencies are explicit."},
                "tasks": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 50,
                    "items": {
                        "type": "object",
                        "required": ["subject"],
                        "properties": {
                            "task_id": {"type": "string"},
                            "subject": {"type": "string"},
                            "description": {"type": "string"},
                            "phase": {
                                "type": "string",
                                "enum": ["conversation", "research", "synthesis", "implementation", "verification", "maintenance"],
                            },
                            "task_type": {"type": "string"},
                            "priority": {"type": "integer", "minimum": 1, "maximum": 10},
                            "blocked_by": {"type": "array", "items": {"type": "string"}},
                            "blocked_by_refs": {"type": "array", "items": {"type": "string"}},
                            "read_set": {"type": "array", "items": {"type": "string"}},
                            "write_set": {"type": "array", "items": {"type": "string"}},
                            "completion_criteria": {"type": "array", "items": {"type": "string"}},
                            "verification_steps": {"type": "array", "items": {"type": "string"}},
                            "artifact_targets": {"type": "array", "items": {"type": "string"}},
                            "metadata": {"type": "object", "additionalProperties": True},
                        },
                        "additionalProperties": True,
                    },
                },
            },
            "additionalProperties": False,
        },
        source="project",
        risk="write_shared",
        permission="allow",
        concurrency="serial",
        timeout_seconds=10,
        result_budget=5000,
        project_service_id="agent_task.plan.append",
        metadata={"auto_allow_session_write": True, "contract_version": "agent_task.plan.append.v1"},
    )


def _agent_task_plan_append_handler(
    service: AgentSessionService,
) -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        raw_tasks = tool_call.arguments.get("tasks") or tool_call.arguments.get("task_blueprints") or []
        if not isinstance(raw_tasks, list) or not raw_tasks:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary="agent_task.plan.append requires a non-empty tasks array.",
                error={"code": "missing_tasks", "message": "tasks must be a non-empty array"},
            )

        idempotency_key = str(tool_call.arguments.get("idempotency_key") or "").strip()
        normalized_for_hash = _compact_json_value(raw_tasks, max_items=60, max_depth=6, max_string=800)
        if not idempotency_key:
            idempotency_key = _stable_hash(
                {
                    "session_id": request.session_id,
                    "goal": tool_call.arguments.get("goal") or request.message,
                    "tasks": normalized_for_hash,
                }
            )

        existing_tasks = service.list_tasks(request.session_id)
        existing_ids = {str(task.get("task_id") or "") for task in existing_tasks}
        existing_keys = {
            str((task.get("metadata") or {}).get("agent_core_plan_idempotency_key") or "")
            for task in existing_tasks
            if isinstance(task.get("metadata"), dict)
        }
        if idempotency_key in existing_keys:
            matched = [
                _compact_task(task)
                for task in existing_tasks
                if str((task.get("metadata") or {}).get("agent_core_plan_idempotency_key") or "") == idempotency_key
            ]
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="completed",
                model_summary=f"Task plan already exists; skipped duplicate append with {len(matched)} task(s).",
                structured_content={
                    "contract_version": "agent_task.plan.append.v1",
                    "session_id": request.session_id,
                    "idempotency_key": idempotency_key,
                    "created_count": 0,
                    "skipped_count": len(matched),
                    "tasks": matched,
                    "duplicate_replay": True,
                },
            )

        sequential = bool(tool_call.arguments.get("sequential"))
        blueprints: list[dict[str, Any]] = []
        skipped_task_ids: list[str] = []
        for index, raw in enumerate(raw_tasks[:50], start=1):
            if not isinstance(raw, dict):
                continue
            subject = str(raw.get("subject") or raw.get("title") or "").strip()
            if not subject:
                continue
            task_id = str(raw.get("task_id") or "").strip()
            if task_id and task_id in existing_ids:
                skipped_task_ids.append(task_id)
                continue
            blocked_by_refs = list(raw.get("blocked_by_refs") or [])
            if sequential and index > 1 and not raw.get("blocked_by") and "prev" not in blocked_by_refs:
                blocked_by_refs.append("prev")
            metadata = dict(raw.get("metadata") or {})
            metadata.update(
                {
                    "created_by": "agent_core",
                    "agent_core_call_id": tool_call.call_id,
                    "agent_core_plan_idempotency_key": idempotency_key,
                    "agent_core_plan_index": index,
                }
            )
            blueprint = {
                "subject": subject,
                "description": raw.get("description"),
                "phase": str(raw.get("phase") or "research").strip() or "research",
                "task_type": str(raw.get("task_type") or raw.get("phase") or "research").strip() or "research",
                "priority": int(raw.get("priority") or 5),
                "blocked_by": list(raw.get("blocked_by") or []),
                "blocked_by_refs": blocked_by_refs,
                "read_set": list(raw.get("read_set") or []),
                "write_set": list(raw.get("write_set") or []),
                "completion_criteria": list(raw.get("completion_criteria") or []),
                "verification_steps": list(raw.get("verification_steps") or []),
                "artifact_targets": list(raw.get("artifact_targets") or []),
                "metadata": metadata,
                "task_spec": dict(raw.get("task_spec") or {}),
            }
            if task_id:
                blueprint["task_id"] = task_id
            blueprints.append(blueprint)

        if not blueprints:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="completed",
                model_summary=f"No new tasks were appended; skipped {len(skipped_task_ids)} existing task id(s).",
                structured_content={
                    "contract_version": "agent_task.plan.append.v1",
                    "session_id": request.session_id,
                    "idempotency_key": idempotency_key,
                    "created_count": 0,
                    "skipped_task_ids": skipped_task_ids,
                },
            )

        try:
            created = service.append_task_blueprints(
                request.session_id,
                goal=str(tool_call.arguments.get("goal") or request.message or "").strip() or None,
                task_blueprints=blueprints,
            )
        except Exception as exc:  # noqa: BLE001
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary=f"Failed to append task plan: {exc}",
                error={"code": exc.__class__.__name__, "message": str(exc)},
            )

        compact_tasks = [_compact_task(task) for task in created]
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=f"Appended {len(created)} durable task(s) to the current agent session.",
            ui_summary=f"Added {len(created)} task(s) to the session plan.",
            structured_content={
                "contract_version": "agent_task.plan.append.v1",
                "session_id": request.session_id,
                "idempotency_key": idempotency_key,
                "created_count": len(created),
                "skipped_task_ids": skipped_task_ids,
                "tasks": compact_tasks,
            },
        )

    return handler


_LONG_TASK_STAGE_ORDER = (
    "plan",
    "internal_evidence",
    "gap_analysis",
    "external_discovery",
    "source_intake",
    "clue_trace",
    "draft_output",
    "verification",
    "done",
)

_LONG_TASK_STAGE_LABELS = {
    "plan": "Plan stages",
    "internal_evidence": "Internal evidence pass",
    "gap_analysis": "Gap list",
    "external_discovery": "External discovery plan",
    "source_intake": "Source intake and trust gates",
    "clue_trace": "Clue trace",
    "draft_output": "Draft or artifact outputs",
    "verification": "Verification",
    "done": "Done",
}

_LONG_TASK_STAGE_STATUSES = {"pending", "in_progress", "completed", "blocked", "failed"}


def _agent_long_task_stage_update_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="agent_long_task.stage.update",
        title="Update Long Task Stage State",
        description_for_model=(
            "Persist durable stage-machine state for long writing or investigation work. "
            "Use after planning, internal evidence search, gap detection, external discovery planning, source intake, clue tracing, draft output, or verification. "
            "This writes only the current agent session state artifact and can be replayed safely with idempotency_key."
        ),
        input_schema={
            "type": "object",
            "required": ["stage"],
            "properties": {
                "project_key": {"type": "string"},
                "artifact_name": {"type": "string"},
                "task_id": {"type": "string"},
                "task_kind": {"type": "string", "enum": ["investigation", "writing", "mixed"], "default": "mixed"},
                "stage": {"type": "string", "enum": list(_LONG_TASK_STAGE_ORDER)},
                "stage_status": {"type": "string", "enum": sorted(_LONG_TASK_STAGE_STATUSES), "default": "in_progress"},
                "summary": {"type": "string"},
                "idempotency_key": {"type": "string"},
                "evidence_refs": {"type": "array", "items": {"oneOf": [{"type": "string"}, {"type": "object", "additionalProperties": True}]}},
                "gap_list": {"type": "array", "items": {"oneOf": [{"type": "string"}, {"type": "object", "additionalProperties": True}]}},
                "external_discovery_plan": {"type": "array", "items": {"oneOf": [{"type": "string"}, {"type": "object", "additionalProperties": True}]}},
                "source_intake": {"type": "array", "items": {"oneOf": [{"type": "string"}, {"type": "object", "additionalProperties": True}]}},
                "clue_refs": {"type": "array", "items": {"oneOf": [{"type": "string"}, {"type": "object", "additionalProperties": True}]}},
                "draft_refs": {"type": "array", "items": {"oneOf": [{"type": "string"}, {"type": "object", "additionalProperties": True}]}},
                "next_actions": {"type": "array", "items": {"oneOf": [{"type": "string"}, {"type": "object", "additionalProperties": True}]}},
                "metadata": {"type": "object", "additionalProperties": True},
            },
            "additionalProperties": False,
        },
        source="project",
        risk="write_shared",
        permission="allow",
        concurrency="serial",
        timeout_seconds=10,
        result_budget=7000,
        project_service_id="agent_long_task.stage.update",
        metadata={"auto_allow_session_write": True, "contract_version": "agent_long_task.stage.v1"},
    )


def _agent_long_task_stage_update_handler(
    service: AgentSessionService,
) -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        stage = _normalize_long_task_stage(tool_call.arguments.get("stage"))
        stage_status = _normalize_long_task_stage_status(tool_call.arguments.get("stage_status"))
        project_key = _resolve_project_key(tool_call, request) or str(request.project_key or "").strip() or None
        artifact_name = str(tool_call.arguments.get("artifact_name") or "agent_long_task.state.json").strip() or "agent_long_task.state.json"
        task_id = str(tool_call.arguments.get("task_id") or "").strip() or None
        task_kind = str(tool_call.arguments.get("task_kind") or "mixed").strip().lower()
        if task_kind not in {"investigation", "writing", "mixed"}:
            task_kind = "mixed"
        existing_artifact = next((item for item in service.list_artifacts(request.session_id) if item.get("name") == artifact_name), None)
        existing_content = dict((existing_artifact or {}).get("content_json") or {})
        idempotency_key = str(tool_call.arguments.get("idempotency_key") or "").strip()
        replay_keys = [str(item or "") for item in list(existing_content.get("replay_keys") or []) if str(item or "").strip()]
        replayed = bool(idempotency_key and idempotency_key in replay_keys)
        if replayed:
            updated_content = _normalize_long_task_state(existing_content, session_id=request.session_id, project_key=project_key, task_kind=task_kind)
        else:
            if idempotency_key:
                replay_keys.append(idempotency_key)
            updated_content = _update_long_task_state(
                existing_content=existing_content,
                session_id=request.session_id,
                project_key=project_key,
                task_kind=task_kind,
                task_id=task_id,
                tool_call=tool_call,
                stage=stage,
                stage_status=stage_status,
                replay_keys=replay_keys[-80:],
            )
        artifact = service.store.upsert_artifact(
            {
                "session_id": request.session_id,
                "name": artifact_name,
                "artifact_type": "agent_long_task_state",
                "mime_type": "application/json",
                "content_text": json.dumps(updated_content, ensure_ascii=False, sort_keys=True, default=str),
                "content_json": updated_content,
                "metadata": {
                    "project_key": project_key,
                    "task_kind": task_kind,
                    "contract_version": "agent_long_task.stage.v1",
                    "auto_written_by": "agent_core",
                    "replayed": replayed,
                },
            }
        )
        if task_id:
            _attach_long_task_state_to_task(
                service=service,
                session_id=request.session_id,
                task_id=task_id,
                artifact_name=artifact_name,
                state=updated_content,
                stage=stage,
                stage_status=stage_status,
            )
        service.store.append_event(
            request.session_id,
            event_type="agent_long_task.stage.updated",
            task_id=task_id,
            payload={
                "artifact_name": artifact_name,
                "stage": stage,
                "stage_status": stage_status,
                "current_stage": updated_content.get("current_stage"),
                "replayed": replayed,
            },
        )
        state = _compact_long_task_state(updated_content)
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=f"Updated long-task stage {stage} as {stage_status}; current_stage={state.get('current_stage')}.",
            structured_content={
                "contract_version": "agent_long_task.stage.v1",
                "project_key": project_key,
                "artifact_name": artifact_name,
                "artifact_id": artifact.get("artifact_id"),
                "state": state,
                "replayed": replayed,
            },
            artifact_refs=(str(artifact.get("artifact_id") or artifact_name),),
        )

    return handler


def _agent_long_task_stage_read_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="agent_long_task.stage.read",
        title="Read Long Task Stage State",
        description_for_model=(
            "Read durable long writing/investigation stage-machine state from the current session. "
            "Use before continuing a long task after page switch, hard refresh, or a follow-up like 'continue'."
        ),
        input_schema={
            "type": "object",
            "properties": {"artifact_name": {"type": "string"}},
            "additionalProperties": False,
        },
        source="project",
        risk="read_only",
        permission="allow",
        concurrency="parallel",
        timeout_seconds=10,
        result_budget=7000,
        project_service_id="agent_long_task.stage.read",
        metadata={"contract_version": "agent_long_task.stage.v1"},
    )


def _agent_long_task_stage_read_handler(
    service: AgentSessionService,
) -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        artifact_name = str(tool_call.arguments.get("artifact_name") or "agent_long_task.state.json").strip() or "agent_long_task.state.json"
        artifact = next((item for item in service.list_artifacts(request.session_id) if item.get("name") == artifact_name), None)
        if artifact is None:
            state = _seed_long_task_state(session_id=request.session_id, project_key=request.project_key, task_kind="mixed", replay_keys=[])
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="completed",
                model_summary=f"No long-task stage artifact named {artifact_name} exists yet.",
                structured_content={
                    "contract_version": "agent_long_task.stage.v1",
                    "artifact_name": artifact_name,
                    "missing_artifact": True,
                    "state": _compact_long_task_state(state),
                },
            )
        content = _normalize_long_task_state(
            dict(artifact.get("content_json") or {}),
            session_id=request.session_id,
            project_key=request.project_key,
            task_kind=str((artifact.get("metadata") or {}).get("task_kind") or "mixed"),
        )
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=f"Read long-task stage state from {artifact_name}: current_stage={content.get('current_stage')}.",
            structured_content={
                "contract_version": "agent_long_task.stage.v1",
                "artifact_name": artifact_name,
                "missing_artifact": False,
                "artifact_id": artifact.get("artifact_id"),
                "state": _compact_long_task_state(content),
            },
            artifact_refs=(str(artifact.get("artifact_id") or artifact_name),),
        )

    return handler


def _agent_session_resume_bundle_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="agent_session.resume_bundle",
        title="Agent Session Resume Bundle",
        description_for_model=(
            "Read a compact resume bundle for the current session, including active tasks, recent messages, artifacts, approvals, and status. "
            "Use this before continuing long-running work or resolving ambiguous follow-up instructions."
        ),
        input_schema={
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 30}},
            "additionalProperties": False,
        },
        source="project",
        risk="read_only",
        permission="allow",
        concurrency="parallel",
        timeout_seconds=10,
        result_budget=5000,
        project_service_id="agent_session.resume_bundle",
    )


def _agent_session_resume_bundle_handler(
    service: AgentSessionService,
) -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        limit = max(1, min(30, int(tool_call.arguments.get("limit") or 10)))
        try:
            bundle = service.get_session_bundle(request.session_id)
        except Exception as exc:  # noqa: BLE001
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary=f"Failed to read session resume bundle: {exc}",
                error={"code": exc.__class__.__name__, "message": str(exc)},
            )
        tasks = list(bundle.get("tasks") or [])
        artifacts = list(bundle.get("artifacts") or [])
        active_tasks = [task for task in tasks if str(task.get("status") or "") not in {"completed", "failed", "canceled", "expired"}]
        long_task_states = [
            _compact_long_task_state(_normalize_long_task_state(dict(item.get("content_json") or {}), session_id=request.session_id, project_key=request.project_key, task_kind=str((item.get("metadata") or {}).get("task_kind") or "mixed")))
            for item in artifacts
            if str(item.get("artifact_type") or "") == "agent_long_task_state"
        ]
        content = {
            "contract_version": "agent_session.resume_bundle.v1",
            "session": _compact_session(dict(bundle.get("session") or {})),
            "active_tasks": [_compact_task(task) for task in active_tasks[:limit]],
            "recent_tasks": [_compact_task(task) for task in tasks[-limit:]],
            "recent_messages": _compact_json_value(list(bundle.get("messages") or [])[-limit:], max_items=limit, max_depth=4),
            "recent_artifacts": _compact_json_value(artifacts[-limit:], max_items=limit, max_depth=4),
            "long_task_states": _compact_json_value(long_task_states[-limit:], max_items=limit, max_depth=5),
            "pending_approvals": _compact_json_value(
                [item for item in list(bundle.get("approvals") or []) if str(item.get("status") or "") in {"pending", "requested"}],
                max_items=limit,
                max_depth=4,
            ),
            "counts": {
                "tasks": len(tasks),
                "active_tasks": len(active_tasks),
                "messages": len(list(bundle.get("messages") or [])),
                "artifacts": len(artifacts),
                "long_task_states": len(long_task_states),
                "approvals": len(list(bundle.get("approvals") or [])),
            },
        }
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=f"Read resume bundle with {len(active_tasks)} active task(s).",
            structured_content=content,
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
        }
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
        "requires_review": True,
        "decision_contract": "ChainDecision",
        "decision_api": f"POST /api/v1/clue-chains/{chain_id}/candidates/{{candidate_id}}/decision",
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
            try:
                if bool(getattr(settings, "agent_core_e2e_scripted_provider_enabled", False)) and branch_query.lower().startswith("e2e "):
                    raw_results = [
                        {
                            "title": "E2E Robotics Policy Candidate",
                            "link": "https://example.gov/robotics-policy",
                            "snippet": "Deterministic external search candidate for AgentCore browser E2E.",
                            "source": "e2e_scripted_search",
                            "keyword": branch_query,
                        }
                    ]
                else:
                    raw_results = search_sources(
                        branch_query,
                        language=language,
                        max_results=branch_limit if matrix_mode else max_results,
                        provider=branch_provider,
                        days_back=days_back,
                        exclude_existing=True,
                    )
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
            search_branches.append(
                {
                    "branch_id": f"b{branch_index}",
                    "query": branch_query,
                    "provider": branch_provider,
                    "purpose": branch.get("purpose"),
                    "status": "completed",
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
        candidate = _normalize_source_candidate(tool_call.arguments.get("candidate"))
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


def _ingest_url_pool_submit_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="ingest.url_pool.submit",
        title="Submit URL-Pool Ingest",
        description_for_model=(
            "Submit an approved URL candidate to the existing URL-pool/source-library ingestion frontdoor. "
            "Use this after source.candidate.review returns an approved URL-pool ingest_payload, or when the user explicitly asks to collect a concrete external URL. "
            "Prefer async_mode=true for interactive chat so the turn returns with a task id instead of waiting for network extraction."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "project_key": {"type": "string"},
                "url": {"type": "string"},
                "query_terms": {"type": "array", "items": {"type": "string"}},
                "strict_mode": {"type": "boolean"},
                "async_mode": {"type": "boolean", "description": "Default true. Queue ingestion and return a task id."},
                "search_options": {"type": "object", "additionalProperties": True},
                "source_name": {"type": "string"},
                "metadata": {"type": "object", "additionalProperties": True},
                "candidate_review_key": {"type": "string"},
                "idempotency_key": {"type": "string"},
                "artifact_name": {"type": "string"},
                "ingest_payload": {
                    "type": "object",
                    "description": "The url_pool ingest_payload returned by source.candidate.review.",
                    "additionalProperties": True,
                },
            },
            "additionalProperties": False,
        },
        source="project",
        risk="write_external",
        permission="allow",
        concurrency="serial",
        timeout_seconds=20,
        result_budget=8000,
        project_service_id="ingest.url_pool.submit",
        metadata={
            "contract_version": "ingest.url_pool.submit.v1",
            "uses_existing_frontdoor": "services.ingest.url_pool.ingest_url_via_source_library_frontdoor",
            "preferred_after_tool": "source.candidate.review",
        },
    )


def _ingest_url_pool_submit_handler(
    service: AgentSessionService,
) -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        raw_payload = tool_call.arguments.get("ingest_payload")
        ingest_payload = dict(raw_payload or {}) if isinstance(raw_payload, dict) else {}
        project_key = str(
            tool_call.arguments.get("project_key")
            or ingest_payload.get("project_key")
            or request.project_key
            or ""
        ).strip()
        if not project_key:
            return _missing_project_result(tool_call)

        url = str(tool_call.arguments.get("url") or ingest_payload.get("url") or "").strip()
        if not url:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary="url is required for URL-pool ingestion.",
                error={"code": "missing_url", "message": "url is required"},
                structured_content={"arguments": dict(tool_call.arguments or {})},
            )

        query_terms = _normalize_string_list(tool_call.arguments.get("query_terms") or ingest_payload.get("query_terms"))
        strict_mode = bool(tool_call.arguments.get("strict_mode") or ingest_payload.get("strict_mode") or False)
        async_mode = bool(tool_call.arguments.get("async_mode", ingest_payload.get("async_mode", True)))
        search_options = tool_call.arguments.get("search_options", ingest_payload.get("search_options"))
        search_options = dict(search_options) if isinstance(search_options, dict) else None
        metadata = dict(ingest_payload.get("metadata") or {})
        if isinstance(tool_call.arguments.get("metadata"), dict):
            metadata.update(dict(tool_call.arguments.get("metadata") or {}))
        source_name = str(
            tool_call.arguments.get("source_name")
            or ingest_payload.get("source_name")
            or metadata.get("title")
            or url
        ).strip()
        artifact_name = str(tool_call.arguments.get("artifact_name") or "ingest.url_pool_submissions.json").strip() or "ingest.url_pool_submissions.json"
        candidate_review_key = str(tool_call.arguments.get("candidate_review_key") or metadata.get("review_key") or "").strip()
        idempotency_key = str(tool_call.arguments.get("idempotency_key") or "").strip() or _stable_hash(
            {
                "project_key": project_key,
                "url": url,
                "query_terms": query_terms,
                "strict_mode": strict_mode,
                "search_options": search_options,
                "candidate_review_key": candidate_review_key,
            }
        )

        if _session_abort_requested(service=service, session_id=request.session_id):
            return _abort_requested_result(
                service=service,
                request=request,
                tool_call=tool_call,
                emit=emit,
                skipped_items=[url],
                dispatched_count=0,
            )

        existing_artifact = next((item for item in service.list_artifacts(request.session_id) if item.get("name") == artifact_name), None)
        existing_content = dict((existing_artifact or {}).get("content_json") or {})
        submissions = [dict(item) for item in list(existing_content.get("submissions") or []) if isinstance(item, dict)]
        replayed_submission = next((item for item in submissions if str(item.get("idempotency_key") or "") == idempotency_key), None)
        if replayed_submission:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="completed",
                model_summary=f"URL-pool ingest submission was already queued for {url}.",
                ui_summary=f"URL-pool ingest already queued: {url}",
                structured_content={
                    "contract_version": "ingest.url_pool.submit.v1",
                    "project_key": project_key,
                    "url": url,
                    "replayed": True,
                    "submission": _compact_json_value(replayed_submission, max_items=18, max_depth=5),
                },
                artifact_refs=(str((existing_artifact or {}).get("artifact_id") or artifact_name),),
            )

        task_search_options = dict(search_options or {})
        deterministic_task_id = f"agent-url-pool-{_stable_hash({'project_key': project_key, 'url': url, 'idempotency_key': idempotency_key})[:24]}"
        agent_submission_marker = {
            "session_id": request.session_id,
            "artifact_name": artifact_name,
            "idempotency_key": idempotency_key,
            "candidate_review_key": candidate_review_key,
            "project_key": project_key,
            "url": url,
            "task_id": deterministic_task_id,
            "source_call_id": tool_call.call_id,
        }
        task_search_options["_agent_core_url_pool_submission"] = agent_submission_marker

        try:
            if bool(getattr(settings, "agent_core_e2e_scripted_provider_enabled", False)):
                task_id = f"e2e-url-pool-{_stable_hash({'project_key': project_key, 'url': url})[:12]}"
                dispatch_result: dict[str, Any] = {
                    "task_id": task_id,
                    "status": "queued",
                    "async": True,
                    "task_result_status": "queued",
                    "params": {
                        "url": url,
                        "query_terms": query_terms or None,
                        "strict_mode": strict_mode,
                        **({"search_options": search_options} if isinstance(search_options, dict) else {}),
                    },
                    "effective_payload": {
                        "url": url,
                        "project_key": project_key,
                        "query_terms": query_terms or None,
                        "strict_mode": strict_mode,
                        "async_mode": True,
                    },
                    "e2e_scripted": True,
                }
                async_mode = True
            elif async_mode:
                from app.services.tasks import task_ingest_url_via_source_library

                task_args = (url, query_terms or None, strict_mode, project_key, task_search_options)
                if hasattr(task_ingest_url_via_source_library, "apply_async"):
                    async_result = task_ingest_url_via_source_library.apply_async(args=task_args, task_id=deterministic_task_id)
                else:
                    async_result = task_ingest_url_via_source_library.delay(*task_args)
                dispatch_result = {
                    "task_id": str(getattr(async_result, "id", "") or ""),
                    "status": "queued",
                    "async": True,
                    "task_result_status": "queued",
                    "params": {
                        "url": url,
                        "query_terms": query_terms or None,
                        "strict_mode": strict_mode,
                        **({"search_options": search_options} if isinstance(search_options, dict) else {}),
                    },
                    "effective_payload": {
                        "url": url,
                        "project_key": project_key,
                        "query_terms": query_terms or None,
                        "strict_mode": strict_mode,
                        "async_mode": True,
                        "agent_session_id": request.session_id,
                    },
                }
            else:
                with bind_project(project_key):
                    from app.services.ingest.url_pool import ingest_url_via_source_library_frontdoor

                    dispatch_result = ingest_url_via_source_library_frontdoor(
                        url=url,
                        project_key=project_key,
                        query_terms=query_terms or None,
                        strict_mode=strict_mode,
                        search_options=task_search_options,
                        frontdoor_options={"enabled": True},
                        entrypoint="agent_core.ingest.url_pool.submit",
                        source_name=source_name or "agent_core_url_pool_submit",
                        enable_extraction=True,
                    )
                    if isinstance(dispatch_result, dict):
                        dispatch_result.setdefault(
                            "effective_payload",
                            {
                                "url": url,
                                "project_key": project_key,
                                "query_terms": query_terms or None,
                                "strict_mode": strict_mode,
                                "async_mode": False,
                                "agent_session_id": request.session_id,
                            },
                        )
        except Exception as exc:  # noqa: BLE001
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary=f"URL-pool ingest submission failed: {exc}",
                error={"code": exc.__class__.__name__, "message": str(exc)},
                structured_content={
                    "contract_version": "ingest.url_pool.submit.v1",
                    "project_key": project_key,
                    "url": url,
                    "async_mode": async_mode,
                    "search_options": search_options,
                },
            )

        if _session_abort_requested(service=service, session_id=request.session_id):
            return _abort_requested_result(
                service=service,
                request=request,
                tool_call=tool_call,
                emit=emit,
                skipped_items=[url],
                dispatched_count=1,
                structured_content={
                    "contract_version": "ingest.url_pool.submit.v1",
                    "project_key": project_key,
                    "url": url,
                    "async_mode": async_mode,
                    "dispatch_result": _compact_json_value(dispatch_result, max_items=20, max_depth=5),
                },
            )

        task_id = str((dispatch_result or {}).get("task_id") or "").strip() if isinstance(dispatch_result, dict) else ""
        submission = {
            "idempotency_key": idempotency_key,
            "project_key": project_key,
            "url": url,
            "task_id": task_id,
            "query_terms": query_terms,
            "strict_mode": strict_mode,
            "async_mode": async_mode,
            "source_name": source_name,
            "metadata": metadata,
            "candidate_review_key": candidate_review_key,
            "dispatch_result": _compact_json_value(dispatch_result, max_items=20, max_depth=5),
            "submitted_at": _utcnow_iso(),
            "source_call_id": tool_call.call_id,
        }
        submissions = [item for item in submissions if str(item.get("idempotency_key") or "") != idempotency_key]
        submissions.append(submission)
        updated_content = {
            **existing_content,
            "contract_version": "ingest.url_pool.submit.v1",
            "project_key": project_key,
            "updated_at": _utcnow_iso(),
            "submissions": submissions[-100:],
            "counts": {
                "submitted": len(submissions),
                "async": sum(1 for item in submissions if bool(item.get("async_mode"))),
                "sync": sum(1 for item in submissions if not bool(item.get("async_mode"))),
            },
        }
        artifact = service.store.upsert_artifact(
            {
                "session_id": request.session_id,
                "name": artifact_name,
                "artifact_type": "url_pool_ingest_submission_state",
                "mime_type": "application/json",
                "content_text": json.dumps(updated_content, ensure_ascii=False, sort_keys=True, default=str),
                "content_json": updated_content,
                "metadata": {
                    "project_key": project_key,
                    "contract_version": "ingest.url_pool.submit.v1",
                    "auto_written_by": "agent_core",
                    "idempotency_key": idempotency_key,
                },
            }
        )
        if bool(getattr(settings, "agent_core_e2e_scripted_provider_enabled", False)) and isinstance(dispatch_result, dict) and dispatch_result.get("e2e_scripted"):
            task_event = {
                "contract_version": "ingest.url_pool.task_event.v1",
                "project_key": project_key,
                "url": url,
                "task_id": task_id or agent_submission_marker["task_id"],
                "status": "completed",
                "idempotency_key": idempotency_key,
                "candidate_review_key": candidate_review_key,
                "source_call_id": tool_call.call_id,
                "recorded_at": _utcnow_iso(),
                "result": _compact_json_value({**dispatch_result, "e2e_scripted_task_event": True}, max_items=18, max_depth=4),
                "error": None,
            }
            submission["task_events"] = [task_event]
            submission["latest_task_status"] = "completed"
            submission["latest_task_event_at"] = task_event["recorded_at"]
            submission["completed_at"] = task_event["recorded_at"]
            submission["task_result"] = task_event["result"]
            try:
                from app.services.tasks import _record_agent_url_pool_task_event

                _record_agent_url_pool_task_event(
                    {**agent_submission_marker, "task_id": task_id or agent_submission_marker["task_id"]},
                    status="completed",
                    result={**dispatch_result, "e2e_scripted_task_event": True},
                )
            except Exception:  # noqa: BLE001
                pass
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=(
                f"Submitted URL-pool ingest for {url}. Project={project_key}. "
                f"async_mode={async_mode}; task_id={task_id or 'not returned'}."
            ),
            ui_summary=f"Submitted URL-pool ingest: {url}",
            structured_content={
                "contract_version": "ingest.url_pool.submit.v1",
                "project_key": project_key,
                "url": url,
                "async_mode": async_mode,
                "task_id": task_id,
                "dispatch_result": _compact_json_value(dispatch_result, max_items=20, max_depth=5),
                "submission": _compact_json_value(submission, max_items=20, max_depth=5),
                "artifact": _compact_json_value(artifact, max_items=16, max_depth=4),
                "replayed": False,
                "next_gate": "inspect_ingest_status_or_source_artifacts",
            },
            artifact_refs=(str(artifact.get("artifact_id") or artifact_name),),
        )

    return handler


def _ingest_url_pool_status_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="ingest.url_pool.status",
        title="Read URL-Pool Ingest Status",
        description_for_model=(
            "Read the status of a URL-pool submission from the current Agent session, recent ingest jobs, and already stored project documents/sources. "
            "Use this before replacing pending writing evidence with verified citations from an approved URL candidate."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "project_key": {"type": "string"},
                "url": {"type": "string"},
                "task_id": {"type": "string"},
                "artifact_name": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "additionalProperties": False,
        },
        source="project",
        risk="read_only",
        permission="allow",
        concurrency="parallel",
        timeout_seconds=10,
        result_budget=9000,
        project_service_id="ingest.url_pool.status",
        metadata={"contract_version": "ingest.url_pool.status.v1", "after_tool": "ingest.url_pool.submit"},
    )


def _ingest_url_pool_status_handler(
    service: AgentSessionService,
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
        artifact_name = str(tool_call.arguments.get("artifact_name") or "ingest.url_pool_submissions.json").strip() or "ingest.url_pool_submissions.json"
        limit = max(1, min(20, int(tool_call.arguments.get("limit") or 8)))
        explicit_url = str(tool_call.arguments.get("url") or "").strip()
        explicit_task_id = str(tool_call.arguments.get("task_id") or "").strip()

        artifact = next((item for item in service.list_artifacts(request.session_id) if item.get("name") == artifact_name), None)
        artifact_content = dict((artifact or {}).get("content_json") or {})
        submissions = [dict(item) for item in list(artifact_content.get("submissions") or []) if isinstance(item, dict)]
        if explicit_url:
            submissions = [item for item in submissions if str(item.get("url") or "").strip() == explicit_url] or submissions
        if explicit_task_id:
            submissions = [
                item
                for item in submissions
                if explicit_task_id in json.dumps(item, ensure_ascii=False, default=str)
            ] or submissions
        latest_submission = submissions[-1] if submissions else {}
        url = explicit_url or str(latest_submission.get("url") or "").strip()
        dispatch = dict(latest_submission.get("dispatch_result") or {}) if isinstance(latest_submission.get("dispatch_result"), dict) else {}
        task_id = explicit_task_id or str(dispatch.get("task_id") or latest_submission.get("task_id") or "").strip()
        task_event_artifact = next((item for item in service.list_artifacts(request.session_id) if item.get("name") == "ingest.url_pool_task_events.json"), None)
        task_event_content = dict((task_event_artifact or {}).get("content_json") or {})
        all_task_events = [dict(item) for item in list(task_event_content.get("events") or []) if isinstance(item, dict)]
        latest_submission_key = str(latest_submission.get("idempotency_key") or "").strip()
        task_events = [
            item
            for item in all_task_events
            if (
                (url and str(item.get("url") or "").strip() == url)
                or (task_id and str(item.get("task_id") or "").strip() == task_id)
                or (latest_submission_key and str(item.get("idempotency_key") or "").strip() == latest_submission_key)
            )
        ][-limit:]
        latest_task_event = task_events[-1] if task_events else {}
        latest_task_event_status = str(latest_task_event.get("status") or "").strip().lower()

        job_matches: list[dict[str, Any]] = []
        try:
            from app.services.job_logger import list_jobs

            needle_values = [item for item in (url, task_id) if item]
            for job in list_jobs(limit=max(20, limit * 4)):
                haystack = json.dumps(job, ensure_ascii=False, default=str)
                if any(needle in haystack for needle in needle_values):
                    job_matches.append(job)
        except Exception as exc:  # noqa: BLE001
            job_error = {"code": exc.__class__.__name__, "message": str(exc)}
        else:
            job_error = None

        stored_result: dict[str, Any] = {}
        if url:
            try:
                stored_result = searcher(project_key=project_key, query=url, limit=limit, datasets=["documents", "sources"])
            except Exception as exc:  # noqa: BLE001
                stored_result = {
                    "contract_version": "project.structured_data.search.v1",
                    "project_key": project_key,
                    "query": url,
                    "items": [],
                    "total_matches": 0,
                    "errors": [{"dataset": "documents|sources", "type": exc.__class__.__name__, "message": str(exc)}],
                }

        evidence_items = list(stored_result.get("items") or []) if isinstance(stored_result, dict) else []
        verified = bool(evidence_items)
        latest_job_status = str((job_matches[0] if job_matches else {}).get("status") or "").strip().lower()
        pending = not verified and latest_task_event_status not in {"failed", "canceled", "cancelled"} and (
            latest_task_event_status != "completed"
            and (bool(task_id) or latest_job_status in {"", "queued", "running", "pending", "started"})
        )
        if verified:
            next_gate = "verified_evidence_ready_for_writing"
            writing_guidance = "Verified project evidence is available; writing may replace pending language with cited evidence."
        elif latest_task_event_status == "failed":
            next_gate = "url_pool_ingest_failed_review_error_or_retry"
            writing_guidance = "The URL-pool ingest task failed; keep writing language pending and inspect the task error before retrying."
        elif latest_task_event_status in {"canceled", "cancelled"}:
            next_gate = "url_pool_ingest_canceled_resume_or_retry"
            writing_guidance = "The URL-pool ingest task was canceled; do not treat it as collected evidence. Use task.continue or retry collection if the user wants to resume."
        elif latest_task_event_status == "completed":
            next_gate = "ingest_completed_without_verified_project_record"
            writing_guidance = "The URL-pool task completed, but no stored project document/source matched the URL yet; keep writing evidence pending and inspect ingest output."
        else:
            next_gate = "wait_for_ingest_completion_or_retry_status"
            writing_guidance = "No stored document/source evidence found yet; keep writing language marked as pending or retry status later."
        payload = {
            "contract_version": "ingest.url_pool.status.v1",
            "project_key": project_key,
            "url": url,
            "task_id": task_id,
            "artifact_name": artifact_name,
            "submission": _compact_json_value(latest_submission, max_items=20, max_depth=5),
            "artifact_found": bool(artifact),
            "task_events": _compact_json_value(task_events, max_items=limit, max_depth=5),
            "latest_task_event": _compact_json_value(latest_task_event, max_items=12, max_depth=4),
            "task_event_artifact_found": bool(task_event_artifact),
            "job_matches": _compact_json_value(job_matches[:limit], max_items=limit, max_depth=4),
            "job_error": job_error,
            "stored_evidence": _compact_json_value(stored_result, max_items=20, max_depth=5),
            "verified": verified,
            "pending": pending,
            "evidence_items": _compact_json_value(evidence_items[:limit], max_items=limit, max_depth=4),
            "next_gate": next_gate,
            "writing_guidance": writing_guidance,
        }
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=(
                f"URL-pool status for {url or task_id or 'latest submission'}: "
                f"verified={verified}, pending={pending}, job_matches={len(job_matches)}."
            ),
            structured_content=payload,
            artifact_refs=(str((artifact or {}).get("artifact_id") or artifact_name),) if artifact else (),
        )

    return handler


def _source_history_read_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="source.history.read",
        title="Read Source Candidate History",
        description_for_model=(
            "Read recent source-candidate decisions and URL-pool submissions from the current Agent session, "
            "optionally including recent sessions in the same project. Use this before continuing a long investigation, "
            "checking prior candidate decisions, or writing with previously approved/collected sources."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "project_key": {"type": "string"},
                "include_recent_sessions": {"type": "boolean"},
                "session_limit": {"type": "integer", "minimum": 1, "maximum": 10},
                "item_limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "additionalProperties": False,
        },
        source="project",
        risk="read_only",
        permission="allow",
        concurrency="parallel",
        timeout_seconds=10,
        result_budget=10000,
        project_service_id="source.history.read",
        metadata={"contract_version": "source.history.read.v1", "no_external_io": True, "no_project_write": True},
    )


def _source_history_read_handler(
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
        include_recent_sessions = bool(tool_call.arguments.get("include_recent_sessions"))
        session_limit = max(1, min(10, int(tool_call.arguments.get("session_limit") or 5)))
        item_limit = max(1, min(50, int(tool_call.arguments.get("item_limit") or 20)))

        session_ids: list[str] = [request.session_id]
        session_meta_by_id: dict[str, dict[str, Any]] = {}
        try:
            current_session = service.get_session(request.session_id)
            session_meta_by_id[request.session_id] = current_session
        except Exception:
            current_session = {"session_id": request.session_id, "project_key": project_key}
            session_meta_by_id[request.session_id] = current_session

        if include_recent_sessions:
            for session in service.list_sessions(limit=max(session_limit * 3, session_limit)):
                sid = str(session.get("session_id") or "").strip()
                if not sid or sid in session_ids:
                    continue
                if str(session.get("project_key") or "").strip() != project_key:
                    continue
                session_ids.append(sid)
                session_meta_by_id[sid] = session
                if len(session_ids) >= session_limit:
                    break

        sessions: list[dict[str, Any]] = []
        totals = {"sessions": 0, "reviews": 0, "approved": 0, "deferred": 0, "rejected": 0, "submissions": 0, "task_events": 0}
        for sid in session_ids[:session_limit]:
            meta = session_meta_by_id.get(sid) or {"session_id": sid}
            try:
                artifacts = service.list_artifacts(sid)
            except Exception:
                artifacts = []
            reviews: list[dict[str, Any]] = []
            submissions: list[dict[str, Any]] = []
            task_events: list[dict[str, Any]] = []
            for artifact in artifacts:
                content = dict(artifact.get("content_json") or {}) if isinstance(artifact.get("content_json"), dict) else {}
                name = str(artifact.get("name") or "").strip()
                contract = str(content.get("contract_version") or "").strip()
                if name == "source.candidate_reviews.json" or contract == "source.candidate.review.v1":
                    reviews.extend([dict(item) for item in list(content.get("reviews") or []) if isinstance(item, dict)])
                if name == "ingest.url_pool_submissions.json" or contract == "ingest.url_pool.submit.v1":
                    submissions.extend([dict(item) for item in list(content.get("submissions") or []) if isinstance(item, dict)])
                if name == "ingest.url_pool_task_events.json" or contract == "ingest.url_pool.task_event.v1":
                    task_events.extend([dict(item) for item in list(content.get("events") or []) if isinstance(item, dict)])

            reviews = _sort_source_history_items(reviews, keys=("reviewed_at", "updated_at"))[-item_limit:]
            submissions = _sort_source_history_items(submissions, keys=("submitted_at", "updated_at"))[-item_limit:]
            task_events = _sort_source_history_items(task_events, keys=("recorded_at", "updated_at"))[-item_limit:]
            counts = {
                "reviews": len(reviews),
                "approved": sum(1 for item in reviews if str(item.get("decision") or "") == "approved"),
                "deferred": sum(1 for item in reviews if str(item.get("decision") or "") == "deferred"),
                "rejected": sum(1 for item in reviews if str(item.get("decision") or "") == "rejected"),
                "submissions": len(submissions),
                "task_events": len(task_events),
            }
            if counts["reviews"] or counts["submissions"] or counts["task_events"] or sid == request.session_id:
                sessions.append(
                    {
                        "session_id": sid,
                        "is_current_session": sid == request.session_id,
                        "goal": str(meta.get("goal") or ""),
                        "updated_at": str(meta.get("updated_at") or ""),
                        "counts": counts,
                        "reviews": _compact_json_value(reviews, max_items=item_limit, max_depth=5),
                        "submissions": _compact_json_value(submissions, max_items=item_limit, max_depth=5),
                        "task_events": _compact_json_value(task_events, max_items=item_limit, max_depth=5),
                    }
                )
                totals["sessions"] += 1
                for key in ("reviews", "approved", "deferred", "rejected", "submissions", "task_events"):
                    totals[key] += counts[key]

        next_gate = "resume_reviewed_sources_or_check_url_pool_status" if totals["reviews"] or totals["submissions"] else "run_source_discovery_or_search_first"
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=(
                f"Read source history: sessions={totals['sessions']}, reviews={totals['reviews']}, "
                f"submissions={totals['submissions']}."
            ),
            structured_content={
                "contract_version": "source.history.read.v1",
                "project_key": project_key,
                "session_id": request.session_id,
                "include_recent_sessions": include_recent_sessions,
                "totals": totals,
                "sessions": _compact_json_value(sessions, max_items=session_limit, max_depth=6),
                "next_gate": next_gate,
                "guidance": (
                    "Use approved reviews and URL-pool submissions as prior context. Call ingest.url_pool.status before treating queued sources as verified writing evidence."
                    if totals["reviews"] or totals["submissions"]
                    else "No prior source history was found in the checked sessions; start with internal context, source.discovery.plan, and source.web.search when external material is needed."
                ),
            },
        )

    return handler


def _sort_source_history_items(items: list[dict[str, Any]], *, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: next((str(item.get(key) or "") for key in keys if str(item.get(key) or "").strip()), ""),
    )


def _agent_investigation_leads_append_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="agent_investigation.leads.append",
        title="Append Investigation Leads",
        description_for_model=(
            "Append multi-round investigation state to the current agent session artifact trail. "
            "Use this after tracing leads across local data, graph nodes, source-library records, or source-discovery plans. "
            "It records clue nodes/edges, pending questions, followed leads, rejected leads, and citations without external I/O."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "project_key": {"type": "string"},
                "artifact_name": {"type": "string"},
                "goal": {"type": "string"},
                "summary": {"type": "string"},
                "idempotency_key": {"type": "string"},
                "clue_nodes": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "clue_edges": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "pending_questions": {
                    "type": "array",
                    "items": {"oneOf": [{"type": "string"}, {"type": "object", "additionalProperties": True}]},
                },
                "followed_leads": {
                    "type": "array",
                    "items": {"oneOf": [{"type": "string"}, {"type": "object", "additionalProperties": True}]},
                },
                "rejected_leads": {
                    "type": "array",
                    "items": {"oneOf": [{"type": "string"}, {"type": "object", "additionalProperties": True}]},
                },
                "citations": {
                    "type": "array",
                    "items": {"oneOf": [{"type": "string"}, {"type": "object", "additionalProperties": True}]},
                },
            },
            "additionalProperties": False,
        },
        source="project",
        risk="write_shared",
        permission="allow",
        concurrency="serial",
        timeout_seconds=10,
        result_budget=7000,
        project_service_id="agent_investigation.leads.append",
        metadata={"contract_version": "agent_investigation.leads.v1", "auto_allow_session_write": True},
    )


def _agent_investigation_leads_append_handler(
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
        artifact_name = str(tool_call.arguments.get("artifact_name") or "investigation.leads.json").strip()
        if not artifact_name:
            artifact_name = "investigation.leads.json"
        existing_artifact = next((item for item in service.list_artifacts(request.session_id) if item.get("name") == artifact_name), None)
        existing_content = dict((existing_artifact or {}).get("content_json") or {})
        idempotency_key = str(tool_call.arguments.get("idempotency_key") or "").strip()
        replay_keys = [str(item or "") for item in list(existing_content.get("replay_keys") or []) if str(item or "").strip()]
        replayed = bool(idempotency_key and idempotency_key in replay_keys)

        sections = {
            "clue_nodes": _dedupe_artifact_records(existing_content.get("clue_nodes"), tool_call.arguments.get("clue_nodes")),
            "clue_edges": _dedupe_artifact_records(existing_content.get("clue_edges"), tool_call.arguments.get("clue_edges")),
            "pending_questions": _dedupe_artifact_records(existing_content.get("pending_questions"), tool_call.arguments.get("pending_questions")),
            "followed_leads": _dedupe_artifact_records(existing_content.get("followed_leads"), tool_call.arguments.get("followed_leads")),
            "rejected_leads": _dedupe_artifact_records(existing_content.get("rejected_leads"), tool_call.arguments.get("rejected_leads")),
            "citations": _dedupe_artifact_records(existing_content.get("citations"), tool_call.arguments.get("citations")),
        }
        if replayed:
            sections = {
                key: _normalize_artifact_records(existing_content.get(key))
                for key in sections
            }
        elif idempotency_key:
            replay_keys.append(idempotency_key)

        summary = str(tool_call.arguments.get("summary") or "").strip()
        goal = str(tool_call.arguments.get("goal") or existing_content.get("goal") or request.message or "").strip()
        updated_content = {
            **existing_content,
            "contract_version": "agent_investigation.leads.v1",
            "project_key": project_key,
            "goal": goal,
            "summary": summary or existing_content.get("summary") or "",
            "updated_at": _utcnow_iso(),
            "source_call_id": tool_call.call_id,
            "replay_keys": replay_keys[-50:],
            **sections,
        }
        artifact = service.store.upsert_artifact(
            {
                "session_id": request.session_id,
                "name": artifact_name,
                "artifact_type": "agent_investigation_state",
                "mime_type": "application/json",
                "content_text": json.dumps(updated_content, ensure_ascii=False, sort_keys=True, default=str),
                "content_json": updated_content,
                "metadata": {
                    "project_key": project_key,
                    "contract_version": "agent_investigation.leads.v1",
                    "auto_written_by": "agent_core",
                    "replayed": replayed,
                },
            }
        )
        counts = {key: len(value) for key, value in sections.items()}
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=f"Recorded investigation state in {artifact_name}: {counts}.",
            structured_content={
                "contract_version": "agent_investigation.leads.v1",
                "project_key": project_key,
                "artifact": _compact_json_value(artifact, max_items=16, max_depth=4),
                "counts": counts,
                "replayed": replayed,
            },
            artifact_refs=(str(artifact.get("artifact_id") or artifact_name),),
        )

    return handler


def _agent_investigation_trace_read_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="agent_investigation.trace.read",
        title="Read Investigation Trace",
        description_for_model=(
            "Read the current investigation state artifact and expand clue nodes/edges into a bounded multi-hop trace. "
            "Use this before follow-up investigation, evidence synthesis, or writing from previously collected leads."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "project_key": {"type": "string"},
                "artifact_name": {
                    "type": "string",
                    "description": "Investigation artifact name. Defaults to investigation.leads.json.",
                },
                "focus_node_id": {
                    "type": "string",
                    "description": "Optional clue node id to expand from. If omitted, returns a compact whole-artifact trace.",
                },
                "max_hops": {"type": "integer", "minimum": 0, "maximum": 5, "default": 2},
                "max_items": {"type": "integer", "minimum": 1, "maximum": 100, "default": 30},
            },
            "additionalProperties": False,
        },
        source="project",
        risk="read_only",
        permission="allow",
        concurrency="parallel",
        timeout_seconds=10,
        result_budget=7000,
        project_service_id="agent_investigation.trace.read",
        metadata={"contract_version": "agent_investigation.trace.v1"},
    )


def _agent_investigation_trace_read_handler(
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
        artifact_name = str(tool_call.arguments.get("artifact_name") or "investigation.leads.json").strip()
        if not artifact_name:
            artifact_name = "investigation.leads.json"
        focus_node_id = str(tool_call.arguments.get("focus_node_id") or "").strip()
        max_hops = _bounded_int(tool_call.arguments.get("max_hops"), default=2, minimum=0, maximum=5)
        max_items = _bounded_int(tool_call.arguments.get("max_items"), default=30, minimum=1, maximum=100)

        artifact = next((item for item in service.list_artifacts(request.session_id) if item.get("name") == artifact_name), None)
        if artifact is None:
            payload = {
                "contract_version": "agent_investigation.trace.v1",
                "project_key": project_key,
                "artifact_name": artifact_name,
                "missing_artifact": True,
                "focus_node_id": focus_node_id or None,
                "max_hops": max_hops,
                "nodes": [],
                "edges": [],
                "followed_leads": [],
                "rejected_leads": [],
                "citations": [],
                "pending_questions": [],
                "counts": {"nodes": 0, "edges": 0, "pending_questions": 0, "followed_leads": 0, "citations": 0},
                "trace_summary": "No investigation artifact exists yet; start by appending leads.",
            }
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="completed",
                model_summary=f"No investigation artifact named {artifact_name} exists yet.",
                structured_content=payload,
            )

        content = dict(artifact.get("content_json") or {})
        payload = _build_investigation_trace_payload(
            project_key=project_key,
            artifact_name=artifact_name,
            artifact_content=content,
            focus_node_id=focus_node_id,
            max_hops=max_hops,
            max_items=max_items,
        )
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=(
                f"Read investigation trace from {artifact_name}: "
                f"{payload['counts']['nodes']} node(s), {payload['counts']['edges']} edge(s)."
            ),
            structured_content=payload,
            artifact_refs=(str(artifact.get("artifact_id") or artifact_name),),
        )

    return handler


def _writing_document_list_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="writing.document.list",
        title="List Writing Documents",
        description_for_model="List writing workbench documents for the current project. Use before reading or editing a draft when the target document is unclear.",
        input_schema={
            "type": "object",
            "properties": {
                "project_key": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "additionalProperties": False,
        },
        source="project",
        risk="read_only",
        permission="allow",
        concurrency="parallel",
        timeout_seconds=10,
        result_budget=4000,
        project_service_id="writing.document.list",
    )


def _writing_document_list_handler() -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        project_key = _resolve_project_key(tool_call, request)
        if not project_key:
            return _missing_project_result(tool_call)
        limit = max(1, min(100, int(tool_call.arguments.get("limit") or 20)))
        try:
            with bind_project(project_key):
                documents = list_documents(project_key=project_key, limit=limit)
        except Exception as exc:  # noqa: BLE001
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary=f"Failed to list writing documents: {exc}",
                error={"code": exc.__class__.__name__, "message": str(exc)},
            )
        compact = [_compact_writing_document(item, include_body=False) for item in documents]
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=f"Found {len(compact)} writing document(s).",
            structured_content={
                "contract_version": "writing.document.list.v1",
                "project_key": project_key,
                "documents": compact,
                "total_returned": len(compact),
            },
        )

    return handler


def _writing_document_read_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="writing.document.read",
        title="Read Writing Document",
        description_for_model=(
            "Read one writing workbench document, including version and etag. "
            "Use this before writing so insert tools can pass base_version/if_match."
        ),
        input_schema={
            "type": "object",
            "required": ["doc_id"],
            "properties": {
                "project_key": {"type": "string"},
                "doc_id": {"type": "integer", "minimum": 1},
                "max_chars": {"type": "integer", "minimum": 200, "maximum": 50000},
            },
            "additionalProperties": False,
        },
        source="project",
        risk="read_only",
        permission="allow",
        concurrency="parallel",
        timeout_seconds=10,
        result_budget=8000,
        project_service_id="writing.document.read",
    )


def _writing_document_read_handler() -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        project_key = _resolve_project_key(tool_call, request)
        if not project_key:
            return _missing_project_result(tool_call)
        doc_id = _safe_int(tool_call.arguments.get("doc_id"))
        if not doc_id:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary="doc_id is required to read a writing document.",
                error={"code": "missing_doc_id", "message": "doc_id is required"},
            )
        max_chars = max(200, min(50000, int(tool_call.arguments.get("max_chars") or 8000)))
        try:
            with bind_project(project_key):
                document = get_document(doc_id=doc_id, project_key=project_key)
        except Exception as exc:  # noqa: BLE001
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary=f"Failed to read writing document {doc_id}: {exc}",
                error={"code": exc.__class__.__name__, "message": str(exc)},
            )
        compact = _compact_writing_document(document, include_body=True, max_chars=max_chars)
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=f"Read writing document {doc_id} version {compact.get('version')}.",
            structured_content={
                "contract_version": "writing.document.read.v1",
                "project_key": project_key,
                "document": compact,
            },
        )

    return handler


def _writing_document_section_read_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="writing.document.section.read",
        title="Read Writing Document Section",
        description_for_model=(
            "Read one section or line range from a writing workbench document. "
            "Use this when the user brings a selected passage into context or asks to edit from a specific position."
        ),
        input_schema={
            "type": "object",
            "required": ["doc_id"],
            "properties": {
                "project_key": {"type": "string"},
                "doc_id": {"type": "integer", "minimum": 1},
                "heading": {"type": "string"},
                "block_id": {"type": "string"},
                "line_start": {"type": "integer", "minimum": 1},
                "line_end": {"type": "integer", "minimum": 1},
                "max_chars": {"type": "integer", "minimum": 200, "maximum": 20000},
            },
            "additionalProperties": False,
        },
        source="project",
        risk="read_only",
        permission="allow",
        concurrency="parallel",
        timeout_seconds=10,
        result_budget=7000,
        project_service_id="writing.document.section.read",
    )


def _writing_document_section_read_handler() -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        project_key = _resolve_project_key(tool_call, request)
        if not project_key:
            return _missing_project_result(tool_call)
        doc_id = _safe_int(tool_call.arguments.get("doc_id"))
        if not doc_id:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary="doc_id is required to read a writing document section.",
                error={"code": "missing_doc_id", "message": "doc_id is required"},
            )
        try:
            with bind_project(project_key):
                document = get_document(doc_id=doc_id, project_key=project_key)
        except Exception as exc:  # noqa: BLE001
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary=f"Failed to read writing document section {doc_id}: {exc}",
                error={"code": exc.__class__.__name__, "message": str(exc)},
            )
        body = str(document.get("body_md") or "")
        max_chars = max(200, min(20000, int(tool_call.arguments.get("max_chars") or 5000)))
        section = _extract_writing_section(
            body,
            heading=str(tool_call.arguments.get("heading") or "").strip(),
            block_id=str(tool_call.arguments.get("block_id") or "").strip(),
            line_start=_safe_int(tool_call.arguments.get("line_start")),
            line_end=_safe_int(tool_call.arguments.get("line_end")),
            max_chars=max_chars,
        )
        compact_doc = _compact_writing_document(document, include_body=False)
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=f"Read section from writing document {doc_id}: lines {section.get('line_start')}-{section.get('line_end')}.",
            structured_content={
                "contract_version": "writing.document.section.read.v1",
                "project_key": project_key,
                "document": compact_doc,
                "section": section,
            },
        )

    return handler


def _writing_document_create_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="writing.document.create",
        title="Create Writing Document",
        description_for_model=(
            "Create a formal writing workbench document for the current project. "
            "Use this when the user asks to establish/register a draft, turn an artifact/report into a writing document, "
            "or start a new canvas-backed document before later anchored edits."
        ),
        input_schema={
            "type": "object",
            "required": ["title"],
            "properties": {
                "project_key": {"type": "string"},
                "title": {"type": "string", "minLength": 1, "maxLength": 500},
                "body_md": {"type": "string", "description": "Initial markdown body for the document."},
                "content_md": {"type": "string", "description": "Alias for body_md when the model has already drafted markdown."},
                "dry_run": {"type": "boolean"},
                "source_refs": {"type": "array", "items": {"type": "string"}},
                "provenance": {"type": "object", "additionalProperties": True},
                "metadata_json": {"type": "object", "additionalProperties": True},
            },
            "additionalProperties": False,
        },
        source="project",
        risk="write_shared",
        permission="ask",
        concurrency="serial",
        timeout_seconds=15,
        result_budget=7000,
        project_service_id="writing.document.create",
        metadata={"contract_version": "writing.document.create.v1"},
    )


def _writing_document_create_handler() -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        project_key = _resolve_project_key(tool_call, request)
        if not project_key:
            return _missing_project_result(tool_call)
        title = str(tool_call.arguments.get("title") or "").strip()
        if not title:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary="title is required to create a writing document.",
                error={"code": "missing_title", "message": "title is required"},
            )
        body_md = str(tool_call.arguments.get("body_md") or tool_call.arguments.get("content_md") or "")
        if len(body_md) > 50000:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary="body_md is too large for one writing document create operation.",
                error={"code": "body_too_large", "message": "body_md must be <= 50000 characters"},
            )
        source_refs = _normalize_string_list(tool_call.arguments.get("source_refs"))
        provenance = dict(tool_call.arguments.get("provenance") or {})
        metadata_json = dict(tool_call.arguments.get("metadata_json") or {})
        metadata_json.update(
            {
                "created_by": "agent_core",
                "agent_core_call_id": tool_call.call_id,
                "source_refs": source_refs,
                "provenance": _compact_json_value(provenance, max_items=20, max_depth=4),
                "agent_document_contract": "writing.document.create.v1",
            }
        )
        if bool(tool_call.arguments.get("dry_run")):
            preview_document = {
                "id": None,
                "project_key": project_key,
                "title": title,
                "body_md": body_md,
                "status": "draft",
                "version": 1,
                "etag": None,
                "metadata_json": metadata_json,
            }
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="completed",
                model_summary=f"Prepared writing document create preview: {title}.",
                structured_content={
                    "contract_version": "writing.document.create.v1",
                    "project_key": project_key,
                    "dry_run": True,
                    "document": _compact_writing_document(preview_document, include_body=True),
                    "source_refs": source_refs,
                    "provenance": provenance,
                },
            )
        try:
            with bind_project(project_key):
                saved = create_document(
                    project_key=project_key,
                    title=title,
                    body_md=body_md,
                    updated_by_user_id="agent_core",
                    metadata_json=metadata_json,
                )
        except Exception as exc:  # noqa: BLE001
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary=f"Failed to create writing document: {exc}",
                error={"code": exc.__class__.__name__, "message": str(exc)},
            )
        doc_id = _safe_int(saved.get("id"))
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=f"Created writing document {doc_id}: {saved.get('title') or title}.",
            ui_summary=f"Created writing document {doc_id}: {saved.get('title') or title}.",
            structured_content={
                "contract_version": "writing.document.create.v1",
                "project_key": project_key,
                "doc_id": doc_id,
                "document": _compact_writing_document(saved, include_body=False),
                "source_refs": source_refs,
                "provenance": provenance,
            },
        )

    return handler


def _writing_document_insert_paragraph_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="writing.document.insert_paragraph",
        title="Insert Paragraph Into Writing Document",
        description_for_model=(
            "Insert, prepend, append, or replace text in a writing workbench document. "
            "Use after reading the document. It mutates project writing state and must satisfy version-lock or explicit allow_latest boundaries. "
            "For existing documents, pass base_version/if_match from writing.document.read, or set allow_latest=true when the user explicitly wants to edit the latest server version. "
            "When no doc_id is available, provide title to create a new draft document after the write approval boundary."
        ),
        input_schema={
            "type": "object",
            "required": ["content_md"],
            "properties": {
                "project_key": {"type": "string"},
                "doc_id": {"type": "integer", "minimum": 1},
                "title": {"type": "string"},
                "content_md": {"type": "string"},
                "operation": {
                    "type": "string",
                    "enum": [
                        "append",
                        "prepend",
                        "after_heading",
                        "replace_text",
                        "replace_range",
                        "insert_at_offset",
                        "insert_after_text",
                        "insert_before_text",
                    ],
                    "default": "append",
                },
                "anchor_heading": {"type": "string"},
                "anchor_text": {"type": "string"},
                "range_start": {"type": "integer", "minimum": 0},
                "range_end": {"type": "integer", "minimum": 0},
                "cursor_offset": {"type": "integer", "minimum": 0},
                "selection_snapshot": {"type": "object", "additionalProperties": True},
                "base_version": {"type": "integer", "minimum": 1},
                "if_match": {"type": "string"},
                "allow_latest": {"type": "boolean"},
                "create_if_missing": {"type": "boolean"},
                "dry_run": {"type": "boolean"},
                "idempotency_key": {"type": "string"},
                "source_refs": {"type": "array", "items": {"type": "string"}},
                "provenance": {"type": "object", "additionalProperties": True},
            },
            "additionalProperties": False,
        },
        source="project",
        risk="write_shared",
        permission="ask",
        concurrency="serial",
        timeout_seconds=15,
        result_budget=7000,
        project_service_id="writing.document.insert_paragraph",
        metadata={"contract_version": "writing.document.insert_paragraph.v1"},
    )


def _writing_document_insert_paragraph_handler() -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        project_key = _resolve_project_key(tool_call, request)
        if not project_key:
            return _missing_project_result(tool_call)
        content_md = str(tool_call.arguments.get("content_md") or "").strip()
        if not content_md:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary="content_md is required for writing document insertion.",
                error={"code": "missing_content", "message": "content_md is required"},
            )
        if len(content_md) > 20000:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary="content_md is too large for one insert operation.",
                error={"code": "content_too_large", "message": "content_md must be <= 20000 characters"},
            )

        doc_id = _safe_int(tool_call.arguments.get("doc_id"))
        operation = str(tool_call.arguments.get("operation") or "append").strip() or "append"
        dry_run = bool(tool_call.arguments.get("dry_run"))
        allow_latest = bool(tool_call.arguments.get("allow_latest"))
        base_version = _safe_int(tool_call.arguments.get("base_version"))
        if_match = str(tool_call.arguments.get("if_match") or "").strip() or None
        create_if_missing = bool(tool_call.arguments.get("create_if_missing"))
        title = str(tool_call.arguments.get("title") or "").strip()
        if not doc_id and title:
            create_if_missing = True

        try:
            with bind_project(project_key):
                if doc_id:
                    current = get_document(doc_id=doc_id, project_key=project_key)
                elif create_if_missing:
                    current = {
                        "id": None,
                        "title": title or "Untitled",
                        "body_md": "",
                        "version": 1,
                        "etag": None,
                    }
                else:
                    return CoreToolResult(
                        call_id=tool_call.call_id,
                        tool_name=tool_call.tool_name,
                        status="failed",
                        model_summary="doc_id is required unless create_if_missing=true.",
                        error={"code": "missing_doc_id", "message": "doc_id is required unless create_if_missing=true"},
                    )

                old_body = str(current.get("body_md") or "")
                replayed_update = _find_replayed_agent_writing_update(
                    metadata=current.get("metadata_json"),
                    tool_call=tool_call,
                    current=current,
                    content_md=content_md,
                    operation=operation,
                )
                if replayed_update is not None:
                    return CoreToolResult(
                        call_id=tool_call.call_id,
                        tool_name=tool_call.tool_name,
                        status="completed",
                        model_summary=(
                            f"Writing document edit already applied for idempotency key "
                            f"{replayed_update.get('idempotency_key') or replayed_update.get('call_id')}; no duplicate paragraph inserted."
                        ),
                        ui_summary=f"Writing update already applied: {current.get('title') or doc_id or title}.",
                        structured_content={
                            "contract_version": "writing.document.insert_paragraph.v1",
                            "project_key": project_key,
                            "doc_id": doc_id or current.get("id"),
                            "document": _compact_writing_document(current, include_body=False),
                            "operation": operation,
                            "replayed": True,
                            "diff": {
                                "added_lines": 0,
                                "removed_lines": 0,
                                "old_line_count": len(old_body.splitlines()),
                                "new_line_count": len(old_body.splitlines()),
                                "diff_excerpt": "",
                                "diff_truncated": False,
                            },
                            "source_refs": _normalize_string_list(tool_call.arguments.get("source_refs")),
                            "provenance": dict(tool_call.arguments.get("provenance") or {}),
                            "agent_update": replayed_update,
                        },
                    )
                new_body = _apply_writing_body_operation(
                    old_body,
                    operation=operation,
                    content_md=content_md,
                    anchor_heading=str(tool_call.arguments.get("anchor_heading") or "").strip(),
                    anchor_text=str(tool_call.arguments.get("anchor_text") or "").strip(),
                    range_start=_safe_nonnegative_int(tool_call.arguments.get("range_start")),
                    range_end=_safe_nonnegative_int(tool_call.arguments.get("range_end")),
                    cursor_offset=_safe_nonnegative_int(tool_call.arguments.get("cursor_offset")),
                )
                if len(new_body) > 50000:
                    return CoreToolResult(
                        call_id=tool_call.call_id,
                        tool_name=tool_call.tool_name,
                        status="failed",
                        model_summary="The updated writing document would exceed the 50000 character limit.",
                        error={"code": "document_too_large", "message": "updated document would exceed 50000 characters"},
                    )

                diff = _body_diff_summary(old_body, new_body)
                agent_update = _build_agent_writing_update(
                    tool_call=tool_call,
                    current=current,
                    new_body=new_body,
                    operation=operation,
                    content_md=content_md,
                    diff=diff,
                )
                if dry_run:
                    return CoreToolResult(
                        call_id=tool_call.call_id,
                        tool_name=tool_call.tool_name,
                        status="completed",
                        model_summary=f"Prepared writing document edit preview: +{diff['added_lines']} -{diff['removed_lines']} lines.",
                        structured_content={
                            "contract_version": "writing.document.insert_paragraph.v1",
                            "project_key": project_key,
                            "doc_id": doc_id,
                            "dry_run": True,
                            "operation": operation,
                            "diff": diff,
                            "source_refs": _normalize_string_list(tool_call.arguments.get("source_refs")),
                            "provenance": dict(tool_call.arguments.get("provenance") or {}),
                            "agent_update": agent_update,
                        },
                    )

                if doc_id:
                    current_version = int(current.get("version") or 1)
                    current_etag = str(current.get("etag") or "").strip() or None
                    if not base_version and not if_match and not allow_latest:
                        return CoreToolResult(
                            call_id=tool_call.call_id,
                            tool_name=tool_call.tool_name,
                            status="failed",
                            model_summary=(
                                "Writing mutation needs base_version/if_match from writing.document.read, "
                                "or allow_latest=true for an explicit latest-version edit."
                            ),
                            structured_content={
                                "contract_version": "writing.document.insert_paragraph.v1",
                                "project_key": project_key,
                                "doc_id": doc_id,
                                "current_version": current_version,
                                "current_etag": current_etag,
                                "retry_arguments": {
                                    **dict(tool_call.arguments or {}),
                                    "base_version": current_version,
                                    "if_match": current_etag,
                                },
                            },
                            error={"code": "version_lock_required", "message": "base_version or if_match required"},
                            retry_hint="Call writing.document.read first, then retry with base_version and if_match.",
                        )
                    saved = save_document_with_conflict(
                        doc_id=doc_id,
                        project_key=project_key,
                        body_md=new_body,
                        title=str(tool_call.arguments.get("title") or "").strip() or None,
                        base_version=base_version or (current_version if allow_latest else None),
                        if_match=if_match or (current_etag if allow_latest else None),
                        updated_by_user_id="agent_core",
                        metadata_json=_append_agent_writing_update(
                            current.get("metadata_json"),
                            agent_update,
                        ),
                    )
                else:
                    metadata_json = _append_agent_writing_update(
                        {
                            "created_by": "agent_core",
                            "agent_core_call_id": tool_call.call_id,
                            "source_refs": _normalize_string_list(tool_call.arguments.get("source_refs")),
                            "provenance": dict(tool_call.arguments.get("provenance") or {}),
                        },
                        agent_update,
                    )
                    saved = create_document(
                        project_key=project_key,
                        title=str(tool_call.arguments.get("title") or current.get("title") or "Untitled").strip() or "Untitled",
                        body_md=new_body,
                        updated_by_user_id="agent_core",
                        metadata_json=metadata_json,
                    )
                    doc_id = int(saved.get("id") or 0)
        except WritingVersionConflictError as exc:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary=f"Writing document version conflict: current version is {exc.current_version}.",
                structured_content={"conflict": exc.server_snapshot},
                error={"code": "writing_version_conflict", "message": str(exc), "current_version": exc.current_version},
                retry_hint="Read the document again and retry against the current version.",
            )
        except ValueError as exc:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary=str(exc),
                error={"code": "invalid_writing_operation", "message": str(exc)},
            )
        except Exception as exc:  # noqa: BLE001
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary=f"Failed to update writing document: {exc}",
                error={"code": exc.__class__.__name__, "message": str(exc)},
            )

        document_title = str((saved or {}).get("title") or current.get("title") or tool_call.arguments.get("title") or "Untitled").strip()
        inserted_excerpt = " ".join(str(content_md or "").split())[:180]
        source_ref_count = len(_normalize_string_list(tool_call.arguments.get("source_refs")))
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=(
                f"Updated writing document {doc_id} ({document_title}): operation={operation}, "
                f"+{diff['added_lines']} -{diff['removed_lines']} lines, source_refs={source_ref_count}. "
                f"Inserted excerpt: {inserted_excerpt}"
            ),
            ui_summary=f"Updated writing document {doc_id}: {document_title}.",
            structured_content={
                "contract_version": "writing.document.insert_paragraph.v1",
                "project_key": project_key,
                "doc_id": doc_id,
                "document": _compact_writing_document(saved, include_body=False),
                "operation": operation,
                "diff": diff,
                "source_refs": _normalize_string_list(tool_call.arguments.get("source_refs")),
                "provenance": dict(tool_call.arguments.get("provenance") or {}),
                "agent_update": agent_update,
            },
        )

    return handler


def _writing_document_citations_upsert_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name="writing.document.citations.upsert",
        title="Attach Material Citations To Writing Document",
        description_for_model=(
            "Attach material-card citations to a writing workbench document. "
            "Use this after reading or creating a document when the user asks to add cited material cards, citation cards, "
            "reference cards, source cards, or selected evidence into the writing workbench citation tray. "
            "This writes the formal citation table used by the writing workbench; source_refs on prose edits are only provenance hints."
        ),
        input_schema={
            "type": "object",
            "required": ["doc_id"],
            "properties": {
                "project_key": {"type": "string"},
                "doc_id": {"type": "integer", "minimum": 1},
                "mode": {"type": "string", "enum": ["append", "replace"], "default": "append"},
                "dry_run": {"type": "boolean"},
                "citations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "card_id": {"type": "string"},
                            "source_doc_id": {"type": "integer", "minimum": 1},
                            "source_uri": {"type": "string"},
                            "source_title": {"type": "string"},
                            "quote_text": {"type": "string"},
                            "position_anchor": {"type": "string"},
                            "metadata_json": {"type": "object", "additionalProperties": True},
                        },
                        "additionalProperties": True,
                    },
                },
                "material_cards": {
                    "type": "array",
                    "items": {"type": "object", "additionalProperties": True},
                    "description": "Alias for citations when the model has material card previews with id/title/url/snippet fields.",
                },
                "source_refs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Fallback citation references such as record:94, artifact ids, document ids, or URLs.",
                },
                "position_anchor": {"type": "string"},
                "provenance": {"type": "object", "additionalProperties": True},
            },
            "additionalProperties": False,
        },
        source="project",
        risk="write_shared",
        permission="ask",
        concurrency="serial",
        timeout_seconds=15,
        result_budget=7000,
        project_service_id="writing.document.citations.upsert",
        metadata={"contract_version": "writing.document.citations.upsert.v1"},
    )


def _writing_document_citations_upsert_handler() -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]:
    def handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        project_key = _resolve_project_key(tool_call, request)
        if not project_key:
            return _missing_project_result(tool_call)
        doc_id = _safe_int(tool_call.arguments.get("doc_id"))
        if not doc_id:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary="doc_id is required to attach writing citations.",
                error={"code": "missing_doc_id", "message": "doc_id is required"},
            )
        incoming = _normalize_writing_citation_inputs(tool_call.arguments)
        if not incoming:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary="At least one citation, material card, or source_ref is required.",
                error={"code": "missing_citations", "message": "citations, material_cards, or source_refs required"},
            )
        mode = str(tool_call.arguments.get("mode") or "append").strip().lower()
        if mode not in {"append", "replace"}:
            mode = "append"
        dry_run = bool(tool_call.arguments.get("dry_run"))
        try:
            with bind_project(project_key):
                existing = [] if mode == "replace" else list_citations(doc_id=doc_id, project_key=project_key)
                merged = _merge_writing_citations(existing, incoming)
                saved = merged if dry_run else upsert_citations(doc_id=doc_id, project_key=project_key, citations=merged)
        except Exception as exc:  # noqa: BLE001
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary=f"Failed to attach writing citations: {exc}",
                error={"code": exc.__class__.__name__, "message": str(exc)},
            )

        added_count = max(0, len(saved) - len(existing))
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=f"Attached {added_count} writing citation(s) to document {doc_id}; total citations={len(saved)}.",
            ui_summary=f"Updated writing citations for document {doc_id}: {len(saved)} refs.",
            structured_content={
                "contract_version": "writing.document.citations.upsert.v1",
                "project_key": project_key,
                "doc_id": doc_id,
                "mode": mode,
                "dry_run": dry_run,
                "added_count": added_count,
                "total_count": len(saved),
                "citations": _compact_json_value(saved, max_items=20, max_depth=4),
            },
        )

    return handler


def _normalize_writing_citation_inputs(arguments: dict[str, Any]) -> list[dict[str, Any]]:
    root_anchor = str(arguments.get("position_anchor") or "").strip() or None
    provenance = dict(arguments.get("provenance") or {})
    out: list[dict[str, Any]] = []
    for item in list(arguments.get("citations") or []) + list(arguments.get("material_cards") or []):
        if not isinstance(item, dict):
            continue
        card_id = str(item.get("card_id") or item.get("id") or item.get("source_id") or "").strip() or None
        source_uri = str(item.get("source_uri") or item.get("url") or item.get("uri") or "").strip() or None
        source_title = str(item.get("source_title") or item.get("title") or item.get("label") or card_id or source_uri or "").strip() or None
        quote_text = str(item.get("quote_text") or item.get("quote") or item.get("snippet") or item.get("summary") or "").strip() or None
        source_doc_id = _safe_int(item.get("source_doc_id") or item.get("doc_id"))
        position_anchor = str(item.get("position_anchor") or item.get("anchor") or root_anchor or "").strip() or None
        metadata_json = dict(item.get("metadata_json") or {})
        if provenance:
            metadata_json.setdefault("provenance", provenance)
        if not any([card_id, source_doc_id, source_uri, source_title, quote_text]):
            continue
        out.append(
            _prune_empty_citation(
                {
                    "card_id": card_id,
                    "source_doc_id": source_doc_id,
                    "source_uri": source_uri,
                    "source_title": source_title,
                    "quote_text": quote_text,
                    "position_anchor": position_anchor,
                    "metadata_json": metadata_json,
                }
            )
        )
    for ref in _normalize_string_list(arguments.get("source_refs")):
        ref_metadata: dict[str, Any] = {"source_ref": ref}
        if provenance:
            ref_metadata["provenance"] = provenance
        if ref.startswith(("http://", "https://")):
            citation = {
                "card_id": ref,
                "source_uri": ref,
                "source_title": ref,
                "position_anchor": root_anchor,
                "metadata_json": ref_metadata,
            }
        else:
            citation = {
                "card_id": ref,
                "source_title": ref,
                "position_anchor": root_anchor,
                "metadata_json": ref_metadata,
            }
        out.append(_prune_empty_citation(citation))
    return _merge_writing_citations([], out)


def _prune_empty_citation(citation: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in citation.items() if value not in (None, "", [], {})}


def _merge_writing_citations(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in list(existing or []) + list(incoming or []):
        if not isinstance(item, dict):
            continue
        normalized = _prune_empty_citation(
            {
                "source_doc_id": _safe_int(item.get("source_doc_id")),
                "source_uri": str(item.get("source_uri") or "").strip() or None,
                "source_title": str(item.get("source_title") or item.get("title") or "").strip() or None,
                "quote_text": str(item.get("quote_text") or item.get("quote") or "").strip() or None,
                "position_anchor": str(item.get("position_anchor") or "").strip() or None,
                "card_id": str(item.get("card_id") or item.get("id") or "").strip() or None,
                "metadata_json": dict(item.get("metadata_json") or {}) if isinstance(item.get("metadata_json"), dict) else {},
            }
        )
        identity = _writing_citation_identity(normalized)
        if identity in seen:
            continue
        seen.add(identity)
        merged.append(normalized)
    return merged


def _writing_citation_identity(item: dict[str, Any]) -> tuple[str, str]:
    for key in ("card_id", "source_uri", "source_doc_id"):
        value = item.get(key)
        if value not in (None, ""):
            return key, str(value)
    fallback = "|".join(
        [
            str(item.get("source_title") or ""),
            str(item.get("quote_text") or ""),
            str(item.get("position_anchor") or ""),
        ]
    )
    return "content", _stable_hash(fallback)


def _resolve_project_key(tool_call: CoreToolCall, request: AgentCoreRequest) -> str:
    return str(tool_call.arguments.get("project_key") or request.project_key or "").strip()


def _missing_project_result(tool_call: CoreToolCall) -> CoreToolResult:
    return CoreToolResult(
        call_id=tool_call.call_id,
        tool_name=tool_call.tool_name,
        status="failed",
        model_summary="project_key is required for this project tool.",
        error={"code": "missing_project_key", "message": "project_key is required"},
    )


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _safe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed > 0 else None


def _safe_nonnegative_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed >= 0 else None


def _normalize_string_list(values: Any) -> list[str]:
    if isinstance(values, str):
        values = [values]
    out: list[str] = []
    for value in values or []:
        item = str(value or "").strip()
        if item and item not in out:
            out.append(item)
    return out


def _compact_task(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": task.get("task_id"),
        "parent_task_id": task.get("parent_task_id"),
        "subject": task.get("subject"),
        "description": task.get("description"),
        "task_type": task.get("task_type"),
        "phase": task.get("phase"),
        "status": task.get("status"),
        "priority": task.get("priority"),
        "blocked_by": list(task.get("blocked_by") or []),
        "blocks": list(task.get("blocks") or []),
        "read_set": list(task.get("read_set") or []),
        "write_set": list(task.get("write_set") or []),
        "artifact_targets": list((task.get("task_spec") or {}).get("artifact_targets") or []),
        "result_summary": task.get("result_summary"),
        "result_payload": _compact_json_value(task.get("result_payload"), max_items=8, max_depth=3),
        "summary_label": task.get("summary_label"),
        "last_activity": task.get("last_activity"),
        "metadata": _compact_json_value(task.get("metadata"), max_items=8, max_depth=3),
    }


def _normalize_long_task_stage(value: Any) -> str:
    stage = str(value or "").strip().lower()
    if stage not in _LONG_TASK_STAGE_ORDER:
        raise ValueError(f"unsupported long-task stage: {stage or value}")
    return stage


def _normalize_long_task_stage_status(value: Any) -> str:
    status = str(value or "in_progress").strip().lower() or "in_progress"
    if status not in _LONG_TASK_STAGE_STATUSES:
        raise ValueError(f"unsupported long-task stage status: {status}")
    return status


def _seed_long_task_state(
    *,
    session_id: str,
    project_key: str | None,
    task_kind: str,
    replay_keys: list[str],
) -> dict[str, Any]:
    now = _utcnow_iso()
    return {
        "contract_version": "agent_long_task.stage.v1",
        "session_id": session_id,
        "project_key": project_key,
        "task_kind": task_kind if task_kind in {"investigation", "writing", "mixed"} else "mixed",
        "created_at": now,
        "updated_at": now,
        "current_stage": "plan",
        "replay_keys": replay_keys[-80:],
        "stages": [
            {
                "stage": stage,
                "label": _LONG_TASK_STAGE_LABELS[stage],
                "status": "pending",
                "summary": "",
                "updated_at": None,
                "evidence_refs": [],
                "gap_list": [],
                "external_discovery_plan": [],
                "source_intake": [],
                "clue_refs": [],
                "draft_refs": [],
                "next_actions": [],
                "metadata": {},
            }
            for stage in _LONG_TASK_STAGE_ORDER
        ],
    }


def _normalize_long_task_state(
    content: dict[str, Any],
    *,
    session_id: str,
    project_key: str | None,
    task_kind: str,
) -> dict[str, Any]:
    seeded = _seed_long_task_state(
        session_id=session_id,
        project_key=str(content.get("project_key") or project_key or "").strip() or None,
        task_kind=str(content.get("task_kind") or task_kind or "mixed").strip().lower(),
        replay_keys=[str(item or "") for item in list(content.get("replay_keys") or []) if str(item or "").strip()],
    )
    existing_by_stage = {
        str(item.get("stage") or "").strip(): dict(item)
        for item in list(content.get("stages") or [])
        if isinstance(item, dict)
    }
    normalized_stages: list[dict[str, Any]] = []
    for seeded_stage in seeded["stages"]:
        stage_name = str(seeded_stage.get("stage") or "")
        merged = {**seeded_stage, **existing_by_stage.get(stage_name, {})}
        merged["stage"] = stage_name
        merged["label"] = _LONG_TASK_STAGE_LABELS.get(stage_name, stage_name)
        merged["status"] = str(merged.get("status") or "pending").strip().lower()
        if merged["status"] not in _LONG_TASK_STAGE_STATUSES:
            merged["status"] = "pending"
        for key in ("evidence_refs", "gap_list", "external_discovery_plan", "source_intake", "clue_refs", "draft_refs", "next_actions"):
            merged[key] = _normalize_artifact_records(merged.get(key))
        merged["metadata"] = dict(merged.get("metadata") or {}) if isinstance(merged.get("metadata"), dict) else {}
        normalized_stages.append(merged)
    seeded.update(
        {
            **content,
            "contract_version": "agent_long_task.stage.v1",
            "session_id": session_id,
            "project_key": str(content.get("project_key") or project_key or "").strip() or None,
            "task_kind": str(content.get("task_kind") or task_kind or "mixed").strip().lower() if str(content.get("task_kind") or task_kind or "mixed").strip().lower() in {"investigation", "writing", "mixed"} else "mixed",
            "stages": normalized_stages,
            "current_stage": _derive_long_task_current_stage(normalized_stages, preferred=str(content.get("current_stage") or "")),
        }
    )
    return seeded


def _update_long_task_state(
    *,
    existing_content: dict[str, Any],
    session_id: str,
    project_key: str | None,
    task_kind: str,
    task_id: str | None,
    tool_call: CoreToolCall,
    stage: str,
    stage_status: str,
    replay_keys: list[str],
) -> dict[str, Any]:
    state = _normalize_long_task_state(existing_content, session_id=session_id, project_key=project_key, task_kind=task_kind)
    now = _utcnow_iso()
    stages = list(state.get("stages") or [])
    stage_index = _LONG_TASK_STAGE_ORDER.index(stage)
    for index, item in enumerate(stages):
        if index < stage_index and str(item.get("status") or "pending") == "pending":
            item["status"] = "completed"
            item["summary"] = item.get("summary") or f"Completed before {stage}."
            item["updated_at"] = item.get("updated_at") or now
            item["completed_at"] = item.get("completed_at") or now
        if str(item.get("stage") or "") != stage:
            continue
        item["status"] = stage_status
        item["summary"] = str(tool_call.arguments.get("summary") or item.get("summary") or "").strip()
        item["updated_at"] = now
        item["task_id"] = task_id or item.get("task_id")
        item["source_call_id"] = tool_call.call_id
        if stage_status == "completed":
            item["completed_at"] = now
        for key in ("evidence_refs", "gap_list", "external_discovery_plan", "source_intake", "clue_refs", "draft_refs", "next_actions"):
            item[key] = _dedupe_artifact_records(item.get(key), tool_call.arguments.get(key))
        metadata = dict(item.get("metadata") or {})
        metadata.update(dict(tool_call.arguments.get("metadata") or {}))
        item["metadata"] = metadata
        break
    state.update(
        {
            "updated_at": now,
            "project_key": project_key,
            "task_kind": task_kind,
            "last_stage": stage,
            "last_stage_status": stage_status,
            "source_call_id": tool_call.call_id,
            "replay_keys": replay_keys[-80:],
            "stages": stages,
            "current_stage": _derive_long_task_current_stage(stages, preferred=stage if stage_status != "completed" else ""),
        }
    )
    return state


def _derive_long_task_current_stage(stages: list[dict[str, Any]], *, preferred: str = "") -> str:
    if preferred in _LONG_TASK_STAGE_ORDER:
        preferred_status = next((str(item.get("status") or "") for item in stages if str(item.get("stage") or "") == preferred), "")
        if preferred_status in {"pending", "in_progress", "blocked", "failed"}:
            return preferred
    for stage in _LONG_TASK_STAGE_ORDER:
        status = next((str(item.get("status") or "pending") for item in stages if str(item.get("stage") or "") == stage), "pending")
        if status != "completed":
            return stage
    return "done"


def _compact_long_task_state(state: dict[str, Any]) -> dict[str, Any]:
    stages = list(state.get("stages") or [])
    completed = [str(item.get("stage") or "") for item in stages if str(item.get("status") or "") == "completed"]
    blocked = [str(item.get("stage") or "") for item in stages if str(item.get("status") or "") in {"blocked", "failed"}]
    stage_summaries = []
    for item in stages:
        stage_summaries.append(
            {
                "stage": item.get("stage"),
                "label": item.get("label"),
                "status": item.get("status"),
                "summary": item.get("summary") or "",
                "task_id": item.get("task_id"),
                "updated_at": item.get("updated_at"),
                "counts": {
                    "evidence_refs": len(list(item.get("evidence_refs") or [])),
                    "gap_list": len(list(item.get("gap_list") or [])),
                    "external_discovery_plan": len(list(item.get("external_discovery_plan") or [])),
                    "source_intake": len(list(item.get("source_intake") or [])),
                    "clue_refs": len(list(item.get("clue_refs") or [])),
                    "draft_refs": len(list(item.get("draft_refs") or [])),
                    "next_actions": len(list(item.get("next_actions") or [])),
                },
                "evidence_refs": _compact_json_value(item.get("evidence_refs"), max_items=5, max_depth=3),
                "gap_list": _compact_json_value(item.get("gap_list"), max_items=5, max_depth=3),
                "external_discovery_plan": _compact_json_value(item.get("external_discovery_plan"), max_items=5, max_depth=3),
                "source_intake": _compact_json_value(item.get("source_intake"), max_items=5, max_depth=3),
                "clue_refs": _compact_json_value(item.get("clue_refs"), max_items=5, max_depth=3),
                "draft_refs": _compact_json_value(item.get("draft_refs"), max_items=5, max_depth=3),
                "next_actions": _compact_json_value(item.get("next_actions"), max_items=5, max_depth=3),
            }
        )
    return {
        "contract_version": "agent_long_task.stage.v1",
        "session_id": state.get("session_id"),
        "project_key": state.get("project_key"),
        "task_kind": state.get("task_kind"),
        "current_stage": state.get("current_stage"),
        "completed_stages": completed,
        "blocked_stages": blocked,
        "updated_at": state.get("updated_at"),
        "stage_summaries": stage_summaries,
        "next_actions": _collect_long_task_next_actions(stages),
    }


def _collect_long_task_next_actions(stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in stages:
        for action in _normalize_artifact_records(item.get("next_actions")):
            action.setdefault("stage", item.get("stage"))
            out.append(action)
            if len(out) >= 12:
                return out
    return out


def _attach_long_task_state_to_task(
    *,
    service: AgentSessionService,
    session_id: str,
    task_id: str,
    artifact_name: str,
    state: dict[str, Any],
    stage: str,
    stage_status: str,
) -> None:
    try:
        task = service.store.get_task(session_id, task_id)
    except Exception:
        return
    metadata = dict(task.get("metadata") or {})
    metadata["long_task_state_artifact"] = artifact_name
    metadata["long_task_current_stage"] = state.get("current_stage")
    metadata["long_task_last_stage"] = stage
    result_payload = dict(task.get("result_payload") or {})
    result_payload["long_task_stage_state"] = _compact_long_task_state(state)
    recent_activities = list(task.get("recent_activities") or [])
    recent_activities.append(f"{stage}:{stage_status}")
    service.store.update_task(
        session_id,
        task_id,
        {
            "metadata": metadata,
            "result_payload": result_payload,
            "last_activity": f"long-task stage {stage} {stage_status}",
            "recent_activities": recent_activities[-8:],
        },
    )


def _group_items_by_dataset(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        dataset = str(item.get("dataset") or "unknown").strip() or "unknown"
        grouped.setdefault(dataset, []).append(item)
    return grouped


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        resolved = default
    return max(minimum, min(maximum, resolved))


def _normalize_artifact_records(value: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    raw_items = value if isinstance(value, list) else []
    for raw in raw_items:
        if isinstance(raw, dict):
            item = dict(raw)
        else:
            text = str(raw or "").strip()
            if not text:
                continue
            item = {"text": text}
        item.setdefault("record_id", _stable_hash(item))
        records.append(item)
    return records


def _dedupe_artifact_records(existing: Any, incoming: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in [*_normalize_artifact_records(existing), *_normalize_artifact_records(incoming)]:
        key = str(item.get("record_id") or item.get("id") or item.get("url") or item.get("title") or item.get("text") or _stable_hash(item))
        if key in seen:
            continue
        seen.add(key)
        normalized = dict(item)
        normalized["record_id"] = key
        out.append(normalized)
    return out


def _build_investigation_trace_payload(
    *,
    project_key: str,
    artifact_name: str,
    artifact_content: dict[str, Any],
    focus_node_id: str,
    max_hops: int,
    max_items: int,
) -> dict[str, Any]:
    nodes_by_id, node_order = _normalize_investigation_nodes(artifact_content.get("clue_nodes"))
    edges = _normalize_investigation_edges(artifact_content.get("clue_edges"), nodes_by_id=nodes_by_id, node_order=node_order)
    focus = str(focus_node_id or "").strip()
    if focus:
        selected_node_ids = _trace_investigation_node_ids(
            focus_node_id=focus,
            node_order=node_order,
            edges=edges,
            max_hops=max_hops,
            max_items=max_items,
        )
    else:
        selected_node_ids = node_order[:max_items]

    selected_node_set = set(selected_node_ids)
    selected_edges = [
        edge
        for edge in edges
        if str(edge.get("source") or "") in selected_node_set and str(edge.get("target") or "") in selected_node_set
    ][:max_items]
    selected_nodes = [nodes_by_id[node_id] for node_id in selected_node_ids if node_id in nodes_by_id][:max_items]
    pending_questions = _normalize_artifact_records(artifact_content.get("pending_questions"))[:max_items]
    followed_leads = _normalize_artifact_records(artifact_content.get("followed_leads"))[:max_items]
    rejected_leads = _normalize_artifact_records(artifact_content.get("rejected_leads"))[:max_items]
    citations = _normalize_artifact_records(artifact_content.get("citations"))[:max_items]
    focus_found = bool(not focus or focus in nodes_by_id)
    trace_summary = _summarize_investigation_trace(
        goal=str(artifact_content.get("goal") or "").strip(),
        focus_node_id=focus,
        focus_found=focus_found,
        node_count=len(selected_nodes),
        edge_count=len(selected_edges),
        pending_questions=pending_questions,
    )
    return {
        "contract_version": "agent_investigation.trace.v1",
        "project_key": project_key,
        "artifact_name": artifact_name,
        "artifact_contract_version": artifact_content.get("contract_version"),
        "missing_artifact": False,
        "focus_node_id": focus or None,
        "focus_found": focus_found,
        "max_hops": max_hops,
        "max_items": max_items,
        "goal": artifact_content.get("goal") or "",
        "summary": artifact_content.get("summary") or "",
        "nodes": _compact_json_value(selected_nodes, max_items=max_items, max_depth=4),
        "edges": _compact_json_value(selected_edges, max_items=max_items, max_depth=4),
        "followed_leads": _compact_json_value(followed_leads, max_items=max_items, max_depth=4),
        "rejected_leads": _compact_json_value(rejected_leads, max_items=max_items, max_depth=4),
        "citations": _compact_json_value(citations, max_items=max_items, max_depth=4),
        "pending_questions": _compact_json_value(pending_questions, max_items=max_items, max_depth=4),
        "available_node_ids": node_order[:max_items],
        "counts": {
            "nodes": len(selected_nodes),
            "edges": len(selected_edges),
            "all_nodes": len(node_order),
            "all_edges": len(edges),
            "pending_questions": len(pending_questions),
            "followed_leads": len(followed_leads),
            "rejected_leads": len(rejected_leads),
            "citations": len(citations),
        },
        "trace_summary": trace_summary,
        "next_steps": _derive_investigation_next_steps(pending_questions, followed_leads, citations, focus_found=focus_found),
    }


def _normalize_investigation_nodes(value: Any) -> tuple[dict[str, dict[str, Any]], list[str]]:
    nodes_by_id: dict[str, dict[str, Any]] = {}
    node_order: list[str] = []
    for index, raw in enumerate(_normalize_artifact_records(value), start=1):
        node_id = _first_text_value(raw, ("id", "node_id", "entity_id", "record_id", "url", "title", "label", "name", "text"))
        if not node_id:
            node_id = f"node-{index}"
        node = dict(raw)
        node["id"] = node_id
        node.setdefault("label", _first_text_value(node, ("label", "title", "name", "text")) or node_id)
        if node_id in nodes_by_id:
            nodes_by_id[node_id].update({key: value for key, value in node.items() if value not in (None, "", [])})
            continue
        nodes_by_id[node_id] = node
        node_order.append(node_id)
    return nodes_by_id, node_order


def _normalize_investigation_edges(
    value: Any,
    *,
    nodes_by_id: dict[str, dict[str, Any]],
    node_order: list[str],
) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(_normalize_artifact_records(value), start=1):
        source = _first_text_value(raw, ("source", "source_id", "from", "from_id", "start", "subject", "subject_id"))
        target = _first_text_value(raw, ("target", "target_id", "to", "to_id", "end", "object", "object_id"))
        if not source or not target:
            continue
        for node_id in (source, target):
            if node_id not in nodes_by_id:
                nodes_by_id[node_id] = {"id": node_id, "label": node_id, "inferred_from_edge": True}
                node_order.append(node_id)
        relation = _first_text_value(raw, ("relation", "label", "type", "predicate", "text")) or "related_to"
        edge_id = _first_text_value(raw, ("id", "edge_id", "record_id")) or f"{source}->{relation}->{target}"
        if edge_id in seen:
            continue
        seen.add(edge_id)
        edge = dict(raw)
        edge.update({"id": edge_id, "source": source, "target": target, "relation": relation})
        edges.append(edge)
    return edges


def _trace_investigation_node_ids(
    *,
    focus_node_id: str,
    node_order: list[str],
    edges: list[dict[str, Any]],
    max_hops: int,
    max_items: int,
) -> list[str]:
    if focus_node_id not in set(node_order):
        return []
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_order}
    for edge in edges:
        source = str(edge.get("source") or "").strip()
        target = str(edge.get("target") or "").strip()
        if not source or not target:
            continue
        adjacency.setdefault(source, []).append(target)
        adjacency.setdefault(target, []).append(source)

    selected: list[str] = []
    visited: set[str] = {focus_node_id}
    queue: deque[tuple[str, int]] = deque([(focus_node_id, 0)])
    while queue and len(selected) < max_items:
        node_id, hops = queue.popleft()
        selected.append(node_id)
        if hops >= max_hops:
            continue
        for neighbor in adjacency.get(node_id, []):
            if neighbor in visited:
                continue
            visited.add(neighbor)
            queue.append((neighbor, hops + 1))
    return selected


def _first_text_value(item: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, (dict, list)):
            continue
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _summarize_investigation_trace(
    *,
    goal: str,
    focus_node_id: str,
    focus_found: bool,
    node_count: int,
    edge_count: int,
    pending_questions: list[dict[str, Any]],
) -> str:
    if focus_node_id and not focus_found:
        return f"Focus node {focus_node_id} was not found in the investigation artifact."
    scope = f"from focus node {focus_node_id}" if focus_node_id else "from the whole investigation artifact"
    question_text = _first_text_value(pending_questions[0], ("text", "question", "title")) if pending_questions else ""
    suffix = f" Next unresolved question: {question_text}" if question_text else ""
    prefix = f"Goal: {goal}. " if goal else ""
    return f"{prefix}Expanded {node_count} node(s) and {edge_count} edge(s) {scope}.{suffix}"


def _derive_investigation_next_steps(
    pending_questions: list[dict[str, Any]],
    followed_leads: list[dict[str, Any]],
    citations: list[dict[str, Any]],
    *,
    focus_found: bool,
) -> list[str]:
    if not focus_found:
        return ["Pick one available_node_id as focus_node_id or append the missing clue node first."]
    steps: list[str] = []
    if pending_questions:
        steps.append("Use pending_questions to drive the next project-data search or external source-discovery plan.")
    if followed_leads and not citations:
        steps.append("Validate followed_leads with citations before writing derived claims.")
    if citations:
        steps.append("Use citations and selected trace nodes as source_refs/provenance when updating the writing workbench.")
    if not steps:
        steps.append("Append new clue nodes or edges after the next investigation pass.")
    return steps


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


def _compact_writing_document(document: dict[str, Any], *, include_body: bool, max_chars: int = 8000) -> dict[str, Any]:
    body = str(document.get("body_md") or "")
    compact = {
        "id": document.get("id"),
        "project_key": document.get("project_key"),
        "title": document.get("title"),
        "status": document.get("status"),
        "version": document.get("version"),
        "etag": document.get("etag"),
        "updated_at": document.get("updated_at"),
        "created_at": document.get("created_at"),
        "updated_by_user_id": document.get("updated_by_user_id"),
        "body_length": len(body),
        "block_anchors": _writing_block_anchors(body),
        "metadata_json": _compact_json_value(document.get("metadata_json"), max_items=8, max_depth=3),
    }
    if include_body:
        compact["body_md"] = body[:max_chars]
        compact["body_truncated"] = len(body) > max_chars
    return compact


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _writing_block_anchors(body_md: str, *, max_blocks: int = 80) -> list[dict[str, Any]]:
    lines = str(body_md or "").splitlines()
    blocks: list[dict[str, Any]] = []
    start_line: int | None = None
    buffer: list[str] = []

    def flush(end_line: int) -> None:
        nonlocal start_line, buffer
        text = "\n".join(buffer).strip()
        if not text or start_line is None:
            start_line = None
            buffer = []
            return
        first_line = buffer[0].strip()
        kind = "heading" if first_line.startswith("#") else "paragraph"
        heading_level = len(first_line) - len(first_line.lstrip("#")) if kind == "heading" else None
        blocks.append(
            {
                "block_id": f"block-{_stable_hash({'start': start_line, 'text': text})}",
                "kind": kind,
                "heading_level": heading_level,
                "line_start": start_line,
                "line_end": end_line,
                "preview": _first_nonempty_line(text),
                "content_hash": _stable_hash({"text": text}),
            }
        )
        start_line = None
        buffer = []

    for index, line in enumerate(lines, start=1):
        if line.strip():
            if start_line is None:
                start_line = index
            buffer.append(line)
            continue
        flush(index - 1)
        if len(blocks) >= max_blocks:
            return blocks[:max_blocks]
    flush(len(lines))
    return blocks[:max_blocks]


def _extract_writing_section(
    body_md: str,
    *,
    heading: str = "",
    block_id: str = "",
    line_start: int | None = None,
    line_end: int | None = None,
    max_chars: int = 5000,
) -> dict[str, Any]:
    lines = str(body_md or "").splitlines()
    anchors = _writing_block_anchors(body_md, max_blocks=500)
    selected_start = line_start if line_start and line_start > 0 else None
    selected_end = line_end if line_end and line_end > 0 else None
    if block_id:
        anchor = next((item for item in anchors if str(item.get("block_id") or "") == block_id), None)
        if anchor:
            selected_start = int(anchor.get("line_start") or 1)
            selected_end = int(anchor.get("line_end") or selected_start)
    if heading and selected_start is None:
        lowered = heading.lower()
        heading_anchor = next(
            (
                item
                for item in anchors
                if item.get("kind") == "heading" and lowered in str(item.get("preview") or "").lower()
            ),
            None,
        )
        if heading_anchor:
            selected_start = int(heading_anchor.get("line_start") or 1)
            selected_end = len(lines)
            heading_level = int(heading_anchor.get("heading_level") or 1)
            for candidate in anchors:
                candidate_start = int(candidate.get("line_start") or 0)
                candidate_level = int(candidate.get("heading_level") or 0)
                if candidate_start > selected_start and candidate.get("kind") == "heading" and candidate_level <= heading_level:
                    selected_end = max(selected_start, candidate_start - 1)
                    break
    if selected_start is None:
        selected_start = 1
    if selected_end is None:
        selected_end = min(len(lines), selected_start + 80)
    selected_start = max(1, min(selected_start, max(1, len(lines) or 1)))
    selected_end = max(selected_start, min(selected_end, max(1, len(lines) or 1)))
    text = "\n".join(lines[selected_start - 1 : selected_end])
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]
    return {
        "heading": heading or None,
        "block_id": block_id or None,
        "line_start": selected_start,
        "line_end": selected_end,
        "content_md": text,
        "content_truncated": truncated,
        "body_line_count": len(lines),
    }


def _first_nonempty_line(value: str, *, max_chars: int = 240) -> str:
    for line in str(value or "").splitlines():
        normalized = line.strip()
        if normalized:
            return normalized[:max_chars]
    return str(value or "").strip()[:max_chars]


def _find_anchor_line(body_md: str, content_md: str) -> int | None:
    body = str(body_md or "")
    content = str(content_md or "").strip()
    candidates = [content, _first_nonempty_line(content)]
    for candidate in candidates:
        if not candidate:
            continue
        offset = body.find(candidate)
        if offset >= 0:
            return body[:offset].count("\n") + 1
    return None


def _build_agent_writing_update(
    *,
    tool_call: CoreToolCall,
    current: dict[str, Any],
    new_body: str,
    operation: str,
    content_md: str,
    diff: dict[str, Any],
) -> dict[str, Any]:
    old_version = _safe_int(current.get("version"))
    old_body = str(current.get("body_md") or "")
    selection_snapshot = _normalize_selection_snapshot(tool_call.arguments.get("selection_snapshot"))
    selection_text = str(selection_snapshot.get("selected_text") or selection_snapshot.get("text") or "").strip()
    explicit_anchor_text = str(tool_call.arguments.get("anchor_text") or "").strip()
    anchor_text = selection_text or explicit_anchor_text or _first_nonempty_line(content_md)
    content_hash = _stable_hash({"content_md": content_md})
    idempotency_key = _agent_writing_idempotency_key(tool_call=tool_call, current=current, content_md=content_md, operation=operation)
    anchor_id = f"agent-{_stable_hash({'idempotency_key': idempotency_key, 'content_hash': content_hash})}"
    inserted_text = str(content_md or "").strip()
    replaced_text = _extract_replaced_writing_text(
        old_body,
        operation=operation,
        anchor_text=explicit_anchor_text or selection_text,
        range_start=_safe_nonnegative_int(tool_call.arguments.get("range_start")),
        range_end=_safe_nonnegative_int(tool_call.arguments.get("range_end")),
    )
    provenance = dict(tool_call.arguments.get("provenance") or {})
    if selection_snapshot:
        provenance.setdefault("selection_snapshot", selection_snapshot)
    return {
        "id": anchor_id,
        "anchor_id": anchor_id,
        "call_id": tool_call.call_id,
        "idempotency_key": idempotency_key,
        "tool_name": tool_call.tool_name,
        "actor": "agent_core",
        "operation": operation,
        "created_at": _utcnow_iso(),
        "doc_id": current.get("id"),
        "title": current.get("title"),
        "old_version": old_version,
        "new_version": 1 if current.get("id") is None else ((old_version + 1) if old_version else None),
        "content_hash": content_hash,
        "inserted_text": inserted_text[:2000],
        "inserted_text_truncated": len(inserted_text) > 2000,
        "replaced_text": replaced_text[:2000],
        "replaced_text_truncated": len(replaced_text) > 2000,
        "summary": f"{operation} via AgentCore: +{diff.get('added_lines')} -{diff.get('removed_lines')} lines",
        "diff": _compact_json_value(diff, max_items=8, max_depth=3, max_string=1200),
        "source_refs": _normalize_string_list(tool_call.arguments.get("source_refs")),
        "provenance": _compact_json_value(provenance, max_items=20, max_depth=4),
        "locator": {
            "anchor_id": anchor_id,
            "anchor_text": anchor_text,
            "anchor_heading": str(tool_call.arguments.get("anchor_heading") or "").strip() or None,
            "anchor_line": _find_anchor_line(new_body, content_md),
            "range_start": _safe_nonnegative_int(tool_call.arguments.get("range_start")),
            "range_end": _safe_nonnegative_int(tool_call.arguments.get("range_end")),
            "cursor_offset": _safe_nonnegative_int(tool_call.arguments.get("cursor_offset")),
            "selection_snapshot": selection_snapshot or None,
            "content_hash": content_hash,
        },
    }


def _agent_writing_idempotency_key(
    *,
    tool_call: CoreToolCall,
    current: dict[str, Any],
    content_md: str,
    operation: str,
) -> str:
    explicit = str(tool_call.arguments.get("idempotency_key") or "").strip()
    provenance = dict(tool_call.arguments.get("provenance") or {})
    explicit = explicit or str(provenance.get("idempotency_key") or "").strip()
    if explicit:
        return explicit[:240]
    selection_snapshot = _normalize_selection_snapshot(tool_call.arguments.get("selection_snapshot"))
    return _stable_hash(
        {
            "session_anchor": provenance.get("session_id") or provenance.get("message_id"),
            "doc_id": current.get("id") or tool_call.arguments.get("doc_id") or tool_call.arguments.get("title"),
            "operation": operation,
            "anchor_heading": str(tool_call.arguments.get("anchor_heading") or "").strip(),
            "anchor_text": str(tool_call.arguments.get("anchor_text") or "").strip(),
            "range_start": _safe_nonnegative_int(tool_call.arguments.get("range_start")),
            "range_end": _safe_nonnegative_int(tool_call.arguments.get("range_end")),
            "cursor_offset": _safe_nonnegative_int(tool_call.arguments.get("cursor_offset")),
            "selection": selection_snapshot,
            "content_hash": _stable_hash({"content_md": content_md}),
        }
    )


def _find_replayed_agent_writing_update(
    *,
    metadata: Any,
    tool_call: CoreToolCall,
    current: dict[str, Any],
    content_md: str,
    operation: str,
) -> dict[str, Any] | None:
    if not isinstance(metadata, dict):
        return None
    idempotency_key = _agent_writing_idempotency_key(tool_call=tool_call, current=current, content_md=content_md, operation=operation)
    for item in reversed([dict(entry) for entry in list(metadata.get("agent_updates") or []) if isinstance(entry, dict)]):
        if str(item.get("call_id") or "") == tool_call.call_id:
            return item
        if idempotency_key and str(item.get("idempotency_key") or "") == idempotency_key:
            return item
    return None


def _extract_replaced_writing_text(
    body_md: str,
    *,
    operation: str,
    anchor_text: str,
    range_start: int | None,
    range_end: int | None,
) -> str:
    body = str(body_md or "")
    normalized_operation = str(operation or "").strip()
    if normalized_operation == "replace_range" and range_start is not None and range_end is not None:
        if 0 <= range_start <= range_end <= len(body):
            return body[range_start:range_end]
        return ""
    if normalized_operation == "replace_text" and anchor_text:
        index = body.find(anchor_text)
        if index >= 0:
            return body[index : index + len(anchor_text)]
    return ""


def _append_agent_writing_update(metadata: Any, update: dict[str, Any], *, max_items: int = 30) -> dict[str, Any]:
    next_metadata = dict(metadata or {}) if isinstance(metadata, dict) else {}
    existing = [
        dict(item)
        for item in list(next_metadata.get("agent_updates") or [])
        if isinstance(item, dict)
    ]
    next_updates = [*existing, dict(update)][-max_items:]
    next_metadata["agent_updates"] = next_updates
    next_metadata["last_agent_update"] = dict(update)
    next_metadata["agent_update_count"] = len(next_updates)
    return next_metadata


def _apply_writing_body_operation(
    body_md: str,
    *,
    operation: str,
    content_md: str,
    anchor_heading: str,
    anchor_text: str,
    range_start: int | None = None,
    range_end: int | None = None,
    cursor_offset: int | None = None,
) -> str:
    operation = str(operation or "append").strip()
    content = str(content_md or "").strip()
    body = str(body_md or "")
    if operation == "append":
        return _join_markdown_blocks(body, content)
    if operation == "prepend":
        return _join_markdown_blocks(content, body)
    if operation == "after_heading":
        if not anchor_heading:
            raise ValueError("anchor_heading is required for after_heading")
        lines = body.splitlines()
        for index, line in enumerate(lines):
            if _heading_matches(line, anchor_heading):
                insert_at = index + 1
                while insert_at < len(lines) and not lines[insert_at].strip():
                    insert_at += 1
                updated = lines[:insert_at] + ["", content, ""] + lines[insert_at:]
                return "\n".join(updated).strip() + "\n"
        raise ValueError(f"anchor heading not found: {anchor_heading}")
    if operation == "replace_text":
        if not anchor_text:
            raise ValueError("anchor_text is required for replace_text")
        if anchor_text not in body:
            raise ValueError("anchor_text was not found in the document")
        return body.replace(anchor_text, content, 1)
    if operation == "replace_range":
        if range_start is None or range_end is None:
            raise ValueError("range_start and range_end are required for replace_range")
        _validate_body_range(body, range_start, range_end)
        return _splice_markdown_range(body, range_start, range_end, content)
    if operation == "insert_at_offset":
        if cursor_offset is None:
            raise ValueError("cursor_offset is required for insert_at_offset")
        _validate_body_range(body, cursor_offset, cursor_offset)
        return _splice_markdown_range(body, cursor_offset, cursor_offset, content)
    if operation == "insert_after_text":
        if not anchor_text:
            raise ValueError("anchor_text is required for insert_after_text")
        index = body.find(anchor_text)
        if index < 0:
            raise ValueError("anchor_text was not found in the document")
        insert_at = index + len(anchor_text)
        return _join_markdown_blocks(body[:insert_at], _join_markdown_blocks(content, body[insert_at:]))
    if operation == "insert_before_text":
        if not anchor_text:
            raise ValueError("anchor_text is required for insert_before_text")
        index = body.find(anchor_text)
        if index < 0:
            raise ValueError("anchor_text was not found in the document")
        return _join_markdown_blocks(_join_markdown_blocks(body[:index], content), body[index:])
    raise ValueError(f"unsupported writing operation: {operation}")


def _validate_body_range(body: str, start: int, end: int) -> None:
    if start < 0 or end < 0:
        raise ValueError("range offsets must be >= 0")
    if start > end:
        raise ValueError("range_start must be <= range_end")
    body_len = len(str(body or ""))
    if end > body_len:
        raise ValueError("range_end is outside the document")


def _splice_markdown_range(body: str, start: int, end: int, content: str) -> str:
    raw_body = str(body or "")
    inserted = str(content or "").strip()
    before = raw_body[:start]
    after = raw_body[end:]
    if not before:
        return _join_markdown_blocks(inserted, after)
    if not after:
        return _join_markdown_blocks(before, inserted)
    return _join_markdown_blocks(_join_markdown_blocks(before, inserted), after)


def _normalize_selection_snapshot(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, Any] = {}
    for key in ("text", "selected_text", "start", "end", "line", "active_heading", "before", "after"):
        if key not in value:
            continue
        item = value.get(key)
        if isinstance(item, str):
            item = item[:1400]
        out[key] = item
    return out


def _join_markdown_blocks(first: str, second: str) -> str:
    left = str(first or "").strip()
    right = str(second or "").strip()
    if not left:
        return f"{right}\n" if right else ""
    if not right:
        return f"{left}\n"
    return f"{left}\n\n{right}\n"


def _heading_matches(line: str, anchor_heading: str) -> bool:
    left = str(line or "").strip().lstrip("#").strip().lower()
    right = str(anchor_heading or "").strip().lstrip("#").strip().lower()
    return bool(left and right and left == right)


def _body_diff_summary(old_body: str, new_body: str) -> dict[str, Any]:
    old_lines = str(old_body or "").splitlines()
    new_lines = str(new_body or "").splitlines()
    diff_lines = list(difflib.unified_diff(old_lines, new_lines, fromfile="before.md", tofile="after.md", lineterm="", n=3))
    added = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))
    return {
        "added_lines": added,
        "removed_lines": removed,
        "old_line_count": len(old_lines),
        "new_line_count": len(new_lines),
        "diff_excerpt": "\n".join(diff_lines[:120]),
        "diff_truncated": len(diff_lines) > 120,
    }


def _spec_from_tool_definition(tool: dict[str, Any], *, source: str) -> CoreToolSpec:
    approval_level = str(tool.get("approval_level") or "none").strip()
    concurrency_class = str(tool.get("concurrency_class") or "read_only").strip()
    name = str(tool.get("name") or tool.get("tool_name") or tool.get("capability_id") or "").strip()
    return CoreToolSpec(
        name=name,
        title=str(tool.get("title") or tool.get("name") or name),
        description_for_model=str(tool.get("description") or name),
        input_schema=dict(tool.get("input_schema") or {"type": "object", "properties": {}}),
        output_schema=dict(tool.get("output_schema") or {"type": "object", "additionalProperties": True}),
        source=source,  # type: ignore[arg-type]
        risk=_risk_from_metadata(approval_level=approval_level, concurrency_class=concurrency_class, risks=list(tool.get("risks") or [])),
        permission=_permission_from_approval(approval_level),
        concurrency=_concurrency_from_class(concurrency_class),
        timeout_seconds=int(tool.get("timeout_seconds") or 10),
        result_budget=int(tool.get("result_budget") or 4000),
        project_service_id=str(tool.get("capability_id") or name),
        metadata={"legacy_tool_definition": dict(tool)},
    )


def _spec_from_capability(capability: dict[str, Any]) -> CoreToolSpec:
    capability_id = str(capability.get("capability_id") or "").strip()
    approval_level = str(capability.get("approval_level") or "none").strip()
    concurrency_class = str(capability.get("concurrency_class") or "read_only").strip()
    risks = list(capability.get("risks") or [])
    required = list(capability.get("required_input") or [])
    if capability_id == "ingest.source_library.run":
        input_schema = {
            "type": "object",
            "required": ["items", "project_key"],
            "properties": {
                "items": {
                    "type": "array",
                    "description": "Source-library item keys or item objects. Prefer an array of strings when the user gives item keys.",
                    "items": {
                        "oneOf": [
                            {"type": "string"},
                            {
                                "type": "object",
                                "properties": {
                                    "item_key": {"type": "string"},
                                    "handler_key": {"type": "string"},
                                    "override_params": {"type": "object", "additionalProperties": True},
                                },
                                "additionalProperties": True,
                            },
                        ]
                    },
                },
                "project_key": {"type": "string"},
                "override_params": {"type": "object", "additionalProperties": True},
                "max_items": {"type": "integer", "minimum": 1, "maximum": 100},
                "async_mode": {"type": "boolean", "description": "Prefer true for user-facing collection requests."},
            },
            "additionalProperties": True,
        }
    elif capability_id == "agent_batch.nl_command.submit":
        input_schema = {
            "type": "object",
            "required": ["command", "project_key"],
            "properties": {
                "command": {"type": "string"},
                "project_key": {"type": "string"},
                "idempotency_key": {"type": "string"},
                "dry_run": {"type": "boolean"},
                "enable_bounded_retry": {"type": "boolean"},
                "enable_limited_branching": {"type": "boolean"},
            },
            "additionalProperties": False,
        }
    elif capability_id == "workflow_graph.run":
        input_schema = {
            "type": "object",
            "required": ["graph_id", "inputs"],
            "properties": {
                "graph_id": {"type": "string"},
                "inputs": {"type": "object", "additionalProperties": True},
                "input": {"type": "object", "additionalProperties": True},
                "project_key": {"type": "string"},
            },
            "additionalProperties": False,
        }
    elif capability_id == "report.generate":
        input_schema = {
            "type": "object",
            "required": ["topic", "output_path"],
            "properties": {
                "topic": {"type": "string"},
                "output_path": {"type": "string"},
                "project_key": {"type": "string"},
                "sources": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "section_titles": {"type": "array", "items": {"type": "string"}},
            },
            "additionalProperties": False,
        }
    else:
        input_schema = {
            "type": "object",
            "required": required,
            "properties": {key: {"type": "string"} for key in required},
            "additionalProperties": True,
        }
    return CoreToolSpec(
        name=capability_id,
        title=str(capability.get("name") or capability_id),
        description_for_model=str(capability.get("description") or capability_id),
        input_schema=input_schema,
        source="legacy_adapter",
        risk=_risk_from_metadata(approval_level=approval_level, concurrency_class=concurrency_class, risks=risks),
        permission=_permission_from_approval(approval_level),
        concurrency=_concurrency_from_class(concurrency_class),
        project_service_id=capability_id,
        metadata={"legacy_capability": dict(capability)},
    )


def _handler_for_capability(
    capability_id: str,
    *,
    service: AgentSessionService,
) -> Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult] | None:
    if capability_id == "agent_batch.nl_command.submit":
        def agent_batch_nl_handler(
            tool_call: CoreToolCall,
            tool_spec: CoreToolSpec,
            request: AgentCoreRequest,
            emit: Callable[[CoreEvent], None],
        ) -> CoreToolResult:
            return _run_agent_batch_submit_tool(tool_call=tool_call, request=request, legacy_nl_only=True)

        return agent_batch_nl_handler

    if capability_id == "workflow_graph.run":
        def workflow_graph_run_handler(
            tool_call: CoreToolCall,
            tool_spec: CoreToolSpec,
            request: AgentCoreRequest,
            emit: Callable[[CoreEvent], None],
        ) -> CoreToolResult:
            project_key = _resolve_project_key(tool_call, request)
            graph_id = str(tool_call.arguments.get("graph_id") or "").strip()
            inputs = tool_call.arguments.get("inputs")
            if inputs is None:
                inputs = tool_call.arguments.get("input")
            if not project_key:
                return _missing_project_result(tool_call)
            if not graph_id:
                return CoreToolResult(
                    call_id=tool_call.call_id,
                    tool_name=tool_call.tool_name,
                    status="failed",
                    model_summary="graph_id is required for workflow_graph.run.",
                    error={"code": "missing_graph_id", "message": "graph_id is required"},
                )
            if not isinstance(inputs, dict):
                return CoreToolResult(
                    call_id=tool_call.call_id,
                    tool_name=tool_call.tool_name,
                    status="failed",
                    model_summary="inputs must be an object for workflow_graph.run.",
                    error={"code": "invalid_inputs", "message": "inputs must be an object"},
                )
            if _session_abort_requested(service=service, session_id=request.session_id):
                return _abort_requested_result(
                    service=service,
                    request=request,
                    tool_call=tool_call,
                    emit=emit,
                    skipped_items=[graph_id],
                    dispatched_count=0,
                )
            invoked = invoke_skill(
                skill_id="workflow_graph.run",
                payload={"graph_id": graph_id, "input": dict(inputs), "project_key": project_key},
                context={
                    "actor_role": "business_capability_wrapper",
                    "permissions": ["workflow_graph.run"],
                    "agent_session_id": request.session_id,
                    "agent_task_id": str((request.context or {}).get("root_task_id") or "").strip() or None,
                    "approval_granted": True,
                    "consumer": "agent_core.workflow_graph.run",
                    "trace_id": tool_call.call_id,
                },
            )
            result = invoked.get("result") if isinstance(invoked, dict) else invoked
            run_id = str((result or {}).get("run_id") or "").strip() if isinstance(result, dict) else ""
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="completed",
                model_summary=f"Started workflow graph run {run_id or graph_id}.",
                ui_summary=f"Started workflow graph: {graph_id}",
                structured_content={
                    "contract_version": "workflow_graph.run.agent_core.v1",
                    "project_key": project_key,
                    "graph_id": graph_id,
                    "result": _compact_json_value(result, max_items=30, max_depth=5),
                    "skill_meta": {
                        "owner": invoked.get("owner") if isinstance(invoked, dict) else None,
                        "execution_profile": invoked.get("execution_profile") if isinstance(invoked, dict) else None,
                    },
                },
            )

        return workflow_graph_run_handler

    if capability_id == "report.generate":
        def report_generate_handler(
            tool_call: CoreToolCall,
            tool_spec: CoreToolSpec,
            request: AgentCoreRequest,
            emit: Callable[[CoreEvent], None],
        ) -> CoreToolResult:
            project_key = _resolve_project_key(tool_call, request)
            topic = str(tool_call.arguments.get("topic") or request.message or "").strip()
            output_path = str(tool_call.arguments.get("output_path") or "").strip()
            if not topic:
                return CoreToolResult(
                    call_id=tool_call.call_id,
                    tool_name=tool_call.tool_name,
                    status="failed",
                    model_summary="topic is required for report.generate.",
                    error={"code": "missing_topic", "message": "topic is required"},
                )
            if not output_path:
                return CoreToolResult(
                    call_id=tool_call.call_id,
                    tool_name=tool_call.tool_name,
                    status="failed",
                    model_summary="output_path is required for report.generate.",
                    error={"code": "missing_output_path", "message": "output_path is required"},
                )
            if _session_abort_requested(service=service, session_id=request.session_id):
                return _abort_requested_result(
                    service=service,
                    request=request,
                    tool_call=tool_call,
                    emit=emit,
                    skipped_items=[output_path],
                    dispatched_count=0,
                )
            raw_sources = tool_call.arguments.get("sources")
            sources = [dict(item or {}) for item in list(raw_sources or []) if isinstance(item, dict)]
            if not sources:
                sources = [
                    {
                        "id": "S1",
                        "title": "Current agent session context",
                        "url": f"agent-session://{request.session_id}",
                        "publisher": "agent_session",
                        "evidence": request.message,
                    }
                ]
            section_titles = [str(item) for item in list(tool_call.arguments.get("section_titles") or []) if str(item or "").strip()]
            try:
                from app.services.llm_report_generator import build_structured_report, evaluate_report_gate, render_markdown

                report = build_structured_report(topic=topic[:200], sources=sources, section_titles=section_titles or None)
                markdown = render_markdown(report)
                gate = evaluate_report_gate(report)
                artifact = service.store.upsert_artifact(
                    {
                        "session_id": request.session_id,
                        "task_id": str((request.context or {}).get("root_task_id") or "").strip() or None,
                        "artifact_type": "report.generate.markdown",
                        "name": output_path,
                        "mime_type": "text/markdown",
                        "content_text": markdown,
                        "content_json": {"report": report.to_dict(), "quality_gate": gate},
                        "metadata": {
                            "turn_id": request.turn_id,
                            "capability_id": capability_id,
                            "project_key": project_key,
                            "output_path": output_path,
                            "agent_core_call_id": tool_call.call_id,
                        },
                    }
                )
            except Exception as exc:  # noqa: BLE001
                return CoreToolResult(
                    call_id=tool_call.call_id,
                    tool_name=tool_call.tool_name,
                    status="failed",
                    model_summary=f"report.generate failed: {exc}",
                    error={"code": exc.__class__.__name__, "message": str(exc)},
                )
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="completed",
                model_summary=f"Generated report draft artifact {output_path}.",
                ui_summary=f"Generated report: {output_path}",
                structured_content={
                    "contract_version": "report.generate.agent_core.v1",
                    "project_key": project_key,
                    "topic": topic[:200],
                    "output_path": output_path,
                    "artifact_id": artifact.get("artifact_id"),
                    "quality_gate": gate,
                    "artifact": _compact_json_value(artifact, max_items=16, max_depth=4),
                },
                artifact_refs=(str(artifact.get("artifact_id") or output_path),),
            )

        return report_generate_handler

    if capability_id != "ingest.source_library.run":
        return None

    def source_library_run_handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        project_key = str(tool_call.arguments.get("project_key") or request.project_key or "").strip()
        if not project_key:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary="project_key is required for source-library execution.",
                error={"code": "missing_project_key", "message": "project_key is required"},
            )

        override_params = dict(tool_call.arguments.get("override_params") or {})
        if tool_call.arguments.get("max_items") is not None:
            override_params.setdefault("max_items", tool_call.arguments.get("max_items"))

        item_keys = _normalize_source_library_items(tool_call.arguments)
        if not item_keys:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary="No source-library item_key was provided.",
                structured_content={"arguments": dict(tool_call.arguments or {})},
                error={"code": "missing_item_key", "message": "item_key is required"},
            )

        dispatches: list[dict[str, Any]] = []
        skipped_due_to_abort: list[str] = []
        for item_key in item_keys:
            if _session_abort_requested(service=service, session_id=request.session_id):
                skipped_due_to_abort.extend(item_keys[len(dispatches) :])
                emit(
                    CoreEvent(
                        event_type="tool_progress",
                        session_id=request.session_id,
                        turn_id=request.turn_id,
                        call_id=tool_call.call_id,
                        payload={
                            "contract_version": "agent_core.cooperative_abort.v1",
                            "tool_name": tool_call.tool_name,
                            "status": "abort_requested",
                            "dispatched_count": len(dispatches),
                            "skipped_items": list(skipped_due_to_abort),
                        },
                    )
                )
                break
            if bool(getattr(settings, "agent_core_e2e_scripted_provider_enabled", False)) and item_key.startswith("e2e."):
                scripted_task_suffix = item_key.removeprefix("e2e.").replace(".", "-").replace("_", "-")
                dispatches.append(
                    {
                        "item_key": item_key,
                        "task_id": f"e2e-task-{scripted_task_suffix or 'source'}",
                        "skill_id": "ingest.dispatch.source_library_item",
                    }
                )
                continue
            invoked = invoke_skill(
                skill_id="ingest.dispatch.source_library_item",
                payload={
                    "item_key": item_key,
                    "project_key": project_key,
                    "override_params": override_params,
                    "lane": "subagent",
                },
                context={
                    "actor_role": "business_capability_wrapper",
                    "permissions": ["ingest.dispatch.source_library_item"],
                    "agent_session_id": request.session_id,
                    "agent_task_id": str((request.context or {}).get("root_task_id") or "").strip() or None,
                    "approval_granted": True,
                    "consumer": "agent_core.ingest.source_library.run",
                    "trace_id": f"{tool_call.call_id}:{item_key}",
                },
            )
            result = invoked.get("result") if isinstance(invoked, dict) else {}
            dispatches.append(
                {
                    "item_key": item_key,
                    "task_id": str((result or {}).get("task_id") or "").strip() if isinstance(result, dict) else "",
                    "skill_id": "ingest.dispatch.source_library_item",
                }
            )
            if _session_abort_requested(service=service, session_id=request.session_id):
                remaining = item_keys[len(dispatches) :]
                skipped_due_to_abort.extend(remaining)
                emit(
                    CoreEvent(
                        event_type="tool_progress",
                        session_id=request.session_id,
                        turn_id=request.turn_id,
                        call_id=tool_call.call_id,
                        payload={
                            "contract_version": "agent_core.cooperative_abort.v1",
                            "tool_name": tool_call.tool_name,
                            "status": "abort_requested",
                            "dispatched_count": len(dispatches),
                            "skipped_items": list(skipped_due_to_abort),
                        },
                    )
                )
                break

        task_ids = [item["task_id"] for item in dispatches if item.get("task_id")]
        item_summary = ", ".join(item_keys)
        task_summary = ", ".join(task_ids) if task_ids else "none returned yet"
        dispatch_artifact = _record_source_library_dispatch_state(
            service=service,
            request=request,
            tool_call=tool_call,
            project_key=project_key,
            dispatches=dispatches,
            task_ids=task_ids,
            override_params=override_params,
            skipped_items=skipped_due_to_abort,
        )
        if skipped_due_to_abort:
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="canceled",
                model_summary=f"Source-library collection stopped after {len(dispatches)} dispatch(es) because the session was canceled.",
                ui_summary="Source-library collection stopped after session cancellation.",
                structured_content={
                    "project_key": project_key,
                    "items": dispatches,
                    "task_ids": task_ids,
                    "skipped_items": list(skipped_due_to_abort),
                    "abort_requested": True,
                    "override_params": override_params,
                    "dispatch_artifact_id": dispatch_artifact.get("artifact_id"),
                },
                artifact_refs=(str(dispatch_artifact.get("artifact_id") or "ingest.source_library_dispatches.json"),),
            )
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=(
                f"Queued source-library collection for {len(dispatches)} item(s): {item_summary}. "
                f"Project={project_key}. Dispatch task ids: {task_summary}. "
                "Next inspectable state: source-library ingest tasks/artifacts for these item keys."
            ),
            ui_summary=f"Queued source-library collection: {', '.join(item_keys)}",
            structured_content={
                "project_key": project_key,
                "items": dispatches,
                "task_ids": task_ids,
                "override_params": override_params,
                "dispatch_artifact_id": dispatch_artifact.get("artifact_id"),
                "next_read_tools": ["ingest.status.read", "agent_session.resume_bundle"],
            },
            artifact_refs=(str(dispatch_artifact.get("artifact_id") or "ingest.source_library_dispatches.json"),),
        )

    return source_library_run_handler


def _record_source_library_dispatch_state(
    *,
    service: AgentSessionService,
    request: AgentCoreRequest,
    tool_call: CoreToolCall,
    project_key: str,
    dispatches: list[dict[str, Any]],
    task_ids: list[str],
    override_params: dict[str, Any],
    skipped_items: list[str],
) -> dict[str, Any]:
    artifact_name = "ingest.source_library_dispatches.json"
    existing = next((item for item in service.list_artifacts(request.session_id) if item.get("name") == artifact_name), None)
    content = dict((existing or {}).get("content_json") or {})
    records = [dict(item) for item in list(content.get("dispatches") or []) if isinstance(item, dict)]
    record = {
        "call_id": tool_call.call_id,
        "turn_id": request.turn_id,
        "session_id": request.session_id,
        "project_key": project_key,
        "recorded_at": _utcnow_iso(),
        "items": list(dispatches),
        "task_ids": list(task_ids),
        "override_params": dict(override_params),
        "skipped_items": list(skipped_items),
        "status": "canceled" if skipped_items else "queued",
    }
    records = [item for item in records if item.get("call_id") != tool_call.call_id]
    records.append(record)
    updated = {
        "contract_version": "ingest.source_library.dispatch_state.v1",
        "session_id": request.session_id,
        "project_key": project_key,
        "dispatches": records[-50:],
        "latest": record,
    }
    artifact = service.store.upsert_artifact(
        {
            "session_id": request.session_id,
            "name": artifact_name,
            "artifact_type": "source_library_dispatch_state",
            "mime_type": "application/json",
            "content_text": json.dumps(updated, ensure_ascii=False, sort_keys=True, default=str),
            "content_json": updated,
            "metadata": {
                "project_key": project_key,
                "contract_version": "ingest.source_library.dispatch_state.v1",
                "agent_core_call_id": tool_call.call_id,
            },
        }
    )
    service.store.append_event(
        request.session_id,
        event_type="ingest.source_library.dispatch_recorded",
        payload={
            "contract_version": "ingest.source_library.dispatch_state.v1",
            "project_key": project_key,
            "call_id": tool_call.call_id,
            "task_ids": list(task_ids),
            "artifact_id": artifact.get("artifact_id"),
            "status": record["status"],
        },
    )
    return dict(artifact or {})


def _session_abort_requested(*, service: AgentSessionService, session_id: str) -> bool:
    try:
        session = service.get_session(session_id)
    except Exception:  # noqa: BLE001
        return False
    return str(session.get("status") or "").strip().lower() == "canceled"


def _abort_requested_result(
    *,
    service: AgentSessionService,
    request: AgentCoreRequest,
    tool_call: CoreToolCall,
    emit: Callable[[CoreEvent], None],
    skipped_items: list[str] | tuple[str, ...] = (),
    dispatched_count: int = 0,
    structured_content: dict[str, Any] | None = None,
) -> CoreToolResult:
    skipped = [str(item) for item in skipped_items if str(item).strip()]
    payload = {
        "contract_version": "agent_core.cooperative_abort.v1",
        "tool_name": tool_call.tool_name,
        "status": "abort_requested",
        "dispatched_count": int(dispatched_count),
        "skipped_items": skipped,
    }
    emit(
        CoreEvent(
            event_type="tool_progress",
            session_id=request.session_id,
            turn_id=request.turn_id,
            call_id=tool_call.call_id,
            payload=payload,
        )
    )
    content = {
        **(structured_content or {}),
        "abort_requested": True,
        "session_status": str((service.get_session(request.session_id) or {}).get("status") or ""),
        "skipped_items": skipped,
        "dispatched_count": int(dispatched_count),
    }
    return CoreToolResult(
        call_id=tool_call.call_id,
        tool_name=tool_call.tool_name,
        status="canceled",
        model_summary=f"Tool {tool_call.tool_name} did not continue because the session was canceled.",
        ui_summary=f"{tool_call.tool_name} stopped after session cancellation.",
        structured_content=content,
        error={"code": "session_canceled", "message": "session is canceled"},
        retry_hint="Use task.continue or task.retry after confirming the session should resume.",
    )


def _normalize_source_library_items(arguments: dict[str, Any]) -> list[str]:
    raw_items = arguments.get("items")
    candidates: list[Any]
    if isinstance(raw_items, list):
        candidates = list(raw_items)
    elif raw_items:
        candidates = [raw_items]
    else:
        candidates = [arguments.get("item_key")]

    out: list[str] = []
    for item in candidates:
        if isinstance(item, str):
            item_key = item.strip()
        elif isinstance(item, dict):
            item_key = str(item.get("item_key") or item.get("key") or "").strip()
        else:
            item_key = ""
        if item_key and item_key not in out:
            out.append(item_key)
    return out


def _run_agent_batch_submit_tool(
    *,
    tool_call: CoreToolCall,
    request: AgentCoreRequest,
    legacy_nl_only: bool,
) -> CoreToolResult:
    project_key = _resolve_project_key(tool_call, request)
    if not project_key:
        return _missing_project_result(tool_call)
    command = str(tool_call.arguments.get("command") or request.message or "").strip()
    idempotency_key = str(tool_call.arguments.get("idempotency_key") or "").strip() or None

    if command and (legacy_nl_only or not _agent_batch_structured_jobs(tool_call.arguments)):
        try:
            from app.api.agent_batch import _submit_jobs_from_loop_tasks
            from app.services.agent_batch.agent_loop import run_agent_batch_nl_command_loop
            from app.services.agent_batch.executor_health import inspect_executor_health
            from app.services.agent_batch.planner import plan_batch_search_command

            result = run_agent_batch_nl_command_loop(
                command=command,
                project_key=project_key,
                idempotency_key=idempotency_key
                or f"agent-core:{tool_call.call_id}:{_stable_hash({'command': command, 'project_key': project_key})}",
                dry_run=bool(tool_call.arguments.get("dry_run", False)),
                enable_bounded_retry=bool(tool_call.arguments.get("enable_bounded_retry", True)),
                enable_limited_branching=bool(tool_call.arguments.get("enable_limited_branching", True)),
                parser_fallback=plan_batch_search_command,
                submitter=_submit_jobs_from_loop_tasks,
                executor_snapshot=inspect_executor_health,
            )
        except Exception as exc:  # noqa: BLE001
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary=f"agent_batch command submit failed: {exc}",
                error={"code": exc.__class__.__name__, "message": str(exc)},
            )
        submit = dict(result.get("submit") or {}) if isinstance(result, dict) else {}
        job_id = str(submit.get("job_id") or "").strip()
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=f"Submitted agent_batch command{f' as job {job_id}' if job_id else ''}.",
            ui_summary="Submitted agent_batch command.",
            structured_content={
                "contract_version": "agent_batch.submit.v1",
                "mode": "nl_command",
                "project_key": project_key,
                "command": command,
                "job_id": job_id or None,
                "result": _compact_json_value(result, max_items=30, max_depth=5),
            },
        )

    if legacy_nl_only:
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="failed",
            model_summary="command is required for agent_batch.nl_command.submit.",
            error={"code": "missing_command", "message": "command is required"},
        )

    jobs = _agent_batch_structured_jobs(tool_call.arguments)
    if not jobs:
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="failed",
            model_summary="agent_batch.submit requires either command or jobs.",
            error={"code": "missing_agent_batch_work", "message": "command or jobs is required"},
        )

    try:
        from app.api.agent_batch import AgentBatchItemSubmit, AgentBatchSubmitBatch, AgentBatchSubmitRequest, submit_agent_batch_job

        payload = AgentBatchSubmitRequest(
            project_key=project_key,
            batch=AgentBatchSubmitBatch(jobs=[AgentBatchItemSubmit(**dict(item or {})) for item in jobs]),
            idempotency_key=idempotency_key,
            priority=tool_call.arguments.get("priority"),
            rule_set_id=tool_call.arguments.get("rule_set_id"),
            rule_set=dict(tool_call.arguments.get("rule_set") or {}),
        )
        response = submit_agent_batch_job(payload)
    except Exception as exc:  # noqa: BLE001
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="failed",
            model_summary=f"agent_batch structured submit failed: {exc}",
            error={"code": exc.__class__.__name__, "message": str(exc)},
        )

    data = dict(response.get("data") or {}) if isinstance(response, dict) else {}
    return CoreToolResult(
        call_id=tool_call.call_id,
        tool_name=tool_call.tool_name,
        status="completed",
        model_summary=f"Submitted {len(jobs)} agent_batch job item(s).",
        ui_summary=f"Submitted agent_batch job {data.get('job_id') or ''}".strip(),
        structured_content={
            "contract_version": "agent_batch.submit.v1",
            "mode": "structured_jobs",
            "project_key": project_key,
            "job_id": data.get("job_id"),
            "status": data.get("status"),
            "accepted_count": data.get("accepted_count"),
            "rejected_count": data.get("rejected_count"),
            "result": _compact_json_value(data, max_items=30, max_depth=5),
        },
    )


def _agent_batch_structured_jobs(arguments: dict[str, Any]) -> list[dict[str, Any]]:
    raw_jobs = arguments.get("jobs")
    if raw_jobs is None and isinstance(arguments.get("batch"), dict):
        raw_jobs = dict(arguments.get("batch") or {}).get("jobs")
    return [dict(item or {}) for item in list(raw_jobs or []) if isinstance(item, dict)]


def _compact_skill_meta(skill: dict[str, Any]) -> dict[str, Any]:
    manifest = dict(skill.get("agent_batch_task_manifest") or {})
    return {
        "skill_id": str(skill.get("skill_id") or "").strip(),
        "owner": skill.get("owner"),
        "execution_profile": skill.get("execution_profile") or "default",
        "concurrency_class": skill.get("concurrency_class") or "read_only",
        "required_permissions": list(skill.get("required_permissions") or []),
        "allowed_actor_roles": list(skill.get("allowed_actor_roles") or []),
        "approval_policy": dict(skill.get("approval_policy") or {}),
        "agent_batch_task_manifest": _compact_json_value(manifest, max_items=20, max_depth=4) if manifest else {},
    }


def _spec_from_skill(skill: dict[str, Any]) -> CoreToolSpec:
    skill_id = str(skill.get("skill_id") or "").strip()
    concurrency_class = str(skill.get("concurrency_class") or "read_only").strip()
    permissions = list(skill.get("required_permissions") or [])
    manifest = dict(skill.get("agent_batch_task_manifest") or {})
    manifest_description = str(manifest.get("description") or "").strip()
    description = (
        f"Invoke backend skill {skill_id}. "
        f"Owner: {skill.get('owner') or 'unknown'}. "
        f"Execution profile: {skill.get('execution_profile') or 'default'}. "
        f"Required permissions: {', '.join(str(item) for item in permissions) or 'none'}."
    )
    if manifest_description:
        description = f"{description} {manifest_description}"
    return CoreToolSpec(
        name=f"skill.{skill_id}",
        title=f"Skill: {skill_id}",
        description_for_model=description,
        input_schema={
            "type": "object",
            "properties": {
                "payload": {
                    "type": "object",
                    "description": "Skill payload. If omitted, the full argument object is passed as payload.",
                    "additionalProperties": True,
                }
            },
            "additionalProperties": True,
        },
        source="skill",
        risk=_risk_from_metadata(
            approval_level="explicit_user_request" if concurrency_class != "read_only" else "none",
            concurrency_class=concurrency_class,
            risks=[],
        ),
        permission="allow" if concurrency_class == "read_only" else "ask",
        concurrency=_concurrency_from_class(concurrency_class),
        skill_id=skill_id,
        project_service_id=skill_id,
        metadata={"required_permissions": permissions, "owner": skill.get("owner"), "execution_profile": skill.get("execution_profile")},
    )


def _mcp_catalog_tool_specs() -> list[tuple[CoreToolSpec, Callable[[CoreToolCall, CoreToolSpec, AgentCoreRequest, Callable[[CoreEvent], None]], CoreToolResult]]]:
    catalog_spec = CoreToolSpec(
        name="mcp.service.catalog",
        title="MCP Service Catalog",
        description_for_model=(
            "List MCP-suitable service surfaces for this project. "
            "This is a read-only catalog; executable MCP clients are exposed only after a concrete MCP server is configured."
        ),
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        source="mcp",
        risk="read_only",
        permission="allow",
        concurrency="parallel",
        mcp_server="project-internal-catalog",
        project_service_id="mcp.service.catalog",
    )
    list_spec = CoreToolSpec(
        name="mcp.tools.list",
        title="List MCP Tools",
        description_for_model=(
            "List executable MCP-compatible tools currently mounted for AgentCore. "
            "This returns concrete callable tools and clearly marks tools/services that are not configured."
        ),
        input_schema={
            "type": "object",
            "properties": {"service_id": {"type": "string"}},
            "additionalProperties": False,
        },
        source="mcp",
        risk="read_only",
        permission="allow",
        concurrency="parallel",
        mcp_server="project-internal-catalog",
        project_service_id="mcp.tools.list",
        metadata={"contract_version": "mcp.tools.list.v1", "implemented": True},
    )
    call_spec = CoreToolSpec(
        name="mcp.tool.call",
        title="Call MCP Tool",
        description_for_model=(
            "Call one mounted MCP-compatible tool by name. "
            "Unknown or unconfigured MCP tools return an explicit not_configured error instead of pretending to run."
        ),
        input_schema={
            "type": "object",
            "required": ["tool_name"],
            "properties": {
                "service_id": {"type": "string"},
                "tool_name": {"type": "string"},
                "arguments": {"type": "object", "additionalProperties": True},
            },
            "additionalProperties": False,
        },
        source="mcp",
        risk="read_only",
        permission="allow",
        concurrency="parallel",
        mcp_server="project-internal-catalog",
        project_service_id="mcp.tool.call",
        metadata={"contract_version": "mcp.tool.call.v1", "implemented": True},
    )

    def catalog_handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        services = _mcp_catalog_services()
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary="listed MCP service catalog",
            structured_content={
                "contract_version": "mcp.service.catalog.v1",
                "services": services,
                "status_matrix": services,
                "project_key": request.project_key,
            },
        )

    def list_handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        service_id = str(tool_call.arguments.get("service_id") or "").strip()
        tools = _mcp_tool_catalog_entries()
        if service_id:
            tools = [item for item in tools if str(item.get("service_id") or "") == service_id]
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary=f"Listed {len(tools)} MCP-compatible tool(s).",
            structured_content={
                "contract_version": "mcp.tools.list.v1",
                "service_id": service_id or None,
                "tools": tools,
                "services": _mcp_catalog_services(),
            },
        )

    def call_handler(
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        service_id = str(tool_call.arguments.get("service_id") or "project-internal-catalog").strip() or "project-internal-catalog"
        target_name = str(tool_call.arguments.get("tool_name") or "").strip()
        target_arguments = dict(tool_call.arguments.get("arguments") or {})
        if target_name == "mcp.service.catalog":
            catalog = catalog_handler(
                CoreToolCall(tool_name="mcp.service.catalog", arguments=target_arguments, call_id=tool_call.call_id),
                catalog_spec,
                request,
                emit,
            )
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status=catalog.status,
                model_summary="Called MCP tool mcp.service.catalog.",
                structured_content={
                    "contract_version": "mcp.tool.call.v1",
                    "service_id": service_id,
                    "called_tool": target_name,
                    "result": catalog.structured_content,
                },
                error=catalog.error,
            )
        if target_name == "mcp.tools.list":
            listed = list_handler(
                CoreToolCall(tool_name="mcp.tools.list", arguments=target_arguments, call_id=tool_call.call_id),
                list_spec,
                request,
                emit,
            )
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status=listed.status,
                model_summary="Called MCP tool mcp.tools.list.",
                structured_content={
                    "contract_version": "mcp.tool.call.v1",
                    "service_id": service_id,
                    "called_tool": target_name,
                    "result": listed.structured_content,
                },
                error=listed.error,
            )
        mounted = _MOUNTED_MCP_TOOLS.get(target_name)
        if mounted is not None:
            entry, mounted_handler = mounted
            expected_service_id = str(entry.get("service_id") or "").strip()
            if service_id and expected_service_id and service_id != expected_service_id:
                return CoreToolResult(
                    call_id=tool_call.call_id,
                    tool_name=tool_call.tool_name,
                    status="failed",
                    model_summary=f"MCP tool {target_name} is mounted on {expected_service_id}, not {service_id}.",
                    structured_content={
                        "contract_version": "mcp.tool.call.v1",
                        "service_id": service_id,
                        "called_tool": target_name,
                        "available_tools": _mcp_tool_catalog_entries(),
                        "service_status": get_external_service_status(service_id),
                    },
                    error={
                        "code": "mcp_tool_service_mismatch",
                        "message": f"MCP tool {target_name} is mounted on {expected_service_id}, not {service_id}.",
                    },
                )
            try:
                result = mounted_handler(dict(target_arguments or {}), request)
            except Exception as exc:  # noqa: BLE001
                return CoreToolResult(
                    call_id=tool_call.call_id,
                    tool_name=tool_call.tool_name,
                    status="failed",
                    model_summary=f"MCP tool {target_name} failed: {exc}",
                    structured_content={
                        "contract_version": "mcp.tool.call.v1",
                        "service_id": expected_service_id or service_id,
                        "called_tool": target_name,
                        "arguments": _compact_json_value(target_arguments, max_items=20, max_depth=4),
                        "service_status": get_external_service_status(expected_service_id or service_id),
                    },
                    error={"code": "mcp_tool_failed", "message": str(exc), "tool_name": target_name},
                )
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="completed",
                model_summary=f"Called mounted MCP tool {target_name}.",
                structured_content={
                    "contract_version": "mcp.tool.call.v1",
                    "service_id": expected_service_id or service_id,
                    "called_tool": target_name,
                    "success": True,
                    "result": _compact_json_value(result, max_items=50, max_depth=6),
                },
            )
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="failed",
            model_summary=f"MCP tool is not configured: {target_name or '(empty)'}",
            structured_content={
                "contract_version": "mcp.tool.call.v1",
                "service_id": service_id,
                "called_tool": target_name,
                "available_tools": _mcp_tool_catalog_entries(),
                "service_status": get_external_service_status(service_id),
            },
            error={"code": "mcp_tool_not_configured", "message": f"MCP tool is not configured: {target_name or '(empty)'}"},
        )

    return [(catalog_spec, catalog_handler), (list_spec, list_handler), (call_spec, call_handler)]


def _mcp_catalog_services() -> list[dict[str, Any]]:
    return list_external_service_statuses()


def _mcp_tool_catalog_entries() -> list[dict[str, Any]]:
    return [
        {
            "service_id": "project-internal-catalog",
            "tool_name": "mcp.service.catalog",
            "status": "available",
            "description": "List MCP-suitable project service surfaces.",
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "service_id": "project-internal-catalog",
            "tool_name": "mcp.tools.list",
            "status": "available",
            "description": "List currently mounted MCP-compatible tools.",
            "input_schema": {
                "type": "object",
                "properties": {"service_id": {"type": "string"}},
                "additionalProperties": False,
            },
        },
    ] + _mcp_unmounted_tool_entries() + [dict(item[0]) for item in sorted(_MOUNTED_MCP_TOOLS.values(), key=lambda entry: str(entry[0].get("tool_name") or ""))]


def _mcp_unmounted_tool_entries() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for service in list_external_service_statuses():
        if str(service.get("fit") or "") != "external_mcp":
            continue
        if service.get("enabled"):
            continue
        service_id = str(service.get("service_id") or "").strip()
        entries.append(
            {
                "service_id": service_id,
                "tool_name": f"{service_id}.placeholder",
                "status": service.get("status"),
                "implementation_state": service.get("implementation_state"),
                "description": service.get("reason"),
                "input_schema": {"type": "object", "properties": {}, "additionalProperties": True},
                "mounted": False,
                "configured": service.get("configured"),
                "reachable": service.get("reachable"),
                "auth_ok": service.get("auth_ok"),
                "server_error": service.get("server_error"),
            }
        )
    return entries


def _core_result_from_capability_call(tool_call: CoreToolCall, old_call: dict[str, Any]) -> CoreToolResult:
    status = _core_status(str(old_call.get("status") or old_call.get("stream_state") or "completed"))
    summary = str(old_call.get("summary") or old_call.get("status") or status)
    error = old_call.get("error") if isinstance(old_call.get("error"), dict) else None
    legacy_result = old_call.get("result") if isinstance(old_call.get("result"), dict) else {}
    return CoreToolResult(
        call_id=tool_call.call_id,
        tool_name=tool_call.tool_name,
        status=status,
        model_summary=summary,
        ui_summary=summary,
        structured_content={"result": _compact_result_for_core(tool_call.tool_name, dict(legacy_result or {}))},
        error=error,
    )


def _compact_result_for_core(tool_name: str, result: dict[str, Any]) -> dict[str, Any]:
    """Keep tool results useful for the model/UI without replaying legacy envelopes."""

    name = str(tool_name or "").strip()
    payload = dict(result or {})
    if name == "project.summary.read":
        session = dict(payload.get("session") or {})
        return {
            "project_key": payload.get("project_key"),
            "session": _compact_session(session),
            "session_counts": dict(payload.get("session_counts") or {}),
            "source_library": _compact_json_value(payload.get("source_library"), max_items=10, max_depth=4),
        }
    if name == "project.structured_data.search":
        return {
            "project_key": payload.get("project_key"),
            "query": payload.get("query"),
            "query_mode": payload.get("query_mode"),
            "model_evidence_manifest": _compact_json_value(payload.get("model_evidence_manifest"), max_items=16, max_depth=4),
            "items": _compact_json_value(payload.get("items"), max_items=12, max_depth=4),
            "inventory": _compact_json_value(payload.get("inventory"), max_items=20, max_depth=3),
            "dataset_counts": dict(payload.get("dataset_counts") or {}),
            "dataset_total_rows": dict(payload.get("dataset_total_rows") or {}),
            "total_stored_rows": payload.get("total_stored_rows"),
            "total_matches": payload.get("total_matches"),
            "fallback_used": payload.get("fallback_used"),
            "errors": _compact_json_value(payload.get("errors"), max_items=8, max_depth=3),
        }
    if name in {"project.structured_data.item.read", "project.context.resource.read"}:
        return {
            "project_key": payload.get("project_key"),
            "dataset": payload.get("dataset"),
            "record_id": payload.get("record_id"),
            "resource_uri": payload.get("resource_uri"),
            "item": _compact_json_value(payload.get("item"), max_items=18, max_depth=5),
            "model_evidence_manifest": _compact_json_value(payload.get("model_evidence_manifest"), max_items=12, max_depth=4),
            "cleaned_text": _compact_json_value(payload.get("cleaned_text"), max_items=6, max_depth=2),
            "source_ref": payload.get("source_ref"),
            "quality_flags": _compact_json_value(payload.get("quality_flags"), max_items=8, max_depth=3),
            "errors": _compact_json_value(payload.get("errors"), max_items=8, max_depth=3),
        }
    if name == "project.structured_data.items.read":
        return {
            "project_key": payload.get("project_key"),
            "items": _compact_json_value(payload.get("items"), max_items=8, max_depth=5),
            "model_evidence_manifest": _compact_json_value(payload.get("model_evidence_manifest"), max_items=12, max_depth=4),
            "total_returned": payload.get("total_returned"),
            "errors": _compact_json_value(payload.get("errors"), max_items=8, max_depth=3),
        }
    if name == "project.context.bundle":
        return {
            "project_key": payload.get("project_key"),
            "query": payload.get("query"),
            "material_intent": _compact_json_value(payload.get("material_intent"), max_items=8, max_depth=4),
            "material_categories": _compact_json_value(payload.get("material_categories"), max_items=8, max_depth=4),
            "model_evidence_manifest": _compact_json_value(payload.get("model_evidence_manifest"), max_items=18, max_depth=4),
            "evidence": _compact_json_value(payload.get("evidence"), max_items=18, max_depth=4),
            "missing_evidence": _compact_json_value(payload.get("missing_evidence"), max_items=8, max_depth=3),
            "source_catalog_note": payload.get("source_catalog_note"),
            "components": {
                "structured_data": _compact_json_value(dict(dict(payload.get("components") or {}).get("structured_data") or {}), max_items=12, max_depth=4),
                "writing_documents": _compact_json_value(dict(dict(payload.get("components") or {}).get("writing_documents") or {}), max_items=8, max_depth=4),
                "artifacts": _compact_json_value(dict(dict(payload.get("components") or {}).get("artifacts") or {}), max_items=8, max_depth=4),
                "source_catalog": _compact_json_value(dict(dict(payload.get("components") or {}).get("source_catalog") or {}), max_items=8, max_depth=4),
            },
        }
    if name == "writing.document.section.read":
        return {
            "project_key": payload.get("project_key"),
            "document": _compact_json_value(payload.get("document"), max_items=12, max_depth=4),
            "section": _compact_json_value(payload.get("section"), max_items=12, max_depth=4),
        }
    if name == "agent_session.context.read":
        return {
            "session": _compact_session(dict(payload.get("session") or {})),
            "task_count": payload.get("task_count"),
            "event_count": payload.get("event_count"),
            "artifact_count": payload.get("artifact_count"),
            "approval_count": payload.get("approval_count"),
            "recent_tasks": _compact_json_value(payload.get("recent_tasks"), max_items=8, max_depth=4),
            "recent_messages": _compact_json_value(payload.get("recent_messages"), max_items=6, max_depth=4),
            "recent_tool_results": _compact_json_value(payload.get("recent_tool_results"), max_items=8, max_depth=4),
        }
    if name in {"source_library.item.list", "source_library.item.search"}:
        return {
            "project_key": payload.get("project_key"),
            "query": payload.get("query"),
            "total": payload.get("total"),
            "source_total": payload.get("source_total"),
            "items": _compact_json_value(payload.get("items"), max_items=12, max_depth=3),
        }
    if name == "ingest.status.read":
        return {
            "session_id": payload.get("session_id"),
            "job_status_counts": dict(payload.get("job_status_counts") or {}),
            "recent_jobs": [_compact_job(dict(item or {})) for item in list(payload.get("recent_jobs") or [])[:8]],
            "recent_session_tasks": _compact_json_value(payload.get("recent_session_tasks"), max_items=5, max_depth=3),
        }
    return _compact_json_value(payload, max_items=20, max_depth=4)


def _compact_session(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": session.get("session_id"),
        "project_key": session.get("project_key"),
        "entrypoint_type": session.get("entrypoint_type"),
        "goal": session.get("goal"),
        "status": session.get("status"),
        "current_phase": session.get("current_phase"),
        "root_task_id": session.get("root_task_id"),
        "task_count": session.get("task_count"),
    }


def _compact_job(job: dict[str, Any]) -> dict[str, Any]:
    params = dict(job.get("params") or {})
    display_meta = dict(params.get("display_meta") or {})
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


def _compact_json_value(value: Any, *, max_items: int = 30, max_depth: int = 5, max_string: int = 500) -> Any:
    if max_depth <= 0:
        if isinstance(value, (dict, list, tuple)):
            return "[truncated]"
        return value
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= max_items:
                out["_truncated"] = True
                out["_omitted_count"] = max(0, len(value) - max_items)
                break
            out[str(key)] = _compact_json_value(item, max_items=max_items, max_depth=max_depth - 1, max_string=max_string)
        return out
    if isinstance(value, (list, tuple)):
        items = list(value)
        out = [_compact_json_value(item, max_items=max_items, max_depth=max_depth - 1, max_string=max_string) for item in items[:max_items]]
        if len(items) > max_items:
            out.append({"_truncated": True, "_omitted_count": len(items) - max_items})
        return out
    if isinstance(value, str) and len(value) > max_string:
        return f"{value[:max_string]}..."
    return value


def _core_status(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in {"completed", "success", "ok", "delegated"}:
        return "completed"
    if normalized in {"canceled", "cancelled"}:
        return "canceled"
    if normalized in {"needs_approval", "approval_waiting"}:
        return "needs_approval"
    if normalized in {"skipped", "deferred"}:
        return "deferred"
    return "failed"


def _permission_from_approval(approval_level: str) -> str:
    value = str(approval_level or "none").strip().lower()
    if value == "none":
        return "allow"
    if value == "explicit_user_request":
        return "explicit_user_request"
    return "ask"


def _risk_from_metadata(*, approval_level: str, concurrency_class: str, risks: list[Any]) -> str:
    approval = str(approval_level or "none").strip().lower()
    concurrency = str(concurrency_class or "read_only").strip().lower()
    risk_text = " ".join(str(item or "").lower() for item in risks)
    if approval == "none" and concurrency == "read_only":
        return "read_only"
    if "privileged" in risk_text:
        return "privileged"
    if concurrency == "write_external" or "external" in risk_text or "network" in risk_text:
        return "write_external"
    return "write_shared"


def _concurrency_from_class(concurrency_class: str) -> str:
    value = str(concurrency_class or "read_only").strip().lower()
    if value == "read_only":
        return "parallel"
    if value == "write_shared":
        return "serial"
    return "exclusive"
