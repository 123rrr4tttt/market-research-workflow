"""Caller-owned PostgreSQL activation for the P0-C first specimen.

The adapter re-opens one exact Program/Plan/QualifiedPlan closure, delegates
all pure interpretation to :func:`activate_plan`, materializes derived values
in the project value owner, and publishes only opaque value refs and runtime
work in the public control plane.  It never commits or rolls back its caller's
transaction.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Literal, Protocol, TypeGuard

from functorial_kit import Failure

from sqlalchemy import MetaData, insert, select, update
from sqlalchemy.engine import Connection, RowMapping

from app.successor_runtime.language.algebra import ValueRef
from app.successor_runtime.language.catalog import OperationContractCatalogSnapshot, OperationContractRegistry
from app.successor_runtime.language.compile import (
    TRAVERSAL_MATERIALIZER_TRANSFORM,
    compile_program,
)
from app.successor_runtime.language.checksum import sha256_hex
from app.successor_runtime.language.plan import (
    CompiledControlNode,
    CompiledStep,
    ExecutionPlan,
)
from app.successor_runtime.language.program import (
    Atom,
    Decide,
    MapOutput,
    ProgramNode,
    ProgramSpec,
    Then,
    TraverseOrdered,
    ZipOrdered,
    program_atoms,
)
from app.successor_runtime.language.transforms import TransformRegistry
from app.successor_runtime.research.object_types import OBJECT_TYPE_BY_ID
from app.successor_runtime.research.object_types import ObjectType
from app.successor_runtime.runtime.activation import (
    ActivationResult,
    BoundStepValue,
    ReadyActivation,
    SettledTraversalValue,
    TraversalMaterialization,
    ValueMaterialization,
    ValueEncoder,
    encode_language_value,
    activate_plan,
    semantic_input_step_ids,
    activation_dependency_groups,
    finalize_activation_descriptor,
)
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompiledAdmissionBinding,
    CompiledStepRole,
    HandlerBindingKind,
    InterpreterBinding,
    RecoveryBinding,
    ReturnContractBinding,
    RuntimeAssignment,
    canonical_digest,
    require_digest,
)
from app.successor_runtime.runtime.ports import RuntimeScope
from app.successor_runtime.runtime.qualification import (
    QualifiedPlan,
    StepAuthorizationBinding,
    require_current_authority,
)
from app.successor_runtime.runtime.resources import QueueEligibility

from .models import PUBLIC_TABLES, ProjectTables, project_tables
from .authority_provider import PostgresAuthorityProvider
from .idempotency import IdempotencyBinding, IdempotencyRepository
from .plans import PlanRepository
from .programs import ProgramRepository
from .research_ledger import one_mapping
from .runtime_journal import (
    ExactBindingConflict,
    RecordNotFound,
    StaleRevisionError,
    runtime_scope_key,
    utc_now,
    validate_authorization_row,
    validate_qualification_row,
    ExactQualificationBinding,
    RuntimeJournalRepository,
)
from .runtime_lifecycle import (
    ActivateQualification, AssignmentEnvelope, AttachPlan, RequestCancel, RuntimeLifecycleRepository,
    SubmitRun, assignment_values,
)
from .qualification_store import QualificationStoreRepository
from .runtime_values import RuntimeValueBinding, RuntimeValueRepository
from .values import ValueRepository, derive_value_write_intent_digest

RuntimeRow = Mapping[str, object] | RowMapping


class FirstSpecimenActivationError(RuntimeError):
    """The persisted run cannot be activated without weakening exactness."""


@dataclass(frozen=True, slots=True)
class ActivationCatalogEntry:
    """Immutable runtime realization for one operation contract digest."""

    operation_contract_digest: str
    interpreter_binding: InterpreterBinding
    recovery_binding: RecoveryBinding
    queue_eligibility: QueueEligibility
    required_node_profile_selector: str
    resource_policy_digest: str
    fairness_key: str
    effect_class: str
    max_attempts: int = 1
    declared_priority: int = 0
    external_gate_required: bool = False

    def __post_init__(self) -> None:
        require_digest(self.operation_contract_digest, "operation_contract_digest")
        require_digest(self.resource_policy_digest, "resource_policy_digest")
        if (
            self.interpreter_binding.operation_contract_digest
            != self.operation_contract_digest
        ):
            raise ValueError("catalog interpreter/operation contract drift")
        if (
            self.recovery_binding.interpreter_profile_digest
            != self.interpreter_binding.interpreter_profile_digest
        ):
            raise ValueError("catalog recovery/interpreter profile drift")
        if not self.required_node_profile_selector or not self.fairness_key:
            raise ValueError("catalog node profile and fairness key are required")
        if not self.effect_class or self.max_attempts < 1 or self.declared_priority < 0:
            raise ValueError("catalog effect/retry/priority binding is invalid")


@dataclass(frozen=True, slots=True)
class OperationActivationCatalog:
    """Exact digest index plus the registries needed by the pure fold."""

    entries: tuple[ActivationCatalogEntry, ...]
    transform_registry: TransformRegistry
    merge_registry: TransformRegistry
    discriminator_registry: TransformRegistry
    encode_value: ValueEncoder = encode_language_value

    def __post_init__(self) -> None:
        digests = tuple(item.operation_contract_digest for item in self.entries)
        if not digests or len(digests) != len(set(digests)):
            raise ValueError("activation catalog operation digests must be non-empty/unique")

    def entry_for(self, operation_contract_digest: str) -> ActivationCatalogEntry:
        matches = tuple(
            item
            for item in self.entries
            if item.operation_contract_digest == operation_contract_digest
        )
        if len(matches) != 1:
            raise FirstSpecimenActivationError(
                "activation catalog lacks one exact operation realization"
            )
        return matches[0]


@dataclass(frozen=True, slots=True)
class ActivationTrigger:
    """Bounded scheduling facts supplied by the caller."""

    due_at: datetime
    trace_id: str
    observed_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.due_at.tzinfo is None:
            raise ValueError("activation due_at must be timezone-aware")
        if self.observed_at is not None and self.observed_at.tzinfo is None:
            raise ValueError("activation observed_at must be timezone-aware")
        if not self.trace_id:
            raise ValueError("activation trace_id is required")


@dataclass(frozen=True, slots=True)
class ActivationReceipt:
    run_id: str
    previous_run_revision: int
    run_revision: int
    materialized_value_ids: tuple[str, ...]
    activated_step_ids: tuple[str, ...]
    work_item_ids: tuple[str, ...]
    event_seqs: tuple[int, ...]
    awaiting_external_gate_step_ids: tuple[str, ...]
    result: ActivationResult


def selected_completion_steps(
    plan: ExecutionPlan, result: ActivationResult,
) -> tuple[frozenset[str], frozenset[str]] | None:
    """Project the resolved control path; unresolved branches cannot complete."""
    decisions = {item.control_id: item.reduction.selected_branch_id
                 for item in result.branch_decisions}
    selected: set[str] = set()

    def visit(control: CompiledControlNode) -> bool:
        if dict(control.attributes).get("template") == "true":
            return True
        selected.update(control.step_ids)
        children = control.children
        if control.node_kind == "decide":
            branch_id = decisions.get(control.control_id)
            if branch_id is None:
                return False
            matches = [index for index, branch in enumerate(control.decision_branches)
                       if branch.branch_id == branch_id]
            if len(matches) != 1:
                raise ExactBindingConflict("completion branch is absent from exact Plan")
            children = (children[matches[0]],)
        return all(visit(child) for child in children)

    if not visit(plan.control_root):
        return None
    returns = set(plan.control_root.semantic_return_step_ids) & selected
    if not returns or not returns.issubset({value.step_id for value in result.values}):
        return None
    effects = frozenset(step.step_id for step in plan.ordered_steps
                        if step.step_id in selected and step.step_kind in {"EFFECT", "ADMISSION"})
    traversals = frozenset(step.step_id for step in plan.ordered_steps
                           if step.step_id in selected and step.transform_ref is not None
                           and step.transform_ref.name == TRAVERSAL_MATERIALIZER_TRANSFORM)
    if not traversals.issubset({value.step_id for value in result.values}):
        return None
    # The fixed point already read exact settled traversal values. Effects have
    # their own step authority; do not equate it with a parent's settlement grant.
    return (effects, frozenset()) if effects else (traversals, traversals)


class ActiveChildSubmission(Protocol):
    """Structural domain declaration consumed by the active-run seam."""

    element_index: int
    element_digest: str
    program: ProgramSpec
    values: tuple[tuple[ValueRef, bytes], ...]
    invocation_ref: ValueRef
    budget_ref: ValueRef
    canonical_bindings: Mapping[str, tuple[int, str]]
    approvals_by_step: Mapping[str, tuple[str, ...]]
    logical_request_id: str
    idempotency_id: str
    child_run_id: str
    incarnation: str


@dataclass(frozen=True, slots=True)
class ActiveChildMaterializationReceipt:
    parent_run_id: str
    source_step_id: str
    child_run_ids: tuple[str, ...]
    repeated: bool


@dataclass(frozen=True, slots=True)
class ActiveChildSettlementReceipt:
    parent_run_id: str
    source_step_id: str
    state: Literal["WAIT", "SETTLED", "FAILED"]
    child_run_ids: tuple[str, ...]
    result_ref: ValueRef | None = None


@dataclass(frozen=True, slots=True)
class LinkedRuntimeWork:
    work_item_id: str
    run_id: str
    due_at: datetime


@dataclass(frozen=True, slots=True)
class LinkedRuntimeFrontier:
    project_key: str
    source_work_item_id: str
    root_run_id: str
    related_run_ids: tuple[str, ...]
    ready_work: tuple[LinkedRuntimeWork, ...]


@dataclass(frozen=True, slots=True)
class ActiveChildTerminalObservation:
    element_index: int
    element_digest: str
    child_run_id: str
    state: Literal["COMPLETED", "FAILED", "CANCELLED"]
    input_ref: ValueRef
    input_bytes: bytes
    result_ref: ValueRef | None = None
    result_bytes: bytes | None = None
    failure_digest: str | None = None
    terminal_ref: str | None = None
    terminal_digest: str | None = None


ActiveChildSettlementBuilder = Callable[
    [tuple[ActiveChildTerminalObservation, ...]], bytes | None
]


class ActiveChildMaterializer(Protocol):
    """Domain lowering invoked for one persisted traversal request."""

    def __call__(
        self,
        *,
        connection: Connection,
        scope: RuntimeScope,
        parent_run_id: str,
        descriptor: TraversalMaterialization,
        trigger: ActivationTrigger,
    ) -> ActiveChildMaterializationReceipt: ...


def compiled_submission_request_digest(
    program: ProgramSpec,
    scope: RuntimeScope,
    canonical_bindings: Mapping[str, tuple[int, str]],
    approvals_by_step: Mapping[str, tuple[str, ...]],
) -> str:
    return canonical_digest({
        "program_digest": program.program_digest,
        "actor_id": scope.actor_id,
        "project_scope_digest": scope.project_scope.scope_digest,
        "canonical_bindings": dict(canonical_bindings),
        "approvals_by_step": dict(approvals_by_step),
    })


def submit_compiled_program(
    connection: Connection,
    scope: RuntimeScope,
    *,
    program: ProgramSpec,
    operation_catalog: OperationContractCatalogSnapshot,
    operation_contracts: OperationContractRegistry,
    activation_catalog: OperationActivationCatalog,
    values: tuple[tuple[ValueRef, bytes], ...],
    idempotency: IdempotencyBinding,
    incarnation: str,
    canonical_bindings: Mapping[str, tuple[int, str]],
    approvals_by_step: Mapping[str, tuple[str, ...]],
    trigger: ActivationTrigger,
) -> str:
    """Compile, qualify and activate one submission on the caller transaction.

    The supplied values are exact domain payloads; compilation and current
    authorization happen here. RuntimeNode remains the only effect executor.
    """
    now = trigger.observed_at or trigger.due_at
    if operation_catalog.catalog_digest is None:
        raise ExactBindingConflict("submission operation catalog has no exact digest")
    expected_request_digest = compiled_submission_request_digest(
        program, scope, canonical_bindings, approvals_by_step,
    )
    if idempotency.request_digest != expected_request_digest:
        raise ExactBindingConflict("submission idempotency does not bind exact input")
    IdempotencyRepository(connection, scope).reserve(idempotency)
    runs = PUBLIC_TABLES["runtime_runs"]
    existing = one_mapping(connection.execute(select(runs).where(
        runs.c.project_key == scope.project_scope.project_key,
        runs.c.run_id == idempotency.run_id,
    )))
    if existing is not None:
        if (existing["program_digest"], existing["incarnation"]) != (
            program.program_digest, incarnation,
        ):
            raise ExactBindingConflict("submission run identity is already bound")
        return idempotency.run_id
    plan = compile_program(
        program, operation_catalog, operation_contracts=operation_contracts,
        transform_registry=activation_catalog.transform_registry,
        merge_registry=activation_catalog.merge_registry,
        discriminator_registry=activation_catalog.discriminator_registry,
    )
    atoms = {atom.operation.operation_id: atom for atom in program_atoms(program.root)}
    steps = tuple(step for step in plan.ordered_steps if step.step_kind in {"EFFECT", "ADMISSION"})
    if not steps or set(canonical_bindings) != {step.step_id for step in steps}:
        raise ExactBindingConflict("submission requires exact canonical bindings for every effect")
    if set(approvals_by_step) - set(canonical_bindings):
        raise ExactBindingConflict("submission approvals reference unknown steps")
    provider = PostgresAuthorityProvider(connection, scope)
    authorizations: list[StepAuthorizationBinding] = []
    qualification_context = None
    for step in steps:
        if step.operation_contract_ref is None or step.operation_id not in atoms:
            raise ExactBindingConflict("compiled effect lacks its source operation")
        entry = activation_catalog.entry_for(step.operation_contract_ref.contract_digest)
        approval_refs = approvals_by_step.get(step.step_id, ())
        if entry.external_gate_required and not approval_refs:
            raise ExactBindingConflict("installed operation requires its exact approval")
        base_revision, base_incarnation = canonical_bindings[step.step_id]
        context, authorization = provider.qualify_step(
            run_id=idempotency.run_id, step=step,
            operation=atoms[step.operation_id].operation,
            installed_operation=operation_contracts.resolve_required(step.operation_contract_ref),
            interpreter=entry.interpreter_binding, eligibility=entry.queue_eligibility,
            canonical_base_revision=base_revision, canonical_incarnation=base_incarnation,
            approval_refs=approval_refs, now=now,
        )
        qualification_context = qualification_context or context
        authorizations.append(authorization)
    assert qualification_context is not None
    qualified = QualifiedPlan.from_content(
        plan_digest=plan.plan_digest,
        authority_context_digest=qualification_context.context_digest,
        step_bindings=tuple(authorizations),
    )
    qualification = ExactQualificationBinding.from_content(
        qualification_id=f"qualification:{idempotency.run_id}",
        project_key=scope.project_scope.project_key, run_id=idempotency.run_id,
        plan_id=plan.plan_id, plan_digest=plan.plan_digest,
        authority_context=qualification_context,
        authority_context_digest=qualification_context.context_digest,
        qualified_plan=qualified, decision="QUALIFIED",
    )
    tables = project_tables(MetaData(), scope.project_scope.resolved_schema)
    value_repository = ValueRepository(connection, tables)
    for ref, content in values:
        if ref.project_key != scope.project_scope.project_key or len(content) != ref.byte_size:
            raise ExactBindingConflict("submission value scope or byte size drift")
        existing_ref = _existing_project_content(connection, scope, tables, ref.object_type, ref.content_digest, content)
        if existing_ref is not None:
            if existing_ref != ref:
                raise ExactBindingConflict("submission does not reuse the canonical original value ref")
            continue
        value_repository.put_exact(
            scope, value_id=ref.value_id, object_type=ref.object_type.type_id,
            codec_id=ref.codec_id, content=content, expected_digest=ref.content_digest,
            provenance_digest=ref.provenance_digest, expected_revision=0,
            expected_incarnation=incarnation, source_ref=ref.storage_ref,
        )
    ProgramRepository(connection, tables).put_exact(scope, program, program.program_digest)
    PlanRepository(connection, tables).put_exact(
        scope, plan, plan.plan_digest, operation_catalog_id=operation_catalog.catalog_id,
        catalog_version=operation_catalog.catalog_version, catalog_digest=operation_catalog.catalog_digest,
    )
    lifecycle = RuntimeLifecycleRepository(connection, scope)
    lifecycle.submit(SubmitRun(
        run_id=idempotency.run_id, incarnation=incarnation, program_id=program.program_id,
        program_digest=program.program_digest, program_storage_ref=f"project-value:program:{program.program_id}",
        contract_version=program.contract_version,
        submission_authority_digest=qualification_context.context_digest,
        compile_work=None, due_at=now,
    ))
    RuntimeJournalRepository(connection, scope).append_transition(
        run_id=idempotency.run_id, expected_revision=0, snapshot_values={"state": "COMPILING"},
        events=({"event_type": "CompileSucceeded", "schema_version": "mrw.runtime.event.compile-succeeded.v1",
                 "event_metadata_json": {"plan_digest": plan.plan_digest},
                 "authority_digest": qualification_context.context_digest},),
    )
    lifecycle.attach_plan(AttachPlan(
        run_id=idempotency.run_id, expected_run_revision=1,
        plan_id=plan.plan_id, plan_digest=plan.plan_digest,
        program_id=program.program_id, program_digest=program.program_digest,
        project_storage_ref=f"project-value:plan:{plan.plan_id}",
        compiler_id=plan.compiler_id, compiler_version=plan.compiler_version,
        operation_catalog_id=operation_catalog.catalog_id,
        catalog_version=operation_catalog.catalog_version, catalog_digest=operation_catalog.catalog_digest,
        effect_closure_digest=plan.effect_closure_digest,
        authority_closure_digest=plan.authority_closure_digest,
        resource_closure_digest=plan.resource_closure_digest,
        qualify_work=None, due_at=now, compilation_authority_digest=qualification_context.context_digest,
    ))
    persist_qualification_step_shells(
        connection, scope, run_id=idempotency.run_id, plan=plan, catalog=activation_catalog,
        authorizations=tuple(authorizations), observed_at=now,
    )
    QualificationStoreRepository(connection, scope).persist(qualification)
    lifecycle.activate_qualification(ActivateQualification(
        run_id=idempotency.run_id, expected_run_revision=2, binding=qualification,
    ))
    activate_run(connection, scope, idempotency.run_id, activation_catalog, trigger)
    return idempotency.run_id


def materialize_active_children(
    connection: Connection,
    scope: RuntimeScope,
    *,
    parent_run_id: str,
    descriptor: TraversalMaterialization,
    children: Sequence[ActiveChildSubmission],
    root_value_identity: str,
    operation_catalog: OperationContractCatalogSnapshot,
    operation_contracts: OperationContractRegistry,
    activation_catalog: OperationActivationCatalog,
    trigger: ActivationTrigger,
    empty_result_bytes: bytes | None = None,
    child_activation_catalog_factory: Callable[[Connection, RuntimeScope, ProgramSpec], OperationActivationCatalog] | None = None,
    active_child_materializer_factory: Callable[[OperationActivationCatalog], ActiveChildMaterializer] | None = None,
) -> ActiveChildMaterializationReceipt:
    """Create one immutable child run per ordered traversal element.

    Domain code supplies already-typed Programs and values.  This function
    verifies only the shared traversal, root-value and immutable runtime
    bindings, then uses the ordinary submission path for every child.
    """

    if not root_value_identity:
        raise ExactBindingConflict("active children require a root value identity")
    ordered = tuple(children)
    if len(ordered) != descriptor.element_count:
        raise ExactBindingConflict("active child count differs from traversal shape")
    for index, child in enumerate(ordered):
        if (
            child.element_index != index
            or child.element_digest != descriptor.element_digests[index]
            or child.program.project_key != scope.project_scope.project_key
            or child.invocation_ref.project_key != scope.project_scope.project_key
            or child.budget_ref.project_key != scope.project_scope.project_key
        ):
            raise ExactBindingConflict("active child order or project binding drift")
    if ordered:
        root_ref = ordered[0].budget_ref
        if any(child.budget_ref != root_ref for child in ordered):
            raise ExactBindingConflict("active children do not share one root value ref")
        if empty_result_bytes is not None:
            raise ExactBindingConflict(
                "non-empty active traversal cannot carry an empty result"
            )
    elif not isinstance(empty_result_bytes, bytes):
        raise ExactBindingConflict(
            "empty active traversal requires a domain-owned typed empty result"
        )

    runs = PUBLIC_TABLES["runtime_runs"]
    parent = one_mapping(
        connection.execute(
            select(runs)
            .where(
                runs.c.project_key == scope.project_scope.project_key,
                runs.c.run_id == parent_run_id,
            )
            .with_for_update()
        )
    )
    if parent is None or parent["state"] != "WAITING":
        raise ExactBindingConflict("active children require a WAITING parent run")
    _require_run_scope(parent, scope)
    _require_traversal_request(connection, parent, descriptor)

    relation_rows = active_child_rows(
        connection,
        project_key=scope.project_scope.project_key,
        parent_run_id=parent_run_id,
        source_step_id=descriptor.step_id,
    )
    repeated = bool(relation_rows)
    if not ordered:
        repeated = (
            _active_children_settled_event(
                connection,
                project_key=scope.project_scope.project_key,
                parent_run_id=parent_run_id,
                source_step_id=descriptor.step_id,
            )
            is not None
        )
        settlement = settle_active_children(
            connection,
            scope,
            parent_run_id=parent_run_id,
            source_step_id=descriptor.step_id,
            activation_catalog=activation_catalog,
            settlement_builder=lambda _observations: empty_result_bytes,
            trigger=trigger,
            empty_result_bytes=empty_result_bytes,
            active_child_materializer_factory=active_child_materializer_factory,
        )
        if settlement.state != "SETTLED" or settlement.child_run_ids:
            raise ExactBindingConflict("empty active traversal did not settle exactly")
        return ActiveChildMaterializationReceipt(
            parent_run_id=parent_run_id,
            source_step_id=descriptor.step_id,
            child_run_ids=(),
            repeated=repeated,
        )
    expected_rows: list[dict[str, object]] = []
    for child in ordered:
        atom_refs = tuple(
            ref
            for atom in program_atoms(child.program.root)
            for ref in atom.operation.input_refs
        )
        supplied_refs = {ref for ref, _ in child.values}
        if (
            child.budget_ref not in atom_refs
            or child.invocation_ref not in atom_refs
            or child.budget_ref not in supplied_refs
            or child.invocation_ref not in supplied_refs
        ):
            raise ExactBindingConflict("active child omits exact root or payload value")
        child_catalog = (child_activation_catalog_factory(connection, scope, child.program)
                         if child_activation_catalog_factory is not None else activation_catalog)
        plan = compile_program(
            child.program,
            operation_catalog,
            operation_contracts=operation_contracts,
            transform_registry=child_catalog.transform_registry,
            merge_registry=child_catalog.merge_registry,
            discriminator_registry=child_catalog.discriminator_registry,
        )
        result_steps = plan.control_root.semantic_return_step_ids
        if len(result_steps) != 1:
            raise ExactBindingConflict("active child requires one semantic result step")
        atoms = program_atoms(child.program.root)
        if not atoms:
            raise ExactBindingConflict("active child requires an operation declaration")
        contract = operation_contracts.resolve_required(atoms[0].operation.contract_ref)
        idempotency = IdempotencyBinding(
            idempotency_id=child.idempotency_id,
            capability_id=contract.owner_capability_id,
            logical_request_id=child.logical_request_id,
            operation_kind=contract.ref.kind,
            run_id=child.child_run_id,
            request_digest=compiled_submission_request_digest(
                child.program,
                scope,
                child.canonical_bindings,
                child.approvals_by_step,
            ),
        )
        submit_compiled_program(
            connection,
            scope,
            program=child.program,
            operation_catalog=operation_catalog,
            operation_contracts=operation_contracts,
            activation_catalog=child_catalog,
            values=child.values,
            idempotency=idempotency,
            incarnation=child.incarnation,
            canonical_bindings=child.canonical_bindings,
            approvals_by_step=child.approvals_by_step,
            trigger=trigger,
        )
        expected_rows.append(
            {
                "source_step_id": descriptor.step_id,
                "materialization_digest": descriptor.materialization_digest,
                "element_index": child.element_index,
                "element_digest": child.element_digest,
                "child_run_id": child.child_run_id,
                "child_program_digest": child.program.program_digest,
                "result_step_id": result_steps[0],
                "input_ref": child.invocation_ref.storage_ref,
                "input_digest": child.invocation_ref.content_digest,
                "root_value_identity": root_value_identity,
                "root_value_ref": child.budget_ref.storage_ref,
                "root_value_digest": child.budget_ref.content_digest,
            }
        )

    if relation_rows:
        actual = tuple(_event_metadata(row) for row in relation_rows)
        if actual != tuple(expected_rows):
            raise ExactBindingConflict("active child lineage differs from exact replay")
    else:
        RuntimeJournalRepository(connection, scope).append_transition(
            run_id=parent_run_id,
            expected_revision=int(parent["revision"]),
            snapshot_values={"state": "WAITING"},
            events=tuple(
                {
                    "event_type": "ActiveChildMaterialized",
                    "schema_version": "mrw.runtime.event.active_child_materialized.v1",
                    "event_metadata_json": metadata,
                    "authority_digest": parent["submission_authority_digest"],
                }
                for metadata in expected_rows
            ),
        )
    return ActiveChildMaterializationReceipt(
        parent_run_id=parent_run_id,
        source_step_id=descriptor.step_id,
        child_run_ids=tuple(child.child_run_id for child in ordered),
        repeated=repeated,
    )


def settle_active_children(
    connection: Connection,
    scope: RuntimeScope,
    *,
    parent_run_id: str,
    source_step_id: str,
    activation_catalog: OperationActivationCatalog,
    settlement_builder: ActiveChildSettlementBuilder,
    trigger: ActivationTrigger,
    empty_result_bytes: bytes | None = None,
    parent_activation_catalog_factory: Callable[[Connection, RuntimeScope, ProgramSpec], OperationActivationCatalog] | None = None,
    active_child_materializer_factory: Callable[[OperationActivationCatalog], ActiveChildMaterializer] | None = None,
) -> ActiveChildSettlementReceipt:
    """Publish the ordered traversal result after every child is terminal."""

    project_key = scope.project_scope.project_key
    runs = PUBLIC_TABLES["runtime_runs"]
    parent = one_mapping(
        connection.execute(
            select(runs)
            .where(runs.c.project_key == project_key, runs.c.run_id == parent_run_id)
            .with_for_update()
        )
    )
    if parent is None:
        raise RecordNotFound(f"runtime run not found: {parent_run_id}")
    _require_run_scope(parent, scope)
    relations = active_child_rows(
        connection,
        project_key=project_key,
        parent_run_id=parent_run_id,
        source_step_id=source_step_id,
    )
    metadata = tuple(_event_metadata(row) for row in relations)
    child_ids = tuple(str(item["child_run_id"]) for item in metadata)

    settled_event = _active_children_settled_event(
        connection,
        project_key=project_key,
        parent_run_id=parent_run_id,
        source_step_id=source_step_id,
    )
    if settled_event is not None:
        tables = project_tables(MetaData(), str(parent["resolved_schema"]))
        program = ProgramRepository(connection, tables).get(
            scope,
            str(parent["program_id"]),
            expected_digest=str(parent["program_digest"]),
        )
        plan = PlanRepository(connection, tables).get(scope, str(parent["plan_digest"]))
        require_program_plan_run(program, plan, parent)
        step = traversal_plan_step(plan, source_step_id)
        result = load_bound_runtime_output(
            connection,
            scope,
            tables,
            step,
            str(settled_event["payload_digest"]),
        )[0]
        return ActiveChildSettlementReceipt(
            parent_run_id,
            source_step_id,
            "SETTLED",
            child_ids,
            result.value_ref,
        )

    if not relations:
        if not isinstance(empty_result_bytes, bytes):
            raise ExactBindingConflict("active-child lineage is absent")
        _require_empty_traversal_request(
            connection,
            parent,
            source_step_id=source_step_id,
        )
    elif empty_result_bytes is not None:
        raise ExactBindingConflict(
            "non-empty active-child settlement cannot carry an empty result"
        )

    child_rows: list[RowMapping] = []
    for child_id in child_ids:
        child = one_mapping(
            connection.execute(
                select(runs).where(
                    runs.c.project_key == project_key,
                    runs.c.run_id == child_id,
                )
            )
        )
        if child is None:
            raise ExactBindingConflict("active child run is absent")
        child_rows.append(child)
    failed = next((child for child in child_rows if child["state"] == "FAILED"), None)
    cancelled = any(child["state"] == "CANCELLED" for child in child_rows)
    if (failed is not None or cancelled) and parent["state"] in {"WAITING", "FAILED"}:
        authority_run = parent
        bindings = _load_qualified_plan(connection, authority_run).step_bindings
        if not bindings and failed is not None:
            authority_run = failed
            bindings = _load_qualified_plan(connection, authority_run).step_bindings
        if not bindings or len({binding.actor_id for binding in bindings}) != 1:
            raise ExactBindingConflict("parent settlement lacks one qualified authority subject")
        scope = _active_child_authority_scope(
            connection, scope, run_id=str(authority_run["run_id"]), authority_step_id=bindings[0].step_id,
            authority_digest=bindings[0].binding_digest, observed_at=trigger.observed_at or utc_now(),
        )
        lifecycle = RuntimeLifecycleRepository(connection, scope)
        if failed is not None:
            lifecycle.fail_active_child(
                parent_run_id=parent_run_id, source_step_id=source_step_id,
                child_run_id=str(failed["run_id"]), observed_at=trigger.observed_at,
            )
            return ActiveChildSettlementReceipt(parent_run_id, source_step_id, "FAILED", child_ids)
        if parent["state"] == "WAITING":
            lifecycle.request_cancel(RequestCancel(parent_run_id, int(parent["revision"]),
                                                   reason="active_child_cancelled"), observed_at=trigger.observed_at)
    if cancelled:
        return ActiveChildSettlementReceipt(parent_run_id, source_step_id, "WAIT", child_ids)
    if any(child["state"] != "COMPLETED" for child in child_rows):
        return ActiveChildSettlementReceipt(
            parent_run_id, source_step_id, "WAIT", child_ids
        )
    if parent["state"] != "WAITING":
        return ActiveChildSettlementReceipt(
            parent_run_id, source_step_id, "WAIT", child_ids
        )

    tables = project_tables(MetaData(), str(parent["resolved_schema"]))
    parent_program = ProgramRepository(connection, tables).get(
        scope,
        str(parent["program_id"]),
        expected_digest=str(parent["program_digest"]),
    )
    parent_plan = PlanRepository(connection, tables).get(
        scope, str(parent["plan_digest"])
    )
    require_program_plan_run(parent_program, parent_plan, parent)
    if parent_activation_catalog_factory is not None:
        bindings = _load_qualified_plan(connection, parent).step_bindings
        if not bindings or len({binding.actor_id for binding in bindings}) != 1:
            raise ExactBindingConflict("parent settlement lacks one qualified authority subject")
        for binding in bindings:
            scope = _active_child_authority_scope(
                connection, scope, run_id=parent_run_id,
                authority_step_id=binding.step_id,
                authority_digest=binding.binding_digest,
                observed_at=trigger.observed_at or utc_now(),
            )
        activation_catalog = parent_activation_catalog_factory(connection, scope, parent_program)
    traversal_step = traversal_plan_step(parent_plan, source_step_id)
    observations: list[ActiveChildTerminalObservation] = []
    value_reader = PostgresRuntimeActivationBindingAdapter()
    for relation, child in zip(metadata, child_rows, strict=True):
        child_program = ProgramRepository(connection, tables).get(
            scope,
            str(child["program_id"]),
            expected_digest=str(child["program_digest"]),
        )
        declared_inputs = {
            ref for atom in program_atoms(child_program.root)
            for ref in atom.operation.input_refs
            if ref.storage_ref == relation.get("input_ref")
            and ref.content_digest == relation.get("input_digest")
        }
        if len(declared_inputs) != 1:
            raise ExactBindingConflict("active child lacks one exact declared invocation")
        declared_input = next(iter(declared_inputs))
        input_ref = _read_project_value(
            connection,
            scope,
            tables,
            declared_input.storage_ref,
            declared_input.object_type,
        )[0]
        if (
            input_ref != declared_input
            or relation.get("input_ref") != input_ref.storage_ref
            or relation.get("input_digest") != input_ref.content_digest
        ):
            raise ExactBindingConflict("active child invocation binding drift")
        input_bytes = value_reader.read_value_bytes(
            connection, scope, tables, input_ref
        )
        child_plan = PlanRepository(connection, tables).get(
            scope, str(child["plan_digest"])
        )
        require_program_plan_run(child_program, child_plan, child)
        if child_plan.control_root.semantic_return_step_ids != (relation["result_step_id"],):
            raise ExactBindingConflict("active child semantic return binding drift")
        result_step = next(step for step in child_plan.ordered_steps
                           if step.step_id == relation["result_step_id"])
        observed, activated = load_runtime_observations(connection, scope, tables, child, child_plan)
        result = _bind_materializations_to_project(activate_plan(
            run_id=str(child["run_id"]), program=child_program, plan=child_plan,
            completed_outputs=observed, already_activated_step_ids=activated,
            transform_registry=activation_catalog.transform_registry,
            merge_registry=activation_catalog.merge_registry,
            discriminator_registry=activation_catalog.discriminator_registry,
            encode_value=activation_catalog.encode_value,
        ), child_plan, canonical_value=lambda item: _existing_project_content(
            connection, scope, tables, item.value_ref.object_type, item.value_ref.content_digest, item.exact_bytes,
        ))
        returned = tuple(value for value in result.values if value.step_id == result_step.step_id)
        if len(returned) != 1:
            raise ExactBindingConflict("completed child lacks its exact semantic result")
        bound = returned[0]
        result_ref = bound.value_ref
        result_bytes = value_reader.read_value_bytes(
            connection, scope, tables, result_ref
        )
        observations.append(
            ActiveChildTerminalObservation(
                element_index=_db_int(relation["element_index"], "element_index"),
                element_digest=str(relation["element_digest"]),
                child_run_id=str(child["run_id"]),
                state="COMPLETED",
                input_ref=input_ref,
                input_bytes=input_bytes,
                result_ref=result_ref,
                result_bytes=result_bytes,
            )
        )
    aggregate_bytes = (
        empty_result_bytes
        if not relations
        else settlement_builder(tuple(observations))
    )
    if aggregate_bytes is None:
        return ActiveChildSettlementReceipt(
            parent_run_id, source_step_id, "WAIT", child_ids
        )
    aggregate_bytes = _require_settlement_bytes(aggregate_bytes)
    if activation_catalog.encode_value(traversal_step.output_type, json.loads(aggregate_bytes)) != aggregate_bytes:
        raise ExactBindingConflict("active child settlement bytes differ from their declared codec")
    result_ref = _publish_active_child_result(
        connection,
        scope,
        tables,
        parent_run_id=parent_run_id,
        source_step=traversal_step,
        observations=tuple(observations),
        content=aggregate_bytes,
    )
    current = RuntimeJournalRepository(connection, scope).load_run(
        parent_run_id, for_update=True
    )
    RuntimeJournalRepository(connection, scope).append_transition(
        run_id=parent_run_id,
        expected_revision=int(current["revision"]),
        snapshot_values={"state": "RUNNING"},
        events=(
            {
                "event_type": "ActiveChildrenSettled",
                "schema_version": "mrw.runtime.event.active_children_settled.v1",
                "event_metadata_json": {
                    "source_step_id": source_step_id,
                    "child_count": len(child_ids),
                    "child_run_ids": child_ids,
                    "child_result_digests": tuple(
                        item.result_ref.content_digest
                        if item.result_ref is not None
                        else item.failure_digest
                        for item in observations
                    ),
                    "result_digest": result_ref.content_digest,
                },
                "payload_ref": result_ref.storage_ref,
                "payload_digest": result_ref.content_digest,
                "authority_digest": current["submission_authority_digest"],
            },
        ),
    )
    receipt = activate_run(
        connection,
        scope,
        parent_run_id,
        activation_catalog,
        trigger,
    )
    if active_child_materializer_factory is not None:
        _materialize_active_traversals(
            connection, scope, parent_run_id, receipt, trigger,
            active_child_materializer_factory(activation_catalog),
        )
    return_steps = frozenset(parent_plan.control_root.semantic_return_step_ids)
    if return_steps == frozenset({source_step_id}):
        RuntimeLifecycleRepository(connection, scope).complete_if_satisfied(
            parent_run_id,
            required_step_ids=return_steps,
            journal_succeeded_step_ids=frozenset({source_step_id}),
            authority_digest=str(parent["submission_authority_digest"]),
            observed_at=trigger.observed_at,
        )
    return ActiveChildSettlementReceipt(
        parent_run_id,
        source_step_id,
        "SETTLED",
        child_ids,
        result_ref,
    )


def settle_active_parents_for_child(
    connection: Connection,
    scope: RuntimeScope,
    *,
    child_run_id: str,
    activation_catalog: OperationActivationCatalog,
    settlement_builder: ActiveChildSettlementBuilder,
    trigger: ActivationTrigger,
    parent_activation_catalog_factory: Callable[[Connection, RuntimeScope, ProgramSpec], OperationActivationCatalog] | None = None,
    active_child_materializer_factory: Callable[[OperationActivationCatalog], ActiveChildMaterializer] | None = None,
) -> tuple[ActiveChildSettlementReceipt, ...]:
    """Settle every parent that names the terminal child in its own journal."""

    events = PUBLIC_TABLES["runtime_events"]
    rows = connection.execute(
        select(events.c.run_id, events.c.event_metadata_json)
        .where(
            events.c.project_key == scope.project_scope.project_key,
            events.c.event_type == "ActiveChildMaterialized",
            events.c.event_metadata_json["child_run_id"].astext == child_run_id,
        )
        .order_by(events.c.run_id, events.c.seq)
    ).mappings().all()
    targets = {
        (str(row["run_id"]), str(row["event_metadata_json"]["source_step_id"]))
        for row in rows
    }
    return tuple(
        settle_active_children(
            connection,
            scope,
            parent_run_id=parent_run_id,
            source_step_id=source_step_id,
            activation_catalog=activation_catalog,
            settlement_builder=settlement_builder,
            trigger=trigger,
            parent_activation_catalog_factory=parent_activation_catalog_factory,
            active_child_materializer_factory=active_child_materializer_factory,
        )
        for parent_run_id, source_step_id in sorted(targets)
    )


def _materialize_active_traversals(
    connection: Connection, scope: RuntimeScope, run_id: str,
    receipt: ActivationReceipt, trigger: ActivationTrigger,
    materializer: ActiveChildMaterializer,
) -> None:
    for descriptor in receipt.result.traversal_materializations:
        materializer(
            connection=connection, scope=scope, parent_run_id=run_id,
            descriptor=descriptor, trigger=trigger,
        )


class PostgresRuntimeActivationPort:
    """Terminal-hook adapter around caller-owned :func:`activate_run`."""

    def __init__(
        self,
        catalog: OperationActivationCatalog,
        *,
        active_child_materializer: ActiveChildMaterializer | None = None,
        active_child_settlement: ActiveChildSettlementBuilder | None = None,
        parent_activation_catalog_factory: Callable[[Connection, RuntimeScope, ProgramSpec], OperationActivationCatalog] | None = None,
        active_child_materializer_factory: Callable[[OperationActivationCatalog], ActiveChildMaterializer] | None = None,
        trace_prefix: str = "trace:first-specimen:activation",
    ) -> None:
        if not trace_prefix:
            raise ValueError("activation trace prefix is required")
        self.catalog = catalog
        self.active_child_materializer = active_child_materializer
        self.active_child_materializer_factory = active_child_materializer_factory
        self.active_child_settlement = active_child_settlement
        self.parent_activation_catalog_factory = parent_activation_catalog_factory
        self.trace_prefix = trace_prefix

    def activate_after_terminal(
        self,
        *,
        connection: Connection,
        scope: RuntimeScope,
        run_id: str,
        observed_at: datetime,
        authority_step_id: str | None = None,
        authority_digest: str | None = None,
    ) -> ActivationReceipt:
        trigger = ActivationTrigger(
            due_at=observed_at,
            observed_at=observed_at,
            trace_id=f"{self.trace_prefix}:{run_id}",
        )
        receipt = activate_run(
            connection,
            scope,
            run_id,
            self.catalog,
            trigger,
        )
        descriptors = receipt.result.traversal_materializations
        if not descriptors:
            return receipt
        materializer = (self.active_child_materializer_factory(self.catalog)
                        if self.active_child_materializer_factory is not None
                        else self.active_child_materializer)
        if materializer is not None and descriptors:
            materializer_scope = _active_child_authority_scope(
                connection,
                scope,
                run_id=run_id,
                authority_step_id=authority_step_id,
                authority_digest=authority_digest,
                observed_at=observed_at,
            )
            _materialize_active_traversals(
                connection, materializer_scope, run_id, receipt, trigger, materializer,
            )
        return receipt

    def settle_parents_after_terminal(
        self,
        *,
        connection: Connection,
        scope: RuntimeScope,
        run_id: str,
        observed_at: datetime,
    ) -> tuple[ActiveChildSettlementReceipt, ...]:
        if self.active_child_settlement is None:
            return ()
        return settle_active_parents_for_child(
            connection,
            scope,
            child_run_id=run_id,
            activation_catalog=self.catalog,
            settlement_builder=self.active_child_settlement,
            parent_activation_catalog_factory=self.parent_activation_catalog_factory,
            active_child_materializer_factory=self.active_child_materializer_factory,
            trigger=ActivationTrigger(
                due_at=observed_at,
                observed_at=observed_at,
                trace_id=f"{self.trace_prefix}:settle:{run_id}",
            ),
        )


def persist_qualification_step_shells(
    connection: Connection,
    scope: RuntimeScope,
    *,
    run_id: str,
    plan: ExecutionPlan,
    catalog: OperationActivationCatalog,
    authorizations: tuple[StepAuthorizationBinding, ...],
    observed_at: datetime,
) -> tuple[str, ...]:
    """Create exact PENDING step identities required by authorization FKs."""

    by_step = {item.step_id: item for item in authorizations}
    if len(by_step) != len(authorizations):
        raise ExactBindingConflict("qualification step authorizations are not unique")
    table = PUBLIC_TABLES["runtime_steps"]
    created: list[str] = []
    for step in plan.ordered_steps:
        if step.step_kind not in {"EFFECT", "ADMISSION"}:
            continue
        if step.operation_id is None or step.operation_contract_ref is None:
            raise ExactBindingConflict("authorizable Plan step lacks operation identity")
        authorization = by_step.get(step.step_id)
        if authorization is None:
            raise ExactBindingConflict("qualification omits an authorizable Plan step")
        entry = catalog.entry_for(step.operation_contract_ref.contract_digest)
        expected = {
            "project_key": scope.project_scope.project_key,
            "run_id": run_id,
            "step_id": step.step_id,
            "operation_id": step.operation_id,
            "operation_kind": step.operation_contract_ref.kind,
            "operation_version": step.operation_contract_ref.contract_version,
            "state": "PENDING",
            "revision": 0,
            "execution_epoch": 0,
            "input_digest": authorization.payload_digest,
            "effect_class": entry.effect_class,
            "resource_class": entry.queue_eligibility.resource_class.value,
            "concurrency_key": entry.queue_eligibility.concurrency_key,
            "capability_id": entry.queue_eligibility.capability_id,
            "claim_owner": authorization.claim_owner,
            "claim_authority_epoch": authorization.claim_authority_epoch,
            "claim_policy_digest": authorization.claim_policy_digest,
            "attempt_count": 0,
            "max_attempts": entry.max_attempts,
        }
        existing = one_mapping(
            connection.execute(
                select(table).where(
                    table.c.project_key == expected["project_key"],
                    table.c.run_id == run_id,
                    table.c.step_id == step.step_id,
                )
            )
        )
        if existing is not None:
            _require_exact_existing(existing, expected, "qualification step shell")
            if existing["state"] != "PENDING" or int(existing["revision"]) != 0:
                raise ExactBindingConflict("qualification step shell is not PENDING@0")
            continue
        connection.execute(
            insert(table).values(
                **expected,
                created_at=observed_at,
                updated_at=observed_at,
            )
        )
        created.append(step.step_id)
    if set(by_step) != {
        step.step_id
        for step in plan.ordered_steps
        if step.step_kind in {"EFFECT", "ADMISSION"}
    }:
        raise ExactBindingConflict("qualification contains non-Plan step authorization")
    return tuple(created)


class PostgresRuntimeActivationBindingAdapter:
    """Reconstruct a ReadyActivation without a second descriptor truth.

    The event carries only bounded digests and the work identity.  Full
    ValueRefs are recovered from the exact Program static suffix/payload and
    project-owned values named by the assignment's dynamic prefix.
    """

    def read_value_bytes(
        self, connection: Connection, scope: RuntimeScope, tables: ProjectTables, ref: ValueRef,
    ) -> bytes:
        """Read exact codec bytes through the project value owner."""
        actual, exact, _ = _read_project_value(connection, scope, tables, ref.storage_ref, ref.object_type)
        if actual != ref:
            raise ExactBindingConflict("operation input ValueRef differs from its stored binding")
        return exact

    def semantic_input_ref(
        self, connection: Connection, assignment: RuntimeAssignment, scope: RuntimeScope,
        tables: ProjectTables, descriptor: ReadyActivation,
    ) -> ValueRef:
        """Project the typed data edge; serial Zip dependencies remain ordering."""
        if assignment.plan_digest is None or descriptor.step_id != assignment.step_id:
            raise ExactBindingConflict("semantic input lacks an exact assignment plan")
        plan = PlanRepository(connection, tables).get(scope, assignment.plan_digest)
        step = _plan_step(plan, descriptor.step_id)
        required = semantic_input_step_ids(plan.control_root, step.source_path)
        if isinstance(required, Failure):
            raise ExactBindingConflict(required.message)
        if not required:
            return descriptor.payload_ref
        groups = _dynamic_dependency_groups(step, plan)
        selected = [ref for group, ref in zip(groups, descriptor.ordered_dependency_refs, strict=True)
                    if any(dependency.step_id in required for dependency in group)]
        covered = {dependency.step_id for group in groups for dependency in group if dependency.step_id in required}
        if covered != set(required) or len(selected) != 1:
            raise ExactBindingConflict("compiled data edge is absent or not a single typed input")
        if selected[0].object_type != step.input_type:
            raise ExactBindingConflict("compiled data input endpoint type drift")
        return selected[0]

    def publish_output(
        self, connection: Connection, assignment: RuntimeAssignment,
        scope: RuntimeScope, tables: ProjectTables, *, content: bytes,
    ) -> str:
        """Publish exact domain-codec output for the current compiled step.

        The public value index contains only the project owner reference.
        RuntimeNode's terminal commit separately makes this value an observed
        step result; publishing bytes never changes run or step status.
        """
        descriptor = self.load_exact(connection, assignment, scope, tables)
        if assignment.plan_digest is None:
            raise ExactBindingConflict("operation output lacks a bound plan")
        plan = PlanRepository(connection, tables).get(scope, assignment.plan_digest)
        step = _plan_step(plan, descriptor.step_id)
        digest = hashlib.sha256(content).hexdigest()
        _publish_typed_content(
            connection, scope, tables, value_id=f"operation-output:{digest}",
            object_type=step.output_type, content=content, incarnation=f"content:{digest}",
            provenance={"schema": "mrw.runtime.operation-output.v1",
                        "object_type": step.output_type.type_id,
                        "codec_id": step.output_type.codec_id, "content_digest": digest},
        )
        return digest

    def load_exact(
        self,
        connection: Connection,
        assignment: RuntimeAssignment,
        scope: RuntimeScope,
        tables: ProjectTables,
    ) -> ReadyActivation:
        if (
            assignment.assignment_kind
            not in {AssignmentKind.INTERPRET, AssignmentKind.VERIFY_ADMIT}
            or assignment.step_id is None
            or assignment.plan_digest is None
            or assignment.input_closure_digest is None
            or assignment.operation_contract_digest is None
        ):
            raise FirstSpecimenActivationError(
                "activation binding requires exact effect/admission assignment"
            )
        run = one_mapping(
            connection.execute(
                select(PUBLIC_TABLES["runtime_runs"]).where(
                    PUBLIC_TABLES["runtime_runs"].c.project_key
                    == scope.project_scope.project_key,
                    PUBLIC_TABLES["runtime_runs"].c.run_id == assignment.run_id,
                )
            )
        )
        if run is None:
            raise RecordNotFound(f"runtime run not found: {assignment.run_id}")
        _require_run_scope(run, scope)
        if (
            run["program_digest"] != assignment.program_digest
            or run["plan_digest"] != assignment.plan_digest
            or run["incarnation"] != assignment.incarnation
            or int(run["execution_epoch"]) != assignment.execution_epoch
        ):
            raise ExactBindingConflict("activation assignment/run identity drift")
        program = ProgramRepository(connection, tables).get(
            scope,
            str(run["program_id"]),
            expected_digest=assignment.program_digest,
        )
        plan = PlanRepository(connection, tables).get(scope, assignment.plan_digest)
        step = _plan_step(plan, assignment.step_id)
        step_kind = step.step_kind
        if (
            step_kind not in ("EFFECT", "ADMISSION")
            or step.operation_id is None
            or step.operation_contract_ref is None
            or step.operation_contract_ref.contract_digest
            != assignment.operation_contract_digest
        ):
            raise ExactBindingConflict("activation assignment/Plan operation drift")
        atom = _atom_for_step(program.root, step)
        static = atom.operation.input_refs
        static_locators = tuple(ref.storage_ref for ref in static)
        if static_locators:
            if assignment.input_refs[-len(static_locators) :] != static_locators:
                raise ExactBindingConflict("activation assignment static suffix drift")
            dynamic_locators = assignment.input_refs[: -len(static_locators)]
        else:
            dynamic_locators = assignment.input_refs
        dependency_groups = _dynamic_dependency_groups(step, plan)
        if len(dynamic_locators) != len(dependency_groups):
            raise ExactBindingConflict("activation dynamic prefix/dependency arity drift")
        dynamic: list[ValueRef] = []
        for group, locator in zip(dependency_groups, dynamic_locators, strict=True):
            candidates: set[ValueRef] = set()
            for dependency in group:
                try:
                    candidates.add(
                        _read_project_value(
                            connection,
                            scope,
                            tables,
                            locator,
                            dependency.output_type,
                        )[0]
                    )
                except ExactBindingConflict as exc:
                    if "type drift" not in str(exc):
                        raise
            if len(candidates) != 1:
                raise ExactBindingConflict(
                    "activation dynamic project value does not bind one dependency group"
                )
            dynamic.append(next(iter(candidates)))
        descriptor = finalize_activation_descriptor(
            plan,
            ReadyActivation(
                step_id=step.step_id,
                step_kind=step_kind,
                operation_id=step.operation_id,
                ordered_dependency_refs=tuple(dynamic),
                static_atom_input_refs=static,
                payload_ref=atom.operation.payload_ref,
                input_closure_digest=assignment.input_closure_digest,
                activation_digest="0" * 64,
            ),
        )
        if (
            descriptor.input_closure_digest != assignment.input_closure_digest
            or descriptor.payload_ref.storage_ref != assignment.payload_ref
            or descriptor.payload_ref.content_digest != assignment.payload_digest
        ):
            raise ExactBindingConflict("reconstructed activation/assignment drift")
        events = PUBLIC_TABLES["runtime_events"]
        rows = connection.execute(
            select(events.c.event_metadata_json)
            .where(
                events.c.project_key == assignment.project_key,
                events.c.run_id == assignment.run_id,
                events.c.step_id == assignment.step_id,
                events.c.event_type == "StepActivated",
            )
            .order_by(events.c.seq)
        ).mappings().all()
        matches = tuple(
            row
            for row in rows
            if row["event_metadata_json"].get("work_item_id")
            == assignment.work_item_id
        )
        if len(matches) != 1:
            raise ExactBindingConflict("activation event binding is absent or ambiguous")
        metadata = matches[0]["event_metadata_json"]
        if (
            metadata.get("activation_digest") != descriptor.activation_digest
            or metadata.get("input_closure_digest")
            != descriptor.input_closure_digest
            or metadata.get("assignment_digest") != assignment.assignment_digest
        ):
            raise ExactBindingConflict("activation event digest binding drift")
        return descriptor


def activate_run(
    connection: Connection,
    scope: RuntimeScope,
    run_id: str,
    catalog: OperationActivationCatalog,
    trigger: ActivationTrigger,
) -> ActivationReceipt:
    """Activate one exact run inside the caller-owned transaction."""

    project_key = runtime_scope_key(scope)
    runs = PUBLIC_TABLES["runtime_runs"]
    run = one_mapping(
        connection.execute(
            select(runs)
            .where(runs.c.project_key == project_key, runs.c.run_id == run_id)
            .with_for_update()
        )
    )
    if run is None:
        raise RecordNotFound(f"runtime run not found: {run_id}")
    _require_run_scope(run, scope)
    if run["state"] not in {"READY", "RUNNING", "WAITING"}:
        raise FirstSpecimenActivationError("run state does not permit activation")
    if run["plan_id"] is None or run["plan_digest"] is None:
        raise FirstSpecimenActivationError("activation requires an exact ExecutionPlan")
    if run["qualification_digest"] is None:
        raise FirstSpecimenActivationError("activation requires an exact QualifiedPlan")

    tables = project_tables(MetaData(), str(run["resolved_schema"]))
    program = ProgramRepository(connection, tables).get(
        scope, str(run["program_id"]), expected_digest=str(run["program_digest"])
    )
    plan = PlanRepository(connection, tables).get(scope, str(run["plan_digest"]))
    require_program_plan_run(program, plan, run)
    qualified = _load_qualified_plan(connection, run)

    completed_outputs, activated_step_ids = load_runtime_observations(
        connection, scope, tables, run, plan
    )
    raw_result = activate_plan(
        run_id=run_id,
        program=program,
        plan=plan,
        completed_outputs=completed_outputs,
        transform_registry=catalog.transform_registry,
        merge_registry=catalog.merge_registry,
        discriminator_registry=catalog.discriminator_registry,
        already_activated_step_ids=activated_step_ids,
        encode_value=catalog.encode_value,
    )
    result = _bind_materializations_to_project(
        raw_result, plan, canonical_value=lambda item: _existing_project_content(
            connection, scope, tables, item.value_ref.object_type, item.value_ref.content_digest, item.exact_bytes,
        ),
    )
    materialized = _materialize_values(connection, scope, tables, program, plan, result)

    steps_table = PUBLIC_TABLES["runtime_steps"]
    work_table = PUBLIC_TABLES["runtime_work_items"]
    now = trigger.observed_at or utc_now()
    new_steps: list[str] = []
    new_work: list[str] = []
    awaiting_external_gate: list[str] = []
    events: list[dict[str, object]] = []
    for descriptor in result.activations:
        step = _plan_step(plan, descriptor.step_id)
        authorization = _authorization_for(
            connection, run, qualified, step, descriptor, catalog, now
        )
        operation = step.operation_contract_ref
        if operation is None:
            raise ExactBindingConflict("activated step lacks operation contract")
        entry = catalog.entry_for(operation.contract_digest)
        if entry.external_gate_required and step.step_kind == "EFFECT":
            awaiting_external_gate.append(step.step_id)
            continue
        assignment = _assignment(
            run=run,
            plan=plan,
            step=step,
            descriptor=descriptor,
            authorization=authorization,
            entry=entry,
            trace_id=trigger.trace_id,
        )
        envelope = _envelope(assignment, authorization, entry, str(run["qualification_digest"]))
        step_values = _step_values(run, step, descriptor, authorization, entry, now)
        work_values = assignment_values(envelope, due_at=trigger.due_at)

        existing_step = one_mapping(
            connection.execute(
                select(steps_table)
                .where(
                    steps_table.c.project_key == project_key,
                    steps_table.c.run_id == run_id,
                    steps_table.c.step_id == step.step_id,
                )
                .with_for_update()
            )
        )
        existing_work = one_mapping(
            connection.execute(
                select(work_table)
                .where(
                    work_table.c.project_key == project_key,
                    work_table.c.work_item_id == assignment.work_item_id,
                )
                .with_for_update()
            )
        )
        if existing_step is None and existing_work is not None:
            raise ExactBindingConflict("activation work exists without its runtime step")
        if existing_step is not None and existing_work is not None:
            _require_exact_existing(existing_step, step_values, "runtime step")
            _require_exact_existing(existing_work, work_values, "runtime work item")
            continue
        if existing_step is not None:
            _activate_pending_step(
                connection,
                steps_table,
                existing_step,
                step_values,
            )
        else:
            connection.execute(insert(steps_table).values(**step_values))
        connection.execute(insert(work_table).values(**work_values))
        new_steps.append(step.step_id)
        new_work.append(assignment.work_item_id)
        events.append(
            {
                "event_type": "StepActivated",
                "schema_version": "mrw.runtime.event.step_activated.v1",
                "step_id": step.step_id,
                "event_metadata_json": {
                    "work_item_id": assignment.work_item_id,
                    "assignment_digest": assignment.assignment_digest,
                    "activation_digest": descriptor.activation_digest,
                    "input_closure_digest": descriptor.input_closure_digest,
                },
                "authority_digest": authorization.binding_digest,
            }
        )

    traversal_waiting = False
    for descriptor in result.traversal_materializations:
        existing = _traversal_request_event(
            connection,
            project_key=project_key,
            run_id=run_id,
            descriptor=descriptor,
        )
        if existing:
            continue
        traversal_waiting = True
        events.append(
            {
                "event_type": "TraversalMaterializationRequested",
                "schema_version": "mrw.runtime.event.traversal_materialization_requested.v1",
                "step_id": None,
                "event_metadata_json": {
                    "source_step_id": descriptor.step_id,
                    "traversal_policy": descriptor.traversal_policy,
                    "input_ref": descriptor.input_ref.storage_ref,
                    "input_sequence_digest": descriptor.input_sequence_digest,
                    "element_program_digest": descriptor.element_program_digest,
                    "element_count": descriptor.element_count,
                    "element_digests": descriptor.element_digests,
                    "shape_digest": descriptor.shape_digest,
                    "binding_digest": descriptor.binding_digest,
                    "materialization_digest": descriptor.materialization_digest,
                },
                "authority_digest": str(run["submission_authority_digest"]),
            }
        )

    previous_revision = int(run["revision"])
    event_seqs: tuple[int, ...] = ()
    if events:
        first_seq = int(run["next_event_seq"])
        for offset, event in enumerate(events):
            connection.execute(
                insert(PUBLIC_TABLES["runtime_events"]).values(
                    project_key=project_key,
                    run_id=run_id,
                    seq=first_seq + offset,
                    created_at=now,
                    updated_at=now,
                    **event,
                )
            )
        updated = connection.execute(
            update(runs)
            .where(
                runs.c.project_key == project_key,
                runs.c.run_id == run_id,
                runs.c.revision == previous_revision,
                runs.c.next_event_seq == first_seq,
            )
            .values(
                revision=previous_revision + 1,
                next_event_seq=first_seq + len(events),
                state=("WAITING" if traversal_waiting else run["state"]),
                updated_at=now,
            )
        )
        if getattr(updated, "rowcount", None) != 1:
            raise StaleRevisionError("activation run/event allocator CAS failed")
        event_seqs = tuple(range(first_seq, first_seq + len(events)))

    return ActivationReceipt(
        run_id=run_id,
        previous_run_revision=previous_revision,
        run_revision=previous_revision + (1 if events else 0),
        materialized_value_ids=materialized,
        activated_step_ids=tuple(new_steps),
        work_item_ids=tuple(new_work),
        event_seqs=event_seqs,
        awaiting_external_gate_step_ids=tuple(awaiting_external_gate),
        result=result,
    )
def _require_run_scope(run: RuntimeRow, scope: RuntimeScope) -> None:
    expected = scope.project_scope
    if (
        run["project_key"] != expected.project_key
        or _db_int(run["project_registry_revision"], "project_registry_revision")
        != expected.project_registry_revision
        or run["project_scope_digest"] != expected.scope_digest
        or run["resolved_schema"] != expected.resolved_schema
    ):
        raise ExactBindingConflict("activation run project scope drift")


def require_program_plan_run(
    program: ProgramSpec, plan: ExecutionPlan, run: RuntimeRow
) -> None:
    if (
        program.program_id != run["program_id"]
        or program.program_digest != run["program_digest"]
        or plan.plan_id != run["plan_id"]
        or plan.plan_digest != run["plan_digest"]
        or plan.program_id != program.program_id
        or plan.program_digest != program.program_digest
    ):
        raise ExactBindingConflict("run/Program/Plan exact identity drift")


def _load_qualified_plan(
    connection: Connection, run: RuntimeRow
) -> QualifiedPlan:
    table = PUBLIC_TABLES["runtime_qualifications"]
    rows = connection.execute(
        select(table)
        .where(
            table.c.project_key == run["project_key"],
            table.c.run_id == run["run_id"],
            table.c.plan_id == run["plan_id"],
            table.c.plan_digest == run["plan_digest"],
            table.c.qualification_digest == run["qualification_digest"],
            table.c.decision == "QUALIFIED",
        )
        .with_for_update()
    ).mappings().all()
    if len(rows) != 1:
        raise ExactBindingConflict("activation requires one exact QUALIFIED binding")
    binding = validate_qualification_row(rows[0])
    if binding.qualified_plan.qualification_digest != run["qualification_digest"]:
        raise ExactBindingConflict("run qualification digest drift")
    return binding.qualified_plan


def load_runtime_observations(
    connection: Connection,
    scope: RuntimeScope,
    tables: ProjectTables,
    run: RuntimeRow,
    plan: ExecutionPlan,
    *, lock: bool = True,
) -> tuple[tuple[BoundStepValue, ...], frozenset[str]]:
    """Read exact effect and settled traversal facts without advancing execution."""
    steps_table = PUBLIC_TABLES["runtime_steps"]
    statement = select(steps_table).where(
        steps_table.c.project_key == run["project_key"], steps_table.c.run_id == run["run_id"],
    )
    rows = connection.execute(statement.with_for_update() if lock else statement).mappings().all()
    plan_steps = {
        step.step_id: step
        for step in plan.ordered_steps
        if step.step_kind in {"EFFECT", "ADMISSION"}
    }
    observed: list[BoundStepValue] = []
    activated: set[str] = set()
    for row in rows:
        step = plan_steps.get(str(row["step_id"]))
        if step is None:
            raise ExactBindingConflict("persisted runtime step is absent from exact Plan")
        if row["state"] != "PENDING":
            activated.add(step.step_id)
        if row["state"] != "SUCCEEDED" or row["output_digest"] is None:
            continue
        observed.append(
            load_bound_runtime_output(
                connection,
                scope,
                tables,
                step,
                str(row["output_digest"]),
            )[0]
        )
    events = PUBLIC_TABLES["runtime_events"]
    statement = select(events).where(
        events.c.project_key == run["project_key"], events.c.run_id == run["run_id"],
        events.c.event_type == "ActiveChildrenSettled",
    ).order_by(events.c.seq)
    settled = connection.execute(statement.with_for_update(read=True) if lock else statement).mappings().all()
    settled_steps: set[str] = set()
    all_plan_steps = {step.step_id: step for step in plan.ordered_steps}
    requests = RuntimeJournalRepository(connection, scope).load_events(str(run["run_id"]))
    for event in settled:
        metadata = _event_metadata(event)
        step_id = metadata.get("source_step_id")
        if not isinstance(step_id, str):
            raise ExactBindingConflict(
                "active-child settlement lacks source step identity"
            )
        step = all_plan_steps.get(step_id)
        if (
            step is None
            or step.step_kind != "TRANSFORM"
            or step.transform_ref is None
            or step.transform_ref.name != TRAVERSAL_MATERIALIZER_TRANSFORM
            or step_id in settled_steps
            or event["payload_digest"] is None
            or event["schema_version"] != "mrw.runtime.event.active_children_settled.v1"
            or metadata.get("result_digest") != event["payload_digest"]
        ):
            raise ExactBindingConflict("active-child settlement/Plan binding drift")
        settled_steps.add(step_id)
        matching = tuple(row for row in requests if row["event_type"] == "TraversalMaterializationRequested"
                         and _event_metadata(row).get("source_step_id") == step_id)
        if len(matching) != 1 or matching[0]["schema_version"] != "mrw.runtime.event.traversal_materialization_requested.v1":
            raise ExactBindingConflict("settled traversal lacks one original materialization")
        request = _event_metadata(matching[0])
        descriptor = TraversalMaterialization(
            step_id=step_id,
            traversal_policy=_traversal_policy(request.get("traversal_policy")),
            input_ref=_read_project_value(
                connection,
                scope,
                tables,
                _metadata_string(request, "input_ref"),
                step.input_type,
            )[0],
            input_sequence_digest=_metadata_string(
                request, "input_sequence_digest"
            ),
            element_program_digest=_metadata_string(
                request, "element_program_digest"
            ),
            element_count=_db_int(request.get("element_count"), "element_count"),
            element_digests=_metadata_string_tuple(
                request.get("element_digests"), "element_digests"
            ),
            shape_digest=_metadata_string(request, "shape_digest"),
            binding_digest=_metadata_string(request, "binding_digest"),
            materialization_digest=_metadata_string(
                request, "materialization_digest"
            ),
        )
        relations = active_child_rows(connection, project_key=str(run["project_key"]),
                                      parent_run_id=str(run["run_id"]), source_step_id=step_id)
        children = tuple(_event_metadata(row) for row in relations)
        raw_digests = metadata.get("child_result_digests")
        digests = raw_digests if _is_object_sequence(raw_digests) else None
        if (not isinstance(metadata.get("child_count"), int) or isinstance(metadata.get("child_count"), bool)
                or metadata.get("child_count") != descriptor.element_count
                or descriptor.element_count != len(children)
                or len(descriptor.element_digests) != len(children)
                or metadata.get("child_run_ids") != [child["child_run_id"] for child in children]
                or digests is None or len(digests) != len(children)
                or any(child.get("materialization_digest") != descriptor.materialization_digest
                       or child.get("element_digest") != descriptor.element_digests[index]
                       for index, child in enumerate(children))):
            raise ExactBindingConflict("settled traversal ordered child binding drift")
        for digest in digests:
            if digest is not None:
                if not isinstance(digest, str):
                    raise ExactBindingConflict("settled traversal child result digest is invalid")
                require_digest(digest, "child_result_digest")
        bound, exact = load_bound_runtime_output(connection, scope, tables, step, str(event["payload_digest"]))
        if bound.value_ref.storage_ref != event["payload_ref"]:
            raise ExactBindingConflict("settled traversal result reference drift")
        observed.append(SettledTraversalValue(bound.step_id, bound.value_ref, bound.value, descriptor, exact_bytes=exact))
    return tuple(observed), frozenset(activated)


def _traversal_request_event(
    connection: Connection,
    *,
    project_key: str,
    run_id: str,
    descriptor: TraversalMaterialization,
) -> bool:
    events = PUBLIC_TABLES["runtime_events"]
    rows = connection.execute(
        select(events.c.event_metadata_json).where(
            events.c.project_key == project_key,
            events.c.run_id == run_id,
            events.c.event_type == "TraversalMaterializationRequested",
        )
    ).mappings().all()
    matches = tuple(
        row
        for row in rows
        if row["event_metadata_json"].get("source_step_id") == descriptor.step_id
    )
    if not matches:
        return False
    if len(matches) != 1:
        raise ExactBindingConflict("traversal materialization request is ambiguous")
    metadata = matches[0]["event_metadata_json"]
    expected = {
        "input_sequence_digest": descriptor.input_sequence_digest,
        "element_program_digest": descriptor.element_program_digest,
        "element_count": descriptor.element_count,
        "element_digests": list(descriptor.element_digests),
        "shape_digest": descriptor.shape_digest,
        "binding_digest": descriptor.binding_digest,
        "materialization_digest": descriptor.materialization_digest,
    }
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise ExactBindingConflict("traversal materialization request digest drift")
    return True


def _require_traversal_request(
    connection: Connection,
    parent: RuntimeRow,
    descriptor: TraversalMaterialization,
) -> None:
    if not _traversal_request_event(
        connection,
        project_key=str(parent["project_key"]),
        run_id=str(parent["run_id"]),
        descriptor=descriptor,
    ):
        raise ExactBindingConflict("active child has no traversal request")


def _require_empty_traversal_request(
    connection: Connection,
    parent: RuntimeRow,
    *,
    source_step_id: str,
) -> None:
    events = PUBLIC_TABLES["runtime_events"]
    rows = tuple(
        connection.execute(
            select(events.c.event_metadata_json).where(
                events.c.project_key == parent["project_key"],
                events.c.run_id == parent["run_id"],
                events.c.event_type == "TraversalMaterializationRequested",
            )
        ).mappings()
    )
    matches = tuple(
        _event_metadata(row)
        for row in rows
        if _event_metadata(row).get("source_step_id") == source_step_id
    )
    if len(matches) != 1:
        raise ExactBindingConflict("empty traversal request is absent or ambiguous")
    metadata = matches[0]
    if metadata.get("element_count") != 0 or metadata.get("element_digests") not in (
        [],
        (),
    ):
        raise ExactBindingConflict("empty traversal request shape is not empty")
    for key in (
        "input_sequence_digest",
        "element_program_digest",
        "shape_digest",
        "binding_digest",
        "materialization_digest",
    ):
        value = metadata.get(key)
        if not isinstance(value, str):
            raise ExactBindingConflict("empty traversal request digest is absent")
        require_digest(value, key)


def _active_child_authority_scope(
    connection: Connection,
    scope: RuntimeScope,
    *,
    run_id: str,
    authority_step_id: str | None,
    authority_digest: str | None,
    observed_at: datetime,
) -> RuntimeScope:
    """Recover the parent's authority subject before qualifying child runs."""

    if authority_step_id is None or authority_digest is None:
        raise ExactBindingConflict(
            "active traversal requires its terminal authority binding"
        )
    authorizations = PUBLIC_TABLES["runtime_step_authorizations"]
    rows = tuple(
        connection.execute(
            select(authorizations)
            .where(
                authorizations.c.project_key == scope.project_scope.project_key,
                authorizations.c.run_id == run_id,
                authorizations.c.step_id == authority_step_id,
                authorizations.c.authorization_digest == authority_digest,
            )
            .with_for_update(read=True)
        ).mappings()
    )
    if len(rows) != 1:
        raise ExactBindingConflict(
            "active traversal lacks one stored parent authorization"
        )
    stored = validate_authorization_row(rows[0])
    authority_scope = RuntimeScope(
        project_scope=scope.project_scope,
        actor_id=stored.actor_id,
    )
    current = PostgresAuthorityProvider(
        connection,
        authority_scope,
    ).current_step_binding(run_id, authority_step_id, now=observed_at)
    require_current_authority(stored, current, now=observed_at)
    return authority_scope


def read_linked_runtime_frontier(
    connection: Connection,
    *,
    source_work_item_id: str,
) -> LinkedRuntimeFrontier:
    """Read READY work across one exact active-child lineage component."""

    work = PUBLIC_TABLES["runtime_work_items"]
    sources = tuple(
        connection.execute(
            select(work.c.project_key, work.c.run_id).where(
                work.c.work_item_id == source_work_item_id,
            )
        ).mappings()
    )
    if len(sources) != 1:
        raise ExactBindingConflict("source work item is absent or ambiguous")
    project_key = str(sources[0]["project_key"])
    source_run_id = str(sources[0]["run_id"])

    events = PUBLIC_TABLES["runtime_events"]
    edges = tuple(
        connection.execute(
            select(events.c.run_id, events.c.event_metadata_json)
            .where(
                events.c.project_key == project_key,
                events.c.event_type == "ActiveChildMaterialized",
            )
            .order_by(events.c.run_id, events.c.seq)
        ).mappings()
    )
    parent_by_child: dict[str, str] = {}
    children_by_parent: dict[str, list[str]] = {}
    for edge in edges:
        parent_id = str(edge["run_id"])
        metadata = _event_metadata(edge)
        child_id = metadata.get("child_run_id")
        if not isinstance(child_id, str) or not child_id or child_id == parent_id:
            raise ExactBindingConflict("active-child lineage event is invalid")
        prior = parent_by_child.setdefault(child_id, parent_id)
        if prior != parent_id:
            raise ExactBindingConflict("active child has multiple parent runs")
        siblings = children_by_parent.setdefault(parent_id, [])
        if child_id in siblings:
            raise ExactBindingConflict("active-child lineage edge is duplicated")
        siblings.append(child_id)

    root_run_id = source_run_id
    ancestors: set[str] = set()
    while root_run_id in parent_by_child:
        if root_run_id in ancestors:
            raise ExactBindingConflict("active-child lineage contains a cycle")
        ancestors.add(root_run_id)
        root_run_id = parent_by_child[root_run_id]

    ordered_runs: list[str] = []
    pending = [root_run_id]
    while pending:
        run_id = pending.pop(0)
        if run_id in ordered_runs:
            raise ExactBindingConflict("active-child lineage contains a cycle")
        ordered_runs.append(run_id)
        pending.extend(children_by_parent.get(run_id, ()))

    runs = PUBLIC_TABLES["runtime_runs"]
    run_rows = tuple(
        connection.execute(
            select(runs.c.run_id).where(
                runs.c.project_key == project_key,
                runs.c.run_id.in_(tuple(ordered_runs)),
            )
        ).mappings()
    )
    if {str(row["run_id"]) for row in run_rows} != set(ordered_runs):
        raise ExactBindingConflict("active-child lineage names an absent run")

    frontier_rows = tuple(
        connection.execute(
            select(work.c.work_item_id, work.c.run_id, work.c.due_at)
            .join(
                runs,
                (runs.c.project_key == work.c.project_key)
                & (runs.c.run_id == work.c.run_id),
            )
            .where(
                work.c.project_key == project_key,
                work.c.run_id.in_(tuple(ordered_runs)),
                work.c.state == "READY",
                runs.c.cancellation_requested.is_(False),
            )
            .order_by(work.c.due_at, work.c.enqueue_seq, work.c.work_item_id)
        ).mappings()
    )
    ready_work = tuple(
        LinkedRuntimeWork(
            work_item_id=str(row["work_item_id"]),
            run_id=str(row["run_id"]),
            due_at=row["due_at"],
        )
        for row in frontier_rows
    )
    return LinkedRuntimeFrontier(
        project_key=project_key,
        source_work_item_id=source_work_item_id,
        root_run_id=root_run_id,
        related_run_ids=tuple(ordered_runs),
        ready_work=ready_work,
    )


def active_child_rows(
    connection: Connection,
    *,
    project_key: str,
    parent_run_id: str,
    source_step_id: str,
) -> tuple[dict[str, Any], ...]:
    events = PUBLIC_TABLES["runtime_events"]
    rows = connection.execute(
        select(events)
        .where(
            events.c.project_key == project_key,
            events.c.run_id == parent_run_id,
            events.c.event_type == "ActiveChildMaterialized",
        )
        .order_by(events.c.seq)
    ).mappings().all()
    selected = tuple(
        dict(row)
        for row in rows
        if _event_metadata(row).get("source_step_id") == source_step_id
    )
    indices = tuple(
        _event_metadata(row).get("element_index") for row in selected
    )
    if indices != tuple(range(len(selected))):
        raise ExactBindingConflict("active child lineage order is not contiguous")
    return selected


def ordered_active_child_lineage(
    connection: Connection, *, project_key: str, child_run_id: str,
) -> tuple[str, tuple[dict[str, Any], ...], int] | None:
    """Read one exact, contiguous public traversal lineage for a child."""
    events = PUBLIC_TABLES["runtime_events"]
    matches = tuple(connection.execute(select(events).where(
        events.c.project_key == project_key, events.c.event_type == "ActiveChildMaterialized",
        events.c.event_metadata_json["child_run_id"].astext == child_run_id,
    )).mappings())
    if not matches:
        return None
    if len(matches) != 1:
        raise ExactBindingConflict("ordered child has ambiguous parent lineage")
    relation = _event_metadata(matches[0])
    source_step_id, index = relation.get("source_step_id"), relation.get("element_index")
    if not isinstance(source_step_id, str) or not source_step_id or type(index) is not int or index < 0:
        raise ExactBindingConflict("ordered child lineage identity is invalid")
    rows = active_child_rows(connection, project_key=project_key,
                             parent_run_id=str(matches[0]["run_id"]), source_step_id=source_step_id)
    metadata = tuple(_event_metadata(row) for row in rows)
    if (index >= len(metadata) or metadata[index] != relation
            or any(type(item.get("element_index")) is not int for item in metadata)
            or len({item.get("child_run_id") for item in metadata}) != len(metadata)
            or any(item.get("materialization_digest") != relation.get("materialization_digest") for item in metadata)):
        raise ExactBindingConflict("ordered child lineage binding drift")
    return str(matches[0]["run_id"]), metadata, index


def read_ordered_prior_effect_outputs(
    connection: Connection, scope: RuntimeScope, assignment: RuntimeAssignment,
) -> tuple[bytes, tuple[tuple[bytes, bytes], ...]]:
    """Read exact earlier sibling outputs for the current assigned effect contract."""
    lineage = ordered_active_child_lineage(connection, project_key=assignment.project_key,
                                           child_run_id=assignment.run_id)
    if lineage is None or assignment.project_key != scope.project_scope.project_key:
        raise ExactBindingConflict("ordered effect lacks its exact active child lineage")
    parent_id, relations, index = lineage
    journal = RuntimeJournalRepository(connection, scope)
    parent = journal.load_run(parent_id, for_update=True)
    if parent["state"] != "WAITING" or parent["cancellation_requested"]:
        raise ExactBindingConflict("ordered effect parent is not waiting")
    tables = project_tables(MetaData(), scope.project_scope.resolved_schema)
    reader = PostgresRuntimeActivationBindingAdapter()
    outputs: list[tuple[bytes, bytes]] = []
    current_input: bytes | None = None
    root_keys = ("root_value_identity", "root_value_ref", "root_value_digest", "materialization_digest")
    for position, relation in enumerate(relations[:index + 1]):
        if any(relation[key] != relations[index][key] for key in root_keys):
            raise ExactBindingConflict("ordered effect root binding drift")
        child = dict(journal.load_run(str(relation["child_run_id"])))
        _require_run_scope(child, scope)
        if position < index and child["state"] != "COMPLETED":
            raise ExactBindingConflict("ordered effect prefix is not completed")
        program = ProgramRepository(connection, tables).get(scope, str(child["program_id"]),
                                                            expected_digest=str(child["program_digest"]))
        plan = PlanRepository(connection, tables).get(scope, str(child["plan_digest"]))
        require_program_plan_run(program, plan, child)
        refs = {ref for atom in program_atoms(program.root) for ref in atom.operation.input_refs
                if ref.storage_ref == relation["input_ref"] and ref.content_digest == relation["input_digest"]}
        if len(refs) != 1 or program.program_digest != relation["child_program_digest"]:
            raise ExactBindingConflict("ordered effect child invocation binding drift")
        input_bytes = reader.read_value_bytes(connection, scope, tables, next(iter(refs)))
        steps = tuple(step for step in plan.ordered_steps
                      if step.operation_contract_ref == assignment.operation_contract_ref)
        if len(steps) != 1:
            raise ExactBindingConflict("ordered child lacks one exact effect contract")
        step = steps[0]
        if position == index:
            if step.step_id != assignment.step_id:
                raise ExactBindingConflict("ordered effect assignment step drift")
            current_input = input_bytes
            continue
        stored = PUBLIC_TABLES["runtime_steps"]
        row = one_mapping(connection.execute(select(stored).where(
            stored.c.project_key == assignment.project_key, stored.c.run_id == child["run_id"],
            stored.c.step_id == step.step_id,
        )))
        if row is None or row["state"] != "SUCCEEDED" or not row["output_digest"]:
            raise ExactBindingConflict("ordered effect prefix lacks a succeeded output")
        _, output_bytes = load_bound_runtime_output(connection, scope, tables, step, str(row["output_digest"]))
        outputs.append((input_bytes, output_bytes))
    if current_input is None:
        raise ExactBindingConflict("ordered effect current input is absent")
    return current_input, tuple(outputs)


def _active_children_settled_event(
    connection: Connection,
    *,
    project_key: str,
    parent_run_id: str,
    source_step_id: str,
) -> dict[str, Any] | None:
    events = PUBLIC_TABLES["runtime_events"]
    rows = connection.execute(
        select(events).where(
            events.c.project_key == project_key,
            events.c.run_id == parent_run_id,
            events.c.event_type == "ActiveChildrenSettled",
        )
    ).mappings().all()
    matches = tuple(
        dict(row)
        for row in rows
        if _event_metadata(row).get("source_step_id") == source_step_id
    )
    if len(matches) > 1:
        raise ExactBindingConflict("active child settlement is ambiguous")
    return matches[0] if matches else None


def _publish_active_child_result(
    connection: Connection,
    scope: RuntimeScope,
    tables: ProjectTables,
    *,
    parent_run_id: str,
    source_step: CompiledStep,
    observations: tuple[ActiveChildTerminalObservation, ...],
    content: bytes,
) -> ValueRef:
    digest = hashlib.sha256(content).hexdigest()
    return _publish_typed_content(
        connection, scope, tables, value_id=f"active-children:{digest}",
        object_type=source_step.output_type, content=content, incarnation=f"active-children:{digest}",
        provenance={"schema": "mrw.runtime.active-children-result.v1",
                    "parent_run_id": parent_run_id, "source_step_id": source_step.step_id,
                    "ordered_child_digests": tuple(item.result_ref.content_digest
                                                   for item in observations if item.result_ref is not None)},
    )


def _publish_typed_content(
    connection: Connection, scope: RuntimeScope, tables: ProjectTables, *,
    value_id: str, object_type: ObjectType, content: bytes,
    incarnation: str, provenance: dict[str, object],
) -> ValueRef:
    """Reuse canonical typed content; each producing occurrence stays in its journal."""
    digest = hashlib.sha256(content).hexdigest()
    ref = _existing_project_content(connection, scope, tables, object_type, digest, content)
    if ref is None:
        locator = f"project-value:{value_id}"
        ValueRepository(connection, tables).put_exact(
            scope, value_id=value_id, object_type=object_type.type_id, codec_id=object_type.codec_id,
            content=content, expected_digest=digest, provenance_digest=canonical_digest(provenance),
            provenance=provenance, expected_revision=0, expected_incarnation=incarnation, source_ref=locator,
        )
        ref = _read_project_value(connection, scope, tables, locator, object_type)[0]
    _publish_runtime_value(connection, scope, tables, value_id=ref.value_id,
                           object_type=ref.object_type, digest=digest, byte_size=len(content))
    return ref


def _require_settlement_bytes(value: object) -> bytes:
    if not isinstance(value, bytes):
        raise ExactBindingConflict(
            "active child settlement builder returned no bytes"
        )
    return value


def _db_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ExactBindingConflict(f"{field_name} is not an exact database integer")
    return value


def _metadata_string(values: Mapping[str, object], field_name: str) -> str:
    value = values.get(field_name)
    if not isinstance(value, str):
        raise ExactBindingConflict(f"runtime event {field_name} is not a string")
    return value


def _traversal_policy(
    value: object,
) -> Literal["STATIC_SHAPE", "MATERIALIZED_SHAPE"]:
    if value == "STATIC_SHAPE":
        return "STATIC_SHAPE"
    if value == "MATERIALIZED_SHAPE":
        return "MATERIALIZED_SHAPE"
    raise ExactBindingConflict("runtime event traversal_policy is invalid")


def _is_object_sequence(
    value: object,
) -> TypeGuard[tuple[object, ...] | list[object]]:
    return isinstance(value, (tuple, list))


def _metadata_string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not _is_object_sequence(value) or any(
        not isinstance(item, str) for item in value
    ):
        raise ExactBindingConflict(
            f"runtime event {field_name} is not a string sequence"
        )
    return tuple(item for item in value if isinstance(item, str))


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _is_object_dict(value: object) -> TypeGuard[dict[object, object]]:
    return isinstance(value, dict)


def _event_metadata(row: object) -> dict[str, object]:
    if not _is_object_mapping(row):
        raise ExactBindingConflict("runtime event row is not a mapping")
    raw = row.get("event_metadata_json")
    if not _is_object_dict(raw):
        raise ExactBindingConflict("runtime event metadata is not an object")
    if any(not isinstance(key, str) for key in raw):
        raise ExactBindingConflict("runtime event metadata keys must be strings")
    return {key: value for key, value in raw.items() if isinstance(key, str)}


def load_bound_runtime_output(
    connection: Connection, scope: RuntimeScope, tables: ProjectTables,
    step: CompiledStep, output_digest: str,
) -> tuple[BoundStepValue, bytes]:
    """Read one exact typed runtime output and its digest-verified bytes."""
    require_digest(output_digest, "step output_digest")
    public = PUBLIC_TABLES["runtime_values"]
    rows = connection.execute(select(public).where(
        public.c.project_key == scope.project_scope.project_key,
        public.c.content_digest == output_digest, public.c.codec_id == step.output_type.codec_id,
        public.c.state == "AVAILABLE",
    )).mappings().all()
    if len(rows) != 1:
        raise ExactBindingConflict(f"terminal output lacks one exact public value binding: step={step.step_id}, matches={len(rows)}")
    row = rows[0]
    ref, exact, _ = _read_project_value(connection, scope, tables, str(row["project_value_ref"]), step.output_type)
    if (ref.content_digest != output_digest or ref.object_type.type_id != row["object_type"]
            or ref.byte_size != row["byte_size"] or ref.value_id != row["value_id"]):
        raise ExactBindingConflict("terminal output public/project value binding drift")
    try:
        value = json.loads(exact)
    except (UnicodeDecodeError, json.JSONDecodeError):
        value = exact
    return BoundStepValue(step.step_id, ref, value, exact_bytes=exact), exact


def _read_project_value(
    connection: Connection,
    scope: RuntimeScope,
    tables: ProjectTables,
    locator: str,
    object_type: ObjectType,
) -> tuple[ValueRef, bytes, RowMapping]:
    if not locator.startswith("project-value:"):
        raise ExactBindingConflict("activation dynamic input is not project-value owned")
    value_id = locator.removeprefix("project-value:")
    if not value_id:
        raise ExactBindingConflict("activation dynamic project-value locator is empty")
    row = one_mapping(
        connection.execute(
            select(tables.successor_values).where(
                tables.successor_values.c.project_key
                == scope.project_scope.project_key,
                tables.successor_values.c.value_id == value_id,
                tables.successor_values.c.codec_id == object_type.codec_id,
                tables.successor_values.c.state == "AVAILABLE",
            )
        )
    )
    if row is None:
        raise ExactBindingConflict("activation dynamic project value is absent")
    actual_type = object_type
    if row["object_type"] != object_type.type_id:
        if (
            object_type.type_id != "ClaimOrGap.v1"
            or row["object_type"] not in {"Claim.v1", "Gap.v1"}
        ):
            raise ExactBindingConflict("activation dynamic project value type drift")
        actual_type = OBJECT_TYPE_BY_ID[str(row["object_type"])]
    exact = ValueRepository(connection, tables).get_exact(
        scope, value_id, expected_revision=int(row["revision"]),
        expected_incarnation=str(row["incarnation"]), expected_digest=str(row["content_digest"]),
    )
    if len(exact) != int(row["byte_size"]):
        raise ExactBindingConflict("activation dynamic project value readback drift")
    ref = ValueRef(
        value_id=value_id,
        project_key=scope.project_scope.project_key,
        object_type=actual_type,
        codec_id=str(row["codec_id"]),
        content_digest=str(row["content_digest"]),
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=locator,
        byte_size=int(row["byte_size"]),
        provenance_digest=str(row["provenance_digest"]),
    )
    return ref, exact, row


def _dynamic_dependency_groups(
    step: CompiledStep,
    plan: ExecutionPlan,
) -> tuple[tuple[CompiledStep, ...], ...]:
    groups = activation_dependency_groups(plan, step)
    if isinstance(groups, Failure):
        raise ExactBindingConflict(groups.message)
    return groups


def _bind_materializations_to_project(
    result: ActivationResult, plan: ExecutionPlan, *,
    canonical_value: Callable[[ValueMaterialization], ValueRef | None] | None = None,
) -> ActivationResult:
    replacements: dict[ValueRef, ValueRef] = {}
    content_refs: dict[tuple[str, str], ValueRef] = {}
    materializations: list[ValueMaterialization] = []
    for item in result.materializations:
        ref = item.value_ref
        dependencies = tuple(
            replacements.get(dependency, dependency)
            for dependency in item.dependency_refs
        )
        provenance_digest = sha256_hex(
            {
                "schema_version": "mrw.activation-value-provenance.v1",
                "program_digest": plan.program_digest,
                "plan_digest": plan.plan_digest,
                "step_id": item.step_id,
                "ordered_dependencies": tuple(
                    dependency.to_plain() for dependency in dependencies
                ),
            }
        )
        rebound = replace(
            ref,
            storage_kind="project_value_ref",
            store_id="successor_values",
            store_version="1",
            storage_ref=f"project-value:{ref.value_id}",
            provenance_digest=provenance_digest,
        )
        content_key = (ref.content_digest, ref.codec_id)
        canonical = content_refs.get(content_key)
        if canonical is None and canonical_value is not None:
            canonical = canonical_value(item)
        if canonical is not None:
            if (canonical.project_key, canonical.object_type, canonical.codec_id,
                canonical.content_digest, canonical.byte_size) != (
                ref.project_key, ref.object_type, ref.codec_id, ref.content_digest, ref.byte_size,
            ):
                raise ExactBindingConflict("pure materialization canonical value binding drift")
            rebound = canonical
        content_refs[content_key] = rebound
        replacements[ref] = rebound
        digest = sha256_hex(
            {
                "schema_version": "mrw.value-materialization.v1",
                "step_id": item.step_id,
                "value_ref": rebound.to_plain(),
                "exact_bytes_digest": rebound.content_digest,
                "ordered_dependencies": tuple(ref.to_plain() for ref in dependencies),
            }
        )
        materializations.append(
            replace(
                item,
                value_ref=rebound,
                dependency_refs=dependencies,
                materialization_digest=digest,
            )
        )
    values = tuple(
        replace(item, value_ref=replacements.get(item.value_ref, item.value_ref))
        for item in result.values
    )
    activations = tuple(
        finalize_activation_descriptor(plan, _rebind_descriptor(item, replacements))
        for item in result.activations
    )
    return replace(
        result,
        values=values,
        materializations=tuple(materializations),
        activations=activations,
        traversal_materializations=tuple(
            replace(
                item, input_ref=replacements.get(item.input_ref, item.input_ref),
                materialization_digest=sha256_hex({
                    "schema": "mrw.traverse-ordered.materialization.v1",
                    "program_digest": plan.program_digest, "plan_digest": plan.plan_digest,
                    "step_id": item.step_id,
                    "input_ref": replacements.get(item.input_ref, item.input_ref).to_plain(),
                    "input_sequence_digest": item.input_sequence_digest,
                    "shape_digest": item.shape_digest, "binding_digest": item.binding_digest,
                }),
            )
            for item in result.traversal_materializations
        ),
    )


def _rebind_descriptor(
    descriptor: ReadyActivation, replacements: Mapping[ValueRef, ValueRef]
) -> ReadyActivation:
    dynamic = tuple(replacements.get(ref, ref) for ref in descriptor.ordered_dependency_refs)
    return replace(descriptor, ordered_dependency_refs=dynamic)


def _existing_project_content(
    connection: Connection, scope: RuntimeScope, tables: ProjectTables,
    object_type: ObjectType, content_digest: str, exact_bytes: bytes,
) -> ValueRef | None:
    """Resolve immutable content to its original project identity and provenance."""
    table = tables.successor_values
    row = one_mapping(connection.execute(select(table).where(
        table.c.project_key == scope.project_scope.project_key,
        table.c.content_digest == content_digest, table.c.codec_id == object_type.codec_id,
    )))
    if row is None:
        return None
    actual, exact, _ = _read_project_value(
        connection, scope, tables, f"project-value:{row['value_id']}", object_type,
    )
    if exact != exact_bytes:
        raise ExactBindingConflict("pure materialization canonical bytes drift")
    expected_intent = derive_value_write_intent_digest(
        project_key=str(row["project_key"]), value_id=str(row["value_id"]),
        object_type=str(row["object_type"]), codec_id=str(row["codec_id"]),
        content_digest=str(row["content_digest"]), provenance_digest=str(row["provenance_digest"]),
        source_ref=row["source_ref"], expected_revision=0,
        expected_incarnation=str(row["incarnation"]), state=str(row["state"]),
    )
    if row["write_intent_digest"] != expected_intent:
        raise ExactBindingConflict("pure materialization canonical write intent drift")
    return actual


def _materialize_values(
    connection: Connection,
    scope: RuntimeScope,
    tables: ProjectTables,
    program: ProgramSpec,
    plan: ExecutionPlan,
    result: ActivationResult,
) -> tuple[str, ...]:
    ids: list[str] = []
    for item in result.materializations:
        ref = item.value_ref
        provenance = {
            "schema_version": "mrw.activation-value-provenance.v1",
            "program_digest": program.program_digest,
            "plan_digest": plan.plan_digest,
            "step_id": item.step_id,
            "ordered_dependencies": [dependency.to_plain() for dependency in item.dependency_refs],
        }
        existing_ref = _existing_project_content(connection, scope, tables, ref.object_type, ref.content_digest, item.exact_bytes)
        if existing_ref is not None:
            if existing_ref != ref:
                raise ExactBindingConflict("pure materialization did not reuse canonical value")
        else:
            if sha256_hex(provenance) != ref.provenance_digest:
                raise ExactBindingConflict("pure materialization provenance drift")
            ValueRepository(connection, tables).put_exact(
                scope, value_id=ref.value_id, object_type=ref.object_type.type_id,
                codec_id=ref.codec_id, content=item.exact_bytes,
                expected_digest=ref.content_digest, provenance_digest=ref.provenance_digest,
                expected_revision=0, expected_incarnation=f"activation:{plan.plan_id}:{item.step_id}",
                provenance=provenance,
            )
        _publish_runtime_value(connection, scope, tables, value_id=ref.value_id,
                               object_type=ref.object_type, digest=ref.content_digest,
                               byte_size=ref.byte_size)
        ids.append(ref.value_id)
    return tuple(ids)


def _publish_runtime_value(
    connection: Connection, scope: RuntimeScope, tables: ProjectTables, *,
    value_id: str, object_type: ObjectType, digest: str, byte_size: int,
) -> None:
    """Project one project-owned value into the original opaque runtime index."""
    locator = f"project-value:{value_id}"
    RuntimeValueRepository(connection, scope).put_exact(RuntimeValueBinding(
        value_id=value_id, object_type=object_type.type_id, codec_id=object_type.codec_id,
        content_digest=digest, byte_size=byte_size, project_value_ref=locator,
        storage_digest=canonical_digest({
            "contract": "ProjectRuntimeValueBinding.v1", "project_key": scope.project_scope.project_key,
            "runtime_value_id": value_id, "project_value_ref": locator,
            "content_digest": digest, "codec_id": object_type.codec_id,
        }),
        write_intent_digest=_value_write_intent(connection, tables, scope, value_id),
    ))


def _value_write_intent(
    connection: Connection, tables: ProjectTables, scope: RuntimeScope, value_id: str
) -> str:
    row = one_mapping(
        connection.execute(
            select(tables.successor_values.c.write_intent_digest).where(
                tables.successor_values.c.project_key == scope.project_scope.project_key,
                tables.successor_values.c.value_id == value_id,
            )
        )
    )
    if row is None:
        raise ExactBindingConflict("materialized value write intent readback is absent")
    return str(row["write_intent_digest"])


def _authorization_for(
    connection: Connection,
    run: RuntimeRow,
    qualified: QualifiedPlan,
    step: CompiledStep,
    descriptor: ReadyActivation,
    catalog: OperationActivationCatalog,
    now: datetime,
) -> StepAuthorizationBinding:
    frozen = qualified.step_binding(step.step_id)
    if frozen is None:
        raise ExactBindingConflict("QualifiedPlan lacks activated step authorization")
    table = PUBLIC_TABLES["runtime_step_authorizations"]
    rows = connection.execute(
        select(table)
        .where(
            table.c.project_key == run["project_key"],
            table.c.run_id == run["run_id"],
            table.c.step_id == step.step_id,
            table.c.authorization_digest == frozen.binding_digest,
        )
        .with_for_update()
    ).mappings().all()
    if len(rows) != 1:
        raise ExactBindingConflict("activated step lacks one exact authorization row")
    persisted = validate_authorization_row(rows[0])
    if persisted != frozen:
        raise ExactBindingConflict("persisted authorization differs from QualifiedPlan")
    if step.operation_contract_ref is None:
        raise ExactBindingConflict("activated step lacks operation contract")
    entry = catalog.entry_for(step.operation_contract_ref.contract_digest)
    expected = {
        "operation_kind": step.operation_contract_ref.kind,
        "operation_contract_digest": step.operation_contract_ref.contract_digest,
        "capability_id": entry.queue_eligibility.capability_id,
        "claim_owner": "successor",
        "payload_digest": descriptor.payload_ref.content_digest,
        "project_key": run["project_key"],
        "project_registry_revision": run["project_registry_revision"],
        "project_scope_digest": run["project_scope_digest"],
        "interpreter_binding_digest": entry.interpreter_binding.binding_digest,
        "deployment_catalog_digest": entry.interpreter_binding.deployment_catalog_digest,
        "resource_policy_epoch": entry.queue_eligibility.policy_epoch,
        "queue_eligibility_digest": entry.queue_eligibility.eligibility_digest,
    }
    drift = [name for name, value in expected.items() if getattr(persisted, name) != value]
    if drift:
        raise ExactBindingConflict(
            "activation catalog/authorization drift: " + ", ".join(drift)
        )
    if persisted.expires_at <= now:
        raise ExactBindingConflict("activation step authorization is expired")
    if (
        entry.queue_eligibility.project_key != run["project_key"]
        or entry.queue_eligibility.policy_digest != entry.resource_policy_digest
        or entry.interpreter_binding.project_scope_digest != run["project_scope_digest"]
        or entry.interpreter_binding.resource_policy_epoch
        != entry.queue_eligibility.policy_epoch
    ):
        raise ExactBindingConflict("activation catalog scope/resource binding drift")
    return persisted


def _assignment(
    *,
    run: RuntimeRow,
    plan: ExecutionPlan,
    step: CompiledStep,
    descriptor: ReadyActivation,
    authorization: StepAuthorizationBinding,
    entry: ActivationCatalogEntry,
    trace_id: str,
) -> RuntimeAssignment:
    assert step.operation_contract_ref is not None
    if step.return_contract_ref is None:
        raise ExactBindingConflict("activated step lacks named return contract")
    kind = (
        AssignmentKind.INTERPRET
        if step.step_kind == "EFFECT"
        else AssignmentKind.VERIFY_ADMIT
    )
    role = CompiledStepRole.EFFECT if step.step_kind == "EFFECT" else CompiledStepRole.ADMISSION
    return_binding = ReturnContractBinding.from_contract(
        step.return_contract_ref, step.return_contract
    )
    compiled_admission = None
    if kind is AssignmentKind.VERIFY_ADMIT:
        admission = step.admission
        if admission is None or admission.admission_step_id != step.step_id:
            raise ExactBindingConflict("admission step lacks exact compiled admission")
        control = _control_for_step(plan.control_root, step.step_id)
        compiled_admission = CompiledAdmissionBinding.from_content(
            plan_digest=plan.plan_digest,
            effect_step_id=admission.effect_step_id,
            admission_step_id=admission.admission_step_id,
            operation_contract_digest=step.operation_contract_ref.contract_digest,
            return_contract_ref=step.return_contract_ref,
            return_contract_digest=return_binding.binding_digest,
            source_map_digest=sha256_hex(
                tuple(
                    item
                    for item in plan.source_map
                    if step.step_id in item.step_ids
                )
            ),
            control_digest=control.control_digest,
        )
    work_digest = canonical_digest(
        {
            "schema_version": "mrw.activation-work-id.v1",
            "run_id": run["run_id"],
            "step_id": step.step_id,
            "execution_epoch": run["execution_epoch"],
            "input_closure_digest": descriptor.input_closure_digest,
        }
    )
    return RuntimeAssignment(
        runtime_protocol_version=entry.interpreter_binding.runtime_protocol_version,
        work_item_id=f"work:activation:{work_digest}",
        assignment_kind=kind,
        project_key=str(run["project_key"]),
        run_id=str(run["run_id"]),
        step_id=step.step_id,
        step_role=role,
        capability_id=entry.queue_eligibility.capability_id,
        operation_contract_ref=step.operation_contract_ref,
        operation_contract_digest=step.operation_contract_ref.contract_digest,
        return_contract_binding=return_binding,
        compiled_admission_binding=compiled_admission,
        handler_binding_kind=HandlerBindingKind.INTERPRETER,
        handler_binding_ref=(
            f"handler-binding:sha256:{entry.interpreter_binding.binding_digest}"
        ),
        handler_binding_digest=entry.interpreter_binding.binding_digest,
        handler_binding=entry.interpreter_binding,
        program_digest=str(run["program_digest"]),
        plan_digest=plan.plan_digest,
        deployment_catalog_digest=entry.interpreter_binding.deployment_catalog_digest,
        execution_epoch=_db_int(run["execution_epoch"], "execution_epoch"),
        incarnation=str(run["incarnation"]),
        input_refs=tuple(ref.storage_ref for ref in descriptor.ordered_input_refs),
        input_closure_digest=descriptor.input_closure_digest,
        payload_ref=descriptor.payload_ref.storage_ref,
        payload_digest=descriptor.payload_ref.content_digest,
        queue_eligibility_digest=entry.queue_eligibility.eligibility_digest,
        resource_policy_epoch=entry.queue_eligibility.policy_epoch,
        claim_authority_epoch=authorization.claim_authority_epoch,
        claim_policy_digest=authorization.claim_policy_digest,
        expected_step_revision=0,
        trace_id=f"{trace_id}:{step.step_id}",
    )


def _envelope(
    assignment: RuntimeAssignment,
    authorization: StepAuthorizationBinding,
    entry: ActivationCatalogEntry,
    qualification_digest: str,
):
    eligibility = entry.queue_eligibility
    return AssignmentEnvelope(
        assignment=assignment,
        required_node_profile_selector=entry.required_node_profile_selector,
        authority_digest=authorization.binding_digest,
        resource_policy_digest=entry.resource_policy_digest,
        fairness_key=entry.fairness_key,
        qualification_digest=qualification_digest,
        resource_class=eligibility.resource_class.value,
        resource_units=eligibility.units,
        concurrency_key=eligibility.concurrency_key,
        provider_key=eligibility.provider_key,
        recovery_binding=entry.recovery_binding,
        authoritative_readback_profile_ref=(
            entry.recovery_binding.authoritative_readback_profile_ref
        ),
        declared_priority=entry.declared_priority,
    )


def _step_values(
    run: RuntimeRow,
    step: CompiledStep,
    descriptor: ReadyActivation,
    authorization: StepAuthorizationBinding,
    entry: ActivationCatalogEntry,
    now: datetime,
) -> dict[str, object]:
    assert step.operation_contract_ref is not None
    return {
        "project_key": run["project_key"],
        "run_id": run["run_id"],
        "step_id": step.step_id,
        "operation_id": descriptor.operation_id,
        "operation_kind": step.operation_contract_ref.kind,
        "operation_version": step.operation_contract_ref.contract_version,
        "state": "READY",
        "revision": 0,
        "execution_epoch": run["execution_epoch"],
        "input_digest": descriptor.input_closure_digest,
        "output_digest": None,
        "failure_digest": None,
        "effect_class": entry.effect_class,
        "resource_class": entry.queue_eligibility.resource_class.value,
        "concurrency_key": entry.queue_eligibility.concurrency_key,
        "capability_id": entry.queue_eligibility.capability_id,
        "claim_owner": authorization.claim_owner,
        "claim_authority_epoch": authorization.claim_authority_epoch,
        "claim_policy_digest": authorization.claim_policy_digest,
        "attempt_count": 0,
        "max_attempts": entry.max_attempts,
        "created_at": now,
        "updated_at": now,
    }


def _require_exact_existing(
    existing: RuntimeRow, expected: Mapping[str, object], label: str
) -> None:
    immutable = tuple(
        key
        for key in expected
        if key not in {"created_at", "updated_at", "state", "revision"}
    )
    drift = [key for key in immutable if existing.get(key) != expected[key]]
    if drift:
        raise ExactBindingConflict(f"existing {label} drift: {', '.join(drift)}")


def _activate_pending_step(
    connection: Connection,
    table: Any,
    existing: RuntimeRow,
    ready: Mapping[str, object],
) -> None:
    if (
        existing.get("state") != "PENDING"
        or _db_int(existing.get("revision", -1), "revision") != 0
    ):
        raise ExactBindingConflict("pre-qualified runtime step is not PENDING@0")
    immutable = (
        "project_key",
        "run_id",
        "step_id",
        "operation_id",
        "operation_kind",
        "operation_version",
        "execution_epoch",
        "effect_class",
        "resource_class",
        "concurrency_key",
        "capability_id",
        "claim_owner",
        "claim_authority_epoch",
        "claim_policy_digest",
        "max_attempts",
    )
    drift = tuple(key for key in immutable if existing.get(key) != ready[key])
    if drift:
        raise ExactBindingConflict(
            "pre-qualified runtime step drift: " + ", ".join(drift)
        )
    result = connection.execute(
        update(table)
        .where(
            table.c.project_key == ready["project_key"],
            table.c.run_id == ready["run_id"],
            table.c.step_id == ready["step_id"],
            table.c.state == "PENDING",
            table.c.revision == 0,
        )
        .values(
            state="READY",
            input_digest=ready["input_digest"],
            revision=0,
            updated_at=ready["updated_at"],
        )
    )
    if getattr(result, "rowcount", None) != 1:
        raise StaleRevisionError("pre-qualified step activation CAS failed")


def _plan_step(plan: ExecutionPlan, step_id: str) -> CompiledStep:
    matches = tuple(step for step in plan.ordered_steps if step.step_id == step_id)
    if len(matches) != 1 or matches[0].step_kind not in {"EFFECT", "ADMISSION"}:
        raise ExactBindingConflict("activation descriptor lacks one exact runtime step")
    return matches[0]


def traversal_plan_step(plan: ExecutionPlan, step_id: str) -> CompiledStep:
    matches = tuple(step for step in plan.ordered_steps if step.step_id == step_id)
    if (
        len(matches) != 1
        or matches[0].step_kind != "TRANSFORM"
        or matches[0].transform_ref is None
        or matches[0].transform_ref.name != TRAVERSAL_MATERIALIZER_TRANSFORM
    ):
        raise ExactBindingConflict("active child lineage lacks one traversal step")
    return matches[0]


def _control_for_step(root: CompiledControlNode, step_id: str) -> CompiledControlNode:
    matches: list[CompiledControlNode] = []

    def visit(node: CompiledControlNode) -> None:
        if step_id in node.step_ids:
            matches.append(node)
        for child in node.children:
            visit(child)

    visit(root)
    if not matches:
        raise ExactBindingConflict("compiled admission lacks exact control")
    return matches[-1]


def _atom_for_step(root: ProgramNode, step: CompiledStep) -> Atom:
    path = step.source_path[:-1] if step.step_kind == "ADMISSION" else step.source_path
    matches: list[Atom] = []

    def visit(node: ProgramNode, current: tuple[str, ...]) -> None:
        if current == path and isinstance(node, Atom):
            matches.append(node)
        if isinstance(node, Then):
            visit(node.first, current + ("first",))
            visit(node.second, current + ("second",))
        elif isinstance(node, MapOutput):
            visit(node.source, current + ("source",))
        elif isinstance(node, ZipOrdered):
            visit(node.left, current + ("left",))
            visit(node.right, current + ("right",))
        elif isinstance(node, TraverseOrdered):
            visit(node.element_program, current + ("element",))
        elif isinstance(node, Decide):
            for branch in node.branches:
                visit(branch.program, current + ("branch", branch.branch_id))

    visit(root, ("root",))
    if len(matches) != 1:
        raise ExactBindingConflict("activation Plan source path lacks one exact Atom")
    atom = matches[0]
    if (
        atom.operation.operation_id != step.operation_id
        or atom.operation.contract_ref != step.operation_contract_ref
    ):
        raise ExactBindingConflict("activation Program/Plan Atom binding drift")
    return atom


__all__ = [
    "ActiveChildMaterializer",
    "ActiveChildMaterializationReceipt",
    "ActiveChildSettlementBuilder",
    "ActiveChildSettlementReceipt",
    "ActiveChildTerminalObservation",
    "load_runtime_observations",
    "ActivationCatalogEntry",
    "ActivationReceipt",
    "ActivationTrigger",
    "OperationActivationCatalog",
    "FirstSpecimenActivationError",
    "LinkedRuntimeFrontier",
    "LinkedRuntimeWork",
    "PostgresRuntimeActivationBindingAdapter",
    "PostgresRuntimeActivationPort",
    "load_bound_runtime_output",
    "materialize_active_children",
    "read_linked_runtime_frontier",
    "settle_active_children",
    "settle_active_parents_for_child",
    "submit_compiled_program",
    "persist_qualification_step_shells",
    "activate_run",
]
