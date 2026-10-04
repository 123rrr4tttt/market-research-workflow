"""Pure compiled-plan data structures and structural observations.

Plans describe execution.  They do not select interpreters, grant authority, or
perform effects.  Operational identifiers are deliberately excluded from
``NormalizedPlanStructure`` so compilation laws compare semantic structure.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Literal

from app.successor_runtime.research.object_types import ObjectType

from .algebra import ReturnContract
from .checksum import sha256_hex
from .object_contracts import OperationContractRef
from .transforms import TransformRef

SourcePath = tuple[str, ...]


def object_type_digest(object_type: Any) -> str:
    """Digest the one canonical ObjectType field shape, accepting AST adapters."""
    return sha256_hex(
        {
            "type_id": object_type.type_id,
            "schema_version": object_type.schema_version,
            "codec_id": object_type.codec_id,
            "canonical_codec_version": object_type.canonical_codec_version,
        }
    )


def traversal_element_digests(elements: tuple[object, ...]) -> tuple[str, ...]:
    """Return the ordered canonical digest of each traversal element."""

    return tuple(sha256_hex(element) for element in elements)


def traversal_shape_digest(elements: tuple[object, ...]) -> str:
    """Canonical ordered finite-shape identity shared by compile and runtime."""

    element_digests = traversal_element_digests(elements)
    return sha256_hex(
        {
            "schema": "mrw.traverse-ordered.shape.v1",
            "element_count": len(elements),
            "element_digests": element_digests,
            "output_order": "INPUT_INDEX",
        }
    )


@dataclass(frozen=True, slots=True)
class CompiledAdmission:
    effect_step_id: str
    admission_step_id: str
    operation_id: str
    operation_contract_ref: OperationContractRef
    return_contract: ReturnContract


@dataclass(frozen=True, slots=True)
class CompiledStep:
    step_id: str
    step_kind: Literal["PURE", "EFFECT", "ADMISSION", "TRANSFORM", "MERGE", "DECIDE"]
    source_path: SourcePath
    input_type: ObjectType
    output_type: ObjectType
    dependencies: tuple[str, ...]
    operation_id: str | None
    operation_contract_ref: OperationContractRef | None
    transform_ref: TransformRef | None
    effect_profile_ref: str | None
    resource_profile_ref: str | None
    failure_profile_ref: str | None
    authority_profile_ref: str | None
    return_contract: ReturnContract
    semantic_return_barrier: bool
    staged_output_only: bool
    return_contract_ref: str | None = None
    admission: CompiledAdmission | None = None
    branch_id: str | None = None
    guard: str | None = None
    disposition: Literal["UNCONDITIONAL", "BRANCH_SELECTOR", "BRANCH_UNRESOLVED"] = (
        "UNCONDITIONAL"
    )
    branch_control_id: str | None = None
    branch_entry: bool = False
    branch_order: int | None = None


@dataclass(frozen=True, slots=True)
class CompiledDecisionBranch:
    """One branch occurrence set frozen into a compiled ``Decide`` control."""

    branch_id: str
    guard: str
    step_ids: tuple[str, ...]
    entry_step_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.branch_id or not self.guard:
            raise ValueError("compiled decision branch requires identity and guard")
        if not self.step_ids or not self.entry_step_ids:
            raise ValueError("compiled decision branch requires steps and entries")
        if len(set(self.step_ids)) != len(self.step_ids):
            raise ValueError("compiled decision branch step IDs must be unique")
        if not set(self.entry_step_ids).issubset(self.step_ids):
            raise ValueError("compiled decision entries must belong to the branch")


@dataclass(frozen=True, slots=True)
class CompiledControlNode:
    control_id: str
    node_kind: str
    source_path: SourcePath
    input_type: ObjectType
    output_type: ObjectType
    children: tuple[CompiledControlNode, ...]
    step_ids: tuple[str, ...]
    semantic_return_step_ids: tuple[str, ...]
    source_digest: str
    attributes: tuple[tuple[str, str], ...] = ()
    discriminator_ref: TransformRef | None = None
    decision_branches: tuple[CompiledDecisionBranch, ...] = ()
    control_digest: str = ""

    def __post_init__(self) -> None:
        expected = compiled_control_digest(self)
        if not self.control_digest:
            object.__setattr__(self, "control_digest", expected)
        elif self.control_digest != expected:
            raise ValueError("compiled control digest mismatch")

        if self.node_kind == "decide":
            if self.discriminator_ref is None or not self.decision_branches:
                raise ValueError("compiled Decide requires discriminator and branches")
            branch_ids = tuple(branch.branch_id for branch in self.decision_branches)
            if len(set(branch_ids)) != len(branch_ids):
                raise ValueError("compiled Decide branch IDs must be unique")
        elif self.discriminator_ref is not None or self.decision_branches:
            raise ValueError("only compiled Decide may carry decision control")

    def require_valid_control_digest(self) -> None:
        if self.control_digest != compiled_control_digest(self):
            raise ValueError("compiled control digest mismatch")


def compiled_control_digest(node: CompiledControlNode) -> str:
    """Bind the exact recursive compiled control, not merely its AST source."""

    return sha256_hex(
        {
            "schema_version": "mrw.compiled-control.v1",
            "control_id": node.control_id,
            "node_kind": node.node_kind,
            "source_path": node.source_path,
            "input_type": object_type_digest(node.input_type),
            "output_type": object_type_digest(node.output_type),
            "children": tuple(child.control_digest for child in node.children),
            "step_ids": node.step_ids,
            "semantic_return_step_ids": node.semantic_return_step_ids,
            "source_digest": node.source_digest,
            "attributes": node.attributes,
            "discriminator_ref": (
                None
                if node.discriminator_ref is None
                else (
                    node.discriminator_ref.name,
                    node.discriminator_ref.version,
                    node.discriminator_ref.digest,
                    node.discriminator_ref.transform_kind,
                )
            ),
            "decision_branches": tuple(
                (
                    branch.branch_id,
                    branch.guard,
                    branch.step_ids,
                    branch.entry_step_ids,
                )
                for branch in node.decision_branches
            ),
        }
    )


@dataclass(frozen=True, slots=True)
class ProgramPlanSourceMap:
    source_path: SourcePath
    source_kind: str
    source_digest: str
    control_id: str
    step_ids: tuple[str, ...]
    semantic_return_step_ids: tuple[str, ...]
    branch_id: str | None = None


@dataclass(frozen=True, slots=True)
class FrozenDependencyIndex:
    entries: tuple[tuple[str, tuple[str, ...]], ...]

    def dependencies_for(self, step_id: str) -> tuple[str, ...]:
        for candidate, dependencies in self.entries:
            if candidate == step_id:
                return dependencies
        raise KeyError(step_id)


@dataclass(frozen=True, slots=True)
class PlanReturnPolicy:
    success_modes: tuple[str, ...]
    failure_modes: tuple[str, ...]
    wait_modes: tuple[str, ...]
    cancel_modes: tuple[str, ...]
    exported_barrier_step_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CompletionPolicy:
    mode: str = "SEMANTIC_RETURN_BARRIERS"
    branch_mode: str = "SELECTED_BRANCH_ONLY"
    ordered: bool = True


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    plan_id: str
    program_id: str
    program_digest: str
    input_type: ObjectType
    output_type: ObjectType
    compiler_id: str
    compiler_version: str
    control_root: CompiledControlNode
    ordered_steps: tuple[CompiledStep, ...]
    dependency_index: FrozenDependencyIndex
    ready_order: tuple[str, ...]
    source_map: tuple[ProgramPlanSourceMap, ...]
    return_policy: PlanReturnPolicy
    completion_policy: CompletionPolicy
    effect_closure_digest: str
    authority_closure_digest: str
    resource_closure_digest: str
    plan_digest: str


@dataclass(frozen=True, slots=True)
class NormalizedPlanStructure:
    structure_version: str
    input_type_digest: str
    output_type_digest: str
    control_structure: Any
    step_structure: tuple[Any, ...]
    return_structure: tuple[Any, ...]


def _return_key(contract: ReturnContract) -> tuple[Any, ...]:
    return (
        contract.success_modes,
        contract.failure_modes,
        contract.wait_modes,
        contract.cancel_modes,
        contract.admission_required,
    )


def _ref_key(ref: OperationContractRef | None) -> tuple[str, str, str] | None:
    if ref is None:
        return None
    return (ref.kind, ref.contract_version, ref.contract_digest)


def _control_key(node: CompiledControlNode) -> Any:
    children = tuple(_control_key(child) for child in node.children)
    if node.node_kind == "then":
        flattened: list[Any] = []
        for child in children:
            if child[0] == "identity":
                continue
            if child[0] == "then":
                flattened.extend(child[1])
            else:
                flattened.append(child)
        if not flattened:
            return ("identity", object_type_digest(node.input_type))
        if len(flattened) == 1:
            return flattened[0]
        return ("then", tuple(flattened))
    return (
        node.node_kind,
        tuple(node.attributes),
        children,
        object_type_digest(node.input_type),
        object_type_digest(node.output_type),
    )


def normalized_plan_structure(plan: ExecutionPlan) -> NormalizedPlanStructure:
    step_keys = tuple(
        (
            step.step_kind,
            step.operation_id,
            _ref_key(step.operation_contract_ref),
            None
            if step.transform_ref is None
            else (
                step.transform_ref.name,
                step.transform_ref.version,
                step.transform_ref.digest,
                step.transform_ref.transform_kind,
            ),
            object_type_digest(step.input_type),
            object_type_digest(step.output_type),
            _return_key(step.return_contract),
            step.return_contract_ref,
            step.semantic_return_barrier,
            step.staged_output_only,
            step.branch_id,
            step.guard,
            step.disposition,
            step.branch_control_id,
            step.branch_entry,
            step.branch_order,
        )
        for step in plan.ordered_steps
    )
    barriers = tuple(
        (
            step.step_kind,
            step.operation_id,
            _ref_key(step.operation_contract_ref),
            _return_key(step.return_contract),
        )
        for step in plan.ordered_steps
        if step.step_id in plan.return_policy.exported_barrier_step_ids
    )
    if not barriers and plan.control_root.node_kind == "identity":
        barriers = (("identity", object_type_digest(plan.output_type)),)
    return NormalizedPlanStructure(
        structure_version="NormalizedPlanStructure.v1",
        input_type_digest=object_type_digest(plan.input_type),
        output_type_digest=object_type_digest(plan.output_type),
        control_structure=_control_key(plan.control_root),
        step_structure=step_keys,
        return_structure=(
            barriers,
            plan.return_policy.success_modes,
            plan.return_policy.failure_modes,
            plan.return_policy.wait_modes,
            plan.return_policy.cancel_modes,
            (
                plan.completion_policy.mode,
                plan.completion_policy.branch_mode,
                plan.completion_policy.ordered,
            ),
        ),
    )


def plans_structurally_equivalent(left: ExecutionPlan, right: ExecutionPlan) -> bool:
    return normalized_plan_structure(left) == normalized_plan_structure(right)


def _plan_payload(plan: ExecutionPlan) -> dict[str, Any]:
    return {
        "program_id": plan.program_id,
        "program_digest": plan.program_digest,
        "compiler": (plan.compiler_id, plan.compiler_version),
        "input": object_type_digest(plan.input_type),
        "output": object_type_digest(plan.output_type),
        "control": normalized_plan_structure(plan).control_structure,
        "steps": [
            {
                "id": step.step_id,
                "kind": step.step_kind,
                "path": step.source_path,
                "dependencies": step.dependencies,
                "contract": _ref_key(step.operation_contract_ref),
                "operation_id": step.operation_id,
                "transform": (
                    None
                    if step.transform_ref is None
                    else (
                        step.transform_ref.name,
                        step.transform_ref.version,
                        step.transform_ref.digest,
                        step.transform_ref.transform_kind,
                    )
                ),
                "profiles": (
                    step.effect_profile_ref,
                    step.authority_profile_ref,
                    step.resource_profile_ref,
                    step.failure_profile_ref,
                ),
                "barrier": step.semantic_return_barrier,
                "staged": step.staged_output_only,
                "return_contract_ref": step.return_contract_ref,
                "branch_id": step.branch_id,
                "guard": step.guard,
                "disposition": step.disposition,
                "branch_control_id": step.branch_control_id,
                "branch_entry": step.branch_entry,
                "branch_order": step.branch_order,
            }
            for step in plan.ordered_steps
        ],
        "ready_order": plan.ready_order,
        "return_policy": {
            "success_modes": plan.return_policy.success_modes,
            "failure_modes": plan.return_policy.failure_modes,
            "wait_modes": plan.return_policy.wait_modes,
            "cancel_modes": plan.return_policy.cancel_modes,
            "exported_barrier_step_ids": plan.return_policy.exported_barrier_step_ids,
        },
        "completion_policy": {
            "mode": plan.completion_policy.mode,
            "branch_mode": plan.completion_policy.branch_mode,
            "ordered": plan.completion_policy.ordered,
        },
        "effect_closure_digest": plan.effect_closure_digest,
        "authority_closure_digest": plan.authority_closure_digest,
        "resource_closure_digest": plan.resource_closure_digest,
    }


def with_plan_digest(plan: ExecutionPlan) -> ExecutionPlan:
    return replace(plan, plan_digest=sha256_hex(_plan_payload(plan)))


def identity_plan(object_type: ObjectType) -> ExecutionPlan:
    source_digest = sha256_hex({"identity": object_type_digest(object_type)})
    control = CompiledControlNode(
        control_id="control-" + source_digest[:24],
        node_kind="identity",
        source_path=("root",),
        input_type=object_type,
        output_type=object_type,
        children=(),
        step_ids=(),
        semantic_return_step_ids=(),
        source_digest=source_digest,
    )
    plan = ExecutionPlan(
        plan_id="plan-identity-" + source_digest[:16],
        program_id="identity",
        program_digest=source_digest,
        input_type=object_type,
        output_type=object_type,
        compiler_id="mrw.successor.compiler",
        compiler_version="1.0.0",
        control_root=control,
        ordered_steps=(),
        dependency_index=FrozenDependencyIndex(()),
        ready_order=(),
        source_map=(
            ProgramPlanSourceMap(
                source_path=("root",),
                source_kind="identity",
                source_digest=source_digest,
                control_id=control.control_id,
                step_ids=(),
                semantic_return_step_ids=(),
            ),
        ),
        return_policy=PlanReturnPolicy(
            success_modes=("SUCCEEDED",),
            failure_modes=("FAILED",),
            wait_modes=("WAIT",),
            cancel_modes=("CANCELED",),
            exported_barrier_step_ids=(),
        ),
        completion_policy=CompletionPolicy(),
        effect_closure_digest=sha256_hex({"effects": []}),
        authority_closure_digest=sha256_hex({"authority": []}),
        resource_closure_digest=sha256_hex({"resources": []}),
        plan_digest="",
    )
    return with_plan_digest(plan)
