"""Pure fixed-point activation for one exact Program/ExecutionPlan pair.

The activation core interprets only the plan's pure structure.  It never reads
or writes a store and never constructs a ``RuntimeAssignment``.  Content
addressed values produced by PURE/TRANSFORM/MERGE are returned as explicit
materialization descriptors; an outer project-plane adapter must durably bind
those bytes before publishing the corresponding EFFECT/ADMISSION activation.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any, Literal, cast

from functorial_kit import Failure

from app.successor_runtime.language.algebra import (
    ValueRef,
    sha256_digest_bytes,
    thaw_json_value,
)
from app.successor_runtime.research.object_types import ObjectType
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
    RegistryError,
    TransformRef,
    TransformRegistry,
)

from .reducer import (
    BranchDecisionReduction,
    BranchDecisionUnresolved,
    GuardExpressionError,
    RunSnapshot,
    StepSnapshot,
    reduce_branch_decision_result,
)
from .transitions import RunState, StepState
from .failure_policy import raise_runtime_failure, runtime_failure


ValueEncoder = Callable[[ObjectType, object], bytes]


def encode_language_value(object_type: ObjectType, value: object) -> bytes:
    """The existing language realization; domain installations supply theirs."""
    return canonical_bytes(value)


class ActivationError(ValueError):
    """The exact Program/Plan/value closure cannot be activated safely."""


def _activation_failure(
    message: object,
    *,
    code: str = "ACTIVATION_INVALID",
    exception_type: type[Exception] = ActivationError,
) -> Failure:
    return runtime_failure(
        code,
        message,
        exception_type,
        site="successor_runtime.runtime.activation.activate_plan",
    )


@dataclass(frozen=True, slots=True)
class ProgramInput:
    """Exact root input used only when a control has no step dependency."""

    value_ref: ValueRef
    value: object
    exact_bytes: bytes | None = field(default=None, kw_only=True)


@dataclass(frozen=True, slots=True)
class BoundStepValue:
    """One completed or purely derived step output and its exact value ref."""

    step_id: str
    value_ref: ValueRef
    value: object
    exact_bytes: bytes | None = field(default=None, kw_only=True)


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
class SettledTraversalValue(BoundStepValue):
    """Project-read settlement bound to its original ordered materialization."""

    materialization: TraversalMaterialization


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


def _activate_plan_impl(
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
    encode_value: ValueEncoder = encode_language_value,
) -> ActivationResult | Failure:
    """Interpret pure steps and discover ready effect/admission work.

    The fold is ordered and reaches a fixed point.  It preserves dependency
    order, invokes a MERGE callable as ``merge(left, right)``, and delegates
    every fresh DECIDE to :func:`reduce_branch_decision`.  Replaying identical
    inputs returns byte-for-byte equal descriptors; conflicting duplicate
    observations fail closed.
    """

    if not run_id:
        return _activation_failure("activation requires a run_id")
    try:
        normalized = normalize_program(program)
    except (TypeError, ValueError) as exc:
        return _activation_failure(str(exc))
    exact_plan = _require_exact_plan(normalized, plan)
    if isinstance(exact_plan, Failure):
        return exact_plan

    if program_input is not None:
        input_check = _require_value_ref(program_input.value_ref, program.project_key)
        if isinstance(input_check, Failure):
            return input_check

    nodes = _nodes_by_path(normalized.root)
    if isinstance(nodes, Failure):
        return nodes
    steps = {step.step_id: step for step in plan.ordered_steps}
    if len(steps) != len(plan.ordered_steps):
        return _activation_failure("ExecutionPlan step IDs must be unique")

    values = _completed_values(completed_outputs, steps, program.project_key, nodes, encode_value)
    if isinstance(values, Failure):
        return values
    settlements = {key: value for key, value in values.items() if isinstance(value, SettledTraversalValue)}
    values = {key: value for key, value in values.items() if key not in settlements}
    materializations: dict[str, ValueMaterialization] = {}
    activations: dict[str, ReadyActivation] = {}
    traversal_materializations: dict[str, TraversalMaterialization] = {}
    controls = _controls_by_id(plan.control_root)
    if isinstance(controls, Failure):
        return controls
    decisions = _completed_decisions(completed_branch_decisions, controls)
    if isinstance(decisions, Failure):
        return decisions

    progress = True
    while progress:
        progress = False
        for step in plan.ordered_steps:
            if step.step_id in values:
                continue
            released = _branch_is_released(step, decisions)
            if isinstance(released, Failure):
                return released
            if not released:
                continue

            dependencies = _dependency_values(
                step,
                values,
                steps,
                decisions,
            )
            if dependencies is None:
                continue

            if step.step_kind in {"TRANSFORM", "MERGE", "DECIDE"}:
                semantic = _semantic_dependencies(
                    plan.control_root, step, values, program_input,
                )
                if isinstance(semantic, Failure):
                    return semantic
                dependencies = semantic

            if step.step_kind == "PURE":
                node = _require_node(nodes, step, Pure)
                if isinstance(node, Failure):
                    return node
                value = thaw_json_value(node.literal_value)
                embedded_ref = _unique_embedded_value_ref(
                    value, project_key=program.project_key
                )
                if isinstance(embedded_ref, Failure):
                    return embedded_ref
                if embedded_ref is None:
                    derived = _derive_value(
                        program=program,
                        plan=plan,
                        step=step,
                        value=value,
                        dependency_refs=tuple(item.value_ref for item in dependencies),
                        codec_id=node.literal_codec,
                        encode_value=encode_value,
                    )
                    if isinstance(derived, Failure):
                        return derived
                    bound, materialization = derived
                    materializations[step.step_id] = materialization
                else:
                    bound = BoundStepValue(step.step_id, embedded_ref, value)
                values[step.step_id] = bound
                progress = True
                continue

            if step.step_kind == "TRANSFORM":
                traversal_node = nodes.get(step.source_path)
                if isinstance(traversal_node, TraverseOrdered):
                    settled = settlements.get(step.step_id)
                    settled_input = None
                    if settled is not None:
                        current = dependencies[0] if len(dependencies) == 1 else program_input if not dependencies else None
                        canonical = settled.materialization.input_ref
                        if current is None or any(
                            getattr(current.value_ref, field) != getattr(canonical, field)
                            for field in ("project_key", "object_type", "codec_id", "content_digest", "byte_size")
                        ):
                            return _activation_failure("settled traversal input binding drift")
                        settled_input = ProgramInput(canonical, current.value, exact_bytes=current.exact_bytes)
                    descriptor = _traversal_materialization_descriptor(
                        program=program,
                        plan=plan,
                        step=step,
                        node=traversal_node,
                        dependencies=() if settled_input is not None else dependencies,
                        program_input=settled_input or program_input,
                        encode_value=encode_value,
                    )
                    if isinstance(descriptor, Failure):
                        return descriptor
                    if settled is not None:
                        if descriptor != settled.materialization:
                            return _activation_failure("settled traversal materialization binding drift")
                        values[step.step_id] = settled
                        progress = True
                        continue
                    traversal_materializations.setdefault(
                        step.step_id,
                        descriptor,
                    )
                    continue
                if len(dependencies) != 1 or step.transform_ref is None:
                    return _activation_failure(
                        f"TRANSFORM {step.step_id} requires one dependency and exact ref"
                    )
                ref = TransformRef(
                    step.transform_ref.name,
                    step.transform_ref.version,
                    step.transform_ref.digest,
                    "transform",
                )
                entry = transform_registry.try_resolve_transform(ref)
                if isinstance(entry, Failure):
                    return _activation_failure(
                        entry.message,
                        code=entry.code,
                        exception_type=RegistryError,
                    )
                type_check = _require_transform_types(step, entry.input_type, entry.output_type)
                if isinstance(type_check, Failure):
                    return type_check
                try:
                    value = entry.callable(dependencies[0].value)
                except Exception as exc:
                    return _activation_failure(f"TRANSFORM {step.step_id} failed: {exc}")
                if entry.preserves_value_ref:
                    try:
                        source = dependencies[0]
                        original = source.exact_bytes
                        if original is None:
                            # Ref-bearing research values transport a reference
                            # representation; they do not claim its target bytes.
                            original = encode_value(source.value_ref.object_type, source.value)
                        bytes_equal = encode_value(source.value_ref.object_type, value) == original
                    except (TypeError, ValueError, OverflowError) as exc:
                        return _activation_failure(str(exc))
                    if not bytes_equal:
                        return _activation_failure(
                            f"TRANSFORM {step.step_id} changed bytes despite ValueRef-preserving binding"
                        )
                    if not _output_type_compatible(
                        step.output_type, dependencies[0].value_ref.object_type
                    ):
                        return _activation_failure(
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
                        exact_bytes=dependencies[0].exact_bytes,
                    )
                    progress = True
                    continue
                derived = _derive_value(
                    program=program,
                    plan=plan,
                    step=step,
                    value=value,
                    dependency_refs=(dependencies[0].value_ref,),
                    encode_value=encode_value,
                )
                if isinstance(derived, Failure):
                    return derived
                bound, materialization = derived
                values[step.step_id] = bound
                materializations[step.step_id] = materialization
                progress = True
                continue

            if step.step_kind == "MERGE":
                if len(dependencies) != 2 or step.transform_ref is None:
                    return _activation_failure(
                        f"MERGE {step.step_id} requires exact ordered left/right outputs"
                    )
                ref = MergeRef(
                    step.transform_ref.name,
                    step.transform_ref.version,
                    step.transform_ref.digest,
                    "merge",
                )
                entry = merge_registry.try_resolve_merge(ref)
                if isinstance(entry, Failure):
                    return _activation_failure(
                        entry.message,
                        code=entry.code,
                        exception_type=RegistryError,
                    )
                if object_type_digest(entry.output_type) != object_type_digest(
                    step.output_type
                ):
                    return _activation_failure(
                        "MERGE output type does not match compiled step"
                    )
                # This order is semantic.  It is not normalized or commuted.
                try:
                    value = entry.callable(dependencies[0].value, dependencies[1].value)
                except Exception as exc:
                    return _activation_failure(f"MERGE {step.step_id} failed: {exc}")
                dependency_refs = tuple(item.value_ref for item in dependencies)
                derived = _derive_value(
                    program=program,
                    plan=plan,
                    step=step,
                    value=value,
                    dependency_refs=dependency_refs,
                    encode_value=encode_value,
                )
                if isinstance(derived, Failure):
                    return derived
                bound, materialization = derived
                values[step.step_id] = bound
                materializations[step.step_id] = materialization
                progress = True
                continue

            if step.step_kind == "DECIDE":
                control_id = step.branch_control_id
                if control_id is None or control_id not in controls:
                    return _activation_failure("DECIDE step lacks its exact compiled control")
                decision_input = _control_input(
                    dependencies, program_input, step.step_id
                )
                if isinstance(decision_input, Failure):
                    return decision_input
                decision = decisions.get(control_id)
                if decision is None:
                    reduction = reduce_branch_decision_result(
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
                    if isinstance(reduction, Failure):
                        return reduction
                    decision = CompletedBranchDecision(control_id, reduction)
                    decisions[control_id] = decision
                decision_check = _require_decision_matches_input(
                    decision,
                    controls[control_id],
                    decision_input.value,
                )
                if isinstance(decision_check, Failure):
                    return decision_check
                if decision.reduction.selected_branch_id is None:
                    # No branch is released from an unresolved decision.
                    continue
                values[step.step_id] = BoundStepValue(
                    step.step_id, decision_input.value_ref, decision_input.value,
                    exact_bytes=decision_input.exact_bytes,
                )
                progress = True
                continue

            if step.step_kind in {"EFFECT", "ADMISSION"}:
                if step.step_id in already_activated_step_ids:
                    continue
                groups = activation_dependency_groups(plan, step)
                if isinstance(groups, Failure):
                    return groups
                dependencies = _dependency_values(
                    replace(step, dependencies=tuple(item.step_id for group in groups for item in group)),
                    values, steps, decisions,
                )
                if dependencies is None:
                    continue
                atom = _require_atom(nodes, step)
                if isinstance(atom, Failure):
                    return atom
                descriptor = _activation_descriptor(
                    project_key=program.project_key,
                    plan=plan,
                    step=step,
                    atom=atom,
                    dependencies=dependencies,
                )
                if isinstance(descriptor, Failure):
                    return descriptor
                activations.setdefault(step.step_id, descriptor)
                continue

            return _activation_failure(f"unsupported compiled step kind {step.step_kind!r}")

    if set(settlements) - set(values):
        return _activation_failure("settled traversal has no released dependency path")
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


def activate_plan_result(
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
    encode_value: ValueEncoder = encode_language_value,
) -> ActivationResult | Failure:
    """Return activation observations or a closed runtime failure value."""

    return _activate_plan_impl(
        run_id=run_id,
        program=program,
        plan=plan,
        completed_outputs=completed_outputs,
        completed_branch_decisions=completed_branch_decisions,
        program_input=program_input,
        transform_registry=transform_registry,
        merge_registry=merge_registry,
        discriminator_registry=discriminator_registry,
        already_activated_step_ids=already_activated_step_ids,
        encode_value=encode_value,
    )


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
    encode_value: ValueEncoder = encode_language_value,
) -> ActivationResult:
    """Legacy exception ABI over :func:`activate_plan_result`."""

    result = activate_plan_result(
        run_id=run_id,
        program=program,
        plan=plan,
        completed_outputs=completed_outputs,
        completed_branch_decisions=completed_branch_decisions,
        program_input=program_input,
        transform_registry=transform_registry,
        merge_registry=merge_registry,
        discriminator_registry=discriminator_registry,
        already_activated_step_ids=already_activated_step_ids,
        encode_value=encode_value,
    )
    if isinstance(result, Failure):
        exception_type = {
            "ACTIVATION_INVALID": ActivationError,
            "TRANSFORM_BINDING_MISSING": RegistryError,
            "TRANSFORM_REGISTRY_INVALID": RegistryError,
            "TRANSFORM_CALLABLE_INVALID": RegistryError,
            "BRANCH_DECISION_UNRESOLVED": BranchDecisionUnresolved,
            "BRANCH_CONTROL_INVALID": ValueError,
            "GUARD_EXPRESSION_INVALID": GuardExpressionError,
        }.get(result.code, ActivationError)
        raise_runtime_failure(result, exception_type)
    return result


def _traversal_materialization_descriptor(
    *,
    program: ProgramSpec,
    plan: ExecutionPlan,
    step: CompiledStep,
    node: TraverseOrdered,
    dependencies: tuple[BoundStepValue | ProgramInput, ...],
    program_input: ProgramInput | None,
    encode_value: ValueEncoder,
) -> TraversalMaterialization | Failure:
    if step.transform_ref is None or (
        step.transform_ref.name != "mrw.traverse_ordered.materialize"
        or step.transform_ref.version != "1.0.0"
    ):
        return _activation_failure("TraverseOrdered step lacks exact materializer binding")
    if len(dependencies) == 1:
        traversal_input = ProgramInput(
            dependencies[0].value_ref,
            dependencies[0].value,
            exact_bytes=dependencies[0].exact_bytes,
        )
    elif not dependencies and program_input is not None:
        traversal_input = program_input
    else:
        return _activation_failure(
            f"TraverseOrdered {step.step_id} requires exactly one sequence input"
        )
    value_ref_check = _require_value_ref(traversal_input.value_ref, program.project_key)
    if isinstance(value_ref_check, Failure):
        return value_ref_check
    if not _output_type_compatible(
        step.input_type,
        traversal_input.value_ref.object_type,
    ):
        return _activation_failure("TraverseOrdered input ValueRef type mismatch")
    if not isinstance(traversal_input.value, (tuple, list)):
        return _activation_failure("TraverseOrdered input must be a finite sequence")

    elements = tuple(traversal_input.value)
    try:
        exact_input_bytes = _bound_value_bytes(traversal_input, encode_value)
    except (TypeError, ValueError, OverflowError) as exc:
        return _activation_failure(str(exc))
    if traversal_input.value_ref.codec_id != step.input_type.codec_id:
        return _activation_failure("TraverseOrdered input codec drift")
    if traversal_input.value_ref.byte_size != len(exact_input_bytes):
        return _activation_failure("TraverseOrdered input byte-size drift")
    try:
        element_digests = traversal_element_digests(elements)
        input_sequence_digest = sha256_digest_bytes(exact_input_bytes)
        shape_digest = traversal_shape_digest(elements)
    except (TypeError, ValueError, OverflowError) as exc:
        return _activation_failure(str(exc))
    if traversal_input.value_ref.content_digest != input_sequence_digest:
        return _activation_failure("TraverseOrdered input content digest mismatch")

    metadata = dict(program.metadata)
    static_shape_digest: str | None = None
    static_element_count: int | None = None
    if node.traversal_policy == "STATIC_SHAPE":
        static_shape_digest = metadata.get("traversal_shape_digest")
        static_element_count = metadata.get("traversal_element_count")
        if static_shape_digest != shape_digest or static_element_count != len(elements):
            return _activation_failure("STATIC_SHAPE traversal input drift")
    elif node.traversal_policy != "MATERIALIZED_SHAPE":
        return _activation_failure("unsupported traversal policy")

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
        return _activation_failure("TraverseOrdered materializer binding drift")
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


def _require_exact_plan(program: ProgramSpec, plan: ExecutionPlan) -> None | Failure:
    try:
        if program.program_id != plan.program_id:
            return _activation_failure("Program/ExecutionPlan program_id mismatch")
        if program.program_digest != program.digest():
            return _activation_failure("ProgramSpec carries a stale program_digest")
        if plan.program_digest != program.program_digest:
            return _activation_failure("ExecutionPlan does not bind the normalized ProgramSpec")
        if plan.plan_digest != with_plan_digest(plan).plan_digest:
            return _activation_failure("ExecutionPlan carries a stale plan_digest")
        return _require_control_digests(plan.control_root)
    except (AttributeError, TypeError, ValueError) as exc:
        return _activation_failure(str(exc))


def _require_control_digests(control: CompiledControlNode) -> None | Failure:
    for child in control.children:
        result = _require_control_digests(child)
        if isinstance(result, Failure):
            return result
    try:
        control.require_valid_control_digest()
    except ValueError as exc:
        return _activation_failure(str(exc))
    return None


def _nodes_by_path(root: ProgramNode) -> dict[tuple[str, ...], ProgramNode] | Failure:
    result: dict[tuple[str, ...], ProgramNode] = {}

    def visit(node: ProgramNode, path: tuple[str, ...]) -> Failure | None:
        result[path] = node
        if isinstance(node, Then):
            child_result = visit(node.first, path + ("first",))
            if isinstance(child_result, Failure):
                return child_result
            return visit(node.second, path + ("second",))
        elif isinstance(node, MapOutput):
            return visit(node.source, path + ("source",))
        elif isinstance(node, ZipOrdered):
            child_result = visit(node.left, path + ("left",))
            if isinstance(child_result, Failure):
                return child_result
            return visit(node.right, path + ("right",))
        elif isinstance(node, TraverseOrdered):
            return visit(node.element_program, path + ("element",))
        elif isinstance(node, Decide):
            for branch in node.branches:
                child_result = visit(branch.program, path + ("branch", branch.branch_id))
                if isinstance(child_result, Failure):
                    return child_result
        elif not isinstance(node, (Identity, Pure, Atom)):
            return _activation_failure(f"unsupported Program node {type(node).__name__}")
        return None

    visit_result = visit(root, ("root",))
    if isinstance(visit_result, Failure):
        return visit_result
    return result


def _controls_by_id(root: CompiledControlNode) -> dict[str, CompiledControlNode] | Failure:
    result: dict[str, CompiledControlNode] = {}

    def visit(control: CompiledControlNode) -> Failure | None:
        if control.control_id in result:
            return _activation_failure("compiled control IDs must be unique")
        result[control.control_id] = control
        for child in control.children:
            child_result = visit(child)
            if isinstance(child_result, Failure):
                return child_result
        return None

    result_value = visit(root)
    if isinstance(result_value, Failure):
        return result_value
    return result


def _bound_value_bytes(value: BoundStepValue | ProgramInput, encode_value: ValueEncoder) -> bytes:
    if value.value_ref.codec_id != value.value_ref.object_type.codec_id:
        raise_runtime_failure(
            _activation_failure("typed value codec identity drift"), ActivationError
        )
    encoded = encode_value(value.value_ref.object_type, value.value)
    exact = value.exact_bytes if value.exact_bytes is not None else encoded
    if exact != encoded:
        raise_runtime_failure(
            _activation_failure("typed value codec/semantic bytes drift"), ActivationError
        )
    if len(exact) != value.value_ref.byte_size or sha256_digest_bytes(exact) != value.value_ref.content_digest:
        raise_runtime_failure(
            _activation_failure("typed value exact bytes binding drift"), ActivationError
        )
    return exact


def _completed_values(
    outputs: tuple[BoundStepValue, ...],
    steps: dict[str, CompiledStep],
    project_key: str,
    nodes: dict[tuple[str, ...], ProgramNode],
    encode_value: ValueEncoder,
) -> dict[str, BoundStepValue] | Failure:
    result: dict[str, BoundStepValue] = {}
    for output in outputs:
        step = steps.get(output.step_id)
        if step is None or (isinstance(output, SettledTraversalValue) and (
            step.step_kind != "TRANSFORM" or not isinstance(nodes.get(step.source_path), TraverseOrdered)
            or output.materialization.step_id != output.step_id
        )) or (not isinstance(output, SettledTraversalValue) and step.step_kind not in {"EFFECT", "ADMISSION"}):
            return _activation_failure("completed output must bind an EFFECT/ADMISSION step")
        value_ref_check = _require_value_ref(output.value_ref, project_key)
        if isinstance(value_ref_check, Failure):
            return value_ref_check
        if not _output_type_compatible(
            step.output_type,
            output.value_ref.object_type,
        ):
            return _activation_failure("completed output ValueRef type mismatch")
        if output.exact_bytes is not None:
            try:
                _bound_value_bytes(output, encode_value)
            except (TypeError, ValueError, OverflowError) as exc:
                return _activation_failure(str(exc))
        if isinstance(output, SettledTraversalValue):
            count = cast(object, output.materialization.element_count)
            raw_value: object = output.value
            sequence = cast(tuple[object, ...] | list[object], raw_value) if isinstance(raw_value, (tuple, list)) else None
            if (not isinstance(count, int) or isinstance(count, bool) or count < 0
                    or sequence is None or len(sequence) != count):
                return _activation_failure("settled traversal output cardinality drift")
            try:
                exact = _bound_value_bytes(output, encode_value)
            except (TypeError, ValueError, OverflowError) as exc:
                return _activation_failure(str(exc))
            if sha256_digest_bytes(exact) != output.value_ref.content_digest or len(exact) != output.value_ref.byte_size:
                return _activation_failure("settled traversal output bytes drift")
        existing = result.get(output.step_id)
        if existing is not None and existing != output:
            return _activation_failure("conflicting duplicate completed step output")
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
) -> dict[str, CompletedBranchDecision] | Failure:
    result: dict[str, CompletedBranchDecision] = {}
    for item in inputs:
        control = controls.get(item.control_id)
        if control is None or control.node_kind != "decide":
            return _activation_failure("completed branch decision has no exact control")
        if item.reduction.selected_branch_id not in {
            branch.branch_id for branch in control.decision_branches
        }:
            return _activation_failure("completed branch decision is unresolved or unknown")
        if not item.reduction.events or any(
            event.control_id != item.control_id
            or event.control_digest != control.control_digest
            for event in item.reduction.events
        ):
            return _activation_failure("completed branch decision lineage mismatch")
        existing = result.get(item.control_id)
        if existing is not None and existing != item:
            return _activation_failure("conflicting duplicate branch decision")
        result[item.control_id] = item
    return result


def _branch_is_released(
    step: CompiledStep,
    decisions: dict[str, CompletedBranchDecision],
) -> bool | Failure:
    if step.branch_id is None:
        return True
    if step.branch_control_id is None:
        return _activation_failure("branch step lacks branch_control_id")
    decision = decisions.get(step.branch_control_id)
    return (
        decision is not None and decision.reduction.selected_branch_id == step.branch_id
    )


def semantic_input_step_ids(
    control: CompiledControlNode, target_path: tuple[str, ...],
    inherited: tuple[str, ...] = (),
) -> tuple[str, ...] | Failure:
    """Project data sources from the original control tree, independently of order."""
    if control.source_path == target_path:
        return inherited
    for index, child in enumerate(control.children):
        if target_path[:len(child.source_path)] != child.source_path:
            continue
        incoming = inherited
        if control.node_kind == "then" and index == 1:
            incoming = control.children[0].semantic_return_step_ids or inherited
        elif control.node_kind == "decide":
            incoming = control.step_ids
        elif control.node_kind == "traverse_ordered":
            return _activation_failure("traversal element requires its materialized Program")
        return semantic_input_step_ids(child, target_path, incoming)
    return _activation_failure("source path is absent from compiled control structure")


def activation_dependency_groups(
    plan: ExecutionPlan, step: CompiledStep,
) -> tuple[tuple[CompiledStep, ...], ...] | Failure:
    """Bind order witnesses and missing data sources once for execute and reload."""
    semantic = (() if step.step_kind == "ADMISSION"
                else semantic_input_step_ids(plan.control_root, step.source_path))
    if isinstance(semantic, Failure):
        return semantic
    source_ids = tuple(dict.fromkeys((*step.dependencies, *semantic)))
    by_step = {item.step_id: item for item in plan.ordered_steps}
    groups: list[list[CompiledStep]] = []
    for source_id in source_ids:
        dependency = by_step.get(source_id)
        if dependency is None:
            return _activation_failure("activation dependency is absent from Plan")
        control_id = dependency.branch_control_id
        if control_id is None or dependency.branch_id is None:
            groups.append([dependency])
        else:
            alternative = next((group for group in groups
                                if group[0].branch_control_id == control_id
                                and all(item.branch_id != dependency.branch_id for item in group)), None)
            if alternative is None:
                groups.append([dependency])
            else:
                alternative.append(dependency)
    return tuple(tuple(group) for group in groups)


def _semantic_dependencies(
    root: CompiledControlNode, step: CompiledStep,
    values: dict[str, BoundStepValue], program_input: ProgramInput | None,
) -> tuple[BoundStepValue | ProgramInput, ...] | Failure:
    incoming = semantic_input_step_ids(root, step.source_path)
    if isinstance(incoming, Failure):
        return incoming
    control = root
    while control.source_path != step.source_path:
        control = next(child for child in control.children
                       if step.source_path[:len(child.source_path)] == child.source_path)
    sources = ((incoming, control.input_type),)
    if control.node_kind in {"map_output", "zip_ordered"}:
        sources = tuple((child.semantic_return_step_ids or incoming, child.output_type)
                        for child in control.children)
    resolved: list[BoundStepValue | ProgramInput] = []
    for source_ids, expected_type in sources:
        selected = tuple(values[source_id] for source_id in source_ids if source_id in values)
        if not source_ids and program_input is not None:
            selected = (program_input,)
        if len(selected) != 1:
            return _activation_failure(f"{step.step_kind} requires one exact value per semantic input")
        value = selected[0]
        if not _output_type_compatible(expected_type, value.value_ref.object_type):
            return _activation_failure("compiled semantic input type mismatch")
        resolved.append(value)
    return tuple(resolved)


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
) -> Any | Failure:
    node = nodes.get(step.source_path)
    if node is None or not isinstance(node, expected):
        return _activation_failure(
            f"compiled {step.step_kind} source path does not bind exact Program node"
        )
    return node


def _require_atom(
    nodes: dict[tuple[str, ...], ProgramNode], step: CompiledStep
) -> Atom | Failure:
    path = step.source_path[:-1] if step.step_kind == "ADMISSION" else step.source_path
    node = nodes.get(path)
    if not isinstance(node, Atom):
        return _activation_failure("compiled effect/admission does not bind an exact Atom")
    if (
        step.operation_id != node.operation.operation_id
        or step.operation_contract_ref != node.operation.contract_ref
    ):
        return _activation_failure("compiled step/Atom operation binding mismatch")
    return node


def _require_transform_types(
    step: CompiledStep, input_type: Any, output_type: Any
) -> None | Failure:
    if object_type_digest(input_type) != object_type_digest(
        step.input_type
    ) or object_type_digest(output_type) != object_type_digest(step.output_type):
        return _activation_failure("TRANSFORM registry types do not match compiled step")
    return None


def _control_input(
    dependencies: tuple[BoundStepValue | ProgramInput, ...],
    program_input: ProgramInput | None,
    step_id: str,
) -> ProgramInput | Failure:
    if len(dependencies) == 1:
        return ProgramInput(dependencies[0].value_ref, dependencies[0].value,
                            exact_bytes=dependencies[0].exact_bytes)
    if not dependencies and program_input is not None:
        return program_input
    return _activation_failure(f"DECIDE {step_id} requires exactly one control input")


def _require_decision_matches_input(
    decision: CompletedBranchDecision,
    control: CompiledControlNode,
    input_value: object,
) -> None | Failure:
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
        return _activation_failure("branch decision does not bind the exact control input")
    return None


def _derive_value(
    *,
    program: ProgramSpec,
    plan: ExecutionPlan,
    step: CompiledStep,
    value: object,
    dependency_refs: tuple[ValueRef, ...],
    codec_id: str | None = None,
    encode_value: ValueEncoder,
) -> tuple[BoundStepValue, ValueMaterialization] | Failure:
    try:
        exact_bytes = encode_value(step.output_type, value)
    except (TypeError, ValueError, OverflowError) as exc:
        return _activation_failure(str(exc))
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
    bound = BoundStepValue(step.step_id, value_ref, value, exact_bytes=exact_bytes)
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
) -> ReadyActivation | Failure:
    if step.operation_id is None:
        return _activation_failure("effect/admission step lacks operation_id")
    dependency_refs = tuple(item.value_ref for item in dependencies)
    static_refs = atom.operation.input_refs
    payload_ref = atom.operation.payload_ref
    for ref in dependency_refs + static_refs + (payload_ref,):
        value_ref_check = _require_value_ref(ref, project_key)
        if isinstance(value_ref_check, Failure):
            return value_ref_check
    return finalize_activation_descriptor(plan, ReadyActivation(
        step_id=step.step_id, step_kind=step.step_kind, operation_id=step.operation_id,
        ordered_dependency_refs=dependency_refs, static_atom_input_refs=static_refs,
        payload_ref=payload_ref, input_closure_digest="0" * 64, activation_digest="0" * 64,
    ))


def finalize_activation_descriptor(plan: ExecutionPlan, descriptor: ReadyActivation) -> ReadyActivation:
    """One original closure digest rule for pure activation and project rebinding."""
    closure = {
        "schema_version": "mrw.activation-input-closure.v1",
        "plan_digest": plan.plan_digest,
        "step_id": descriptor.step_id,
        "step_kind": descriptor.step_kind,
        "ordered_dependency_refs": tuple(ref.to_plain() for ref in descriptor.ordered_dependency_refs),
        "static_atom_input_refs": tuple(ref.to_plain() for ref in descriptor.static_atom_input_refs),
        "payload_ref": descriptor.payload_ref.to_plain(),
    }
    digest = sha256_hex(closure)
    step = next(item for item in plan.ordered_steps if item.step_id == descriptor.step_id)
    return replace(descriptor, input_closure_digest=digest, activation_digest=sha256_hex({
        **closure, "operation_id": descriptor.operation_id,
        "operation_contract_digest": step.operation_contract_ref.contract_digest
        if step.operation_contract_ref is not None else None,
        "input_closure_digest": digest,
    }))


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


def _unique_embedded_value_ref(value: object, *, project_key: str) -> ValueRef | None | Failure:
    found: list[ValueRef] = []

    def visit(item: object) -> Failure | None:
        if isinstance(item, dict):
            if _VALUE_REF_FIELDS <= item.keys():
                object_value = item["object_type"]
                if not isinstance(object_value, dict):
                    return _activation_failure("embedded ValueRef object_type is malformed")
                from app.successor_runtime.research.object_types import ObjectType

                try:
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
                except (KeyError, TypeError, ValueError, OverflowError) as exc:
                    return _activation_failure(str(exc))
                value_ref_check = _require_value_ref(ref, project_key)
                if isinstance(value_ref_check, Failure):
                    return value_ref_check
                found.append(ref)
                return None
            for child in item.values():
                result = visit(child)
                if isinstance(result, Failure):
                    return result
        elif isinstance(item, list):
            for child in item:
                result = visit(child)
                if isinstance(result, Failure):
                    return result
        return None

    visit_result = visit(value)
    if isinstance(visit_result, Failure):
        return visit_result
    unique = tuple(dict.fromkeys(found))
    if len(unique) > 1:
        return _activation_failure("PURE literal contains multiple distinct ValueRefs")
    return unique[0] if unique else None


def _require_value_ref(ref: ValueRef, project_key: str) -> None | Failure:
    try:
        if ref.project_key != project_key:
            return _activation_failure("ValueRef project scope drift")
        for name in ("content_digest", "provenance_digest"):
            digest = getattr(ref, name)
            if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
                return _activation_failure(f"ValueRef.{name} must be canonical sha256 hex")
        if not ref.value_id or not ref.storage_ref or ref.byte_size < 0:
            return _activation_failure("ValueRef identity/storage binding is incomplete")
        return None
    except (AttributeError, TypeError, ValueError) as exc:
        return _activation_failure(str(exc))


def _value_ref_payload(ref: ValueRef) -> dict[str, object]:
    return ref.to_plain()


__all__ = [
    "ActivationError",
    "ActivationResult",
    "BoundStepValue",
    "CompletedBranchDecision",
    "ProgramInput",
    "ReadyActivation",
    "SettledTraversalValue",
    "ValueMaterialization",
    "semantic_input_step_ids",
    "activation_dependency_groups",
    "finalize_activation_descriptor",
    "activate_plan",
    "activate_plan_result",
]
