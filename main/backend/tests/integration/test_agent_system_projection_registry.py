from __future__ import annotations

from dataclasses import asdict
import json
from unittest.mock import patch

from app.services.agent_core.contracts import AgentCoreRequest, CoreToolCall
from app.services.agent_core.project_tools import build_project_core_tool_registry
from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_sessions.store import InMemoryAgentSessionStore


SOURCE_ITEM = {
    "item_key": "water.monitoring",
    "name": "Water monitoring",
    "channel_key": "official_site",
    "enabled": True,
    "item_type": "website",
    "scope": "project",
    "managed_by": "demo",
    "description": "Water-quality observations",
    "tags": ["water"],
}


def _request(project_key: str | None = "water_proj") -> AgentCoreRequest:
    return AgentCoreRequest(
        message="inspect MRW",
        session_id="system-projection-session",
        project_key=project_key,
    )


def _execute(registry, tool_name: str, arguments: dict | None = None, *, project_key: str | None = "water_proj"):
    return registry.execute_tool(
        tool_call=CoreToolCall(
            tool_name=tool_name,
            arguments=arguments or {},
            call_id=f"call-{tool_name}",
        ),
        request=_request(project_key),
        emit=lambda _event: None,
    )


def _result(result):
    return result.structured_content["result"]


def _core_envelope_bytes(result) -> int:
    return len(json.dumps(asdict(result), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def test_registry_registers_one_system_inspect_after_original_registration() -> None:
    calls: list[str | None] = []

    def controlled_lister(project_key: str | None):
        calls.append(project_key)
        return [dict(SOURCE_ITEM)]

    with (
        patch("app.services.agent_core.project_tools.list_registered_skills", return_value=[]),
        patch(
            "app.services.agent_core.project_tools.build_system_projection",
            side_effect=build_project_core_tool_registry.__globals__["build_system_projection"],
        ) as projection_builder,
    ):
        registry = build_project_core_tool_registry(
            service=AgentSessionService(store=InMemoryAgentSessionStore()),
            source_library_lister=controlled_lister,
        )

    assert calls == []
    assert projection_builder.call_count == 1
    inspect_specs = [
        spec for spec in registry.list_specs() if spec.name == "agent_runtime.system.inspect"
    ]
    assert len(inspect_specs) == 1
    spec = inspect_specs[0]
    assert spec.risk == "read_only"
    assert spec.permission == "allow"
    assert spec.concurrency == "parallel"
    schema_bytes = len(
        json.dumps(spec.input_schema, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    assert schema_bytes <= 4096

    run_spec = registry.get("ingest.source_library.run")
    assert run_spec is not None
    assert run_spec.permission == "ask"


def test_registry_system_projection_navigates_to_original_source_tool() -> None:
    service = AgentSessionService(store=InMemoryAgentSessionStore())
    with patch("app.services.agent_core.project_tools.list_registered_skills", return_value=[]):
        registry = build_project_core_tool_registry(
            service=service,
            source_library_lister=lambda project_key: [dict(SOURCE_ITEM)],
        )

    root = _execute(
        registry,
        "agent_runtime.system.inspect",
        {},
        project_key=None,
    )
    assert root.status == "completed"
    assert _core_envelope_bytes(root) <= 8192
    root_result = _result(root)
    assert root_result["system_id"] == "mrw.system"
    assert root_result["project_key"] is None
    root_item = root_result["items"][0]
    assert root_item["ref"] == "mrw.system"
    assert root_item["unmapped_tool_count"] >= 0
    assert root_item["coverage_ref"] == "mrw.coverage.unmapped_tools"
    root_relations = list(root_result["relations"])
    continuation = root_result["next"]
    while continuation is not None:
        continued = _execute(registry, "agent_runtime.system.inspect", continuation, project_key=None)
        assert continued.status == "completed"
        continued_result = _result(continued)
        root_relations.extend(continued_result["relations"])
        continuation = continued_result["next"]
    assert any(
        relation["target_ref"] == "tool:agent_runtime.system.inspect"
        for relation in root_relations
    )

    queried = _execute(
        registry,
        "agent_runtime.system.inspect",
        {"query": "数据源", "limit": 20},
    )
    assert queried.status == "completed"
    assert _result(queried)["items"][0]["ref"] == "mrw.sources"

    projected_tool = _execute(
        registry,
        "agent_runtime.system.inspect",
        {"ref": "tool:source_library.item.list"},
    )
    assert projected_tool.status == "completed"
    tool_item = _result(projected_tool)["items"][0]
    original = registry.get("source_library.item.list")
    assert original is not None
    assert tool_item["tool_name"] == original.name
    assert tool_item["schema_ref"] == "tool:source_library.item.list#input_schema"
    assert tool_item["risk"] == original.risk
    assert tool_item["permission"] == original.permission
    assert tool_item["project_service_id"] == original.project_service_id
    assert tool_item["system_refs"] == ["mrw.sources"]


def test_catalog_and_tool_search_use_exact_system_ref_projection() -> None:
    service = AgentSessionService(store=InMemoryAgentSessionStore())
    with patch("app.services.agent_core.project_tools.list_registered_skills", return_value=[]):
        registry = build_project_core_tool_registry(
            service=service,
            source_library_lister=lambda project_key: [dict(SOURCE_ITEM)],
        )

    catalog = _execute(registry, "agent_runtime.capability.catalog", {})
    assert catalog.status == "completed"
    catalog_items = _result(catalog)["items"]
    by_id = {str(item.get("capability_id")): item for item in catalog_items}
    assert by_id["source_library.item.list"]["system_refs"] == ["mrw.sources"]
    assert by_id["agent_runtime.system.inspect"]["system_refs"] == ["mrw.system"]
    assert by_id["ingest.source_library.run"]["system_refs"] == ["mrw.ingestion"]
    assert by_id["source.history.read"]["system_refs"] == ["mrw.sources"]

    searched = _execute(
        registry,
        "agent_runtime.tool.search",
        {"query": "source_library.item.list", "limit": 20},
    )
    assert searched.status == "completed"
    search_items = _result(searched)["items"]
    exact = [item for item in search_items if item.get("tool_name") == "source_library.item.list"]
    assert exact
    assert exact[0]["system_refs"] == ["mrw.sources"]


def test_system_projection_handler_preserves_real_call_identity_and_transport_budget() -> None:
    service = AgentSessionService(store=InMemoryAgentSessionStore())
    with patch("app.services.agent_core.project_tools.list_registered_skills", return_value=[]):
        registry = build_project_core_tool_registry(
            service=service,
            source_library_lister=lambda project_key: [dict(SOURCE_ITEM)],
        )
    long_call_id = "identity-" + "x" * 9000
    result = registry.execute_tool(
        tool_call=CoreToolCall(
            tool_name="agent_runtime.system.inspect",
            arguments={},
            call_id=long_call_id,
        ),
        request=_request(None),
        emit=lambda _event: None,
    )
    assert result.call_id == long_call_id
    assert result.status == "failed"
    assert result.error["code"] == "system_projection_transport_too_large"


def test_original_source_library_handler_and_failure_remain_authoritative() -> None:
    calls: list[str | None] = []

    def successful_lister(project_key: str | None):
        calls.append(project_key)
        return [dict(SOURCE_ITEM)]

    service = AgentSessionService(store=InMemoryAgentSessionStore())
    with patch("app.services.agent_core.project_tools.list_registered_skills", return_value=[]):
        registry = build_project_core_tool_registry(
            service=service,
            source_library_lister=successful_lister,
        )
    listed = _execute(registry, "source_library.item.list", {"limit": 10})
    assert listed.status == "completed"
    assert _result(listed)["items"][0]["item_key"] == "water.monitoring"
    assert calls == ["water_proj"]

    def failing_lister(project_key: str | None):
        raise RuntimeError("controlled source failure")

    with patch("app.services.agent_core.project_tools.list_registered_skills", return_value=[]):
        failing_registry = build_project_core_tool_registry(
            service=AgentSessionService(store=InMemoryAgentSessionStore()),
            source_library_lister=failing_lister,
        )
    failed = _execute(failing_registry, "source_library.item.list", {"limit": 10})
    assert failed.status == "failed"
    assert failed.error["type"] == "RuntimeError"
    assert "controlled source failure" in failed.error["message"]
    assert _result(failed)["items"] == []
