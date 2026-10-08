"""Batch business wait readback: facade states plus the reconciliation handler."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

from app.services.agent_batch.business_readback import (
    BusinessCancelObservation,
    BusinessTaskObservation,
    BusinessTaskState,
)
from app.successor_runtime.capabilities import batch_business
from app.successor_runtime.runtime.recovery import NonStartProof
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompiledStepRole,
    HandlerBindingKind,
    InterpreterBinding,
    RecoveryBinding,
    ReturnContractBinding,
    RuntimeAssignment,
    canonical_digest,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import (
    NodeIdentity,
    RuntimeExecutionContext,
)
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
from app.successor_runtime.runtime.reconciliation import ReconciliationState
from app.successor_runtime.runtime.transitions import EffectDisposition
from app.successor_runtime.substrate.postgres.effect_reconciliation import (
    BatchBusinessBrokerReadbackFacade,
    BatchBusinessNonStartUnprovable,
    BatchBusinessReadback,
    BatchBusinessReadbackError,
    BatchBusinessReadbackReplayData,
    BatchBusinessReadbackRequest,
    InstalledBatchTaskBusinessReadbackHandler,
    PostgresBatchTaskBusinessReadbackHandler,
)
from app.successor_runtime.substrate.postgres.models import (
    PUBLIC_METADATA,
    PUBLIC_TABLES,
    project_tables,
)
from app.successor_runtime.substrate.postgres.runtime_lifecycle import (
    AssignmentEnvelope,
    assignment_values,
)
from app.successor_runtime.substrate.postgres.session import compute_scope_digest


pytestmark = pytest.mark.unit


@compiles(JSONB, "sqlite")
def _sqlite_jsonb(_type: object, _compiler: object, **_kw: object) -> str:
    return "JSON"


NOW = datetime(2026, 8, 31, 8, 0, tzinfo=UTC)
PROJECT_KEY = "alpha"
PROJECT_SCHEMA = "project_alpha"
SCOPE_DIGEST = compute_scope_digest(PROJECT_KEY, PROJECT_SCHEMA, 1, "scope-inc-1")
TASK_ID = "celery-task:business-readback-1"
ACK_DIGEST = "b" * 64


def _digest(value: str | bytes) -> str:
    if isinstance(value, str):
        value = value.encode()
    return hashlib.sha256(value).hexdigest()


def _wait_operation() -> Any:
    return batch_business.build_batch_business_wait_contract()


def _request(
    *,
    celery_task_id: str = TASK_ID,
    attempt_id: str = "c" * 64,
) -> BatchBusinessReadbackRequest:
    operation = _wait_operation()
    return BatchBusinessReadbackRequest(
        project_key=PROJECT_KEY,
        project_scope_digest=SCOPE_DIGEST,
        run_id="run:wait",
        step_id="step:wait",
        attempt_id=attempt_id,
        assignment_digest="d" * 64,
        operation_contract_ref=operation.ref,
        handler_binding_digest="e" * 64,
        dispatch_id="dispatch:1",
        channel="search.market",
        lane="main",
        celery_task_id=celery_task_id,
        ack_digest=ACK_DIGEST,
    )


@pytest.mark.parametrize("field", ["project_scope_digest", "attempt_id", "assignment_digest", "handler_binding_digest", "ack_digest"])
def test_business_readback_preserves_opaque_task_id_and_strict_digests(field: str) -> None:
    request = _request()
    assert request.external_idempotency_key == TASK_ID
    with pytest.raises(ValueError):
        replace(request, **{field: "not-a-digest"})


class _FakeBroker:
    def __init__(
        self,
        state: BusinessTaskState,
        result: object | None = None,
    ) -> None:
        self.state = state
        self.result = result
        self.read_calls = 0
        self.cancel_calls = 0

    def read_task(self, task_id: str) -> BusinessTaskObservation:
        self.read_calls += 1
        return BusinessTaskObservation(
            task_id=task_id,
            state=self.state,
            result=self.result,
        )

    def cancel_task(self, task_id: str) -> BusinessCancelObservation:
        self.cancel_calls += 1
        return BusinessCancelObservation(task_id=task_id, state="REVOKE_REQUESTED")


def _facade(state: BusinessTaskState) -> tuple[
    BatchBusinessBrokerReadbackFacade, _FakeBroker
]:
    broker = _FakeBroker(state)
    facade = BatchBusinessBrokerReadbackFacade(
        operation_contract_ref=_wait_operation().ref,
        broker=broker,
    )
    return facade, broker


def test_facade_success_binds_typed_result_and_locator() -> None:
    output = {"items": [1, 2, 3], "ok": True}
    facade, broker = _facade(BusinessTaskState.SUCCESS)
    broker.result = output
    request = _request()
    observed = facade.readback_exact(request)

    assert isinstance(observed, BatchBusinessReadback)
    assert observed.result is not None
    assert observed.result.task_id == TASK_ID
    assert observed.result.provider_locator == f"celery-task:{TASK_ID}"
    assert observed.result.output == output
    assert observed.readback.disposition is EffectDisposition.SUCCEEDED
    assert observed.readback.receipt_digest == observed.result.receipt_digest
    assert broker.read_calls == 1


def test_facade_failure_and_revoked_are_terminal_failure() -> None:
    for state, reason in (
        (BusinessTaskState.FAILURE, "CELERY_TASK_FAILURE"),
        (BusinessTaskState.REVOKED, "CELERY_TASK_REVOKED"),
    ):
        facade, broker = _facade(state)
        broker.result = {"exception": "Boom", "traceback": "tb"}
        observed = facade.readback_exact(_request())
        assert not isinstance(observed, BatchBusinessReadback)
        assert observed.disposition is EffectDisposition.FAILED
        assert observed.reason == reason
        assert observed.failure_digest is not None


def test_facade_pending_and_unknown_are_waiting_evidence() -> None:
    for state, reason in (
        (BusinessTaskState.PENDING, "CELERY_PENDING"),
        (BusinessTaskState.UNKNOWN, "CELERY_BROKER_STATE_UNKNOWN"),
        (BusinessTaskState.NOT_STARTED, "CELERY_NOT_STARTED"),
    ):
        facade, _ = _facade(state)
        observed = facade.readback_exact(_request())
        assert observed.disposition is EffectDisposition.OUTCOME_UNKNOWN
        assert observed.reason == reason


def test_facade_cancel_returns_typed_revoke_request() -> None:
    facade, broker = _facade(BusinessTaskState.PENDING)
    result = facade.cancel(_request())
    assert result.state == "REVOKE_REQUESTED"
    assert result.task_id == TASK_ID
    assert broker.cancel_calls == 1


def test_facade_proves_not_started_only_from_authoritative_observation() -> None:
    facade, _ = _facade(BusinessTaskState.NOT_STARTED)
    proof = facade.prove_not_started(_request())
    assert isinstance(proof, NonStartProof)
    assert proof.external_idempotency_key == TASK_ID


def test_facade_pending_is_never_non_start_evidence() -> None:
    facade, _ = _facade(BusinessTaskState.PENDING)
    proof = facade.prove_not_started(_request())
    assert isinstance(proof, BatchBusinessNonStartUnprovable)
    assert proof.reason == "CELERY_PENDING_IS_NOT_NON_START_EVIDENCE"


def _scope() -> RuntimeScope:
    return RuntimeScope(
        project_scope=ProjectScopeRef(
            project_key=PROJECT_KEY,
            resolved_schema=PROJECT_SCHEMA,
            project_registry_revision=1,
            incarnation="scope-inc-1",
            scope_digest=SCOPE_DIGEST,
        ),
        actor_id="runtime-node-a",
    )


@pytest.fixture
def handler_db():
    engine = sa.create_engine("sqlite://")
    connection = engine.connect()
    connection.connection.create_function(
        "num_nonnulls", -1, lambda *values: sum(v is not None for v in values)
    )
    connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS public")
    connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS project_alpha")
    tables = project_tables(sa.MetaData(), PROJECT_SCHEMA)
    tables.successor_values.create(connection)
    PUBLIC_METADATA.create_all(
        connection,
        tables=[
            PUBLIC_TABLES["runtime_work_items"],
            PUBLIC_TABLES["runtime_effect_attempts"],
        ],
    )
    connection.commit()
    try:
        yield connection, tables, _scope()
    finally:
        connection.close()
        engine.dispose()


def _wait_assignment() -> tuple[
    RuntimeAssignment, ClaimBinding, RuntimeExecutionContext
]:
    operation = _wait_operation()
    deployment = _digest("deployment")
    profile = _digest("wait-profile")
    authority = _digest("wait-authority")
    binding = InterpreterBinding.from_content(
        operation_contract_digest=operation.ref.contract_digest,
        interpreter_profile_digest=profile,
        deployment_catalog_digest=deployment,
        runtime_protocol_version="1",
        project_scope_digest=SCOPE_DIGEST,
        resource_policy_epoch=2,
        authority_requirement_digest=authority,
    )
    returns = ReturnContractBinding.from_content(
        return_contract_ref=batch_business.BUSINESS_WAIT_KIND + ".return",
        success_modes=("succeeded",),
        failure_modes=("failed", "cancelled"),
        admission_required=False,
    )
    input_refs = ("project-value:dispatch:ack",)
    assignment = RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id="work:wait",
        assignment_kind=AssignmentKind.INTERPRET,
        project_key=PROJECT_KEY,
        run_id="run:wait",
        step_id="step:wait",
        step_role=CompiledStepRole.EFFECT,
        capability_id=batch_business.BUSINESS_WAIT_OWNER,
        operation_contract_ref=operation.ref,
        operation_contract_digest=operation.ref.contract_digest,
        return_contract_binding=returns,
        handler_binding_kind=HandlerBindingKind.INTERPRETER,
        handler_binding_ref=f"handler-binding:sha256:{binding.binding_digest}",
        handler_binding_digest=binding.binding_digest,
        handler_binding=binding,
        program_digest=_digest("program"),
        plan_digest=_digest("plan"),
        deployment_catalog_digest=deployment,
        execution_epoch=0,
        incarnation="run-inc-1",
        input_refs=input_refs,
        input_closure_digest=canonical_digest(input_refs),
        payload_ref=None,
        payload_digest=None,
        queue_eligibility_digest=_digest("eligibility"),
        resource_policy_epoch=2,
        claim_authority_epoch=5,
        claim_policy_digest=_digest("claim-policy"),
        expected_step_revision=2,
        trace_id="trace:wait",
    )
    claim = ClaimBinding.bind(
        assignment,
        authorization_digest=_digest("authorization"),
        lease_token="lease:wait",
        lease_expires_at=NOW + timedelta(minutes=5),
        node_id="runtime-node-a",
        node_profile_digest=_digest("node-profile"),
        interpreter_profile_digest=profile,
        authority_digest=_digest("claim-authority-context"),
    )
    context = RuntimeExecutionContext(
        node=NodeIdentity(
            node_id="runtime-node-a",
            incarnation="runtime-node-a:inc-1",
            started_at=NOW - timedelta(minutes=1),
        ),
        observed_at=NOW,
    )
    return assignment, claim, context


def _recovery(original: RuntimeAssignment) -> RecoveryBinding:
    profile = original.handler_binding.interpreter_profile_digest
    return RecoveryBinding.from_content(
        recovery_handler_id="batch.business.wait.readback",
        recovery_handler_version="1",
        interpreter_profile_digest=profile,
        authoritative_readback_profile_ref=batch_business.BUSINESS_WAIT_OBSERVATION_PROFILE,
    )


def _reconcile_assignment(
    original: RuntimeAssignment,
    original_claim: ClaimBinding,
    recovery: RecoveryBinding,
) -> RuntimeAssignment:
    values = original.model_dump(mode="python")
    values.update(
        work_item_id=f"reconcile:{original_claim.attempt_id}",
        assignment_kind=AssignmentKind.RECONCILE,
        handler_binding_kind=HandlerBindingKind.RECOVERY,
        handler_binding_ref=f"handler-binding:sha256:{recovery.binding_digest}",
        handler_binding_digest=recovery.binding_digest,
        handler_binding=recovery,
        expected_step_revision=(original.expected_step_revision or 0) + 1,
        reconciliation_attempt_id=original_claim.attempt_id,
    )
    return RuntimeAssignment(**values)


def _seed_wait(
    connection: sa.Connection,
    original: RuntimeAssignment,
    original_claim: ClaimBinding,
    recovery: RecoveryBinding,
) -> None:
    envelope = AssignmentEnvelope(
        assignment=original,
        required_node_profile_selector="node-profile:wait",
        authority_digest=original_claim.authorization_digest,
        resource_policy_digest=_digest("resource-policy"),
        qualification_digest=_digest("qualification"),
        fairness_key="wait:fairness",
        resource_class="NETWORK_IO",
        resource_units=1,
        concurrency_key="project:alpha:wait",
        provider_key="celery",
        recovery_binding=recovery,
        authoritative_readback_profile_ref=recovery.authoritative_readback_profile_ref,
    )
    work_values = assignment_values(envelope, due_at=NOW)
    work_values.update(
        state="WAITING",
        wait_reason="BACKOFF",
        enqueue_seq=1,
        created_at=NOW,
        updated_at=NOW,
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_work_items"]).values(**work_values)
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_effect_attempts"]).values(
            attempt_id=original_claim.attempt_id,
            project_key=original.project_key,
            run_id=original.run_id,
            step_id=original.step_id,
            execution_epoch=original.execution_epoch,
            incarnation=original.incarnation,
            assignment_digest=original.assignment_digest,
            handler_binding_digest=original.handler_binding_digest,
            handler_realization_digest=original.handler_binding_digest,
            idempotency_key=f"attempt:{original_claim.attempt_id}",
            authorization_digest=original_claim.authorization_digest,
            input_digest=original.input_closure_digest,
            claim_binding_json=original_claim.model_dump(mode="json"),
            claim_binding_digest=original_claim.binding_digest,
            disposition=EffectDisposition.OUTCOME_UNKNOWN.value,
            revision=2,
            dispatched_at=NOW - timedelta(minutes=2),
            started_at=NOW - timedelta(minutes=2),
            created_at=NOW - timedelta(minutes=2),
            updated_at=NOW,
        )
    )
    connection.commit()


class _FakeReplay:
    def __init__(self, scope: RuntimeScope) -> None:
        self.scope = scope

    def load_exact(
        self,
        connection: sa.Connection,
        installation: InstalledBatchTaskBusinessReadbackHandler,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> BatchBusinessReadbackReplayData:
        request = BatchBusinessReadbackRequest(
            project_key=assignment.project_key,
            project_scope_digest=self.scope.project_scope.scope_digest,
            run_id=assignment.run_id,
            step_id=assignment.step_id or "",
            attempt_id=claim.attempt_id,
            assignment_digest=assignment.assignment_digest,
            operation_contract_ref=assignment.operation_contract_ref,
            handler_binding_digest=assignment.handler_binding_digest,
            dispatch_id="dispatch:1",
            channel="search.market",
            lane="main",
            celery_task_id=TASK_ID,
            ack_digest=ACK_DIGEST,
        )
        return BatchBusinessReadbackReplayData(scope=self.scope, request=request)


class _Uow:
    def __init__(self, connection: sa.Connection) -> None:
        self.connection = connection
        self.transaction: Any = None

    def __enter__(self) -> Any:
        self.transaction = self.connection.begin()
        return self

    def commit(self) -> None:
        self.transaction.commit()

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.transaction.is_active:
            self.transaction.rollback()


class _FakePublisher:
    def __init__(self) -> None:
        self.published: list[batch_business.BatchBusinessResult] = []
        self.digest = "f" * 64

    def publish(self, connection, assignment, scope, result) -> str:
        self.published.append(result)
        return self.digest


def _setup(
    handler_db,
    state: BusinessTaskState,
) -> tuple[
    RuntimeAssignment,
    ClaimBinding,
    RuntimeExecutionContext,
    PostgresBatchTaskBusinessReadbackHandler,
]:
    connection, tables, scope = handler_db
    PUBLIC_TABLES["runtime_work_items"].create(connection, checkfirst=True)
    PUBLIC_TABLES["runtime_effect_attempts"].create(connection, checkfirst=True)
    connection.commit()
    original, original_claim, context = _wait_assignment()
    recovery = _recovery(original)
    reconciliation = _reconcile_assignment(original, original_claim, recovery)
    reconcile_claim = ClaimBinding.bind(
        reconciliation,
        authorization_digest=original_claim.authorization_digest,
        lease_token="lease:reconciliation",
        lease_expires_at=NOW + timedelta(minutes=5),
        node_id=context.node.node_id,
        node_profile_digest=original_claim.node_profile_digest,
        interpreter_profile_digest=recovery.interpreter_profile_digest,
        authority_digest=original_claim.authority_digest,
    )
    _seed_wait(connection, original, original_claim, recovery)
    broker = _FakeBroker(state)
    facade = BatchBusinessBrokerReadbackFacade(
        operation_contract_ref=original.operation_contract_ref,
        broker=broker,
    )
    handler = PostgresBatchTaskBusinessReadbackHandler(
        InstalledBatchTaskBusinessReadbackHandler(
            recovery_binding=recovery,
            operation_contract_digest=original.operation_contract_digest,
        ),
        lambda: _Uow(connection),
        readback=facade,
        replay=_FakeReplay(scope),
        publisher=_FakePublisher(),
    )
    return reconciliation, reconcile_claim, context, handler


def test_handler_waiting_is_typed_and_never_dispaches(handler_db) -> None:
    reconciliation, reconcile_claim, context, handler = _setup(
        handler_db, BusinessTaskState.PENDING
    )
    outcome = handler.execute(reconciliation, reconcile_claim, context)
    assert outcome.result.state is ReconciliationState.WAITING
    assert outcome.result.disposition is EffectDisposition.OUTCOME_UNKNOWN
    assert outcome.output_digest is None
    assert outcome.receipt_ref is None


def test_handler_success_adopts_business_terminal(handler_db) -> None:
    reconciliation, reconcile_claim, context, handler = _setup(
        handler_db, BusinessTaskState.SUCCESS
    )
    outcome = handler.execute(reconciliation, reconcile_claim, context)
    assert outcome.result.state is ReconciliationState.RESOLVED
    assert outcome.result.disposition is EffectDisposition.SUCCEEDED
    assert outcome.output_digest == "f" * 64
    assert outcome.receipt_ref == "receipt:sha256:" + "f" * 64


def test_handler_failure_binds_business_failure(handler_db) -> None:
    reconciliation, reconcile_claim, context, handler = _setup(
        handler_db, BusinessTaskState.FAILURE
    )
    outcome = handler.execute(reconciliation, reconcile_claim, context)
    assert outcome.result.state is ReconciliationState.RESOLVED
    assert outcome.result.disposition is EffectDisposition.FAILED
    assert outcome.output_digest is None
    assert outcome.receipt_ref is None


def test_handler_rejects_recovery_binding_drift(handler_db) -> None:
    connection, tables, scope = handler_db
    PUBLIC_TABLES["runtime_work_items"].create(connection, checkfirst=True)
    PUBLIC_TABLES["runtime_effect_attempts"].create(connection, checkfirst=True)
    connection.commit()
    original, original_claim, context = _wait_assignment()
    recovery = _recovery(original)
    drifted = RecoveryBinding.from_content(
        recovery_handler_id=recovery.recovery_handler_id,
        recovery_handler_version="2.0.0",
        interpreter_profile_digest=recovery.interpreter_profile_digest,
        authoritative_readback_profile_ref=recovery.authoritative_readback_profile_ref,
    )
    reconciliation = _reconcile_assignment(original, original_claim, drifted)
    reconcile_claim = ClaimBinding.bind(
        reconciliation,
        authorization_digest=original_claim.authorization_digest,
        lease_token="lease:drifted",
        lease_expires_at=NOW + timedelta(minutes=5),
        node_id=context.node.node_id,
        node_profile_digest=original_claim.node_profile_digest,
        interpreter_profile_digest=drifted.interpreter_profile_digest,
        authority_digest=original_claim.authority_digest,
    )
    _seed_wait(connection, original, original_claim, recovery)
    broker = _FakeBroker(BusinessTaskState.PENDING)
    facade = BatchBusinessBrokerReadbackFacade(
        operation_contract_ref=original.operation_contract_ref, broker=broker
    )
    handler = PostgresBatchTaskBusinessReadbackHandler(
        InstalledBatchTaskBusinessReadbackHandler(
            recovery_binding=recovery,
            operation_contract_digest=original.operation_contract_digest,
        ),
        lambda: _Uow(connection),
        readback=facade,
        replay=_FakeReplay(scope),
        publisher=_FakePublisher(),
    )
    with pytest.raises(BatchBusinessReadbackError, match="RecoveryBinding"):
        handler.execute(reconciliation, reconcile_claim, context)


def test_business_wait_kernel_preserves_terminal_waiting_and_drift() -> None:
    from app.services.agent_batch.business_readback import build_batch_business_wait_invoke
    from app.successor_runtime.capabilities.batch_task import BatchTaskSingleDispatchAck
    from app.successor_runtime.runtime.node import DefiniteInterpreterFailure, OutcomeUncertain

    ack = BatchTaskSingleDispatchAck(
        schema_version="mrw.batch.task-dispatch.ack.v2", operation_kind="batch.task.dispatch_single.v2",
        dispatch_id="dispatch:wait", channel="search.market", celery_task_id="task:wait", lane="main", queue="celery",
    )
    output = {"nested": [None, {"ok": True}], "number": 2}
    result = build_batch_business_wait_invoke(_FakeBroker(BusinessTaskState.SUCCESS, output))(ack)
    contract = batch_business.build_batch_business_wait_contract()
    codec = batch_business.build_batch_business_wait_result_codec(contract.ref)
    assert codec.decode_payload(codec.encode_payload(result)) == result
    assert result.output == output
    assert batch_business.build_batch_business_wait_registry().resolve_required(contract.ref) == contract
    for state, error in ((BusinessTaskState.FAILURE, DefiniteInterpreterFailure),
                         (BusinessTaskState.REVOKED, DefiniteInterpreterFailure),
                         (BusinessTaskState.PENDING, OutcomeUncertain),
                         (BusinessTaskState.UNKNOWN, OutcomeUncertain)):
        with pytest.raises(error):
            build_batch_business_wait_invoke(_FakeBroker(state))(ack)
    broker = _FakeBroker(BusinessTaskState.SUCCESS)
    broker.read_task = lambda task_id: BusinessTaskObservation("different-task", BusinessTaskState.SUCCESS)
    with pytest.raises(DefiniteInterpreterFailure, match="DRIFT"):
        build_batch_business_wait_invoke(broker)(ack)


def test_business_result_rejects_invalid_identity_and_digest() -> None:
    for constructor in (lambda: BusinessTaskObservation("", BusinessTaskState.PENDING),
                        lambda: BusinessCancelObservation("", "REVOKE_REQUESTED")):
        with pytest.raises(ValueError):
            constructor()
    result = batch_business.build_batch_business_result_from_ack_fields(task_id="task:one", ack_digest="a" * 64)
    for changes in ({"schema_version": "wrong"}, {"operation_kind": "wrong"}, {"task_id": ""},
                    {"provider_locator": ""}, {"receipt_digest": ""}, {"result_digest": "wrong"}):
        with pytest.raises(ValueError):
            replace(result, **changes)
