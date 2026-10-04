"""Registration packages for Agent macro cells.

Creation is candidate-only.  Activation is a separate, explicit AgentCore
operation that records the user's in-conversation agreement and remains scoped
to the current session/project; it does not silently install a global tool.
"""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json
import re
from typing import Annotated, Any

from functorial_kit import Failure
from mrw_functorial_kit.core.agent_service_semantics import agent_runtime_failures


CONTRACT_VERSION = "agent_macro.registration_package.v1"
_IDENTITY = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _failure(code: str, message: str, *, path: str = "$") -> Failure:
    mapped = {
        "macro_registration_scope": "session_project_mismatch",
        "macro_registration_not_found": "writing_anchor_not_found",
        "macro_registration_readback": "writing_range_invalid",
    }.get(code, "capability_input_missing")
    return agent_runtime_failures.fail(mapped, message, {"path": path, "contract_version": CONTRACT_VERSION, "registration_code": code})


def _text(value: Any, path: str) -> str | Failure:
    result = str(value or "").strip()
    return result if result else _failure("macro_registration_invalid", "non-empty value required", path=path)


def _refs(value: Any, path: str) -> tuple[str, ...] | Failure:
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) or not item.strip() for item in value):
        return _failure("macro_registration_invalid", "expected a non-empty string array", path=path)
    result = tuple(item.strip() for item in value)
    if len(result) != len(set(result)):
        return _failure("macro_registration_invalid", "references must be unique", path=path)
    return result


def validate_registration_package(payload: Mapping[str, Any], *, project_key: str) -> dict[str, Any] | Failure:
    if not isinstance(payload, Mapping):
        return _failure("macro_registration_invalid", "package must be an object")
    contract = str(payload.get("contract_version") or CONTRACT_VERSION)
    if contract != CONTRACT_VERSION:
        return _failure("macro_registration_version", "unsupported registration package version", path="$.contract_version")
    package_id = _text(payload.get("package_id"), "$.package_id")
    version = _text(payload.get("package_version"), "$.package_version")
    owner = _text(payload.get("owner"), "$.owner")
    if isinstance(package_id, Failure) or isinstance(version, Failure) or isinstance(owner, Failure):
        return package_id if isinstance(package_id, Failure) else version if isinstance(version, Failure) else owner
    if not _IDENTITY.fullmatch(package_id) or not _VERSION.fullmatch(version):
        return _failure("macro_registration_invalid", "package identity contains unsupported characters", path="$.package_id")
    declared_project = str(payload.get("project_key") or project_key).strip()
    if declared_project != project_key:
        return _failure("macro_registration_scope", "package project does not match the trusted request project", path="$.project_key")
    cell = payload.get("cell")
    if not isinstance(cell, Mapping):
        return _failure("macro_registration_invalid", "cell declaration is required", path="$.cell")
    for key in ("cell_id", "core_binding_ref", "core_mode"):
        value = _text(cell.get(key), f"$.cell.{key}")
        if isinstance(value, Failure):
            return value
    core_mode = str(cell.get("core_mode") or "")
    if core_mode not in {"native-agent", "model-only"}:
        return _failure("macro_registration_invalid", "unsupported core mode", path="$.cell.core_mode")
    arrays: dict[str, tuple[str, ...]] = {}
    for key in ("conceptual_rule_refs", "tool_refs", "facility_refs", "readback_refs"):
        value = _refs(cell.get(key), f"$.cell.{key}")
        if isinstance(value, Failure):
            return value
        arrays[key] = value
    skills = payload.get("skill_contents", [])
    if not isinstance(skills, list):
        return _failure("macro_registration_invalid", "skill_contents must be an array", path="$.skill_contents")
    normalized_skills: list[dict[str, Any]] = []
    seen_skills: set[str] = set()
    for index, raw in enumerate(skills):
        if not isinstance(raw, Mapping):
            return _failure("macro_registration_invalid", "skill content must be an object", path=f"$.skill_contents[{index}]")
        item = dict(raw)
        skill_id = _text(item.get("skill_id"), f"$.skill_contents[{index}].skill_id")
        if isinstance(skill_id, Failure):
            return skill_id
        if skill_id in seen_skills:
            return _failure("macro_registration_invalid", "duplicate skill identity", path=f"$.skill_contents[{index}].skill_id")
        seen_skills.add(skill_id)
        for key in ("source_ref", "content_id", "applicability_ref", "outcome_ref"):
            value = _text(item.get(key), f"$.skill_contents[{index}].{key}")
            if isinstance(value, Failure):
                return value
            item[key] = value
        tool_refs = _refs(item.get("tool_refs", []), f"$.skill_contents[{index}].tool_refs")
        if isinstance(tool_refs, Failure):
            return tool_refs
        if not set(tool_refs).issubset(set(arrays["tool_refs"])):
            return _failure("macro_registration_dependency", "skill references an undeclared tool", path=f"$.skill_contents[{index}].tool_refs")
        item["skill_id"] = skill_id
        item["tool_refs"] = list(tool_refs)
        normalized_skills.append(item)
    relations = payload.get("relations", [])
    if not isinstance(relations, list):
        return _failure("macro_registration_invalid", "relations must be an array", path="$.relations")
    normalized_relations: list[dict[str, Any]] = []
    seen_relations: set[tuple[str, str]] = set()
    for index, raw in enumerate(relations):
        if not isinstance(raw, Mapping):
            return _failure("macro_registration_invalid", "relation must be an object", path=f"$.relations[{index}]")
        item = dict(raw)
        values: dict[str, str] = {}
        for key in ("relation_id", "source_ref", "target_ref", "observation_boundary", "implementation_ref", "authority_ref"):
            value = _text(item.get(key), f"$.relations[{index}].{key}")
            if isinstance(value, Failure):
                return value
            values[key] = value
        realization = str(item.get("realization") or "")
        if realization not in {"virtual", "real"}:
            return _failure("macro_registration_invalid", "relation realization must be virtual or real", path=f"$.relations[{index}].realization")
        key = (values["relation_id"], values["observation_boundary"])
        if key in seen_relations:
            return _failure("macro_registration_invalid", "duplicate relation observation", path=f"$.relations[{index}]")
        seen_relations.add(key)
        failures = _refs(item.get("failure_refs", []), f"$.relations[{index}].failure_refs")
        readbacks = _refs(item.get("readback_refs", []), f"$.relations[{index}].readback_refs")
        if isinstance(failures, Failure) or isinstance(readbacks, Failure):
            return failures if isinstance(failures, Failure) else readbacks
        normalized_relations.append({**values, "realization": realization, "failure_refs": list(failures), "readback_refs": list(readbacks)})
    normalized = {
        "contract_version": CONTRACT_VERSION,
        "package_id": package_id,
        "package_version": version,
        "project_key": project_key,
        "owner": owner,
        "cell": {**dict(cell), **arrays, "cell_id": str(cell["cell_id"]).strip(), "core_binding_ref": str(cell["core_binding_ref"]).strip(), "core_mode": core_mode},
        "skill_contents": normalized_skills,
        "relations": normalized_relations,
        "activation": {"status": "candidate", "authority": "host_activation_required"},
    }
    normalized["content_digest"] = sha256(_canonical(normalized)).hexdigest()
    return normalized


def build_registration_package(payload: Mapping[str, Any], *, project_key: str) -> Annotated[
    dict[str, Any] | Failure,
    "kit:non-authoritative derived_as=registration_candidate fact_source=payload+trusted_project_key "
    "witness=test:test_candidate_package_is_canonical_and_not_active",
]:
    return validate_registration_package(payload, project_key=project_key)


def registration_artifact_name(package: Mapping[str, Any]) -> str:
    return f"macro-registration/{package['package_id']}@{package['package_version']}.json"


def save_registration_package(service: Any, *, session_id: str, project_key: str, payload: Mapping[str, Any]) -> dict[str, Any] | Failure:
    package = build_registration_package(payload, project_key=project_key)
    if isinstance(package, Failure):
        return package
    artifact_payload = {
        "session_id": session_id,
        "name": registration_artifact_name(package),
        "artifact_type": "agent_macro.registration_package",
        "mime_type": "application/json",
        "content_text": json.dumps(package, ensure_ascii=False, sort_keys=True),
        "content_json": package,
        "metadata": {"project_key": project_key, "content_digest": package["content_digest"], "activation_status": "candidate"},
    }
    result = service.store.upsert_artifact(artifact_payload)
    if isinstance(result, Failure):
        return result
    project_artifact = service.store.upsert_project_artifact({
        **artifact_payload,
        "project_key": project_key,
        "metadata": {**artifact_payload["metadata"], "project_scope": True},
    })
    if isinstance(project_artifact, Failure):
        return project_artifact
    return {"package": package, "artifact": result, "project_artifact": project_artifact, "activation": package["activation"]}


def read_registration_package(service: Any, *, session_id: str, project_key: str, package_id: str, package_version: str | None = None) -> dict[str, Any] | Failure:
    prefix = f"macro-registration/{package_id}@"
    name = f"{prefix}{package_version}.json" if package_version else None
    row = service.store.get_project_artifact(project_key=str(project_key or ""), name=name) if name else None
    if row is None or isinstance(row, Failure):
        artifacts = service.store.list_artifacts(session_id)
        if isinstance(artifacts, Failure):
            return artifacts
        matches = [item for item in artifacts if str(item.get("name") or "").startswith(prefix)]
        if package_version:
            matches = [item for item in matches if str(item.get("name") or "").endswith(f"@{package_version}.json")]
        if not matches:
            return _failure("macro_registration_not_found", "registration package was not found", path="$.package_id")
        row = sorted(matches, key=lambda item: str(item.get("updated_at") or ""))[-1]
    package = dict(row.get("content_json") or {})
    persisted_activation = dict(package.get("activation") or {})
    digest = package.pop("content_digest", None)
    checked = build_registration_package(package, project_key=str(package.get("project_key") or ""))
    if isinstance(checked, Failure):
        return checked
    if checked.get("content_digest") != digest:
        return _failure("macro_registration_readback", "registration package digest mismatch", path="$.content_digest")
    checked["content_digest"] = digest
    if persisted_activation:
        checked["activation"] = persisted_activation
    return {"package": checked, "artifact": row, "activation": checked.get("activation")}


def activate_registration_package(
    service: Any,
    *,
    session_id: str,
    project_key: str,
    package_id: str,
    package_version: str | None,
    consent_statement: str,
) -> dict[str, Any] | Failure:
    """Activate a candidate after explicit agreement in the AgentCore chat.

    The consent statement is an auditable transcript-level acknowledgement,
    not a second policy engine.  The package digest is revalidated before the
    artifact is updated, and the resulting activation is still session and
    project scoped.
    """
    consent = str(consent_statement or "").strip()
    if not consent:
        return _failure("macro_registration_consent_required", "explicit user agreement is required", path="$.consent_statement")
    result = read_registration_package(service, session_id=session_id, project_key=project_key, package_id=package_id, package_version=package_version)
    if isinstance(result, Failure):
        return result
    package = dict(result["package"])
    if str(package.get("project_key") or "") != project_key:
        return _failure("macro_registration_scope", "package project does not match the trusted request project", path="$.project_key")
    activation = dict(package.get("activation") or {})
    status = str(activation.get("status") or "candidate")
    if status == "activated":
        if activation.get("scope") != {"project_key": project_key, "scope_type": "project"}:
            activation = {
                **activation,
                "scope": {"project_key": project_key, "scope_type": "project"},
                "consent_source_session_id": str((activation.get("scope") or {}).get("session_id") or session_id),
            }
            package["activation"] = activation
            service.store.upsert_project_artifact({
                "session_id": session_id,
                "project_key": project_key,
                "name": registration_artifact_name(package),
                "artifact_type": "agent_macro.registration_package",
                "mime_type": "application/json",
                "content_text": json.dumps(package, ensure_ascii=False, sort_keys=True),
                "content_json": package,
                "metadata": {"project_key": project_key, "content_digest": package["content_digest"], "activation_status": "activated", "activation_authority": "agentcore_user_consent", "project_scope": True},
            })
        return {"package": package, "artifact": result["artifact"], "activation": activation, "already_activated": True}
    if status != "candidate":
        return _failure("macro_registration_activation_state", "only candidate packages can be activated", path="$.activation.status")
    activation = {
        "status": "activated",
        "authority": "agentcore_user_consent",
        "scope": {"project_key": project_key, "scope_type": "project"},
        "consent_source_session_id": session_id,
        "consent_statement": consent,
    }
    package["activation"] = activation
    artifact_payload = {
        "session_id": session_id,
        "name": registration_artifact_name(package),
        "artifact_type": "agent_macro.registration_package",
        "mime_type": "application/json",
        "content_text": json.dumps(package, ensure_ascii=False, sort_keys=True),
        "content_json": package,
        "metadata": {
            "project_key": project_key,
            "content_digest": result["package"]["content_digest"],
            "activation_status": "activated",
            "activation_authority": "agentcore_user_consent",
        },
    }
    artifact = service.store.upsert_project_artifact({
        **artifact_payload,
        "project_key": project_key,
        "metadata": {**artifact_payload["metadata"], "project_scope": True},
    })
    if isinstance(artifact, Failure):
        return artifact
    # Keep the originating conversation artifact in sync for replay; the
    # project artifact above is the authority used by later sessions.
    service.store.upsert_artifact(artifact_payload)
    return {"package": package, "artifact": artifact, "activation": activation, "already_activated": False}
