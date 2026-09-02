from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Self

import pytest

from app.successor_runtime.language.object_contracts import (
    OperationContractRef,
    ReturnContract,
)
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
    ClaimBatchPort,
    DeploymentBinding,
    InterpreterOutcome,
    LeaseLost,
    NodeIdentity,
    OutcomeCommitPort,
    RuntimeClaim,
    RuntimeNodeProfile,
    RuntimeNodeProtocol,
)
from app.successor_runtime.runtime.ports import (
    RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
    ControlPlaneScope,
    ProjectScopeRef,
    RuntimeScope,
)
from app.successor_runtime.runtime.reconciliation import (
    AuthoritativeEffectReadback,
    ReconciliationHandlerOutcome,
    ReconciliationResult,
    ReconciliationState,
)
from app.successor_runtime.runtime.transitions import EffectDisposition
from app.successor_runtime.substrate.postgres.node_adapter import (
    PostgresRuntimeNodeAdapter,
)
from app.successor_runtime.substrate.postgres.runtime_lifecycle import (
    ClaimedLifecycle,
    EffectTerminalKind,
    TerminalOutcome,
)
from app.successor_runtime.substrate.postgres.work_items import (
    ClaimConflict,
    ClaimRecord,
    NodeClaimContext,
)

NOW = datetime(2030, 1, 1, tzinfo=UTC)
NODE_PROFILE_DIGEST = canonical_digest(("node-profile",))
CATALOG_DIGEST = canonical_digest(("deployment-catalog",))
INTERPRETER_PROFILE_DIGEST = canonical_digest(("interpreter-profile",))


def _digest(label: str) -> str:
    return canonical_digest((label,))


def _assignment(work_item_id: str) -> RuntimeAssignment:
    operation_digest = _digest(f"operation:{work_item_id}")
    binding = InterpreterBinding.from_content(
        operation_contract_digest=operation_digest,
        interpreter_profile_digest=INTERPRETER_PROFILE_DIGEST,
        deployment_catalog_digest=CATALOG_DIGEST,
        runtime_protocol_version="1",
        project_scope_digest=_digest("project-scope"),
        resource_policy_epoch=3,
        authority_requirement_digest=_digest("authority-requirement"),
    )
    return_binding = ReturnContractBinding.from_contract(
        "mrw.return.runtime-value.v1",
        ReturnContract(
            success_modes=("SUCCEEDED",),
            failure_modes=("FAILED",),
            admission_required=False,
        ),
    )
    return RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id=work_item_id,
        assignment_kind=AssignmentKind.INTERPRET,
        project_key="project-1",
        run_id=f"run-{work_item_id}",
        step_id=f"step-{work_item_id}",
        step_role=CompiledStepRole.EFFECT,
        capability_id="capability-1",
        operation_contract_ref=OperationContractRef(
            kind="fixture.operation.v1",
            contract_version="1.0.0",
            contract_digest=operation_digest,
        ),
        operation_contract_digest=operation_digest,
        return_contract_binding=return_binding,
        handler_binding_kind=HandlerBindingKind.INTERPRETER,
        handler_binding_ref=f"handler-binding:sha256:{binding.binding_digest}",
        handler_binding_digest=binding.binding_digest,
        handler_binding=binding,
        program_digest=_digest("program"),
        plan_digest=_digest("plan"),
        deployment_catalog_digest=CATALOG_DIGEST,
        execution_epoch=1,
        incarnation="run-incarnation-1",
        input_refs=("value:1",),
        input_closure_digest=_digest(f"input:{work_item_id}"),
        queue_eligibility_digest=_digest("queue-eligibility"),
        resource_policy_epoch=3,
        claim_authority_epoch=4,
        claim_policy_digest=_digest("claim-policy"),
        expected_step_revision=0,
        trace_id=f"trace-{work_item_id}",
    )


def _reconciliation_assignment(
    work_item_id: str, *, target_attempt_id: str
) -> RuntimeAssignment:
    original = _assignment(f"original:{work_item_id}")
    recovery = RecoveryBinding.from_content(
        recovery_handler_id="fixture-authoritative-readback",
        recovery_handler_version="1",
        interpreter_profile_digest=INTERPRETER_PROFILE_DIGEST,
        authoritative_readback_profile_ref="fixture-readback-profile",
    )
    values = original.model_dump(mode="python")
    values.update(
        work_item_id=work_item_id,
        assignment_kind=AssignmentKind.RECONCILE,
        handler_binding_kind=HandlerBindingKind.RECOVERY,
        handler_binding_ref=f"handler-binding:sha256:{recovery.binding_digest}",
        handler_binding_digest=recovery.binding_digest,
        handler_binding=recovery,
        reconciliation_attempt_id=target_attempt_id,
        expected_step_revision=3,
    )
    return RuntimeAssignment(**values)


@dataclass
class _Pending:
    assignment: RuntimeAssignment
    authorization_digest: str


@dataclass
class _Durable:
    claim: RuntimeClaim
    lifecycle: ClaimedLifecycle


class _Backend:
    def __init__(self, pending: tuple[_Pending, ...]) -> None:
        self.pending = deque(pending)
        self.durable: dict[str, _Durable] = {}
        self.claim_contexts: list[NodeClaimContext] = []
        self.terminals: list[TerminalOutcome] = []
        self.reconciliation_adoptions: list[dict[str, object]] = []
        self.fail_heartbeat = False
        self.connection_ids: list[int] = []
        self.uows: list[_FakeUow] = []
        self.scope = RuntimeScope(
            project_scope=ProjectScopeRef(
                project_key="project-1",
                resolved_schema="mrw_p_fixture",
                project_registry_revision=1,
                incarnation="project-incarnation-1",
                scope_digest=_digest("project-scope"),
            ),
            actor_id="runtime-node",
        )

    def uow_factory(self) -> _FakeUow:
        uow = _FakeUow(self, connection_id=len(self.uows) + 1)
        self.uows.append(uow)
        return uow

    def claim_repository(self, connection: Any) -> _FakeClaimRepository:
        return _FakeClaimRepository(self, connection)

    def lifecycle_repository(
        self, connection: Any, scope: RuntimeScope
    ) -> _FakeLifecycleRepository:
        assert scope.project_scope == self.scope.project_scope
        return _FakeLifecycleRepository(self, connection)

    def state_reader(self, connection: Any) -> _FakeStateReader:
        return _FakeStateReader(self, connection)

    def reconciliation_owner(self, connection: Any) -> _FakeReconciliationOwner:
        return _FakeReconciliationOwner(self, connection)

    def runtime_failure_repository(
        self, connection: Any, scope: RuntimeScope
    ) -> _FakeRuntimeFailureRepository:
        assert scope.project_scope == self.scope.project_scope
        return _FakeRuntimeFailureRepository(connection)


@dataclass(frozen=True)
class _FakeFailureRecord:
    failure_ref: str
    failure_digest: str


class _FakeRuntimeFailureRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def put_exact(
        self,
        _scope: RuntimeScope,
        *,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        failure_code: str,
    ) -> _FakeFailureRecord:
        return _FakeFailureRecord(
            failure_ref=f"project-value:runtime-failure:{claim.attempt_id}",
            failure_digest=canonical_digest(
                {
                    "assignment_digest": assignment.assignment_digest,
                    "attempt_id": claim.attempt_id,
                    "failure_code": failure_code,
                }
            ),
        )


class _FakeUow:
    def __init__(self, backend: _Backend, *, connection_id: int) -> None:
        self.backend = backend
        self.connection = connection_id
        self.committed = False
        self.rolled_back = False

    def __enter__(self) -> Self:
        self.backend.connection_ids.append(self.connection)
        return self

    def commit(self) -> None:
        self.committed = True

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if not self.committed:
            self.rolled_back = True


class _FakeClaimRepository:
    def __init__(self, backend: _Backend, connection: Any) -> None:
        self.backend = backend
        self.connection = connection

    def claim_due(
        self,
        control_scope: ControlPlaneScope,
        context: NodeClaimContext,
        *,
        limit: int,
        fairness: object,
        now: datetime,
        cursor: int | None = None,
    ) -> tuple[ClaimRecord, ...]:
        del fairness, cursor
        control_scope.require_permission(RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION)
        self.backend.claim_contexts.append(context)
        records: list[ClaimRecord] = []
        while self.backend.pending and len(records) < limit:
            pending = self.backend.pending.popleft()
            assignment = pending.assignment
            requires_reservation = (
                assignment.assignment_kind is not AssignmentKind.RECONCILE
            )
            binding = ClaimBinding.bind(
                assignment,
                authorization_digest=pending.authorization_digest,
                lease_token=f"lease:{assignment.work_item_id}:{context.node_id}",
                lease_expires_at=now + timedelta(seconds=context.lease_seconds),
                node_id=context.node_id,
                node_profile_digest=context.node_profile_digest,
                authority_digest=pending.authorization_digest,
                interpreter_profile_digest=INTERPRETER_PROFILE_DIGEST,
                execution_reservation_ref=(
                    f"reservation:{assignment.work_item_id}"
                    if requires_reservation
                    else None
                ),
                execution_reservation_digest=(
                    _digest(f"reservation:{assignment.work_item_id}")
                    if requires_reservation
                    else None
                ),
            )
            claim = RuntimeClaim(
                assignment=assignment,
                claim_binding=binding,
                work_item_revision=1,
            )
            lifecycle = ClaimedLifecycle(
                claim=binding,
                run_id=assignment.run_id,
                step_id=assignment.step_id or "",
                work_item_id=assignment.work_item_id,
                attempt_id=binding.attempt_id,
                reservation_id=binding.execution_reservation_ref or "",
                expected_run_revision=5,
                expected_step_revision=2,
                expected_work_revision=1,
                expected_attempt_revision=0,
                expected_reservation_revision=0,
            )
            self.backend.durable[binding.attempt_id] = _Durable(claim, lifecycle)
            records.append(
                ClaimRecord(
                    work_item_id=assignment.work_item_id,
                    project_key=assignment.project_key,
                    run_id=assignment.run_id,
                    step_id=assignment.step_id,
                    assignment_digest=assignment.assignment_digest,
                    attempt_id=binding.attempt_id,
                    lease_token=binding.lease_token,
                    lease_expires_at=binding.lease_expires_at,
                    reservation_id=binding.execution_reservation_ref,
                    assignment=assignment,
                    claim_binding=binding,
                )
            )
        return tuple(records)

    def heartbeat(
        self,
        control_scope: ControlPlaneScope,
        work_item_id: str,
        lease_token: str,
        *,
        expected_revision: int,
        new_expiry: datetime,
    ) -> dict[str, object]:
        del control_scope
        if self.backend.fail_heartbeat:
            raise ClaimConflict("simulated stale lease")
        durable = next(
            item
            for item in self.backend.durable.values()
            if item.claim.assignment.work_item_id == work_item_id
        )
        if (
            durable.claim.work_item_revision != expected_revision
            or durable.claim.claim_binding.lease_token != lease_token
        ):
            raise ClaimConflict("simulated revision drift")
        old = durable.claim.claim_binding
        binding = ClaimBinding.bind(
            durable.claim.assignment,
            authorization_digest=old.authorization_digest,
            lease_token=old.lease_token,
            lease_expires_at=new_expiry,
            node_id=old.node_id,
            node_profile_digest=old.node_profile_digest,
            authority_digest=old.authority_digest,
            interpreter_profile_digest=old.interpreter_profile_digest,
            execution_reservation_ref=old.execution_reservation_ref,
            execution_reservation_digest=old.execution_reservation_digest,
        )
        durable.claim = replace(
            durable.claim,
            claim_binding=binding,
            work_item_revision=expected_revision + 1,
        )
        durable.lifecycle = replace(
            durable.lifecycle,
            claim=binding,
            expected_work_revision=durable.lifecycle.expected_work_revision + 1,
            expected_attempt_revision=durable.lifecycle.expected_attempt_revision + 1,
            expected_reservation_revision=(
                durable.lifecycle.expected_reservation_revision + 1
            ),
        )
        return {"work_item_id": work_item_id}


class _FakeStateReader:
    def __init__(self, backend: _Backend, connection: Any) -> None:
        self.backend = backend
        self.connection = connection

    def runtime_claim(self, record: ClaimRecord) -> RuntimeClaim:
        return self.backend.durable[record.claim_binding.attempt_id].claim

    def renewed_claim(
        self, previous: RuntimeClaim, row: dict[str, object]
    ) -> RuntimeClaim:
        del row
        return self.backend.durable[previous.claim_binding.attempt_id].claim

    def claimed_lifecycle(
        self,
        claim: RuntimeClaim,
        control_scope: ControlPlaneScope,
        *,
        require_started: bool,
    ) -> tuple[RuntimeScope, ClaimedLifecycle]:
        durable = self.backend.durable[claim.claim_binding.attempt_id]
        assert durable.claim == claim
        expected = (
            EffectDisposition.IN_FLIGHT
            if require_started
            else EffectDisposition.NOT_STARTED
        )
        assert claim.effect_disposition is expected
        return (
            replace(self.backend.scope, actor_id=control_scope.system_actor_id),
            durable.lifecycle,
        )


class _FakeLifecycleRepository:
    def __init__(self, backend: _Backend, connection: Any) -> None:
        self.backend = backend
        self.connection = connection

    def start_claim(
        self, claimed: ClaimedLifecycle, *, observed_at: datetime | None = None
    ) -> None:
        assert observed_at is not None
        durable = self.backend.durable[claimed.attempt_id]
        durable.claim = replace(
            durable.claim,
            work_item_revision=durable.claim.work_item_revision + 1,
            effect_disposition=EffectDisposition.IN_FLIGHT,
        )
        durable.lifecycle = replace(
            claimed,
            expected_run_revision=claimed.expected_run_revision + 1,
            expected_step_revision=claimed.expected_step_revision + 1,
            expected_work_revision=claimed.expected_work_revision + 1,
            expected_attempt_revision=claimed.expected_attempt_revision + 1,
        )

    def commit_outcome(self, outcome: TerminalOutcome) -> None:
        self.backend.terminals.append(outcome)


class _FakeReconciliationOwner:
    def __init__(self, backend: _Backend, connection: Any) -> None:
        self.backend = backend
        self.connection = connection

    def adopt(self, **values: object) -> None:
        self.backend.reconciliation_adoptions.append(
            {"connection": self.connection, **values}
        )


def _adapter(backend: _Backend) -> PostgresRuntimeNodeAdapter:
    return PostgresRuntimeNodeAdapter(
        backend.uow_factory,
        claim_repository_factory=backend.claim_repository,
        lifecycle_repository_factory=backend.lifecycle_repository,
        state_reader_factory=backend.state_reader,
        reconciliation_owner_factory=backend.reconciliation_owner,
        runtime_failure_repository_factory=backend.runtime_failure_repository,
    )


def _node_context(node_id: str):
    return {
        "control_scope": ControlPlaneScope(
            system_actor_id=node_id,
            permission=RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
            authority_epoch=4,
        ),
        "node": NodeIdentity(
            node_id=node_id,
            incarnation=f"{node_id}-incarnation",
            started_at=NOW - timedelta(minutes=1),
        ),
        "profile": RuntimeNodeProfile(
            profile_digest=NODE_PROFILE_DIGEST,
            supported_assignment_kinds=frozenset({AssignmentKind.INTERPRET}),
            interpreter_profile_digests=frozenset({INTERPRETER_PROFILE_DIGEST}),
        ),
        "deployment": DeploymentBinding(
            catalog_digest=CATALOG_DIGEST,
            node_profile_digest=NODE_PROFILE_DIGEST,
            runtime_protocol_version="1",
        ),
        "protocol": RuntimeNodeProtocol(version="1"),
    }


def test_fixed_node_context_claims_distinct_step_authorizations_and_two_nodes() -> None:
    backend = _Backend(
        (
            _Pending(_assignment("work-a"), _digest("authorization-a")),
            _Pending(_assignment("work-b"), _digest("authorization-b")),
            _Pending(_assignment("work-c"), _digest("authorization-c")),
        )
    )
    adapter = _adapter(backend)
    assert isinstance(adapter, ClaimBatchPort)
    assert isinstance(adapter, OutcomeCommitPort)
    node_one = _node_context("node-1")
    first = adapter.claim_due(
        **node_one,
        limit=2,
        observed_at=NOW,
    )
    node_two = _node_context("node-2")
    second = adapter.claim_due(
        **node_two,
        limit=2,
        observed_at=NOW,
    )

    assert [claim.claim_binding.authorization_digest for claim in first] == [
        _digest("authorization-a"),
        _digest("authorization-b"),
    ]
    assert [claim.claim_binding.node_id for claim in first] == ["node-1", "node-1"]
    assert second[0].claim_binding.node_id == "node-2"
    assert all(
        context.node_profile_digest == NODE_PROFILE_DIGEST
        and context.deployment_catalog_digest == CATALOG_DIGEST
        and context.runtime_protocol_version == "1"
        and context.interpreter_profile_digests
        == frozenset({INTERPRETER_PROFILE_DIGEST})
        for context in backend.claim_contexts
    )
    assert len(set(backend.connection_ids)) == 2
    assert all(uow.committed for uow in backend.uows)


def _claim_one(
    adapter: PostgresRuntimeNodeAdapter,
    *,
    node_id: str = "node-1",
) -> tuple[RuntimeClaim, ControlPlaneScope]:
    context = _node_context(node_id)
    claim = adapter.claim_due(
        **context,
        limit=1,
        observed_at=NOW,
    )[0]
    return claim, context["control_scope"]


def _started_claim(
    backend: _Backend,
) -> tuple[PostgresRuntimeNodeAdapter, RuntimeClaim, ControlPlaneScope]:
    adapter = _adapter(backend)
    claim, scope = _claim_one(adapter)
    renewed = adapter.heartbeat(
        control_scope=scope,
        claim=claim,
        expected_revision=claim.work_item_revision,
        new_expiry=NOW + timedelta(seconds=90),
    )
    started = adapter.begin_in_flight(
        control_scope=scope,
        claim=renewed,
        expected_revision=renewed.work_item_revision,
        started_at=NOW + timedelta(seconds=1),
    )
    live = adapter.heartbeat(
        control_scope=scope,
        claim=started,
        expected_revision=started.work_item_revision,
        new_expiry=NOW + timedelta(seconds=120),
    )
    return adapter, live, scope


@pytest.mark.parametrize(
    ("outcome", "kind"),
    [
        (
            InterpreterOutcome.succeeded(
                _digest("result"),
                receipt_ref=f"receipt:sha256:{_digest('receipt')}",
            ),
            EffectTerminalKind.SUCCEEDED,
        ),
        (InterpreterOutcome.failed("PROVIDER_REJECTED"), EffectTerminalKind.FAILED),
        (
            InterpreterOutcome.outcome_unknown("READBACK_REQUIRED"),
            EffectTerminalKind.OUTCOME_UNKNOWN,
        ),
    ],
)
def test_start_heartbeat_and_terminal_mapping_use_fresh_uows(
    outcome: InterpreterOutcome, kind: EffectTerminalKind
) -> None:
    backend = _Backend(
        (_Pending(_assignment("work-terminal"), _digest("authorization")),)
    )
    adapter, claim, scope = _started_claim(backend)

    adapter.commit_outcome(
        control_scope=scope,
        claim=claim,
        outcome=outcome,
        expected_revision=claim.work_item_revision,
        observed_at=NOW + timedelta(seconds=2),
    )

    terminal = backend.terminals[-1]
    assert terminal.kind is kind
    assert terminal.claimed.expected_work_revision == claim.work_item_revision
    assert terminal.authority_digest == claim.claim_binding.authorization_digest
    if kind is EffectTerminalKind.SUCCEEDED:
        assert terminal.output_digest == _digest("result")
        assert terminal.receipt_digest == _digest("receipt")
    elif kind is EffectTerminalKind.FAILED:
        assert terminal.failure_ref == (
            f"project-value:runtime-failure:{claim.claim_binding.attempt_id}"
        )
        assert terminal.failure_digest == canonical_digest(
            {
                "assignment_digest": claim.assignment.assignment_digest,
                "attempt_id": claim.claim_binding.attempt_id,
                "failure_code": "PROVIDER_REJECTED",
            }
        )
    assert len(backend.connection_ids) == 5
    assert len(set(backend.connection_ids)) == 5
    assert all(uow.committed for uow in backend.uows)


def test_heartbeat_revision_loss_is_lease_loss_and_rolls_back_uow() -> None:
    backend = _Backend(
        (_Pending(_assignment("work-lease-loss"), _digest("authorization")),)
    )
    adapter = _adapter(backend)
    claim, scope = _claim_one(adapter)
    backend.fail_heartbeat = True

    with pytest.raises(LeaseLost, match="heartbeat lost"):
        adapter.heartbeat(
            control_scope=scope,
            claim=claim,
            expected_revision=claim.work_item_revision,
            new_expiry=NOW + timedelta(seconds=90),
        )

    assert backend.uows[-1].committed is False
    assert backend.uows[-1].rolled_back is True


def test_started_claim_expiry_fails_before_terminal_uow_and_keeps_recovery_path() -> (
    None
):
    backend = _Backend(
        (_Pending(_assignment("work-expiry"), _digest("authorization")),)
    )
    adapter = _adapter(backend)
    claim, scope = _claim_one(adapter)
    started = adapter.begin_in_flight(
        control_scope=scope,
        claim=claim,
        expected_revision=claim.work_item_revision,
        started_at=NOW + timedelta(seconds=1),
    )
    uow_count = len(backend.uows)

    with pytest.raises(LeaseLost, match="claim lease has expired"):
        adapter.commit_outcome(
            control_scope=scope,
            claim=started,
            outcome=InterpreterOutcome.outcome_unknown("LEASE_EXPIRY_RECONCILE"),
            expected_revision=started.work_item_revision,
            observed_at=NOW + timedelta(seconds=46),
        )

    assert len(backend.uows) == uow_count
    assert backend.terminals == []


def test_reconcile_commit_dispatches_without_in_flight_cache_or_reservation() -> None:
    target_attempt_id = _digest("original-target-attempt")
    backend = _Backend(
        (
            _Pending(
                _reconciliation_assignment(
                    "work-reconcile", target_attempt_id=target_attempt_id
                ),
                _digest("authorization"),
            ),
        )
    )
    adapter = _adapter(backend)
    claim, scope = _claim_one(adapter)
    assert claim.claim_binding.execution_reservation_ref is None
    renewed = adapter.heartbeat(
        control_scope=scope,
        claim=claim,
        expected_revision=claim.work_item_revision,
        new_expiry=NOW + timedelta(seconds=90),
    )
    readback = AuthoritativeEffectReadback(
        attempt_id=target_attempt_id,
        disposition=EffectDisposition.SUCCEEDED,
        provider_locator="provider-receipt:fixture",
        receipt_digest=_digest("receipt"),
        observation_digest=_digest("observation"),
    )
    outcome = ReconciliationHandlerOutcome(
        result=ReconciliationResult(
            state=ReconciliationState.RESOLVED,
            attempt_id=target_attempt_id,
            disposition=EffectDisposition.SUCCEEDED,
            readback=readback,
        ),
        output_digest=_digest("adopted-output"),
        receipt_ref="receipt:fixture",
    )

    adapter.commit_outcome(
        control_scope=scope,
        claim=renewed,
        outcome=outcome,
        expected_revision=renewed.work_item_revision,
        observed_at=NOW + timedelta(seconds=2),
    )

    assert backend.terminals == []
    assert len(backend.reconciliation_adoptions) == 1
    adoption = backend.reconciliation_adoptions[0]
    assert adoption["claim"] == renewed
    assert adoption["outcome"] == outcome
    assert adoption["actor_id"] == scope.system_actor_id
    assert len(backend.uows) == 3
    assert all(uow.committed for uow in backend.uows)
