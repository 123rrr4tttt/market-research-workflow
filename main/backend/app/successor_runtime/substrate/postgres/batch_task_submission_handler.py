"""Restartable store-rehydrated RuntimeHandler for the C4.3 submission atom.

The handler captures no Program/Plan/payload fixture.  Every ``execute`` opens
a fresh read-only unit of work, re-resolves the current project scope, reloads
the exact canonical Program, ExecutionPlan and payload bytes from the project
stores, revalidates operation/deployment catalog and payload codec identities,
and only then invokes the pure successor submission interpreter.  The typed
receipt (including family-specific acceptance state) is persisted as an exact
project value in the same transaction, so acceptance status is durable store
state rather than transient input.  There is no legacy service, provider,
network, credential or fixture-closure fallback.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
from typing import Any, Generic, Literal, TypeVar

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from app.successor_runtime.capabilities import batch_task as batch_task
from app.successor_runtime.capabilities.batch_task_interpreters import (
    BatchTaskSubmissionSuccessorInterpreter,
    InterpreterFailure,
)
from app.successor_runtime.capabilities.checksum import (
    CanonicalJsonValue,
    canonical_json,
    content_digest,
    sha256_hex,
)
from app.successor_runtime.capabilities.codecs import PayloadCodec
from app.successor_runtime.language.object_contracts import OperationContract
from app.successor_runtime.language.algebra import ValueRef
from app.successor_runtime.language.catalog import OperationContractCatalogSnapshot
from app.successor_runtime.language.plan import ExecutionPlan
from app.successor_runtime.language.program import ProgramSpec
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompiledStepRole,
    RuntimeAssignment,
    InterpreterBinding,
    require_digest,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import (
    DefiniteInterpreterFailure,
    InterpreterOutcome,
    RuntimeExecutionContext,
    RuntimeHandler,
)
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
from app.successor_runtime.substrate.postgres.idempotency import (
    IdempotencyBinding as SharedIdempotencyBinding,
)
from app.successor_runtime.substrate.postgres.idempotency import (
    IdempotencyRepository,
)
from app.successor_runtime.substrate.postgres.models import project_tables
from app.successor_runtime.substrate.postgres.nodes import DeploymentCatalogRepository
from app.successor_runtime.substrate.postgres.plans import PlanRepository
from app.successor_runtime.substrate.postgres.programs import ProgramRepository
from app.successor_runtime.substrate.postgres.runtime_journal import (
    ExactBindingConflict, RecordNotFound,
    one_mapping,
    runtime_table,
)
from app.successor_runtime.substrate.postgres.session import (
    ProjectScopeStale,
    ServerProjectScopeResolver,
)
from app.successor_runtime.substrate.postgres.unit_of_work import RuntimeUnitOfWork
from app.successor_runtime.substrate.postgres.values import ValueRepository
from app.successor_runtime.substrate.postgres.first_specimen_activation import (
    PostgresFirstSpecimenActivationBindingAdapter,
)
from app.successor_runtime.substrate.postgres.node_adapter import UowFactory


Input = TypeVar("Input")
Output = TypeVar("Output")


class PersistentOperationHandler(RuntimeHandler, Generic[Input, Output]):
    """Execute one installed typed kernel from exact project-owned values."""

    def __init__(
        self, *, uow_factory: UowFactory, binding: InterpreterBinding,
        contract: OperationContract, input_codec: PayloadCodec[Input],
        output_codec: PayloadCodec[Output], invoke: Callable[[Input], Output],
        validate_input: Callable[[Input, ProjectScopeRef, str], None] | None = None,
        validate_bound_inputs: Callable[
            [Input, tuple[tuple[ValueRef, bytes], ...]], None
        ] | None = None,
        bound_payload_source: Literal["static", "semantic"] = "static",
        validate_output: Callable[[Input, Output], None] | None = None,
        invoke_with_assignment: Callable[[Input, RuntimeAssignment], Output] | None = None,
    ) -> None:
        if (binding.operation_contract_digest != contract.ref.contract_digest
                or input_codec.contract_ref != contract.ref or output_codec.contract_ref != contract.ref
                or input_codec.codec_id != contract.input_type.codec_id
                or output_codec.codec_id != contract.output_type.codec_id):
            raise ValueError("installed operation contract/codec drift")
        self.contract = contract
        self.binding = binding
        self.handler_binding_digest = binding.binding_digest
        self.interpreter_profile_digest = binding.interpreter_profile_digest
        self.operation_contract_digest = binding.operation_contract_digest
        self._uow_factory = uow_factory
        self._invoke = invoke
        self._invoke_with_assignment = invoke_with_assignment
        self._input_codec = input_codec
        self._output_codec = output_codec
        self._validate_input = validate_input
        self._validate_bound_inputs = validate_bound_inputs
        self._bound_payload_source = bound_payload_source
        self._validate_output = validate_output
        self._values = PostgresFirstSpecimenActivationBindingAdapter()

    def execute(
        self, assignment: RuntimeAssignment, claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> InterpreterOutcome:
        claim.validate_against(assignment)
        if (assignment.assignment_kind is not AssignmentKind.INTERPRET
                or assignment.handler_binding != self.binding
                or assignment.operation_contract_ref != self.contract.ref):
            raise DefiniteInterpreterFailure("OPERATION_BINDING_DRIFT")
        with self._uow_factory() as uow:
            project_scope = ServerProjectScopeResolver(connection=uow.connection).resolve(assignment.project_key)
            if project_scope.scope_digest != self.binding.project_scope_digest:
                raise DefiniteInterpreterFailure("OPERATION_SCOPE_DRIFT")
            scope = RuntimeScope(project_scope=project_scope, actor_id=context.node.node_id)
            tables = project_tables(sa.MetaData(), project_scope.resolved_schema)
            descriptor = self._values.load_exact(uow.connection, assignment, scope, tables)
            try:
                input_ref = self._values.semantic_input_ref(uow.connection, assignment, scope, tables, descriptor)
                exact = self._values.read_value_bytes(uow.connection, scope, tables, input_ref)
                static_inputs = tuple(
                    (
                        ref,
                        exact
                        if ref == input_ref
                        else self._values.read_value_bytes(
                            uow.connection, scope, tables, ref
                        ),
                    )
                    for ref in descriptor.static_atom_input_refs
                )
                # Static occurrence/budget facts are always read exactly. Only
                # declared template consumers validate the semantic payload slot.
                bound_inputs = tuple(
                    (input_ref, exact)
                    if self._bound_payload_source == "semantic" and ref == descriptor.payload_ref
                    else (ref, content)
                    for ref, content in static_inputs
                )
            except (ExactBindingConflict, RecordNotFound) as exc:
                raise DefiniteInterpreterFailure("OPERATION_INPUT_BINDING_DRIFT") from exc
            try:
                decoded: CanonicalJsonValue = json.loads(exact)
                if not isinstance(decoded, dict) or canonical_json(decoded).encode() != exact:
                    raise ValueError("noncanonical operation payload")
                payload = self._input_codec.decode_payload(decoded)
                if self._validate_input is not None:
                    self._validate_input(payload, project_scope, assignment.capability_id)
                if self._validate_bound_inputs is not None:
                    self._validate_bound_inputs(payload, bound_inputs)
            except (TypeError, ValueError) as exc:
                raise DefiniteInterpreterFailure("OPERATION_PAYLOAD_INVALID") from exc
        # Only this call crosses the effect boundary. Unclassified failures here
        # or during output persistence remain OUTCOME_UNKNOWN and cannot retry.
        output = (self._invoke_with_assignment(payload, assignment)
                  if self._invoke_with_assignment is not None else self._invoke(payload))
        if self._validate_output is not None:
            self._validate_output(payload, output)
        content = canonical_json(self._output_codec.encode_payload(output)).encode()
        with self._uow_factory() as uow:
            digest = self._values.publish_output(uow.connection, assignment, scope, tables, content=content)
            uow.commit()
        return InterpreterOutcome.succeeded(digest)


class BatchTaskSingleDispatchHandler(PersistentOperationHandler[
    batch_task.BatchTaskSingleDispatchPayload, batch_task.BatchTaskSingleDispatchAck,
]):
    """The dispatch kernel adds payload scope and broker ACK association."""

    def __init__(
        self, *, uow_factory: UowFactory, binding: InterpreterBinding,
        dispatch: Callable[[batch_task.BatchTaskSingleDispatchPayload], batch_task.BatchTaskSingleDispatchAck],
    ) -> None:
        contract = batch_task.build_batch_task_single_dispatch_contract()
        super().__init__(
            uow_factory=uow_factory, binding=binding, contract=contract,
            input_codec=batch_task.build_batch_task_single_dispatch_payload_codec(contract.ref),
            output_codec=batch_task.build_batch_task_single_dispatch_ack_codec(contract.ref),
            invoke=dispatch, validate_input=self._check_scope, validate_output=self._check_ack,
        )

    @staticmethod
    def _check_scope(payload: batch_task.BatchTaskSingleDispatchPayload, scope: ProjectScopeRef, capability_id: str) -> None:
        if (payload.project_key != scope.project_key or payload.scope_digest != scope.scope_digest
                or payload.resolved_schema != scope.resolved_schema
                or payload.registry_revision != scope.project_registry_revision
                or payload.scope_incarnation != scope.incarnation or payload.capability_id != capability_id):
            raise ValueError("single dispatch payload scope drift")

    @staticmethod
    def _check_ack(payload: batch_task.BatchTaskSingleDispatchPayload, ack: batch_task.BatchTaskSingleDispatchAck) -> None:
        if (ack.dispatch_id != payload.dispatch_id or ack.channel != payload.item.channel
                or ack.lane != payload.lane or ack.trace_id != payload.trace_id
                or ack.workflow_run_id != payload.workflow_run_id
                or (payload.queue is not None and ack.queue != payload.queue)):
            raise ValueError("single dispatch ACK does not bind the dispatched item")

BATCH_TASK_SUBMISSION_ASSIGNMENT_BINDING_MISSING = (
    "BATCH_TASK_SUBMISSION_ASSIGNMENT_BINDING_MISSING"
)
BATCH_TASK_SUBMISSION_RUN_STORE_DRIFT = "BATCH_TASK_SUBMISSION_RUN_STORE_DRIFT"
BATCH_TASK_SUBMISSION_SCOPE_REHYDRATION_DRIFT = (
    "BATCH_TASK_SUBMISSION_SCOPE_REHYDRATION_DRIFT"
)
BATCH_TASK_SUBMISSION_PROGRAM_STORE_DRIFT = (
    "BATCH_TASK_SUBMISSION_PROGRAM_STORE_DRIFT"
)
BATCH_TASK_SUBMISSION_PLAN_STORE_DRIFT = "BATCH_TASK_SUBMISSION_PLAN_STORE_DRIFT"
BATCH_TASK_SUBMISSION_OPERATION_CATALOG_DRIFT = (
    "BATCH_TASK_SUBMISSION_OPERATION_CATALOG_DRIFT"
)
BATCH_TASK_SUBMISSION_DEPLOYMENT_CATALOG_DRIFT = (
    "BATCH_TASK_SUBMISSION_DEPLOYMENT_CATALOG_DRIFT"
)
BATCH_TASK_SUBMISSION_PAYLOAD_STORE_DRIFT = (
    "BATCH_TASK_SUBMISSION_PAYLOAD_STORE_DRIFT"
)
BATCH_TASK_SUBMISSION_PAYLOAD_CODEC_DRIFT = (
    "BATCH_TASK_SUBMISSION_PAYLOAD_CODEC_DRIFT"
)
BATCH_TASK_SUBMISSION_STORE_REHYDRATION_REJECTED = (
    "BATCH_TASK_SUBMISSION_STORE_REHYDRATION_REJECTED"
)
BATCH_TASK_SUBMISSION_RECEIPT_PERSISTENCE_REJECTED = (
    "BATCH_TASK_SUBMISSION_RECEIPT_PERSISTENCE_REJECTED"
)
BATCH_TASK_SUBMISSION_RECEIPT_CODEC_DRIFT = (
    "BATCH_TASK_SUBMISSION_RECEIPT_CODEC_DRIFT"
)

_PAYLOAD_VALUE_ID_SUFFIX = ":payload:task-submission"
_RECEIPT_VALUE_ID_SUFFIX = ":receipt:task-submission"
_HISTORICAL_RECEIPT_VALUE_ID_SUFFIX = ":receipt:batch_task-3"


@dataclass(frozen=True, slots=True)
class _LoadedClosure:
    program: ProgramSpec
    plan: ExecutionPlan
    contract_ref: Any
    payload_ref: ValueRef
    payload: batch_task.AgentBatchSubmission
    catalog: OperationContractCatalogSnapshot
    project_scope: ProjectScopeRef
    project_schema: str
    uow: RuntimeUnitOfWork


@dataclass(frozen=True, slots=True)
class _SubmissionScopeView:
    project_key: str
    registry_revision: int
    incarnation: str
    resolved_schema: str
    scope_digest: str


def read_batch_task_submission_receipt(
    connection: Connection,
    tables: Any,
    scope: RuntimeScope,
    *,
    program_id: str,
    historical: bool,
    current_codec_id: str = batch_task.SUBMISSION_RECEIPT_CODEC_ID,
) -> batch_task.SubmissionReceiptReadback | None:
    """Read one version-explicit receipt without changing its digest identity."""

    suffix = (
        _HISTORICAL_RECEIPT_VALUE_ID_SUFFIX
        if historical
        else _RECEIPT_VALUE_ID_SUFFIX
    )
    expected_codec_id = (
        batch_task.HISTORICAL_SUBMISSION_RECEIPT_CODEC_ID
        if historical
        else current_codec_id
    )
    expected_provenance_schema = (
        batch_task.HISTORICAL_SUBMISSION_RECEIPT_PROVENANCE_SCHEMA
        if historical
        else batch_task.SUBMISSION_RECEIPT_PROVENANCE_SCHEMA
    )
    value_id = f"{program_id}{suffix}"
    row = one_mapping(
        connection.execute(
            sa.select(tables.successor_values).where(
                tables.successor_values.c.project_key
                == scope.project_scope.project_key,
                tables.successor_values.c.value_id == value_id,
            )
        )
    )
    if row is None:
        return None
    provenance = row["provenance_json"]
    if (
        str(row["object_type"]) != batch_task.SUBMISSION_RECEIPT_TYPE.type_id
        or str(row["codec_id"]) != expected_codec_id
        or str(row["source_ref"]) != f"project-value:{value_id}"
        or not isinstance(provenance, dict)
        or "schema" not in provenance
        or provenance["schema"] != expected_provenance_schema
    ):
        raise ValueError("batch task submission receipt identity drift")
    exact = row["content_bytes"]
    if exact is None:
        exact = canonical_json(row["content_json"]).encode("utf-8")
    else:
        exact = bytes(exact)
    return batch_task.decode_submission_receipt_readback(
        codec_id=expected_codec_id,
        exact_bytes=exact,
        stored_digest=str(row["content_digest"]),
    )


class BatchTaskSubmissionStoreRehydratedHandler(RuntimeHandler):
    """Exact installed realization that rehydrates the batch-task closure.

    Constructor accepts only immutable deployment facts and a fresh-UoW
    factory; no Program/Plan/payload is captured.
    """

    def __init__(
        self,
        *,
        uow_factory: Callable[[], RuntimeUnitOfWork],
        handler_binding_digest: str,
        interpreter_profile_digest: str,
        operation_contract_digest: str,
        deployment_catalog_digest: str,
        receipt_codec_id: str,
        receipt_provenance_schema: str,
    ) -> None:
        require_digest(
            handler_binding_digest, "batch task submission handler binding digest"
        )
        if receipt_codec_id != batch_task.SUBMISSION_RECEIPT_CODEC_ID:
            raise ValueError("batch task submission receipt codec is not current")
        if receipt_provenance_schema != batch_task.SUBMISSION_RECEIPT_PROVENANCE_SCHEMA:
            raise ValueError("batch task submission receipt provenance is not current")
        require_digest(
            interpreter_profile_digest,
            "batch task submission interpreter profile digest",
        )
        require_digest(
            operation_contract_digest, "batch task submission operation digest"
        )
        require_digest(
            deployment_catalog_digest,
            "batch task submission deployment catalog digest",
        )
        self.uow_factory = uow_factory
        self.handler_binding_digest = handler_binding_digest
        self.interpreter_profile_digest = interpreter_profile_digest
        self.operation_contract_digest = operation_contract_digest
        self.deployment_catalog_digest = deployment_catalog_digest
        self.receipt_codec_id = receipt_codec_id
        self.receipt_provenance_schema = receipt_provenance_schema
        self.provider_calls = 0

    def execute(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> InterpreterOutcome:
        if claim.assignment_digest != assignment.assignment_digest:
            raise DefiniteInterpreterFailure("CLAIM_ASSIGNMENT_BINDING_DRIFT")
        if claim.claim_authority_epoch != assignment.claim_authority_epoch:
            raise DefiniteInterpreterFailure("CLAIM_AUTHORITY_EPOCH_DRIFT")
        if (
            assignment.handler_binding_digest != self.handler_binding_digest
            or assignment.operation_contract_digest != self.operation_contract_digest
        ):
            raise DefiniteInterpreterFailure(
                "EXACT_BATCH_TASK_SUBMISSION_HANDLER_BINDING_DRIFT"
            )
        if assignment.deployment_catalog_digest != self.deployment_catalog_digest:
            raise DefiniteInterpreterFailure(
                "EXACT_BATCH_TASK_SUBMISSION_DEPLOYMENT_CATALOG_DRIFT"
            )

        receipt_digest = self._load_interpret_and_persist(
            assignment,
            actor_id=context.node.node_id,
            observed_at=context.observed_at,
        )
        return InterpreterOutcome.succeeded(receipt_digest)

    def _load_interpret_and_persist(
        self,
        assignment: RuntimeAssignment,
        *,
        actor_id: str,
        observed_at: Any,
    ) -> str:
        if (
            assignment.assignment_kind is not AssignmentKind.INTERPRET
            or assignment.step_role is not CompiledStepRole.EFFECT
            or assignment.operation_contract_ref is None
            or assignment.plan_digest is None
            or assignment.payload_ref is None
            or assignment.payload_digest is None
        ):
            raise DefiniteInterpreterFailure(
                BATCH_TASK_SUBMISSION_ASSIGNMENT_BINDING_MISSING
            )
        if not isinstance(assignment.handler_binding, InterpreterBinding):
            raise DefiniteInterpreterFailure(BATCH_TASK_SUBMISSION_ASSIGNMENT_BINDING_MISSING)
        try:
            with self.uow_factory() as uow:
                connection = uow.connection
                run = self._load_run(connection, assignment)
                scope = self._resolve_scope(
                    connection, run, assignment, actor_id=actor_id
                )
                schema = scope.project_scope.resolved_schema
                tables = project_tables(sa.MetaData(), schema)
                program_ref = self._program_ref(connection, assignment)
                program = ProgramRepository(connection, tables).get(
                    scope,
                    program_ref,
                    expected_digest=assignment.program_digest,
                )
                self._require_payload_metadata(program)
                plan_ref = self._plan_ref(connection, run, assignment, program_ref)
                project_plan_row = self._project_plan_row(
                    connection, tables, assignment, plan_ref, program_ref
                )
                plan = PlanRepository(connection, tables).get(
                    scope.project_scope,
                    assignment.plan_digest,
                )
                catalog, contract_ref, codec = self._installed_closure(plan_ref)
                self._require_operation_catalog(
                    plan_ref, project_plan_row, catalog, contract_ref, assignment
                )
                payload_bytes, payload_ref = self._load_payload(
                    connection,
                    tables,
                    scope,
                    program,
                    assignment,
                )
                payload = self._decode_payload(codec, payload_bytes)
                self._require_payload_scope(payload, scope)
                self._require_deployment_catalog(connection, assignment)
                idem_repo = IdempotencyRepository(connection, scope)
                idem_binding = SharedIdempotencyBinding(
                    idempotency_id=f"idem:{program.program_id}:{payload.logical_request_id}",
                    capability_id=assignment.capability_id,
                    logical_request_id=payload.logical_request_id,
                    operation_kind=batch_task.SUBMISSION_KIND,
                    request_digest=payload.request_digest,
                    run_id=assignment.run_id,
                )
                try:
                    idem_row = idem_repo.reserve(idem_binding)
                except Exception as exc:
                    raise DefiniteInterpreterFailure(
                        "BATCH_TASK_SUBMISSION_IDEMPOTENCY_RESERVE_REJECTED"
                    ) from exc
                idem_state = str(idem_row["state"])
                if idem_state == "TERMINAL":
                    existing_digest = self._load_receipt_digest(
                        connection, tables, scope, program
                    )
                    if existing_digest is not None:
                        uow.commit()
                        return existing_digest
                    raise DefiniteInterpreterFailure(
                        "BATCH_TASK_SUBMISSION_TERMINAL_REPLAY_RECEIPT_ABSENT"
                    )
                loaded = _LoadedClosure(
                    program=program,
                    plan=plan,
                    contract_ref=contract_ref,
                    payload_ref=payload_ref,
                    payload=payload,
                    catalog=catalog,
                    project_scope=scope.project_scope,
                    project_schema=schema,
                    uow=uow,
                )
                outcome = BatchTaskSubmissionSuccessorInterpreter().interpret(
                    program=loaded.program,
                    plan=loaded.plan,
                    contract_ref=loaded.contract_ref,
                    payload_ref=loaded.payload_ref,
                    payload=loaded.payload,
                    project_scope=_SubmissionScopeView(
                        project_key=loaded.payload.project_key,
                        registry_revision=loaded.payload.registry_revision,
                        incarnation=loaded.payload.scope_incarnation,
                        resolved_schema=loaded.payload.resolved_schema,
                        scope_digest=loaded.payload.scope_digest,
                    ),
                    catalog=loaded.catalog,
                    deployment_catalog_digest=self.deployment_catalog_digest,
                    binding=assignment.handler_binding,
                    run_ref=assignment.run_id,
                    created_at=observed_at.isoformat(),
                )
                if isinstance(outcome, InterpreterFailure):
                    raise DefiniteInterpreterFailure(outcome.code)
                existing_digest = self._load_receipt_digest(
                    connection, tables, scope, program
                )
                if existing_digest is not None:
                    # Crash-before-terminal replay: adopt the persisted stable
                    # receipt identity instead of recomputing/persisting twice.
                    self._record_idempotency_terminal(
                        connection,
                        scope,
                        idem_repo,
                        idem_binding,
                        idem_row,
                        existing_digest,
                    )
                    uow.commit()
                    return existing_digest
                self._persist_receipt(loaded, outcome.value)
                self._record_idempotency_terminal(
                    connection,
                    scope,
                    idem_repo,
                    idem_binding,
                    idem_row,
                    outcome.value.receipt_digest,
                )
                uow.commit()
                return outcome.value.receipt_digest
        except DefiniteInterpreterFailure:
            raise
        except Exception as exc:
            raise DefiniteInterpreterFailure(
                BATCH_TASK_SUBMISSION_STORE_REHYDRATION_REJECTED
            ) from exc

    def _load_receipt_digest(
        self,
        connection: Connection,
        tables: Any,
        scope: RuntimeScope,
        program: ProgramSpec,
    ) -> str | None:
        try:
            readback = read_batch_task_submission_receipt(
                connection,
                tables,
                scope,
                program_id=program.program_id,
                historical=False,
                current_codec_id=self.receipt_codec_id,
            )
        except (TypeError, ValueError) as exc:
            raise DefiniteInterpreterFailure(
                BATCH_TASK_SUBMISSION_RECEIPT_CODEC_DRIFT
            ) from exc
        return None if readback is None else readback.stored_digest

    def _record_idempotency_terminal(
        self,
        connection: Connection,
        scope: RuntimeScope,
        repository: IdempotencyRepository,
        binding: SharedIdempotencyBinding,
        reserved_row: Any,
        receipt_digest: str,
    ) -> None:
        expected_revision = int(reserved_row["revision"])
        try:
            repository.record_terminal(
                binding.capability_id,
                binding.logical_request_id,
                expected_revision=expected_revision,
                terminal_observation_ref=f"receipt:sha256:{receipt_digest}",
            )
        except Exception as exc:
            raise DefiniteInterpreterFailure(
                "BATCH_TASK_SUBMISSION_IDEMPOTENCY_TERMINAL_REJECTED"
            ) from exc

    def _persist_receipt(self, loaded: _LoadedClosure, receipt: Any) -> None:
        try:
            connection = loaded.uow.connection
            tables = project_tables(sa.MetaData(), loaded.project_schema)
            scope = RuntimeScope(
                project_scope=loaded.project_scope,
                actor_id="runtime-node:batch-task-submit",
            )
            receipt_digest = content_digest(receipt, omit_fields=("receipt_digest",))
            if receipt_digest != receipt.receipt_digest:
                raise ValueError("receipt digest does not match receipt content")
            # Persist the canonical digest payload (receipt_digest excluded) so
            # the stored bytes hash to the same digest the dataclass binds.
            exact_bytes = canonical_json(
                receipt, omit_fields=("receipt_digest",)
            ).encode("utf-8")
            value_id = f"{loaded.program.program_id}{_RECEIPT_VALUE_ID_SUFFIX}"
            ValueRepository(connection, tables).put_exact(
                scope,
                value_id=value_id,
                object_type=batch_task.SUBMISSION_RECEIPT_TYPE.type_id,
                codec_id=self.receipt_codec_id,
                content=exact_bytes,
                expected_digest=receipt_digest,
                provenance_digest=content_digest(
                    {
                        "schema": self.receipt_provenance_schema,
                        "program_id": loaded.program.program_id,
                        "run_ref": receipt.run_ref,
                        "submission_id": receipt.submission_id,
                    }
                ),
                expected_revision=0,
                expected_incarnation=f"receipt-inc:{receipt_digest[:24]}",
                source_ref=f"project-value:{value_id}",
                provenance={
                    "schema": self.receipt_provenance_schema,
                    "program_id": loaded.program.program_id,
                    "submission_id": receipt.submission_id,
                    "receipt_digest": receipt_digest,
                },
            )
        except DefiniteInterpreterFailure:
            raise
        except Exception as exc:
            raise DefiniteInterpreterFailure(
                BATCH_TASK_SUBMISSION_RECEIPT_PERSISTENCE_REJECTED
            ) from exc

    # --- minimal shared-store helpers, mirroring the C2.1 handler ---

    def _load_run(self, connection: Connection, assignment: RuntimeAssignment) -> Any:
        row = one_mapping(
            connection.execute(
                sa.select(runtime_table("runtime_runs")).where(
                    runtime_table("runtime_runs").c.project_key == assignment.project_key,
                    runtime_table("runtime_runs").c.run_id == assignment.run_id,
                )
            )
        )
        if row is None:
            raise DefiniteInterpreterFailure(BATCH_TASK_SUBMISSION_RUN_STORE_DRIFT)
        return row

    def _resolve_scope(
        self,
        connection: Connection,
        run: Any,
        assignment: RuntimeAssignment,
        *,
        actor_id: str,
    ) -> RuntimeScope:
        resolver = ServerProjectScopeResolver(connection=connection)
        expected = resolver.resolve_expected(
            assignment.project_key,
            int(run["project_registry_revision"]),
            str(run["project_scope_digest"]),
        )
        if isinstance(expected, ProjectScopeStale):
            raise DefiniteInterpreterFailure(
                BATCH_TASK_SUBMISSION_SCOPE_REHYDRATION_DRIFT
            )
        current = resolver.resolve(assignment.project_key)
        if current != expected or current.resolved_schema != run["resolved_schema"]:
            raise DefiniteInterpreterFailure(
                BATCH_TASK_SUBMISSION_SCOPE_REHYDRATION_DRIFT
            )
        return RuntimeScope(project_scope=current, actor_id=actor_id)

    def _program_ref(
        self, connection: Connection, assignment: RuntimeAssignment
    ) -> str:
        row = one_mapping(
            connection.execute(
                sa.select(runtime_table("runtime_program_refs")).where(
                    runtime_table("runtime_program_refs").c.project_key
                    == assignment.project_key,
                    runtime_table("runtime_program_refs").c.program_digest
                    == assignment.program_digest,
                )
            )
        )
        if row is None:
            raise DefiniteInterpreterFailure(
                BATCH_TASK_SUBMISSION_PROGRAM_STORE_DRIFT
            )
        return str(row["program_id"])

    def _require_payload_metadata(self, program: ProgramSpec) -> None:
        metadata = dict(program.metadata or {})
        for name in (
            "payload_value_id",
            "payload_storage_ref",
            "payload_content_digest",
            "payload_provenance_digest",
        ):
            if name not in metadata:
                raise DefiniteInterpreterFailure(
                    BATCH_TASK_SUBMISSION_PROGRAM_STORE_DRIFT
                )

    def _plan_ref(
        self,
        connection: Connection,
        run: Any,
        assignment: RuntimeAssignment,
        program_ref: str,
    ) -> Any:
        refs = runtime_table("runtime_plan_refs")
        row = one_mapping(
            connection.execute(
                sa.select(refs).where(
                    refs.c.project_key == assignment.project_key,
                    refs.c.plan_digest == assignment.plan_digest,
                )
            )
        )
        if row is None:
            raise DefiniteInterpreterFailure(BATCH_TASK_SUBMISSION_PLAN_STORE_DRIFT)
        if (
            row["plan_id"] != run["plan_id"]
            or row["program_digest"] != assignment.program_digest
        ):
            raise DefiniteInterpreterFailure(BATCH_TASK_SUBMISSION_PLAN_STORE_DRIFT)
        return row

    def _project_plan_row(
        self,
        connection: Connection,
        tables: Any,
        assignment: RuntimeAssignment,
        plan_ref: Any,
        program_ref: str,
    ) -> Any:
        plans = tables.research_execution_plans
        row = one_mapping(
            connection.execute(
                sa.select(plans).where(
                    plans.c.project_key == assignment.project_key,
                    plans.c.plan_digest == assignment.plan_digest,
                )
            )
        )
        if row is None:
            raise DefiniteInterpreterFailure(BATCH_TASK_SUBMISSION_PLAN_STORE_DRIFT)
        if (
            row["plan_id"] != plan_ref["plan_id"]
            or row["program_id"] != plan_ref["program_id"]
            or row["program_digest"] != assignment.program_digest
        ):
            raise DefiniteInterpreterFailure(BATCH_TASK_SUBMISSION_PLAN_STORE_DRIFT)
        return row

    def _installed_closure(self, plan_ref: str) -> tuple[Any, Any, Any]:
        bundle = batch_task.build_batch_task_bundle()
        catalog = batch_task.build_batch_task_catalog(bundle)
        contract_ref = catalog.lookup(batch_task.SUBMISSION_KIND)
        if contract_ref is None:
            raise DefiniteInterpreterFailure(
                BATCH_TASK_SUBMISSION_OPERATION_CATALOG_DRIFT
            )
        codec = bundle.codec_by_kind(batch_task.SUBMISSION_KIND)
        return catalog, contract_ref, codec

    def _require_operation_catalog(
        self,
        plan_ref: Any,
        project_plan_row: Any,
        catalog: Any,
        contract_ref: Any,
        assignment: RuntimeAssignment,
    ) -> None:
        if (
            str(project_plan_row["operation_catalog_id"]) != catalog.catalog_id
            or str(project_plan_row["catalog_digest"]) != catalog.catalog_digest
            or str(plan_ref["operation_catalog_id"]) != catalog.catalog_id
            or str(plan_ref["catalog_digest"]) != catalog.catalog_digest
        ):
            raise DefiniteInterpreterFailure(
                BATCH_TASK_SUBMISSION_OPERATION_CATALOG_DRIFT
            )
        if contract_ref.contract_digest != assignment.operation_contract_digest:
            raise DefiniteInterpreterFailure(
                BATCH_TASK_SUBMISSION_OPERATION_CATALOG_DRIFT
            )

    def _load_payload(
        self,
        connection: Connection,
        tables: Any,
        scope: RuntimeScope,
        program: ProgramSpec,
        assignment: RuntimeAssignment,
    ) -> tuple[bytes, ValueRef]:
        metadata = dict(program.metadata)
        value_id = str(metadata["payload_value_id"])
        expected_value_id = f"{program.program_id}{_PAYLOAD_VALUE_ID_SUFFIX}"
        if value_id != expected_value_id:
            raise DefiniteInterpreterFailure(
                BATCH_TASK_SUBMISSION_PROGRAM_STORE_DRIFT
            )
        incarnation = (
            f"payload-inc:{content_digest(metadata['payload_content_digest'])}"
        )
        try:
            exact_bytes = ValueRepository(connection, tables).get_exact(
                scope,
                value_id=value_id,
                expected_revision=1,
                expected_incarnation=incarnation,
                expected_digest=str(metadata["payload_content_digest"]),
            )
        except Exception as exc:
            raise DefiniteInterpreterFailure(
                BATCH_TASK_SUBMISSION_PAYLOAD_STORE_DRIFT
            ) from exc
        payload_ref = ValueRef(
            value_id=value_id,
            project_key=program.project_key,
            object_type=batch_task.SUBMISSION_TYPE,
            codec_id=batch_task.SUBMISSION_PAYLOAD_CODEC_ID,
            content_digest=sha256_hex(exact_bytes),
            storage_kind="project_value_ref",
            store_id="successor_values",
            store_version="1",
            storage_ref=str(metadata["payload_storage_ref"]),
            byte_size=len(exact_bytes),
            provenance_digest=str(metadata["payload_provenance_digest"]),
        )
        return exact_bytes, payload_ref

    def _decode_payload(
        self, codec: Any, payload_bytes: bytes
    ) -> batch_task.AgentBatchSubmission:
        import json

        try:
            return codec.decode_payload(json.loads(payload_bytes.decode("utf-8")))
        except Exception as exc:
            raise DefiniteInterpreterFailure(
                BATCH_TASK_SUBMISSION_PAYLOAD_CODEC_DRIFT
            ) from exc

    def _require_payload_scope(
        self, payload: batch_task.AgentBatchSubmission, scope: RuntimeScope
    ) -> None:
        if (
            payload.project_key != scope.project_scope.project_key
            or payload.scope_digest != scope.project_scope.scope_digest
        ):
            raise DefiniteInterpreterFailure(
                BATCH_TASK_SUBMISSION_SCOPE_REHYDRATION_DRIFT
            )

    def _require_deployment_catalog(
        self, connection: Connection, assignment: RuntimeAssignment
    ) -> None:
        try:
            DeploymentCatalogRepository(connection).load(self.deployment_catalog_digest)
        except Exception as exc:
            raise DefiniteInterpreterFailure(
                BATCH_TASK_SUBMISSION_DEPLOYMENT_CATALOG_DRIFT
            ) from exc
