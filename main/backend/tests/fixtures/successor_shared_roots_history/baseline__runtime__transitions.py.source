"""Frozen run/step/effect state spaces and fail-closed transition tables."""

from __future__ import annotations

from enum import StrEnum


class RunState(StrEnum):
    SUBMITTED = "SUBMITTED"
    COMPILING = "COMPILING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    RECONCILING = "RECONCILING"
    CANCELLING = "CANCELLING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"


class StepState(StrEnum):
    PENDING = "PENDING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    READY = "READY"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    COMMITTING = "COMMITTING"
    WAITING_EXTERNAL = "WAITING_EXTERNAL"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    RECONCILING = "RECONCILING"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"
    NOT_SELECTED = "NOT_SELECTED"
    SKIPPED_BY_DECISION = "SKIPPED_BY_DECISION"


class EffectDisposition(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    IN_FLIGHT = "IN_FLIGHT"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"


class BranchEvent(StrEnum):
    """Typed decision outcome recorded once for every declared branch."""

    BRANCH_SELECTED = "BRANCH_SELECTED"
    BRANCH_NOT_SELECTED = "BRANCH_NOT_SELECTED"
    BRANCH_SKIPPED = "BRANCH_SKIPPED"
    BRANCH_UNRESOLVED = "BRANCH_UNRESOLVED"


class RunEvent(StrEnum):
    COMPILE_REQUESTED = "CompileRequested"
    PLAN_COMPILED = "PlanCompiled"
    REQUIRED_APPROVALS_GRANTED = "RequiredApprovalsGranted"
    FIRST_REQUIRED_STEP_READY = "FirstRequiredStepReady"
    RUN_WAITING_DERIVED = "RunWaitingDerived"
    REQUIRED_STEP_RUNNABLE = "RequiredStepRunnable"
    BRANCH_UNRESOLVED = "BranchUnresolved"
    RUN_COMPLETION_DERIVED = "RunCompletionDerived"
    REQUIRED_STEP_FAILED = "RequiredStepFailed"
    CANCELLATION_REQUESTED = "CancellationRequested"
    REQUIRED_CLEANUP_SETTLED = "RequiredCleanupAndReadbackSettled"
    SUCCESSOR_RUN_ADOPTED = "SuccessorRunAdopted"


class StepEvent(StrEnum):
    DEPENDENCIES_SATISFIED = "DependenciesSatisfied"
    APPROVAL_GRANTED = "ApprovalGranted"
    STEP_CLAIMED = "StepClaimed"
    EFFECT_STARTED = "EffectStarted"
    EFFECT_FAILED = "EffectFailed"
    PURE_VALUE_PRODUCED = "PureValueProduced"
    RUNTIME_VALUE_PRODUCED = "RuntimeValueProduced"
    EFFECT_RECEIPT_LOST = "EffectReceiptLost"
    OUTCOME_STAGED = "OutcomeStaged"
    STAGED_DEPENDENCY_SATISFIED = "StagedDependencySatisfied"
    COMMIT_PREPARED = "CommitPrepared"
    COMMIT_READBACK_CONFIRMED = "CommitReadbackConfirmed"
    COMMIT_OR_DELIVERY_OUTCOME_UNKNOWN = "CommitOrDeliveryOutcomeUnknown"
    COMMIT_OR_DELIVERY_REJECTED = "CommitOrDeliveryRejected"
    AUTHORITATIVE_READBACK_SUCCEEDED = "AuthoritativeReadbackSucceeded"
    AUTHORITATIVE_READBACK_FAILED = "AuthoritativeReadbackFailed"
    READBACK_UNAVAILABLE = "ReadbackUnavailable"
    RECONCILE_REQUESTED = "ReconcileRequested"
    RETRY_AUTHORIZED = "RetryAuthorized"
    RETRY_DUE = "RetryDue"
    BRANCH_SELECTED = "BranchSelected"
    BRANCH_NOT_SELECTED = "BranchNotSelected"
    BRANCH_SKIPPED = "BranchSkipped"
    BRANCH_UNRESOLVED = "BranchUnresolved"
    CANCELLATION_REQUESTED = "CancellationRequested"
    CLEANUP_OR_READBACK_CONFIRMED = "CleanupOrReadbackConfirmed"


TERMINAL_RUN_STATES = frozenset(
    {RunState.COMPLETED, RunState.FAILED, RunState.CANCELLED, RunState.SUPERSEDED}
)
TERMINAL_STEP_STATES = frozenset(
    {
        StepState.SUCCEEDED,
        StepState.FAILED,
        StepState.CANCELLED,
        StepState.SUPERSEDED,
        StepState.NOT_SELECTED,
        StepState.SKIPPED_BY_DECISION,
    }
)


RUN_TRANSITIONS: dict[tuple[RunState, RunEvent], frozenset[RunState]] = {
    (RunState.SUBMITTED, RunEvent.COMPILE_REQUESTED): frozenset({RunState.COMPILING}),
    (RunState.COMPILING, RunEvent.PLAN_COMPILED): frozenset(
        {RunState.AWAITING_APPROVAL, RunState.READY}
    ),
    (RunState.AWAITING_APPROVAL, RunEvent.REQUIRED_APPROVALS_GRANTED): frozenset(
        {RunState.READY}
    ),
    (RunState.READY, RunEvent.FIRST_REQUIRED_STEP_READY): frozenset({RunState.RUNNING}),
    (RunState.RUNNING, RunEvent.RUN_WAITING_DERIVED): frozenset(
        {RunState.WAITING, RunState.RECONCILING}
    ),
    (RunState.WAITING, RunEvent.REQUIRED_STEP_RUNNABLE): frozenset({RunState.RUNNING}),
    (RunState.RECONCILING, RunEvent.REQUIRED_STEP_RUNNABLE): frozenset(
        {RunState.RUNNING}
    ),
    (RunState.RUNNING, RunEvent.RUN_COMPLETION_DERIVED): frozenset(
        {RunState.COMPLETED}
    ),
}
for _state in RunState:
    if _state not in TERMINAL_RUN_STATES:
        RUN_TRANSITIONS[(_state, RunEvent.REQUIRED_STEP_FAILED)] = frozenset(
            {RunState.FAILED}
        )
        RUN_TRANSITIONS[(_state, RunEvent.CANCELLATION_REQUESTED)] = frozenset(
            {RunState.CANCELLED, RunState.CANCELLING}
        )
        RUN_TRANSITIONS[(_state, RunEvent.SUCCESSOR_RUN_ADOPTED)] = frozenset(
            {RunState.SUPERSEDED}
        )
RUN_TRANSITIONS[(RunState.CANCELLING, RunEvent.REQUIRED_CLEANUP_SETTLED)] = frozenset(
    {RunState.CANCELLED, RunState.COMPLETED, RunState.FAILED, RunState.RECONCILING}
)


STEP_TRANSITIONS: dict[tuple[StepState, StepEvent], frozenset[StepState]] = {
    (StepState.PENDING, StepEvent.DEPENDENCIES_SATISFIED): frozenset(
        {StepState.READY, StepState.AWAITING_APPROVAL}
    ),
    (StepState.AWAITING_APPROVAL, StepEvent.APPROVAL_GRANTED): frozenset(
        {StepState.READY}
    ),
    (StepState.READY, StepEvent.STEP_CLAIMED): frozenset({StepState.CLAIMED}),
    (StepState.CLAIMED, StepEvent.EFFECT_STARTED): frozenset({StepState.RUNNING}),
    (StepState.RUNNING, StepEvent.EFFECT_FAILED): frozenset({StepState.FAILED}),
    (StepState.RUNNING, StepEvent.PURE_VALUE_PRODUCED): frozenset(
        {StepState.SUCCEEDED}
    ),
    (StepState.RUNNING, StepEvent.RUNTIME_VALUE_PRODUCED): frozenset(
        {StepState.SUCCEEDED}
    ),
    (StepState.RUNNING, StepEvent.EFFECT_RECEIPT_LOST): frozenset(
        {StepState.RECONCILING}
    ),
    (StepState.RUNNING, StepEvent.OUTCOME_STAGED): frozenset({StepState.SUCCEEDED}),
    (StepState.PENDING, StepEvent.STAGED_DEPENDENCY_SATISFIED): frozenset(
        {StepState.READY, StepState.AWAITING_APPROVAL}
    ),
    (StepState.RUNNING, StepEvent.COMMIT_PREPARED): frozenset({StepState.COMMITTING}),
    (StepState.COMMITTING, StepEvent.COMMIT_READBACK_CONFIRMED): frozenset(
        {StepState.SUCCEEDED}
    ),
    (StepState.COMMITTING, StepEvent.COMMIT_OR_DELIVERY_OUTCOME_UNKNOWN): frozenset(
        {StepState.RECONCILING}
    ),
    (StepState.COMMITTING, StepEvent.COMMIT_OR_DELIVERY_REJECTED): frozenset(
        {StepState.FAILED}
    ),
    (StepState.RECONCILING, StepEvent.AUTHORITATIVE_READBACK_SUCCEEDED): frozenset(
        {StepState.SUCCEEDED}
    ),
    (StepState.RECONCILING, StepEvent.AUTHORITATIVE_READBACK_FAILED): frozenset(
        {StepState.FAILED}
    ),
    (StepState.RECONCILING, StepEvent.READBACK_UNAVAILABLE): frozenset(
        {StepState.WAITING_EXTERNAL}
    ),
    (StepState.WAITING_EXTERNAL, StepEvent.RECONCILE_REQUESTED): frozenset(
        {StepState.RECONCILING}
    ),
    (StepState.FAILED, StepEvent.RETRY_AUTHORIZED): frozenset(
        {StepState.RETRY_SCHEDULED}
    ),
    (StepState.RETRY_SCHEDULED, StepEvent.RETRY_DUE): frozenset({StepState.READY}),
    (StepState.PENDING, StepEvent.BRANCH_NOT_SELECTED): frozenset(
        {StepState.NOT_SELECTED}
    ),
    (StepState.PENDING, StepEvent.BRANCH_SKIPPED): frozenset(
        {StepState.SKIPPED_BY_DECISION}
    ),
}
for _source in (
    StepState.PENDING,
    StepState.AWAITING_APPROVAL,
    StepState.READY,
    StepState.RETRY_SCHEDULED,
):
    STEP_TRANSITIONS[(_source, StepEvent.CANCELLATION_REQUESTED)] = frozenset(
        {StepState.CANCELLED}
    )
for _source in (
    StepState.CLAIMED,
    StepState.RUNNING,
    StepState.COMMITTING,
    StepState.WAITING_EXTERNAL,
    StepState.RECONCILING,
):
    STEP_TRANSITIONS[(_source, StepEvent.CANCELLATION_REQUESTED)] = frozenset(
        {StepState.CANCEL_REQUESTED}
    )
STEP_TRANSITIONS[
    (StepState.CANCEL_REQUESTED, StepEvent.CLEANUP_OR_READBACK_CONFIRMED)
] = frozenset(
    {
        StepState.CANCELLED,
        StepState.SUCCEEDED,
        StepState.FAILED,
        StepState.WAITING_EXTERNAL,
    }
)


class IllegalTransition(ValueError):
    pass


def transition_run(
    current: RunState, event: RunEvent, target: RunState, *, guard: bool
) -> RunState:
    allowed = RUN_TRANSITIONS.get((current, event), frozenset())
    if not guard or target not in allowed:
        raise IllegalTransition(
            f"illegal run transition: {current} + {event} -> {target}"
        )
    return target


def transition_step(
    current: StepState, event: StepEvent, target: StepState, *, guard: bool
) -> StepState:
    allowed = STEP_TRANSITIONS.get((current, event), frozenset())
    if not guard or target not in allowed:
        raise IllegalTransition(
            f"illegal step transition: {current} + {event} -> {target}"
        )
    return target
