from __future__ import annotations

import hashlib
from collections import deque
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

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
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import (
    ClaimRunState,
    DeploymentBinding,
    ExactHandlerMismatch,
    InterpreterOutcome,
    LeaseLost,
    NodeIdentity,
    RuntimeClaim,
    RuntimeExecutionContext,
    RuntimeHandler,
    RuntimeNode,
    RuntimeNodeProfile,
    RuntimeNodeProtocol,
    RuntimeNodeState,
)
from app.successor_runtime.runtime.ports import (
    RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
    ControlPlaneScope,
)
from app.successor_runtime.runtime.reconciliation import (
    AuthoritativeEffectReadback,
    ReconciliationHandlerOutcome,
    ReconciliationResult,
    ReconciliationState,
)
from app.successor_runtime.runtime.transitions import EffectDisposition

NOW = datetime(2030, 1, 1, tzinfo=UTC)
NODE_PROFILE_DIGEST = hashlib.sha256(b"node-profile").hexdigest()
CATALOG_DIGEST = hashlib.sha256(b"deployment-catalog").hexdigest()
INTERPRETER_PROFILE_DIGEST = hashlib.sha256(b"interpreter-profile").hexdigest()
AUTHORITY_DIGEST = hashlib.sha256(b"authority").hexdigest()


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _assignment(work_item_id: str) -> RuntimeAssignment:
    operation_digest = _digest("operation-contract")
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
        input_closure_digest=_digest("input-closure"),
        queue_eligibility_digest=_digest("queue-eligibility"),
        resource_policy_epoch=3,
        claim_authority_epoch=4,
        claim_policy_digest=_digest("claim-policy"),
        expected_step_revision=0,
        trace_id=f"trace-{work_item_id}",
    )


def _reconciliation_assignment(
    work_item_id: str,
    *,
    target_attempt_id: str,
) -> RuntimeAssignment:
    operation_digest = _digest("operation-contract")
    recovery = RecoveryBinding.from_content(
        recovery_handler_id="readback-only-reconciler",
        recovery_handler_version="1",
        interpreter_profile_digest=INTERPRETER_PROFILE_DIGEST,
        authoritative_readback_profile_ref="authoritative-readback:fixture",
    )
    return RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id=work_item_id,
        assignment_kind=AssignmentKind.RECONCILE,
        project_key="project-1",
        run_id=f"run-{work_item_id}",
        step_id=f"step-{work_item_id}",
        capability_id="capability-1",
        operation_contract_ref=OperationContractRef(
            kind="fixture.operation.v1",
            contract_version="1.0.0",
            contract_digest=operation_digest,
        ),
        operation_contract_digest=operation_digest,
        handler_binding_kind=HandlerBindingKind.RECOVERY,
        handler_binding_ref=f"handler-binding:sha256:{recovery.binding_digest}",
        handler_binding_digest=recovery.binding_digest,
        handler_binding=recovery,
        program_digest=_digest("program"),
        plan_digest=_digest("plan"),
        deployment_catalog_digest=CATALOG_DIGEST,
        execution_epoch=1,
        incarnation="run-incarnation-1",
        input_closure_digest=_digest("input-closure"),
        queue_eligibility_digest=_digest("queue-eligibility"),
        resource_policy_epoch=3,
        claim_authority_epoch=4,
        claim_policy_digest=_digest("claim-policy"),
        expected_step_revision=0,
        reconciliation_attempt_id=target_attempt_id,
        trace_id=f"trace-{work_item_id}",
    )


class FixedClock:
    def now(self) -> datetime:
        return NOW


@dataclass(frozen=True, slots=True)
class PendingClaim:
    assignment: RuntimeAssignment
    effect_disposition: EffectDisposition = EffectDisposition.NOT_STARTED
    revision: int = 0


class FakeClaimBatch:
    def __init__(self, pending: tuple[PendingClaim, ...]) -> None:
        self.pending = deque(pending)
        self.claim_calls: list[str] = []
        self.heartbeats: list[tuple[str, int]] = []
        self.fail_heartbeat_number: int | None = None

    def claim_due(
        self,
        *,
        control_scope: ControlPlaneScope,
        node: NodeIdentity,
        profile: RuntimeNodeProfile,
        deployment: DeploymentBinding,
        protocol: RuntimeNodeProtocol,
        limit: int,
        observed_at: datetime,
    ) -> tuple[RuntimeClaim, ...]:
        del deployment, protocol
        control_scope.require_permission(RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION)
        self.claim_calls.append(node.node_id)
        claimed: list[RuntimeClaim] = []
        while self.pending and len(claimed) < limit:
            pending = self.pending.popleft()
            assignment = pending.assignment
            claim_binding = ClaimBinding.bind(
                assignment,
                authorization_digest=AUTHORITY_DIGEST,
                lease_token=f"lease-{assignment.work_item_id}-{node.node_id}",
                lease_expires_at=observed_at + timedelta(seconds=45),
                node_id=node.node_id,
                node_profile_digest=profile.profile_digest,
                authority_digest=AUTHORITY_DIGEST,
                interpreter_profile_digest=INTERPRETER_PROFILE_DIGEST,
                execution_reservation_ref=f"reservation:{assignment.work_item_id}",
                execution_reservation_digest=_digest(
                    f"reservation:{assignment.work_item_id}"
                ),
            )
            claimed.append(
                RuntimeClaim(
                    assignment=assignment,
                    claim_binding=claim_binding,
                    work_item_revision=pending.revision,
                    effect_disposition=pending.effect_disposition,
                )
            )
        return tuple(claimed)

    def heartbeat(
        self,
        *,
        control_scope: ControlPlaneScope,
        claim: RuntimeClaim,
        expected_revision: int,
        new_expiry: datetime,
    ) -> RuntimeClaim:
        control_scope.require_permission(RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION)
        assert expected_revision == claim.work_item_revision
        self.heartbeats.append((claim.assignment.work_item_id, expected_revision))
        if self.fail_heartbeat_number == len(self.heartbeats):
            raise LeaseLost("simulated stale lease")
        old = claim.claim_binding
        renewed = ClaimBinding.bind(
            claim.assignment,
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
        return replace(
            claim,
            claim_binding=renewed,
            work_item_revision=expected_revision + 1,
        )


class DeterministicSimulationInterpreter:
    """Deterministic no-I/O interpreter explicitly used only as simulation."""

    def __init__(
        self,
        handler_binding_digest: str,
        outcomes: dict[str, InterpreterOutcome],
        *,
        interpreter_profile_digest: str | None = INTERPRETER_PROFILE_DIGEST,
    ) -> None:
        self.handler_binding_digest = handler_binding_digest
        self.interpreter_profile_digest = interpreter_profile_digest
        self.outcomes = outcomes
        self.executions: list[str] = []

    def execute(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> InterpreterOutcome:
        assert claim.assignment_digest == assignment.assignment_digest
        assert context.node.node_id == claim.node_id
        self.executions.append(assignment.work_item_id)
        return self.outcomes[assignment.work_item_id]


class DeterministicReconciliationHandler:
    def __init__(
        self,
        handler_binding_digest: str,
        outcomes: dict[str, ReconciliationHandlerOutcome | InterpreterOutcome],
        *,
        interpreter_profile_digest: str | None = INTERPRETER_PROFILE_DIGEST,
    ) -> None:
        self.handler_binding_digest = handler_binding_digest
        self.interpreter_profile_digest = interpreter_profile_digest
        self.outcomes = outcomes
        self.executions: list[str] = []

    def execute(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> ReconciliationHandlerOutcome | InterpreterOutcome:
        assert claim.assignment_digest == assignment.assignment_digest
        assert context.node.node_id == claim.node_id
        self.executions.append(assignment.work_item_id)
        return self.outcomes[assignment.work_item_id]


class ExactResolver:
    def __init__(self, handler: RuntimeHandler) -> None:
        self.handler = handler
        self.requests: list[str] = []

    def resolve_exact(
        self,
        *,
        assignment: RuntimeAssignment,
        handler_binding_digest: str,
    ) -> RuntimeHandler:
        if handler_binding_digest != assignment.handler_binding_digest:
            raise ExactHandlerMismatch(
                "resolver request is not the exact assignment binding"
            )
        self.requests.append(handler_binding_digest)
        return self.handler


class FakeOutcomeCommitter:
    def __init__(self) -> None:
        self.started: list[tuple[str, int]] = []
        self.committed: list[
            tuple[
                RuntimeClaim,
                InterpreterOutcome | ReconciliationHandlerOutcome,
                int,
            ]
        ] = []

    def begin_in_flight(
        self,
        *,
        control_scope: ControlPlaneScope,
        claim: RuntimeClaim,
        expected_revision: int,
        started_at: datetime,
    ) -> RuntimeClaim:
        del started_at
        control_scope.require_permission(RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION)
        assert expected_revision == claim.work_item_revision
        self.started.append((claim.assignment.work_item_id, expected_revision))
        return replace(
            claim,
            work_item_revision=expected_revision + 1,
            effect_disposition=EffectDisposition.IN_FLIGHT,
        )

    def commit_outcome(
        self,
        *,
        control_scope: ControlPlaneScope,
        claim: RuntimeClaim,
        outcome: InterpreterOutcome | ReconciliationHandlerOutcome,
        expected_revision: int,
        observed_at: datetime,
    ) -> None:
        del observed_at
        control_scope.require_permission(RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION)
        assert expected_revision == claim.work_item_revision
        self.committed.append((claim, outcome, expected_revision))


class CurrentGuard:
    def __init__(self) -> None:
        self.cancellation_checks: list[str] = []
        self.authority_checks: list[tuple[str, str, int]] = []

    def require_not_cancelled(
        self, *, claim: RuntimeClaim, observed_at: datetime
    ) -> None:
        del observed_at
        self.cancellation_checks.append(claim.assignment.work_item_id)

    def require_current_authority(
        self,
        *,
        claim: RuntimeClaim,
        expected_authority_digest: str,
        expected_authority_epoch: int,
        observed_at: datetime,
    ) -> None:
        del observed_at
        assert expected_authority_digest == claim.claim_binding.authority_digest
        assert expected_authority_epoch == claim.assignment.claim_authority_epoch
        self.authority_checks.append(
            (
                claim.assignment.work_item_id,
                expected_authority_digest,
                expected_authority_epoch,
            )
        )


class StaleAuthorityGuard(CurrentGuard):
    def require_current_authority(
        self,
        *,
        claim: RuntimeClaim,
        expected_authority_digest: str,
        expected_authority_epoch: int,
        observed_at: datetime,
    ) -> None:
        super().require_current_authority(
            claim=claim,
            expected_authority_digest=expected_authority_digest,
            expected_authority_epoch=expected_authority_epoch,
            observed_at=observed_at,
        )
        raise RuntimeError("authority stale before effect")


def _node(
    node_id: str,
    claims: FakeClaimBatch,
    handler: RuntimeHandler,
    outcomes: FakeOutcomeCommitter,
    *,
    state: RuntimeNodeState = RuntimeNodeState.ACTIVE,
    guard: CurrentGuard | None = None,
    supported_assignment_kinds: frozenset[AssignmentKind] = frozenset(
        {AssignmentKind.INTERPRET}
    ),
) -> RuntimeNode:
    return RuntimeNode(
        identity=NodeIdentity(
            node_id=node_id,
            incarnation=f"{node_id}-incarnation",
            started_at=NOW - timedelta(minutes=1),
            state=state,
        ),
        profile=RuntimeNodeProfile(
            profile_digest=NODE_PROFILE_DIGEST,
            supported_assignment_kinds=supported_assignment_kinds,
            interpreter_profile_digests=frozenset({INTERPRETER_PROFILE_DIGEST}),
        ),
        deployment=DeploymentBinding(
            catalog_digest=CATALOG_DIGEST,
            node_profile_digest=NODE_PROFILE_DIGEST,
            runtime_protocol_version="1",
        ),
        protocol=RuntimeNodeProtocol(version="1", claim_batch_size=32),
        control_scope=ControlPlaneScope(
            system_actor_id=node_id,
            permission=RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
            authority_epoch=4,
        ),
        claims=claims,
        interpreters=ExactResolver(handler),
        outcomes=outcomes,
        cancellation=guard or CurrentGuard(),
        clock=FixedClock(),
    )


def test_two_nodes_use_one_interface_and_only_one_claims_shared_work() -> None:
    assignment = _assignment("work-1")
    queue = FakeClaimBatch((PendingClaim(assignment),))
    handler = DeterministicSimulationInterpreter(
        assignment.handler_binding_digest,
        {"work-1": InterpreterOutcome.succeeded(_digest("result-1"))},
    )
    commits = FakeOutcomeCommitter()
    node_one_guard = CurrentGuard()
    node_one = _node("node-1", queue, handler, commits, guard=node_one_guard)
    node_two = _node("node-2", queue, handler, commits)

    first = node_one.run_once()
    second = node_two.run_once()

    assert type(node_one) is type(node_two) is RuntimeNode
    assert first.claimed == 1
    assert second.claimed == 0
    assert handler.executions == ["work-1"]
    assert [outcome.disposition for _, outcome, _ in commits.committed] == [
        EffectDisposition.SUCCEEDED
    ]
    assert queue.claim_calls == ["node-1", "node-2"]
    assert node_one_guard.cancellation_checks == ["work-1", "work-1"]
    assert len(node_one_guard.authority_checks) == 2


def test_reconcile_uses_typed_readback_outcome_without_effect_lifecycle() -> None:
    target_attempt_id = _digest("original-target-attempt")
    assignment = _reconciliation_assignment(
        "work-reconcile",
        target_attempt_id=target_attempt_id,
    )
    queue = FakeClaimBatch((PendingClaim(assignment),))
    readback = AuthoritativeEffectReadback(
        attempt_id=target_attempt_id,
        disposition=EffectDisposition.SUCCEEDED,
        provider_locator="provider-receipt:fixture",
        receipt_digest=_digest("provider-receipt"),
        observation_digest=_digest("authoritative-observation"),
    )
    handler_outcome = ReconciliationHandlerOutcome(
        result=ReconciliationResult(
            state=ReconciliationState.RESOLVED,
            attempt_id=target_attempt_id,
            disposition=EffectDisposition.SUCCEEDED,
            readback=readback,
        ),
        output_digest=_digest("recovered-output"),
        receipt_ref="receipt:recovered-output",
    )
    handler = DeterministicReconciliationHandler(
        assignment.handler_binding_digest,
        {assignment.work_item_id: handler_outcome},
    )
    commits = FakeOutcomeCommitter()
    guard = CurrentGuard()

    report = _node(
        "node-reconcile",
        queue,
        handler,
        commits,
        guard=guard,
        supported_assignment_kinds=frozenset({AssignmentKind.RECONCILE}),
    ).run_once()

    assert report.results[0].state is ClaimRunState.COMMITTED
    assert report.results[0].disposition is EffectDisposition.SUCCEEDED
    assert report.results[0].executed is False
    assert handler.executions == [assignment.work_item_id]
    assert commits.started == []
    assert queue.heartbeats == [
        (assignment.work_item_id, 0),
        (assignment.work_item_id, 1),
    ]
    assert len(commits.committed) == 1
    committed_claim, committed_outcome, committed_revision = commits.committed[0]
    assert committed_claim.assignment.reconciliation_attempt_id == target_attempt_id
    assert isinstance(committed_outcome, ReconciliationHandlerOutcome)
    assert committed_outcome.result.attempt_id == target_attempt_id
    assert committed_revision == 2
    assert guard.cancellation_checks == [assignment.work_item_id]
    assert len(guard.authority_checks) == 1


def test_reconcile_rejects_ordinary_outcome_without_claiming_original_failure() -> None:
    target_attempt_id = _digest("still-unknown-target-attempt")
    assignment = _reconciliation_assignment(
        "work-reconcile-wrong-outcome",
        target_attempt_id=target_attempt_id,
    )
    queue = FakeClaimBatch((PendingClaim(assignment),))
    handler = DeterministicReconciliationHandler(
        assignment.handler_binding_digest,
        {
            assignment.work_item_id: InterpreterOutcome.failed(
                "NOT_AN_AUTHORITATIVE_READBACK"
            )
        },
    )
    commits = FakeOutcomeCommitter()

    report = _node(
        "node-reconcile",
        queue,
        handler,
        commits,
        supported_assignment_kinds=frozenset({AssignmentKind.RECONCILE}),
    ).run_once()

    result = report.results[0]
    assert result.state is ClaimRunState.REJECTED
    assert result.disposition is EffectDisposition.OUTCOME_UNKNOWN
    assert result.executed is False
    assert result.committed is False
    assert "NON-RECONCILIATIONHANDLEROUTCOME" in (result.failure_code or "")
    assert handler.executions == [assignment.work_item_id]
    assert commits.started == []
    assert commits.committed == []
    assert queue.heartbeats == [(assignment.work_item_id, 0)]


def test_missing_exact_installation_stays_non_terminal_before_effect() -> None:
    assignment = _assignment("work-wrong-handler")
    queue = FakeClaimBatch((PendingClaim(assignment),))
    wrong = DeterministicSimulationInterpreter(
        _digest("wrong-handler"),
        {
            assignment.work_item_id: InterpreterOutcome.succeeded(
                _digest("impossible-result")
            )
        },
    )
    commits = FakeOutcomeCommitter()

    report = _node("node-1", queue, wrong, commits).run_once()

    assert wrong.executions == []
    assert len(report.results) == 1
    result = report.results[0]
    assert result.state is ClaimRunState.REJECTED
    assert result.disposition is EffectDisposition.NOT_STARTED
    assert result.executed is False
    assert result.committed is False
    assert commits.started == []
    assert commits.committed == []
    assert "DIFFERENT_HANDLER_DIGEST" in (result.failure_code or "")


def test_cancel_authority_guard_is_rechecked_before_effect() -> None:
    assignment = _assignment("work-stale-authority")
    queue = FakeClaimBatch((PendingClaim(assignment),))
    handler = DeterministicSimulationInterpreter(
        assignment.handler_binding_digest,
        {assignment.work_item_id: InterpreterOutcome.succeeded(_digest("result"))},
    )
    commits = FakeOutcomeCommitter()
    guard = StaleAuthorityGuard()

    report = _node("node-1", queue, handler, commits, guard=guard).run_once()

    result = report.results[0]
    assert result.disposition is EffectDisposition.FAILED
    assert result.executed is False
    assert result.committed is True
    assert handler.executions == []
    assert commits.started == []
    assert len(guard.cancellation_checks) == 1
    assert len(guard.authority_checks) == 1
    assert "AUTHORITY_STALE_BEFORE_EFFECT" in (result.failure_code or "")


def test_stale_lease_before_effect_prohibits_execution_and_commit() -> None:
    assignment = _assignment("work-stale-before")
    queue = FakeClaimBatch((PendingClaim(assignment),))
    queue.fail_heartbeat_number = 1
    handler = DeterministicSimulationInterpreter(
        assignment.handler_binding_digest,
        {assignment.work_item_id: InterpreterOutcome.succeeded(_digest("result"))},
    )
    commits = FakeOutcomeCommitter()

    report = _node("node-1", queue, handler, commits).run_once()

    result = report.results[0]
    assert result.state is ClaimRunState.LEASE_LOST
    assert result.executed is False
    assert result.committed is False
    assert handler.executions == []
    assert commits.started == []
    assert commits.committed == []


def test_stale_lease_after_effect_prohibits_commit_and_reports_unknown() -> None:
    assignment = _assignment("work-stale-after")
    queue = FakeClaimBatch((PendingClaim(assignment),))
    queue.fail_heartbeat_number = 2
    handler = DeterministicSimulationInterpreter(
        assignment.handler_binding_digest,
        {assignment.work_item_id: InterpreterOutcome.succeeded(_digest("result"))},
    )
    commits = FakeOutcomeCommitter()

    report = _node("node-1", queue, handler, commits).run_once()

    result = report.results[0]
    assert result.state is ClaimRunState.LEASE_LOST
    assert result.disposition is EffectDisposition.OUTCOME_UNKNOWN
    assert result.executed is True
    assert result.committed is False
    assert handler.executions == [assignment.work_item_id]
    assert commits.started == [(assignment.work_item_id, 1)]
    assert commits.committed == []
    assert queue.heartbeats == [
        (assignment.work_item_id, 0),
        (assignment.work_item_id, 2),
    ]


def test_outcome_unknown_is_committed_once_and_never_redispatched() -> None:
    assignment = _assignment("work-unknown")
    queue = FakeClaimBatch((PendingClaim(assignment),))
    handler = DeterministicSimulationInterpreter(
        assignment.handler_binding_digest,
        {
            assignment.work_item_id: InterpreterOutcome.outcome_unknown(
                "authoritative-readback:fixture"
            )
        },
    )
    commits = FakeOutcomeCommitter()
    node = _node("node-1", queue, handler, commits)

    first = node.run_once()
    queue.pending.append(
        PendingClaim(
            assignment,
            effect_disposition=EffectDisposition.OUTCOME_UNKNOWN,
            revision=4,
        )
    )
    second = node.run_once()

    assert first.results[0].disposition is EffectDisposition.OUTCOME_UNKNOWN
    assert first.results[0].committed is True
    assert second.results[0].state is ClaimRunState.RECOVERY_REQUIRED
    assert second.results[0].executed is False
    assert second.results[0].committed is False
    assert handler.executions == [assignment.work_item_id]
    assert len(commits.committed) == 1


def test_one_claim_failure_does_not_fabricate_or_suppress_other_outcomes() -> None:
    failed = _assignment("work-failed")
    succeeded = _assignment("work-succeeded")
    queue = FakeClaimBatch((PendingClaim(failed), PendingClaim(succeeded)))
    handler = DeterministicSimulationInterpreter(
        failed.handler_binding_digest,
        {
            failed.work_item_id: InterpreterOutcome.failed("FIXTURE_FAILURE"),
            succeeded.work_item_id: InterpreterOutcome.succeeded(
                _digest("successful-result")
            ),
        },
    )
    commits = FakeOutcomeCommitter()

    report = _node("node-1", queue, handler, commits).run_once()

    assert [(item.work_item_id, item.disposition) for item in report.results] == [
        (failed.work_item_id, EffectDisposition.FAILED),
        (succeeded.work_item_id, EffectDisposition.SUCCEEDED),
    ]
    assert [outcome.disposition for _, outcome, _ in commits.committed] == [
        EffectDisposition.FAILED,
        EffectDisposition.SUCCEEDED,
    ]


def test_draining_node_does_not_claim_new_work() -> None:
    assignment = _assignment("work-draining")
    queue = FakeClaimBatch((PendingClaim(assignment),))
    handler = DeterministicSimulationInterpreter(
        assignment.handler_binding_digest,
        {assignment.work_item_id: InterpreterOutcome.succeeded(_digest("result"))},
    )
    commits = FakeOutcomeCommitter()

    report = _node(
        "node-draining",
        queue,
        handler,
        commits,
        state=RuntimeNodeState.DRAINING,
    ).run_once()

    assert report.skipped_new_claims is True
    assert report.claimed == 0
    assert queue.claim_calls == []
    assert handler.executions == []
    assert commits.committed == []


def test_resolver_protocol_rejects_arbitrary_handler_selection() -> None:
    assignment = _assignment("work-exact")
    exact = DeterministicSimulationInterpreter(
        assignment.handler_binding_digest,
        {assignment.work_item_id: InterpreterOutcome.succeeded(_digest("result"))},
    )
    resolver = ExactResolver(exact)

    resolved = resolver.resolve_exact(
        assignment=assignment,
        handler_binding_digest=assignment.handler_binding_digest,
    )

    assert resolved is exact
    try:
        resolver.resolve_exact(
            assignment=assignment,
            handler_binding_digest=_digest("arbitrary-mutable-registry-key"),
        )
    except ExactHandlerMismatch:
        pass
    else:
        raise ExactHandlerMismatch("resolver accepted a non-exact handler request")
