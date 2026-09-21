# ruff: noqa: E501
"""Pure persisted-plan failure policy derivation.

The reducer owns state transitions; this module only proves whether a failed
step is a required semantic-return dependency and whether the exact frozen
plan permits the run to continue.  It performs no database access and never
authorizes retry, fallback, or successor materialization by itself.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal, NoReturn, Protocol, runtime_checkable

from functorial_kit import Failure

from mrw_functorial_kit.core.w07_semantics import runtime_failures
from pydantic import BaseModel

from app.successor_runtime.research.codec import sha256_hex

if TYPE_CHECKING:
    from app.successor_runtime.language.plan import (
        CompiledControlNode,
        CompiledStep,
        ExecutionPlan,
    )


_EXCLUDE_FIELDS_MAPPING_REQUIRED = (
    "exclude_fields is only valid for model or mapping digests"
)


def canonical_digest(
    value: BaseModel | dict[str, object] | tuple[object, ...],
    *,
    exclude_fields: Collection[str] = (),
) -> str:
    """Return the deterministic sha256 digest used by identity contracts."""

    if isinstance(value, BaseModel):
        payload = value.model_dump(
            mode="json",
            exclude=set(exclude_fields),
            exclude_none=False,
        )
    else:
        payload = value
        if exclude_fields:
            if not isinstance(payload, dict):
                # kit:boundary owner=successor.runtime.canonical_digest class=PROGRAMMER_DEFECT failure_family=none witness=test:test_canonical_digest_rejects_exclude_fields_for_non_mapping
                raise TypeError(_EXCLUDE_FIELDS_MAPPING_REQUIRED)
            payload = {
                key: item for key, item in payload.items() if key not in exclude_fields
            }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@runtime_checkable
class _QualifiedPlanLike(Protocol):
    """Runtime shape needed by failure derivation without importing qualification."""

    plan_digest: str
    qualification_digest: str
    awaiting_approval_steps: tuple[Any, ...]
    denied_steps: tuple[Any, ...]
    step_bindings: tuple[Any, ...]


class FailurePolicyDerivationError(ValueError):
    """The persisted plan/qualification cannot prove a failure decision."""


def _policy_failure(message: object, *, site: str) -> Failure:
    return runtime_failure(
        "FAILURE_POLICY_INVALID",
        message,
        FailurePolicyDerivationError,
        site=site,
        context={
            "owner": "successor_runtime.runtime.failure_policy",
            "operation": site,
        },
    )


_RUNTIME_FAILURE_WITNESS = "test:test_w07_runtime_failure_lift_context"
_RUNTIME_FAILURE_CONTEXT_KEYS = frozenset(
    {
        "public_exception",
        "public_argument",
        "public_message",
        "site",
        "witness",
    }
)


@dataclass(frozen=True, slots=True)
class RuntimeFailure(Failure):
    """Failure value with the exact process-local public exception ABI."""

    exception_type: type[Exception] = field(kw_only=True)


def _closed_failure(message: object, *, site: str) -> Failure:
    """Create a typed validation failure without relying on a public ABI."""

    text = str(message)
    return runtime_failures.fail(
        "FAILURE_POLICY_INVALID",
        text,
        {
            "public_exception": "TypeError",
            "public_argument": text,
            "public_message": text,
            "site": site,
            "witness": _RUNTIME_FAILURE_WITNESS,
        },
    )


def _canonical_digest(value: object, *, exclude_fields: set[str]) -> str | Failure:
    try:
        return canonical_digest(value, exclude_fields=exclude_fields)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError, KeyError, AttributeError) as exc:
        return _policy_failure(str(exc), site="successor_runtime.runtime.failure_policy.digest")


def _require_exception_type(exception_type: object) -> type[Exception] | Failure:
    if not isinstance(exception_type, type) or not issubclass(exception_type, Exception):
        return _closed_failure(
            "runtime failure exception_type must be an Exception class",
            site="successor_runtime.runtime.failure_policy.exception_type",
        )
    return exception_type


def _require_site(site: object) -> str | Failure:
    if not isinstance(site, str) or not site.strip():
        return _closed_failure(
            "runtime failure site must be a non-empty string",
            site="successor_runtime.runtime.failure_policy.site",
        )
    return site.strip()


def _require_context(
    context: Mapping[str, object] | None, *, site: str
) -> dict[str, object] | Failure:
    if context is not None and not isinstance(context, Mapping):
        return _closed_failure("runtime failure context must be a mapping", site=site)
    supplied = dict(context or {})
    if not all(isinstance(key, str) for key in supplied):
        return _closed_failure(
            "runtime failure context keys must be strings", site=site
        )
    conflicts = _RUNTIME_FAILURE_CONTEXT_KEYS.intersection(supplied)
    if conflicts:
        names = ", ".join(sorted(conflicts))
        return _closed_failure(
            f"runtime failure context reserves canonical keys: {names}", site=site
        )
    return supplied


def _raise_legacy_exception(
    exception_type: type[Exception], argument: object, cause: BaseException | None = None
) -> NoReturn:
    """Single compatibility boundary for the retained exception ABI."""

    if cause is None:
        # kit:boundary owner=successor.runtime.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.runtime.failure witness=test:test_w07_runtime_failure_lift_context
        raise exception_type(argument)
    # kit:boundary owner=successor.runtime.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.runtime.failure witness=test:test_w07_runtime_failure_lift_context
    raise exception_type(argument) from cause


def _raise_programmer_type_error(
    argument: object, cause: BaseException | None = None
) -> NoReturn:
    """Reject malformed ABI inputs at the programmer-defect boundary."""

    if cause is None:
        # kit:boundary owner=successor.runtime.failure_lift.validation class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w07_runtime_failure_lift_context
        raise TypeError(argument)
    # kit:boundary owner=successor.runtime.failure_lift.validation class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w07_runtime_failure_lift_context
    raise TypeError(argument) from cause


def _raise_legacy_type_error(failure: Failure) -> NoReturn:
    _raise_programmer_type_error(failure.message)


def runtime_failure(
    code: str,
    message: object,
    exception_type: type[Exception],
    *,
    site: str,
    context: Mapping[str, object] | None = None,
) -> Failure:
    """Construct one closed runtime failure without interpreting messages."""

    checked_type = _require_exception_type(exception_type)
    if isinstance(checked_type, Failure):
        _raise_legacy_type_error(checked_type)
    checked_site = _require_site(site)
    if isinstance(checked_site, Failure):
        _raise_legacy_type_error(checked_site)
    supplied = _require_context(context, site=checked_site)
    if isinstance(supplied, Failure):
        _raise_legacy_type_error(supplied)
    try:
        public_message = str(checked_type(message))
    except (TypeError, ValueError, OverflowError, KeyError, AttributeError) as exc:
        _raise_programmer_type_error(str(exc), exc)
    payload: dict[str, object] = {
        "public_exception": checked_type.__name__,
        "public_argument": message,
        "public_message": public_message,
        "site": checked_site,
        "witness": _RUNTIME_FAILURE_WITNESS,
        **supplied,
    }
    failure = runtime_failures.fail(code, public_message, payload)
    return RuntimeFailure(
        family=failure.family,
        code=failure.code,
        message=failure.message,
        context=failure.context,
        exception_type=checked_type,
    )


def raise_runtime_failure(
    failure: Failure,
    exception_type: type[Exception],
    *,
    cause: BaseException | None = None,
) -> NoReturn:
    """Lift a typed runtime failure at an existing public ABI boundary."""

    checked_type = _require_exception_type(exception_type)
    if isinstance(checked_type, Failure):
        _raise_legacy_type_error(checked_type)
    if not isinstance(failure, Failure):
        _raise_programmer_type_error(
            "runtime failure lift context is incomplete or inconsistent"
        )
    if cause is not None and not isinstance(cause, BaseException):
        _raise_programmer_type_error("runtime failure cause must be a BaseException")
    payload = failure.context or {}
    required = _RUNTIME_FAILURE_CONTEXT_KEYS
    exact_exception_type = getattr(failure, "exception_type", None)
    if exact_exception_type is not None:
        if (
            not isinstance(exact_exception_type, type)
            or not issubclass(exact_exception_type, Exception)
            or exact_exception_type.__name__ != payload.get("public_exception")
        ):
            _raise_programmer_type_error(
                "runtime failure lift context is incomplete or inconsistent"
            )
        checked_type = exact_exception_type
    if (
        not runtime_failures.matches(failure)
        or not isinstance(failure.context, Mapping)
        or required - set(payload)
        or payload.get("public_exception") != checked_type.__name__
        or payload.get("public_message") != failure.message
        or not isinstance(payload.get("site"), str)
        or not str(payload.get("site")).strip()
        or payload.get("witness") != _RUNTIME_FAILURE_WITNESS
    ):
        _raise_programmer_type_error(
            "runtime failure lift context is incomplete or inconsistent"
        )
    argument = payload["public_argument"]
    try:
        expected_message = str(checked_type(argument))
    except (TypeError, ValueError, OverflowError, KeyError, AttributeError) as exc:
        _raise_programmer_type_error(
            "runtime failure lift context is incomplete or inconsistent", exc
        )
    if expected_message != failure.message:
        _raise_programmer_type_error(
            "runtime failure lift context is incomplete or inconsistent"
        )
    _raise_legacy_exception(checked_type, argument, cause)


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


def _normalized_modes(
    values: tuple[str, ...], *, owner: str
) -> tuple[str, ...] | Failure:
    if not values:
        return _policy_failure(
            f"{owner} failure_modes are empty",
            site="successor_runtime.runtime.failure_policy.modes",
        )
    normalized: list[str] = []
    for raw in values:
        if not isinstance(raw, str) or not raw.strip():
            return _policy_failure(
                f"{owner} failure_modes contain a non-canonical value",
                site="successor_runtime.runtime.failure_policy.modes",
            )
        value = raw.strip().upper().replace("-", "_")
        if value in normalized:
            return _policy_failure(
                f"{owner} failure_modes contain duplicate {value}",
                site="successor_runtime.runtime.failure_policy.modes",
            )
        if (
            value not in _NON_CONTINUATION_FAILURE_MODES
            and value not in _CONTINUATION_MODES
        ):
            return _policy_failure(
                f"{owner} failure mode is not frozen for run aggregation: {value}",
                site="successor_runtime.runtime.failure_policy.modes",
            )
        normalized.append(value)
    return tuple(normalized)


def _profile_ref(value: object) -> FrozenFailureProfileRef | Failure:
    from app.successor_runtime.language.profiles import ContractProfileRef

    if isinstance(value, str):
        if not value or value != value.strip():
            return _policy_failure(
                "failure_profile_ref must be a canonical non-empty reference",
                site="successor_runtime.runtime.failure_policy.profile_ref",
            )
        return FrozenFailureProfileRef("OPAQUE", value, None, None)
    if isinstance(value, ContractProfileRef):
        ref = value
    elif isinstance(value, Mapping):
        if set(value) != {"profile_id", "profile_version", "profile_digest"}:
            return _policy_failure(
                "failure_profile_ref mapping is not the exact frozen ref shape",
                site="successor_runtime.runtime.failure_policy.profile_ref",
            )
        try:
            ref = ContractProfileRef(
                profile_id=value["profile_id"],
                profile_version=value["profile_version"],
                profile_digest=value["profile_digest"],
            )
        except (TypeError, ValueError, OverflowError, KeyError, AttributeError):
            return _policy_failure(
                "failure_profile_ref content-addressed identity is invalid",
                site="successor_runtime.runtime.failure_policy.profile_ref",
            )
    else:
        return _policy_failure(
            "step lacks a frozen failure_profile_ref",
            site="successor_runtime.runtime.failure_policy.profile_ref",
        )
    if not ref.profile_id or not ref.profile_version:
        return _policy_failure(
            "failure_profile_ref content-addressed identity is incomplete",
            site="successor_runtime.runtime.failure_policy.profile_ref",
        )
    return FrozenFailureProfileRef(
        "CONTENT_ADDRESSED",
        ref.profile_id,
        ref.profile_version,
        ref.profile_digest,
    )


def _exact_steps(plan: ExecutionPlan) -> dict[str, CompiledStep] | Failure:
    steps = {step.step_id: step for step in plan.ordered_steps}
    if len(steps) != len(plan.ordered_steps):
        return _policy_failure(
            "ExecutionPlan contains duplicate step IDs",
            site="successor_runtime.runtime.failure_policy.plan",
        )
    dependency_entries = dict(plan.dependency_index.entries)
    if len(dependency_entries) != len(plan.dependency_index.entries):
        return _policy_failure(
            "ExecutionPlan dependency index contains duplicate step IDs",
            site="successor_runtime.runtime.failure_policy.plan",
        )
    if set(dependency_entries) != set(steps):
        return _policy_failure(
            "ExecutionPlan dependency index does not cover exact steps",
            site="successor_runtime.runtime.failure_policy.plan",
        )
    for step_id, step in steps.items():
        if tuple(dependency_entries[step_id]) != step.dependencies:
            return _policy_failure(
                f"ExecutionPlan dependency index drift for {step_id}",
                site="successor_runtime.runtime.failure_policy.plan",
            )
        unknown = set(step.dependencies) - set(steps)
        if unknown:
            return _policy_failure(
                f"ExecutionPlan step {step_id} has unknown dependencies",
                site="successor_runtime.runtime.failure_policy.plan",
            )
    return steps


def _require_control_digests(node: CompiledControlNode) -> None | Failure:
    try:
        node.require_valid_control_digest()
    except (TypeError, ValueError, OverflowError, KeyError, AttributeError):
        return _policy_failure(
            "ExecutionPlan control digest drift",
            site="successor_runtime.runtime.failure_policy.plan",
        )
    for child in node.children:
        result = _require_control_digests(child)
        if isinstance(result, Failure):
            return result
    return None


def _required_step_ids(
    plan: ExecutionPlan, steps: Mapping[str, CompiledStep]
) -> tuple[str, ...] | Failure:
    policy = plan.completion_policy
    if (
        policy.mode != "SEMANTIC_RETURN_BARRIERS"
        or policy.branch_mode != "SELECTED_BRANCH_ONLY"
        or policy.ordered is not True
    ):
        return _policy_failure(
            "CompletionPolicy is not the frozen semantic-return policy",
            site="successor_runtime.runtime.failure_policy.policy",
        )
    barriers = tuple(plan.return_policy.exported_barrier_step_ids)
    if not barriers:
        return _policy_failure(
            "failure derivation requires at least one exported return barrier",
            site="successor_runtime.runtime.failure_policy.policy",
        )
    if len(set(barriers)) != len(barriers) or set(barriers) - set(steps):
        return _policy_failure(
            "ExecutionPlan exported barrier closure is invalid",
            site="successor_runtime.runtime.failure_policy.policy",
        )

    required: set[str] = set()
    visiting: set[str] = set()

    def include(step_id: str) -> None | Failure:
        if step_id in required:
            return
        if step_id in visiting:
            return _policy_failure(
                "ExecutionPlan dependency closure contains a cycle",
                site="successor_runtime.runtime.failure_policy.policy",
            )
        visiting.add(step_id)
        for dependency in steps[step_id].dependencies:
            result = include(dependency)
            if isinstance(result, Failure):
                return result
        visiting.remove(step_id)
        required.add(step_id)

    for barrier in barriers:
        result = include(barrier)
        if isinstance(result, Failure):
            return result
    return tuple(
        step.step_id for step in plan.ordered_steps if step.step_id in required
    )


def _require_qualified_closure(
    plan: ExecutionPlan,
    qualified_plan: _QualifiedPlanLike,
    steps: Mapping[str, CompiledStep],
) -> dict[str, object] | Failure:
    qualification_digest = _canonical_digest(
        qualified_plan, exclude_fields={"qualification_digest"}
    )
    if isinstance(qualification_digest, Failure):
        return qualification_digest
    if qualification_digest != qualified_plan.qualification_digest:
        return _policy_failure(
            "QualifiedPlan content digest drift",
            site="successor_runtime.runtime.failure_policy.qualification",
        )
    if qualified_plan.plan_digest != plan.plan_digest:
        return _policy_failure(
            "QualifiedPlan does not bind the exact ExecutionPlan",
            site="successor_runtime.runtime.failure_policy.qualification",
        )
    if qualified_plan.awaiting_approval_steps or qualified_plan.denied_steps:
        return _policy_failure(
            "qualified failure derivation cannot use awaiting or denied steps",
            site="successor_runtime.runtime.failure_policy.qualification",
        )
    bindings = {binding.step_id: binding for binding in qualified_plan.step_bindings}
    if len(bindings) != len(qualified_plan.step_bindings):
        return _policy_failure(
            "QualifiedPlan contains duplicate step bindings",
            site="successor_runtime.runtime.failure_policy.qualification",
        )
    authorizable = {
        step_id: step
        for step_id, step in steps.items()
        if step.step_kind in {"EFFECT", "ADMISSION"}
        and step.operation_contract_ref is not None
    }
    if set(bindings) != set(authorizable):
        return _policy_failure(
            "QualifiedPlan membership differs from exact authorizable plan steps",
            site="successor_runtime.runtime.failure_policy.qualification",
        )
    run_ids = {binding.run_id for binding in qualified_plan.step_bindings}
    project_keys = {binding.project_key for binding in qualified_plan.step_bindings}
    if len(run_ids) != 1 or len(project_keys) != 1:
        return _policy_failure(
            "QualifiedPlan step membership is not one run/project closure",
            site="successor_runtime.runtime.failure_policy.qualification",
        )
    for step_id, step in authorizable.items():
        binding = bindings[step_id]
        binding_digest = _canonical_digest(binding, exclude_fields={"binding_digest"})
        if isinstance(binding_digest, Failure):
            return binding_digest
        if binding_digest != binding.binding_digest:
            return _policy_failure(
                f"QualifiedPlan authorization digest drift for {step_id}",
                site="successor_runtime.runtime.failure_policy.qualification",
            )
        contract_ref = step.operation_contract_ref
        assert contract_ref is not None
        if (
            binding.operation_kind != contract_ref.kind
            or binding.operation_contract_digest != contract_ref.contract_digest
        ):
            return _policy_failure(
                f"QualifiedPlan operation binding drift for {step_id}",
                site="successor_runtime.runtime.failure_policy.qualification",
            )
    return bindings


def _continuation(
    step_modes: tuple[str, ...], plan_modes: tuple[str, ...]
) -> FailureContinuation | Failure:
    candidates = {
        _CONTINUATION_MODES[mode]
        for mode in (*step_modes, *plan_modes)
        if mode in _CONTINUATION_MODES
    }
    if len(candidates) > 1:
        return _policy_failure(
            "frozen failure policy has multiple unresolved continuation strategies",
            site="successor_runtime.runtime.failure_policy.policy",
        )
    return next(iter(candidates), FailureContinuation.NONE)


def _derive_failure_policy_impl(
    plan: ExecutionPlan,
    qualified_plan: _QualifiedPlanLike,
    step_id: str,
) -> FailurePolicyDecision | Failure:
    """Derive run aggregation eligibility from exact persisted contracts.

    A ``CONTINUE`` result with a non-``NONE`` continuation is not execution
    authority.  The caller must still obtain the separately frozen retry,
    fallback, accumulation, or materialization control event.
    """

    from app.successor_runtime.language.plan import ExecutionPlan, with_plan_digest
    if not step_id:
        return _policy_failure(
            "failure derivation requires step_id",
            site="successor_runtime.runtime.failure_policy.derive",
        )
    if not isinstance(plan, ExecutionPlan):
        return _policy_failure(
            "failure derivation requires an ExecutionPlan",
            site="successor_runtime.runtime.failure_policy.derive",
        )
    if not isinstance(qualified_plan, _QualifiedPlanLike):
        return _policy_failure(
            "failure derivation requires a QualifiedPlan",
            site="successor_runtime.runtime.failure_policy.derive",
        )
    try:
        structural_digest = with_plan_digest(plan).plan_digest
    except (TypeError, ValueError, OverflowError, KeyError, AttributeError) as exc:
        return _policy_failure(
            str(exc), site="successor_runtime.runtime.failure_policy.plan"
        )
    if structural_digest != plan.plan_digest:
        return _policy_failure(
            "ExecutionPlan structural digest drift",
            site="successor_runtime.runtime.failure_policy.plan",
        )
    control_result = _require_control_digests(plan.control_root)
    if isinstance(control_result, Failure):
        return control_result

    steps = _exact_steps(plan)
    if isinstance(steps, Failure):
        return steps
    step = steps.get(step_id)
    if step is None:
        return _policy_failure(
            f"step is absent from ExecutionPlan: {step_id}",
            site="successor_runtime.runtime.failure_policy.plan",
        )
    bindings = _require_qualified_closure(plan, qualified_plan, steps)
    if isinstance(bindings, Failure):
        return bindings
    binding = bindings.get(step_id)
    if binding is None:
        return _policy_failure(
            f"step is absent from QualifiedPlan membership: {step_id}",
            site="successor_runtime.runtime.failure_policy.qualification",
        )

    required_ids = _required_step_ids(plan, steps)
    if isinstance(required_ids, Failure):
        return required_ids
    step_modes = _normalized_modes(step.return_contract.failure_modes, owner="step")
    if isinstance(step_modes, Failure):
        return step_modes
    plan_modes = _normalized_modes(plan.return_policy.failure_modes, owner="plan")
    if isinstance(plan_modes, Failure):
        return plan_modes
    if "FAILED" not in step_modes:
        return _policy_failure(
            "EffectFailed is not declared by the exact step ReturnContract",
            site="successor_runtime.runtime.failure_policy.policy",
        )
    continuation = _continuation(step_modes, plan_modes)
    if isinstance(continuation, Failure):
        return continuation
    if "FAILED" not in plan_modes and continuation is FailureContinuation.NONE:
        return _policy_failure(
            "plan failure policy neither accepts FAILED nor declares continuation",
            site="successor_runtime.runtime.failure_policy.policy",
        )

    required = step_id in required_ids
    fatal = required and continuation is FailureContinuation.NONE
    run_decision = (
        RunFailureDecision.REQUIRED_STEP_FAILED
        if fatal
        else RunFailureDecision.CONTINUE
    )
    profile = _profile_ref(step.failure_profile_ref)
    if isinstance(profile, Failure):
        return profile
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


def derive_failure_policy_result(
    plan: ExecutionPlan,
    qualified_plan: _QualifiedPlanLike,
    step_id: str,
) -> FailurePolicyDecision | Failure:
    """Return a policy decision or a closed W07 runtime failure value."""

    try:
        result = _derive_failure_policy_impl(plan, qualified_plan, step_id)
    except (TypeError, ValueError, OverflowError, KeyError, AttributeError) as exc:
        return _policy_failure(
            str(exc),
            site="successor_runtime.runtime.failure_policy.derive_failure_policy",
        )
    return result


def derive_failure_policy(
    plan: ExecutionPlan,
    qualified_plan: _QualifiedPlanLike,
    step_id: str,
) -> FailurePolicyDecision:
    """Legacy exception ABI over :func:`derive_failure_policy_result`."""

    result = derive_failure_policy_result(plan, qualified_plan, step_id)
    if isinstance(result, Failure):
        raise_runtime_failure(result, FailurePolicyDerivationError)
    return result


__all__ = [
    "FailureContinuation",
    "FailurePolicyDecision",
    "FailurePolicyDerivationError",
    "raise_runtime_failure",
    "runtime_failure",
    "FrozenFailureProfileRef",
    "RunFailureDecision",
    "derive_failure_policy",
    "derive_failure_policy_result",
]
