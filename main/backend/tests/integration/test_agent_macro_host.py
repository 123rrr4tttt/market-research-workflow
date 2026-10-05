from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest
from functorial_kit import Failure

import app.api.agent_macro_host as host_api
import app.services.agent_core.macro_host as macro_host_module
from app.services.agent_core.contracts import AgentCoreRequest, CoreToolCall, CoreToolSpec
from app.services.agent_core.host_authorization import TrustedHostContext, authorize_tool_call
from app.services.agent_core.macro_host import (
    AgentMacroHostService,
    DefaultMacroEnvironmentOwner,
    MacroEnvironment,
    MacroHostError,
    MacroNativeBinding,
)
from app.services.agent_core.macro_registration import (
    read_registration_package,
    save_registration_package,
)
from app.services.agent_core.project_tools import build_project_core_tool_registry
from app.services.agent_core.registry import CoreToolRegistry
from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_sessions.store import InMemoryAgentSessionStore


pytestmark = pytest.mark.integration


class FakeEnvironmentOwner:
    """Controlled B-side stand-in that resolves to a fixed inert environment."""

    def __init__(self, registry: CoreToolRegistry, *, digest: str = "env-digest-v1") -> None:
        self.registry = registry
        self.digest = digest

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
        return MacroEnvironment(
            environment_digest=self.digest,
            dynamic_tools=(),
            skills=(),
            skill_roots=(),
            descriptor={"contract_version": "test.environment.v1", "status": "configured"},
            status="configured",
        )

    def assemble(self, environment: MacroEnvironment, context: object) -> MacroNativeBinding:
        del context
        return MacroNativeBinding(
            native_binding=object(),
            registry=self.registry,
            package_digest=environment.package_digest,
        )


def _make_registry(permission: str = "ask") -> CoreToolRegistry:
    registry = CoreToolRegistry()
    spec = CoreToolSpec(
        name="demo.write",
        description_for_model="Demo gated tool",
        permission=permission,
        risk="write_shared",
    )

    def handler(call, spec, request, emit):
        del spec, request, emit
        return CoreToolRegistry.simple_result(
            call=call,
            status="completed",
            model_summary="ran",
            structured_content={"reader_id": "readback-123", "artifact_id": "art-1"},
        )

    registry.register(spec, handler)
    return registry


def _make_service(
    registry: CoreToolRegistry,
    *,
    digest: str = "env-digest-v1",
) -> tuple[AgentMacroHostService, AgentSessionService, FakeEnvironmentOwner]:
    sessions = AgentSessionService(store=InMemoryAgentSessionStore())
    owner = FakeEnvironmentOwner(registry, digest=digest)
    service = AgentMacroHostService(
        project_checker=lambda key: key == "project-a",
        agent_session_service=sessions,
        environment_owner=owner,
    )
    return service, sessions, owner


def test_prepare_is_non_session_and_bind_creates_session() -> None:
    service, sessions, _ = _make_service(_make_registry())

    prepared = service.prepare(project_key="project-a")
    assert prepared["status"] == "prepared"
    assert prepared["bindingId"]
    assert prepared["sessionId"] is None
    assert prepared["threadId"] is None
    assert "environmentDigest" in prepared
    assert "dynamicTools" in prepared
    assert "skills" in prepared

    bound = service.bind(binding_id=prepared["bindingId"], thread_id="thread-1")
    assert bound["status"] == "bound"
    assert bound["threadId"] == "thread-1"
    assert bound["sessionId"]
    assert len(sessions.list_sessions(limit=10)) == 1


def test_prepare_rejects_unavailable_project() -> None:
    service, _, _ = _make_service(_make_registry())
    with pytest.raises(MacroHostError) as exc:
        service.prepare(project_key="missing-project")
    assert exc.value.code == "project_not_found"
    assert exc.value.status_code == 404


def test_bind_detects_environment_stale() -> None:
    service, _, owner = _make_service(_make_registry(), digest="env-digest-v1")
    prepared = service.prepare(project_key="project-a")
    owner.digest = "env-digest-v2"
    with pytest.raises(MacroHostError) as exc:
        service.bind(binding_id=prepared["bindingId"], thread_id="thread-1")
    assert exc.value.code == "environment_stale"
    assert exc.value.status_code == 409


def test_dispatch_confirm_redispatch_completes() -> None:
    service, sessions, _ = _make_service(_make_registry("ask"))
    binding_id = service.prepare(project_key="project-a")["bindingId"]
    bound = service.bind(binding_id=binding_id, thread_id="thread-1")
    session_id = bound["sessionId"]
    service.record_input(thread_id="thread-1", turn_id="turn-1", content="please write")

    first = service.dispatch(
        thread_id="thread-1",
        turn_id="turn-1",
        call_id="call-1",
        namespace="demo",
        tool="write",
        arguments={"target": "a"},
    )
    assert first["success"] is False
    assert first["pendingAction"] is not None
    action_id = first["pendingAction"]["actionId"]
    assert action_id
    assert first["pendingAction"]["toolName"] == "demo.write"
    assert first["pendingAction"]["projectKey"] == "project-a"

    confirmed = service.confirm(
        thread_id="thread-1",
        turn_id="turn-1",
        action_id=action_id,
        approved=True,
    )
    assert confirmed["confirmed"] is True
    assert confirmed["approved"] is True

    second = service.dispatch(
        thread_id="thread-1",
        turn_id="turn-1",
        call_id="call-1",
        namespace="demo",
        tool="write",
        arguments={"target": "a"},
    )
    assert second["success"] is True
    assert second["pendingAction"] is None
    content_text = second["contentItems"][0]["text"]
    assert "readback-123" in content_text
    assert "structured_content" in content_text
    dispatched = [
        event
        for event in sessions.list_events(session_id)
        if event.get("event_type") == "macro_host.tool.dispatched"
    ]
    assert any(
        isinstance(event.get("payload"), dict)
        and event["payload"].get("status") == "completed"
        and event["payload"].get("tool") == "demo.write"
        for event in dispatched
    )


def test_confirm_reject_blocks_redispatch() -> None:
    service, _, _ = _make_service(_make_registry("ask"))
    binding_id = service.prepare(project_key="project-a")["bindingId"]
    service.bind(binding_id=binding_id, thread_id="thread-1")
    service.record_input(thread_id="thread-1", turn_id="turn-1", content="go")

    first = service.dispatch(
        thread_id="thread-1",
        turn_id="turn-1",
        call_id="call-1",
        namespace="demo",
        tool="write",
        arguments={"target": "a"},
    )
    action_id = first["pendingAction"]["actionId"]

    rejected = service.confirm(
        thread_id="thread-1",
        turn_id="turn-1",
        action_id=action_id,
        approved=False,
    )
    assert rejected["confirmed"] is True
    assert rejected["approved"] is False

    second = service.dispatch(
        thread_id="thread-1",
        turn_id="turn-1",
        call_id="call-1",
        namespace="demo",
        tool="write",
        arguments={"target": "a"},
    )
    assert second["success"] is False
    assert second["pendingAction"] is None


def test_environment_read_reports_stale() -> None:
    service, _, owner = _make_service(_make_registry(), digest="env-digest-v1")
    binding_id = service.prepare(project_key="project-a")["bindingId"]
    service.bind(binding_id=binding_id, thread_id="thread-1")
    owner.digest = "env-digest-v2"

    read = service.environment(thread_id="thread-1")
    assert read["environmentStale"] is True
    assert read["status"] == "environment_stale"


def test_server_api_key_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(host_api, "_configured_server_key", lambda: "secret")
    host_api.require_webui_server(request=None, x_mrw_server_api_key="secret")

    with pytest.raises(MacroHostError) as exc:
        host_api.require_webui_server(request=None, x_mrw_server_api_key="wrong")
    assert exc.value.code == "invalid_server_api_key"

    monkeypatch.setattr(host_api, "_configured_server_key", lambda: "")
    with pytest.raises(MacroHostError) as exc:
        host_api.require_webui_server(request=None, x_mrw_server_api_key="secret")
    assert exc.value.code == "server_api_key_unconfigured"
    assert exc.value.status_code == 503


def test_project_exists_binds_public_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    from contextlib import contextmanager

    bound: list[str] = []

    class FakeSession:
        def __enter__(self) -> "FakeSession":
            return self

        def __exit__(self, *args: object) -> bool:
            return False

        def execute(self, _statement: object) -> SimpleNamespace:
            return SimpleNamespace(scalar_one_or_none=lambda: object())

    def fake_session_local() -> FakeSession:
        return FakeSession()

    @contextmanager
    def fake_bind_schema(schema_name: str):
        bound.append(schema_name)
        yield

    monkeypatch.setattr(host_api, "SessionLocal", fake_session_local)
    monkeypatch.setattr(host_api, "bind_schema", fake_bind_schema)

    assert host_api._project_exists("project-a") is True
    assert bound == ["public"]


def _base_resolved() -> SimpleNamespace:
    return SimpleNamespace(
        environment_digest="base-digest",
        package=None,
        skills=(),
        registry=SimpleNamespace(list_specs=lambda: []),
        descriptor=lambda: {
            "contract_version": "agent_macro.environment.resolved.v1",
            "project_key": "project-a",
            "package": None,
            "skills": [],
            "tools": [],
            "declared_tool_names": [],
            "facilities": [],
        },
    )


def test_default_owner_resolves_base_with_empty_package_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, list[str]] = {}

    def fake_resolve(service, project, ids, versions, roots, registry, facility_catalog=None):
        del service, project, roots, registry, facility_catalog
        calls["ids"] = list(ids)
        calls["versions"] = list(versions)
        return _base_resolved()

    monkeypatch.setattr(macro_host_module, "resolve_macro_environment", fake_resolve)
    monkeypatch.setattr(
        macro_host_module,
        "build_project_core_tool_registry",
        lambda *, service: SimpleNamespace(),
    )
    monkeypatch.setattr(
        macro_host_module,
        "select_active_macro_identity",
        lambda service, project_key, package_id=None, package_version=None: ((), ()),
    )

    owner = macro_host_module.DefaultMacroEnvironmentOwner(service=object(), source_roots=())
    env = owner.resolve(project_key="project-a", binding_id="b", phase="prepare")

    assert calls == {"ids": [], "versions": []}
    assert env.skills == ()
    assert env.package_digest is None
    assert env.status == "configured"
    assert env.resolved is not None


def test_default_owner_resolves_explicit_package(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, list[str]] = {}

    def fake_resolve(service, project, ids, versions, roots, registry, facility_catalog=None):
        del service, project, roots, registry, facility_catalog
        calls["ids"] = list(ids)
        calls["versions"] = list(versions)
        return _base_resolved()

    monkeypatch.setattr(macro_host_module, "resolve_macro_environment", fake_resolve)
    monkeypatch.setattr(
        macro_host_module,
        "build_project_core_tool_registry",
        lambda *, service: SimpleNamespace(),
    )
    monkeypatch.setattr(
        macro_host_module,
        "select_active_macro_identity",
        lambda service, project_key, package_id=None, package_version=None: (
            (package_id,),
            (package_version,),
        ),
    )

    owner = macro_host_module.DefaultMacroEnvironmentOwner(service=object(), source_roots=())
    owner.resolve(project_key="project-a", binding_id="b", phase="prepare", package_id="pkg", package_version="v1")

    assert calls == {"ids": ["pkg"], "versions": ["v1"]}


def test_dispatch_cache_reads_final_result_without_reexecuting() -> None:
    registry = CoreToolRegistry()
    spec = CoreToolSpec(
        name="demo.write",
        description_for_model="demo",
        permission="allow",
        risk="write_shared",
    )
    calls: list[object] = []

    def handler(call, spec, request, emit):
        del spec, request, emit
        calls.append(call)
        return CoreToolRegistry.simple_result(
            call=call,
            status="completed",
            model_summary="ran",
            structured_content={"reader_id": f"read-{len(calls)}"},
        )

    registry.register(spec, handler)
    service, _, _ = _make_service(registry)
    binding_id = service.prepare(project_key="project-a")["bindingId"]
    service.bind(binding_id=binding_id, thread_id="thread-1")
    service.record_input(thread_id="thread-1", turn_id="turn-1", content="go")

    first = service.dispatch(
        thread_id="thread-1",
        turn_id="turn-1",
        call_id="call-1",
        namespace="demo",
        tool="write",
        arguments={"target": "a"},
    )
    second = service.dispatch(
        thread_id="thread-1",
        turn_id="turn-1",
        call_id="call-1",
        namespace="demo",
        tool="write",
        arguments={"target": "a"},
    )

    assert len(calls) == 1
    assert second["resultProjection"] == first["resultProjection"]
    assert "read-1" in second["contentItems"][0]["text"]

    changed = service.dispatch(
        thread_id="thread-1",
        turn_id="turn-1",
        call_id="call-1",
        namespace="demo",
        tool="write",
        arguments={"target": "different"},
    )
    assert changed["success"] is False
    assert "changed" in changed["contentItems"][0]["text"]
    assert len(calls) == 1


def test_end_turn_rejects_dispatch_and_confirm() -> None:
    service, _, _ = _make_service(_make_registry("ask"))
    binding_id = service.prepare(project_key="project-a")["bindingId"]
    service.bind(binding_id=binding_id, thread_id="thread-1")
    service.record_input(thread_id="thread-1", turn_id="turn-1", content="go")
    first = service.dispatch(
        thread_id="thread-1",
        turn_id="turn-1",
        call_id="call-1",
        namespace="demo",
        tool="write",
        arguments={"target": "a"},
    )
    action_id = first["pendingAction"]["actionId"]

    service.end_turn(thread_id="thread-1", turn_id="turn-1")

    after_end = service.dispatch(
        thread_id="thread-1",
        turn_id="turn-1",
        call_id="call-1",
        namespace="demo",
        tool="write",
        arguments={"target": "a"},
    )
    assert after_end["success"] is False
    assert "ended" in after_end["contentItems"][0]["text"]

    with pytest.raises(MacroHostError) as exc:
        service.confirm(
            thread_id="thread-1",
            turn_id="turn-1",
            action_id=action_id,
            approved=True,
        )
    assert exc.value.code == "turn_ended"


def test_binding_memory_miss_raises_rebind_required() -> None:
    sessions = AgentSessionService(store=InMemoryAgentSessionStore())
    sessions.create_session(
        source="codex_webui_host",
        entrypoint_type="codex_native_thread",
        project_key="project-a",
        goal="demo",
        metadata={"native_thread_id": "thread-1"},
    )
    service = AgentMacroHostService(
        project_checker=lambda key: key == "project-a",
        agent_session_service=sessions,
        environment_owner=FakeEnvironmentOwner(CoreToolRegistry()),
    )

    with pytest.raises(MacroHostError) as exc:
        service.environment(thread_id="thread-1")
    assert exc.value.code == "rebind_required"
    assert exc.value.status_code == 409


def _real_package(*, package_id: str = "agent.macro.pilot", version: str = "1") -> dict:
    skill_name = "agent-macro-pilot"
    tool_name = "skill.project_retrieval.read_run"
    skill_path = (
        Path(__file__).resolve().parents[2] / "skills" / skill_name / "SKILL.md"
    )
    return {
        "contract_version": "agent_macro.registration_package.v1",
        "package_id": package_id,
        "package_version": version,
        "owner": "macro.host.integration",
        "cell": {
            "cell_id": "agent.macro.pilot.cell",
            "core_binding_ref": "agent-macro-pilot.v1",
            "core_mode": "native-agent",
            "conceptual_rule_refs": ["agent_macro_architecture.section.2"],
            "tool_refs": [tool_name],
            "facility_refs": ["facility.project_retrieval.current"],
            "readback_refs": ["facility.project_retrieval.current"],
        },
        "skill_contents": [{
            "skill_id": skill_name,
            "source_ref": f"{skill_name}/SKILL.md",
            "content_id": f"sha256:{sha256(skill_path.read_bytes()).hexdigest()}",
            "applicability_ref": f"{skill_name}#applicability",
            "outcome_ref": f"{skill_name}#outcome",
            "tool_refs": [tool_name],
        }],
        "relations": [
            {
                "relation_id": "current-binding",
                "source_ref": "core",
                "target_ref": "project_retrieval.binding",
                "observation_boundary": "service",
                "realization": "real",
                "implementation_ref": "facility.project_retrieval.current",
                "authority_ref": "ProjectRetrievalService.current read boundary",
                "failure_refs": ["project_retrieval.failure"],
                "readback_refs": ["facility.project_retrieval.current"],
            },
        ],
    }


def _save_candidate(service: AgentSessionService, package: dict) -> str:
    bundle = service.create_session(
        source="codex_webui_host",
        entrypoint_type="codex_native_thread",
        project_key="project-a",
        goal="activate package",
    )
    session_id = bundle["session"]["session_id"]
    saved = save_registration_package(
        service,
        session_id=session_id,
        project_key="project-a",
        payload=package,
    )
    assert not isinstance(saved, Failure)
    return session_id


def _build_host_service(sessions: AgentSessionService) -> AgentMacroHostService:
    owner = DefaultMacroEnvironmentOwner(
        service=sessions,
        source_roots=(Path(__file__).resolve().parents[2] / "skills",),
    )
    return AgentMacroHostService(
        project_checker=lambda key: key == "project-a",
        agent_session_service=sessions,
        environment_owner=owner,
    )


def _activate_arguments(package: dict) -> dict:
    return {
        "package_id": package["package_id"],
        "package_version": package["package_version"],
    }


def test_real_activation_from_base_candidate() -> None:
    sessions = AgentSessionService(store=InMemoryAgentSessionStore())
    package = _real_package()
    session_id = _save_candidate(sessions, package)
    service = _build_host_service(sessions)

    prepared = service.prepare(project_key="project-a")
    assert prepared["packageId"] is None

    bound = service.bind(binding_id=prepared["bindingId"], thread_id="thread-1")
    assert bound["sessionId"]
    service.record_input(thread_id="thread-1", turn_id="turn-1", content="activate")

    first = service.dispatch(
        thread_id="thread-1",
        turn_id="turn-1",
        call_id="call-1",
        namespace="agent_macro_registration_package",
        tool="activate",
        arguments=_activate_arguments(package),
    )
    assert first["success"] is True
    assert first["pendingAction"] is None

    read = read_registration_package(
        sessions,
        session_id=session_id,
        project_key="project-a",
        package_id=package["package_id"],
        package_version=package["package_version"],
    )
    assert not isinstance(read, Failure)
    assert read["activation"]["status"] == "activated"
    assert read["activation"]["authorization_source"] == "host_policy"


def test_activated_package_change_is_rejected() -> None:
    sessions = AgentSessionService(store=InMemoryAgentSessionStore())
    package = _real_package()
    session_id = _save_candidate(sessions, package)
    service = _build_host_service(sessions)

    prepared = service.prepare(project_key="project-a")
    service.bind(binding_id=prepared["bindingId"], thread_id="thread-1")
    service.record_input(thread_id="thread-1", turn_id="turn-1", content="activate")

    first = service.dispatch(
        thread_id="thread-1",
        turn_id="turn-1",
        call_id="call-1",
        namespace="agent_macro_registration_package",
        tool="activate",
        arguments=_activate_arguments(package),
    )
    assert first["success"] is True
    assert first["pendingAction"] is None

    changed = _real_package()
    changed["owner"] = "macro.host.integration.changed"
    conflict = save_registration_package(
        sessions,
        session_id=session_id,
        project_key="project-a",
        payload=changed,
    )
    assert isinstance(conflict, Failure)
    assert conflict.context["registration_code"] == "macro_registration_activation_conflict"

    read = read_registration_package(
        sessions,
        session_id=session_id,
        project_key="project-a",
        package_id=package["package_id"],
        package_version=package["package_version"],
    )
    assert not isinstance(read, Failure)
    assert read["activation"]["status"] == "activated"


def test_real_create_activate_first_call_chain() -> None:
    sessions = AgentSessionService(store=InMemoryAgentSessionStore())
    package = _real_package()
    service = _build_host_service(sessions)

    prepared = service.prepare(project_key="project-a")
    bound = service.bind(binding_id=prepared["bindingId"], thread_id="thread-1")
    session_id = bound["sessionId"]
    service.record_input(thread_id="thread-1", turn_id="turn-1", content="create and activate")

    created = service.dispatch(
        thread_id="thread-1",
        turn_id="turn-1",
        call_id="create-1",
        namespace="agent_macro_registration_package",
        tool="create",
        arguments={"package": package},
    )
    assert created["success"] is True
    assert created["pendingAction"] is None

    activated = service.dispatch(
        thread_id="thread-1",
        turn_id="turn-1",
        call_id="activate-1",
        namespace="agent_macro_registration_package",
        tool="activate",
        arguments=_activate_arguments(package),
    )
    assert activated["success"] is True
    assert activated["pendingAction"] is None

    assert sessions.list_approvals(session_id=session_id) == []
    messages = sessions.list_messages(session_id)
    assert all(not dict(message.get("metadata") or {}).get("host_confirmation") for message in messages)

    read = read_registration_package(
        sessions,
        session_id=session_id,
        project_key="project-a",
        package_id=package["package_id"],
        package_version=package["package_version"],
    )
    assert not isinstance(read, Failure)
    assert read["activation"]["status"] == "activated"
    assert read["activation"]["authorization_source"] == "host_policy"


def test_activate_dispatch_cache_and_idempotency() -> None:
    sessions = AgentSessionService(store=InMemoryAgentSessionStore())
    package = _real_package()
    service = _build_host_service(sessions)

    prepared = service.prepare(project_key="project-a")
    service.bind(binding_id=prepared["bindingId"], thread_id="thread-1")
    service.record_input(thread_id="thread-1", turn_id="turn-1", content="go")

    created = service.dispatch(
        thread_id="thread-1",
        turn_id="turn-1",
        call_id="create-1",
        namespace="agent_macro_registration_package",
        tool="create",
        arguments={"package": package},
    )
    assert created["success"] is True

    activated = service.dispatch(
        thread_id="thread-1",
        turn_id="turn-1",
        call_id="activate-1",
        namespace="agent_macro_registration_package",
        tool="activate",
        arguments=_activate_arguments(package),
    )
    assert activated["success"] is True

    cached = service.dispatch(
        thread_id="thread-1",
        turn_id="turn-1",
        call_id="activate-1",
        namespace="agent_macro_registration_package",
        tool="activate",
        arguments=_activate_arguments(package),
    )
    assert cached["success"] is True
    assert cached.get("resultProjection") == activated.get("resultProjection")

    again = service.dispatch(
        thread_id="thread-1",
        turn_id="turn-1",
        call_id="activate-2",
        namespace="agent_macro_registration_package",
        tool="activate",
        arguments=_activate_arguments(package),
    )
    assert again["success"] is True
    assert again["pendingAction"] is None


def test_authorization_bound_to_old_digest_rejects_after_candidate_change() -> None:
    sessions = AgentSessionService(store=InMemoryAgentSessionStore())
    package = _real_package()
    session_id = _save_candidate(sessions, package)

    registry = build_project_core_tool_registry(service=sessions)
    activate_spec = registry.get("agent_macro.registration_package.activate")
    assert activate_spec is not None

    read = read_registration_package(
        sessions,
        session_id=session_id,
        project_key="project-a",
        package_id=package["package_id"],
        package_version=package["package_version"],
    )
    assert not isinstance(read, Failure)
    old_digest = read["package"]["content_digest"]

    context = TrustedHostContext("project-a", session_id, "thread-1", "turn-1", "request-message")
    sessions.create_host_user_message(context, content="activate")

    decision = authorize_tool_call(
        sessions,
        context,
        activate_spec,
        {"package_id": package["package_id"], "package_version": package["package_version"]},
        package_digest=old_digest,
        originating_call_id="call-1",
    )
    assert not isinstance(decision, Failure)
    assert decision.status == "authorized"

    changed = _real_package()
    changed["owner"] = "macro.host.integration.changed"
    saved = save_registration_package(
        sessions,
        session_id=session_id,
        project_key="project-a",
        payload=changed,
    )
    assert not isinstance(saved, Failure)

    result = registry.execute_tool(
        tool_call=CoreToolCall(
            call_id="call-1",
            tool_name="agent_macro.registration_package.activate",
            arguments={"package_id": package["package_id"], "package_version": package["package_version"]},
            reason="test",
        ),
        tool_spec=activate_spec,
        request=AgentCoreRequest(message="", session_id=session_id, project_key="project-a", turn_id="turn-1"),
        emit=lambda _: None,
        trusted_context=context,
        host_authorization=decision.authorization,
        package_digest=old_digest,
    )
    assert result.status == "failed"


def test_record_input_rejects_stale_environment() -> None:
    service, _, owner = _make_service(_make_registry("allow"), digest="env-digest-v1")
    binding_id = service.prepare(project_key="project-a")["bindingId"]
    service.bind(binding_id=binding_id, thread_id="thread-1")
    owner.digest = "env-digest-v2"

    with pytest.raises(MacroHostError) as exc:
        service.record_input(thread_id="thread-1", turn_id="turn-1", content="hello")
    assert exc.value.code == "environment_stale"
    assert exc.value.status_code == 409


def test_slow_handler_does_not_block_other_thread_end_turn() -> None:
    import threading

    registry = CoreToolRegistry()
    spec = CoreToolSpec(
        name="demo.write",
        description_for_model="demo",
        permission="allow",
        risk="write_shared",
    )
    started = threading.Event()
    release = threading.Event()

    def handler(call, spec, request, emit):
        del spec, request, emit
        started.set()
        release.wait(timeout=5)
        return CoreToolRegistry.simple_result(call=call, status="completed", model_summary="done")

    registry.register(spec, handler)
    service, _, _ = _make_service(registry)
    b1 = service.prepare(project_key="project-a")["bindingId"]
    service.bind(binding_id=b1, thread_id="thread-1")
    service.record_input(thread_id="thread-1", turn_id="turn-1", content="go")
    b2 = service.prepare(project_key="project-a")["bindingId"]
    service.bind(binding_id=b2, thread_id="thread-2")
    service.record_input(thread_id="thread-2", turn_id="turn-2", content="go")

    results: dict[str, object] = {}

    def run_dispatch() -> None:
        results["dispatch"] = service.dispatch(
            thread_id="thread-1",
            turn_id="turn-1",
            call_id="c1",
            namespace="demo",
            tool="write",
            arguments={"target": "a"},
        )

    thread = threading.Thread(target=run_dispatch)
    thread.start()
    assert started.wait(timeout=5)

    ended = service.end_turn(thread_id="thread-2", turn_id="turn-2")
    assert ended["ended"] is True

    release.set()
    thread.join(timeout=5)
    assert results["dispatch"]["success"] is True


def test_same_call_concurrent_executes_once() -> None:
    import threading

    registry = CoreToolRegistry()
    spec = CoreToolSpec(
        name="demo.write",
        description_for_model="demo",
        permission="allow",
        risk="write_shared",
    )
    calls: list[str] = []
    lock = threading.Lock()

    def handler(call, spec, request, emit):
        del spec, request, emit
        with lock:
            calls.append(call.call_id)
        return CoreToolRegistry.simple_result(call=call, status="completed", model_summary="done")

    registry.register(spec, handler)
    service, _, _ = _make_service(registry)
    binding_id = service.prepare(project_key="project-a")["bindingId"]
    service.bind(binding_id=binding_id, thread_id="thread-1")
    service.record_input(thread_id="thread-1", turn_id="turn-1", content="go")

    results: list[object] = []

    def run() -> None:
        results.append(
            service.dispatch(
                thread_id="thread-1",
                turn_id="turn-1",
                call_id="c1",
                namespace="demo",
                tool="write",
                arguments={"target": "a"},
            )
        )

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert len(calls) == 1
    assert len(results) == 2


def test_prepare_http_explicit_id_version() -> None:
    from app.api.agent_macro_host import (
        PrepareRequest,
        configure_agent_macro_host_service,
        prepare_macro_host,
    )

    calls: dict[str, str] = {}

    class FakeService:
        def prepare(self, **kwargs: str) -> dict:
            calls.update(kwargs)
            return {"bindingId": "b1"}

    configure_agent_macro_host_service(FakeService())
    try:
        prepare_macro_host(
            PrepareRequest(projectKey="project-a", packageId="pkg", packageVersion="v1")
        )
    finally:
        configure_agent_macro_host_service(None)

    assert calls == {
        "project_key": "project-a",
        "package_id": "pkg",
        "package_version": "v1",
    }
