from __future__ import annotations

import json
from pathlib import Path

import pytest
from functorial_kit import Failure
from starlette.requests import Request

from app.api.crawler import list_crawler_agent_modules_api
from app.services.agent_core.contracts import AgentCoreRequest, CoreToolCall, CoreToolSpec
from app.services.agent_core.host_authorization import TrustedHostContext
from app.services.agent_core.macro_environment import resolve_macro_environment, assemble_native_macro_binding
from app.services.agent_core.registry import CoreToolRegistry
from app.services.agent_core import workbench_tools
from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_sessions.store import InMemoryAgentSessionStore
from app.services.crawlers_mgmt import workbench


def _registry():
    registry = CoreToolRegistry()
    facilities = workbench_tools.workbench_facilities()
    for binding in facilities:
        assert registry.register(binding.tool_spec, binding.handler) is None
    registry.register(CoreToolSpec(name="original.read", description_for_model="An unrelated base tool."), lambda *args: None)
    return registry, facilities


def _host():
    service = AgentSessionService(store=InMemoryAgentSessionStore())
    bundle = service.create_session(source="trusted_host", entrypoint_type="agent_macro", project_key="project_a", goal="connect project")
    session_id = bundle["session"]["session_id"]
    context = TrustedHostContext("project_a", session_id, "host-1", "turn-1", "message-1")
    service.create_host_user_message(context, content="Connect this project's code through the workbench.")
    return service, context, AgentCoreRequest(message="connect project", project_key="project_a", session_id=session_id, turn_id="turn-1")


def test_workbench_catalog_derives_real_facilities_with_host_boundary():
    registry, facilities = _registry()
    names = {spec.name for spec in registry.list_specs()}
    assert {f"concept_workbench.project.{item['id']}" for item in workbench.OPERATION_DEFINITIONS} <= names
    assert {"concept_workbench.module.read", "concept_workbench.method.read"} <= names
    for binding in facilities:
        assert binding.governed_dispatch_ref == "agent_core.host_authorization"
        assert binding.tool_spec.permission == "allow"
        assert "root" not in binding.tool_spec.input_schema["properties"]
        assert binding.tool_spec.input_schema["additionalProperties"] is False


def test_unbound_workbench_call_has_zero_effect(monkeypatch):
    registry, _ = _registry()
    calls = []
    monkeypatch.setattr(workbench_tools, "run_workbench", lambda *args: calls.append(args))
    result = registry.execute_tool(
        tool_call=CoreToolCall(call_id="call-1", tool_name="concept_workbench.project.sync", arguments={"target_id": "mrw"}),
        request=AgentCoreRequest(message="sync", project_key="project_a", session_id="session-1", turn_id="turn-1"), emit=lambda event: None,
    )
    assert result.status == "failed"
    assert result.error["code"] == "workbench_host_required"
    assert calls == []


@pytest.mark.parametrize("exit_code,status", [(0, "completed"), (7, "failed")])
def test_host_workbench_calls_preserve_original_result_without_approval(monkeypatch, exit_code, status):
    registry, _ = _registry()
    service, context, request = _host()
    observed = []
    original = {"exit_code": exit_code, "stdout": '{"observed":true}', "stderr": "original diagnostic", "report": {"observed": True}}
    def runner(operation, arguments, project_key):
        observed.append((operation, arguments, project_key))
        return original
    monkeypatch.setattr(workbench_tools, "run_workbench", runner)
    result = registry.execute_tool(
        tool_call=CoreToolCall(call_id="call-1", tool_name="concept_workbench.project.check", arguments={"target_id": "mrw", "catalog": "catalog.py"}),
        request=request, emit=lambda event: None, trusted_context=context, authorization_service=service,
    )
    assert result.status == status
    assert result.structured_content == original
    assert observed == [("check", {"target_id": "mrw", "catalog": "catalog.py"}, "project_a")]
    assert service.list_approvals(session_id=context.session_id) == []


def test_registered_workbench_method_is_consumed_by_base_cell_without_fake_package(monkeypatch, tmp_path):
    monkeypatch.setattr(workbench, "workbench_module", lambda key: {"available": key == "project_a"})
    skill = tmp_path / workbench_tools.WORKBENCH_SKILL_ID / "SKILL.md"
    skill.parent.mkdir()
    skill.write_text("# Wiring\nRead original methods and invoke original tools.\n")
    registry, facilities = _registry()
    service, context, _ = _host()
    resolved = resolve_macro_environment(service, "project_a", (), (), (tmp_path,), registry, facilities)
    assert not isinstance(resolved, Failure)
    assert resolved.package is None
    assert resolved.definition.core_binding_ref == "agent.macro.base"
    assert resolved.definition.skill_contents[0].skill_id == workbench_tools.WORKBENCH_SKILL_ID
    assert "original.read" in {spec.name for spec in resolved.tools}
    native = assemble_native_macro_binding(resolved, context, service)
    assert not isinstance(native, Failure)
    assert native.skills[0].name == workbench_tools.WORKBENCH_SKILL_ID
    assert Path(native.skills[0].path).read_bytes() == skill.read_bytes()
    assert native.find_tool(namespace="concept_workbench_project", name="scan") is not None
    assert service.store.list_project_artifacts(project_key="project_a") == []
    digest = resolved.environment_digest
    skill.write_text("# Wiring\nUpdated source instructions.\n")
    changed = resolve_macro_environment(service, "project_a", (), (), (tmp_path,), registry, facilities)
    assert changed.environment_digest != digest
    other = resolve_macro_environment(service, "project_b", (), (), (tmp_path,), registry, facilities)
    assert other.skills == ()


def test_collector_module_readback_is_scoped_and_does_not_deploy(monkeypatch):
    calls = []
    module = {"id": "concept_workbench.project_wiring", "available": True, "cell_ref": "agent.macro.base"}
    def read(project):
        calls.append(project)
        return module
    monkeypatch.setattr(workbench, "workbench_module", read)
    request = Request({"type": "http", "headers": [(b"x-project-key", b"project_a")], "query_string": b""})
    result = list_crawler_agent_modules_api(request)
    assert json.loads(result.body)["data"]["items"] == [module]
    assert calls == ["project_a"]
    unbound = list_crawler_agent_modules_api(Request({"type": "http", "headers": [], "query_string": b""}))
    assert unbound.status_code == 400
    assert calls == ["project_a"]
