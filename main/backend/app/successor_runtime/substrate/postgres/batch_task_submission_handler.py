"""Persistent operation handler used by installed single-item dispatch."""

from __future__ import annotations

from collections.abc import Callable
import json
from typing import Generic, Literal, TypeVar

import sqlalchemy as sa

from app.successor_runtime.capabilities import batch_task as batch_task
from app.successor_runtime.capabilities.checksum import (
    CanonicalJsonValue,
    canonical_json,
)
from app.successor_runtime.capabilities.codecs import PayloadCodec
from app.successor_runtime.language.object_contracts import OperationContract
from app.successor_runtime.language.algebra import ValueRef
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    RuntimeAssignment,
    InterpreterBinding,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import (
    DefiniteInterpreterFailure,
    InterpreterOutcome,
    RuntimeExecutionContext,
    RuntimeHandler,
)
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
from app.successor_runtime.substrate.postgres.models import project_tables
from app.successor_runtime.substrate.postgres.runtime_journal import (
    ExactBindingConflict,
    RecordNotFound,
)
from app.successor_runtime.substrate.postgres.session import (
    ServerProjectScopeResolver,
)
from app.successor_runtime.substrate.postgres.runtime_activation import (
    PostgresRuntimeActivationBindingAdapter,
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
        self._values = PostgresRuntimeActivationBindingAdapter()

    @property
    def input_codec(self) -> PayloadCodec[Input]:
        return self._input_codec

    @property
    def output_codec(self) -> PayloadCodec[Output]:
        return self._output_codec

    @property
    def input_payload_type_id(self) -> str:
        return self._input_codec.payload_type_id

    @property
    def output_payload_type_id(self) -> str:
        return self._output_codec.payload_type_id

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
        contract: OperationContract,
        input_codec: PayloadCodec[batch_task.BatchTaskSingleDispatchPayload],
        output_codec: PayloadCodec[batch_task.BatchTaskSingleDispatchAck],
        dispatch: Callable[[batch_task.BatchTaskSingleDispatchPayload], batch_task.BatchTaskSingleDispatchAck],
    ) -> None:
        super().__init__(
            uow_factory=uow_factory, binding=binding, contract=contract,
            input_codec=input_codec, output_codec=output_codec,
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
