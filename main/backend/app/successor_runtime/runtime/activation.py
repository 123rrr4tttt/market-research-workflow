"""Pure fixed-point activation for one exact Program/ExecutionPlan pair.

The activation core interprets only the plan's pure structure.  It never reads
or writes a store and never constructs a ``RuntimeAssignment``.  Content
addressed values produced by PURE/TRANSFORM/MERGE are returned as explicit
materialization descriptors; an outer project-plane adapter must durably bind
those bytes before publishing the corresponding EFFECT/ADMISSION activation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.successor_runtime.language.algebra import ValueRef, sha256_digest_bytes
from app.successor_runtime.language.checksum import canonical_bytes, sha256_hex
from app.successor_runtime.language.normalize import normalize_program
from app.successor_runtime.language.plan import (
    CompiledControlNode,
    CompiledStep,
    ExecutionPlan,
    object_type_digest,
    traversal_element_digests,
    traversal_shape_digest,
    with_plan_digest,
)
from app.successor_runtime.language.program import (
    Atom,
    Decide,
    Identity,
    MapOutput,
    ProgramNode,
    ProgramSpec,
    Pure,
    Then,
    TraverseOrdered,
    ZipOrdered,
)
from app.successor_runtime.language.transforms import (
    MergeRef,
    TransformRef,
    TransformRegistry,
)

from .reducer import (
    BranchDecisionReduction,
    RunSnapshot,
    StepSnapshot,
    reduce_branch_decision,
)
from .transitions import RunState, StepState


class ActivationError(ValueError):
    """The exact Program/Plan/value closure cannot be activated safely."""


@dataclass(frozen=True, slots=True)
class ProgramInput:
    """Exact root input used only when a control has no step dependency."""

    value_ref: ValueRef
    value: object


@dataclass(frozen=True, slots=True)
class BoundStepValue:
    """One completed or purely derived step output and its exact value ref."""

    step_id: str
    value_ref: ValueRef
    value: object


@dataclass(frozen=True, slots=True)
class ValueMaterialization:
    """Pure request to materialize a content-addressed value outside this core."""

    step_id: str
    value_ref: ValueRef
    exact_bytes: bytes
    value: object
    dependency_refs: tuple[ValueRef, ...]
    materialization_digest: str


@dataclass(frozen=True, slots=True)
class TraversalMaterialization:
    """Exact request to materialize one ordered successor Program epoch.

    The shared activation core never expands traversal elements into hidden
    callbacks or work items.  It binds the input sequence and element order;
    an outer project-plane materializer must persist a successor Program/Plan
    before any element effect can be claimed.
    """

    step_id: str
    traversal_policy: Literal["STATIC_SHAPE", "MATERIALIZED_SHAPE"]
    input_ref: ValueRef
    input_sequence_digest: str
    element_program_digest: str
    element_count: int
    element_digests: tuple[str, ...]
    shape_digest: str
    binding_digest: str
    materialization_digest: str


@dataclass(frozen=True, slots=True)
class ReadyActivation:
    """Store-independent EFFECT/ADMISSION activation descriptor."""

    step_id: str
    step_kind: Literal["EFFECT", "ADMISSION"]
    operation_id: str
    ordered_dependency_refs: tuple[ValueRef, ...]
    static_atom_input_refs: tuple[ValueRef, ...]
    payload_ref: ValueRef
    input_closure_digest: str
    activation_digest: str

    @property
    def ordered_input_refs(self) -> tuple[ValueRef, ...]:
        """Dynamic dependencies precede the Atom's declared static refs."""

        return self.ordered_dependency_refs + self.static_atom_input_refs


@dataclass(frozen=True, slots=True)
class CompletedBranchDecision:
    """Previously persisted output of the shared branch reducer."""

    control_id: str
    reduction: BranchDecisionReduction


@dataclass(frozen=True, slots=True)
class ActivationResult:
    """The deterministic fixed point reached from the supplied observations."""

    values: tuple[BoundStepValue, ...]
    materializations: tuple[ValueMaterialization, ...]
    activations: tuple[ReadyActivation, ...]
    branch_decisions: tuple[CompletedBranchDecision, ...]
    traversal_materializations: tuple[TraversalMaterialization, ...] = ()


def activate_plan(
    *,
    run_id: str,
    program: ProgramSpec,
    plan: ExecutionPlan,
    completed_outputs: tuple[BoundStepValue, ...] = (),
    completed_branch_decisions: tuple[CompletedBranchDecision, ...] = (),
    program_input: ProgramInput | None = None,
    transform_registry: TransformRegistry,
    merge_registry: TransformRegistry,
    discriminator_registry: TransformRegistry,
    already_activated_step_ids: frozenset[str] = frozenset(),
) -> ActivationResult:
    """Interpret pure steps and discover ready effect/admission work.

    The fold is ordered and reaches a fixed point.  It preserves dependency
    order, invokes a MERGE callable as ``merge(left, right)``, and delegates
    every fresh DECIDE to :func:`reduce_branch_decision`.  Replaying identical
    inputs returns byte-for-byte equal descriptors; conflicting duplicate
    observations fail closed.
    """

    if not run_id:
        raise ActivationError("activation requires a run_id")
    normalized = normalize_program(program)
    _require_exact_plan(normalized, plan)

    nodes = _nodes_by_path(normalized.root)
    steps = {step.step_id: step for step in plan.ordered_steps}
    if len(steps) != len(plan.ordered_steps):
        raise ActivationError("ExecutionPlan step IDs must be unique")

    values = _completed_values(completed_outputs, steps, program.project_key)
    materializations: dict[str, ValueMaterialization] = {}
    activations: dict[str, ReadyActivation] = {}
    traversal_materializations: dict[str, TraversalMaterialization] = {}
    controls = _controls_by_id(plan.control_root)
    decisions = _completed_decisions(completed_branch_decisions, controls)

    progress = True
    while progress:
        progress = False
        for step in plan.ordered_steps:
            if step.step_id in values:
                continue
            if not _branch_is_released(step, decisions):
                continue

            dependencies = _dependency_values(
                step,
                values,
                steps,
                decisions,
            )
            if dependencies is None:
                continue

            if step.step_kind == "PURE":
                node = _require_node(nodes, step, Pure)
                value = _thaw(node.literal_value)
                embedded_ref = _unique_embedded_value_ref(
                    value, project_key=program.project_key
                )
                if embedded_ref is None:
                    bound, materialization = _derive_value(
                        program=program,
                        plan=plan,
                        step=step,
                        value=value,
                        dependency_refs=tuple(item.value_ref for item in dependencies),
                        codec_id=node.literal_codec,
                    )
                    materializations[step.step_id] = materialization
                else:
                    bound = BoundStepValue(step.step_id, embedded_ref, value)
                values[step.step_id] = bound
                progress = True
                continue

            if step.step_kind == "TRANSFORM":
                traversal_node = nodes.get(step.source_path)
                if isinstance(traversal_node, TraverseOrdered):
                    descriptor = _traversal_materialization_descriptor(
                        program=program,
                        plan=plan,
                        step=step,
                        node=traversal_node,
                        dependencies=dependencies,
                        program_input=program_input,
                    )
                    traversal_materializations.setdefault(
                        step.step_id,
                        descriptor,
                    )
                    continue
                if len(dependencies) != 1 or step.transform_ref is None:
                    raise ActivationError(
                        f"TRANSFORM {step.step_id} requires one dependency and exact ref"
                    )
                ref = TransformRef(
                    step.transform_ref.name,
                    step.transform_ref.version,
                    step.transform_ref.digest,
                    "transform",
                )
                entry = transform_registry.resolve_transform(ref)
                _require_transform_types(step, entry.input_type, entry.output_type)
                value = entry.callable(dependencies[0].value)
                if entry.preserves_value_ref:
                    if canonical_bytes(value) != canonical_bytes(dependencies[0].value):
                        raise ActivationError(
                            f"TRANSFORM {step.step_id} changed bytes despite ValueRef-preserving binding"
                        )
                    if not _output_type_compatible(
                        step.output_type, dependencies[0].value_ref.object_type
                    ):
                        raise ActivationError(
                            f"TRANSFORM {step.step_id} cannot preserve an incompatible ValueRef type"
                        )
                    # A representation-preserving transform, including the
                    # Claim/Gap branch identities typed through
                    # ClaimOrGap.v1, must not invent a second canonical value.
                    # The step remains observable while its exact ValueRef is
                    # preserved for the following ordered composition.
                    values[step.step_id] = BoundStepValue(
                        step.step_id,
                        dependencies[0].value_ref,
                        dependencies[0].value,
                    )
                    progress = True
                    continue
                bound, materialization = _derive_value(
                    program=program,
                    plan=plan,
                    step=step,
                    value=value,
                    dependency_refs=(dependencies[0].value_ref,),
                )
                values[step.step_id] = bound
                materializations[step.step_id] = materialization
                progress = True
                continue

            if step.step_kind == "MERGE":
                if len(dependencies) != 2 or step.transform_ref is None:
                    raise ActivationError(
                        f"MERGE {step.step_id} requires exact ordered left/right outputs"
                    )
                ref = MergeRef(
                    step.transform_ref.name,
                    step.transform_ref.version,
                    step.transform_ref.digest,
                    "merge",
                )
                entry = merge_registry.resolve_merge(ref)
                if object_type_digest(entry.output_type) != object_type_digest(
                    step.output_type
                ):
                    raise ActivationError(
                        "MERGE output type does not match compiled step"
                    )
                # This order is semantic.  It is not normalized or commuted.
                value = entry.callable(dependencies[0].value, dependencies[1].value)
                dependency_refs = tuple(item.value_ref for item in dependencies)
                bound, materialization = _derive_value(
                    program=program,
                    plan=plan,
                    step=step,
                    value=value,
                    dependency_refs=dependency_refs,
                )
                values[step.step_id] = bound
                materializations[step.step_id] = materialization
                progress = True
                continue

            if step.step_kind == "DECIDE":
                control_id = step.branch_control_id
                if control_id is None or control_id not in controls:
                    raise ActivationError(
                        "DECIDE step lacks its exact compiled control"
                    )
                decision_input = _control_input(
                    dependencies, program_input, step.step_id
                )
                decision = decisions.get(control_id)
                if decision is None:
                    reduction = reduce_branch_decision(
                        RunSnapshot(run_id, RunState.RUNNING),
                        tuple(
                            StepSnapshot(step_id, StepState.PENDING)
                            for branch in controls[control_id].decision_branches
                            for step_id in branch.step_ids
                        ),
                        controls[control_id],
                        discriminator_registry=discriminator_registry,
                        input_value=decision_input.value,
                    )
                    decision = CompletedBranchDecision(control_id, reduction)
                    decisions[control_id] = decision
                _require_decision_matches_input(
                    decision,
                    controls[control_id],
                    decision_input.value,
                )
                if decision.reduction.selected_branch_id is None:
                    # No branch is released from an unresolved decision.
                    continue
                values[step.step_id] = BoundStepValue(
                    step.step_id, decision_input.value_ref, decision_input.value
                )
                progress = True
                continue

            if step.step_kind in {"EFFECT", "ADMISSION"}:
                if step.step_id in already_activated_step_ids:
                    continue
                atom = _require_atom(nodes, step)
                descriptor = _activation_descriptor(
                    project_key=program.project_key,
                    plan=plan,
                    step=step,
                    atom=atom,
                    dependencies=dependencies,
                )
                activations.setdefault(step.step_id, descriptor)
                continue

            raise ActivationError(f"unsupported compiled step kind {step.step_kind!r}")

    ordered_value_ids = tuple(
        step.step_id for step in plan.ordered_steps if step.step_id in values
    )
    ordered_decision_ids = tuple(
        control_id for control_id in controls if control_id in decisions
    )
    return ActivationResult(
        values=tuple(values[step_id] for step_id in ordered_value_ids),
        materializations=tuple(
            materializations[step_id]
            for step_id in ordered_value_ids
            if step_id in materializations
        ),
        activations=tuple(
            activations[step.step_id]
            for step in plan.ordered_steps
            if step.step_id in activations
        ),
        branch_decisions=tuple(decisions[item] for item in ordered_decision_ids),
        traversal_materializations=tuple(
            traversal_materializations[step.step_id]
            for step in plan.ordered_steps
            if step.step_id in traversal_materializations
        ),
    )


def _traversal_materialization_descriptor(
    *,
    program: ProgramSpec,
    plan: ExecutionPlan,
    step: CompiledStep,
    node: TraverseOrdered,
    dependencies: tuple[BoundStepValue, ...],
    program_input: ProgramInput | None,
) -> TraversalMaterialization:
    if step.transform_ref is None or (
        step.transform_ref.name != "mrw.traverse_ordered.materialize"
        or step.transform_ref.version != "1.0.0"
    ):
        raise ActivationError("TraverseOrdered step lacks exact materializer binding")
    if len(dependencies) == 1:
        traversal_input = ProgramInput(
            dependencies[0].value_ref,
            dependencies[0].value,
        )
    elif not dependencies and program_input is not None:
        traversal_input = program_input
    else:
        raise ActivationError(
            f"TraverseOrdered {step.step_id} requires exactly one sequence input"
        )
    _require_value_ref(traversal_input.value_ref, program.project_key)
    if not _output_type_compatible(
        step.input_type,
        traversal_input.value_ref.object_type,
    ):
        raise ActivationError("TraverseOrdered input ValueRef type mismatch")
    if not isinstance(traversal_input.value, (tuple, list)):
        raise ActivationError("TraverseOrdered input must be a finite sequence")

    elements = tuple(traversal_input.value)
    exact_input_bytes = canonical_bytes(list(elements))
    if traversal_input.value_ref.codec_id != step.input_type.codec_id:
        raise ActivationError("TraverseOrdered input codec drift")
    if traversal_input.value_ref.byte_size != len(exact_input_bytes):
        raise ActivationError("TraverseOrdered input byte-size drift")
    element_digests = traversal_element_digests(elements)
    input_sequence_digest = sha256_digest_bytes(exact_input_bytes)
    if traversal_input.value_ref.content_digest != input_sequence_digest:
        raise ActivationError("TraverseOrdered input content digest mismatch")
    shape_digest = traversal_shape_digest(elements)

    metadata = dict(program.metadata)
    static_shape_digest: str | None = None
    static_element_count: int | None = None
    if node.traversal_policy == "STATIC_SHAPE":
        static_shape_digest = metadata.get("traversal_shape_digest")
        static_element_count = metadata.get("traversal_element_count")
        if static_shape_digest != shape_digest or static_element_count != len(elements):
            raise ActivationError("STATIC_SHAPE traversal input drift")
    elif node.traversal_policy != "MATERIALIZED_SHAPE":
        raise ActivationError("unsupported traversal policy")

    binding = {
        "schema": "mrw.traverse-ordered.materialization-binding.v1",
        "policy": node.traversal_policy,
        "element_program_digest": node.element_program.ast_digest(),
        "static_shape_digest": static_shape_digest,
        "static_element_count": static_element_count,
        "output_order": "INPUT_INDEX",
        "realization": "SUCCESSOR_PROGRAM_EPOCH",
    }
    binding_digest = sha256_hex(binding)
    if step.transform_ref.digest != binding_digest:
        raise ActivationError("TraverseOrdered materializer binding drift")
    materialization_digest = sha256_hex(
        {
            "schema": "mrw.traverse-ordered.materialization.v1",
            "program_digest": program.program_digest,
            "plan_digest": plan.plan_digest,
            "step_id": step.step_id,
            "input_ref": traversal_input.value_ref.to_plain(),
            "input_sequence_digest": input_sequence_digest,
            "shape_digest": shape_digest,
            "binding_digest": binding_digest,
        }
    )
    return TraversalMaterialization(
        step_id=step.step_id,
        traversal_policy=node.traversal_policy,
        input_ref=traversal_input.value_ref,
        input_sequence_digest=input_sequence_digest,
        element_program_digest=node.element_program.ast_digest(),
        element_count=len(elements),
        element_digests=element_digests,
        shape_digest=shape_digest,
        binding_digest=binding_digest,
        materialization_digest=materialization_digest,
    )


def _require_exact_plan(program: ProgramSpec, plan: ExecutionPlan) -> None:
    if program.program_id != plan.program_id:
        raise ActivationError("Program/ExecutionPlan program_id mismatch")
    if program.program_digest != program.digest():
        raise ActivationError("ProgramSpec carries a stale program_digest")
    if plan.program_digest != program.program_digest:
        raise ActivationError("ExecutionPlan does not bind the normalized ProgramSpec")
    if plan.plan_digest != with_plan_digest(plan).plan_digest:
        raise ActivationError("ExecutionPlan carries a stale plan_digest")
    _require_control_digests(plan.control_root)


def _require_control_digests(control: CompiledControlNode) -> None:
    for child in control.children:
        _require_control_digests(child)
    try:
        control.require_valid_control_digest()
    except ValueError as exc:
        raise ActivationError(str(exc)) from exc


def _nodes_by_path(root: ProgramNode) -> dict[tuple[str, ...], ProgramNode]:
    result: dict[tuple[str, ...], ProgramNode] = {}

    def visit(node: ProgramNode, path: tuple[str, ...]) -> None:
        result[path] = node
        if isinstance(node, Then):
            visit(node.first, path + ("first",))
            visit(node.second, path + ("second",))
        elif isinstance(node, MapOutput):
            visit(node.source, path + ("source",))
        elif isinstance(node, ZipOrdered):
            visit(node.left, path + ("left",))
            visit(node.right, path + ("right",))
        elif isinstance(node, TraverseOrdered):
            visit(node.element_program, path + ("element",))
        elif isinstance(node, Decide):
            for branch in node.branches:
                visit(branch.program, path + ("branch", branch.branch_id))
        elif not isinstance(node, (Identity, Pure, Atom)):
            raise ActivationError(f"unsupported Program node {type(node).__name__}")

    visit(root, ("root",))
    return result


def _controls_by_id(root: CompiledControlNode) -> dict[str, CompiledControlNode]:
    result: dict[str, CompiledControlNode] = {}

    def visit(control: CompiledControlNode) -> None:
        if control.control_id in result:
            raise ActivationError("compiled control IDs must be unique")
        result[control.control_id] = control
        for child in control.children:
            visit(child)

    visit(root)
    return result


def _completed_values(
    outputs: tuple[BoundStepValue, ...],
    steps: dict[str, CompiledStep],
    project_key: str,
) -> dict[str, BoundStepValue]:
    result: dict[str, BoundStepValue] = {}
    for output in outputs:
        step = steps.get(output.step_id)
        if step is None or step.step_kind not in {"EFFECT", "ADMISSION"}:
            raise ActivationError("completed output must bind an EFFECT/ADMISSION step")
        _require_value_ref(output.value_ref, project_key)
        if not _output_type_compatible(
            step.output_type,
            output.value_ref.object_type,
        ):
            raise ActivationError("completed output ValueRef type mismatch")
        existing = result.get(output.step_id)
        if existing is not None and existing != output:
            raise ActivationError("conflicting duplicate completed step output")
        result[output.step_id] = output
    return result


def _output_type_compatible(expected: object, actual: object) -> bool:
    expected_id = getattr(expected, "type_id", None)
    actual_id = getattr(actual, "type_id", None)
    if expected_id == "ClaimOrGap.v1":
        return actual_id in {"Claim.v1", "Gap.v1"}
    return object_type_digest(expected) == object_type_digest(actual)


def _completed_decisions(
    inputs: tuple[CompletedBranchDecision, ...],
    controls: dict[str, CompiledControlNode],
) -> dict[str, CompletedBranchDecision]:
    result: dict[str, CompletedBranchDecision] = {}
    for item in inputs:
        control = controls.get(item.control_id)
        if control is None or control.node_kind != "decide":
            raise ActivationError("completed branch decision has no exact control")
        if item.reduction.selected_branch_id not in {
            branch.branch_id for branch in control.decision_branches
        }:
            raise ActivationError("completed branch decision is unresolved or unknown")
        if not item.reduction.events or any(
            event.control_id != item.control_id
            or event.control_digest != control.control_digest
            for event in item.reduction.events
        ):
            raise ActivationError("completed branch decision lineage mismatch")
        existing = result.get(item.control_id)
        if existing is not None and existing != item:
            raise ActivationError("conflicting duplicate branch decision")
        result[item.control_id] = item
    return result


def _branch_is_released(
    step: CompiledStep,
    decisions: dict[str, CompletedBranchDecision],
) -> bool:
    if step.branch_id is None:
        return True
    if step.branch_control_id is None:
        raise ActivationError("branch step lacks branch_control_id")
    decision = decisions.get(step.branch_control_id)
    return (
        decision is not None and decision.reduction.selected_branch_id == step.branch_id
    )


def _dependency_values(
    step: CompiledStep,
    values: dict[str, BoundStepValue],
    steps: dict[str, CompiledStep],
    decisions: dict[str, CompletedBranchDecision],
) -> tuple[BoundStepValue, ...] | None:
    resolved: list[BoundStepValue] = []
    for step_id in step.dependencies:
        if step_id in values:
            resolved.append(values[step_id])
            continue
        dependency = steps.get(step_id)
        if (
            dependency is not None
            and dependency.branch_control_id is not None
            and dependency.branch_id is not None
        ):
            decision = decisions.get(dependency.branch_control_id)
            if (
                decision is not None
                and decision.reduction.selected_branch_id is not None
                and decision.reduction.selected_branch_id != dependency.branch_id
            ):
                # A join after Decide consumes only the selected branch; the
                # non-selected branch is a typed absence, not a missing value.
                continue
        return None
    return tuple(resolved)


def _require_node(
    nodes: dict[tuple[str, ...], ProgramNode],
    step: CompiledStep,
    expected: type[ProgramNode],
) -> Any:
    node = nodes.get(step.source_path)
    if node is None or not isinstance(node, expected):
        raise ActivationError(
            f"compiled {step.step_kind} source path does not bind exact Program node"
        )
    return node


def _require_atom(
    nodes: dict[tuple[str, ...], ProgramNode], step: CompiledStep
) -> Atom:
    path = step.source_path[:-1] if step.step_kind == "ADMISSION" else step.source_path
    node = nodes.get(path)
    if not isinstance(node, Atom):
        raise ActivationError("compiled effect/admission does not bind an exact Atom")
    if (
        step.operation_id != node.operation.operation_id
        or step.operation_contract_ref != node.operation.contract_ref
    ):
        raise ActivationError("compiled step/Atom operation binding mismatch")
    return node


def _require_transform_types(
    step: CompiledStep, input_type: Any, output_type: Any
) -> None:
    if object_type_digest(input_type) != object_type_digest(
        step.input_type
    ) or object_type_digest(output_type) != object_type_digest(step.output_type):
        raise ActivationError("TRANSFORM registry types do not match compiled step")


def _control_input(
    dependencies: tuple[BoundStepValue, ...],
    program_input: ProgramInput | None,
    step_id: str,
) -> ProgramInput:
    if len(dependencies) == 1:
        return ProgramInput(dependencies[0].value_ref, dependencies[0].value)
    if not dependencies and program_input is not None:
        return program_input
    raise ActivationError(f"DECIDE {step_id} requires exactly one control input")


def _require_decision_matches_input(
    decision: CompletedBranchDecision,
    control: CompiledControlNode,
    input_value: object,
) -> None:
    expected_input_digest = sha256_hex(input_value)
    if not decision.reduction.events or any(
        event.control_id != control.control_id
        or event.control_digest != control.control_digest
        or event.input_digest != expected_input_digest
        or event.discriminator_digest
        != (
            control.discriminator_ref.digest
            if control.discriminator_ref is not None
            else None
        )
        for event in decision.reduction.events
    ):
        raise ActivationError("branch decision does not bind the exact control input")


def _derive_value(
    *,
    program: ProgramSpec,
    plan: ExecutionPlan,
    step: CompiledStep,
    value: object,
    dependency_refs: tuple[ValueRef, ...],
    codec_id: str | None = None,
) -> tuple[BoundStepValue, ValueMaterialization]:
    exact_bytes = canonical_bytes(value)
    content_digest = sha256_digest_bytes(exact_bytes)
    provenance_digest = sha256_hex(
        {
            "schema_version": "mrw.activation-value-provenance.v1",
            "program_digest": program.program_digest,
            "plan_digest": plan.plan_digest,
            "step_id": step.step_id,
            "ordered_dependencies": tuple(
                _value_ref_payload(ref) for ref in dependency_refs
            ),
        }
    )
    value_identity_digest = sha256_hex(
        {
            "schema_version": "mrw.activation-value-identity.v1",
            "plan_digest": plan.plan_digest,
            "step_id": step.step_id,
            "content_digest": content_digest,
            "provenance_digest": provenance_digest,
        }
    )
    value_ref = ValueRef(
        value_id=f"activation:sha256:{value_identity_digest}",
        project_key=program.project_key,
        object_type=step.output_type,
        codec_id=codec_id or step.output_type.codec_id,
        content_digest=content_digest,
        storage_kind="runtime_blob_ref",
        store_id="successor_activation_values",
        store_version="1",
        storage_ref=f"runtime-blob:sha256:{content_digest}",
        byte_size=len(exact_bytes),
        provenance_digest=provenance_digest,
    )
    digest = sha256_hex(
        {
            "schema_version": "mrw.value-materialization.v1",
            "step_id": step.step_id,
            "value_ref": _value_ref_payload(value_ref),
            "exact_bytes_digest": content_digest,
            "ordered_dependencies": tuple(
                _value_ref_payload(ref) for ref in dependency_refs
            ),
        }
    )
    bound = BoundStepValue(step.step_id, value_ref, value)
    materialization = ValueMaterialization(
        step.step_id,
        value_ref,
        exact_bytes,
        value,
        dependency_refs,
        digest,
    )
    return bound, materialization


def _activation_descriptor(
    *,
    project_key: str,
    plan: ExecutionPlan,
    step: CompiledStep,
    atom: Atom,
    dependencies: tuple[BoundStepValue, ...],
) -> ReadyActivation:
    if step.operation_id is None:
        raise ActivationError("effect/admission step lacks operation_id")
    dependency_refs = tuple(item.value_ref for item in dependencies)
    static_refs = atom.operation.input_refs
    payload_ref = atom.operation.payload_ref
    for ref in dependency_refs + static_refs + (payload_ref,):
        _require_value_ref(ref, project_key)
    closure = {
        "schema_version": "mrw.activation-input-closure.v1",
        "plan_digest": plan.plan_digest,
        "step_id": step.step_id,
        "step_kind": step.step_kind,
        "ordered_dependency_refs": tuple(
            _value_ref_payload(ref) for ref in dependency_refs
        ),
        "static_atom_input_refs": tuple(_value_ref_payload(ref) for ref in static_refs),
        "payload_ref": _value_ref_payload(payload_ref),
    }
    input_closure_digest = sha256_hex(closure)
    descriptor = {
        **closure,
        "operation_id": step.operation_id,
        "operation_contract_digest": step.operation_contract_ref.contract_digest
        if step.operation_contract_ref is not None
        else None,
        "input_closure_digest": input_closure_digest,
    }
    return ReadyActivation(
        step_id=step.step_id,
        step_kind=step.step_kind,
        operation_id=step.operation_id,
        ordered_dependency_refs=dependency_refs,
        static_atom_input_refs=static_refs,
        payload_ref=payload_ref,
        input_closure_digest=input_closure_digest,
        activation_digest=sha256_hex(descriptor),
    )


def _thaw(value: object) -> object:
    if isinstance(value, frozenset):
        return sorted(value)
    if isinstance(value, tuple):
        if all(
            isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str)
            for item in value
        ):
            return {str(key): _thaw(item) for key, item in value}
        return [_thaw(item) for item in value]
    return value


_VALUE_REF_FIELDS = frozenset(
    {
        "value_id",
        "project_key",
        "object_type",
        "codec_id",
        "content_digest",
        "storage_kind",
        "store_id",
        "store_version",
        "storage_ref",
        "byte_size",
        "provenance_digest",
    }
)


def _unique_embedded_value_ref(value: object, *, project_key: str) -> ValueRef | None:
    found: list[ValueRef] = []

    def visit(item: object) -> None:
        if isinstance(item, dict):
            if _VALUE_REF_FIELDS <= item.keys():
                object_value = item["object_type"]
                if not isinstance(object_value, dict):
                    raise ActivationError("embedded ValueRef object_type is malformed")
                from app.successor_runtime.research.object_types import ObjectType

                ref = ValueRef(
                    value_id=str(item["value_id"]),
                    project_key=str(item["project_key"]),
                    object_type=ObjectType(
                        type_id=str(object_value["type_id"]),
                        schema_version=str(object_value["schema_version"]),
                        codec_id=str(object_value["codec_id"]),
                        canonical_codec_version=str(
                            object_value["canonical_codec_version"]
                        ),
                    ),
                    codec_id=str(item["codec_id"]),
                    content_digest=str(item["content_digest"]),
                    storage_kind=item["storage_kind"],  # type: ignore[arg-type]
                    store_id=str(item["store_id"]),
                    store_version=str(item["store_version"]),
                    storage_ref=str(item["storage_ref"]),
                    byte_size=int(item["byte_size"]),
                    provenance_digest=str(item["provenance_digest"]),
                )
                _require_value_ref(ref, project_key)
                found.append(ref)
                return
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    unique = tuple(dict.fromkeys(found))
    if len(unique) > 1:
        raise ActivationError("PURE literal contains multiple distinct ValueRefs")
    return unique[0] if unique else None


def _require_value_ref(ref: ValueRef, project_key: str) -> None:
    if ref.project_key != project_key:
        raise ActivationError("ValueRef project scope drift")
    for name in ("content_digest", "provenance_digest"):
        digest = getattr(ref, name)
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ActivationError(f"ValueRef.{name} must be canonical sha256 hex")
    if not ref.value_id or not ref.storage_ref or ref.byte_size < 0:
        raise ActivationError("ValueRef identity/storage binding is incomplete")


def _value_ref_payload(ref: ValueRef) -> dict[str, object]:
    return ref.to_plain()


__all__ = [
    "ActivationError",
    "ActivationResult",
    "BoundStepValue",
    "CompletedBranchDecision",
    "ProgramInput",
    "ReadyActivation",
    "ValueMaterialization",
    "activate_plan",
]
