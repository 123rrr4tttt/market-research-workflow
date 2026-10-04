"""Total, effect-free fold from Program AST to ExecutionPlan."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from app.successor_runtime.research.object_types import ObjectType

from .algebra import OperationContractCatalogSnapshot as ProgramCatalogSnapshot
from .algebra import ReturnContract
from .catalog import OperationContractCatalogSnapshot
from .checksum import sha256_hex
from .normalize import normalize_program
from .object_contracts import (
    OperationContractResolver,
)
from .plan import (
    CompiledAdmission,
    CompiledControlNode,
    CompiledDecisionBranch,
    CompiledStep,
    CompletionPolicy,
    ExecutionPlan,
    FrozenDependencyIndex,
    PlanReturnPolicy,
    ProgramPlanSourceMap,
    object_type_digest,
    with_plan_digest,
)
from .program import (
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
from .transforms import TransformRef, TransformRegistry
from .validate import ValidationFailure, frozen_return_contract, validate_program

COMPILER_ID = "mrw.functorial-successor.compiler"
COMPILER_VERSION = "1.0.0"
TRAVERSAL_MATERIALIZER_TRANSFORM = "mrw.traverse_ordered.materialize"
TRAVERSAL_MATERIALIZER_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class CompileFailure(Exception):
    code: str
    path: str
    message: str
    failures: tuple[ValidationFailure, ...] = ()

    def __str__(self) -> str:
        return f"{self.code} at {self.path}: {self.message}"


@dataclass(frozen=True, slots=True)
class _Fragment:
    control: CompiledControlNode
    steps: tuple[CompiledStep, ...]
    source_map: tuple[ProgramPlanSourceMap, ...]
    entries: tuple[str, ...]
    terminals: tuple[str, ...]


def _stable_id(
    prefix: str, path: tuple[str, ...], content_digest: str, role: str
) -> str:
    digest = sha256_hex({"path": path, "content_digest": content_digest, "role": role})
    return f"{prefix}-{digest[:24]}"


def _control(
    node: ProgramNode,
    path: tuple[str, ...],
    *,
    children: tuple[CompiledControlNode, ...] = (),
    step_ids: tuple[str, ...] = (),
    terminals: tuple[str, ...] = (),
    attributes: tuple[tuple[str, str], ...] = (),
    discriminator_ref: TransformRef | None = None,
    decision_branches: tuple[CompiledDecisionBranch, ...] = (),
) -> CompiledControlNode:
    digest = node.ast_digest()
    return CompiledControlNode(
        control_id=_stable_id("control", path, digest, node.node_kind),
        node_kind=node.node_kind,
        source_path=path,
        input_type=node.input_type,
        output_type=node.output_type,
        children=children,
        step_ids=step_ids,
        semantic_return_step_ids=terminals,
        source_digest=digest,
        attributes=attributes,
        discriminator_ref=discriminator_ref,
        decision_branches=decision_branches,
    )


def _source_map(
    node: ProgramNode,
    path: tuple[str, ...],
    control: CompiledControlNode,
    step_ids: tuple[str, ...],
    terminals: tuple[str, ...],
    branch_id: str | None = None,
) -> ProgramPlanSourceMap:
    return ProgramPlanSourceMap(
        source_path=path,
        source_kind=node.node_kind,
        source_digest=node.ast_digest(),
        control_id=control.control_id,
        step_ids=step_ids,
        semantic_return_step_ids=terminals,
        branch_id=branch_id,
    )


class _Compiler:
    def __init__(
        self,
        contract_resolver: OperationContractResolver,
        program_metadata: dict[str, Any],
    ) -> None:
        self.contract_resolver = contract_resolver
        self.program_metadata = program_metadata

    def fold(self, node: ProgramNode, path: tuple[str, ...]) -> _Fragment:
        if isinstance(node, Identity):
            control = _control(node, path)
            return _Fragment(
                control, (), (_source_map(node, path, control, (), ()),), (), ()
            )
        if isinstance(node, Pure):
            step_id = _stable_id("step", path, node.ast_digest(), "pure")
            step = CompiledStep(
                step_id=step_id,
                step_kind="PURE",
                source_path=path,
                input_type=node.input_type,
                output_type=node.output_type,
                dependencies=(),
                operation_id=None,
                operation_contract_ref=None,
                transform_ref=None,
                effect_profile_ref="PURE_TRANSFORM",
                resource_profile_ref=None,
                failure_profile_ref=None,
                authority_profile_ref=None,
                return_contract=node.return_contract,
                semantic_return_barrier=True,
                staged_output_only=False,
            )
            control = _control(node, path, step_ids=(step_id,), terminals=(step_id,))
            return _Fragment(
                control,
                (step,),
                (_source_map(node, path, control, (step_id,), (step_id,)),),
                (step_id,),
                (step_id,),
            )
        if isinstance(node, Atom):
            return self._atom(node, path)
        if isinstance(node, Then):
            first = self.fold(node.first, path + ("first",))
            second = self.fold(node.second, path + ("second",))
            added = first.terminals
            second_steps = tuple(
                replace(step, dependencies=_ordered_unique(added + step.dependencies))
                if step.step_id in second.entries
                else step
                for step in second.steps
            )
            terminals = second.terminals or first.terminals
            entries = first.entries or second.entries
            control = _control(
                node,
                path,
                children=(first.control, second.control),
                terminals=terminals,
            )
            own = _source_map(node, path, control, (), terminals)
            return _Fragment(
                control,
                first.steps + second_steps,
                (own,) + first.source_map + second.source_map,
                entries,
                terminals,
            )
        if isinstance(node, MapOutput):
            source = self.fold(node.source, path + ("source",))
            step_id = _stable_id(
                "step", path, node.transform_ref.ref_digest(), "map_output"
            )
            step = CompiledStep(
                step_id=step_id,
                step_kind="TRANSFORM",
                source_path=path,
                input_type=node.source.output_type,
                output_type=node.output_type,
                dependencies=source.terminals,
                operation_id=None,
                operation_contract_ref=None,
                transform_ref=node.transform_ref,
                effect_profile_ref="PURE_TRANSFORM",
                resource_profile_ref=None,
                failure_profile_ref=None,
                authority_profile_ref=None,
                return_contract=node.return_contract,
                semantic_return_barrier=True,
                staged_output_only=False,
            )
            control = _control(
                node,
                path,
                children=(source.control,),
                step_ids=(step_id,),
                terminals=(step_id,),
                attributes=(("transform", node.transform_ref.label()),),
            )
            own = _source_map(node, path, control, (step_id,), (step_id,))
            return _Fragment(
                control,
                source.steps + (step,),
                (own,) + source.source_map,
                source.entries or (step_id,),
                (step_id,),
            )
        if isinstance(node, ZipOrdered):
            left = self.fold(node.left, path + ("left",))
            right = self.fold(node.right, path + ("right",))
            # ZipOrdered only exposes potential parallelism.  P0-A has no
            # ParallelPolicy proof in the AST, so compile the declared
            # left-to-right serial fallback explicitly.
            right_steps = tuple(
                replace(
                    item,
                    dependencies=_ordered_unique(left.terminals + item.dependencies),
                )
                if item.step_id in right.entries
                else item
                for item in right.steps
            )
            step_id = _stable_id("step", path, node.merge_ref.ref_digest(), "merge")
            step = CompiledStep(
                step_id=step_id,
                step_kind="MERGE",
                source_path=path,
                input_type=node.input_type,
                output_type=node.output_type,
                dependencies=_ordered_unique(left.terminals + right.terminals),
                operation_id=None,
                operation_contract_ref=None,
                transform_ref=TransformRef(
                    node.merge_ref.name,
                    node.merge_ref.version,
                    node.merge_ref.digest,
                    "merge",
                ),
                effect_profile_ref="PURE_TRANSFORM",
                resource_profile_ref=None,
                failure_profile_ref=None,
                authority_profile_ref=None,
                return_contract=node.return_contract,
                semantic_return_barrier=True,
                staged_output_only=False,
            )
            control = _control(
                node,
                path,
                children=(left.control, right.control),
                step_ids=(step_id,),
                terminals=(step_id,),
                attributes=(
                    ("merge", node.merge_ref.label()),
                    ("order", "left,right"),
                    ("parallel_eligibility", "ABSENT"),
                    ("realization", "SERIAL_FALLBACK"),
                ),
            )
            own = _source_map(node, path, control, (step_id,), (step_id,))
            return _Fragment(
                control,
                left.steps + right_steps + (step,),
                (own,) + left.source_map + right.source_map,
                left.entries or right.entries or (step_id,),
                (step_id,),
            )
        if isinstance(node, Decide):
            discriminator_id = _stable_id(
                "step", path, node.discriminator_ref.ref_digest(), "decide"
            )
            decision_control_id = _stable_id(
                "control", path, node.ast_digest(), node.node_kind
            )
            branch_fragments: list[_Fragment] = []
            for branch_order, branch in enumerate(node.branches):
                fragment = self.fold(
                    branch.program, path + ("branch", branch.branch_id)
                )
                steps = tuple(
                    replace(
                        step,
                        dependencies=(
                            _ordered_unique((discriminator_id,) + step.dependencies)
                            if step.step_id in fragment.entries
                            else step.dependencies
                        ),
                        branch_id=branch.branch_id,
                        guard=branch.guard,
                        disposition="BRANCH_UNRESOLVED",
                        branch_control_id=decision_control_id,
                        branch_entry=step.step_id in fragment.entries,
                        branch_order=branch_order,
                    )
                    for step in fragment.steps
                )
                maps = tuple(
                    replace(item, branch_id=branch.branch_id)
                    for item in fragment.source_map
                )
                branch_fragments.append(replace(fragment, steps=steps, source_map=maps))
            discriminator = CompiledStep(
                step_id=discriminator_id,
                step_kind="DECIDE",
                source_path=path,
                input_type=node.input_type,
                output_type=node.input_type,
                dependencies=(),
                operation_id=None,
                operation_contract_ref=None,
                transform_ref=TransformRef(
                    node.discriminator_ref.name,
                    node.discriminator_ref.version,
                    node.discriminator_ref.digest,
                    "discriminator",
                ),
                effect_profile_ref="PURE_TRANSFORM",
                resource_profile_ref=None,
                failure_profile_ref=None,
                authority_profile_ref=None,
                return_contract=node.return_contract,
                semantic_return_barrier=False,
                staged_output_only=False,
                disposition="BRANCH_SELECTOR",
                branch_control_id=decision_control_id,
            )
            terminals = tuple(
                step_id
                for fragment in branch_fragments
                for step_id in fragment.terminals
            )
            control = _control(
                node,
                path,
                children=tuple(fragment.control for fragment in branch_fragments),
                step_ids=(discriminator_id,),
                terminals=terminals,
                attributes=(
                    ("discriminator", node.discriminator_ref.label()),
                    ("discriminator_id", node.discriminator_ref.name),
                    ("discriminator_version", node.discriminator_ref.version),
                    ("discriminator_digest", node.discriminator_ref.digest),
                    (
                        "branch_order",
                        ",".join(branch.branch_id for branch in node.branches),
                    ),
                    *tuple(
                        (f"branch_guard:{branch.branch_id}", branch.guard)
                        for branch in node.branches
                    ),
                ),
                discriminator_ref=TransformRef(
                    node.discriminator_ref.name,
                    node.discriminator_ref.version,
                    node.discriminator_ref.digest,
                    "discriminator",
                ),
                decision_branches=tuple(
                    CompiledDecisionBranch(
                        branch_id=branch.branch_id,
                        guard=branch.guard,
                        step_ids=tuple(step.step_id for step in fragment.steps),
                        entry_step_ids=fragment.entries,
                    )
                    for branch, fragment in zip(node.branches, branch_fragments)
                ),
            )
            own = _source_map(node, path, control, (discriminator_id,), terminals)
            return _Fragment(
                control,
                (discriminator,)
                + tuple(
                    step for fragment in branch_fragments for step in fragment.steps
                ),
                (own,)
                + tuple(
                    item
                    for fragment in branch_fragments
                    for item in fragment.source_map
                ),
                (discriminator_id,),
                terminals,
            )
        if isinstance(node, TraverseOrdered):
            return self._traverse_ordered(node, path)
        raise CompileFailure(
            "UNKNOWN_NODE_KIND",
            ".".join(path),
            f"unsupported node {type(node).__name__}",
        )

    def _traverse_ordered(
        self,
        node: TraverseOrdered,
        path: tuple[str, ...],
    ) -> _Fragment:
        policy = node.traversal_policy
        if policy not in {"STATIC_SHAPE", "MATERIALIZED_SHAPE"}:
            raise CompileFailure(
                "UNSUPPORTED_TRAVERSAL",
                ".".join(path),
                f"unsupported traversal policy {policy!r}",
            )

        static_shape_digest: str | None = None
        static_element_count: int | None = None
        if policy == "STATIC_SHAPE":
            candidate_digest = self.program_metadata.get("traversal_shape_digest")
            candidate_count = self.program_metadata.get("traversal_element_count")
            if (
                not isinstance(candidate_digest, str)
                or len(candidate_digest) != 64
                or any(char not in "0123456789abcdef" for char in candidate_digest)
                or not isinstance(candidate_count, int)
                or isinstance(candidate_count, bool)
                or candidate_count < 0
            ):
                raise CompileFailure(
                    "TRAVERSAL_SHAPE_BINDING_REQUIRED",
                    ".".join(path),
                    "STATIC_SHAPE requires exact traversal_shape_digest and "
                    "traversal_element_count Program metadata",
                )
            static_shape_digest = candidate_digest
            static_element_count = candidate_count

        binding = {
            "schema": "mrw.traverse-ordered.materialization-binding.v1",
            "policy": policy,
            "element_program_digest": node.element_program.ast_digest(),
            "static_shape_digest": static_shape_digest,
            "static_element_count": static_element_count,
            "output_order": "INPUT_INDEX",
            "realization": "SUCCESSOR_PROGRAM_EPOCH",
        }
        binding_digest = sha256_hex(binding)
        step_id = _stable_id(
            "step",
            path,
            binding_digest,
            "traverse_materialize",
        )
        transform = TransformRef(
            TRAVERSAL_MATERIALIZER_TRANSFORM,
            TRAVERSAL_MATERIALIZER_VERSION,
            binding_digest,
            "transform",
        )
        step = CompiledStep(
            step_id=step_id,
            step_kind="TRANSFORM",
            source_path=path,
            input_type=node.input_type,
            output_type=node.output_type,
            dependencies=(),
            operation_id=None,
            operation_contract_ref=None,
            transform_ref=transform,
            effect_profile_ref="PURE_TRANSFORM",
            resource_profile_ref=("mrw.traverse-ordered.materialization.resource.v1"),
            failure_profile_ref=("mrw.traverse-ordered.materialization.failure.v1"),
            authority_profile_ref=None,
            return_contract=node.return_contract,
            semantic_return_barrier=True,
            staged_output_only=False,
        )
        template = _control(
            node.element_program,
            path + ("element_template",),
            attributes=(("template", "true"),),
        )
        attributes = (
            ("traversal_policy", policy),
            ("element_program_digest", node.element_program.ast_digest()),
            ("binding_digest", binding_digest),
            ("output_order", "INPUT_INDEX"),
            ("realization", "SUCCESSOR_PROGRAM_EPOCH"),
            ("static_shape_digest", static_shape_digest or ""),
            (
                "static_element_count",
                "" if static_element_count is None else str(static_element_count),
            ),
        )
        control = _control(
            node,
            path,
            children=(template,),
            step_ids=(step_id,),
            terminals=(step_id,),
            attributes=attributes,
        )
        own = _source_map(node, path, control, (step_id,), (step_id,))
        template_map = _source_map(
            node.element_program,
            path + ("element_template",),
            template,
            (),
            (),
        )
        return _Fragment(
            control,
            (step,),
            (own, template_map),
            (step_id,),
            (step_id,),
        )

    def _atom(self, node: Atom, path: tuple[str, ...]) -> _Fragment:
        operation = node.operation
        contract = self.contract_resolver.resolve(operation.contract_ref)
        if contract is None:
            raise CompileFailure(
                "UNRESOLVED_OPERATION_CONTRACT",
                ".".join(path),
                f"full contract {operation.contract_ref.kind} is not resolvable by exact ref",
            )
        effective_return = frozen_return_contract(contract)
        if effective_return is None:
            raise CompileFailure(
                "UNKNOWN_RETURN_CONTRACT",
                ".".join(path),
                f"return contract {contract.return_contract_ref!r} is not frozen",
            )
        effect = contract.effect_profile_ref
        resource = contract.resource_profile_ref
        failure = contract.failure_profile_ref
        authority = contract.authority_profile_ref
        atom_digest = node.ast_digest()
        effect_id = _stable_id("step", path, atom_digest, "effect")
        needs_admission = effective_return.admission_required
        admission_id = (
            _stable_id("step", path, atom_digest, "admission")
            if needs_admission
            else None
        )
        admission = None
        if admission_id is not None:
            admission = CompiledAdmission(
                effect_id,
                admission_id,
                operation.operation_id,
                operation.contract_ref,
                effective_return,
            )
        effect_step = CompiledStep(
            step_id=effect_id,
            step_kind="EFFECT",
            source_path=path,
            input_type=node.input_type,
            output_type=node.output_type,
            dependencies=(),
            operation_id=operation.operation_id,
            operation_contract_ref=operation.contract_ref,
            transform_ref=None,
            effect_profile_ref=effect,
            resource_profile_ref=resource,
            failure_profile_ref=failure,
            authority_profile_ref=authority,
            return_contract=effective_return,
            semantic_return_barrier=not needs_admission,
            staged_output_only=needs_admission,
            return_contract_ref=contract.return_contract_ref,
            admission=admission,
        )
        steps: tuple[CompiledStep, ...] = (effect_step,)
        terminals = (effect_id,)
        step_ids = (effect_id,)
        if admission_id is not None:
            admission_step = CompiledStep(
                step_id=admission_id,
                step_kind="ADMISSION",
                source_path=path + ("admission",),
                input_type=node.output_type,
                output_type=node.output_type,
                dependencies=(effect_id,),
                operation_id=operation.operation_id,
                operation_contract_ref=operation.contract_ref,
                transform_ref=None,
                effect_profile_ref="ADMISSION",
                resource_profile_ref=resource,
                failure_profile_ref=failure,
                authority_profile_ref=authority,
                return_contract=effective_return,
                semantic_return_barrier=True,
                staged_output_only=False,
                return_contract_ref=contract.return_contract_ref,
                admission=admission,
            )
            steps += (admission_step,)
            terminals = (admission_id,)
            step_ids += (admission_id,)
        control = _control(
            node,
            path,
            step_ids=step_ids,
            terminals=terminals,
            attributes=(
                ("contract", operation.contract_ref.kind),
                ("return_contract", contract.return_contract_ref),
                ("composite", "effect+admission" if needs_admission else "effect"),
            ),
        )
        source = _source_map(node, path, control, step_ids, terminals)
        return _Fragment(control, steps, (source,), (effect_id,), terminals)


def _ordered_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _topological_order(steps: tuple[CompiledStep, ...]) -> tuple[str, ...]:
    known = {step.step_id for step in steps}
    if len(known) != len(steps):
        raise CompileFailure(
            "DUPLICATE_STEP_ID", "root", "compiled step IDs are not unique"
        )
    remaining = {step.step_id: set(step.dependencies) for step in steps}
    for step_id, dependencies in remaining.items():
        missing = dependencies - known
        if missing:
            raise CompileFailure(
                "MISSING_DEPENDENCY",
                step_id,
                f"missing dependencies: {sorted(missing)}",
            )
    order: list[str] = []
    source_order = [step.step_id for step in steps]
    while remaining:
        ready = [
            step_id
            for step_id in source_order
            if step_id in remaining and not remaining[step_id]
        ]
        if not ready:
            raise CompileFailure(
                "DEPENDENCY_CYCLE", "root", "compiled dependency graph contains a cycle"
            )
        for step_id in ready:
            order.append(step_id)
            remaining.pop(step_id)
            for dependencies in remaining.values():
                dependencies.discard(step_id)
    return tuple(order)


def _ready_order(
    steps: tuple[CompiledStep, ...], topological_order: tuple[str, ...]
) -> tuple[str, ...]:
    by_id = {step.step_id: step for step in steps}
    return tuple(
        step_id
        for step_id in topological_order
        if by_id[step_id].disposition != "BRANCH_UNRESOLVED"
    )


def compile_program(
    program: ProgramSpec,
    catalog: OperationContractCatalogSnapshot,
    *,
    operation_contracts: OperationContractResolver | None = None,
    transform_registry: TransformRegistry | None = None,
    merge_registry: TransformRegistry | None = None,
    discriminator_registry: TransformRegistry | None = None,
    compiler_id: str = COMPILER_ID,
    compiler_version: str = COMPILER_VERSION,
) -> ExecutionPlan:
    if operation_contracts is None or not callable(
        getattr(operation_contracts, "resolve", None)
    ):
        raise CompileFailure(
            "MISSING_OPERATION_CONTRACT_RESOLVER",
            "root",
            "compilation requires a full OperationContract resolver/registry",
        )
    validation_catalog = catalog
    if not hasattr(validation_catalog, "find"):
        validation_catalog = ProgramCatalogSnapshot(
            catalog_id=catalog.catalog_id,
            catalog_version=catalog.catalog_version,
            entries=catalog.entries,
            catalog_digest=catalog.catalog_digest
            or sha256_hex({"entries": catalog.entries}),
        )
    validation = validate_program(
        program,
        validation_catalog,
        transform_registry,
        merge_registry,
        discriminator_registry,
        require_contract_digest_match=True,
        operation_contract_resolver=operation_contracts,
    )
    if not validation.valid:
        first = validation.failures[0]
        raise CompileFailure(
            "INVALID_PROGRAM", first.path, first.message, validation.failures
        )
    if program.program_digest and program.program_digest != program.digest():
        raise CompileFailure(
            "PROGRAM_DIGEST_MISMATCH",
            "root",
            "program_digest does not bind canonical ProgramSpec bytes",
        )
    normalized = normalize_program(program)
    fragment = _Compiler(
        operation_contracts,
        dict(normalized.metadata),
    ).fold(normalized.root, ("root",))
    order = _topological_order(fragment.steps)
    step_by_id = {step.step_id: step for step in fragment.steps}
    ordered_steps = tuple(step_by_id[step_id] for step_id in order)
    return_contract = normalized.root.return_contract
    closure_contracts = [
        step.operation_contract_ref.contract_digest
        for step in ordered_steps
        if step.operation_contract_ref is not None
    ]
    effect_refs = [step.effect_profile_ref for step in ordered_steps]
    authority_refs = [step.authority_profile_ref for step in ordered_steps]
    resource_refs = [step.resource_profile_ref for step in ordered_steps]
    plan_seed = sha256_hex(
        {"program": normalized.digest(), "compiler": (compiler_id, compiler_version)}
    )
    plan = ExecutionPlan(
        plan_id="plan-" + plan_seed[:24],
        program_id=program.program_id,
        program_digest=normalized.digest(),
        input_type=normalized.input_type,
        output_type=normalized.output_type,
        compiler_id=compiler_id,
        compiler_version=compiler_version,
        control_root=fragment.control,
        ordered_steps=ordered_steps,
        dependency_index=FrozenDependencyIndex(
            tuple((step.step_id, step.dependencies) for step in ordered_steps)
        ),
        ready_order=_ready_order(ordered_steps, order),
        source_map=fragment.source_map,
        return_policy=PlanReturnPolicy(
            return_contract.success_modes,
            return_contract.failure_modes,
            return_contract.wait_modes,
            return_contract.cancel_modes,
            fragment.terminals,
        ),
        completion_policy=CompletionPolicy(),
        effect_closure_digest=sha256_hex(
            {"contracts": closure_contracts, "effects": effect_refs}
        ),
        authority_closure_digest=sha256_hex(
            {"contracts": closure_contracts, "authority": authority_refs}
        ),
        resource_closure_digest=sha256_hex(
            {"contracts": closure_contracts, "resources": resource_refs}
        ),
        plan_digest="",
    )
    return with_plan_digest(plan)


def compile(
    program: ProgramSpec, catalog: OperationContractCatalogSnapshot, **kwargs: Any
) -> ExecutionPlan:
    return compile_program(program, catalog, **kwargs)


def compose_plans(first: ExecutionPlan, second: ExecutionPlan) -> ExecutionPlan:
    if object_type_digest(first.output_type) != object_type_digest(second.input_type):
        raise CompileFailure(
            "TYPE_MISMATCH", "compose", "plan output/input types do not match"
        )
    if not first.ordered_steps:
        return second
    if not second.ordered_steps:
        return first
    second_entries = tuple(
        step.step_id for step in second.ordered_steps if not step.dependencies
    )
    second_steps = tuple(
        replace(
            step,
            dependencies=_ordered_unique(
                first.return_policy.exported_barrier_step_ids + step.dependencies
            ),
        )
        if step.step_id in second_entries
        else step
        for step in second.ordered_steps
    )
    steps = first.ordered_steps + second_steps
    control_digest = sha256_hex({"compose": (first.plan_digest, second.plan_digest)})
    control = CompiledControlNode(
        "control-" + control_digest[:24],
        "then",
        ("compose",),
        first.input_type,
        second.output_type,
        (first.control_root, second.control_root),
        (),
        second.return_policy.exported_barrier_step_ids,
        control_digest,
    )
    order = _topological_order(steps)
    contract = second.return_policy
    plan = ExecutionPlan(
        plan_id="plan-" + control_digest[:24],
        program_id=f"{first.program_id};{second.program_id}",
        program_digest=sha256_hex(
            {"then": (first.program_digest, second.program_digest)}
        ),
        input_type=first.input_type,
        output_type=second.output_type,
        compiler_id=first.compiler_id,
        compiler_version=first.compiler_version,
        control_root=control,
        ordered_steps=tuple(
            {step.step_id: step for step in steps}[item] for item in order
        ),
        dependency_index=FrozenDependencyIndex(
            tuple((step.step_id, step.dependencies) for step in steps)
        ),
        ready_order=_ready_order(steps, order),
        source_map=first.source_map + second.source_map,
        return_policy=PlanReturnPolicy(
            contract.success_modes,
            contract.failure_modes,
            contract.wait_modes,
            contract.cancel_modes,
            contract.exported_barrier_step_ids,
        ),
        completion_policy=second.completion_policy,
        effect_closure_digest=sha256_hex(
            {"then": (first.effect_closure_digest, second.effect_closure_digest)}
        ),
        authority_closure_digest=sha256_hex(
            {"then": (first.authority_closure_digest, second.authority_closure_digest)}
        ),
        resource_closure_digest=sha256_hex(
            {"then": (first.resource_closure_digest, second.resource_closure_digest)}
        ),
        plan_digest="",
    )
    return with_plan_digest(plan)


def map_plan_output(
    plan: ExecutionPlan, transform: TransformRef, target_type: ObjectType | None = None
) -> ExecutionPlan:
    target = target_type or plan.output_type
    step_id = _stable_id(
        "step", ("map_plan_output",), transform.ref_digest(), "map_output"
    )
    return_contract = ReturnContract(
        success_modes=plan.return_policy.success_modes,
        failure_modes=plan.return_policy.failure_modes,
        wait_modes=plan.return_policy.wait_modes,
        cancel_modes=plan.return_policy.cancel_modes,
        admission_required=any(
            step.return_contract.admission_required for step in plan.ordered_steps
        ),
    )
    step = CompiledStep(
        step_id,
        "TRANSFORM",
        ("map_plan_output",),
        plan.output_type,
        target,
        plan.return_policy.exported_barrier_step_ids,
        None,
        None,
        transform,
        "PURE_TRANSFORM",
        None,
        None,
        None,
        return_contract,
        True,
        False,
    )
    digest = sha256_hex(
        {"map": (plan.plan_digest, transform.ref_digest(), object_type_digest(target))}
    )
    control = CompiledControlNode(
        "control-" + digest[:24],
        "map_output",
        ("map_plan_output",),
        plan.input_type,
        target,
        (plan.control_root,),
        (step_id,),
        (step_id,),
        digest,
        (("transform", transform.label()),),
    )
    steps = plan.ordered_steps + (step,)
    order = _topological_order(steps)
    result = replace(
        plan,
        plan_id="plan-" + digest[:24],
        program_digest=digest,
        output_type=target,
        control_root=control,
        ordered_steps=steps,
        dependency_index=FrozenDependencyIndex(
            tuple((item.step_id, item.dependencies) for item in steps)
        ),
        ready_order=_ready_order(steps, order),
        return_policy=replace(plan.return_policy, exported_barrier_step_ids=(step_id,)),
        plan_digest="",
    )
    return with_plan_digest(result)
