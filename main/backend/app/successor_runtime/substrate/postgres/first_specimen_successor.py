"""Caller-owned PostgreSQL Gap-to-successor materialization.

All project objects, the ``opens`` relation, Program, Plan, idempotency record,
successor run/event and compile work item are written through one supplied
connection.  The core function never commits.  The RuntimeHandler wrapper owns
one explicit UoW because RuntimeNode execution is itself an effect boundary.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Connection, Engine

from app.successor_runtime.capabilities.first_specimen_successor import (
    GAP_SUCCESSOR_CAPABILITY_ID,
    GapSuccessorClosure,
    GapSuccessorRejected,
    build_gap_successor_closure,
)
from app.successor_runtime.language.algebra import (
    OperationContractCatalogSnapshot,
    ValueRef,
)
from app.successor_runtime.language.object_contracts import OperationContractResolver
from app.successor_runtime.research.claims import Gap
from app.successor_runtime.research.codec import canonical_bytes
from app.successor_runtime.research.identities import ResearchObjectRef
from app.successor_runtime.research.inquiries import Inquiry
from app.successor_runtime.research.object_types import (
    GAP_TYPE,
    INQUIRY_TYPE,
    OBJECT_TYPE_BY_ID,
    RESEARCH_INTENT_TYPE,
)
from app.successor_runtime.research.relations import ResearchRelation
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    MaterializerBinding,
    RuntimeAssignment,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import (
    DefiniteInterpreterFailure,
    MaterializerCommitOutcome,
    RuntimeExecutionContext,
    RuntimeHandler,
)
from app.successor_runtime.runtime.ports import RuntimeScope

from .models import PUBLIC_TABLES, ProjectTables
from .plans import PlanRepository
from .programs import ProgramRepository
from .research_ledger import (
    ExactContentConflict,
    ProjectRecordNotFound,
    ResearchLedgerRepository,
    object_ref_text,
    one_mapping,
)
from .runtime_journal import ExactBindingConflict, validate_runtime_assignment_row
from .runtime_lifecycle import (
    AssignmentEnvelope,
    RuntimeLifecycleRepository,
    SubmitRun,
)
from .unit_of_work import RuntimeUnitOfWork
from .values import ValueRepository


class GapSuccessorPersistenceRejected(RuntimeError):
    """Current PostgreSQL facts cannot authorize the successor closure."""


@dataclass(frozen=True, slots=True)
class SuccessorCompileEnvelope:
    assignment: RuntimeAssignment
    required_node_profile_selector: str
    resource_policy_digest: str
    fairness_key: str


@dataclass(frozen=True, slots=True)
class GapSuccessorReceipt:
    closure: GapSuccessorClosure
    compile_work_item_id: str
    repeated: bool

    @property
    def result_digest(self) -> str:
        return self.closure.request_digest


CompileAssignmentFactory = Callable[[GapSuccessorClosure], SuccessorCompileEnvelope]


def materialize_gap_successor(
    connection: Connection,
    scope: RuntimeScope,
    *,
    assignment: RuntimeAssignment,
    claim: ClaimBinding,
    observed_at: datetime,
    tables: ProjectTables,
    catalog: OperationContractCatalogSnapshot,
    operation_contracts: OperationContractResolver,
    compile_assignment_factory: CompileAssignmentFactory,
) -> GapSuccessorReceipt:
    """Persist one exact successor closure without owning the transaction."""

    if observed_at.tzinfo is None:
        raise GapSuccessorPersistenceRejected(
            "materialization time must be timezone-aware"
        )
    claim.validate_against(assignment)
    binding = assignment.handler_binding
    if (
        assignment.assignment_kind is not AssignmentKind.MATERIALIZE_SUCCESSOR
        or not isinstance(binding, MaterializerBinding)
        or assignment.project_key != scope.project_scope.project_key
        or assignment.step_id is not None
        or assignment.expected_step_revision is not None
        or assignment.payload_ref is None
        or assignment.payload_digest is None
        or assignment.plan_digest is None
    ):
        raise GapSuccessorPersistenceRejected(
            "exact materializer assignment is incomplete"
        )
    _require_current_materializer_claim(
        connection,
        scope,
        assignment,
        claim,
        observed_at,
    )

    predecessor_run, predecessor_step = _load_predecessor(
        connection,
        scope,
        assignment,
    )
    programs = ProgramRepository(connection, tables)
    plans = PlanRepository(connection, tables)
    predecessor_program = programs.get(
        scope,
        str(predecessor_run["program_id"]),
        expected_digest=str(predecessor_run["program_digest"]),
    )
    predecessor_plan = plans.get(scope, str(predecessor_run["plan_digest"]))
    source_value_ref, gap, gap_ref = _load_gap(
        connection,
        scope,
        assignment,
        tables,
    )
    intent_ref = _load_successor_intent(
        connection,
        scope,
        tables,
        gap,
    )
    closure = build_gap_successor_closure(
        predecessor_program=predecessor_program,
        predecessor_plan=predecessor_plan,
        predecessor_run_id=assignment.run_id,
        predecessor_step_id=str(predecessor_step["step_id"]),
        gap=gap,
        gap_ref=gap_ref,
        source_value_ref=source_value_ref,
        successor_intent_ref=intent_ref,
        predecessor_plan_digest=binding.predecessor_plan_digest,
        source_value_digest=binding.source_value_digest,
        materializer_binding_digest=binding.binding_digest,
        materializer_id=binding.materializer_id,
        materializer_version=binding.materializer_version,
        authority_digest=claim.authority_digest,
        catalog=catalog,
        operation_contracts=operation_contracts,
    )
    if predecessor_step["output_digest"] != binding.source_value_digest:
        raise GapSuccessorPersistenceRejected("predecessor output/source digest drift")

    compile_envelope = compile_assignment_factory(closure)
    _require_compile_envelope(compile_envelope, closure, scope)

    repeated = _idempotency_exists(connection, scope, closure)
    _put_generated_values(connection, scope, tables, closure)
    ledger = ResearchLedgerRepository(connection, tables)
    _put_object_absent_or_exact(ledger, connection, scope, tables, closure.inquiry_ref)
    _put_object_absent_or_exact(
        ledger,
        connection,
        scope,
        tables,
        closure.research_plan_ref,
    )
    _put_relation_absent_or_exact(
        ledger,
        connection,
        scope,
        tables,
        closure.opens_relation,
    )
    programs.put_exact(
        scope,
        closure.materialization.successor_program,
        closure.materialization.successor_program_digest,
    )
    plans.put_exact(
        scope,
        closure.successor_plan,
        closure.successor_plan.plan_digest,
        operation_catalog_id=catalog.catalog_id,
        catalog_version=catalog.catalog_version,
        catalog_digest=_required_digest(catalog.catalog_digest, "catalog_digest"),
    )
    _put_idempotency_absent_or_exact(connection, scope, closure)
    existing_run = one_mapping(
        connection.execute(
            select(PUBLIC_TABLES["runtime_runs"]).where(
                PUBLIC_TABLES["runtime_runs"].c.project_key
                == scope.project_scope.project_key,
                PUBLIC_TABLES["runtime_runs"].c.run_id == closure.successor_run_id,
            )
        )
    )
    if existing_run is None:
        RuntimeLifecycleRepository(connection, scope).submit(
            SubmitRun(
                run_id=closure.successor_run_id,
                incarnation=closure.successor_run_incarnation,
                program_id=closure.materialization.successor_program.program_id,
                program_digest=closure.materialization.successor_program_digest,
                program_storage_ref=(
                    "project-value:program:"
                    f"{closure.materialization.successor_program.program_id}"
                ),
                contract_version=closure.materialization.successor_program.contract_version,
                submission_authority_digest=claim.authority_digest,
                compile_work=AssignmentEnvelope(
                    assignment=compile_envelope.assignment,
                    required_node_profile_selector=(
                        compile_envelope.required_node_profile_selector
                    ),
                    authority_digest=claim.authority_digest,
                    resource_policy_digest=compile_envelope.resource_policy_digest,
                    fairness_key=compile_envelope.fairness_key,
                ),
                due_at=observed_at,
            )
        )
    else:
        repeated = True
        _require_exact_successor_run(
            existing_run,
            closure,
            claim,
            compile_envelope.assignment,
            connection,
        )
    return GapSuccessorReceipt(
        closure=closure,
        compile_work_item_id=compile_envelope.assignment.work_item_id,
        repeated=repeated,
    )


class PostgresFirstSpecimenSuccessorHandler(RuntimeHandler):
    """Exact RuntimeNode realization of one MaterializerBinding."""

    interpreter_profile_digest = None

    def __init__(
        self,
        *,
        engine: Engine,
        tables: ProjectTables,
        scope: RuntimeScope,
        binding: MaterializerBinding,
        catalog: OperationContractCatalogSnapshot,
        operation_contracts: OperationContractResolver,
        compile_assignment_factory: CompileAssignmentFactory,
    ) -> None:
        self._engine = engine
        self._tables = tables
        self._scope = scope
        self._binding = binding
        self._catalog = catalog
        self._operation_contracts = operation_contracts
        self._compile_assignment_factory = compile_assignment_factory
        self.handler_binding_digest = binding.binding_digest

    def execute(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> MaterializerCommitOutcome:
        if (
            assignment.handler_binding_digest != self.handler_binding_digest
            or assignment.handler_binding != self._binding
        ):
            raise DefiniteInterpreterFailure("MATERIALIZER_BINDING_DRIFT")
        try:
            with RuntimeUnitOfWork(engine=self._engine) as uow:
                receipt = materialize_gap_successor(
                    uow.connection,
                    self._scope,
                    assignment=assignment,
                    claim=claim,
                    observed_at=context.observed_at,
                    tables=self._tables,
                    catalog=self._catalog,
                    operation_contracts=self._operation_contracts,
                    compile_assignment_factory=self._compile_assignment_factory,
                )
                terminal_observation_ref = _complete_materializer_claim(
                    uow.connection,
                    self._scope,
                    assignment=assignment,
                    claim=claim,
                    receipt=receipt,
                    observed_at=context.observed_at,
                )
                uow.commit()
        except (
            GapSuccessorPersistenceRejected,
            GapSuccessorRejected,
            ExactContentConflict,
            ExactBindingConflict,
        ) as exc:
            raise DefiniteInterpreterFailure(
                "GAP_SUCCESSOR_EXACT_BINDING_REJECTED"
            ) from exc
        return MaterializerCommitOutcome(
            assignment_digest=assignment.assignment_digest,
            attempt_id=claim.attempt_id,
            result_digest=receipt.result_digest,
            receipt_ref=terminal_observation_ref,
        )


def _load_predecessor(
    connection: Connection,
    scope: RuntimeScope,
    assignment: RuntimeAssignment,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    runs = PUBLIC_TABLES["runtime_runs"]
    steps = PUBLIC_TABLES["runtime_steps"]
    run = one_mapping(
        connection.execute(
            select(runs)
            .where(
                runs.c.project_key == scope.project_scope.project_key,
                runs.c.run_id == assignment.run_id,
            )
            .with_for_update()
        )
    )
    step_rows = tuple(
        connection.execute(
            select(steps)
            .where(
                steps.c.project_key == scope.project_scope.project_key,
                steps.c.run_id == assignment.run_id,
                steps.c.execution_epoch == assignment.execution_epoch,
                steps.c.state == "SUCCEEDED",
                steps.c.output_digest == assignment.payload_digest,
            )
            .with_for_update()
        )
        .mappings()
        .all()
    )
    if run is None or len(step_rows) != 1:
        raise GapSuccessorPersistenceRejected(
            "predecessor run/source-step closure is absent or ambiguous"
        )
    step = step_rows[0]
    if (
        run["state"] != "COMPLETED"
        or run["plan_digest"] != assignment.plan_digest
        or run["incarnation"] != assignment.incarnation
        or int(run["execution_epoch"]) != assignment.execution_epoch
        or int(step["execution_epoch"]) != assignment.execution_epoch
        or step["output_digest"] != assignment.payload_digest
    ):
        raise GapSuccessorPersistenceRejected("predecessor terminal closure drift")
    return run, step


def _require_current_materializer_claim(
    connection: Connection,
    scope: RuntimeScope,
    assignment: RuntimeAssignment,
    claim: ClaimBinding,
    observed_at: datetime,
) -> None:
    work_items = PUBLIC_TABLES["runtime_work_items"]
    row = one_mapping(
        connection.execute(
            select(work_items)
            .where(
                work_items.c.project_key == scope.project_scope.project_key,
                work_items.c.work_item_id == assignment.work_item_id,
            )
            .with_for_update(read=True)
        )
    )
    if row is None:
        raise GapSuccessorPersistenceRejected("materializer work item is absent")
    persisted = validate_runtime_assignment_row(row)
    raw_claim = row["claim_binding_json"]
    try:
        persisted_claim = ClaimBinding.model_validate(raw_claim)
    except Exception as exc:
        raise GapSuccessorPersistenceRejected(
            "materializer work item claim binding is malformed"
        ) from exc
    authority = one_mapping(
        connection.execute(
            select(PUBLIC_TABLES["runtime_capability_authority"])
            .where(
                PUBLIC_TABLES["runtime_capability_authority"].c.project_key
                == scope.project_scope.project_key,
                PUBLIC_TABLES["runtime_capability_authority"].c.capability_id
                == assignment.capability_id,
            )
            .with_for_update()
        )
    )
    if (
        persisted != assignment
        or persisted_claim != claim
        or row["state"] != "CLAIMED"
        or row["claim_binding_digest"] != claim.binding_digest
        or row["lease_token"] != claim.lease_token
        or row["lease_owner"] != claim.node_id
        or row["lease_expires_at"] != claim.lease_expires_at
        or row["lease_expires_at"] <= observed_at
        or row["authority_digest"] != claim.authority_digest
        or int(row["claim_authority_epoch"]) != claim.claim_authority_epoch
        or authority is None
        or int(authority["authority_epoch"]) != claim.claim_authority_epoch
        or not authority["successor_claim_enabled"]
        or authority["legacy_claim_enabled"]
        or authority["effective_at"] > observed_at
    ):
        raise GapSuccessorPersistenceRejected(
            "materializer claim/lease/authority is stale"
        )


def _complete_materializer_claim(
    connection: Connection,
    scope: RuntimeScope,
    *,
    assignment: RuntimeAssignment,
    claim: ClaimBinding,
    receipt: GapSuccessorReceipt,
    observed_at: datetime,
) -> str:
    """Atomically terminalize a run-scoped materializer observation.

    The predecessor run remains ``COMPLETED`` and its source step remains
    ``SUCCEEDED``.  Only the journal sequence/revision, the run-scoped work
    item and the materializer idempotency record advance.
    """

    _require_current_materializer_claim(
        connection,
        scope,
        assignment,
        claim,
        observed_at,
    )
    work_items = PUBLIC_TABLES["runtime_work_items"]
    runs = PUBLIC_TABLES["runtime_runs"]
    steps = PUBLIC_TABLES["runtime_steps"]
    events = PUBLIC_TABLES["runtime_events"]
    idempotency = PUBLIC_TABLES["runtime_idempotency"]
    work = one_mapping(
        connection.execute(
            select(work_items)
            .where(
                work_items.c.project_key == scope.project_scope.project_key,
                work_items.c.work_item_id == assignment.work_item_id,
            )
            .with_for_update()
        )
    )
    run = one_mapping(
        connection.execute(
            select(runs)
            .where(
                runs.c.project_key == scope.project_scope.project_key,
                runs.c.run_id == assignment.run_id,
            )
            .with_for_update()
        )
    )
    source_step_id = receipt.closure.materialization.predecessor_step_id
    source_step = one_mapping(
        connection.execute(
            select(steps)
            .where(
                steps.c.project_key == scope.project_scope.project_key,
                steps.c.run_id == assignment.run_id,
                steps.c.step_id == source_step_id,
            )
            .with_for_update(read=True)
        )
    )
    if (
        work is None
        or run is None
        or source_step is None
        or run["state"] != "COMPLETED"
        or run["incarnation"] != assignment.incarnation
        or run["program_digest"] != assignment.program_digest
        or run["plan_digest"] != assignment.plan_digest
        or int(run["execution_epoch"]) != assignment.execution_epoch
        or source_step["state"] != "SUCCEEDED"
        or source_step["output_digest"] != assignment.payload_digest
        or int(source_step["execution_epoch"]) != assignment.execution_epoch
    ):
        raise GapSuccessorPersistenceRejected(
            "materializer terminal predecessor closure drift"
        )

    sequence = int(run["next_event_seq"])
    run_revision = int(run["revision"])
    terminal_observation_ref = f"materialization:sha256:{receipt.result_digest}"
    advanced = connection.execute(
        update(runs)
        .where(
            runs.c.project_key == scope.project_scope.project_key,
            runs.c.run_id == assignment.run_id,
            runs.c.state == "COMPLETED",
            runs.c.revision == run_revision,
            runs.c.next_event_seq == sequence,
        )
        .values(
            next_event_seq=sequence + 1,
            revision=run_revision + 1,
            updated_at=observed_at,
        )
    )
    if getattr(advanced, "rowcount", None) != 1:
        raise ExactBindingConflict("materializer event sequence CAS failed")
    connection.execute(
        insert(events).values(
            project_key=scope.project_scope.project_key,
            run_id=assignment.run_id,
            seq=sequence,
            event_type="SuccessorMaterialized",
            schema_version="mrw.runtime.event.successor_materialized.v1",
            step_id=None,
            attempt_id=None,
            event_metadata_json={
                "work_item_id": assignment.work_item_id,
                "source_step_id": source_step_id,
                "claim_attempt_id": claim.attempt_id,
                "assignment_digest": assignment.assignment_digest,
                "handler_binding_digest": assignment.handler_binding_digest,
                "source_value_digest": assignment.payload_digest,
                "successor_run_id": receipt.closure.successor_run_id,
                "successor_program_digest": (
                    receipt.closure.materialization.successor_program_digest
                ),
                "successor_plan_digest": receipt.closure.successor_plan.plan_digest,
                "result_digest": receipt.result_digest,
                "terminal_observation_ref": terminal_observation_ref,
                "predecessor_run_state": "COMPLETED",
                "predecessor_step_state": "SUCCEEDED",
            },
            payload_ref=terminal_observation_ref,
            payload_digest=receipt.result_digest,
            authority_digest=claim.authority_digest,
            created_at=observed_at,
            updated_at=observed_at,
        )
    )
    released = connection.execute(
        update(work_items)
        .where(
            work_items.c.project_key == scope.project_scope.project_key,
            work_items.c.work_item_id == assignment.work_item_id,
            work_items.c.state == "CLAIMED",
            work_items.c.revision == int(work["revision"]),
            work_items.c.lease_token == claim.lease_token,
            work_items.c.claim_binding_digest == claim.binding_digest,
        )
        .values(
            state="COMPLETED",
            wait_reason=None,
            lease_token=None,
            lease_owner=None,
            lease_expires_at=None,
            revision=int(work["revision"]) + 1,
            updated_at=observed_at,
        )
    )
    if getattr(released, "rowcount", None) != 1:
        raise ExactBindingConflict("materializer work terminal CAS failed")
    terminalized = connection.execute(
        update(idempotency)
        .where(
            idempotency.c.project_key == scope.project_scope.project_key,
            idempotency.c.capability_id == GAP_SUCCESSOR_CAPABILITY_ID,
            idempotency.c.logical_request_id
            == receipt.closure.materialization.idempotency_key,
            idempotency.c.request_digest == receipt.closure.request_digest,
            idempotency.c.run_id == receipt.closure.successor_run_id,
            idempotency.c.state == "STARTED",
        )
        .values(
            state="TERMINAL",
            terminal_observation_ref=terminal_observation_ref,
            revision=idempotency.c.revision + 1,
            updated_at=observed_at,
        )
    )
    if getattr(terminalized, "rowcount", None) != 1:
        raise ExactBindingConflict("materializer idempotency terminal CAS failed")
    return terminal_observation_ref


def _load_gap(
    connection: Connection,
    scope: RuntimeScope,
    assignment: RuntimeAssignment,
    tables: ProjectTables,
) -> tuple[ValueRef, Gap, ResearchObjectRef]:
    prefix = "project-value:"
    if assignment.payload_ref is None or not assignment.payload_ref.startswith(prefix):
        raise GapSuccessorPersistenceRejected("Gap payload_ref is not project-scoped")
    value_id = assignment.payload_ref[len(prefix) :]
    value_row = one_mapping(
        connection.execute(
            select(tables.successor_values).where(
                tables.successor_values.c.project_key
                == scope.project_scope.project_key,
                tables.successor_values.c.value_id == value_id,
                tables.successor_values.c.content_digest == assignment.payload_digest,
                tables.successor_values.c.object_type == GAP_TYPE.type_id,
                tables.successor_values.c.state == "AVAILABLE",
            )
        )
    )
    if value_row is None:
        raise GapSuccessorPersistenceRejected("exact admitted Gap value is absent")
    raw = _value_json(value_row)
    try:
        gap = Gap(
            gap_id=raw["gap_id"],
            inquiry_ref=raw["inquiry_ref"],
            requirement=raw["requirement"],
            reason=raw["reason"],
            closure_condition=raw["closure_condition"],
            reopen_policy=dict(raw["reopen_policy"]),
            missing_evidence_or_decision=raw["missing_evidence_or_decision"],
            content_digest=str(value_row["content_digest"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise GapSuccessorPersistenceRejected(
            "stored Gap payload is malformed"
        ) from exc
    object_row = one_mapping(
        connection.execute(
            select(tables.research_objects).where(
                tables.research_objects.c.project_key
                == scope.project_scope.project_key,
                tables.research_objects.c.object_id == gap.gap_id,
                tables.research_objects.c.object_type == GAP_TYPE.type_id,
                tables.research_objects.c.content_ref == assignment.payload_ref,
                tables.research_objects.c.content_digest == assignment.payload_digest,
                tables.research_objects.c.lifecycle_state == "ADMITTED",
            )
        )
    )
    if object_row is None:
        raise GapSuccessorPersistenceRejected("Gap is not canonically admitted")
    ref = _ref_from_row(object_row)
    value_ref = ValueRef(
        value_id=str(value_row["value_id"]),
        project_key=scope.project_scope.project_key,
        object_type=GAP_TYPE,
        codec_id=str(value_row["codec_id"]),
        content_digest=str(value_row["content_digest"]),
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=assignment.payload_ref,
        byte_size=int(value_row["byte_size"]),
        provenance_digest=str(value_row["provenance_digest"]),
    )
    return value_ref, gap, ref


def _load_successor_intent(
    connection: Connection,
    scope: RuntimeScope,
    tables: ProjectTables,
    gap: Gap,
) -> ResearchObjectRef:
    inquiry_row = _one_admitted_object(
        connection,
        scope,
        tables,
        object_id=gap.inquiry_ref,
        object_type=INQUIRY_TYPE.type_id,
    )
    inquiry_value = _value_for_object(connection, scope, tables, inquiry_row)
    raw = _value_json(inquiry_value)
    try:
        inquiry = Inquiry(
            inquiry_id=raw["inquiry_id"],
            intent_ref=raw["intent_ref"],
            question_or_hypothesis=raw["question_or_hypothesis"],
            acceptance_conditions=tuple(raw["acceptance_conditions"]),
            stop_conditions=tuple(raw["stop_conditions"]),
            uncertainty_ceiling=raw["uncertainty_ceiling"],
            content_digest=str(raw["content_digest"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise GapSuccessorPersistenceRejected(
            "predecessor Inquiry is malformed"
        ) from exc
    if inquiry.inquiry_id != gap.inquiry_ref:
        raise GapSuccessorPersistenceRejected("Gap/Inquiry identity drift")
    return _ref_from_row(
        _one_admitted_object(
            connection,
            scope,
            tables,
            object_id=inquiry.intent_ref,
            object_type=RESEARCH_INTENT_TYPE.type_id,
        )
    )


def _one_admitted_object(
    connection: Connection,
    scope: RuntimeScope,
    tables: ProjectTables,
    *,
    object_id: str,
    object_type: str,
) -> Mapping[str, Any]:
    row = one_mapping(
        connection.execute(
            select(tables.research_objects).where(
                tables.research_objects.c.project_key
                == scope.project_scope.project_key,
                tables.research_objects.c.object_id == object_id,
                tables.research_objects.c.object_type == object_type,
                tables.research_objects.c.lifecycle_state == "ADMITTED",
            )
        )
    )
    if row is None:
        raise GapSuccessorPersistenceRejected(f"admitted object is absent: {object_id}")
    return row


def _value_for_object(
    connection: Connection,
    scope: RuntimeScope,
    tables: ProjectTables,
    object_row: Mapping[str, Any],
) -> Mapping[str, Any]:
    prefix = "project-value:"
    content_ref = str(object_row["content_ref"])
    if not content_ref.startswith(prefix):
        raise GapSuccessorPersistenceRejected(
            "object content_ref is not project-scoped"
        )
    row = one_mapping(
        connection.execute(
            select(tables.successor_values).where(
                tables.successor_values.c.project_key
                == scope.project_scope.project_key,
                tables.successor_values.c.value_id == content_ref[len(prefix) :],
                tables.successor_values.c.content_digest
                == object_row["content_digest"],
            )
        )
    )
    if row is None:
        raise GapSuccessorPersistenceRejected("exact object value is absent")
    return row


def _put_generated_values(
    connection: Connection,
    scope: RuntimeScope,
    tables: ProjectTables,
    closure: GapSuccessorClosure,
) -> None:
    values = ValueRepository(connection, tables)
    for payload, ref in (
        (closure.inquiry, closure.inquiry_value_ref),
        (closure.research_plan, closure.research_plan_value_ref),
    ):
        values.put_exact(
            scope,
            value_id=ref.value_id,
            object_type=ref.object_type.type_id,
            codec_id=ref.codec_id,
            content=canonical_bytes(payload),
            expected_digest=ref.content_digest,
            provenance_digest=ref.provenance_digest,
            expected_revision=0,
            expected_incarnation=(
                closure.inquiry_ref.incarnation
                if ref is closure.inquiry_value_ref
                else closure.research_plan_ref.incarnation
            ),
            source_ref=closure.materialization.source_value_ref.storage_ref,
            provenance={
                "materialization_id": closure.materialization.materialization_id,
                "request_digest": closure.request_digest,
            },
        )


def _put_object_absent_or_exact(
    ledger: ResearchLedgerRepository,
    connection: Connection,
    scope: RuntimeScope,
    tables: ProjectTables,
    ref: ResearchObjectRef,
) -> None:
    row = one_mapping(
        connection.execute(
            select(tables.research_objects).where(
                tables.research_objects.c.project_key
                == scope.project_scope.project_key,
                tables.research_objects.c.object_id == ref.object_id,
                tables.research_objects.c.revision == ref.revision,
                tables.research_objects.c.incarnation == ref.incarnation,
            )
        )
    )
    if row is None:
        ledger.put_object(
            scope,
            ref,
            expected_revision=0,
            expected_incarnation=ref.incarnation,
        )
        return
    if object_ref_text(_ref_from_row(row)) != object_ref_text(ref):
        raise ExactContentConflict("successor research object identity drift")


def _put_relation_absent_or_exact(
    ledger: ResearchLedgerRepository,
    connection: Connection,
    scope: RuntimeScope,
    tables: ProjectTables,
    relation: ResearchRelation,
) -> None:
    row = one_mapping(
        connection.execute(
            select(tables.research_relations).where(
                tables.research_relations.c.project_key
                == scope.project_scope.project_key,
                tables.research_relations.c.relation_id == relation.relation_id,
                tables.research_relations.c.revision == relation.revision,
                tables.research_relations.c.incarnation == relation.incarnation,
            )
        )
    )
    if row is None:
        ledger.put_relation(
            scope,
            relation,
            expected_revision=0,
            expected_incarnation=relation.incarnation,
        )
        return
    expected = {
        "relation_type": relation.relation_type,
        "source_object_ref": object_ref_text(relation.source_ref),
        "target_object_ref": object_ref_text(relation.target_ref),
        "direction": relation.direction,
        "scope_ref": relation.scope_ref,
        "uncertainty_profile_ref": relation.uncertainty_profile_ref,
        "provenance_closure_digest": relation.provenance_closure_digest,
        "state": relation.state,
    }
    if any(row[name] != value for name, value in expected.items()):
        raise ExactContentConflict("opens relation identity drift")


def _put_idempotency_absent_or_exact(
    connection: Connection,
    scope: RuntimeScope,
    closure: GapSuccessorClosure,
) -> None:
    table = PUBLIC_TABLES["runtime_idempotency"]
    identity = f"idempotency:gap-successor:{closure.request_digest}"
    values = {
        "idempotency_id": identity,
        "project_key": scope.project_scope.project_key,
        "capability_id": GAP_SUCCESSOR_CAPABILITY_ID,
        "logical_request_id": closure.materialization.idempotency_key,
        "operation_kind": "materialize.gap_successor.v1",
        "request_digest": closure.request_digest,
        "run_id": closure.successor_run_id,
        "terminal_observation_ref": None,
        "state": "STARTED",
        "revision": 0,
    }
    row = one_mapping(
        connection.execute(
            select(table).where(
                table.c.project_key == scope.project_scope.project_key,
                table.c.capability_id == GAP_SUCCESSOR_CAPABILITY_ID,
                table.c.logical_request_id == closure.materialization.idempotency_key,
            )
        )
    )
    if row is None:
        connection.execute(insert(table).values(**values))
        return
    immutable_fields = (
        "idempotency_id",
        "project_key",
        "capability_id",
        "logical_request_id",
        "operation_kind",
        "request_digest",
        "run_id",
    )
    terminal_ref = f"materialization:sha256:{closure.request_digest}"
    state_is_exact = (
        row["state"] == "STARTED"
        and row["terminal_observation_ref"] is None
        and int(row["revision"]) == 0
    ) or (
        row["state"] == "TERMINAL"
        and row["terminal_observation_ref"] == terminal_ref
        and int(row["revision"]) == 1
    )
    if (
        any(row[name] != values[name] for name in immutable_fields)
        or not state_is_exact
    ):
        raise ExactBindingConflict("Gap successor idempotency binding drift")


def _idempotency_exists(
    connection: Connection,
    scope: RuntimeScope,
    closure: GapSuccessorClosure,
) -> bool:
    table = PUBLIC_TABLES["runtime_idempotency"]
    return (
        one_mapping(
            connection.execute(
                select(table.c.idempotency_id).where(
                    table.c.project_key == scope.project_scope.project_key,
                    table.c.capability_id == GAP_SUCCESSOR_CAPABILITY_ID,
                    table.c.logical_request_id
                    == closure.materialization.idempotency_key,
                )
            )
        )
        is not None
    )


def _require_compile_envelope(
    envelope: SuccessorCompileEnvelope,
    closure: GapSuccessorClosure,
    scope: RuntimeScope,
) -> None:
    assignment = envelope.assignment
    if (
        assignment.assignment_kind is not AssignmentKind.COMPILE
        or assignment.project_key != scope.project_scope.project_key
        or assignment.run_id != closure.successor_run_id
        or assignment.incarnation != closure.successor_run_incarnation
        or assignment.program_digest != closure.materialization.successor_program_digest
        or assignment.plan_digest is not None
        or not envelope.required_node_profile_selector
        or not envelope.fairness_key
    ):
        raise GapSuccessorPersistenceRejected("successor compile assignment drift")
    _required_digest(envelope.resource_policy_digest, "resource_policy_digest")


def _require_exact_successor_run(
    row: Mapping[str, Any],
    closure: GapSuccessorClosure,
    claim: ClaimBinding,
    compile_assignment: RuntimeAssignment,
    connection: Connection,
) -> None:
    exact = {
        "program_id": closure.materialization.successor_program.program_id,
        "program_digest": closure.materialization.successor_program_digest,
        "incarnation": closure.successor_run_incarnation,
        "submission_authority_digest": claim.authority_digest,
    }
    if row["state"] not in {
        "SUBMITTED",
        "COMPILING",
        "AWAITING_APPROVAL",
        "READY",
        "RUNNING",
        "WAITING",
        "RECONCILING",
        "COMPLETED",
    } or any(row[name] != value for name, value in exact.items()):
        raise ExactBindingConflict("successor run identity was rebound")
    work = one_mapping(
        connection.execute(
            select(PUBLIC_TABLES["runtime_work_items"]).where(
                PUBLIC_TABLES["runtime_work_items"].c.project_key == row["project_key"],
                PUBLIC_TABLES["runtime_work_items"].c.work_item_id
                == compile_assignment.work_item_id,
            )
        )
    )
    if (
        work is None
        or work["assignment_digest"] != compile_assignment.assignment_digest
    ):
        raise ExactBindingConflict("successor compile work exact readback failed")


def _value_json(row: Mapping[str, Any]) -> Mapping[str, Any]:
    if row["content_json"] is not None:
        value = row["content_json"]
    elif row["content_bytes"] is not None:
        value = json.loads(bytes(row["content_bytes"]).decode("utf-8"))
    else:
        raise GapSuccessorPersistenceRejected("successor value has no content")
    if not isinstance(value, Mapping):
        raise GapSuccessorPersistenceRejected("successor value is not an object")
    return value


def _ref_from_row(row: Mapping[str, Any]) -> ResearchObjectRef:
    object_type = OBJECT_TYPE_BY_ID.get(str(row["object_type"]))
    if object_type is None:
        raise ProjectRecordNotFound("unknown research object type")
    return ResearchObjectRef(
        object_id=str(row["object_id"]),
        object_type=object_type,
        project_key=str(row["project_key"]),
        revision=int(row["revision"]),
        incarnation=str(row["incarnation"]),
        owner_binding_ref=str(row["owner_binding_ref"]),
        content_ref=str(row["content_ref"]),
        content_digest=str(row["content_digest"]),
        provenance_closure_digest=str(row["provenance_closure_digest"]),
        valid_from=row["valid_from"],
        valid_to=row["valid_to"],
        lifecycle_state=str(row["lifecycle_state"]),
    )


def _required_digest(value: str | None, name: str) -> str:
    if (
        value is None
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise GapSuccessorPersistenceRejected(f"{name} must be canonical sha256 hex")
    return value


__all__ = [
    "CompileAssignmentFactory",
    "GapSuccessorPersistenceRejected",
    "GapSuccessorReceipt",
    "PostgresFirstSpecimenSuccessorHandler",
    "SuccessorCompileEnvelope",
    "materialize_gap_successor",
]
