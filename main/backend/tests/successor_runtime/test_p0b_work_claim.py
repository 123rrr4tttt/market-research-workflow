from __future__ import annotations

import hashlib
import random
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from app.successor_runtime.language.object_contracts import (
    OperationContractRef,
    ReturnContract,
)
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompiledStepRole,
    HandlerBindingKind,
    InterpreterBinding,
    ReturnContractBinding,
    RuntimeAssignment,
    canonical_digest,
)
from app.successor_runtime.runtime.claims import ClaimBinding, derive_attempt_id
from app.successor_runtime.runtime.ports import ControlPlaneScope
from app.successor_runtime.runtime.qualification import (
    AuthoritySourceBinding,
    QualificationFailure,
    QualifiedPlan,
    StepAuthorizationBinding,
)
from app.successor_runtime.runtime.resources import (
    ExecutionReservation,
    FairClaimCandidate,
    FairSharePolicy,
    QueueEligibility,
    ResourceClass,
    ResourcePolicySnapshot,
    ResourceUsage,
    assignment_requires_reservation,
    effective_priority,
    evaluate_reservation,
    select_fair_claims,
    starvation_bound_seconds,
)
from app.successor_runtime.substrate.postgres.resources import (
    ResourceReservationRepository,
    StaleLeaseToken,
    _lock_policy_statement,
)
from app.successor_runtime.substrate.postgres.work_items import (
    ClaimBindingMismatch,
    ClaimConflict,
    NodeClaimContext,
    WorkItemClaimRepository,
    due_claim_statement,
)

PROPERTY_SEED = 0x50B2026
PROPERTY_CASES = 300


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _candidate(
    item: str,
    project: str,
    capability: str,
    *,
    priority: int,
    seq: int,
    now: datetime,
    age: int = 0,
    fairness_key: str | None = None,
) -> FairClaimCandidate:
    return FairClaimCandidate(
        work_item_id=item,
        project_key=project,
        capability_id=capability,
        fairness_key=fairness_key or project,
        declared_priority=priority,
        enqueue_seq=seq,
        enqueued_at=now - timedelta(seconds=age),
        due_at=now,
    )


def test_qualification_is_non_exclusive_and_only_effect_claims_reserve() -> None:
    assert not assignment_requires_reservation(AssignmentKind.QUALIFY)
    assert assignment_requires_reservation(AssignmentKind.INTERPRET)
    assert assignment_requires_reservation(AssignmentKind.VERIFY_ADMIT)
    assert not assignment_requires_reservation(AssignmentKind.RECONCILE)


def test_resource_limit_is_an_observation_and_does_not_create_reservation() -> None:
    eligibility = QueueEligibility(
        project_key="project-a",
        capability_id="cap-a",
        resource_class=ResourceClass.LLM_CALL,
        units=2,
        policy_epoch=4,
        policy_digest=_digest("policy"),
        concurrency_key="run:1:step:1",
        provider_key="provider-a",
    )
    policy = ResourcePolicySnapshot(
        project_key="project-a",
        capability_id="cap-a",
        resource_class=ResourceClass.LLM_CALL,
        policy_epoch=4,
        policy_digest=_digest("policy"),
        max_project_active=2,
        max_capability_active=2,
        max_resource_active=2,
        max_units=2,
        max_provider_active=1,
    )
    decision = evaluate_reservation(
        eligibility,
        policy,
        ResourceUsage(active_units=1),
    )
    assert not decision.granted
    assert decision.reason == "RESOURCE_LIMIT:UNITS"


def test_execution_reservation_binds_attempt_policy_and_lease_token() -> None:
    eligibility = QueueEligibility(
        project_key="project-a",
        capability_id="cap-a",
        resource_class=ResourceClass.CPU_LIGHT,
        units=1,
        policy_epoch=2,
        policy_digest=_digest("policy"),
    )
    values = {
        "work_item_id": "work-1",
        "project_key": "project-a",
        "run_id": "run-1",
        "step_id": "step-1",
        "attempt_id": _digest("attempt"),
        "execution_epoch": 1,
        "eligibility": eligibility,
        "lease_token": "lease-1",
        "lease_expires_at": datetime(2030, 1, 1, tzinfo=UTC),
    }
    first = ExecutionReservation.create(**values)
    replay = ExecutionReservation.create(**values)
    stale = ExecutionReservation.create(**{**values, "lease_token": "lease-2"})
    assert first == replay
    assert first.reservation_id != stale.reservation_id
    assert first.policy_digest == eligibility.policy_digest


def test_effective_priority_is_monotone_bounded_and_replayable() -> None:
    rng = random.Random(PROPERTY_SEED)
    policy = FairSharePolicy(
        aging_quantum_seconds=3,
        aging_increment=2,
        max_aging_boost=120,
        max_declared_priority=100,
    )
    now = datetime(2030, 1, 1, tzinfo=UTC)
    for _ in range(PROPERTY_CASES):
        declared = rng.randint(0, policy.max_declared_priority)
        younger = rng.randint(0, 10_000)
        older = younger + rng.randint(0, 10_000)
        young_priority = effective_priority(
            declared, now - timedelta(seconds=younger), now, policy
        )
        old_priority = effective_priority(
            declared, now - timedelta(seconds=older), now, policy
        )
        assert declared <= young_priority <= old_priority
        assert old_priority <= declared + policy.max_aging_boost


def test_project_and_capability_fair_share_prevent_hot_project_monopoly() -> None:
    now = datetime(2030, 1, 1, tzinfo=UTC)
    policy = FairSharePolicy(project_quantum=1, capability_quantum=1)
    candidates = [
        _candidate(f"hot-{index}", "hot", "llm", priority=100, seq=index, now=now)
        for index in range(20)
    ]
    candidates.extend(
        (
            _candidate("cold-a", "cold-a", "read", priority=0, seq=30, now=now),
            _candidate("cold-b", "cold-b", "read", priority=0, seq=31, now=now),
        )
    )
    selected = select_fair_claims(
        candidates,
        now=now,
        limit=3,
        policy=policy,
    )
    assert {item.project_key for item in selected} == {"hot", "cold-a", "cold-b"}

    same_project = (
        _candidate("llm-1", "p", "llm", priority=100, seq=1, now=now),
        _candidate("llm-2", "p", "llm", priority=100, seq=2, now=now),
        _candidate("read-1", "p", "read", priority=0, seq=3, now=now),
    )
    selected = select_fair_claims(
        same_project,
        now=now,
        limit=2,
        policy=FairSharePolicy(project_quantum=2, capability_quantum=1),
    )
    assert {item.capability_id for item in selected} == {"llm", "read"}

    single_project_rounds = select_fair_claims(
        same_project,
        now=now,
        limit=2,
        policy=FairSharePolicy(project_quantum=1, capability_quantum=1),
    )
    assert [item.capability_id for item in single_project_rounds] == ["llm", "read"]

    first_capability = select_fair_claims(
        same_project,
        now=now,
        limit=1,
        policy=FairSharePolicy(project_quantum=1, capability_quantum=1),
        cursor=0,
    )
    next_capability = select_fair_claims(
        same_project,
        now=now,
        limit=1,
        policy=FairSharePolicy(project_quantum=1, capability_quantum=1),
        cursor=1,
    )
    assert first_capability[0].capability_id != next_capability[0].capability_id


def test_finite_backlog_starvation_bound_holds_in_seeded_simulation() -> None:
    rng = random.Random(PROPERTY_SEED)
    now = datetime(2030, 1, 1, tzinfo=UTC)
    policy = FairSharePolicy(
        aging_quantum_seconds=1,
        max_aging_boost=100,
        max_declared_priority=100,
        claim_cycle_seconds=1,
    )
    for case in range(60):
        project_count = rng.randint(2, 8)
        item_count = rng.randint(project_count, 50)
        claim_batch = rng.randint(1, min(8, project_count))
        pending = [
            _candidate(
                f"case-{case}-item-{index}",
                f"project-{index % project_count}",
                f"cap-{index % 3}",
                priority=rng.randint(0, 100),
                seq=index,
                now=now,
            )
            for index in range(item_count)
        ]
        capability_count = len({item.capability_id for item in pending})
        bound = starvation_bound_seconds(
            policy,
            eligible_item_count=item_count,
            project_count=project_count,
            capability_count=capability_count,
            claim_batch=claim_batch,
        )
        claimed_at: dict[str, int] = {}
        for cursor, elapsed in enumerate(range(bound + 1)):
            selected = select_fair_claims(
                pending,
                now=now + timedelta(seconds=elapsed),
                limit=claim_batch,
                policy=policy,
                cursor=cursor,
            )
            ids = {item.work_item_id for item in selected}
            for item_id in ids:
                claimed_at[item_id] = elapsed
            pending = [item for item in pending if item.work_item_id not in ids]
            if not pending:
                break
        assert len(claimed_at) == item_count, (
            f"seed={PROPERTY_SEED} case={case} pending={len(pending)} bound={bound}"
        )
        assert max(claimed_at.values()) <= bound


def test_starvation_bound_rejects_unbounded_or_zero_capacity_domain() -> None:
    with pytest.raises(ValueError, match="positive bounded"):
        starvation_bound_seconds(
            FairSharePolicy(),
            eligible_item_count=0,
            project_count=1,
            capability_count=1,
            claim_batch=1,
        )


def _postgres_sql(statement: object) -> str:
    return str(
        statement.compile(  # type: ignore[attr-defined]
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def test_due_claim_sql_compiles_to_fair_skip_locked_postgres_query() -> None:
    now = datetime(2030, 1, 1, tzinfo=UTC)
    context = NodeClaimContext(
        node_id="node-1",
        node_profile_digest=_digest("node-profile"),
        deployment_catalog_digest=_digest("catalog"),
        runtime_protocol_version="1",
        authority_snapshot_digest=_digest("authorization"),
        interpreter_profile_digests=frozenset({_digest("interpreter")}),
    )
    sql = _postgres_sql(
        due_claim_statement(
            context,
            now=now,
            limit=32,
            fairness=FairSharePolicy(project_quantum=2, capability_quantum=3),
            cursor=7,
        )
    ).upper()
    assert "FOR UPDATE OF RUNTIME_WORK_ITEMS SKIP LOCKED" in sql
    assert "CAPABILITY_KEYS" in sql and "PROJECT_KEYS" in sql
    assert "CAPABILITY_WAVE" in sql and "PROJECT_ITEM_TURN" in sql
    assert "ROTATED_CAPABILITY" in sql and "ROTATED_PROJECT" in sql
    assert "MOD(" in sql and "CAST(3 AS NUMERIC)" in sql
    assert "CAST(2 AS NUMERIC)" in sql
    assert sql.count("CLAIMED_WORK.STATE = 'CLAIMED'") >= 2
    assert "CLAIMED_WORK.CAPABILITY_ID" in sql
    assert "ELIGIBLE_DUE.PROJECT_ACTIVE AS PROJECT_ACTIVE" in sql
    assert "ELIGIBLE_DUE.CAPABILITY_ACTIVE AS CAPABILITY_ACTIVE" in sql
    assert "RUNTIME_WORK_ITEMS.AUTHORITY_DIGEST =" not in sql
    assert (
        "ORDER BY PROJECT_KEYS.PROJECT_ACTIVE, PROJECT_KEYS.PROJECT_KEY, "
        "PROJECT_KEYS.FAIRNESS_KEY" in sql
    )
    assert (
        "ORDER BY CAPABILITY_KEYS.CAPABILITY_ACTIVE, "
        "CAPABILITY_KEYS.CAPABILITY_ID" in sql
    )
    assert "EFFECTIVE_PRIORITY" in sql
    assert "DEADLINE_AT IS NULL" in sql
    assert "AUTHORITY_DIGEST" in sql
    assert "INTERPRETER_PROFILE_DIGEST" in sql


def test_resource_policy_sql_is_an_exact_row_lock() -> None:
    eligibility = QueueEligibility(
        project_key="project-a",
        capability_id="cap-a",
        resource_class=ResourceClass.CPU_LIGHT,
        units=1,
        policy_epoch=7,
        policy_digest=_digest("policy"),
    )
    sql = _postgres_sql(_lock_policy_statement(eligibility)).upper()
    assert sql.endswith("FOR UPDATE")
    for field in (
        "PROJECT_KEY",
        "CAPABILITY_ID",
        "RESOURCE_CLASS",
        "POLICY_EPOCH",
        "POLICY_DIGEST",
    ):
        assert field in sql


class _ZeroRows:
    rowcount = 0

    def mappings(self):
        return self

    def one_or_none(self):
        return None

    def all(self):
        return []


class _MappedResult(_ZeroRows):
    def __init__(self, row: dict[str, object], *, rowcount: int = 1) -> None:
        self.row = row
        self.rowcount = rowcount

    def one_or_none(self):
        return self.row


class _RecordingConnection:
    def __init__(self, results: list[object] | None = None) -> None:
        self.statements: list[object] = []
        self.results = list(results or [])

    def execute(self, statement: object) -> object:
        self.statements.append(statement)
        if self.results:
            return self.results.pop(0)
        return _ZeroRows()


def test_live_claim_rejects_lossy_queue_eligibility_reconstruction() -> None:
    exact = QueueEligibility(
        project_key="project-a",
        capability_id="cap-a",
        resource_class=ResourceClass.LLM_CALL,
        units=3,
        policy_epoch=7,
        policy_digest=_digest("policy"),
        concurrency_key="project-a:llm",
        provider_key="provider-a",
    )
    work = {
        "project_key": exact.project_key,
        "capability_id": exact.capability_id,
        "resource_class": exact.resource_class.value,
        "resource_units": exact.units,
        "resource_policy_epoch": exact.policy_epoch,
        "resource_policy_digest": exact.policy_digest,
        "queue_eligibility_digest": exact.eligibility_digest,
        "concurrency_key": exact.concurrency_key,
        "provider_key": exact.provider_key,
    }
    step = {
        "resource_class": exact.resource_class.value,
        "concurrency_key": exact.concurrency_key,
    }
    policy_row = {
        "resource_policy_id": "policy-7",
        "project_key": exact.project_key,
        "capability_id": exact.capability_id,
        "resource_class": exact.resource_class.value,
        "policy_epoch": exact.policy_epoch,
        "policy_digest": exact.policy_digest,
    }
    repository = WorkItemClaimRepository(
        _RecordingConnection([_MappedResult(policy_row)])  # type: ignore[arg-type]
    )
    observed, _policy = repository._eligibility(work, step)
    assert observed == exact
    assert observed.units == 3 and observed.provider_key == "provider-a"

    lossy = {**work, "resource_units": 1, "provider_key": None}
    with pytest.raises(ClaimBindingMismatch, match="eligibility digest drift"):
        WorkItemClaimRepository(_RecordingConnection())._eligibility(lossy, step)  # type: ignore[arg-type]


def test_fair_selector_enforces_project_and_capability_active_limits() -> None:
    now = datetime(2030, 1, 1, tzinfo=UTC)
    candidates = (
        _candidate("a-1", "project-a", "cap-a", priority=1, seq=1, now=now),
        _candidate("b-1", "project-b", "cap-a", priority=1, seq=2, now=now),
        _candidate("b-2", "project-b", "cap-b", priority=1, seq=3, now=now),
    )
    selected = select_fair_claims(
        candidates,
        now=now,
        limit=3,
        policy=FairSharePolicy(max_project_active=2, max_capability_active=1),
        active_by_project={"project-a": 2, "project-b": 0},
        active_by_capability={
            ("project-a", "cap-a"): 0,
            ("project-b", "cap-a"): 1,
            ("project-b", "cap-b"): 0,
        },
    )
    assert [item.work_item_id for item in selected] == ["b-2"]


def test_fair_selector_orders_active_counts_before_key_and_cursor_rotation() -> None:
    now = datetime(2030, 1, 1, tzinfo=UTC)
    candidates = (
        _candidate("a-idle-cap", "project-a", "cap-a", priority=1, seq=1, now=now),
        _candidate("b-busy-cap", "project-b", "cap-a", priority=100, seq=2, now=now),
        _candidate("b-idle-cap", "project-b", "cap-b", priority=0, seq=3, now=now),
    )
    policy = FairSharePolicy(
        project_quantum=1,
        capability_quantum=1,
        max_project_active=10,
        max_capability_active=10,
    )
    active_by_project = {"project-a": 2, "project-b": 0}
    active_by_capability = {
        ("project-a", "cap-a"): 0,
        ("project-b", "cap-a"): 1,
        ("project-b", "cap-b"): 0,
    }
    selected = select_fair_claims(
        candidates,
        now=now,
        limit=2,
        policy=policy,
        active_by_project=active_by_project,
        active_by_capability=active_by_capability,
        cursor=0,
    )
    assert [item.work_item_id for item in selected] == [
        "b-idle-cap",
        "a-idle-cap",
    ]

    rotated = select_fair_claims(
        candidates,
        now=now,
        limit=2,
        policy=policy,
        active_by_project=active_by_project,
        active_by_capability=active_by_capability,
        cursor=1,
    )
    assert [item.work_item_id for item in rotated] == [
        "a-idle-cap",
        "b-busy-cap",
    ]


def test_project_active_limit_cannot_be_bypassed_by_fairness_key_split() -> None:
    now = datetime(2030, 1, 1, tzinfo=UTC)
    candidates = (
        _candidate(
            "queue-a",
            "project-a",
            "cap-a",
            priority=1,
            seq=1,
            now=now,
            fairness_key="project-a:cap-a",
        ),
        _candidate(
            "queue-b",
            "project-a",
            "cap-b",
            priority=1,
            seq=2,
            now=now,
            fairness_key="project-a:cap-b",
        ),
    )
    selected = select_fair_claims(
        candidates,
        now=now,
        limit=2,
        policy=FairSharePolicy(max_project_active=1, max_capability_active=2),
        active_by_project={"project-a": 1},
    )
    assert selected == ()


def test_live_claim_binding_persists_exact_assignment_handler_and_reservation() -> None:
    now = datetime(2030, 1, 1, tzinfo=UTC)
    eligibility = QueueEligibility(
        project_key="project-a",
        capability_id="cap-a",
        resource_class=ResourceClass.CPU_LIGHT,
        units=2,
        policy_epoch=4,
        policy_digest=_digest("policy"),
        provider_key="provider-a",
    )
    operation_digest = _digest("operation")
    interpreter = InterpreterBinding.from_content(
        operation_contract_digest=operation_digest,
        interpreter_profile_digest=_digest("interpreter"),
        deployment_catalog_digest=_digest("catalog"),
        runtime_protocol_version="1",
        project_scope_digest=_digest("project-scope"),
        resource_policy_epoch=eligibility.policy_epoch,
        authority_requirement_digest=_digest("authority-requirement"),
    )
    return_binding = ReturnContractBinding.from_contract(
        "return:test.v1",
        ReturnContract(
            success_modes=("SUCCEEDED",),
            failure_modes=("FAILED",),
            admission_required=False,
        ),
    )
    assignment = RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id="work-1",
        assignment_kind=AssignmentKind.INTERPRET,
        project_key="project-a",
        run_id="run-1",
        step_id="step-1",
        step_role=CompiledStepRole.EFFECT,
        capability_id="cap-a",
        operation_contract_ref=OperationContractRef(
            kind="test.operation.v1",
            contract_version="1.0.0",
            contract_digest=operation_digest,
        ),
        operation_contract_digest=operation_digest,
        return_contract_binding=return_binding,
        handler_binding_kind=HandlerBindingKind.INTERPRETER,
        handler_binding_ref=(
            f"handler-binding:sha256:{interpreter.binding_digest}"
        ),
        handler_binding_digest=interpreter.binding_digest,
        handler_binding=interpreter,
        program_digest=_digest("program"),
        plan_digest=_digest("plan"),
        deployment_catalog_digest=_digest("catalog"),
        execution_epoch=2,
        incarnation="run-incarnation-1",
        input_refs=("value:1",),
        input_closure_digest=_digest("input"),
        queue_eligibility_digest=eligibility.eligibility_digest,
        resource_policy_epoch=eligibility.policy_epoch,
        claim_authority_epoch=5,
        claim_policy_digest=_digest("claim-policy"),
        expected_step_revision=0,
        trace_id="trace-1",
    )
    authorization_digest = _digest("authorization")
    attempt_id = derive_attempt_id(
        assignment,
        authorization_digest=authorization_digest,
        handler_realization_digest=assignment.handler_binding_digest,
    )
    reservation = ExecutionReservation.create(
        work_item_id="work-1",
        project_key="project-a",
        run_id="run-1",
        step_id="step-1",
        attempt_id=attempt_id,
        execution_epoch=2,
        eligibility=eligibility,
        lease_token="lease-1",
        lease_expires_at=now + timedelta(seconds=60),
    )
    context = NodeClaimContext(
        node_id="node-1",
        node_profile_digest=_digest("node-profile"),
        deployment_catalog_digest=_digest("catalog"),
        runtime_protocol_version="1",
        authority_snapshot_digest=_digest("authority"),
        interpreter_profile_digests=frozenset({_digest("interpreter")}),
    )
    claim = WorkItemClaimRepository._claim_binding(
        assignment,
        context=context,
        attempt_id=reservation.attempt_id,
        authorization_digest=authorization_digest,
        lease_token="lease-1",
        lease_expires_at=now + timedelta(seconds=45),
        reservation=reservation,
    )
    assert claim.assignment_digest == assignment.assignment_digest
    assert claim.handler_binding_digest == assignment.handler_binding_digest
    assert claim.execution_reservation_ref == reservation.reservation_id
    assert claim.execution_reservation_digest == reservation.reservation_digest
    assert ClaimBinding.model_validate(claim.model_dump(mode="json")) == claim


def test_submitted_run_cannot_claim_effect_before_plan_qualification() -> None:
    work = {
        "assignment_kind": AssignmentKind.INTERPRET.value,
        "program_digest": _digest("program"),
        "plan_digest": _digest("plan"),
        "qualification_digest": _digest("qualification"),
    }
    submitted = {
        "state": "SUBMITTED",
        "program_digest": _digest("program"),
        "plan_id": None,
        "plan_digest": None,
        "qualification_digest": None,
    }
    with pytest.raises(ClaimBindingMismatch, match="cannot claim run state SUBMITTED"):
        WorkItemClaimRepository._require_run_execution_binding(work, submitted)

    ready = {
        **submitted,
        "state": "READY",
        "plan_id": "plan-1",
        "plan_digest": _digest("plan"),
        "qualification_digest": _digest("qualification"),
    }
    WorkItemClaimRepository._require_run_execution_binding(work, ready)

    drifted = {**ready, "qualification_digest": _digest("other-qualification")}
    with pytest.raises(ClaimBindingMismatch, match="binding drift"):
        WorkItemClaimRepository._require_run_execution_binding(work, drifted)


def _closure_binding(
    step_id: str,
    *,
    operation_kind: str = "test.operation.v1",
    operation_digest: str | None = None,
) -> StepAuthorizationBinding:
    source = AuthoritySourceBinding(
        source_kind="PROJECT_SCOPE",
        source_ref="project-scope:project-a:3",
        source_digest=_digest("project-scope"),
        source_epoch=3,
    )
    return StepAuthorizationBinding.from_content(
        run_id="run-1",
        step_id=step_id,
        operation_kind=operation_kind,
        operation_contract_digest=operation_digest or _digest("operation-contract"),
        capability_id="cap-a",
        claim_owner="successor",
        claim_authority_epoch=2,
        claim_policy_digest=_digest("claim-policy"),
        payload_digest=_digest("payload"),
        actor_id="actor-a",
        project_key="project-a",
        project_registry_revision=3,
        project_scope_digest=_digest("project-scope"),
        interpreter_binding_digest=_digest("interpreter"),
        deployment_catalog_digest=_digest("catalog"),
        authority_source_bindings=(source,),
        grants_digest=_digest("grants"),
        approval_refs=(),
        resource_ceiling_digest=_digest("resource-ceiling"),
        resource_policy_epoch=4,
        queue_eligibility_digest=_digest("eligibility"),
        grant_epoch=5,
        expires_at=datetime(2031, 1, 1, tzinfo=UTC),
        canonical_base_revision=1,
        canonical_incarnation="canonical-incarnation-1",
    )


def _qualified_closure(
    bindings: tuple[StepAuthorizationBinding, ...],
    *,
    awaiting: tuple[str, ...] = (),
    denied: tuple[QualificationFailure, ...] = (),
) -> QualifiedPlan:
    return QualifiedPlan.from_content(
        plan_digest=_digest("plan"),
        authority_context_digest=_digest("authority-context"),
        step_bindings=bindings,
        awaiting_approval_steps=awaiting,
        denied_steps=denied,
    )


def _plan_step(
    step_id: str,
    *,
    kind: str = "EFFECT",
    operation_kind: str = "test.operation.v1",
    operation_digest: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        step_id=step_id,
        step_kind=kind,
        operation_contract_ref=OperationContractRef(
            kind=operation_kind,
            contract_version="1.0.0",
            contract_digest=operation_digest or _digest("operation-contract"),
        ),
    )


def _check_qualified_closure(
    steps: tuple[SimpleNamespace, ...], qualified: QualifiedPlan
) -> None:
    WorkItemClaimRepository._require_qualified_plan_closure(
        SimpleNamespace(ordered_steps=steps),
        qualified,
        project_key="project-a",
        run_id="run-1",
        project_registry_revision=3,
        project_scope_digest=_digest("project-scope"),
    )


def test_qualified_plan_rejects_extra_binding_for_empty_plan() -> None:
    with pytest.raises(ClaimBindingMismatch, match="closure differs"):
        _check_qualified_closure((), _qualified_closure((_closure_binding("extra"),)))


def test_qualified_plan_rejects_missing_required_step_binding() -> None:
    with pytest.raises(ClaimBindingMismatch, match="closure differs"):
        _check_qualified_closure((_plan_step("required"),), _qualified_closure(()))


@pytest.mark.parametrize(
    "binding",
    [
        _closure_binding("step-1", operation_kind="wrong.operation.v1"),
        _closure_binding("step-1", operation_digest=_digest("wrong-contract")),
    ],
)
def test_qualified_plan_rejects_wrong_operation_kind_or_digest(
    binding: StepAuthorizationBinding,
) -> None:
    with pytest.raises(ClaimBindingMismatch, match="step binding drift"):
        _check_qualified_closure(
            (_plan_step("step-1"),),
            _qualified_closure((binding,)),
        )


@pytest.mark.parametrize("disposition", ["awaiting", "denied"])
def test_qualified_plan_rejects_awaiting_or_denied_under_qualified(
    disposition: str,
) -> None:
    binding = _closure_binding("step-1")
    awaiting = ("step-1",) if disposition == "awaiting" else ()
    denied = (
        QualificationFailure.from_content(
            step_id="step-1",
            reason_code="DENIED",
            failure_ref="failure:1",
        ),
    ) if disposition == "denied" else ()
    with pytest.raises(ClaimBindingMismatch, match="awaiting or denied"):
        _check_qualified_closure(
            (_plan_step("step-1"),),
            _qualified_closure((binding,), awaiting=awaiting, denied=denied),
        )


def test_qualified_plan_exact_authorization_closure_passes() -> None:
    effect = _closure_binding("effect-step")
    admission = _closure_binding("admission-step")
    _check_qualified_closure(
        (
            _plan_step("pure-step", kind="PURE"),
            _plan_step("effect-step", kind="EFFECT"),
            _plan_step("admission-step", kind="ADMISSION"),
        ),
        _qualified_closure((effect, admission)),
    )


def test_stale_work_and_resource_lease_tokens_fail_closed_with_revision_cas() -> None:
    expires = datetime(2100, 1, 1, tzinfo=UTC)
    binding_content = {
        "work_item_id": "work-1",
        "assignment_digest": _digest("assignment"),
        "handler_binding_digest": _digest("handler"),
        "handler_realization_digest": _digest("handler"),
        "authorization_digest": _digest("authorization"),
        "attempt_id": _digest("attempt"),
        "lease_token": "stale-token",
        "lease_expires_at": expires,
        "node_id": "node-1",
        "node_profile_digest": _digest("node-profile"),
        "interpreter_profile_digest": _digest("interpreter"),
        "authority_digest": _digest("authority"),
        "claim_authority_epoch": 1,
    }
    provisional = ClaimBinding.model_construct(
        **binding_content, binding_digest="0" * 64
    )
    claim_binding = ClaimBinding(
        **binding_content,
        binding_digest=canonical_digest(
            provisional, exclude_fields={"binding_digest"}
        ),
    )
    connection = _RecordingConnection(
        [
            _MappedResult(
                {
                    "work_item_id": "work-1",
                    "project_key": "project-a",
                    "run_id": "run-1",
                    "step_id": "step-1",
                    "state": "CLAIMED",
                    "lease_token": "stale-token",
                    "lease_expires_at": expires,
                    "revision": 4,
                    "claim_binding_json": claim_binding.model_dump(mode="json"),
                    "claim_attempt_id": claim_binding.attempt_id,
                }
            ),
            _ZeroRows(),
        ]
    )
    work = WorkItemClaimRepository(connection)  # type: ignore[arg-type]
    control_scope = ControlPlaneScope(
        system_actor_id="test-scheduler",
        permission="runtime.cross_project_claim",
        authority_epoch=1,
    )
    with pytest.raises(ClaimConflict, match="token/revision CAS"):
        work.heartbeat(
            control_scope,
            "work-1",
            "stale-token",
            expected_revision=4,
            new_expiry=datetime(2100, 1, 2, tzinfo=UTC),
        )
    compiled_work = connection.statements[-1].compile(  # type: ignore[attr-defined]
        dialect=postgresql.dialect()
    )
    work_sql = str(compiled_work).upper()
    assert "LEASE_TOKEN" in work_sql and "REVISION" in work_sql
    assert "STATE =" in work_sql and "CLAIMED" in compiled_work.params.values()

    resource_connection = _RecordingConnection()
    resources = ResourceReservationRepository(resource_connection)  # type: ignore[arg-type]
    with pytest.raises(StaleLeaseToken, match="token/revision CAS"):
        resources.release(
            "reservation-1",
            "stale-token",
            expected_revision=9,
            reason="TERMINAL",
        )
    resource_sql = _postgres_sql(resource_connection.statements[-1]).upper()
    assert "LEASE_TOKEN" in resource_sql and "REVISION" in resource_sql
    assert "STATE = 'ACTIVE'" in resource_sql


def test_cross_project_lifecycle_requires_control_permission_before_database_io() -> None:
    control_scope = ControlPlaneScope(
        system_actor_id="test-scheduler",
        permission="runtime.cross_project_claim",
        authority_epoch=1,
    )
    object.__setattr__(control_scope, "permission", "not-authorized")
    connection = _RecordingConnection()
    repository = WorkItemClaimRepository(connection)  # type: ignore[arg-type]

    with pytest.raises(PermissionError, match="lacks permission"):
        repository.heartbeat(
            control_scope,
            "work-1",
            "lease-1",
            expected_revision=0,
            new_expiry=datetime(2100, 1, 1, tzinfo=UTC),
        )
    with pytest.raises(PermissionError, match="lacks permission"):
        repository.reap_expired(
            control_scope,
            now=datetime(2100, 1, 1, tzinfo=UTC),
            limit=0,
        )
    assert connection.statements == []
