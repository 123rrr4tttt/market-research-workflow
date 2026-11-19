from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest
from functorial_kit import Failure

from app.services.agent_core.contracts import CoreToolSpec
from app.services.agent_core.host_authorization import TrustedHostContext
from app.services.agent_core.macro_environment import (
    SYSTEM_NAVIGATION_INSTRUCTIONS,
    assemble_native_macro_binding,
    native_tool_specs,
    resolve_macro_environment,
)
import app.services.agent_core.macro_host as macro_host_module
from app.services.agent_core.macro_host import (
    AgentMacroHostService,
    DefaultMacroEnvironmentOwner,
    MacroEnvironment,
    MacroNativeBinding,
)
from app.services.agent_core.project_tools import build_project_core_tool_registry
from app.services.agent_core.registry import CoreToolRegistry
from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_sessions.store import InMemoryAgentSessionStore


SKILL_ROOTS = ((Path(__file__).resolve().parents[2] / "skills"),)


def _registry(tool_name: str = "demo.read") -> CoreToolRegistry:
    registry = CoreToolRegistry()
    registry.register(
        CoreToolSpec(name=tool_name, description_for_model="Read a bounded demo item.", permission="allow"),
        lambda call, spec, request, emit: CoreToolRegistry.simple_result(
            call=call, model_summary="read", structured_content={"tool": call.tool_name}
        ),
    )
    return registry


def _default_service(sessions: AgentSessionService) -> AgentMacroHostService:
    return AgentMacroHostService(
        project_checker=lambda key: key == "project-a",
        agent_session_service=sessions,
        environment_owner=DefaultMacroEnvironmentOwner(
            service=sessions,
            source_roots=SKILL_ROOTS,
        ),
    )


class SnapshotEnvironmentOwner:
    def __init__(self) -> None:
        self.revision = 0
        self.registry = _registry("system.inspect")
        self.instructions = SYSTEM_NAVIGATION_INSTRUCTIONS
        self.registries: dict[str, CoreToolRegistry] = {}

    def resolve(
        self,
        *,
        project_key: str,
        binding_id: str,
        phase: str,
        package_id: str | None = None,
        package_version: str | None = None,
    ) -> MacroEnvironment:
        del project_key, binding_id, phase, package_id, package_version
        registry = self.registry
        digest = f"system-{id(registry)}"
        environment = MacroEnvironment(
            environment_digest=digest,
            dynamic_tools=tuple({"name": spec.name} for spec in registry.list_specs()),
            skills=(),
            skill_roots=(),
            descriptor={
                "contract_version": "test.system_projection.v1",
                "status": "configured",
                "system_instructions": self.instructions,
            },
            status="configured",
        )
        self.registries[digest] = registry
        return environment

    def assemble(self, environment: MacroEnvironment, context: object) -> MacroNativeBinding:
        del context
        return MacroNativeBinding(
            native_binding=object(),
            registry=self.registries[environment.environment_digest],
            package_digest=environment.package_digest,
        )


def test_system_navigation_reaches_native_binding_and_host_responses() -> None:
    sessions = AgentSessionService(store=InMemoryAgentSessionStore())
    service = _default_service(sessions)
    resolved = resolve_macro_environment(
        sessions,
        "project-a",
        [],
        [],
        SKILL_ROOTS,
        _registry(),
    )
    assert not isinstance(resolved, Failure)
    context = TrustedHostContext("project-a", "session-1", "thread-1", "turn-1", "message-1")
    native = assemble_native_macro_binding(resolved, context, sessions)
    assert not isinstance(native, Failure)
    assert len(SYSTEM_NAVIGATION_INSTRUCTIONS) <= 600
    assert "agent_runtime.system.inspect" in native.developer_instructions
    assert "Apply the mounted skill content" in native.developer_instructions
    assert "Preserve project identity" in native.developer_instructions
    assert "package identity exactly" in native.developer_instructions
    assert native.developer_instructions.endswith(SYSTEM_NAVIGATION_INSTRUCTIONS)
    assert "mrw.sources" not in native.base_instructions
    assert resolved.descriptor()["system_instructions"] == SYSTEM_NAVIGATION_INSTRUCTIONS
    digest_payload = json.dumps(
        resolved.descriptor(), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    assert resolved.environment_digest == sha256(digest_payload).hexdigest()

    prepared = service.prepare(project_key="project-a")
    bound = service.bind(binding_id=prepared["bindingId"], thread_id="thread-1")
    admission = service.prepare_turn(thread_id="thread-1")
    environment = service.environment(binding_id=prepared["bindingId"])
    assert prepared["systemInstructions"] == SYSTEM_NAVIGATION_INSTRUCTIONS
    assert bound["systemInstructions"] == SYSTEM_NAVIGATION_INSTRUCTIONS
    assert admission["systemInstructions"] == SYSTEM_NAVIGATION_INSTRUCTIONS
    assert environment["systemInstructions"] == SYSTEM_NAVIGATION_INSTRUCTIONS
    assert environment["currentEnvironmentDigest"] == prepared["environmentDigest"]


def test_system_inspect_schema_matches_the_mounted_tool() -> None:
    sessions = AgentSessionService(store=InMemoryAgentSessionStore())
    registry = build_project_core_tool_registry(service=sessions)
    all_specs = tuple(registry.list_specs())
    inspect_spec, = (spec for spec in all_specs if spec.name == "agent_runtime.system.inspect")
    wire_specs = json.loads(json.dumps(native_tool_specs(all_specs), ensure_ascii=False))
    inspect_projection, = (
        tool
        for namespace in wire_specs
        if namespace.get("name") == "agent_runtime_system"
        for tool in namespace["tools"]
        if tool["name"] == "inspect"
    )
    assert inspect_projection == {
        "type": "function",
        "name": "inspect",
        "description": inspect_spec.description_for_model,
        "inputSchema": dict(inspect_spec.input_schema),
        "deferLoading": False,
    }

    resolved = resolve_macro_environment(
        sessions,
        "project-a",
        [],
        [],
        SKILL_ROOTS,
        registry,
    )
    assert not isinstance(resolved, Failure)
    context = TrustedHostContext("project-a", "session-1", "thread-1", "turn-1", "message-1")
    native = assemble_native_macro_binding(resolved, context, sessions)
    assert not isinstance(native, Failure)
    mounted = [
        tool for tool in native.tools
        if (tool.namespace, tool.name) == ("agent_runtime_system", "inspect")
    ]
    assert len(mounted) == 1


def test_prepare_turn_snapshot_dispatches_old_registry_then_end_turn_rejects() -> None:
    sessions = AgentSessionService(store=InMemoryAgentSessionStore())
    owner = SnapshotEnvironmentOwner()
    service = AgentMacroHostService(
        project_checker=lambda key: key == "project-a",
        agent_session_service=sessions,
        environment_owner=owner,
    )
    prepared = service.prepare(project_key="project-a")
    service.bind(binding_id=prepared["bindingId"], thread_id="thread-1")
    admission = service.prepare_turn(thread_id="thread-1")
    assert admission["systemInstructions"] == SYSTEM_NAVIGATION_INSTRUCTIONS
    assert [item["name"] for item in admission["dynamicTools"]] == ["system.inspect"]

    owner.registry = _registry("snapshot.next")
    second = service.prepare_turn(thread_id="thread-1")
    service.record_input(
        thread_id="thread-1",
        turn_id="turn-1",
        content="inspect system",
        admission_id=admission["admissionId"],
    )
    old_dispatch = service.dispatch(
        thread_id="thread-1",
        turn_id="turn-1",
        call_id="old-call",
        namespace="system",
        tool="inspect",
        arguments={},
    )
    assert old_dispatch["success"] is True, old_dispatch
    assert old_dispatch["resultProjection"]["structured_content"]["tool"] == "system.inspect"

    service.record_input(
        thread_id="thread-1",
        turn_id="turn-2",
        content="next turn",
        admission_id=second["admissionId"],
    )
    service.end_turn(thread_id="thread-1", turn_id="turn-2")
    ended = service.dispatch(
        thread_id="thread-1",
        turn_id="turn-2",
        call_id="ended-call",
        namespace="snapshot",
        tool="next",
        arguments={},
    )
    assert ended["success"] is False
    assert "turn ended" in ended["contentItems"][0]["text"]


def test_environment_snapshot_instructions_do_not_follow_later_constant_change(monkeypatch: pytest.MonkeyPatch) -> None:
    sessions = AgentSessionService(store=InMemoryAgentSessionStore())
    owner = SnapshotEnvironmentOwner()
    owner.instructions = "old system navigation"
    service = AgentMacroHostService(
        project_checker=lambda key: key == "project-a",
        agent_session_service=sessions,
        environment_owner=owner,
    )
    prepared = service.prepare(project_key="project-a")
    service.bind(binding_id=prepared["bindingId"], thread_id="thread-1")
    assert prepared["systemInstructions"] == "old system navigation"

    monkeypatch.setattr(
        macro_host_module,
        "SYSTEM_NAVIGATION_INSTRUCTIONS",
        "unrelated fallback changed",
    )
    environment = service.environment(binding_id=prepared["bindingId"])
    assert environment["systemInstructions"] == "old system navigation"

    owner.instructions = "new system navigation"
    owner.registry = _registry("snapshot.next")
    admission = service.prepare_turn(thread_id="thread-1")
    assert admission["systemInstructions"] == "new system navigation"
    assert admission["environmentDigest"] != prepared["environmentDigest"]
