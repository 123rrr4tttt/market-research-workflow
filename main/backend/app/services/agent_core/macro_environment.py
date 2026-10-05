"""Resolve activated macro registration packages into an inert environment.

Artifact identity, skill bytes, original tools and facility bindings are checked
here. Assembly constructs a native Codex environment but never starts a Core
process or executes a project effect.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from functorial_kit import Failure
from mrw_functorial_kit.core.agent_service_semantics import agent_runtime_failures
from app.services.llm.codex_macro_binding import NativeAgentBinding, NativeSkillBinding, NativeToolBinding
from app.successor_runtime.capabilities.agent_macro_native import (
    OPEN_MACRO_INPUT_TYPE, OPEN_MACRO_OUTPUT_TYPE, MacroCellDefinition, MacroRelationRealization,
    SkillContentRef, compile_agent_macro_native, project_macro_cell_structure,
)
from app.successor_runtime.capabilities.retrieval_common import FlowInterface, FlowOperation, FlowPort
from .contracts import AgentCoreRequest, CoreToolCall, CoreToolResult, CoreToolSpec
from .macro_registration import read_registration_package
from .macro_tools import FacilityBinding
from .project_tools import get_agent_macro_facility_catalog
from .registry import CoreToolRegistry


RESOLVED_MACRO_ENVIRONMENT_CONTRACT_VERSION = "agent_macro.environment.resolved.v1"
_CONTENT_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
BASE_CORE_BINDING_REF = "agent.macro.base"
_BASE_CONCEPTUAL_RULE_REFS = ("agent_macro_architecture.section.2",)
_ACTIVATE_TOOL_NAME = "agent_macro.registration_package.activate"
_REGISTRATION_ARTIFACT_TYPE = "agent_macro.registration_package"
_REGISTRATION_NAME_PREFIX = "macro-registration/"


def _failure(code: str, message: str, **context: Any) -> Failure:
    return agent_runtime_failures.fail(
        "capability_input_missing", message,
        {"contract_version": RESOLVED_MACRO_ENVIRONMENT_CONTRACT_VERSION, "macro_environment_code": code, **context},
    )


@dataclass(frozen=True, slots=True)
class ResolvedSkillContent:
    authored: SkillContentRef
    native: NativeSkillBinding
    source_root: str
    relative_path: str


@dataclass(frozen=True, slots=True)
class ResolvedMacroPackage:
    package_id: str
    package_version: str
    content_digest: str
    package: Mapping[str, Any]
    artifact: Mapping[str, Any]
    activation: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ResolvedMacroEnvironment:
    project_key: str
    definition: MacroCellDefinition
    package: ResolvedMacroPackage | None
    skills: tuple[ResolvedSkillContent, ...]
    tools: tuple[CoreToolSpec, ...]
    declared_tools: tuple[CoreToolSpec, ...]
    facilities: tuple[FacilityBinding, ...]
    registry: CoreToolRegistry

    @property
    def environment_digest(self) -> str:
        encoded = json.dumps(self.descriptor(), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        return sha256(encoded).hexdigest()

    def descriptor(self) -> dict[str, Any]:
        package = None
        version_digests: dict[str, str] = {}
        if self.package is not None:
            package = {
                "package_id": self.package.package_id,
                "package_version": self.package.package_version,
                "content_digest": self.package.content_digest,
                "activation": dict(self.package.activation),
            }
            version_digests = {
                f"{self.package.package_id}@{self.package.package_version}": self.package.content_digest
            }
        return {
            "contract_version": RESOLVED_MACRO_ENVIRONMENT_CONTRACT_VERSION,
            "project_key": self.project_key,
            "definition": project_macro_cell_structure(self.definition),
            "package": package,
            "skills": [{
                "skill_id": item.authored.skill_id,
                "source_root": item.source_root,
                "relative_path": item.relative_path,
                "path": item.native.path,
                "content_id": item.authored.content_id,
                "content_digest": item.native.content_digest,
                "tool_refs": list(item.authored.tool_refs),
            } for item in self.skills],
            "tools": [spec.to_dict() for spec in self.tools],
            "declared_tool_names": [spec.name for spec in self.declared_tools],
            "facilities": [binding.to_projection() for binding in self.facilities],
            "package_version_digests": version_digests,
        }


def _text(value: Any, *, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValueError(f"{field} is required")
    return result


def _resolve_skill(raw: Mapping[str, Any], source_roots: Sequence[str | Path]) -> ResolvedSkillContent:
    skill_id = _text(raw.get("skill_id"), field="skill_id")
    authored = SkillContentRef(
        skill_id=skill_id,
        source_ref=_text(raw.get("source_ref"), field="source_ref"),
        content_id=_text(raw.get("content_id"), field="content_id"),
        applicability_ref=_text(raw.get("applicability_ref"), field="applicability_ref"),
        outcome_ref=_text(raw.get("outcome_ref"), field="outcome_ref"),
        tool_refs=tuple(str(item) for item in raw.get("tool_refs") or ()),
    )
    if not _CONTENT_ID.fullmatch(authored.content_id):
        raise ValueError("skill content_id must be sha256:<hex>")
    source = Path(authored.source_ref).expanduser()
    roots = [Path(root).expanduser().resolve(strict=True) for root in source_roots]
    candidates = [source] if source.is_absolute() else [Path(root).expanduser() / source for root in source_roots]
    resolved_skill = source_root = None
    for root, candidate in zip(roots, candidates):
        try:
            resolved_candidate = candidate.resolve(strict=True)
            resolved_candidate.relative_to(root)
        except (FileNotFoundError, ValueError, OSError):
            continue
        if resolved_candidate.name == "SKILL.md" and resolved_candidate.is_file():
            resolved_skill, source_root = resolved_candidate, root
            break
    if resolved_skill is None or source_root is None:
        raise ValueError("skill source_ref is outside allowed roots or is not a real SKILL.md")
    digest = sha256(resolved_skill.read_bytes()).hexdigest()
    if authored.content_id != f"sha256:{digest}":
        raise ValueError("skill content_id does not match source bytes")
    native = NativeSkillBinding.from_path(name=skill_id, path=resolved_skill)
    if native.content_digest != digest:
        raise ValueError("native skill digest changed during resolution")
    return ResolvedSkillContent(authored, native, str(source_root), str(resolved_skill.relative_to(source_root)))


def _validate_activation_source(activation: Mapping[str, Any]) -> None:
    """Reject unknown or internally inconsistent activation authorization sources."""

    authorization_source = activation.get("authorization_source")
    approval_id = activation.get("approval_id")
    if authorization_source is None:
        if not str(approval_id or "").strip():
            raise ValueError("legacy activation requires a real approval_id")
        return
    if authorization_source == "host_policy":
        if approval_id is not None:
            raise ValueError("host_policy activation must not carry an approval_id")
        return
    if authorization_source == "human_confirmation":
        if not str(approval_id or "").strip():
            raise ValueError("human_confirmation activation requires a real approval_id")
        return
    raise ValueError("unknown activation authorization source")


def _activated_package(service: Any, *, project_key: str, package_id: str, package_version: str) -> ResolvedMacroPackage:
    result = read_registration_package(
        service, session_id="", project_key=project_key,
        package_id=package_id, package_version=package_version,
    )
    if isinstance(result, Failure):
        raise ValueError("registration package readback failed")
    if result.get("legacy") or result.get("runnable") is False:
        raise ValueError("legacy_activation_unverified")
    package = dict(result["package"])
    activation = dict(package.get("activation") or {})
    digest = str(package.get("content_digest") or "")
    if activation.get("status") != "activated" or activation.get("authority") != "host_authorization":
        raise ValueError("package is not activated by trusted host authority")
    _validate_activation_source(activation)
    if activation.get("scope") != {"project_key": project_key, "scope_type": "project"}:
        raise ValueError("activation project scope mismatch")
    if str(activation.get("content_digest") or "") != digest:
        raise ValueError("activation package digest mismatch")
    metadata = dict(result.get("artifact", {}).get("metadata") or {})
    if str(metadata.get("content_digest") or "") != digest or metadata.get("activation_status") != "activated":
        raise ValueError("activated artifact metadata mismatch")
    return ResolvedMacroPackage(package_id, package_version, digest, package, dict(result["artifact"]), activation)


def _definition_from_package(
    package: ResolvedMacroPackage, *, tools: Sequence[CoreToolSpec],
    facilities: Sequence[FacilityBinding], skills: Sequence[ResolvedSkillContent],
) -> MacroCellDefinition:
    raw = package.package
    cell = dict(raw.get("cell") or {})
    tool_refs = tuple(str(item) for item in cell.get("tool_refs") or ())
    facility_refs = tuple(str(item) for item in cell.get("facility_refs") or ())
    readback_refs = tuple(str(item) for item in cell.get("readback_refs") or ())
    tool_by_name = {spec.name: spec for spec in tools}
    facility_by_id = {binding.binding_id: binding for binding in facilities}
    if len(tool_by_name) != len(tool_refs) or any(name not in tool_by_name for name in tool_refs):
        raise ValueError("unknown tool_ref")
    if len(facility_by_id) != len(facility_refs) or any(name not in facility_by_id for name in facility_refs):
        raise ValueError("unknown facility_ref")
    if any(name not in facility_by_id for name in readback_refs):
        raise ValueError("unknown readback_ref")
    relations = tuple(MacroRelationRealization(
        relation_id=str(item.get("relation_id") or ""),
        source_ref=str(item.get("source_ref") or ""),
        target_ref=str(item.get("target_ref") or ""),
        observation_boundary=str(item.get("observation_boundary") or ""),
        realization=str(item.get("realization") or ""),
        implementation_ref=str(item.get("implementation_ref") or ""),
        authority_ref=str(item.get("authority_ref") or ""),
        failure_refs=tuple(str(ref) for ref in item.get("failure_refs") or ()),
        readback_refs=tuple(str(ref) for ref in item.get("readback_refs") or ()),
    ) for item in raw.get("relations") or ())
    executable_refs = set(tool_by_name)
    executable_refs.update(spec.project_service_id for spec in tools if spec.project_service_id)
    executable_refs.update(binding.binding_id for binding in facilities)
    executable_refs.update(binding.executor_ref for binding in facilities)
    if any(item.implementation_ref not in executable_refs for item in relations):
        raise ValueError("relation implementation_ref has no real owner")
    core_binding_ref = str(cell.get("core_binding_ref") or "")
    operation = FlowOperation(
        operation_id=str(cell.get("cell_id") or ""),
        version=package.package_version,
        inputs=FlowInterface((FlowPort("message", OPEN_MACRO_INPUT_TYPE),)),
        outputs=FlowInterface((FlowPort("observation", OPEN_MACRO_OUTPUT_TYPE),)),
        effect_refs=tuple(spec.name for spec in tools if spec.name in tool_refs),
        failure_refs=tuple(failure for relation in relations for failure in relation.failure_refs),
        authority_ref="host_authorization",
        stop_ref=core_binding_ref,
        entrypoint_ref=core_binding_ref,
        control_kind="macro",
    )
    definition = MacroCellDefinition(
        operation=operation,
        owner=str(raw.get("owner") or ""),
        core_binding_ref=core_binding_ref,
        conceptual_rule_refs=tuple(str(item) for item in cell.get("conceptual_rule_refs") or ()),
        relations=relations,
        core_mode=str(cell.get("core_mode") or ""),
        skill_contents=tuple(item.authored for item in skills),
        tool_refs=tool_refs,
        facility_refs=facility_refs,
        readback_refs=readback_refs,
    )
    checked = compile_agent_macro_native(definition)
    if isinstance(checked, Failure):
        raise ValueError("macro definition validation failed")
    return definition


def _base_definition() -> MacroCellDefinition:
    """The ordinary native Core surface with no activated package declaration."""

    operation = FlowOperation(
        operation_id=BASE_CORE_BINDING_REF,
        version="1",
        inputs=FlowInterface((FlowPort("message", OPEN_MACRO_INPUT_TYPE),)),
        outputs=FlowInterface((FlowPort("observation", OPEN_MACRO_OUTPUT_TYPE),)),
        effect_refs=(),
        failure_refs=(),
        authority_ref="host_authorization",
        stop_ref=BASE_CORE_BINDING_REF,
        entrypoint_ref=BASE_CORE_BINDING_REF,
        control_kind="macro",
    )
    return MacroCellDefinition(
        operation=operation,
        owner="host",
        core_binding_ref=BASE_CORE_BINDING_REF,
        conceptual_rule_refs=_BASE_CONCEPTUAL_RULE_REFS,
        relations=(),
        core_mode="native-agent",
        skill_contents=(),
        tool_refs=(),
        facility_refs=(),
        readback_refs=(),
    )


def _with_host_workbench(
    project_key: str, definition: MacroCellDefinition,
    skills: tuple[ResolvedSkillContent, ...], registry: CoreToolRegistry,
    source_roots: Sequence[str | Path], facility_catalog: Sequence[FacilityBinding],
) -> tuple[MacroCellDefinition, tuple[ResolvedSkillContent, ...]]:
    from app.services.crawlers_mgmt.workbench import workbench_module
    from .workbench_tools import WORKBENCH_SKILL_ID, WORKBENCH_TOOL_PREFIX

    if not workbench_module(project_key)["available"]:
        return definition, skills
    tool_refs = tuple(spec.name for spec in registry.list_specs() if spec.name.startswith(WORKBENCH_TOOL_PREFIX))
    if not tool_refs:
        return definition, skills
    relative_path = f"{WORKBENCH_SKILL_ID}/SKILL.md"
    content_path = next((Path(root) / relative_path for root in source_roots if (Path(root) / relative_path).is_file()), None)
    if content_path is None:
        raise ValueError("Registered workbench integration skill is missing from the host skill roots.")
    resolved = _resolve_skill({
        "skill_id": WORKBENCH_SKILL_ID, "source_ref": relative_path,
        "content_id": f"sha256:{sha256(content_path.read_bytes()).hexdigest()}",
        "applicability_ref": "crawler.agent_modules.concept_workbench.project_wiring",
        "outcome_ref": "original.concept_workbench.cli.observation",
        "tool_refs": list(tool_refs),
    }, source_roots)
    existing = next((item for item in skills if item.authored.skill_id == WORKBENCH_SKILL_ID), None)
    if existing is not None and existing.authored != resolved.authored:
        raise ValueError("Package workbench skill conflicts with the registered host module.")
    combined = skills if existing is not None else (*skills, resolved)
    facility_refs = tuple(binding.binding_id for binding in facility_catalog if binding.tool_spec.name in tool_refs)
    definition = replace(
        definition,
        skill_contents=tuple(item.authored for item in combined),
        tool_refs=tuple(dict.fromkeys((*definition.tool_refs, *tool_refs))),
        facility_refs=tuple(dict.fromkeys((*definition.facility_refs, *facility_refs))),
        readback_refs=tuple(dict.fromkeys((*definition.readback_refs, "facility.concept_workbench.module.read"))),
    )
    return definition, combined


def _base_environment(
    project_key: str, registry: CoreToolRegistry, facility_catalog: Sequence[FacilityBinding],
    source_roots: Sequence[str | Path],
) -> ResolvedMacroEnvironment | Failure:
    definition = _base_definition()
    try:
        definition, skills = _with_host_workbench(project_key, definition, (), registry, source_roots, facility_catalog)
    except (ValueError, OSError) as exc:
        return _failure("macro_environment_invalid", str(exc))
    checked = compile_agent_macro_native(definition)
    if isinstance(checked, Failure):
        return _failure("macro_environment_invalid", "base macro definition validation failed")
    return ResolvedMacroEnvironment(
        project_key,
        definition,
        None,
        skills,
        tuple(registry.list_specs()),
        tuple(spec for spec in registry.list_specs() if spec.name in definition.tool_refs),
        tuple(facility_catalog),
        registry,
    )


def resolve_macro_environment(
    service: Any,
    trusted_project: str,
    package_ids: Sequence[str],
    package_versions: Sequence[str | None],
    source_roots: Sequence[str | Path],
    registry: CoreToolRegistry,
    facility_catalog: Sequence[FacilityBinding] | None = None,
) -> ResolvedMacroEnvironment | Failure:
    """Resolve exactly one activated id/version without implicit selection."""

    project = str(trusted_project or "").strip()
    ids = [str(item or "").strip() for item in package_ids]
    versions = [str(item).strip() if item is not None else "" for item in package_versions]
    if not project:
        return _failure("project_scope_required", "trusted project is required")
    catalog = tuple(facility_catalog) if facility_catalog is not None else get_agent_macro_facility_catalog(service)

    if not ids and not versions:
        return _base_environment(project, registry, catalog, source_roots)

    if len(ids) != 1 or len(versions) != 1 or not ids[0] or not versions[0]:
        return _failure(
            "exact_package_identity_required",
            "one package id and explicit version are required, or none for the base environment",
        )
    try:
        resolved_package = _activated_package(
            service, project_key=project, package_id=ids[0], package_version=versions[0]
        )
        resolved_skills = tuple(
            _resolve_skill(item, source_roots)
            for item in resolved_package.package.get("skill_contents") or ()
        )
        all_tools = tuple(registry.list_specs())
        tool_refs = tuple(str(item) for item in resolved_package.package["cell"].get("tool_refs") or ())
        declared_tools = tuple(spec for spec in all_tools if spec.name in tool_refs)
        facility_refs = tuple(str(item) for item in resolved_package.package["cell"].get("facility_refs") or ())
        facilities = tuple(binding for binding in catalog if binding.binding_id in facility_refs)
        definition = _definition_from_package(
            resolved_package, tools=declared_tools, facilities=facilities, skills=resolved_skills
        )
        definition, resolved_skills = _with_host_workbench(project, definition, resolved_skills, registry, source_roots, catalog)
        declared_tools = tuple(spec for spec in all_tools if spec.name in definition.tool_refs)
        facilities = tuple(binding for binding in catalog if binding.binding_id in definition.facility_refs)
        checked = compile_agent_macro_native(definition)
        if isinstance(checked, Failure):
            return _failure("macro_environment_invalid", "effective macro definition validation failed")
    except (KeyError, TypeError, ValueError, OSError) as exc:
        return _failure(
            "macro_environment_invalid", str(exc), package_id=ids[0], package_version=versions[0]
        )
    return ResolvedMacroEnvironment(
        project, definition, resolved_package, resolved_skills,
        all_tools, declared_tools, facilities, registry,
    )


def _native_call_id() -> str:
    """Prefer the physical native occurrence id; otherwise mint a fresh occurrence id.

    The native Codex server propagates ``NativeToolCallContext`` through the dispatch
    channel; identical arguments must not collapse into one replayable origin id.
    """

    try:
        from app.services.llm.native_tool_context import current_native_tool_call_context
    except ImportError:
        return f"macro-occurrence-{uuid4().hex}"
    context = current_native_tool_call_context()
    if context is not None:
        call_id = str(getattr(context, "call_id", "") or "").strip()
        if call_id:
            return call_id
    return f"macro-occurrence-{uuid4().hex}"


def _tool_logical_parts(logical_name: str) -> tuple[str | None, str]:
    segments = logical_name.split(".")
    if len(segments) >= 3:
        return "_".join(segments[:-1]), segments[-1]
    if len(segments) == 2:
        return segments[0], segments[1]
    return None, logical_name


def native_tool_specs(tools: Sequence[CoreToolSpec]) -> list[dict[str, Any]]:
    """Project CoreToolSpec into the same wire shape as NativeAgentBinding.dynamic_tool_specs()."""

    plain: list[dict[str, Any]] = []
    namespaces: dict[str, list[dict[str, Any]]] = {}
    for spec in tools:
        namespace, name = _tool_logical_parts(spec.name)
        function = {
            "type": "function",
            "name": name,
            "description": spec.description_for_model,
            "inputSchema": dict(spec.input_schema),
            "deferLoading": False,
        }
        if namespace is None:
            plain.append(function)
        else:
            namespaces.setdefault(namespace, []).append(function)
    specs = list(plain)
    for namespace in sorted(namespaces):
        specs.append({
            "type": "namespace",
            "name": namespace,
            "description": f"MRW {namespace} operations.",
            "tools": namespaces[namespace],
        })
    return specs


def resolve_tool_package_digest(
    resolved: ResolvedMacroEnvironment,
    context: Any,
    executor: Any,
    tool_call: CoreToolCall,
) -> str | None | Failure:
    """Authoritative package digest for one tool call, never model-supplied.

    Activation targets the candidate package named by the call arguments and reads
    its real content digest from the project artifact. Every other tool keeps the
    resolved environment digest (or none for the base environment).
    """

    if tool_call.tool_name != _ACTIVATE_TOOL_NAME:
        return resolved.package.content_digest if resolved.package is not None else None
    package_id = str(tool_call.arguments.get("package_id") or "").strip()
    package_version = str(tool_call.arguments.get("package_version") or "").strip()
    if not package_id or not package_version:
        return _failure("macro_environment_invalid", "activate requires package_id and package_version")
    result = read_registration_package(
        executor,
        session_id=str(getattr(context, "session_id", "") or ""),
        project_key=str(getattr(context, "project_key", "") or ""),
        package_id=package_id,
        package_version=package_version,
    )
    if isinstance(result, Failure):
        return _failure(
            "macro_environment_invalid",
            "activate target package readback failed",
            package_id=package_id,
            package_version=package_version,
        )
    if result.get("legacy") or result.get("runnable") is False:
        return _failure(
            "macro_environment_invalid",
            "activate target package has no verifiable digest",
            package_id=package_id,
            package_version=package_version,
        )
    digest = str(result["package"].get("content_digest") or "").strip()
    if not digest:
        return _failure(
            "macro_environment_invalid",
            "activate target package has no content digest",
            package_id=package_id,
            package_version=package_version,
        )
    return digest


def select_active_macro_identity(
    service: Any,
    project_key: str,
    package_id: str | None = None,
    package_version: str | None = None,
) -> tuple[tuple[str, ...], tuple[str | None, ...]] | Failure:
    """Select the unique active package identity (base, one, or explicit) without implicit choice."""

    project = str(project_key or "").strip()
    explicit_id = str(package_id or "").strip()
    explicit_version = str(package_version or "").strip()
    if not project:
        return _failure("project_scope_required", "trusted project is required")
    if bool(explicit_id) != bool(explicit_version):
        return _failure("exact_package_identity_required", "package_id and package_version must be supplied together")
    if explicit_id and explicit_version:
        return ((explicit_id,), (explicit_version,))

    list_project = getattr(getattr(service, "store", None), "list_project_artifacts", None)
    if not callable(list_project):
        return _failure("macro_environment_invalid", "project artifact listing is unavailable")
    rows = list_project(project_key=project)
    if isinstance(rows, Failure):
        return _failure("macro_environment_invalid", "project artifact listing failed")
    activated: set[tuple[str, str]] = set()
    for row in rows:
        if str(row.get("artifact_type") or "") != _REGISTRATION_ARTIFACT_TYPE:
            continue
        name = str(row.get("name") or "")
        if not (name.startswith(_REGISTRATION_NAME_PREFIX) and name.endswith(".json")):
            continue
        activation = dict((row.get("content_json") or {}).get("activation") or {})
        metadata = dict(row.get("metadata") or {})
        if activation.get("status") != "activated" and metadata.get("activation_status") != "activated":
            continue
        inner = name[len(_REGISTRATION_NAME_PREFIX):-len(".json")]
        if "@" not in inner:
            continue
        activated_id, activated_version = inner.split("@", 1)
        if activated_id and activated_version:
            activated.add((activated_id, activated_version))
    if not activated:
        return ((), ())
    if len(activated) == 1:
        ((selected_id, selected_version),) = tuple(activated)
        return ((selected_id,), (selected_version,))
    return _failure(
        "macro_environment_ambiguous",
        "multiple activated macro packages exist; select an explicit package id and version",
        activated=sorted(activated),
    )


def assemble_native_macro_binding(
    resolved: ResolvedMacroEnvironment,
    trusted_host_context: Any,
    executor: Any,
) -> NativeAgentBinding | Failure:
    """Create an inert binding; authorization and effects occur only on calls."""

    from .host_authorization import TrustedHostContext

    if not isinstance(trusted_host_context, TrustedHostContext):
        return _failure("trusted_host_context_invalid", "trusted host context has the wrong type")
    if str(trusted_host_context.project_key) != resolved.project_key:
        return _failure("project_scope_mismatch", "trusted host project does not match resolved environment")

    tools: list[NativeToolBinding] = []
    for spec in resolved.tools:
        logical_name = spec.name
        namespace, name = _tool_logical_parts(logical_name)

        def handler(
            arguments: Mapping[str, Any],
            *,
            logical_name: str = logical_name,
            spec: CoreToolSpec = spec,
        ) -> Any:
            call = CoreToolCall(
                tool_name=logical_name,
                arguments=dict(arguments),
                call_id=_native_call_id(),
                reason="agent_macro_native",
            )
            package_digest = resolve_tool_package_digest(resolved, trusted_host_context, executor, call)
            if isinstance(package_digest, Failure):
                return CoreToolResult(
                    call_id=call.call_id,
                    tool_name=logical_name,
                    status="failed",
                    model_summary="tool package digest could not be resolved",
                    error={
                        "family": package_digest.family,
                        "code": package_digest.code,
                        "message": package_digest.message,
                    },
                ).to_dict()
            request = AgentCoreRequest(
                message="native macro tool call",
                session_id=trusted_host_context.session_id,
                project_key=trusted_host_context.project_key,
                turn_id=trusted_host_context.turn_id,
                context={"package_digest": package_digest} if package_digest else {},
            )
            result = resolved.registry.execute_tool(
                tool_call=call,
                tool_spec=spec,
                request=request,
                emit=lambda _event: None,
                trusted_context=trusted_host_context,
                authorization_service=executor,
                package_digest=package_digest,
            )
            return result.to_dict() if hasattr(result, "to_dict") else result

        tools.append(NativeToolBinding(
            namespace=namespace,
            name=name,
            description=spec.description_for_model,
            input_schema=spec.input_schema,
            handler=handler,
        ))

    return NativeAgentBinding(
        binding_id=resolved.definition.core_binding_ref,
        project_key=resolved.project_key,
        scope_id=trusted_host_context.host_thread_id,
        skills=tuple(item.native for item in resolved.skills),
        tools=tuple(tools),
        base_instructions=(
            "You are an MRW native Agent in one trusted project. The mounted registry preserves "
            "the ordinary Core surface; registered macro tools are additions, not a narrowing of "
            "native project capabilities."
        ),
        developer_instructions=(
            "Apply the mounted skill content after the original user input. Preserve project "
            "identity, tool failures, readback states and package identity exactly."
        ),
        sandbox="workspace-write",
    )
