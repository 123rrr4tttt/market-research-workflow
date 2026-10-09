from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256

import pytest
from app.services.agent_core.contracts import AgentCoreRequest, CoreToolCall
from app.services.agent_core.host_authorization import (
    TrustedHostContext,
    VerifiedHostAuthorization,
    canonical_arguments_sha256,
)
from app.services.agent_core.macro_registration import (
    CONTRACT_VERSION,
    activate_registration_package,
    build_registration_package,
    read_registration_package,
    save_registration_package,
)
from app.services.agent_core.macro_tools import macro_registration_package_create_facility
from app.services.agent_core.registry import CoreToolRegistry
from app.services.agent_sessions.store import InMemoryAgentSessionStore, validate_json_object
from functorial_kit import Failure


class _Store:
    def __init__(self) -> None:
        self.items = {}
        self.project_items = {}

    def upsert_artifact(self, payload):
        self.items[payload["name"]] = dict(payload)
        return self.items[payload["name"]]

    def list_artifacts(self, session_id):
        return list(self.items.values())

    def upsert_project_artifact(self, payload):
        key = (payload["project_key"], payload["name"])
        self.project_items[key] = dict(payload)
        return self.project_items[key]

    def get_project_artifact(self, *, project_key, name):
        return self.project_items.get((project_key, name))


class _Service:
    def __init__(self) -> None:
        self.store = _Store()


def _package() -> dict:
    return {
        "contract_version": CONTRACT_VERSION,
        "package_id": "demo.macro",
        "package_version": "1",
        "owner": "test.owner",
        "cell": {
            "cell_id": "demo.cell",
            "core_binding_ref": "codex.native",
            "core_mode": "native-agent",
            "conceptual_rule_refs": ["rule.boundary"],
            "tool_refs": ["project.read"],
            "facility_refs": ["project.facility"],
            "readback_refs": ["project.readback"],
        },
        "skill_contents": [{
            "skill_id": "demo.skill",
            "source_ref": "skills/demo/SKILL.md",
            "content_id": "demo:sha256:1",
            "applicability_ref": "demo.scope",
            "outcome_ref": "demo.outcome",
            "tool_refs": ["project.read"],
        }],
        "relations": [{
            "relation_id": "project.read",
            "source_ref": "core",
            "target_ref": "project.store",
            "observation_boundary": "macro",
            "realization": "virtual",
            "implementation_ref": "project.read",
            "authority_ref": "project.permissions",
            "failure_refs": ["project.failure"],
            "readback_refs": ["project.readback"],
        }],
    }


def test_candidate_package_is_canonical_and_not_active() -> None:
    result = build_registration_package(_package(), project_key="demo_project")
    assert not isinstance(result, Failure)
    assert result["activation"]["status"] == "candidate"
    assert result["activation"]["authority"] == "host_activation_required"
    assert len(result["content_digest"]) == 64
    assert validate_json_object(result, field="registration_package") == result
    digest_payload = dict(result)
    digest = str(digest_payload.pop("content_digest"))
    assert digest == sha256(
        json.dumps(
            digest_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def test_candidate_package_preserves_tuple_refs_nested_nulls_and_trimmed_identity() -> None:
    canonical_payload = _package()
    canonical_payload["cell"]["metadata"] = {
        "optional": None,
        "nested": ["kept", None, {"value": None}],
    }
    tuple_payload = _package()
    tuple_payload["cell"]["cell_id"] = "  demo.cell  "
    tuple_payload["cell"]["core_binding_ref"] = "  codex.native  "
    tuple_payload["cell"]["metadata"] = {
        "optional": None,
        "nested": ("kept", None, {"value": None}),
    }
    for key in (
        "conceptual_rule_refs",
        "tool_refs",
        "facility_refs",
        "readback_refs",
    ):
        tuple_payload["cell"][key] = tuple(tuple_payload["cell"][key])
    tuple_payload["skill_contents"][0]["tool_refs"] = tuple(
        tuple_payload["skill_contents"][0]["tool_refs"]
    )
    tuple_payload["relations"][0]["failure_refs"] = tuple(
        tuple_payload["relations"][0]["failure_refs"]
    )
    tuple_payload["relations"][0]["readback_refs"] = tuple(
        tuple_payload["relations"][0]["readback_refs"]
    )

    canonical = build_registration_package(canonical_payload, project_key="demo_project")
    from_tuple = build_registration_package(tuple_payload, project_key="demo_project")

    assert not isinstance(canonical, Failure)
    assert not isinstance(from_tuple, Failure)
    assert from_tuple == canonical
    assert from_tuple["content_digest"] == canonical["content_digest"]


def test_first_save_with_real_store_and_exact_legacy_session_readback() -> None:
    service = _Service()
    service.store = InMemoryAgentSessionStore()
    service.store.create_session({"session_id": "session-1", "project_key": "demo_project"})
    saved = save_registration_package(service, session_id="session-1", project_key="demo_project", payload=_package())
    assert not isinstance(saved, Failure)
    assert saved["package"]["activation"]["status"] == "candidate"
    legacy = _Service()
    legacy.store.items = dict(service.store._artifacts["session-1"])
    readback = read_registration_package(
        legacy, session_id="session-1", project_key="demo_project",
        package_id="demo.macro", package_version="1",
    )
    assert not isinstance(readback, Failure)
    assert readback["package"]["content_digest"] == saved["package"]["content_digest"]


def test_package_rejects_scope_mismatch_and_undeclared_skill_tool() -> None:
    mismatch = build_registration_package({**_package(), "project_key": "other"}, project_key="demo_project")
    assert isinstance(mismatch, Failure)
    invalid = _package()
    invalid["skill_contents"][0]["tool_refs"] = ["undeclared"]
    rejected = build_registration_package(invalid, project_key="demo_project")
    assert isinstance(rejected, Failure)


def test_package_rejects_nested_non_json_values_as_registration_failure() -> None:
    invalid = _package()
    invalid["cell"]["metadata"] = {"nested": ["valid", object()]}

    rejected = build_registration_package(invalid, project_key="demo_project")

    assert isinstance(rejected, Failure)
    assert rejected.context["registration_code"] == "macro_registration_invalid"


@pytest.mark.parametrize("permission,approval_id,source", [
    ("allow", None, "host_policy"),
    ("ask", "approval-1", "human_confirmation"),
])
def test_host_authorization_activates_only_current_scope(permission, approval_id, source) -> None:
    service = _Service()
    saved = save_registration_package(service, session_id="session-1", project_key="demo_project", payload=_package())
    assert not isinstance(saved, Failure)
    arguments = {"package_id": "demo.macro", "package_version": "1"}
    digest = canonical_arguments_sha256(arguments)
    assert not isinstance(digest, Failure)
    context = TrustedHostContext("demo_project", "session-1", "host-1", "turn-1", "message-1")
    authorization = VerifiedHostAuthorization(
        context, "agent_macro.registration_package.activate", digest,
        saved["package"]["content_digest"], permission, approval_id, "origin-call-1", "turn-1", "message-1",
    )
    activated = activate_registration_package(
        service,
        session_id="session-1",
        project_key="demo_project",
        package_id="demo.macro",
        package_version="1",
        host_authorization=authorization,
    )
    assert not isinstance(activated, Failure)
    assert activated["activation"]["status"] == "activated"
    assert activated["activation"]["authority"] == "host_authorization"
    assert activated["activation"]["scope"] == {"project_key": "demo_project", "scope_type": "project"}
    assert activated["activation"]["approval_id"] == approval_id
    assert activated["activation"]["authorization_source"] == source
    assert activated["package"]["content_digest"] == saved["package"]["content_digest"]
    assert activated["artifact"]["metadata"]["activation_authorization_source"] == source
    replay = activate_registration_package(
        service, session_id="session-1", project_key="demo_project",
        package_id="demo.macro", package_version="1", host_authorization=authorization,
    )
    assert replay["already_activated"] is True
    invalid_replay = activate_registration_package(
        service, session_id="session-1", project_key="demo_project",
        package_id="demo.macro", package_version="1",
        host_authorization=replace(authorization, package_digest="0" * 64),
    )
    assert isinstance(invalid_replay, Failure)


@pytest.mark.parametrize("permission,approval_id", [("ask", None), ("allow", "fake"), ("deny", "fake")])
def test_activation_rejects_invalid_authorization_without_writing(permission, approval_id) -> None:
    service = _Service()
    saved = save_registration_package(service, session_id="session-1", project_key="demo_project", payload=_package())
    digest = canonical_arguments_sha256({"package_id": "demo.macro", "package_version": "1"})
    authorization = VerifiedHostAuthorization(
        TrustedHostContext("demo_project", "session-1", "host-1", "turn-1", "message-1"),
        "agent_macro.registration_package.activate", digest, saved["package"]["content_digest"],
        permission, approval_id, "call-1", "turn-1", "message-1",
    )
    result = activate_registration_package(
        service, session_id="session-1", project_key="demo_project",
        package_id="demo.macro", package_version="1", host_authorization=authorization,
    )
    assert isinstance(result, Failure)
    assert next(iter(service.store.project_items.values()))["content_json"]["activation"]["status"] == "candidate"


def test_automatic_create_rejects_untrusted_registry_call_without_writing() -> None:
    service = _Service()
    binding = macro_registration_package_create_facility(service)
    assert binding.tool_spec.permission == "allow"
    registry = CoreToolRegistry()
    registry.register(binding.tool_spec, binding.handler)
    result = registry.execute_tool(
        tool_call=CoreToolCall(call_id="call-1", tool_name=binding.tool_spec.name, arguments={"package": _package()}),
        request=AgentCoreRequest(project_key="demo_project", session_id="session-1", turn_id="turn-1", message="add module"),
        emit=lambda _event: None,
    )
    assert result.status == "failed"
    assert not service.store.items
    assert not service.store.project_items
