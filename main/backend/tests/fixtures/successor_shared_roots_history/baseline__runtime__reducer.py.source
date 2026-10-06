"""Pure reducers.  No handler may write terminal state directly."""

from __future__ import annotations

import ast
from collections.abc import Mapping
from dataclasses import dataclass, replace

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
    RunEvent,
    RunState,
    StepEvent,
    StepState,
    transition_run,
    transition_step,
)


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
            raise ValueError("branch control requires identity, steps, and entries")
        if len(set(self.step_ids)) != len(self.step_ids):
            raise ValueError("branch step IDs must be unique")
        if not set(self.entry_step_ids).issubset(self.step_ids):
            raise ValueError("branch entries must belong to the branch")
        if not set(self.approval_entry_step_ids).issubset(self.entry_step_ids):
            raise ValueError("approval entries must be branch entries")


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
            raise ValueError("branch selection control identity is incomplete")
        if len(self.input_digest) != 64 or any(
            character not in "0123456789abcdef" for character in self.input_digest
        ):
            raise ValueError(
                "branch selection input_digest must be canonical sha256 hex"
            )
        branch_ids = tuple(branch.branch_id for branch in self.branches)
        if not branch_ids or len(set(branch_ids)) != len(branch_ids):
            raise ValueError("branch IDs must be non-empty and unique")
        all_step_ids = tuple(
            step_id for branch in self.branches for step_id in branch.step_ids
        )
        if len(set(all_step_ids)) != len(all_step_ids):
            raise ValueError("a step occurrence cannot belong to multiple branches")


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


def reduce_step(
    snapshot: StepSnapshot,
    event: StepEvent,
    target: StepState,
    *,
    guard: bool,
    qualifier: str | None = None,
) -> StepSnapshot:
    state = transition_step(snapshot.state, event, target, guard=guard)
    effect = _EFFECT_BY_EVENT.get(event, snapshot.effect_disposition)
    return replace(
        snapshot,
        state=state,
        effect_disposition=effect,
        qualifier=qualifier or snapshot.qualifier,
        revision=snapshot.revision + 1,
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
    """Interpret one exact compiled ``Decide`` without caller-selected matches.

    The reducer verifies the recursive compiled-control digest, resolves the
    exact versioned discriminator ref in the supplied registry, canonicalizes
    the real input value, executes the discriminator, and evaluates every
    compiled guard.  A caller cannot substitute ``matched_branch_ids``.
    """

    control.require_valid_control_digest()
    if control.node_kind != "decide":
        raise ValueError("branch reduction requires compiled Decide control")
    if control.discriminator_ref is None:
        raise ValueError("compiled Decide discriminator is missing")

    discriminator_ref = DiscriminatorRef(
        name=control.discriminator_ref.name,
        version=control.discriminator_ref.version,
        digest=control.discriminator_ref.digest,
        transform_kind="discriminator",
    )
    discriminator = discriminator_registry.resolve_discriminator(discriminator_ref)
    branch_ids = tuple(branch.branch_id for branch in control.decision_branches)
    if discriminator.branch_ids != branch_ids:
        raise ValueError(
            "compiled Decide branch set does not match discriminator binding"
        )
    if object_type_digest(discriminator.input_type) != object_type_digest(
        control.input_type
    ):
        raise ValueError(
            "compiled Decide input type does not match discriminator binding"
        )

    input_digest = sha256_hex(input_value)
    branch_by_id = {branch.branch_id: branch for branch in control.decision_branches}
    unknown_skipped = skipped_branch_ids - branch_by_id.keys()
    if unknown_skipped:
        raise ValueError(f"unknown skipped branches: {sorted(unknown_skipped)}")

    step_by_id = {step.step_id: step for step in steps}
    if len(step_by_id) != len(steps):
        raise ValueError("step snapshots must have unique step IDs")
    required_step_ids = {
        step_id for branch in control.decision_branches for step_id in branch.step_ids
    }
    missing = required_step_ids - step_by_id.keys()
    if missing:
        raise ValueError(f"branch step snapshots are missing: {sorted(missing)}")

    try:
        raw_result = discriminator.callable(input_value)
    except Exception as exc:
        raise BranchDecisionUnresolved(
            "compiled Decide discriminator did not produce a frozen branch decision"
        ) from exc
    raw_candidates = _discriminator_candidates(raw_result)

    matched_branch_ids = tuple(
        branch.branch_id
        for branch in control.decision_branches
        if branch.branch_id in raw_candidates
        and branch.branch_id not in skipped_branch_ids
        and _guard_holds(branch.guard, input_value)
    )
    selected_branch_id: str | None = None
    if len(raw_candidates) == len(set(raw_candidates)) and len(matched_branch_ids) == 1:
        selected_branch_id = matched_branch_ids[0]

    if selected_branch_id is None:
        raise BranchDecisionUnresolved(
            "compiled Decide produced no unique selected branch; no frozen "
            "BranchUnresolved state edge exists"
        )

    updates: dict[str, StepSnapshot] = {}
    events: list[BranchDecisionEvent] = []
    for branch in control.decision_branches:
        if branch.branch_id == selected_branch_id:
            branch_event = BranchEvent.BRANCH_SELECTED
            events.append(
                _branch_event(control, input_digest, branch.branch_id, branch_event)
            )
            for step_id in branch.entry_step_ids:
                updates[step_id] = reduce_step(
                    step_by_id[step_id],
                    StepEvent.DEPENDENCIES_SATISFIED,
                    StepState.READY,
                    guard=True,
                )
            continue

        branch_event = (
            BranchEvent.BRANCH_SKIPPED
            if branch.branch_id in skipped_branch_ids
            else BranchEvent.BRANCH_NOT_SELECTED
        )
        events.append(
            _branch_event(control, input_digest, branch.branch_id, branch_event)
        )
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
            updates[step_id] = reduce_step(
                step_by_id[step_id], step_event, target, guard=True
            )

    reduced_steps = tuple(updates.get(step.step_id, step) for step in steps)
    return BranchDecisionReduction(
        run,
        reduced_steps,
        tuple(events),
        selected_branch_id,
    )


def _branch_event(
    control: CompiledControlNode,
    input_digest: str,
    branch_id: str,
    event: BranchEvent,
) -> BranchDecisionEvent:
    assert control.discriminator_ref is not None
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


def _guard_holds(expression: str, input_value: object) -> bool:
    """Evaluate the frozen P0 guard language without Python ``eval``."""

    try:
        parsed = ast.parse(expression, mode="eval")
        result = _guard_value(parsed.body, input_value)
    except (SyntaxError, TypeError, ValueError, KeyError, AttributeError):
        return False
    return result is True


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
        if isinstance(owner, Mapping):
            return owner[node.attr]
        return getattr(owner, node.attr)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not bool(_guard_value(node.operand, root))
    if isinstance(node, ast.BoolOp):
        values = tuple(bool(_guard_value(value, root)) for value in node.values)
        if isinstance(node.op, ast.And):
            return all(values)
        if isinstance(node.op, ast.Or):
            return any(values)
    if isinstance(node, ast.Compare) and len(node.ops) == len(node.comparators) == 1:
        left = _guard_value(node.left, root)
        right = _guard_value(node.comparators[0], root)
        operator = node.ops[0]
        if isinstance(operator, ast.Eq):
            return left == right
        if isinstance(operator, ast.NotEq):
            return left != right
        if isinstance(operator, ast.In):
            return left in right  # type: ignore[operator]
        if isinstance(operator, ast.NotIn):
            return left not in right  # type: ignore[operator]
    raise ValueError("unsupported compiled guard expression")


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


def reduce_run_completion(
    snapshot: RunSnapshot,
    steps: tuple[StepSnapshot, ...],
    policy: CompletionPolicy,
) -> RunSnapshot:
    """The only ordinary route to COMPLETED.

    A caller-supplied event or handler success is deliberately insufficient.
    """

    satisfied = completion_satisfied(steps, policy)
    state = transition_run(
        snapshot.state,
        RunEvent.RUN_COMPLETION_DERIVED,
        RunState.COMPLETED,
        guard=satisfied,
    )
    return replace(snapshot, state=state, revision=snapshot.revision + 1)


def reduce_run_event(
    snapshot: RunSnapshot, event: RunEvent, target: RunState, *, guard: bool
) -> RunSnapshot:
    if event is RunEvent.RUN_COMPLETION_DERIVED:
        raise ValueError(
            "RunCompletionDerived requires required steps and CompletionPolicy"
        )
    state = transition_run(snapshot.state, event, target, guard=guard)
    return replace(snapshot, state=state, revision=snapshot.revision + 1)
