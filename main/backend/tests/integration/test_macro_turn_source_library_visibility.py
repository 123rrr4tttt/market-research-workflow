from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from app.services.agent_core.contracts import CoreToolSpec
from app.services.agent_core.macro_host import (
    AgentMacroHostService,
    MacroEnvironment,
    MacroNativeBinding,
)
from app.services.agent_core.project_tools import build_project_core_tool_registry
from app.services.agent_core.registry import CoreToolRegistry
from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_sessions.store import InMemoryAgentSessionStore


pytestmark = pytest.mark.integration


@dataclass
class ControlledSourceReader:
    items: list[dict[str, object]] = field(default_factory=list)
    reads: list[str | None] = field(default_factory=list)

    def list_items(self, project_key: str | None) -> list[dict[str, object]]:
        self.reads.append(project_key)
        return [dict(item) for item in self.items]


class SourceEnvironmentOwner:
    def __init__(self, sessions: AgentSessionService, reader: ControlledSourceReader) -> None:
        self.sessions = sessions
        self.reader = reader
        self.extra_tool_enabled = False
        self.registries: dict[int, CoreToolRegistry] = {}

    def resolve(self, *, project_key, binding_id, phase, package_id=None, package_version=None):
        del project_key, binding_id, phase, package_id, package_version
        registry = build_project_core_tool_registry(
            service=self.sessions, source_library_lister=self.reader.list_items,
        )
        if self.extra_tool_enabled:
            registry.register(
                CoreToolSpec(name="snapshot.new", description_for_model="New turn tool", permission="allow"),
                lambda call, spec, request, emit: CoreToolRegistry.simple_result(
                    call=call, model_summary="new registry"
                ),
            )
        environment = MacroEnvironment(
            environment_digest="source-registry-v2" if self.extra_tool_enabled else "source-registry-v1",
            dynamic_tools=tuple({"name": spec.name} for spec in registry.list_specs()),
            skills=(),
            skill_roots=(),
            descriptor={"contract_version": "test.source_environment.v1", "status": "configured"},
            status="configured",
        )
        self.registries[id(environment)] = registry
        return environment

    def assemble(self, environment, context):
        del context
        return MacroNativeBinding(
            native_binding=object(), registry=self.registries[id(environment)],
            package_digest=environment.package_digest,
        )


def _record(service: AgentMacroHostService, turn_id: str) -> dict:
    admission = service.prepare_turn(thread_id="thread-1")
    recorded = service.record_input(
        thread_id="thread-1", turn_id=turn_id, content="inspect sources",
        admission_id=admission["admissionId"],
    )
    assert recorded["environmentDigest"] == admission["environmentDigest"]
    return admission


def _dispatch(service: AgentMacroHostService, turn_id: str, call_id: str, namespace: str, tool: str,
              arguments: dict[str, object] | None = None) -> dict:
    return service.dispatch(
        thread_id="thread-1", turn_id=turn_id, call_id=call_id,
        namespace=namespace, tool=tool, arguments=arguments or {},
    )


def _result(response: dict) -> dict:
    assert response["success"] is True, response
    return response["resultProjection"]["structured_content"]["result"]


def test_source_items_remain_live_within_snapshot_while_next_turn_loads_new_registry() -> None:
    reader = ControlledSourceReader(items=[{
        "item_key": "water.monitoring", "name": "Water monitoring", "description": "baseline",
        "channel_key": "official_site", "enabled": True, "scope": "project",
    }])
    sessions = AgentSessionService(store=InMemoryAgentSessionStore())
    owner = SourceEnvironmentOwner(sessions, reader)
    service = AgentMacroHostService(
        project_checker=lambda key: key == "project-a",
        agent_session_service=sessions,
        environment_owner=owner,
    )
    binding = service.prepare(project_key="project-a")
    service.bind(binding_id=binding["bindingId"], thread_id="thread-1")
    first = _record(service, "turn-1")
    assert first["environmentDigest"] == "source-registry-v1"
    assert {"source_library.item.list", "source_library.item.search", "source_library.item.inspect"} <= {
        item["name"] for item in first["dynamicTools"]
    }
    assert reader.reads == []

    listed = _result(_dispatch(service, "turn-1", "list-before", "source_library_item", "list"))
    assert listed["items"][0]["description"] == "baseline"

    reader.items[0]["description"] = "updated quality observations"
    searched = _result(_dispatch(
        service, "turn-1", "search-after", "source_library_item", "search", {"query": "quality"},
    ))
    inspected = _result(_dispatch(
        service, "turn-1", "inspect-after", "source_library_item", "inspect",
        {"item_key": "water.monitoring"},
    ))
    assert searched["total"] == 1
    assert searched["items"][0]["description"] == "updated quality observations"
    assert inspected["item"]["description"] == "updated quality observations"
    assert reader.reads == ["project-a"] * 3

    owner.extra_tool_enabled = True
    second = _record(service, "turn-2")
    assert second["environmentDigest"] == "source-registry-v2"
    assert "snapshot.new" in {item["name"] for item in second["dynamicTools"]}
    assert "snapshot.new" not in {item["name"] for item in first["dynamicTools"]}
    assert _dispatch(service, "turn-2", "new-tool", "snapshot", "new")["success"] is True
    old_tool = _dispatch(service, "turn-1", "old-new-tool", "snapshot", "new")
    assert old_tool["success"] is False
    assert "unknown mounted macro tool" in old_tool["contentItems"][0]["text"]

    reader.items[0]["description"] = "latest quality observations"
    late_old = _result(_dispatch(
        service, "turn-1", "late-old-inspect", "source_library_item", "inspect",
        {"item_key": "water.monitoring"},
    ))
    assert late_old["item"]["description"] == "latest quality observations"
    assert reader.reads == ["project-a"] * 4


def test_delayed_old_turn_record_assembles_its_admitted_registry() -> None:
    sessions = AgentSessionService(store=InMemoryAgentSessionStore())
    owner = SourceEnvironmentOwner(sessions, ControlledSourceReader())
    service = AgentMacroHostService(
        project_checker=lambda key: key == "project-a",
        agent_session_service=sessions,
        environment_owner=owner,
    )
    binding = service.prepare(project_key="project-a")
    service.bind(binding_id=binding["bindingId"], thread_id="thread-1")
    old_admission = service.prepare_turn(thread_id="thread-1")
    owner.extra_tool_enabled = True
    new_admission = service.prepare_turn(thread_id="thread-1")

    for turn_id, admission in (("turn-1", old_admission), ("turn-2", new_admission)):
        service.record_input(
            thread_id="thread-1", turn_id=turn_id, content="inspect sources",
            admission_id=admission["admissionId"],
        )
    assert _dispatch(service, "turn-2", "new-tool", "snapshot", "new")["success"] is True
    old_tool = _dispatch(service, "turn-1", "old-new-tool", "snapshot", "new")
    assert old_tool["success"] is False
    assert "unknown mounted macro tool" in old_tool["contentItems"][0]["text"]
    assert _result(_dispatch(service, "turn-1", "old-list", "source_library_item", "list"))["items"] == []
