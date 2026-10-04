"""Native macro declarations; projection and assembly never invoke the Core.

A definition references the original owners of methods, effects and lifecycle.
Its operation describes the open conversation boundary, not a business-intent
classifier. Existing CellBinding facts are supplied by the host at assembly.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Literal

from functorial_kit.contribution_compiler import NativeContributionRule, compile_native_contribution
from functorial_kit.contributions import ContributionObject, contribution_failures
from functorial_kit.core.failure import Failure
from functorial_kit.native_contribution import BindingAccepted, BindingRejected, NativeBindingIssue, ProjectedContributionSpec

from app.successor_runtime.capabilities.retrieval_common import (
    FlowOccurrence, FlowOperation, FlowOperationBinding, RetrievalFlowAssemblyContext,
    RetrievalFlowSource, assemble_retrieval_flow_definition, lower_retrieval_flow_source,
)
from app.successor_runtime.research.object_types import ObjectType

if TYPE_CHECKING:
    from app.successor_runtime.assembly.base import CellBinding
    from app.successor_runtime.specification.capability_cell_spec import CapabilityCellSpec


OPEN_MACRO_INPUT_TYPE = ObjectType("AgentMacroOpenInput.v1")
OPEN_MACRO_OUTPUT_TYPE = ObjectType("AgentMacroObservation.v1")
CoreMode = Literal["model-only", "native-agent"]


@dataclass(frozen=True, slots=True)
class SkillContentRef:
    """Authored content identity; deployment and actual adoption are separate facts."""

    skill_id: str
    source_ref: str
    content_id: str
    applicability_ref: str
    outcome_ref: str
    tool_refs: tuple[str, ...] = ()
    deployment_ref: str | None = None


@dataclass(frozen=True, slots=True)
class MacroRelationRealization:
    relation_id: str
    source_ref: str
    target_ref: str
    observation_boundary: str
    realization: Literal["virtual", "real"]
    implementation_ref: str
    authority_ref: str
    failure_refs: tuple[str, ...] = ()
    readback_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MacroCellDefinition:
    """One declaration; identity and boundary contracts belong to its operation."""

    operation: FlowOperation
    owner: str
    core_binding_ref: str
    conceptual_rule_refs: tuple[str, ...]
    relations: tuple[MacroRelationRealization, ...]
    core_mode: CoreMode = "native-agent"
    skill_contents: tuple[SkillContentRef, ...] = ()
    tool_refs: tuple[str, ...] = ()
    facility_refs: tuple[str, ...] = ()
    readback_refs: tuple[str, ...] = ()
    family_id: str = "agent.macro"
    capability_spec: CapabilityCellSpec | None = None

    @property
    def cell_id(self) -> str:
        return self.operation.operation_id

    @property
    def version(self) -> str:
        return self.operation.version

    @property
    def contribution_id(self) -> str:
        return f"{self.cell_id}.{self.version}"

    def occurrence(self, occurrence_id: str) -> FlowOccurrence:
        """Repeated occurrences retain their caller-owned identity and ordering."""
        return FlowOccurrence(occurrence_id, self.operation)


@dataclass(frozen=True, slots=True)
class MacroObservation:
    """Host observation only: answered does not establish delivery or saving."""

    invocation_id: str
    outcome: Literal["answered", "paused", "stopped", "failed"]
    response: str | None = None
    artifact_refs: tuple[str, ...] = ()
    receipt_refs: tuple[str, ...] = ()
    thread_id: str | None = None
    turn_id: str | None = None
    continuation_ref: str | None = None
    stop_reason: str | None = None
    failure_ref: str | None = None
    occurrence_id: str | None = None


def lower_macro_cell_definition(definition: MacroCellDefinition) -> MacroCellDefinition | Failure:
    issues: list[dict[str, str]] = []

    def required(value: str, path: str) -> None:
        if not isinstance(value, str) or not value.strip():
            issues.append({"path": path, "message": "nonempty owner reference required"})

    def references(values: tuple[str, ...], path: str) -> None:
        for index, value in enumerate(values):
            required(value, f"{path}[{index}]")

    for name in ("owner", "family_id", "core_binding_ref"):
        required(getattr(definition, name), f"$.{name}")
    for name in ("conceptual_rule_refs", "tool_refs", "facility_refs", "readback_refs"):
        references(getattr(definition, name), f"$.{name}")
    if not definition.conceptual_rule_refs:
        issues.append({"path": "$.conceptual_rule_refs", "message": "reference applicable original owner rules"})
    if definition.core_mode not in {"model-only", "native-agent"}:
        issues.append({"path": "$.core_mode", "message": "unknown Core support mode"})
    if definition.operation.control_kind != "macro":
        issues.append({"path": "$.operation.control_kind", "message": "macro boundary required"})
    for name in ("authority_ref", "stop_ref"):
        required(getattr(definition.operation, name), f"$.operation.{name}")
    skill_ids: set[str] = set()
    for index, skill in enumerate(definition.skill_contents):
        path = f"$.skill_contents[{index}]"
        for name in ("skill_id", "source_ref", "content_id", "applicability_ref", "outcome_ref"):
            required(getattr(skill, name), f"{path}.{name}")
        if skill.skill_id in skill_ids:
            issues.append({"path": path, "message": "one content definition per skill identity"})
        skill_ids.add(skill.skill_id)
        references(skill.tool_refs, f"{path}.tool_refs")
        if not set(skill.tool_refs).issubset(definition.tool_refs):
            issues.append({"path": path, "message": "skill tool references outside declared environment"})
        if skill.deployment_ref is not None:
            required(skill.deployment_ref, f"{path}.deployment_ref")
    relation_keys: set[tuple[str, str]] = set()
    for index, relation in enumerate(definition.relations):
        path = f"$.relations[{index}]"
        for name in ("relation_id", "source_ref", "target_ref", "observation_boundary", "implementation_ref", "authority_ref"):
            required(getattr(relation, name), f"{path}.{name}")
        key = (relation.relation_id, relation.observation_boundary)
        if key in relation_keys or relation.realization not in {"virtual", "real"}:
            issues.append({"path": path, "message": "duplicate relation observation or unknown realization"})
        relation_keys.add(key)
        references(relation.failure_refs, f"{path}.failure_refs")
        references(relation.readback_refs, f"{path}.readback_refs")
    spec = definition.capability_spec
    if spec is not None and (spec.cell_id != definition.cell_id or spec.family_id != definition.family_id):
        issues.append({"path": "$.capability_spec", "message": "existing cell identity/family mismatch"})
    flow = lower_retrieval_flow_source(RetrievalFlowSource(
        definition.cell_id, definition.version, definition.owner, definition.occurrence("boundary"),
    ))
    if isinstance(flow, Failure):
        return flow
    if issues:
        return contribution_failures.fail("CONTRIBUTION_INVALID", "macro declaration invalid", {"issues": tuple(issues)})
    return definition


def project_macro_cell_structure(definition: MacroCellDefinition) -> dict[str, object]:
    """Directed, non-authoritative structural view; carries no execution claims."""
    return {
        "cell_id": definition.cell_id, "version": definition.version,
        "owner": definition.owner, "operation": asdict(definition.operation),
        "core_binding_ref": definition.core_binding_ref, "core_mode": definition.core_mode,
        "conceptual_rule_refs": definition.conceptual_rule_refs,
        "skill_contents": tuple(asdict(item) for item in definition.skill_contents),
        "tool_refs": definition.tool_refs, "facility_refs": definition.facility_refs,
        "readback_refs": definition.readback_refs,
        "relations": tuple(asdict(item) for item in definition.relations),
    }


def project_macro_cell_definition(definition: MacroCellDefinition) -> ProjectedContributionSpec:
    refs = (definition.core_binding_ref, definition.operation.entrypoint_ref,
            definition.operation.authority_ref, definition.operation.stop_ref)
    refs += definition.conceptual_rule_refs + definition.tool_refs + definition.facility_refs
    refs += definition.readback_refs + definition.operation.effect_refs + definition.operation.failure_refs
    refs += tuple(item.content_id for item in definition.skill_contents)
    refs += tuple(item.implementation_ref for item in definition.relations)
    return ProjectedContributionSpec(
        id=definition.contribution_id, owner=definition.owner,
        objects=(ContributionObject(definition.contribution_id, "AgentMacroCell", definition.owner, refs),),
    )


@dataclass(frozen=True, slots=True)
class MacroAssemblyContext:
    """Existing host bindings; declarations cannot manufacture installation facts."""

    cell_binding: CellBinding
    operation_binding: FlowOperationBinding
    core_binding_ref: str
    core_mode: CoreMode
    skill_contents: tuple[SkillContentRef, ...] = ()
    tool_refs: tuple[str, ...] = ()
    facility_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MacroCellBinding:
    definition: MacroCellDefinition
    context: MacroAssemblyContext


def assemble_macro_cell_definition(
    definition: MacroCellDefinition, context: MacroAssemblyContext,
) -> MacroCellBinding | Failure:
    from app.successor_runtime.assembly.base import CellBinding

    cell = context.cell_binding
    if (
        not isinstance(cell, CellBinding)
        or cell.cell_id != definition.cell_id or cell.family_id != definition.family_id
        or cell.status != "INSTALLED"
        or cell.operation_contract_refs != (definition.operation.operation_id,)
        or context.core_binding_ref != definition.core_binding_ref or context.core_mode != definition.core_mode
        or context.skill_contents != definition.skill_contents or context.tool_refs != definition.tool_refs
        or context.facility_refs != definition.facility_refs
        or not callable(context.operation_binding.invoke)
    ):
        return contribution_failures.fail("CONTRIBUTION_INVALID", "macro host binding/environment mismatch")
    flow = lower_retrieval_flow_source(RetrievalFlowSource(
        definition.cell_id, definition.version, definition.owner, definition.occurrence("boundary"),
    ))
    if isinstance(flow, Failure):
        return flow
    binding = assemble_retrieval_flow_definition(flow, RetrievalFlowAssemblyContext((context.operation_binding,)))
    if isinstance(binding, Failure):
        return binding
    return MacroCellBinding(definition, context)


def validate_macro_cell_binding(
    definition: MacroCellDefinition, candidate: object,
) -> BindingAccepted[MacroCellBinding] | BindingRejected:
    if isinstance(candidate, MacroCellBinding) and candidate.definition == definition:
        checked = assemble_macro_cell_definition(definition, candidate.context)
        if not isinstance(checked, Failure):
            return BindingAccepted(candidate)
    return BindingRejected((NativeBindingIssue("$.binding", "macro definition or host binding mismatch"),))


AGENT_MACRO_NATIVE_RULE = NativeContributionRule[
    MacroCellDefinition, MacroCellDefinition, MacroAssemblyContext, MacroCellBinding
](
    lower=lower_macro_cell_definition,
    project=project_macro_cell_definition,
    assemble=assemble_macro_cell_definition,
    validate_binding=validate_macro_cell_binding,
)


def compile_agent_macro_native(definition: MacroCellDefinition):
    return compile_native_contribution(definition, AGENT_MACRO_NATIVE_RULE)
