from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from functorial_kit import Failure

from app.services.agent_core.contracts import CoreToolCall, CoreToolResult, CoreToolSpec
from app.services.agent_core.host_authorization import (
    TrustedHostContext,
    VerifiedHostAuthorization,
    canonical_arguments_sha256,
    current_verified_host_authorization,
)
from app.services.agent_core.macro_environment import (
    RESOLVED_MACRO_ENVIRONMENT_CONTRACT_VERSION,
    assemble_native_macro_binding,
    native_tool_specs,
    resolve_macro_environment,
    resolve_tool_package_digest,
    select_active_macro_identity,
)
from app.services.agent_core.macro_registration import (
    CONTRACT_VERSION,
    activate_registration_package,
    read_registration_package,
    save_registration_package,
)
from app.services.agent_core.project_tools import get_agent_macro_facility_catalog
from app.services.agent_core.registry import CoreToolRegistry
from app.services.projects.context import bind_project
from app.services.request_identity import RequestActorContext


pytestmark = pytest.mark.unit


class Store:
    def __init__(self, project_key: str = "trusted_project") -> None:
        self.project_items: dict[tuple[str, str], dict[str, Any]] = {}
        self.project_key = project_key

    def upsert_project_artifact(self, payload):
        key = (payload["project_key"], payload["name"])
        self.project_items[key] = dict(payload)
        return dict(payload)

    def upsert_artifact(self, payload):
        return dict(payload)

    def get_project_artifact(self, *, project_key, name):
        return self.project_items.get((project_key, name))

    def list_project_artifacts(self, *, project_key):
        return [dict(item) for item in self.project_items.values() if item["project_key"] == project_key]

    def list_artifacts(self, session_id):
        return []

    def get_session(self, session_id):
        return {"session_id": session_id, "project_key": self.project_key}


class Service:
    def __init__(self, project_key: str = "trusted_project") -> None:
        self.store = Store()
        self.project_key = project_key

    def list_messages(self, session_id):
        return [{
            "role": "user",
            "actor": "trusted_host:host-thread-1",
            "metadata": {
                "host_message": {
                    "user_message_id": "message-1",
                    "host_thread_id": "host-thread-1",
                    "turn_id": "turn-1",
                }
            },
        }]

    def list_approvals(self, *, session_id=None):
        return []


class RetrievalService:
    def current(self, project_key):
        assert project_key == "trusted_project"
        return {"mode_id": "water", "version": "1"}


def _content_id(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _package(
    *,
    package_id="agent.macro.pilot",
    version="1",
    skill_name="agent-macro-pilot",
    tool_name="skill.project_retrieval.read_run",
    cell_id="agent.macro.pilot.cell",
    binding_id="agent-macro-pilot.v1",
) -> dict:
    skill_path = Path(__file__).resolve().parents[2] / "skills" / skill_name / "SKILL.md"
    return {
        "contract_version": CONTRACT_VERSION,
        "package_id": package_id,
        "package_version": version,
        "owner": "macro.environment.test",
        "cell": {
            "cell_id": cell_id,
            "core_binding_ref": binding_id,
            "core_mode": "native-agent",
            "conceptual_rule_refs": ["agent_macro_architecture.section.2"],
            "tool_refs": [tool_name],
            "facility_refs": ["facility.project_retrieval.current"],
            "readback_refs": ["facility.project_retrieval.current"],
        },
        "skill_contents": [{
            "skill_id": skill_name,
            "source_ref": f"{skill_name}/SKILL.md",
            "content_id": _content_id(skill_path),
            "applicability_ref": f"{skill_name}#applicability",
            "outcome_ref": f"{skill_name}#outcome",
            "tool_refs": [tool_name],
        }],
        "relations": [
            {
                "relation_id": "read-run",
                "source_ref": "core",
                "target_ref": "project_retrieval.run",
                "observation_boundary": "macro",
                "realization": "virtual",
                "implementation_ref": tool_name,
                "authority_ref": "host_authorization",
                "failure_refs": ["project_retrieval.failure"],
                "readback_refs": ["facility.project_retrieval.current"],
            },
            {
                "relation_id": "current-binding",
                "source_ref": "core",
                "target_ref": "project_retrieval.binding",
                "observation_boundary": "service",
                "realization": "real",
                "implementation_ref": "project_retrieval.current",
                "authority_ref": "ProjectRetrievalService.current read boundary",
                "failure_refs": ["project_retrieval.failure"],
                "readback_refs": ["facility.project_retrieval.current"],
            },
        ],
    }


def _activate(service, package, *, session_id="session-1") -> None:
    saved = save_registration_package(service, session_id=session_id, project_key="trusted_project", payload=package)
    assert not isinstance(saved, Failure)
    arguments = {"package_id": package["package_id"], "package_version": package["package_version"]}
    digest = canonical_arguments_sha256(arguments)
    assert not isinstance(digest, Failure)
    context = TrustedHostContext("trusted_project", session_id, "host-thread-1", "turn-1", "message-1")
    result = activate_registration_package(
        service,
        session_id=session_id,
        project_key="trusted_project",
        package_id=package["package_id"],
        package_version=package["package_version"],
        host_authorization=VerifiedHostAuthorization(
            context,
            "agent_macro.registration_package.activate",
            digest,
            saved["package"]["content_digest"],
            "ask",
            "approval-1",
            "origin-call-1",
            "turn-1",
            "origin-message-1",
        ),
    )
    assert not isinstance(result, Failure)


def _catalog(service):
    return get_agent_macro_facility_catalog(service)


def _registry(tool_name="skill.project_retrieval.read_run") -> CoreToolRegistry:
    registry = CoreToolRegistry()
    registry.register(
        CoreToolSpec(name="base.read", description_for_model="Preserve an ordinary base capability."),
        lambda call, spec, request, emit: CoreToolResult(
            call.call_id, call.tool_name, "completed", "base capability remains mounted"
        ),
    )

    def read_run(call, spec, request, emit):
        from app.services.project_retrieval import skill

        authorization = current_verified_host_authorization()
        if authorization is None or authorization.actor_context is None:
            raise RuntimeError("macro read_run requires verified host actor context")
        with bind_project(request.project_key):
            value = skill.read_run(
                call.arguments,
                invocation_context={"actor_context": authorization.actor_context},
            )
        return CoreToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status="completed",
            model_summary="Read persisted project retrieval run.",
            structured_content=dict(value),
        )

    registry.register(
        CoreToolSpec(
            name=tool_name,
            description_for_model="Read one persisted project retrieval run.",
            input_schema={"type": "object", "required": ["run_id"], "properties": {"run_id": {"type": "string"}}},
            project_service_id=tool_name,
        ),
        read_run,
    )
    return registry


def _resolve(service, registry, package=None, project="trusted_project"):
    package = package or _package()
    _activate(service, package)
    return resolve_macro_environment(
        service,
        project,
        (package["package_id"],),
        (package["package_version"],),
        (Path(__file__).resolve().parents[2] / "skills",),
        registry,
        _catalog(service),
    )


def _resolve_with_activation(service, registry, package, **activation_fields):
    name = f"macro-registration/{package['package_id']}@{package['package_version']}.json"
    saved = save_registration_package(service, session_id="session-1", project_key="trusted_project", payload=package)
    assert not isinstance(saved, Failure)
    digest = saved["package"]["content_digest"]
    activation = {
        "status": "activated",
        "authority": "host_authorization",
        "scope": {"project_key": "trusted_project", "scope_type": "project"},
        "content_digest": digest,
        **activation_fields,
    }
    item = service.store.project_items[("trusted_project", name)]
    item["content_json"]["activation"] = activation
    item["metadata"]["activation_status"] = "activated"
    item["metadata"]["content_digest"] = digest
    return resolve_macro_environment(
        service, "trusted_project", (package["package_id"],), (package["package_version"],),
        (Path(__file__).resolve().parents[2] / "skills",), registry, _catalog(service),
    )


def test_real_pilot_environment_preserves_base_and_project_reader() -> None:
    service = Service()
    registry = _registry()
    resolved = _resolve(service, registry)
    assert not isinstance(resolved, Failure)
    assert resolved.descriptor()["contract_version"] == RESOLVED_MACRO_ENVIRONMENT_CONTRACT_VERSION
    assert resolved.descriptor()["declared_tool_names"] == ["skill.project_retrieval.read_run"]
    assert [spec.name for spec in resolved.tools] == ["base.read", "skill.project_retrieval.read_run"]
    assert resolved.skills[0].native.name == "agent-macro-pilot"
    assert resolved.skills[0].authored.content_id == f"sha256:{resolved.skills[0].native.content_digest}"

    actor_context = RequestActorContext(
        actor_id="trusted-project-reader",
        actor_source="authenticated_session",
        actor_trusted=True,
        actor_auth_mode="session",
    )
    context = TrustedHostContext(
        "trusted_project", "session-1", "host-thread-1", "turn-1", "message-1",
        actor_context=actor_context,
    )
    binding = assemble_native_macro_binding(resolved, context, service)
    assert not isinstance(binding, Failure)
    assert binding.binding_id == "agent-macro-pilot.v1"
    assert binding.skill_roots == (str(Path(resolved.skills[0].native.path).parent.parent),)
    assert {tool.logical_name for tool in binding.tools} == {
        "base.read", "skill_project_retrieval.read_run",
    }
    reader = next(tool for tool in binding.tools if tool.logical_name == "skill_project_retrieval.read_run")

    from app.services.project_retrieval.service import ProjectRetrievalService
    observed = {}

    def read_run(self, project_key, run_id, *, actor_id):
        observed.update(project_key=project_key, run_id=run_id, actor_id=actor_id)
        return {"run_id": run_id, "status": "queued", "receipt": {}}

    original = ProjectRetrievalService.read_run
    ProjectRetrievalService.read_run = read_run
    try:
        result = reader.handler({"run_id": "run-7"})
    finally:
        ProjectRetrievalService.read_run = original
    assert observed == {
        "project_key": "trusted_project",
        "run_id": "run-7",
        "actor_id": "trusted-project-reader",
    }
    assert result["status"] == "completed"
    assert result["structured_content"]["run_id"] == "run-7"


def test_nondefault_rapid_environment_is_not_a_singleton() -> None:
    service = Service()
    registry = _registry("source.web.search")
    package = _package(
        package_id="agent.macro.rapid",
        skill_name="agent-macro-rapid",
        tool_name="source.web.search",
        cell_id="agent.macro.rapid.cell",
        binding_id="agent-macro-rapid.v1",
    )
    resolved = _resolve(service, registry, package)
    assert not isinstance(resolved, Failure)
    assert resolved.definition.cell_id == "agent.macro.rapid.cell"
    assert resolved.skills[0].native.name == "agent-macro-rapid"
    context = TrustedHostContext("trusted_project", "session-1", "host-thread-1", "turn-1", "message-1")
    binding = assemble_native_macro_binding(resolved, context, service)
    assert not isinstance(binding, Failure)
    assert binding.binding_id == "agent-macro-rapid.v1"
    pilot = _resolve(Service(), _registry())
    assert binding.environment_digest != pilot.environment_digest


def test_resolver_rejects_wrong_project_candidate_and_legacy_activation() -> None:
    service = Service()
    registry = _registry()
    wrong = resolve_macro_environment(
        service, "other_project", ("agent.macro.pilot",), ("1",),
        (Path(__file__).resolve().parents[2] / "skills",), registry, _catalog(service),
    )
    assert isinstance(wrong, Failure)

    package = _package()
    saved = save_registration_package(service, session_id="session-1", project_key="trusted_project", payload=package)
    assert not isinstance(saved, Failure)
    candidate = resolve_macro_environment(
        service, "trusted_project", ("agent.macro.pilot",), ("1",),
        (Path(__file__).resolve().parents[2] / "skills",), registry, _catalog(service),
    )
    assert isinstance(candidate, Failure)

    name = f"macro-registration/{package['package_id']}@{package['package_version']}.json"
    legacy = {**package}
    legacy.pop("content_digest", None)
    legacy["activation"] = {"status": "activated", "authority": "agentcore_user_consent"}
    service.store.project_items[("trusted_project", name)] = {
        "project_key": "trusted_project",
        "name": name,
        "artifact_type": "agent_macro.registration_package",
        "content_json": legacy,
        "metadata": {"project_key": "trusted_project"},
    }
    result = read_registration_package(
        service, session_id="session-1", project_key="trusted_project",
        package_id=package["package_id"], package_version=package["package_version"],
    )
    assert not isinstance(result, Failure) and result["legacy"] is True
    legacy_resolve = resolve_macro_environment(
        service, "trusted_project", ("agent.macro.pilot",), ("1",),
        (Path(__file__).resolve().parents[2] / "skills",), registry, _catalog(service),
    )
    assert isinstance(legacy_resolve, Failure)


def test_missing_version_lists_active_versions_without_timestamp_selection() -> None:
    service = Service()
    _activate(service, _package())
    _activate(service, _package(version="2", binding_id="agent-macro-pilot.v2"))
    result = read_registration_package(
        service, session_id="session-1", project_key="trusted_project",
        package_id="agent.macro.pilot", package_version=None,
    )
    assert isinstance(result, Failure)
    assert result.context["registration_code"] == "macro_registration_version_required"
    listed = service.store.list_project_artifacts(project_key="trusted_project")
    assert {item["name"] for item in listed} == {
        "macro-registration/agent.macro.pilot@1.json",
        "macro-registration/agent.macro.pilot@2.json",
    }


def test_activated_identity_rejects_different_digest_and_same_digest_does_not_demote() -> None:
    service = Service()
    package = _package()
    _activate(service, package)
    changed = _package()
    changed["owner"] = "different.owner"
    conflict = save_registration_package(
        service, session_id="session-1", project_key="trusted_project", payload=changed
    )
    assert isinstance(conflict, Failure)
    same = save_registration_package(
        service, session_id="session-1", project_key="trusted_project", payload=_package()
    )
    assert not isinstance(same, Failure)
    assert same["package"]["activation"]["status"] == "activated"


def test_skill_root_containment_hash_and_unknown_refs_are_enforced(tmp_path) -> None:
    registry = _registry()
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    source = Path(__file__).resolve().parents[2] / "skills" / "agent-macro-pilot" / "SKILL.md"
    (allowed / "agent-macro-pilot").mkdir()
    (allowed / "agent-macro-pilot" / "SKILL.md").write_bytes(source.read_bytes())
    (outside / "SKILL.md").write_bytes(source.read_bytes())
    (allowed / "linked").symlink_to(outside / "SKILL.md")

    def resolve_with(source_ref, content_id=None):
        service = Service()
        payload = _package()
        payload["skill_contents"][0]["source_ref"] = source_ref
        if content_id is not None:
            payload["skill_contents"][0]["content_id"] = content_id
        _activate(service, payload)
        return resolve_macro_environment(
            service, "trusted_project", (payload["package_id"],), (payload["package_version"],),
            (allowed,), registry, _catalog(service),
        )

    assert isinstance(resolve_with("linked/SKILL.md"), Failure)
    assert isinstance(resolve_with("agent-macro-pilot/SKILL.md", "sha256:" + "0" * 64), Failure)

    service = Service()
    unknown_tool = _package()
    unknown_tool["cell"]["tool_refs"] = ["missing.tool"]
    unknown_tool["skill_contents"][0]["tool_refs"] = ["missing.tool"]
    _activate(service, unknown_tool)
    assert isinstance(resolve_macro_environment(
        service, "trusted_project", ("agent.macro.pilot",), ("1",),
        (Path(__file__).resolve().parents[2] / "skills",), registry, _catalog(service),
    ), Failure)


def test_base_environment_projects_all_registry_tools_and_facilities() -> None:
    service = Service()
    registry = _registry()
    resolved = resolve_macro_environment(
        service, "trusted_project", [], [],
        (Path(__file__).resolve().parents[2] / "skills",), registry, _catalog(service),
    )
    assert not isinstance(resolved, Failure)
    assert resolved.package is None
    assert resolved.skills == ()
    assert [spec.name for spec in resolved.tools] == ["base.read", "skill.project_retrieval.read_run"]
    assert resolved.declared_tools == ()
    facility_ids = {binding.binding_id for binding in resolved.facilities}
    assert {
        "facility.agent_macro.registration_package.create",
        "facility.agent_macro.registration_package.readback",
        "facility.agent_macro.registration_package.activate",
        "facility.project_retrieval.current",
        "facility.information_topology.read",
        "facility.project_retrieval.rapid_proposal.save",
        "facility.project_retrieval.rapid_proposal.readback",
    } <= facility_ids
    descriptor = resolved.descriptor()
    assert descriptor["package"] is None
    assert descriptor["declared_tool_names"] == []

    context = TrustedHostContext("trusted_project", "session-1", "host-thread-1", "turn-1", "message-1")
    binding = assemble_native_macro_binding(resolved, context, service)
    assert not isinstance(binding, Failure)
    assert binding.binding_id == "agent.macro.base"
    assert binding.skill_roots == ()
    assert {tool.logical_name for tool in binding.tools} == {"base.read", "skill_project_retrieval.read_run"}

    base_tool = next(tool for tool in binding.tools if tool.logical_name == "base.read")
    result = base_tool.handler({})
    assert result["status"] == "completed"
    assert result["model_summary"] == "base capability remains mounted"


def test_invalid_explicit_package_does_not_fall_back_to_base() -> None:
    service = Service()
    registry = _registry()
    result = resolve_macro_environment(
        service, "trusted_project", ("missing.macro",), ("1",),
        (Path(__file__).resolve().parents[2] / "skills",), registry, _catalog(service),
    )
    assert isinstance(result, Failure)
    assert result.context["macro_environment_code"] == "macro_environment_invalid"


def test_same_arguments_produce_distinct_native_call_identity() -> None:
    service = Service()
    registry = _registry()
    resolved = resolve_macro_environment(
        service, "trusted_project", [], [],
        (Path(__file__).resolve().parents[2] / "skills",), registry, _catalog(service),
    )
    assert not isinstance(resolved, Failure)
    context = TrustedHostContext("trusted_project", "session-1", "host-thread-1", "turn-1", "message-1")
    binding = assemble_native_macro_binding(resolved, context, service)
    assert not isinstance(binding, Failure)
    base_tool = next(tool for tool in binding.tools if tool.logical_name == "base.read")
    first = base_tool.handler({})
    second = base_tool.handler({})
    assert first["status"] == "completed" and second["status"] == "completed"
    assert first["call_id"] != second["call_id"]


def test_native_tool_specs_matches_native_binding_projection() -> None:
    service = Service()
    registry = CoreToolRegistry()

    def noop(call, spec, request, emit):
        return CoreToolResult(call.call_id, call.tool_name, "completed", "ok")

    registry.register(CoreToolSpec(name="base.read", description_for_model="Base read."), noop)
    registry.register(
        CoreToolSpec(name="project_retrieval.current", description_for_model="Current binding."), noop
    )
    registry.register(
        CoreToolSpec(name="skill.project_retrieval.read_run", description_for_model="Read run."), noop
    )

    resolved = resolve_macro_environment(
        service, "trusted_project", [], [],
        (Path(__file__).resolve().parents[2] / "skills",), registry, _catalog(service),
    )
    assert not isinstance(resolved, Failure)
    context = TrustedHostContext("trusted_project", "session-1", "host-thread-1", "turn-1", "message-1")
    binding = assemble_native_macro_binding(resolved, context, service)
    assert not isinstance(binding, Failure)

    specs = native_tool_specs(registry.list_specs())
    assert specs == binding.dynamic_tool_specs()

    namespaces = {item["name"]: item for item in specs if item["type"] == "namespace"}
    assert set(namespaces) == {"base", "project_retrieval", "skill_project_retrieval"}
    assert [tool["name"] for tool in namespaces["project_retrieval"]["tools"]] == ["current"]
    assert [tool["name"] for tool in namespaces["skill_project_retrieval"]["tools"]] == ["read_run"]


def test_resolve_tool_package_digest_uses_authoritative_activate_target() -> None:
    service = Service()
    registry = _registry()
    package = _package()
    saved = save_registration_package(service, session_id="session-1", project_key="trusted_project", payload=package)
    assert not isinstance(saved, Failure)

    context = TrustedHostContext("trusted_project", "session-1", "host-thread-1", "turn-1", "message-1")
    base = resolve_macro_environment(
        service, "trusted_project", [], [],
        (Path(__file__).resolve().parents[2] / "skills",), registry, _catalog(service),
    )
    assert not isinstance(base, Failure)

    activate_call = CoreToolCall(
        tool_name="agent_macro.registration_package.activate",
        arguments={"package_id": package["package_id"], "package_version": package["package_version"]},
        call_id="call-activate",
    )
    assert resolve_tool_package_digest(base, context, service, activate_call) == saved["package"]["content_digest"]

    ordinary = CoreToolCall(tool_name="base.read", arguments={}, call_id="call-base")
    assert resolve_tool_package_digest(base, context, service, ordinary) is None

    bad = CoreToolCall(
        tool_name="agent_macro.registration_package.activate",
        arguments={"package_id": "missing.macro", "package_version": "1"},
        call_id="call-bad",
    )
    assert isinstance(resolve_tool_package_digest(base, context, service, bad), Failure)


def test_select_active_macro_identity_base_one_ambiguous_explicit() -> None:
    service = Service()
    assert select_active_macro_identity(service, "trusted_project") == ((), ())

    _activate(service, _package())
    assert select_active_macro_identity(service, "trusted_project") == (("agent.macro.pilot",), ("1",))

    candidate = _package(package_id="agent.macro.other", version="1")
    save_registration_package(service, session_id="session-1", project_key="trusted_project", payload=candidate)
    assert select_active_macro_identity(service, "trusted_project") == (("agent.macro.pilot",), ("1",))

    _activate(service, candidate)
    ambiguous = select_active_macro_identity(service, "trusted_project")
    assert isinstance(ambiguous, Failure)
    assert ambiguous.context["macro_environment_code"] == "macro_environment_ambiguous"

    assert select_active_macro_identity(service, "trusted_project", "agent.macro.pilot", "1") == (("agent.macro.pilot",), ("1",))
    assert isinstance(select_active_macro_identity(service, "trusted_project", "agent.macro.pilot", None), Failure)


@pytest.mark.parametrize("fields,ok", [
    ({"authorization_source": "host_policy", "approval_id": None}, True),
    ({"authorization_source": "human_confirmation", "approval_id": "approval-1"}, True),
    ({"approval_id": "approval-1"}, True),
    ({"authorization_source": "host_policy", "approval_id": "approval-1"}, False),
    ({"authorization_source": "human_confirmation", "approval_id": None}, False),
    ({"approval_id": None}, False),
    ({"authorization_source": "model_consent", "approval_id": None}, False),
    ({"authorization_source": "model_consent", "approval_id": "approval-1"}, False),
])
def test_activation_source_validation(fields, ok) -> None:
    result = _resolve_with_activation(Service(), _registry(), _package(), **fields)
    if ok:
        assert not isinstance(result, Failure)
    else:
        assert isinstance(result, Failure)
        assert result.context["macro_environment_code"] == "macro_environment_invalid"
