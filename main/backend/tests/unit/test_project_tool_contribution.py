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
    assert isinstance(compile_project_tool_native(replace(source, tool_spec=replace(spec, concurrency="parallel"))), Failure)

    # The original macro-facility boundary remains request-only by default.
    with pytest.raises(ValueError, match="cannot grant scope or permission"):
        FacilityBinding(
            binding_id=source.binding_id, version=source.version, tool_spec=spec,
            handler=source.handler, executor_ref=source.executor_ref,
            scope_source=source.scope_source, permission_source=source.permission_source,
            failure_family=source.failure_family, readback_semantics=source.readback_semantics,
        )


def test_source_plan_and_skill_load_reach_native_codex_consumer() -> None:
    service = AgentSessionService(store=InMemoryAgentSessionStore())
    bundle = service.create_session(
        source="user",
        entrypoint_type="agent_core",
        goal="native project tools",
        project_key="demo_proj",
        task_blueprints=[],
    )
    registered_skill = {
        "skill_id": "example.read",
        "owner": "tests",
        "execution_profile": "default",
        "concurrency_class": "read_only",
        "required_permissions": [],
    }
    public_dns = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))
    ]
    observed_sources: list[ProjectToolAuthorSource] = []

    def capture_sources(registry, sources):
        observed_sources.extend(sources)
        return register_project_tool_contributions(registry, sources)

    with patch(
        "app.services.agent_core.project_tools.list_registered_skills",
        return_value=[registered_skill],
    ), patch(
        "app.services.agent_core.query_tools.list_registered_skills",
        return_value=[registered_skill],
    ), patch(
        "app.services.agent_core.project_tools.register_project_tool_contributions",
        side_effect=capture_sources,
    ), patch(
        "app.services.source_library.external_project.socket.getaddrinfo",
        return_value=public_dns,
    ):
        binding = build_agent_macro_rapid_binding(
            project_key="demo_proj",
            scope_id="session-1",
            service=service,
            session_id=bundle["session"]["session_id"],
        )
        tools = {tool.logical_name: tool for tool in binding.tools}
        source_tool = tools["source_discovery.plan"]
        skill_tool = tools["skill.load"]

        sources = {source.tool_spec.name: source for source in observed_sources}
        assert [source.tool_spec.name for source in observed_sources] == [
            "agent_task.plan.append", "agent_long_task.stage.update", "agent_long_task.stage.read",
            "agent_session.resume_bundle", "project.graph.search", "project.structured_graph.query",
            "project.structured_data.quality_audit", "chain.expand", "source.web.search",
            "source.candidate.review", "ingest.url_pool.submit", "ingest.url_pool.status",
            "source.history.read", "agent_investigation.leads.append", "agent_investigation.trace.read",
            "writing.document.list", "writing.document.read", "writing.document.section.read",
            "writing.document.create", "writing.document.insert_paragraph", "writing.document.citations.upsert",
            "agent_batch.submit", "skill.search", "source.discovery.plan", "skill.load",
            "workflow_graph.run", "report.generate",
        ]
        assert sources["source.discovery.plan"].scope_source == "AgentCoreRequest.project_key plus source-discovery planning arguments and source catalog read"
        assert sources["source.discovery.plan"].tool_spec.risk == "read_only"
        assert sources["source.discovery.plan"].tool_spec.permission == "allow"
        assert sources["skill.load"].failure_family.endswith(
            "original skill metadata handler"
        )
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
    assert source_result["structured_content"]["quality_gates"][
        "network_fetch_performed"
    ] is False
    assert skill_result["status"] == "completed"
    assert skill_result["structured_content"]["skill"]["skill_id"] == "example.read"


def test_governed_dispatch_keeps_original_frontdoor_contract() -> None:
    source = _source("example.dispatch", lambda *_: None)
    frontdoor = "existing.governed.frontdoor"
    spec = replace(source.tool_spec, risk="write_external", permission="allow",
                   concurrency="serial", metadata={"uses_existing_frontdoor": frontdoor})
    source = replace(source, tool_spec=spec, governed_dispatch_ref=frontdoor)
    native = compile_project_tool_native(source)
    assert not isinstance(native, Failure)
    assert native.definition.tool_spec is spec
    assert isinstance(compile_project_tool_native(replace(source, governed_dispatch_ref=None)), Failure)
    assert isinstance(compile_project_tool_native(replace(source, governed_dispatch_ref="other.frontdoor")), Failure)
    assert isinstance(compile_project_tool_native(replace(source, tool_spec=replace(spec, concurrency="parallel"))), Failure)
    assert isinstance(compile_project_tool_native(replace(source, tool_spec=replace(spec, input_schema={
        "type": "object", "properties": {"permission": {"type": "string"}}}))), Failure)
