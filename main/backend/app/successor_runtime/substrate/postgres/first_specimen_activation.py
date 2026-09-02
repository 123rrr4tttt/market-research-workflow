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
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime

from sqlalchemy import MetaData, insert, select, update
from sqlalchemy.engine import Connection

from app.successor_runtime.language.algebra import ValueRef
from app.successor_runtime.language.checksum import canonical_bytes, sha256_hex
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
)
from app.successor_runtime.language.transforms import TransformRegistry
from app.successor_runtime.research.object_types import OBJECT_TYPE_BY_ID
from app.successor_runtime.research.object_types import ObjectType
from app.successor_runtime.runtime.activation import (
    ActivationResult,
    BoundStepValue,
    ReadyActivation,
    ValueMaterialization,
    activate_plan,
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
from app.successor_runtime.runtime.qualification import StepAuthorizationBinding
from app.successor_runtime.runtime.resources import QueueEligibility

from .models import PUBLIC_TABLES, ProjectTables, project_tables
from .plans import PlanRepository
from .programs import ProgramRepository
from .research_ledger import one_mapping
from .runtime_journal import (
    ExactBindingConflict,
    RecordNotFound,
    StaleRevisionError,
    _scope_key,
    _utcnow,
    validate_authorization_row,
    validate_qualification_row,
)
from .runtime_lifecycle import AssignmentEnvelope, _assignment_values
from .runtime_values import RuntimeValueBinding, RuntimeValueRepository
from .values import ValueRepository


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
class FirstSpecimenActivationCatalog:
    """Exact digest index plus the registries needed by the pure fold."""

    entries: tuple[ActivationCatalogEntry, ...]
    transform_registry: TransformRegistry
    merge_registry: TransformRegistry
    discriminator_registry: TransformRegistry

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


class PostgresFirstSpecimenActivationPort:
    """Terminal-hook adapter around caller-owned :func:`activate_run`."""

    def __init__(
        self,
        catalog: FirstSpecimenActivationCatalog,
        *,
        trace_prefix: str = "trace:first-specimen:activation",
    ) -> None:
        if not trace_prefix:
            raise ValueError("activation trace prefix is required")
        self.catalog = catalog
        self.trace_prefix = trace_prefix

    def activate_after_terminal(
        self,
        *,
        connection: Connection,
        scope: RuntimeScope,
        run_id: str,
        observed_at: datetime,
    ) -> ActivationReceipt:
        return activate_run(
            connection,
            scope,
            run_id,
            self.catalog,
            ActivationTrigger(
                due_at=observed_at,
                observed_at=observed_at,
                trace_id=f"{self.trace_prefix}:{run_id}",
            ),
        )


def persist_qualification_step_shells(
    connection: Connection,
    scope: RuntimeScope,
    *,
    run_id: str,
    plan: ExecutionPlan,
    catalog: FirstSpecimenActivationCatalog,
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


class PostgresFirstSpecimenActivationBindingAdapter:
    """Reconstruct a ReadyActivation without a second descriptor truth.

    The event carries only bounded digests and the work identity.  Full
    ValueRefs are recovered from the exact Program static suffix/payload and
    project-owned values named by the assignment's dynamic prefix.
    """

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
        if (
            step.operation_id is None
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
                        _project_value_ref(
                            connection,
                            scope,
                            tables,
                            locator,
                            dependency.output_type,
                        )
                    )
                except ExactBindingConflict as exc:
                    if "type drift" not in str(exc):
                        raise
            if len(candidates) != 1:
                raise ExactBindingConflict(
                    "activation dynamic project value does not bind one dependency group"
                )
            dynamic.append(next(iter(candidates)))
        descriptor = _finalize_descriptor(
            plan,
            ReadyActivation(
                step_id=step.step_id,
                step_kind=step.step_kind,  # type: ignore[arg-type]
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
    catalog: FirstSpecimenActivationCatalog,
    trigger: ActivationTrigger,
) -> ActivationReceipt:
    """Activate one exact run inside the caller-owned transaction."""

    project_key = _scope_key(scope)
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
    _require_program_plan_run(program, plan, run)
    qualified = _load_qualified_plan(connection, run)

    completed_outputs, activated_step_ids = _load_step_observations(
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
    )
    result = _bind_materializations_to_project(raw_result, plan)
    materialized = _materialize_values(connection, scope, tables, program, plan, result)

    steps_table = PUBLIC_TABLES["runtime_steps"]
    work_table = PUBLIC_TABLES["runtime_work_items"]
    now = trigger.observed_at or _utcnow()
    new_steps: list[str] = []
    new_work: list[str] = []
    awaiting_external_gate: list[str] = []
    events: list[dict[str, object]] = []
    for descriptor in result.activations:
        step = _plan_step(plan, descriptor.step_id)
        authorization = _authorization_for(
            connection, run, qualified, step, descriptor, catalog, now
        )
        entry = catalog.entry_for(str(step.operation_contract_ref.contract_digest))
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
        work_values = _assignment_values(envelope, due_at=trigger.due_at)

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


def _require_run_scope(run: Mapping[str, object], scope: RuntimeScope) -> None:
    expected = scope.project_scope
    if (
        run["project_key"] != expected.project_key
        or int(run["project_registry_revision"]) != expected.project_registry_revision
        or run["project_scope_digest"] != expected.scope_digest
        or run["resolved_schema"] != expected.resolved_schema
    ):
        raise ExactBindingConflict("activation run project scope drift")


def _require_program_plan_run(
    program: ProgramSpec, plan: ExecutionPlan, run: Mapping[str, object]
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


def _load_qualified_plan(connection: Connection, run: Mapping[str, object]):
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


def _load_step_observations(
    connection: Connection,
    scope: RuntimeScope,
    tables: ProjectTables,
    run: Mapping[str, object],
    plan: ExecutionPlan,
) -> tuple[tuple[BoundStepValue, ...], frozenset[str]]:
    steps_table = PUBLIC_TABLES["runtime_steps"]
    rows = connection.execute(
        select(steps_table)
        .where(
            steps_table.c.project_key == run["project_key"],
            steps_table.c.run_id == run["run_id"],
        )
        .with_for_update()
    ).mappings().all()
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
            _load_bound_output(
                connection,
                scope,
                tables,
                step,
                str(row["output_digest"]),
            )
        )
    return tuple(observed), frozenset(activated)


def _load_bound_output(
    connection: Connection,
    scope: RuntimeScope,
    tables: ProjectTables,
    step: CompiledStep,
    output_digest: str,
) -> BoundStepValue:
    require_digest(output_digest, "step output_digest")
    public = PUBLIC_TABLES["runtime_values"]
    rows = connection.execute(
        select(public).where(
            public.c.project_key == scope.project_scope.project_key,
            public.c.content_digest == output_digest,
            public.c.codec_id == step.output_type.codec_id,
            public.c.state == "AVAILABLE",
        )
    ).mappings().all()
    if len(rows) != 1:
        raise ExactBindingConflict(
            "terminal output lacks one exact public value binding: "
            f"step={step.step_id}, kind={step.operation_contract_ref.kind if step.operation_contract_ref else step.step_kind}, "
            f"digest={output_digest}, matches={len(rows)}"
        )
    row = rows[0]
    actual_type = step.output_type
    if row["object_type"] != step.output_type.type_id:
        if (
            step.output_type.type_id != "ClaimOrGap.v1"
            or row["object_type"] not in {"Claim.v1", "Gap.v1"}
        ):
            raise ExactBindingConflict("terminal output object type drift")
        actual_type = OBJECT_TYPE_BY_ID[str(row["object_type"])]
    project_ref = row["project_value_ref"]
    if not isinstance(project_ref, str) or not project_ref.startswith("project-value:"):
        raise ExactBindingConflict("terminal output is not project-value owned")
    value_id = project_ref.removeprefix("project-value:")
    project = one_mapping(
        connection.execute(
            select(tables.successor_values).where(
                tables.successor_values.c.project_key == scope.project_scope.project_key,
                tables.successor_values.c.value_id == value_id,
                tables.successor_values.c.content_digest == output_digest,
                tables.successor_values.c.codec_id == step.output_type.codec_id,
                tables.successor_values.c.state == "AVAILABLE",
            )
        )
    )
    if project is None:
        raise ExactBindingConflict("terminal output project value is absent")
    exact = (
        bytes(project["content_bytes"])
        if project["content_bytes"] is not None
        else canonical_bytes(project["content_json"])
    )
    if hashlib.sha256(exact).hexdigest() != output_digest:
        raise ExactBindingConflict("terminal output bytes fail digest readback")
    try:
        value = json.loads(exact)
    except (UnicodeDecodeError, json.JSONDecodeError):
        # Captured document snapshots intentionally preserve their exact source
        # bytes; JSON-valued capability outputs take the branch above.
        value = exact
    ref = _project_value_ref(connection, scope, tables, project_ref, actual_type)
    return BoundStepValue(step.step_id, ref, value)


def _project_value_ref(
    connection: Connection,
    scope: RuntimeScope,
    tables: ProjectTables,
    locator: str,
    object_type: ObjectType,
) -> ValueRef:
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
    exact = (
        bytes(row["content_bytes"])
        if row["content_bytes"] is not None
        else canonical_bytes(row["content_json"])
    )
    if (
        hashlib.sha256(exact).hexdigest() != row["content_digest"]
        or len(exact) != int(row["byte_size"])
    ):
        raise ExactBindingConflict("activation dynamic project value readback drift")
    return ValueRef(
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


def _dynamic_dependency_groups(
    step: CompiledStep,
    plan: ExecutionPlan,
) -> tuple[tuple[CompiledStep, ...], ...]:
    """Collapse mutually exclusive branch alternatives into one input slot."""

    by_step = {candidate.step_id: candidate for candidate in plan.ordered_steps}
    groups: list[list[CompiledStep]] = []
    branch_group_index: dict[str, int] = {}
    for dependency_id in step.dependencies:
        dependency = by_step.get(dependency_id)
        if dependency is None:
            raise ExactBindingConflict("activation dependency is absent from Plan")
        control_id = dependency.branch_control_id
        if control_id is None or dependency.branch_id is None:
            groups.append([dependency])
            continue
        index = branch_group_index.get(control_id)
        if index is None:
            branch_group_index[control_id] = len(groups)
            groups.append([dependency])
        else:
            groups[index].append(dependency)
    return tuple(tuple(group) for group in groups)


def _bind_materializations_to_project(
    result: ActivationResult, plan: ExecutionPlan
) -> ActivationResult:
    replacements: dict[ValueRef, ValueRef] = {}
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
        _finalize_descriptor(plan, _rebind_descriptor(item, replacements))
        for item in result.activations
    )
    return replace(
        result,
        values=values,
        materializations=tuple(materializations),
        activations=activations,
    )


def _rebind_descriptor(
    descriptor: ReadyActivation, replacements: Mapping[ValueRef, ValueRef]
) -> ReadyActivation:
    dynamic = tuple(replacements.get(ref, ref) for ref in descriptor.ordered_dependency_refs)
    return replace(descriptor, ordered_dependency_refs=dynamic)


def _finalize_descriptor(plan: ExecutionPlan, descriptor: ReadyActivation) -> ReadyActivation:
    closure = {
        "schema_version": "mrw.activation-input-closure.v1",
        "plan_digest": plan.plan_digest,
        "step_id": descriptor.step_id,
        "step_kind": descriptor.step_kind,
        "ordered_dependency_refs": tuple(ref.to_plain() for ref in descriptor.ordered_dependency_refs),
        "static_atom_input_refs": tuple(ref.to_plain() for ref in descriptor.static_atom_input_refs),
        "payload_ref": descriptor.payload_ref.to_plain(),
    }
    closure_digest = sha256_hex(closure)
    step = _plan_step(plan, descriptor.step_id)
    activation_digest = sha256_hex(
        {
            **closure,
            "operation_id": descriptor.operation_id,
            "operation_contract_digest": step.operation_contract_ref.contract_digest,
            "input_closure_digest": closure_digest,
        }
    )
    return replace(
        descriptor,
        input_closure_digest=closure_digest,
        activation_digest=activation_digest,
    )


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
        if sha256_hex(provenance) != ref.provenance_digest:
            raise ExactBindingConflict("pure materialization provenance drift")
        table = tables.successor_values
        existing = one_mapping(
            connection.execute(
                select(table.c.revision, table.c.incarnation).where(
                    table.c.project_key == scope.project_scope.project_key,
                    table.c.value_id == ref.value_id,
                )
            )
        )
        incarnation = f"activation:{plan.plan_id}:{item.step_id}"
        expected_revision = 0
        if existing is not None:
            if existing["incarnation"] != incarnation:
                raise ExactBindingConflict("pure materialization incarnation drift")
            expected_revision = int(existing["revision"])
        stored = ValueRepository(connection, tables).put_exact(
            scope,
            value_id=ref.value_id,
            object_type=ref.object_type.type_id,
            codec_id=ref.codec_id,
            content=item.exact_bytes,
            expected_digest=ref.content_digest,
            provenance_digest=ref.provenance_digest,
            expected_revision=expected_revision,
            expected_incarnation=incarnation,
            provenance=provenance,
        )
        project_ref = f"project-value:{ref.value_id}"
        storage_digest = canonical_digest(
            {
                "contract": "ProjectRuntimeValueBinding.v1",
                "project_key": scope.project_scope.project_key,
                "runtime_value_id": ref.value_id,
                "project_value_ref": project_ref,
                "content_digest": ref.content_digest,
                "codec_id": ref.codec_id,
            }
        )
        RuntimeValueRepository(connection, scope).put_exact(
            RuntimeValueBinding(
                value_id=ref.value_id,
                object_type=ref.object_type.type_id,
                codec_id=ref.codec_id,
                content_digest=ref.content_digest,
                byte_size=ref.byte_size,
                project_value_ref=project_ref,
                storage_digest=storage_digest,
                write_intent_digest=_value_write_intent(connection, tables, scope, ref.value_id),
            )
        )
        if stored.content_digest != ref.content_digest:
            raise ExactBindingConflict("pure materialization exact readback drift")
        ids.append(ref.value_id)
    return tuple(ids)


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
    run: Mapping[str, object],
    qualified,
    step: CompiledStep,
    descriptor: ReadyActivation,
    catalog: FirstSpecimenActivationCatalog,
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
    run: Mapping[str, object],
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
        execution_epoch=int(run["execution_epoch"]),
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
    run: Mapping[str, object],
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
    existing: Mapping[str, object], expected: Mapping[str, object], label: str
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
    existing: Mapping[str, object],
    ready: Mapping[str, object],
) -> None:
    if existing.get("state") != "PENDING" or int(existing.get("revision", -1)) != 0:
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
    "ActivationCatalogEntry",
    "ActivationReceipt",
    "ActivationTrigger",
    "FirstSpecimenActivationCatalog",
    "FirstSpecimenActivationError",
    "PostgresFirstSpecimenActivationBindingAdapter",
    "PostgresFirstSpecimenActivationPort",
    "persist_qualification_step_shells",
    "activate_run",
]
