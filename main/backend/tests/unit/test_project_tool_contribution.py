from __future__ import annotations

import socket
from dataclasses import replace
from unittest.mock import patch

import pytest
from functorial_kit import Failure

from app.services.agent_core.contracts import (
    AgentCoreRequest,
    CoreToolCall,
    CoreToolResult,
    CoreToolSpec,
)
from app.services.agent_core.registry import CoreToolRegistry
from app.services.agent_core.tool_contribution import (
    ProjectToolAuthorSource,
    bind_project_tool_operation,
    compile_project_tool_native,
    register_project_tool_contributions,
)
from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_sessions.store import InMemoryAgentSessionStore
from app.services.llm.codex_macro_binding import build_agent_macro_rapid_binding


def _spec(name: str) -> CoreToolSpec:
    return CoreToolSpec(
        name=name,
        title=name,
        description_for_model=f"Run {name}.",
        input_schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "additionalProperties": False,
        },
        source="project",
        risk="read_only",
        permission="allow",
        concurrency="parallel",
        project_service_id=name,
    )


def _source(name: str, handler) -> ProjectToolAuthorSource:
    return ProjectToolAuthorSource(
        binding_id=f"facility.{name}",
        version="1",
        tool_spec=_spec(name),
        handler=handler,
        executor_ref=name,
        scope_source="AgentCoreRequest.project_key",
        permission_source="CoreToolSpec.permission",
        failure_family="CoreToolResult.status/error",
        readback_semantics="test observation",
    )


def test_project_tool_rule_registers_without_executing_handler() -> None:
    calls: list[str] = []

    def handler(tool_call, _tool_spec, _request, _emit):
        calls.append(str(tool_call.arguments.get("value") or ""))
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary="observed",
            structured_content={"value": calls[-1]},
        )

    source = _source("example.observe", handler)
    native = compile_project_tool_native(source)
    assert not isinstance(native, Failure)
    assert native.definition.tool_spec is source.tool_spec
    assert native.projection.id == "facility.example.observe@1"
    assert calls == []

    registry = CoreToolRegistry()
    assert register_project_tool_contributions(registry, (source,)) is None
    assert calls == []
    spec = registry.get("example.observe")
    assert spec is source.tool_spec

    result = registry.execute_tool(
        tool_call=CoreToolCall(
            tool_name="example.observe",
            arguments={"value": "actual invocation"},
            call_id="call-1",
        ),
        tool_spec=spec,
        request=AgentCoreRequest(
            message="observe",
            session_id="session-1",
            project_key="demo_proj",
        ),
        emit=lambda _event: None,
    )
    assert calls == ["actual invocation"]
    assert result.structured_content == {"value": "actual invocation"}


def test_task_summary_direct_reads_owner_through_real_registry() -> None:
    from app.services.agent_core.project_tools import build_project_core_tool_registry

    service = AgentSessionService(store=InMemoryAgentSessionStore())
    bundle = service.create_session(source="user", entrypoint_type="interactive_agent", goal="summary")
    session_id = bundle["session"]["session_id"]
    request = AgentCoreRequest(message="read summary", session_id="other-session")
    call = CoreToolCall(tool_name="task.summary", arguments={"session_id": session_id}, call_id="summary-call")
    with (
        patch("app.services.agent_core.project_tools.list_registered_skills", return_value=[]),
        patch.object(service, "get_session_summary", wraps=service.get_session_summary) as owner,
    ):
        registry = build_project_core_tool_registry(service=service)
        owner.assert_not_called()
        result = registry.execute_tool(tool_call=call, request=request, emit=lambda _event: None)
    owner.assert_called_once_with(session_id)
    assert result.call_id == "summary-call"
    assert result.status == "completed"
    assert result.structured_content["result"]["session_id"] == session_id
    assert result.structured_content["result"]["summary"]["session_id"] == session_id


def test_source_library_run_is_project_tool_author_source() -> None:
    from unittest.mock import Mock

    from app.services.agent_core.project_tools import build_project_core_tool_registry

    with patch(
        "app.services.agent_core.project_tools.list_registered_skills",
        return_value=[],
    ):
        registry = build_project_core_tool_registry(service=Mock())
    spec = registry.get("ingest.source_library.run")
    assert spec is not None
    assert spec.source == "project"
    assert spec.permission == "ask"
    assert spec.risk == "write_external"
    capability = spec.metadata["capability"]
    assert capability["capability_id"] == "ingest.source_library.run"
    assert "legacy_capability" not in spec.metadata

    assert spec.concurrency == "exclusive"
    assert "uses_existing_frontdoor" not in spec.metadata


def test_project_tool_operation_rule_preserves_identity_exception_and_permission() -> None:
    call = CoreToolCall(tool_name="example.observe", call_id="operation-call")
    request = AgentCoreRequest(message="observe", session_id="operation-session")
    expected = CoreToolResult(call_id=call.call_id, tool_name=call.tool_name, status="completed", model_summary="observed")
    invocations = []

    def operation(actual_call, actual_request):
        assert actual_call is call
        assert actual_request is request
        invocations.append(actual_call)
        return expected

    handler = bind_project_tool_operation(operation)
    assert handler(call, _spec(call.tool_name), request, lambda _event: None) is expected
    assert invocations == [call]

    error = ValueError("original operation failure")

    def failing_operation(_call, _request):
        raise error

    with pytest.raises(ValueError) as caught:
        bind_project_tool_operation(failing_operation)(call, _spec(call.tool_name), request, lambda _event: None)
    assert caught.value is error

    registry = CoreToolRegistry()
    denied_source = replace(_source(call.tool_name, handler), tool_spec=replace(_spec(call.tool_name), permission="ask"))
    assert register_project_tool_contributions(registry, (denied_source,)) is None
    denied = registry.execute_tool(tool_call=call, request=request, emit=lambda _event: None)
    assert denied.status == "needs_approval"
    assert invocations == [call]


def test_project_read_control_catalog_preserves_original_tools() -> None:
    from app.services.agent_runtime.control_tools import control_project_tool_sources
    from app.services.agent_runtime.read_only_tools import read_only_project_tool_sources

    service = AgentSessionService(store=InMemoryAgentSessionStore())
    with (
        patch.object(service, "get_session", side_effect=AssertionError("construction read session")),
        patch.object(service, "get_session_bundle", side_effect=AssertionError("construction read bundle")),
        patch.object(service, "get_session_summary", side_effect=AssertionError("construction read summary")),
    ):
        sources = (*read_only_project_tool_sources(service=service), *control_project_tool_sources(service=service))
        registry = CoreToolRegistry()
        assert register_project_tool_contributions(registry, sources) is None
    assert len(sources) == len(registry.list_specs()) == 20
    assert len({source.binding_id for source in sources}) == 20
    assert {source.tool_spec.name for source in sources} == {
        "agent_runtime.capability.catalog", "agent_runtime.tool_pool.list", "agent_runtime.tool.search",
        "agent_session.context.read", "project.summary.read", "project.structured_data.search",
        "project.structured_data.item.read", "project.structured_data.items.read", "project.context.resource.read",
        "project.context.bundle", "source_library.item.list", "source_library.item.search", "source_library.item.inspect",
        "agent_artifact.search", "agent_artifact.read", "workflow_graph.list", "workflow_graph.inspect",
        "ingest.status.read", "task.cancel", "task.summary",
    }
    for source in sources:
        definition = source.tool_spec.metadata["legacy_tool_definition"]
        assert source.tool_spec.input_schema == definition["input_schema"]
        assert source.tool_spec.output_schema == definition["output_schema"]
        assert source.tool_spec.name == definition["name"] == definition["capability_id"]


@pytest.mark.parametrize("tool_name", [
    "agent_session.context.read", "project.summary.read", "project.context.bundle",
    "agent_artifact.search", "agent_artifact.read", "ingest.status.read",
])
def test_session_bundle_failure_reaches_original_core_read_consumer(tool_name) -> None:
    from app.services.agent_runtime.read_only_tools import (
        ReadOnlyToolContext, _session_bundle, read_only_project_tool_sources,
    )
    from app.services.agent_core.contracts import compact_json_value

    service = AgentSessionService(store=InMemoryAgentSessionStore())
    failure = service.get_session_bundle("missing-session")
    assert isinstance(failure, Failure)
    assert failure.family == "agent.session.failure"
    assert failure.code == "session_not_found"
    context = ReadOnlyToolContext(service=service, source_library_lister=None, structured_data_searcher=lambda **_: {})
    reads = []

    def source_lister(_project_key):
        reads.append("source_catalog")
        return []

    registry = CoreToolRegistry()
    assert register_project_tool_contributions(registry, read_only_project_tool_sources(
        service=service, source_library_lister=source_lister, structured_data_searcher=lambda **_: reads.append("structured"),
    )) is None
    with (
        patch.object(service, "get_session_bundle", return_value=failure) as owner,
        patch("app.services.job_logger.list_jobs", return_value=[]) as jobs,
        patch("app.services.agent_runtime.read_only_tools._list_writing_documents") as writing,
    ):
        assert _session_bundle(context, "missing-session") is failure
        owner.reset_mock()
        result = registry.execute_tool(
            tool_call=CoreToolCall(tool_name=tool_name, call_id="session-failure-call"),
            request=AgentCoreRequest(message="read", session_id="missing-session", project_key="demo_proj"),
            emit=lambda _event: None,
        )
    owner.assert_called_once_with("missing-session")
    assert jobs.call_count == (1 if tool_name == "ingest.status.read" else 0)
    writing.assert_not_called()
    assert reads == (["source_catalog"] if tool_name in {"project.summary.read", "project.context.bundle"} else [])
    assert result.call_id == "session-failure-call"
    assert result.status == "failed"
    assert result.model_summary == failure.message
    assert result.error == {
        "code": failure.code, "message": failure.message,
        "failure_family": failure.family, "failure_code": failure.code,
        "failure": {"family": failure.family, "code": failure.code, "message": failure.message,
                    "context": compact_json_value(failure.context)},
    }
    assert result.structured_content == {}


def test_context_bundle_stops_after_artifact_session_failure() -> None:
    from app.services.agent_runtime.read_only_tools import read_only_project_tool_sources

    service = AgentSessionService(store=InMemoryAgentSessionStore())
    bundle = service.create_session(source="user", entrypoint_type="interactive_agent", goal="read bundle")
    assert not isinstance(bundle, Failure)
    failure = service.get_session_bundle("missing-artifact-session")
    assert isinstance(failure, Failure)
    reads = []

    def source_lister(_project_key):
        reads.append("source_catalog")
        return []

    def searcher(**_arguments):
        reads.append("structured")
        return {"project_key": "demo_proj", "items": []}

    registry = CoreToolRegistry()
    assert register_project_tool_contributions(registry, read_only_project_tool_sources(
        service=service, source_library_lister=source_lister, structured_data_searcher=searcher,
    )) is None
    with (
        patch.object(service, "get_session_bundle", side_effect=[bundle, failure]) as owner,
        patch("app.services.agent_runtime.read_only_tools._list_writing_documents") as writing,
    ):
        result = registry.execute_tool(
            tool_call=CoreToolCall(tool_name="project.context.bundle", call_id="bundle-failure-call"),
            request=AgentCoreRequest(message="read", session_id=bundle["session"]["session_id"], project_key="demo_proj"),
            emit=lambda _event: None,
        )
    assert owner.call_count == 2
    assert reads == ["source_catalog", "structured"]
    writing.assert_not_called()
    assert result.status == "failed"
    assert result.error["failure"]["code"] == failure.code
    assert result.error["failure"]["context"] == failure.context


def test_session_bundle_read_permission_rejected_before_owner_call() -> None:
    from app.services.agent_runtime.read_only_tools import read_only_project_tool_sources

    service = AgentSessionService(store=InMemoryAgentSessionStore())
    source = next(source for source in read_only_project_tool_sources(service=service)
                  if source.tool_spec.name == "project.context.bundle")
    registry = CoreToolRegistry()
    assert register_project_tool_contributions(registry, (
        replace(source, tool_spec=replace(source.tool_spec, permission="ask")),
    )) is None
    with patch.object(service, "get_session_bundle") as owner:
        result = registry.execute_tool(
            tool_call=CoreToolCall(tool_name="project.context.bundle", call_id="denied-bundle-call"),
            request=AgentCoreRequest(message="read", session_id="missing-session", project_key="demo_proj"),
            emit=lambda _event: None,
        )
    assert result.status == "needs_approval"
    owner.assert_not_called()


@pytest.mark.parametrize("store_result", [None, {"item": None, "errors": []}])
@pytest.mark.parametrize("reference", [
    {"dataset": "materials", "record_id": "record-7"},
    {"item_id": "structured:materials:record-7"},
    {"resource_uri": "project://structured/demo_proj/materials/record-7"},
])
def test_structured_item_read_keeps_searcher_ref_fallback(store_result, reference) -> None:
    from app.services.agent_runtime.read_only_tools import read_only_project_tool_sources

    service = AgentSessionService(store=InMemoryAgentSessionStore())
    searches = []

    def searcher(**arguments):
        searches.append(arguments)
        return {"project_key": "demo_proj", "items": [
            {"dataset": "materials", "record_id": "record-other", "title": "other"},
            {"dataset": "materials", "record_id": "record-7", "title": "recovered", "summary": "full evidence", "source_uri": "source:7"},
        ]}

    registry = CoreToolRegistry()
    assert register_project_tool_contributions(registry, read_only_project_tool_sources(service=service, structured_data_searcher=searcher)) is None
    with patch(
        "app.services.agent_runtime.read_only_tools.read_project_structured_data_item",
        **({"side_effect": OSError("store unavailable")} if store_result is None else {"return_value": store_result}),
    ):
        result = registry.execute_tool(
            tool_call=CoreToolCall(tool_name="project.structured_data.item.read", arguments=reference, call_id="item-call"),
            request=AgentCoreRequest(message="read", session_id="session-1", project_key="demo_proj"),
            emit=lambda _event: None,
        )
    assert searches == [{"project_key": "demo_proj", "query": "record-7", "limit": 50, "datasets": ["materials"]}]
    assert result.status == "completed"
    assert result.error is None
    content = result.structured_content["result"]
    assert content["item"]["record_id"] == "record-7"
    assert content["cleaned_text"] == "full evidence"
    assert content["source_ref"] == "source:7"
    manifest = content["model_evidence_manifest"][0]
    assert manifest["resource_uri"] == "project://structured/demo_proj/materials/record-7"
    assert manifest["dataset"] == "materials"
    assert manifest["record_id"] == "record-7"


def test_project_tool_catalog_rejects_invalid_group_before_registration() -> None:
    valid = _source(
        "example.valid",
        lambda call, _spec, _request, _emit: CoreToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status="completed",
            model_summary="ok",
        ),
    )
    missing_handler = _source("example.missing", None)
    registry = CoreToolRegistry()

    failure = register_project_tool_contributions(
        registry,
        (valid, missing_handler),
    )
    assert isinstance(failure, Failure)
    assert failure.code == "CONTRIBUTION_INVALID"
    assert (failure.context or {})["issues"][0]["path"] == "$.source.handler"
    assert registry.list_specs() == []

    wrong_executor = replace(valid, executor_ref="example.other")
    failure = compile_project_tool_native(wrong_executor)
    assert isinstance(failure, Failure)
    assert "executor_ref" in failure.context["issues"][0]["message"]


def test_project_tool_contract_retains_existing_authority_boundaries() -> None:
    from app.services.agent_core.macro_tools import FacilityBinding

    source = _source("example.review", lambda *_: None)
    spec = replace(
        source.tool_spec,
        input_schema={"type": "object", "properties": {"project_key": {"type": "string"}}},
        risk="write_shared",
        permission="allow",
        concurrency="serial",
        metadata={"auto_allow_session_write": True},
    )
    source = replace(source, tool_spec=spec)
    native = compile_project_tool_native(source)
    assert not isinstance(native, Failure)
    assert native.definition.tool_spec is spec
    assert native.definition.input_policy == "project_tool_contract"

    # A model selector is neither a role grant nor an implicit permission.
    for field in ("permission", "permissions", "actor_role"):
        forbidden = replace(spec, input_schema={"type": "object", "properties": {field: {"type": "string"}}})
        assert isinstance(compile_project_tool_native(replace(source, tool_spec=forbidden)), Failure)
    assert isinstance(compile_project_tool_native(replace(source, tool_spec=replace(spec, metadata={}))), Failure)
    assert isinstance(
        compile_project_tool_native(replace(source, tool_spec=replace(spec, concurrency="parallel"))), Failure
    )

    # The original macro-facility boundary remains request-only by default.
    with pytest.raises(ValueError, match="cannot grant scope or permission"):
        FacilityBinding(
            binding_id=source.binding_id,
            version=source.version,
            tool_spec=spec,
            handler=source.handler,
            executor_ref=source.executor_ref,
            scope_source=source.scope_source,
            permission_source=source.permission_source,
            failure_family=source.failure_family,
            readback_semantics=source.readback_semantics,
        )


def test_source_plan_and_skill_load_reach_native_codex_consumer() -> None:
    from app.services.agent_core.host_authorization import TrustedHostContext

    service = AgentSessionService(store=InMemoryAgentSessionStore())
    bundle = service.create_session(
        source="user",
        entrypoint_type="agent_core",
        goal="native project tools",
        project_key="demo_proj",
        task_blueprints=[],
    )
    session_id = bundle["session"]["session_id"]
    host_context = TrustedHostContext(
        project_key="demo_proj",
        session_id=session_id,
        host_thread_id="session-1",
        turn_id="turn-1",
        user_message_id="host-message-1",
    )
    host_message = service.create_host_user_message(host_context, content="native project tools")
    assert not isinstance(host_message, Failure)
    registered_skill = {
        "skill_id": "example.read",
        "owner": "tests",
        "execution_profile": "default",
        "concurrency_class": "read_only",
        "required_permissions": [],
    }
    public_dns = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
    observed_sources: list[ProjectToolAuthorSource] = []

    def capture_sources(registry, sources):
        observed_sources.extend(sources)
        return register_project_tool_contributions(registry, sources)

    with (
        patch(
            "app.services.agent_core.project_tools.list_registered_skills",
            return_value=[registered_skill],
        ),
        patch(
            "app.services.agent_core.query_tools.list_registered_skills",
            return_value=[registered_skill],
        ),
        patch(
            "app.services.agent_core.project_tools.register_project_tool_contributions",
            side_effect=capture_sources,
        ),
        patch(
            "app.services.source_library.external_project.socket.getaddrinfo",
            return_value=public_dns,
        ),
    ):
        binding = build_agent_macro_rapid_binding(
            project_key="demo_proj",
            scope_id="session-1",
            service=service,
            session_id=session_id,
            turn_id="turn-1",
            user_message_id="host-message-1",
        )
        tools = {tool.logical_name: tool for tool in binding.tools}
        source_tool = tools["source_discovery.plan"]
        skill_tool = tools["skill.load"]

        sources = {source.tool_spec.name: source for source in observed_sources}
        assert [source.tool_spec.name for source in observed_sources] == [
            "agent_runtime.capability.catalog",
            "agent_runtime.tool_pool.list",
            "agent_runtime.tool.search",
            "agent_session.context.read",
            "project.summary.read",
            "project.structured_data.search",
            "project.structured_data.item.read",
            "project.structured_data.items.read",
            "project.context.resource.read",
            "project.context.bundle",
            "source_library.item.list",
            "source_library.item.search",
            "source_library.item.inspect",
            "agent_artifact.search",
            "agent_artifact.read",
            "workflow_graph.list",
            "workflow_graph.inspect",
            "ingest.status.read",
            "task.cancel",
            "task.summary",
            "agent_task.plan.append",
            "agent_long_task.stage.update",
            "agent_long_task.stage.read",
            "agent_session.resume_bundle",
            "project.graph.search",
            "project.structured_graph.query",
            "project.structured_data.quality_audit",
            "chain.expand",
            "source.web.search",
            "source.candidate.review",
            "ingest.url_pool.submit",
            "ingest.url_pool.status",
            "source.history.read",
            "agent_investigation.leads.append",
            "agent_investigation.trace.read",
            "writing.document.list",
            "writing.document.read",
            "writing.document.section.read",
            "writing.document.create",
            "writing.document.insert_paragraph",
            "writing.document.citations.upsert",
            "agent_batch.submit",
            "skill.search",
            "source.discovery.plan",
            "skill.load",
            "ingest.source_library.run",
            "workflow_graph.run",
            "report.generate",
        ]
        assert (
            sources["source.discovery.plan"].scope_source
            == "AgentCoreRequest.project_key plus source-discovery planning arguments and source catalog read"
        )
        assert sources["source.discovery.plan"].tool_spec.risk == "read_only"
        assert sources["source.discovery.plan"].tool_spec.permission == "allow"
        assert sources["skill.load"].failure_family.endswith("original skill metadata handler")
        assert source_tool.input_schema["properties"]["candidate_urls"]["type"] == "array"
        assert skill_tool.input_schema["required"] == ["skill_id"]
        source_result = source_tool.handler(
            {
                "topic": "robot funding",
                "candidate_urls": ["https://example.com/robot"],
                "domains": ["example.com"],
            }
        )
        skill_result = skill_tool.handler({"skill_id": "example.read"})

    assert source_result["status"] == "completed"
    assert source_result["structured_content"]["quality_gates"]["network_fetch_performed"] is False
    assert skill_result["status"] == "completed"
    assert skill_result["structured_content"]["skill"]["skill_id"] == "example.read"


def test_governed_dispatch_keeps_original_frontdoor_contract() -> None:
    source = _source("example.dispatch", lambda *_: None)
    frontdoor = "existing.governed.frontdoor"
    spec = replace(
        source.tool_spec,
        risk="write_external",
        permission="allow",
        concurrency="serial",
        metadata={"uses_existing_frontdoor": frontdoor},
    )
    source = replace(source, tool_spec=spec, governed_dispatch_ref=frontdoor)
    native = compile_project_tool_native(source)
    assert not isinstance(native, Failure)
    assert native.definition.tool_spec is spec
    assert isinstance(compile_project_tool_native(replace(source, governed_dispatch_ref=None)), Failure)
    assert isinstance(compile_project_tool_native(replace(source, governed_dispatch_ref="other.frontdoor")), Failure)
    assert isinstance(
        compile_project_tool_native(replace(source, tool_spec=replace(spec, concurrency="parallel"))), Failure
    )
    assert isinstance(
        compile_project_tool_native(
            replace(
                source,
                tool_spec=replace(
                    spec, input_schema={"type": "object", "properties": {"permission": {"type": "string"}}}
                ),
            )
        ),
        Failure,
    )


def test_source_history_read_failure_is_not_projected_as_empty_success() -> None:
    from app.services.agent_core.authoring_tools import (
        AuthoringToolContext,
        authoring_ingest_writing_batch_sources,
    )

    def execute(service: AgentSessionService, session_id: str) -> CoreToolResult:
        registry = CoreToolRegistry()
        assert (
            register_project_tool_contributions(
                registry,
                authoring_ingest_writing_batch_sources(
                    AuthoringToolContext(service=service, structured_data_searcher=lambda **_kwargs: {})
                ),
            )
            is None
        )
        spec = registry.get("source.history.read")
        assert spec is not None
        return registry.execute_tool(
            tool_call=CoreToolCall(
                tool_name="source.history.read",
                arguments={"project_key": "demo_proj"},
                call_id="call-source-history",
            ),
            tool_spec=spec,
            request=AgentCoreRequest(
                message="read source history",
                session_id=session_id,
                project_key="demo_proj",
            ),
            emit=lambda _event: None,
        )

    missing_session = execute(AgentSessionService(store=InMemoryAgentSessionStore()), "missing-session")
    assert missing_session.status == "failed"
    assert missing_session.error is not None
    assert missing_session.error["code"] == "session_not_found"
    assert missing_session.retry_hint is None

    healthy_service = AgentSessionService(store=InMemoryAgentSessionStore())
    bundle = healthy_service.create_session(
        source="user",
        entrypoint_type="agent_core",
        goal="source history",
        project_key="demo_proj",
        task_blueprints=[],
    )
    assert not isinstance(bundle, Failure)

    class ArtifactFailureService(AgentSessionService):
        def list_artifacts(self, session_id: str):
            return super().list_artifacts("missing-artifact-session")

    failure_service = ArtifactFailureService(store=healthy_service.store)
    propagated_failure = execute(failure_service, bundle["session"]["session_id"])
    assert propagated_failure.status == "failed"
    assert propagated_failure.error is not None
    assert propagated_failure.error["code"] == "session_not_found"
    assert propagated_failure.error["failure_family"] == "agent.session.failure"
    assert propagated_failure.retry_hint is None

    class ArtifactReadExceptionService(AgentSessionService):
        def list_artifacts(self, session_id: str):
            raise RuntimeError("artifact store unavailable")

    service = ArtifactReadExceptionService(store=healthy_service.store)
    artifact_failure = execute(service, bundle["session"]["session_id"])
    assert artifact_failure.status == "failed"
    assert artifact_failure.error is not None
    assert artifact_failure.error["code"] == "source_history_read_failed"
    assert artifact_failure.error["phase"] == "artifact_read"
    assert artifact_failure.structured_content == {}


def test_project_tool_schema_projection_preserves_nested_schema_sequences() -> None:
    from app.services.agent_core.macro_environment import native_tool_specs
    from app.services.agent_core.project_tools import build_project_core_tool_registry

    registry = build_project_core_tool_registry(
        service=AgentSessionService(store=InMemoryAgentSessionStore())
    )
    spec = registry.get("project.structured_data.search")
    assert spec is not None
    dataset_enum = spec.input_schema["properties"]["datasets"]["items"]["enum"]
    assert isinstance(dataset_enum, list)
    assert dataset_enum == [
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
    ]

    projected = next(
        tool
        for namespace in native_tool_specs(registry.list_specs())
        if namespace.get("name") == "project_structured_data"
        for tool in namespace["tools"]
        if tool.get("name") == "search"
    )
    assert projected["inputSchema"]["properties"]["datasets"]["items"]["enum"] == dataset_enum
