"""Pure persisted-plan failure policy derivation.

The reducer owns state transitions; this module only proves whether a failed
step is a required semantic-return dependency and whether the exact frozen
plan permits the run to continue.  It performs no database access and never
authorizes retry, fallback, or successor materialization by itself.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from app.successor_runtime.language.plan import (
    CompiledControlNode,
    CompiledStep,
    ExecutionPlan,
    with_plan_digest,
)
from app.successor_runtime.language.profiles import ContractProfileRef
from app.successor_runtime.research.codec import sha256_hex
from app.successor_runtime.runtime.assignments import canonical_digest
from app.successor_runtime.runtime.qualification import QualifiedPlan


class FailurePolicyDerivationError(ValueError):
    """The persisted plan/qualification cannot prove a failure decision."""


class FailureContinuation(StrEnum):
    NONE = "NONE"
    RETRY = "RETRY"
    FALLBACK = "FALLBACK"
    PARTIAL_RESULT = "PARTIAL_RESULT"
    ERROR_ACCUMULATION = "ERROR_ACCUMULATION"
    SUCCESSOR_MATERIALIZATION = "SUCCESSOR_MATERIALIZATION"


class RunFailureDecision(StrEnum):
    REQUIRED_STEP_FAILED = "REQUIRED_STEP_FAILED"
    CONTINUE = "CONTINUE"


@dataclass(frozen=True, slots=True)
class FrozenFailureProfileRef:
    """Canonical identity of the persisted failure-profile reference.

    Older fixtures store a bounded opaque string.  First-specimen plans store
    the content-addressed ``ContractProfileRef`` shape.  Neither representation
    embeds the FailureProfile body, so this identity is evidence binding only;
    continuation semantics must be explicit in ``failure_modes``.
    """

    representation: Literal["OPAQUE", "CONTENT_ADDRESSED"]
    profile_id: str
    profile_version: str | None
    profile_digest: str | None


@dataclass(frozen=True, slots=True)
class FailurePolicyDecision:
    run_id: str
    step_id: str
    plan_digest: str
    qualification_digest: str
    qualified: bool
    required: bool
    fatal: bool
    may_continue: bool
    continuation: FailureContinuation
    run_decision: RunFailureDecision
    completion_policy_mode: str
    required_step_ids: tuple[str, ...]
    step_failure_modes: tuple[str, ...]
    plan_failure_modes: tuple[str, ...]
    failure_profile_ref: FrozenFailureProfileRef
    decision_digest: str

    @property
    def emit_required_step_failed(self) -> bool:
        return self.run_decision is RunFailureDecision.REQUIRED_STEP_FAILED

    @property
    def requires_explicit_control(self) -> bool:
        return self.continuation is not FailureContinuation.NONE


_CONTINUATION_MODES: dict[str, FailureContinuation] = {
    "RETRY": FailureContinuation.RETRY,
    "RETRYABLE": FailureContinuation.RETRY,
    "FALLBACK": FailureContinuation.FALLBACK,
    "DEGRADED": FailureContinuation.FALLBACK,
    "PARTIAL": FailureContinuation.PARTIAL_RESULT,
    "PARTIAL_RESULT": FailureContinuation.PARTIAL_RESULT,
    "ERROR_ACCUMULATION": FailureContinuation.ERROR_ACCUMULATION,
    "ACCUMULATE_ERRORS": FailureContinuation.ERROR_ACCUMULATION,
    "SUCCESSOR_MATERIALIZATION": FailureContinuation.SUCCESSOR_MATERIALIZATION,
}
_NON_CONTINUATION_FAILURE_MODES = frozenset({"FAILED", "OUTCOME_UNKNOWN"})


def _normalized_modes(values: tuple[str, ...], *, owner: str) -> tuple[str, ...]:
    if not values:
        raise FailurePolicyDerivationError(f"{owner} failure_modes are empty")
    normalized: list[str] = []
    for raw in values:
        if not isinstance(raw, str) or not raw.strip():
            raise FailurePolicyDerivationError(
                f"{owner} failure_modes contain a non-canonical value"
            )
        value = raw.strip().upper().replace("-", "_")
        if value in normalized:
            raise FailurePolicyDerivationError(
                f"{owner} failure_modes contain duplicate {value}"
            )
        if (
            value not in _NON_CONTINUATION_FAILURE_MODES
            and value not in _CONTINUATION_MODES
        ):
            raise FailurePolicyDerivationError(
                f"{owner} failure mode is not frozen for run aggregation: {value}"
            )
        normalized.append(value)
    return tuple(normalized)


def _profile_ref(value: object) -> FrozenFailureProfileRef:
    if isinstance(value, str):
        if not value or value != value.strip():
            raise FailurePolicyDerivationError(
                "failure_profile_ref must be a canonical non-empty reference"
            )
        return FrozenFailureProfileRef("OPAQUE", value, None, None)
    if isinstance(value, ContractProfileRef):
        ref = value
    elif isinstance(value, Mapping):
        if set(value) != {"profile_id", "profile_version", "profile_digest"}:
            raise FailurePolicyDerivationError(
                "failure_profile_ref mapping is not the exact frozen ref shape"
            )
        try:
            ref = ContractProfileRef(
                profile_id=value["profile_id"],
                profile_version=value["profile_version"],
                profile_digest=value["profile_digest"],
            )
        except Exception as exc:
            raise FailurePolicyDerivationError(
                "failure_profile_ref content-addressed identity is invalid"
            ) from exc
    else:
        raise FailurePolicyDerivationError("step lacks a frozen failure_profile_ref")
    if not ref.profile_id or not ref.profile_version:
        raise FailurePolicyDerivationError(
            "failure_profile_ref content-addressed identity is incomplete"
        )
    return FrozenFailureProfileRef(
        "CONTENT_ADDRESSED",
        ref.profile_id,
        ref.profile_version,
        ref.profile_digest,
    )


def _exact_steps(plan: ExecutionPlan) -> dict[str, CompiledStep]:
    steps = {step.step_id: step for step in plan.ordered_steps}
    if len(steps) != len(plan.ordered_steps):
        raise FailurePolicyDerivationError("ExecutionPlan contains duplicate step IDs")
    dependency_entries = dict(plan.dependency_index.entries)
    if len(dependency_entries) != len(plan.dependency_index.entries):
        raise FailurePolicyDerivationError(
            "ExecutionPlan dependency index contains duplicate step IDs"
        )
    if set(dependency_entries) != set(steps):
        raise FailurePolicyDerivationError(
            "ExecutionPlan dependency index does not cover exact steps"
        )
    for step_id, step in steps.items():
        if tuple(dependency_entries[step_id]) != step.dependencies:
            raise FailurePolicyDerivationError(
                f"ExecutionPlan dependency index drift for {step_id}"
            )
        unknown = set(step.dependencies) - set(steps)
        if unknown:
            raise FailurePolicyDerivationError(
                f"ExecutionPlan step {step_id} has unknown dependencies"
            )
    return steps


def _require_control_digests(node: CompiledControlNode) -> None:
    try:
        node.require_valid_control_digest()
    except ValueError as exc:
        raise FailurePolicyDerivationError(
            "ExecutionPlan control digest drift"
        ) from exc
    for child in node.children:
        _require_control_digests(child)


def _required_step_ids(
    plan: ExecutionPlan, steps: Mapping[str, CompiledStep]
) -> tuple[str, ...]:
    policy = plan.completion_policy
    if (
        policy.mode != "SEMANTIC_RETURN_BARRIERS"
        or policy.branch_mode != "SELECTED_BRANCH_ONLY"
        or policy.ordered is not True
    ):
        raise FailurePolicyDerivationError(
            "CompletionPolicy is not the frozen semantic-return policy"
        )
    barriers = tuple(plan.return_policy.exported_barrier_step_ids)
    if not barriers:
        raise FailurePolicyDerivationError(
            "failure derivation requires at least one exported return barrier"
        )
    if len(set(barriers)) != len(barriers) or set(barriers) - set(steps):
        raise FailurePolicyDerivationError(
            "ExecutionPlan exported barrier closure is invalid"
        )

    required: set[str] = set()
    visiting: set[str] = set()

    def include(step_id: str) -> None:
        if step_id in required:
            return
        if step_id in visiting:
            raise FailurePolicyDerivationError(
                "ExecutionPlan dependency closure contains a cycle"
            )
        visiting.add(step_id)
        for dependency in steps[step_id].dependencies:
            include(dependency)
        visiting.remove(step_id)
        required.add(step_id)

    for barrier in barriers:
        include(barrier)
    return tuple(
        step.step_id for step in plan.ordered_steps if step.step_id in required
    )


def _require_qualified_closure(
    plan: ExecutionPlan,
    qualified_plan: QualifiedPlan,
    steps: Mapping[str, CompiledStep],
) -> dict[str, object]:
    if (
        canonical_digest(qualified_plan, exclude_fields={"qualification_digest"})
        != qualified_plan.qualification_digest
    ):
        raise FailurePolicyDerivationError("QualifiedPlan content digest drift")
    if qualified_plan.plan_digest != plan.plan_digest:
        raise FailurePolicyDerivationError(
            "QualifiedPlan does not bind the exact ExecutionPlan"
        )
    if qualified_plan.awaiting_approval_steps or qualified_plan.denied_steps:
        raise FailurePolicyDerivationError(
            "qualified failure derivation cannot use awaiting or denied steps"
        )
    bindings = {binding.step_id: binding for binding in qualified_plan.step_bindings}
    if len(bindings) != len(qualified_plan.step_bindings):
        raise FailurePolicyDerivationError(
            "QualifiedPlan contains duplicate step bindings"
        )
    authorizable = {
        step_id: step
        for step_id, step in steps.items()
        if step.step_kind in {"EFFECT", "ADMISSION"}
        and step.operation_contract_ref is not None
    }
    if set(bindings) != set(authorizable):
        raise FailurePolicyDerivationError(
            "QualifiedPlan membership differs from exact authorizable plan steps"
        )
    run_ids = {binding.run_id for binding in qualified_plan.step_bindings}
    project_keys = {binding.project_key for binding in qualified_plan.step_bindings}
    if len(run_ids) != 1 or len(project_keys) != 1:
        raise FailurePolicyDerivationError(
            "QualifiedPlan step membership is not one run/project closure"
        )
    for step_id, step in authorizable.items():
        binding = bindings[step_id]
        if (
            canonical_digest(binding, exclude_fields={"binding_digest"})
            != binding.binding_digest
        ):
            raise FailurePolicyDerivationError(
                f"QualifiedPlan authorization digest drift for {step_id}"
            )
        contract_ref = step.operation_contract_ref
        assert contract_ref is not None
        if (
            binding.operation_kind != contract_ref.kind
            or binding.operation_contract_digest != contract_ref.contract_digest
        ):
            raise FailurePolicyDerivationError(
                f"QualifiedPlan operation binding drift for {step_id}"
            )
    return bindings


def _continuation(
    step_modes: tuple[str, ...], plan_modes: tuple[str, ...]
) -> FailureContinuation:
    candidates = {
        _CONTINUATION_MODES[mode]
        for mode in (*step_modes, *plan_modes)
        if mode in _CONTINUATION_MODES
    }
    if len(candidates) > 1:
        raise FailurePolicyDerivationError(
            "frozen failure policy has multiple unresolved continuation strategies"
        )
    return next(iter(candidates), FailureContinuation.NONE)


def derive_failure_policy(
    plan: ExecutionPlan,
    qualified_plan: QualifiedPlan,
    step_id: str,
) -> FailurePolicyDecision:
    """Derive run aggregation eligibility from exact persisted contracts.

    A ``CONTINUE`` result with a non-``NONE`` continuation is not execution
    authority.  The caller must still obtain the separately frozen retry,
    fallback, accumulation, or materialization control event.
    """

    if not step_id:
        raise FailurePolicyDerivationError("failure derivation requires step_id")
    if with_plan_digest(plan).plan_digest != plan.plan_digest:
        raise FailurePolicyDerivationError("ExecutionPlan structural digest drift")
    _require_control_digests(plan.control_root)

    steps = _exact_steps(plan)
    step = steps.get(step_id)
    if step is None:
        raise FailurePolicyDerivationError(
            f"step is absent from ExecutionPlan: {step_id}"
        )
    bindings = _require_qualified_closure(plan, qualified_plan, steps)
    binding = bindings.get(step_id)
    if binding is None:
        raise FailurePolicyDerivationError(
            f"step is absent from QualifiedPlan membership: {step_id}"
        )

    required_ids = _required_step_ids(plan, steps)
    step_modes = _normalized_modes(step.return_contract.failure_modes, owner="step")
    plan_modes = _normalized_modes(plan.return_policy.failure_modes, owner="plan")
    if "FAILED" not in step_modes:
        raise FailurePolicyDerivationError(
            "EffectFailed is not declared by the exact step ReturnContract"
        )
    continuation = _continuation(step_modes, plan_modes)
    if "FAILED" not in plan_modes and continuation is FailureContinuation.NONE:
        raise FailurePolicyDerivationError(
            "plan failure policy neither accepts FAILED nor declares continuation"
        )

    required = step_id in required_ids
    fatal = required and continuation is FailureContinuation.NONE
    run_decision = (
        RunFailureDecision.REQUIRED_STEP_FAILED
        if fatal
        else RunFailureDecision.CONTINUE
    )
    profile = _profile_ref(step.failure_profile_ref)
    payload = {
        "schema": "mrw.runtime.failure-policy-decision.v1",
        "run_id": binding.run_id,
        "step_id": step_id,
        "plan_digest": plan.plan_digest,
        "qualification_digest": qualified_plan.qualification_digest,
        "qualified": True,
        "required": required,
        "fatal": fatal,
        "may_continue": not fatal,
        "continuation": continuation.value,
        "run_decision": run_decision.value,
        "completion_policy_mode": plan.completion_policy.mode,
        "required_step_ids": required_ids,
        "step_failure_modes": step_modes,
        "plan_failure_modes": plan_modes,
        "failure_profile_ref": profile,
    }
    return FailurePolicyDecision(
        run_id=binding.run_id,
        step_id=step_id,
        plan_digest=plan.plan_digest,
        qualification_digest=qualified_plan.qualification_digest,
        qualified=True,
        required=required,
        fatal=fatal,
        may_continue=not fatal,
        continuation=continuation,
        run_decision=run_decision,
        completion_policy_mode=plan.completion_policy.mode,
        required_step_ids=required_ids,
        step_failure_modes=step_modes,
        plan_failure_modes=plan_modes,
        failure_profile_ref=profile,
        decision_digest=sha256_hex(payload),
    )


__all__ = [
    "FailureContinuation",
    "FailurePolicyDecision",
    "FailurePolicyDerivationError",
    "FrozenFailureProfileRef",
    "RunFailureDecision",
    "derive_failure_policy",
]
