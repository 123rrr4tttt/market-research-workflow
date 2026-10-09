"""Registration packages for Agent macro cells.

Creation is candidate-only.  Activation is a separate, explicit AgentCore
operation that records the user's in-conversation agreement and remains scoped
to the current session/project; it does not silently install a global tool.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from hashlib import sha256
from typing import Annotated, NotRequired, TypedDict, TypeGuard

from app.contracts.json import JSONObject, JSONValue
from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_sessions.store import AgentArtifactPayload
from functorial_kit import Failure

from mrw_functorial_kit.core.agent_service_semantics import agent_runtime_failures

CONTRACT_VERSION = "agent_macro.registration_package.v1"
_IDENTITY = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _is_string_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    return _is_object_mapping(value) and all(isinstance(key, str) for key in value)


def _is_object_sequence(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _is_object_tuple(value: object) -> TypeGuard[tuple[object, ...]]:
    return isinstance(value, tuple)


class RegistrationSaveResult(TypedDict):
    package: JSONObject
    artifact: JSONObject
    project_artifact: JSONObject
    activation: JSONObject


class RegistrationReadResult(TypedDict):
    package: JSONObject
    artifact: JSONObject
    activation: JSONObject
    legacy: NotRequired[bool]
    runnable: NotRequired[bool]


class RegistrationActivateResult(TypedDict):
    package: JSONObject
    artifact: JSONObject
    activation: JSONObject
    already_activated: bool


def _json_value(value: object, *, path: str = "$") -> JSONValue | Failure:
    if value is None or isinstance(value, str | bool | int | float):
        return value
    if _is_object_sequence(value) or _is_object_tuple(value):
        converted_list: list[JSONValue] = []
        for index, item in enumerate(value):
            converted = _json_value(item, path=f"{path}[{index}]")
            if isinstance(converted, Failure):
                return converted
            converted_list.append(converted)
        return converted_list
    if _is_string_mapping(value):
        converted_object: JSONObject = {}
        for key, item in value.items():
            converted = _json_value(item, path=f"{path}.{key}")
            if isinstance(converted, Failure):
                return converted
            converted_object[key] = converted
        return converted_object
    return _failure(
        "macro_registration_invalid",
        "value is not JSON-compatible",
        path=path,
    )


def _json_object(value: object) -> JSONObject | None:
    converted = _json_value(value)
    if isinstance(converted, Failure):
        return None
    return converted if isinstance(converted, dict) else None


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _failure(code: str, message: str, *, path: str = "$") -> Failure:
    mapped = {
        "macro_registration_scope": "session_project_mismatch",
        "macro_registration_not_found": "writing_anchor_not_found",
        "macro_registration_readback": "writing_range_invalid",
    }.get(code, "capability_input_missing")
    return agent_runtime_failures.fail(mapped, message, {"path": path, "contract_version": CONTRACT_VERSION, "registration_code": code})


def _project_versions(
    service: AgentSessionService, *, session_id: str, project_key: str, package_id: str
) -> list[str]:
    """List exact project-artifact versions without selecting one by time."""

    prefix = f"macro-registration/{package_id}@"
    rows = service.store.list_project_artifacts(project_key=project_key)
    if isinstance(rows, Failure):
        return []
    return sorted({
        str(row.get("name", ""))[len(prefix):-len(".json")]
        for row in rows
        if str(row.get("artifact_type") or "") == "agent_macro.registration_package"
        and str(row.get("name") or "").startswith(prefix)
        and str(row.get("name") or "").endswith(".json")
    })


def _read_exact_artifact(
    service: AgentSessionService,
    *,
    session_id: str,
    project_key: str,
    package_id: str,
    package_version: str,
) -> JSONObject | None | Failure:
    name = registration_artifact_name({
        "package_id": package_id,
        "package_version": package_version,
    })
    row_value = service.store.get_project_artifact(project_key=project_key, name=name)
    if row_value is None or isinstance(row_value, Failure):
        # Pre-project-authority v1 artifacts remain readable from their
        # originating session when an exact version is requested.
        rows_value = service.store.list_artifacts(session_id)
        if isinstance(rows_value, Failure):
            return rows_value
        rows = rows_value
        matches = [item for item in rows if _is_string_mapping(item) and item.get("name") == name]
        if not matches:
            return None
        row_value = sorted(matches, key=lambda item: str(item.get("updated_at") or ""))[-1]
    if not _is_string_mapping(row_value):
        return _failure("macro_registration_readback", "registration artifact is not an object")
    if str(row_value.get("artifact_type") or "") != "agent_macro.registration_package":
        return None
    converted = _json_object(row_value)
    return converted if converted is not None else _failure(
        "macro_registration_readback", "registration artifact is not JSON"
    )


def _text(value: object, path: str) -> str | Failure:
    result = str(value or "").strip()
    return result if result else _failure("macro_registration_invalid", "non-empty value required", path=path)


def _refs(value: object, path: str) -> tuple[str, ...] | Failure:
    if _is_object_sequence(value):
        raw_items: list[object] | tuple[object, ...] = value
    elif _is_object_tuple(value):
        raw_items = value
    else:
        return _failure("macro_registration_invalid", "expected a non-empty string array", path=path)
    if any(not isinstance(item, str) or not item.strip() for item in raw_items):
        return _failure("macro_registration_invalid", "expected a non-empty string array", path=path)
    result = tuple(item.strip() for item in raw_items if isinstance(item, str))
    if len(result) != len(set(result)):
        return _failure("macro_registration_invalid", "references must be unique", path=path)
    return result


def validate_registration_package(payload: object, *, project_key: str) -> JSONObject | Failure:
    if not _is_string_mapping(payload):
        return _failure("macro_registration_invalid", "package must be an object")
    contract = str(payload.get("contract_version") or CONTRACT_VERSION)
    if contract != CONTRACT_VERSION:
        return _failure("macro_registration_version", "unsupported registration package version", path="$.contract_version")
    package_id = _text(payload.get("package_id"), "$.package_id")
    version = _text(payload.get("package_version"), "$.package_version")
    owner = _text(payload.get("owner"), "$.owner")
    if isinstance(package_id, Failure):
        return package_id
    if isinstance(version, Failure):
        return version
    if isinstance(owner, Failure):
        return owner
    if not _IDENTITY.fullmatch(package_id) or not _VERSION.fullmatch(version):
        return _failure("macro_registration_invalid", "package identity contains unsupported characters", path="$.package_id")
    declared_project = str(payload.get("project_key") or project_key).strip()
    if declared_project != project_key:
        return _failure("macro_registration_scope", "package project does not match the trusted request project", path="$.project_key")
    cell_value = payload.get("cell")
    if not _is_string_mapping(cell_value):
        return _failure("macro_registration_invalid", "cell declaration is required", path="$.cell")
    cell = _json_object(cell_value)
    if cell is None:
        return _failure("macro_registration_invalid", "cell declaration is not JSON", path="$.cell")
    cell_id = _text(cell.get("cell_id"), "$.cell.cell_id")
    core_binding_ref = _text(cell.get("core_binding_ref"), "$.cell.core_binding_ref")
    core_mode_value = _text(cell.get("core_mode"), "$.cell.core_mode")
    if isinstance(cell_id, Failure):
        return cell_id
    if isinstance(core_binding_ref, Failure):
        return core_binding_ref
    if isinstance(core_mode_value, Failure):
        return core_mode_value
    core_mode = str(cell.get("core_mode") or "")
    if core_mode not in {"native-agent", "model-only"}:
        return _failure("macro_registration_invalid", "unsupported core mode", path="$.cell.core_mode")
    arrays: dict[str, tuple[str, ...]] = {}
    for key in ("conceptual_rule_refs", "tool_refs", "facility_refs", "readback_refs"):
        value = _refs(cell.get(key), f"$.cell.{key}")
        if isinstance(value, Failure):
            return value
        arrays[key] = value
    canonical_arrays = {key: list(refs) for key, refs in arrays.items()}
    skills_value = payload.get("skill_contents", [])
    if not _is_object_sequence(skills_value):
        return _failure("macro_registration_invalid", "skill_contents must be an array", path="$.skill_contents")
    skills = skills_value
    normalized_skills: list[JSONObject] = []
    seen_skills: set[str] = set()
    for index, raw in enumerate(skills):
        if not _is_string_mapping(raw):
            return _failure("macro_registration_invalid", "skill content must be an object", path=f"$.skill_contents[{index}]")
        converted_item = _json_object(raw)
        if converted_item is None:
            return _failure("macro_registration_invalid", "skill content is not JSON", path=f"$.skill_contents[{index}]")
        item = converted_item
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
    relations_value = payload.get("relations", [])
    if not _is_object_sequence(relations_value):
        return _failure("macro_registration_invalid", "relations must be an array", path="$.relations")
    relations = relations_value
    normalized_relations: list[JSONObject] = []
    seen_relations: set[tuple[str, str]] = set()
    for index, raw in enumerate(relations):
        if not _is_string_mapping(raw):
            return _failure("macro_registration_invalid", "relation must be an object", path=f"$.relations[{index}]")
        converted_item = _json_object(raw)
        if converted_item is None:
            return _failure("macro_registration_invalid", "relation is not JSON", path=f"$.relations[{index}]")
        item = converted_item
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
        if isinstance(failures, Failure):
            return failures
        if isinstance(readbacks, Failure):
            return readbacks
        normalized_relations.append({**values, "realization": realization, "failure_refs": list(failures), "readback_refs": list(readbacks)})
    normalized: JSONObject = {
        "contract_version": CONTRACT_VERSION,
        "package_id": package_id,
        "package_version": version,
        "project_key": project_key,
        "owner": owner,
        "cell": {
            **cell,
            **canonical_arrays,
            "cell_id": cell_id,
            "core_binding_ref": core_binding_ref,
            "core_mode": core_mode,
        },
        "skill_contents": normalized_skills,
        "relations": normalized_relations,
        "activation": {"status": "candidate", "authority": "host_activation_required"},
    }
    normalized["content_digest"] = sha256(_canonical(normalized)).hexdigest()
    return normalized


def build_registration_package(payload: object, *, project_key: str) -> Annotated[
    JSONObject | Failure,
    "kit:non-authoritative derived_as=registration_candidate fact_source=payload+trusted_project_key "
    "witness=test:test_candidate_package_is_canonical_and_not_active",
]:
    return validate_registration_package(payload, project_key=project_key)


def registration_artifact_name(package: Mapping[str, object]) -> str:
    return f"macro-registration/{package['package_id']}@{package['package_version']}.json"


def _stored_json(value: object) -> JSONObject | Failure:
    if isinstance(value, Failure):
        return value
    converted = _json_object(value)
    return converted if converted is not None else _failure(
        "macro_registration_readback", "registration artifact result is not JSON"
    )


def save_registration_package(
    service: AgentSessionService,
    *,
    session_id: str,
    project_key: str,
    payload: object,
) -> RegistrationSaveResult | Failure:
    package = build_registration_package(payload, project_key=project_key)
    if isinstance(package, Failure):
        return package
    existing = _read_exact_artifact(
        service,
        project_key=project_key,
        session_id=session_id,
        package_id=str(package["package_id"]),
        package_version=str(package["package_version"]),
    )
    if isinstance(existing, Failure):
        return existing
    if existing is not None:
        old_package_value = existing.get("content_json")
        old_package = _json_object(old_package_value) or {}
        old_digest = str(old_package.get("content_digest") or "")
        old_activation_value = old_package.get("activation")
        old_activation = _json_object(old_activation_value) or {}
        if old_activation.get("status") == "activated":
            if old_digest != package["content_digest"]:
                return _failure(
                    "macro_registration_activation_conflict",
                    "activated package identity cannot be replaced with different content",
                    path="$.content_digest",
                )
            # Re-saving identical content is idempotent and must not demote an
            # activated package back to candidate.
            package["activation"] = old_activation
    artifact_payload: AgentArtifactPayload = {
        "session_id": session_id,
        "name": registration_artifact_name(package),
        "artifact_type": "agent_macro.registration_package",
        "mime_type": "application/json",
        "content_text": json.dumps(package, ensure_ascii=False, sort_keys=True),
        "content_json": package,
        "metadata": {"project_key": project_key, "content_digest": package["content_digest"], "activation_status": "candidate"},
    }
    result_value = service.store.upsert_artifact(artifact_payload)
    result = _stored_json(result_value)
    if isinstance(result, Failure):
        return result
    project_artifact_payload: AgentArtifactPayload = {
        **artifact_payload,
        "project_key": project_key,
        "metadata": {**artifact_payload["metadata"], "project_scope": True},
    }
    project_artifact_value = service.store.upsert_project_artifact(project_artifact_payload)
    project_artifact = _stored_json(project_artifact_value)
    if isinstance(project_artifact, Failure):
        return project_artifact
    saved: RegistrationSaveResult = {
        "package": package,
        "artifact": result,
        "project_artifact": project_artifact,
        "activation": _json_object(package.get("activation")) or {},
    }
    return saved


def read_registration_package(
    service: AgentSessionService,
    *,
    session_id: str,
    project_key: str,
    package_id: str,
    package_version: str | None = None,
) -> RegistrationReadResult | Failure:
    if not str(package_version or "").strip():
        versions = _project_versions(service, session_id=session_id, project_key=project_key, package_id=package_id)
        version_failure = _failure(
            "macro_registration_version_required",
            "registration package version is required",
            path="$.package_version",
        )
        if isinstance(version_failure.context, dict):
            version_failure.context["available_versions"] = versions
        return version_failure
    row = _read_exact_artifact(
        service,
        project_key=project_key,
        package_id=package_id,
        package_version=str(package_version).strip(),
        session_id=session_id,
    )
    if isinstance(row, Failure):
        return row
    if row is None:
        return _failure("macro_registration_not_found", "registration package was not found", path="$.package_id")
    package_value = row.get("content_json") or {}
    package = _json_object(package_value)
    if package is None:
        return _failure("macro_registration_readback", "registration package is not JSON", path="$")
    persisted_activation_value = package.get("activation") or {}
    persisted_activation = _json_object(persisted_activation_value) or {}
    digest = package.pop("content_digest", None)
    if digest is None:
        return {
            "package": {**package, "content_digest": None},
            "artifact": row,
            "activation": persisted_activation,
            "legacy": True,
            "runnable": False,
        }
    checked = build_registration_package(package, project_key=str(package.get("project_key") or ""))
    if isinstance(checked, Failure):
        return checked
    if checked.get("content_digest") != digest:
        return _failure("macro_registration_readback", "registration package digest mismatch", path="$.content_digest")
    checked["content_digest"] = str(digest)
    if persisted_activation:
        checked["activation"] = persisted_activation
    readback: RegistrationReadResult = {
        "package": checked,
        "artifact": row,
        "activation": _json_object(checked.get("activation")) or {},
    }
    return readback


def activate_registration_package(
    service: AgentSessionService,
    *,
    session_id: str,
    project_key: str,
    package_id: str,
    package_version: str,
    host_authorization: object,
) -> RegistrationActivateResult | Failure:
    """Activate a candidate using verified trusted-host authorization.

    Model-authored consent is not an authority. The registry obtains and checks
    ``VerifiedHostAuthorization`` through the A-owned host channel; this function
    only verifies that the verified object binds this activation tool, project,
    session and package digest, then records activation in the project artifact.
    """
    from .host_authorization import VerifiedHostAuthorization

    if not isinstance(host_authorization, VerifiedHostAuthorization):
        return _failure("macro_registration_host_authorization_required", "trusted host authorization is required", path="$.host_authorization")
    result = read_registration_package(service, session_id=session_id, project_key=project_key, package_id=package_id, package_version=package_version)
    if isinstance(result, Failure):
        return result
    if result.get("legacy") or result.get("runnable") is False:
        return _failure("macro_registration_legacy_unverified", "legacy package has no verifiable digest", path="$.content_digest")
    package_value = result["package"]
    package = _json_object(package_value)
    if package is None:
        return _failure("macro_registration_readback", "registration package is not JSON", path="$")
    if str(package.get("project_key") or "") != project_key:
        return _failure("macro_registration_scope", "package project does not match the trusted request project", path="$.project_key")
    context = host_authorization.context
    package_digest = str(package["content_digest"])
    automatic = host_authorization.permission == "allow" and host_authorization.approval_id is None
    confirmed = host_authorization.permission == "ask" and bool(str(host_authorization.approval_id or "").strip())
    if (
        str(context.project_key) != project_key
        or str(context.session_id) != session_id
        or str(host_authorization.tool_name) != "agent_macro.registration_package.activate"
        or str(host_authorization.package_digest) != package_digest
        or not (automatic or confirmed)
    ):
        return _failure("macro_registration_host_authorization_mismatch", "trusted host authorization does not bind this activation", path="$.host_authorization")
    activation_value = package.get("activation") or {}
    activation = _json_object(activation_value) or {}
    status = str(activation.get("status") or "candidate")
    if status == "activated":
        if str(activation.get("content_digest") or "") != package_digest:
            return _failure("macro_registration_activation_conflict", "activated package content digest changed", path="$.content_digest")
        return {"package": package, "artifact": result["artifact"], "activation": activation, "already_activated": True}
    if status != "candidate":
        return _failure("macro_registration_activation_state", "only candidate packages can be activated", path="$.activation.status")
    activation: JSONObject = {
        "status": "activated",
        "authority": "host_authorization",
        "authorization_source": "host_policy" if automatic else "human_confirmation",
        "scope": {"project_key": project_key, "scope_type": "project"},
        "host_thread_id": str(context.host_thread_id),
        "turn_id": str(context.turn_id),
        "user_message_id": str(context.user_message_id),
        "approval_id": host_authorization.approval_id,
        "content_digest": package_digest,
    }
    package["activation"] = activation
    artifact_payload: AgentArtifactPayload = {
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
            "activation_authority": "host_authorization",
            "activation_authorization_source": activation["authorization_source"],
            "activation_approval_id": activation["approval_id"],
        },
    }
    project_artifact_payload: AgentArtifactPayload = {
        **artifact_payload,
        "project_key": project_key,
        "metadata": {**artifact_payload["metadata"], "project_scope": True},
    }
    artifact_value = service.store.upsert_project_artifact(project_artifact_payload)
    artifact = _stored_json(artifact_value)
    if isinstance(artifact, Failure):
        return artifact
    # Keep the originating conversation artifact in sync for replay; the
    # project artifact above is the authority used by later sessions.
    service.store.upsert_artifact(artifact_payload)
    return {"package": package, "artifact": artifact, "activation": activation, "already_activated": False}
