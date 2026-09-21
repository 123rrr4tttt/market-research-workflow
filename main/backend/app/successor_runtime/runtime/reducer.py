"""Pure reducers.  No handler may write terminal state directly."""

from __future__ import annotations

import ast
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import NoReturn

from functorial_kit import Failure

from app.successor_runtime.language.checksum import sha256_hex
from app.successor_runtime.language.plan import (
    CompiledControlNode,
    object_type_digest,
)
from app.successor_runtime.language.transforms import (
    DiscriminatorRef,
    TransformRegistry,
)

from .transitions import (
    BranchEvent,
    EffectDisposition,
    IllegalTransition,
    RunEvent,
    RunState,
    StepEvent,
    StepState,
    transition_run_result,
    transition_step_result,
)
from .failure_policy import raise_runtime_failure, runtime_failure


@dataclass(frozen=True, slots=True)
class CompletionPolicy:
    required_step_ids: frozenset[str]
    acceptable_terminal_states: frozenset[StepState] = frozenset({StepState.SUCCEEDED})
    acceptable_qualifiers: frozenset[str] = frozenset({"STANDARD"})


@dataclass(frozen=True, slots=True)
class StepSnapshot:
    step_id: str
    state: StepState
    effect_disposition: EffectDisposition = EffectDisposition.NOT_STARTED
    qualifier: str = "STANDARD"
    revision: int = 0


@dataclass(frozen=True, slots=True)
class RunSnapshot:
    run_id: str
    state: RunState
    revision: int = 0


@dataclass(frozen=True, slots=True)
class BranchArmControl:
    """The compiled step occurrence set owned by one declared branch."""

    branch_id: str
    step_ids: tuple[str, ...]
    entry_step_ids: tuple[str, ...]
    approval_entry_step_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.branch_id or not self.step_ids or not self.entry_step_ids:
            _raise_invariant("branch control requires identity, steps, and entries")
        if len(set(self.step_ids)) != len(self.step_ids):
            _raise_invariant("branch step IDs must be unique")
        if not set(self.entry_step_ids).issubset(self.step_ids):
            _raise_invariant("branch entries must belong to the branch")
        if not set(self.approval_entry_step_ids).issubset(self.entry_step_ids):
            _raise_invariant("approval entries must be branch entries")


@dataclass(frozen=True, slots=True)
class BranchSelectionControl:
    """Exact runtime control record for one compiled ``Decide`` node."""

    control_id: str
    discriminator_id: str
    discriminator_version: str
    input_digest: str
    branches: tuple[BranchArmControl, ...]

    def __post_init__(self) -> None:
        if (
            not self.control_id
            or not self.discriminator_id
            or not self.discriminator_version
        ):
            _raise_invariant("branch selection control identity is incomplete")
        if len(self.input_digest) != 64 or any(
            character not in "0123456789abcdef" for character in self.input_digest
        ):
            _raise_invariant(
                "branch selection input_digest must be canonical sha256 hex"
            )
        branch_ids = tuple(branch.branch_id for branch in self.branches)
        if not branch_ids or len(set(branch_ids)) != len(branch_ids):
            _raise_invariant("branch IDs must be non-empty and unique")
        all_step_ids = tuple(
            step_id for branch in self.branches for step_id in branch.step_ids
        )
        if len(set(all_step_ids)) != len(all_step_ids):
            _raise_invariant("a step occurrence cannot belong to multiple branches")


def _raise_invariant(message: str) -> NoReturn:
    # kit:boundary owner=successor.runtime.reducer.invariant class=PROGRAMMER_DEFECT failure_family=none witness=test:test_reducer_programmer_defect_boundaries
    raise ValueError(message)


@dataclass(frozen=True, slots=True)
class BranchDecisionEvent:
    """Typed, lineage-preserving event for one branch arm."""

    control_id: str
    control_digest: str
    event: BranchEvent
    discriminator_id: str
    discriminator_version: str
    discriminator_digest: str
    input_digest: str
    branch_id: str


@dataclass(frozen=True, slots=True)
class BranchDecisionReduction:
    run: RunSnapshot
    steps: tuple[StepSnapshot, ...]
    events: tuple[BranchDecisionEvent, ...]
    selected_branch_id: str | None


class BranchDecisionUnresolved(ValueError):
    """No frozen state edge may materialize an unresolved branch decision."""


class GuardExpressionError(ValueError):
    """A compiled branch guard is outside the frozen guard language."""


_EFFECT_BY_EVENT: dict[StepEvent, EffectDisposition] = {
    StepEvent.EFFECT_STARTED: EffectDisposition.IN_FLIGHT,
    StepEvent.EFFECT_FAILED: EffectDisposition.FAILED,
    StepEvent.PURE_VALUE_PRODUCED: EffectDisposition.SUCCEEDED,
    StepEvent.RUNTIME_VALUE_PRODUCED: EffectDisposition.SUCCEEDED,
    StepEvent.OUTCOME_STAGED: EffectDisposition.SUCCEEDED,
    StepEvent.COMMIT_PREPARED: EffectDisposition.IN_FLIGHT,
    StepEvent.COMMIT_READBACK_CONFIRMED: EffectDisposition.SUCCEEDED,
    StepEvent.EFFECT_RECEIPT_LOST: EffectDisposition.OUTCOME_UNKNOWN,
    StepEvent.COMMIT_OR_DELIVERY_OUTCOME_UNKNOWN: EffectDisposition.OUTCOME_UNKNOWN,
    StepEvent.COMMIT_OR_DELIVERY_REJECTED: EffectDisposition.FAILED,
    StepEvent.AUTHORITATIVE_READBACK_SUCCEEDED: EffectDisposition.SUCCEEDED,
    StepEvent.AUTHORITATIVE_READBACK_FAILED: EffectDisposition.FAILED,
    StepEvent.READBACK_UNAVAILABLE: EffectDisposition.OUTCOME_UNKNOWN,
    StepEvent.RECONCILE_REQUESTED: EffectDisposition.OUTCOME_UNKNOWN,
}


def reduce_step_result(
    snapshot: StepSnapshot,
    event: StepEvent,
    target: StepState,
    *,
    guard: bool,
    qualifier: str | None = None,
) -> StepSnapshot | Failure:
    state = transition_step_result(snapshot.state, event, target, guard=guard)
    if isinstance(state, Failure):
        return state
    effect = _EFFECT_BY_EVENT.get(event, snapshot.effect_disposition)
    return replace(
        snapshot,
        state=state,
        effect_disposition=effect,
        qualifier=qualifier or snapshot.qualifier,
        revision=snapshot.revision + 1,
    )


def reduce_step(
    snapshot: StepSnapshot,
    event: StepEvent,
    target: StepState,
    *,
    guard: bool,
    qualifier: str | None = None,
) -> StepSnapshot:
    """Legacy exception ABI over :func:`reduce_step_result`."""

    result = reduce_step_result(
        snapshot, event, target, guard=guard, qualifier=qualifier
    )
    if isinstance(result, Failure):
        # kit:boundary owner=successor.runtime.reducer.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.runtime.failure witness=test:test_w07_runtime_failure_lift_context  # noqa: E501
        raise_runtime_failure(result, IllegalTransition)
    return result


def _reduce_branch_decision_impl(
    run: RunSnapshot,
    steps: tuple[StepSnapshot, ...],
    control: CompiledControlNode,
    *,
    discriminator_registry: TransformRegistry,
    input_value: object,
    skipped_branch_ids: frozenset[str] = frozenset(),
) -> BranchDecisionReduction | Failure:
    """Interpret one exact compiled ``Decide`` without caller-selected matches.

    The reducer verifies the recursive compiled-control digest, resolves the
    exact versioned discriminator ref in the supplied registry, canonicalizes
    the real input value, executes the discriminator, and evaluates every
    compiled guard.  A caller cannot substitute ``matched_branch_ids``.
    """

    try:
        control.require_valid_control_digest()
    except Exception as exc:
        return runtime_failure(
            "BRANCH_CONTROL_INVALID",
            str(exc),
            ValueError,
            site="successor_runtime.runtime.reducer.reduce_branch_decision",
        )
    if control.node_kind != "decide":
        return runtime_failure(
            "BRANCH_CONTROL_INVALID",
            "branch reduction requires compiled Decide control",
            ValueError,
            site="successor_runtime.runtime.reducer.reduce_branch_decision",
        )
    if control.discriminator_ref is None:
        return runtime_failure(
            "BRANCH_CONTROL_INVALID",
            "compiled Decide discriminator is missing",
            ValueError,
            site="successor_runtime.runtime.reducer.reduce_branch_decision",
        )

    try:
        discriminator_ref = DiscriminatorRef(
            name=control.discriminator_ref.name,
            version=control.discriminator_ref.version,
            digest=control.discriminator_ref.digest,
            transform_kind="discriminator",
        )
        discriminator = discriminator_registry.resolve_discriminator(discriminator_ref)
        branch_ids = tuple(branch.branch_id for branch in control.decision_branches)
        discriminator_input_digest = object_type_digest(discriminator.input_type)
        control_input_digest = object_type_digest(control.input_type)
    except Exception as exc:
        return runtime_failure(
            "BRANCH_CONTROL_INVALID",
            str(exc),
            ValueError,
            site="successor_runtime.runtime.reducer.reduce_branch_decision",
        )
    if discriminator.branch_ids != branch_ids:
        return runtime_failure(
            "BRANCH_CONTROL_INVALID",
            "compiled Decide branch set does not match discriminator binding",
            ValueError,
            site="successor_runtime.runtime.reducer.reduce_branch_decision",
        )
    if discriminator_input_digest != control_input_digest:
        return runtime_failure(
            "BRANCH_CONTROL_INVALID",
            "compiled Decide input type does not match discriminator binding",
            ValueError,
            site="successor_runtime.runtime.reducer.reduce_branch_decision",
        )

    try:
        input_digest = sha256_hex(input_value)
    except Exception as exc:
        return runtime_failure(
            "BRANCH_CONTROL_INVALID",
            str(exc),
            ValueError,
            site="successor_runtime.runtime.reducer.reduce_branch_decision",
        )
    branch_by_id = {branch.branch_id: branch for branch in control.decision_branches}
    unknown_skipped = skipped_branch_ids - branch_by_id.keys()
    if unknown_skipped:
        return runtime_failure(
            "BRANCH_CONTROL_INVALID",
            f"unknown skipped branches: {sorted(unknown_skipped)}",
            ValueError,
            site="successor_runtime.runtime.reducer.reduce_branch_decision",
        )

    step_by_id = {step.step_id: step for step in steps}
    if len(step_by_id) != len(steps):
        return runtime_failure(
            "BRANCH_CONTROL_INVALID",
            "step snapshots must have unique step IDs",
            ValueError,
            site="successor_runtime.runtime.reducer.reduce_branch_decision",
        )
    required_step_ids = {
        step_id for branch in control.decision_branches for step_id in branch.step_ids
    }
    missing = required_step_ids - step_by_id.keys()
    if missing:
        return runtime_failure(
            "BRANCH_CONTROL_INVALID",
            f"branch step snapshots are missing: {sorted(missing)}",
            ValueError,
            site="successor_runtime.runtime.reducer.reduce_branch_decision",
        )

    try:
        raw_result = discriminator.callable(input_value)
    except Exception:
        return runtime_failure(
            "BRANCH_DECISION_UNRESOLVED",
            "compiled Decide discriminator did not produce a frozen branch decision",
            BranchDecisionUnresolved,
            site="successor_runtime.runtime.reducer.reduce_branch_decision",
        )
    raw_candidates = _discriminator_candidates(raw_result)

    matched_branch_ids: list[str] = []
    for branch in control.decision_branches:
        if (
            branch.branch_id not in raw_candidates
            or branch.branch_id in skipped_branch_ids
        ):
            continue
        guard_result = guard_holds_result(branch.guard, input_value)
        if isinstance(guard_result, Failure):
            return guard_result
        if guard_result:
            matched_branch_ids.append(branch.branch_id)
    matched_branch_ids = tuple(matched_branch_ids)
    selected_branch_id: str | None = None
    if len(raw_candidates) == len(set(raw_candidates)) and len(matched_branch_ids) == 1:
        selected_branch_id = matched_branch_ids[0]

    if selected_branch_id is None:
        return runtime_failure(
            "BRANCH_DECISION_UNRESOLVED",
            "compiled Decide produced no unique selected branch; no frozen "
            "BranchUnresolved state edge exists",
            BranchDecisionUnresolved,
            site="successor_runtime.runtime.reducer.reduce_branch_decision",
        )

    updates: dict[str, StepSnapshot] = {}
    events: list[BranchDecisionEvent] = []
    for branch in control.decision_branches:
        if branch.branch_id == selected_branch_id:
            branch_event = BranchEvent.BRANCH_SELECTED
            event = _branch_event(control, input_digest, branch.branch_id, branch_event)
            if isinstance(event, Failure):
                return event
            events.append(event)
            for step_id in branch.entry_step_ids:
                reduced = reduce_step_result(
                    step_by_id[step_id],
                    StepEvent.DEPENDENCIES_SATISFIED,
                    StepState.READY,
                    guard=True,
                )
                if isinstance(reduced, Failure):
                    return reduced
                updates[step_id] = reduced
            continue

        branch_event = (
            BranchEvent.BRANCH_SKIPPED
            if branch.branch_id in skipped_branch_ids
            else BranchEvent.BRANCH_NOT_SELECTED
        )
        event = _branch_event(control, input_digest, branch.branch_id, branch_event)
        if isinstance(event, Failure):
            return event
        events.append(event)
        step_event = (
            StepEvent.BRANCH_SKIPPED
            if branch_event is BranchEvent.BRANCH_SKIPPED
            else StepEvent.BRANCH_NOT_SELECTED
        )
        target = (
            StepState.SKIPPED_BY_DECISION
            if branch_event is BranchEvent.BRANCH_SKIPPED
            else StepState.NOT_SELECTED
        )
        for step_id in branch.step_ids:
            reduced = reduce_step_result(
                step_by_id[step_id], step_event, target, guard=True
            )
            if isinstance(reduced, Failure):
                return reduced
            updates[step_id] = reduced

    reduced_steps = tuple(updates.get(step.step_id, step) for step in steps)
    return BranchDecisionReduction(
        run,
        reduced_steps,
        tuple(events),
        selected_branch_id,
    )


def reduce_branch_decision_result(
    run: RunSnapshot,
    steps: tuple[StepSnapshot, ...],
    control: CompiledControlNode,
    *,
    discriminator_registry: TransformRegistry,
    input_value: object,
    skipped_branch_ids: frozenset[str] = frozenset(),
) -> BranchDecisionReduction | Failure:
    """Return branch reduction or a closed runtime failure value."""

    try:
        return _reduce_branch_decision_impl(
            run,
            steps,
            control,
            discriminator_registry=discriminator_registry,
            input_value=input_value,
            skipped_branch_ids=skipped_branch_ids,
        )
    except BranchDecisionUnresolved as exc:
        return runtime_failure(
            "BRANCH_DECISION_UNRESOLVED",
            str(exc),
            BranchDecisionUnresolved,
            site="successor_runtime.runtime.reducer.reduce_branch_decision",
        )
    except ValueError as exc:
        return runtime_failure(
            "BRANCH_CONTROL_INVALID",
            str(exc),
            ValueError,
            site="successor_runtime.runtime.reducer.reduce_branch_decision",
        )


def reduce_branch_decision(
    run: RunSnapshot,
    steps: tuple[StepSnapshot, ...],
    control: CompiledControlNode,
    *,
    discriminator_registry: TransformRegistry,
    input_value: object,
    skipped_branch_ids: frozenset[str] = frozenset(),
) -> BranchDecisionReduction:
    """Legacy exception ABI over :func:`reduce_branch_decision_result`."""

    result = reduce_branch_decision_result(
        run,
        steps,
        control,
        discriminator_registry=discriminator_registry,
        input_value=input_value,
        skipped_branch_ids=skipped_branch_ids,
    )
    if isinstance(result, Failure):
        exception_type = (
            BranchDecisionUnresolved
            if result.code == "BRANCH_DECISION_UNRESOLVED"
            else GuardExpressionError
            if result.code == "GUARD_EXPRESSION_INVALID"
            else ValueError
        )
        # kit:boundary owner=successor.runtime.reducer.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.runtime.failure witness=test:test_w07_runtime_failure_lift_context  # noqa: E501
        raise_runtime_failure(result, exception_type)
    return result


def _branch_event(
    control: CompiledControlNode,
    input_digest: str,
    branch_id: str,
    event: BranchEvent,
) -> BranchDecisionEvent | Failure:
    if control.discriminator_ref is None:
        return runtime_failure(
            "BRANCH_CONTROL_INVALID",
            "compiled Decide discriminator is missing",
            ValueError,
            site="successor_runtime.runtime.reducer.reduce_branch_decision",
        )
    return BranchDecisionEvent(
        control_id=control.control_id,
        control_digest=control.control_digest,
        event=event,
        discriminator_id=control.discriminator_ref.name,
        discriminator_version=control.discriminator_ref.version,
        discriminator_digest=control.discriminator_ref.digest,
        input_digest=input_digest,
        branch_id=branch_id,
    )


def _discriminator_candidates(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (tuple, list)) and all(
        isinstance(item, str) for item in value
    ):
        return tuple(value)
    return ()


def _guard_holds(expression: str, input_value: object) -> bool | Failure:
    """Evaluate the frozen P0 guard language without Python ``eval``."""

    try:
        parsed = ast.parse(expression, mode="eval")
        result = _guard_value(parsed.body, input_value)
    except (SyntaxError, TypeError, ValueError, KeyError, AttributeError):
        return runtime_failure(
            "GUARD_EXPRESSION_INVALID",
            "compiled guard expression is invalid",
            GuardExpressionError,
            site="successor_runtime.runtime.reducer.guard_holds",
        )
    if isinstance(result, Failure):
        return result
    return result is True


def guard_holds_result(expression: str, input_value: object) -> bool | Failure:
    """Evaluate a guard as a closed runtime result."""

    return _guard_holds(expression, input_value)


def guard_holds(expression: str, input_value: object) -> bool:
    """Legacy exception ABI over :func:`guard_holds_result`."""

    result = guard_holds_result(expression, input_value)
    if isinstance(result, Failure):
        # kit:boundary owner=successor.runtime.reducer.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.runtime.failure witness=test:test_w07_runtime_failure_lift_context  # noqa: E501
        raise_runtime_failure(result, GuardExpressionError)
    return result


def _guard_value(node: ast.AST, root: object) -> object:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if isinstance(root, Mapping) and node.id in root:
            return root[node.id]
        # A leading symbolic name such as ``outcome`` denotes the input root.
        return root
    if isinstance(node, ast.Attribute):
        owner = _guard_value(node.value, root)
        if isinstance(owner, Failure):
            return owner
        if isinstance(owner, Mapping):
            return owner[node.attr]
        return getattr(owner, node.attr)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        operand = _guard_value(node.operand, root)
        if isinstance(operand, Failure):
            return operand
        return not bool(operand)
    if isinstance(node, ast.BoolOp):
        raw_values = tuple(_guard_value(value, root) for value in node.values)
        if any(isinstance(value, Failure) for value in raw_values):
            return next(value for value in raw_values if isinstance(value, Failure))
        values = tuple(bool(value) for value in raw_values)
        if isinstance(node.op, ast.And):
            return all(values)
        if isinstance(node.op, ast.Or):
            return any(values)
    if isinstance(node, ast.Compare) and len(node.ops) == len(node.comparators) == 1:
        left = _guard_value(node.left, root)
        right = _guard_value(node.comparators[0], root)
        if isinstance(left, Failure):
            return left
        if isinstance(right, Failure):
            return right
        operator = node.ops[0]
        if isinstance(operator, ast.Eq):
            return left == right
        if isinstance(operator, ast.NotEq):
            return left != right
        if isinstance(operator, ast.In):
            return left in right  # type: ignore[operator]
        if isinstance(operator, ast.NotIn):
            return left not in right  # type: ignore[operator]
    return runtime_failure(
        "GUARD_EXPRESSION_INVALID",
        "unsupported compiled guard expression",
        GuardExpressionError,
        site="successor_runtime.runtime.reducer.guard_holds",
    )


def completion_satisfied(
    steps: tuple[StepSnapshot, ...], policy: CompletionPolicy
) -> bool:
    by_id = {step.step_id: step for step in steps}
    if len(by_id) != len(steps) or not policy.required_step_ids:
        return False
    if not policy.required_step_ids.issubset(by_id):
        return False
    return all(
        by_id[step_id].state in policy.acceptable_terminal_states
        and by_id[step_id].qualifier in policy.acceptable_qualifiers
        for step_id in policy.required_step_ids
    )


def reduce_run_completion_result(
    snapshot: RunSnapshot,
    steps: tuple[StepSnapshot, ...],
    policy: CompletionPolicy,
) -> RunSnapshot | Failure:
    """The only ordinary route to COMPLETED.

    A caller-supplied event or handler success is deliberately insufficient.
    """

    try:
        satisfied = completion_satisfied(steps, policy)
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        return runtime_failure(
            "RUN_EVENT_INVALID",
            str(exc),
            ValueError,
            site="successor_runtime.runtime.reducer.reduce_run_completion",
        )
    state = transition_run_result(
        snapshot.state,
        RunEvent.RUN_COMPLETION_DERIVED,
        RunState.COMPLETED,
        guard=satisfied,
    )
    if isinstance(state, Failure):
        return state
    return replace(snapshot, state=state, revision=snapshot.revision + 1)


def reduce_run_completion(
    snapshot: RunSnapshot,
    steps: tuple[StepSnapshot, ...],
    policy: CompletionPolicy,
) -> RunSnapshot:
    result = reduce_run_completion_result(snapshot, steps, policy)
    if isinstance(result, Failure):
        exception_type = (
            IllegalTransition
            if result.code == "ILLEGAL_RUN_TRANSITION"
            else ValueError
        )
        # kit:boundary owner=successor.runtime.reducer.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.runtime.failure witness=test:test_w07_runtime_failure_lift_context  # noqa: E501
        raise_runtime_failure(result, exception_type)
    return result


def reduce_run_event_result(
    snapshot: RunSnapshot, event: RunEvent, target: RunState, *, guard: bool
) -> RunSnapshot | Failure:
    if event is RunEvent.RUN_COMPLETION_DERIVED:
        return runtime_failure(
            "RUN_EVENT_INVALID",
            "RunCompletionDerived requires required steps and CompletionPolicy",
            ValueError,
            site="successor_runtime.runtime.reducer.reduce_run_event",
        )
    state = transition_run_result(snapshot.state, event, target, guard=guard)
    if isinstance(state, Failure):
        return state
    return replace(snapshot, state=state, revision=snapshot.revision + 1)


def reduce_run_event(
    snapshot: RunSnapshot, event: RunEvent, target: RunState, *, guard: bool
) -> RunSnapshot:
    result = reduce_run_event_result(snapshot, event, target, guard=guard)
    if isinstance(result, Failure):
        exception_type = (
            IllegalTransition
            if result.code == "ILLEGAL_RUN_TRANSITION"
            else ValueError
        )
        # kit:boundary owner=successor.runtime.reducer.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.runtime.failure witness=test:test_w07_runtime_failure_lift_context  # noqa: E501
        raise_runtime_failure(result, exception_type)
    return result
