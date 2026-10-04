from __future__ import annotations

from app.services.agent_core.macro_registration import (
    CONTRACT_VERSION,
    activate_registration_package,
    build_registration_package,
    save_registration_package,
)
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


def test_package_rejects_scope_mismatch_and_undeclared_skill_tool() -> None:
    mismatch = build_registration_package({**_package(), "project_key": "other"}, project_key="demo_project")
    assert isinstance(mismatch, Failure)
    invalid = _package()
    invalid["skill_contents"][0]["tool_refs"] = ["undeclared"]
    rejected = build_registration_package(invalid, project_key="demo_project")
    assert isinstance(rejected, Failure)


def test_agentcore_consent_activates_only_current_scope() -> None:
    service = _Service()
    saved = save_registration_package(service, session_id="session-1", project_key="demo_project", payload=_package())
    assert not isinstance(saved, Failure)
    activated = activate_registration_package(
        service,
        session_id="session-1",
        project_key="demo_project",
        package_id="demo.macro",
        package_version="1",
        consent_statement="用户已在 AgentCore 对话中同意激活这个胞腔注册包。",
    )
    assert not isinstance(activated, Failure)
    assert activated["activation"]["status"] == "activated"
    assert activated["activation"]["authority"] == "agentcore_user_consent"
    assert activated["activation"]["scope"] == {"project_key": "demo_project", "scope_type": "project"}
    assert activated["activation"]["consent_source_session_id"] == "session-1"
    assert activated["package"]["content_digest"] == saved["package"]["content_digest"]
