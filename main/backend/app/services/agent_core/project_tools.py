from __future__ import annotations

from collections.abc import Callable, Mapping
import json
from typing import Annotated, Any

from functorial_kit import Failure

from app.services.agent_runtime.capability_registry import list_interactive_agent_capabilities
from app.services.agent_runtime.control_tools import AgentControlToolRuntime
from app.services.agent_runtime.external_tool_status import (
    clear_mounted_mcp_tools,
    get_external_service_status,
    list_external_service_statuses,
    mark_mcp_tool_mounted,
)
from app.services.agent_runtime.read_only_tools import ReadOnlyAgentToolRuntime
from app.services.agent_sessions.service import AgentSessionService
from app.services.skill_runtime import invoke_skill, list_registered_skills

from .contracts import AgentCoreRequest, CoreEvent, CoreToolCall, CoreToolResult, CoreToolSpec
from .macro_tools import (
    facility_tool_projection,
    information_topology_read_facility,
    macro_registration_package_activate_facility,
    macro_registration_package_create_facility,
    macro_registration_package_readback_facility,
    project_retrieval_current_facility,
    rapid_proposal_readback_facility,
    rapid_proposal_save_facility,
)
from .authoring_tools import (
    AuthoringToolContext,
    authoring_capability_sources,
    authoring_ingest_writing_batch_sources,
    authoring_task_session_sources,
)
from .query_tools import query_project_tool_sources
from .registry import CoreToolRegistry
from .tool_contribution import register_project_tool_contributions
from .tool_support import (
    _abort_requested_result,
    _compact_json_value,
    _compact_session,
    _concurrency_from_class,
    _permission_from_approval,
    _risk_from_metadata,
    _session_abort_requested,
    _utcnow_iso,
)


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
        # kit:boundary owner=project_tools.py class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w02_programmer_defect_boundary
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
) -> Annotated[
    CoreToolRegistry,
    "kit:non-authoritative derived_as=view fact_source=project_core_tool_specs "
    "witness=test:test_w02_agent_authority_metadata"
]:
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
    _register_agent_macro_facilities(registry, service)

    registered = {tool.name for tool in registry.list_specs()}
    for capability in list_interactive_agent_capabilities():
        capability_id = str(capability.get("capability_id") or "").strip()
        if not capability_id or capability_id in registered or capability_id == "agent_session.stream":
            continue
        authored_sources = authoring_capability_sources(service, (capability,))
        if authored_sources:
            contribution_failure = register_project_tool_contributions(
                registry, authored_sources
            )
            if isinstance(contribution_failure, Failure):
                # kit:boundary owner=project_tools.py class=PROGRAMMER_DEFECT failure_family=none witness=test:test_authoring_capability_sources_preserve_original_loop_semantics
                raise ValueError(
                    "project tool capability contribution is invalid: "
                    f"{contribution_failure.message}: "
                    f"{dict(contribution_failure.context or {})}"
                )
            registered.add(capability_id)
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


def _register_agent_macro_facilities(registry: CoreToolRegistry, session_service: AgentSessionService) -> None:
    """Project the authored M4 facilities into the one shared Core registry."""

    from app.services.project_retrieval.proposals import RapidProposalTopologyAdapter
    from app.services.project_retrieval.service import ProjectRetrievalService
    from app.services.project_retrieval.topology import build_topology_service

    retrieval_service = ProjectRetrievalService()
    topology_service = build_topology_service()
    proposal_adapter = RapidProposalTopologyAdapter(topology_service)
    bindings = (
        project_retrieval_current_facility(retrieval_service),
        information_topology_read_facility(topology_service),
        rapid_proposal_save_facility(
            proposal_adapter, retrieval_service.domain_vocabulary
        ),
        rapid_proposal_readback_facility(proposal_adapter),
        macro_registration_package_create_facility(session_service),
        macro_registration_package_readback_facility(session_service),
        macro_registration_package_activate_facility(session_service),
    )
    for binding in bindings:
        spec, handler = facility_tool_projection(binding)
        registry.register(spec, handler)


def _register_deepening_tools(
    *,
    registry: CoreToolRegistry,
    service: AgentSessionService,
    source_library_lister: SourceLibraryLister | None = None,
    structured_data_searcher: StructuredDataSearcher | None = None,
) -> None:
    """Compile the authored project-tool catalogs in their original order."""

    context = AuthoringToolContext(
        service=service,
        structured_data_searcher=structured_data_searcher,
    )
    query_sources = query_project_tool_sources(
        service=service,
        source_library_lister=source_library_lister,
        structured_data_searcher=structured_data_searcher,
    )
    sources = (
        *authoring_task_session_sources(context),
        *query_sources[:6],
        *authoring_ingest_writing_batch_sources(context),
        *query_sources[6:],
    )
    contribution_failure = register_project_tool_contributions(registry, sources)
    if isinstance(contribution_failure, Failure):
        # kit:boundary owner=project_tools.py class=PROGRAMMER_DEFECT failure_family=none witness=test:test_project_tool_catalog_rejects_invalid_group_before_registration
        raise ValueError(
            "project tool contribution catalog is invalid: "
            f"{contribution_failure.message}: {dict(contribution_failure.context or {})}"
        )


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
        risk=_risk_from_metadata(
            approval_level=approval_level,
            concurrency_class=concurrency_class,
            risks=risks,
        ),
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
    declared_input_schema = skill.get("input_schema")
    input_schema = (
        dict(declared_input_schema)
        if isinstance(declared_input_schema, Mapping) and declared_input_schema
        else {
            "type": "object",
            "properties": {
                "payload": {
                    "type": "object",
                    "description": "Skill payload. If omitted, the full argument object is passed as payload.",
                    "additionalProperties": True,
                }
            },
            "additionalProperties": True,
        }
    )
    return CoreToolSpec(
        name=f"skill.{skill_id}",
        title=f"Skill: {skill_id}",
        description_for_model=description,
        input_schema=input_schema,
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
