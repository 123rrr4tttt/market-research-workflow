from __future__ import annotations

# ruff: noqa: TRY003

from dataclasses import asdict, dataclass, replace
from datetime import datetime
from collections.abc import Iterable, Mapping
from typing import Literal

from .alerts import AlertEvaluation, AlertRule, evaluate_alert_rule
from .errors import ObservabilityTypeError, ObservabilityValueError
from .contracts import (
    AlertState,
    AlertTransition,
    AlertTransitionReason,
    CanaryRouteAction,
    CANARY_ROUTE_DECISION_CONTRACT_VERSION,
    ContinuityReason,
    ReceiptScope,
    StopReason,
)
from .observations import Observation
from .receipts import ReceiptValidationCode, ObservationReceipt, validate_production_receipt


@dataclass(frozen=True)
class StopRequest:
    request_id: str
    requested_by: str
    requested_at: datetime | str
    release_version: str
    reason: str

    def __post_init__(self) -> None:
        if not self.request_id.strip() or not self.requested_by.strip():
            raise ObservabilityValueError("stop request identity is required")
        if not self.release_version.strip() or not self.reason.strip():
            raise ObservabilityValueError("stop release_version and reason are required")
        from .observations import parse_observed_at

        object.__setattr__(self, "requested_at", parse_observed_at(self.requested_at))

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ContinueRequest:
    requested_by: str
    requested_at: datetime | str
    release_version: str
    reason: ContinuityReason

    def __post_init__(self) -> None:
        if not self.requested_by.strip():
            raise ObservabilityValueError("continue requested_by is required")
        if not self.release_version.strip():
            raise ObservabilityValueError("continue release_version is required")
        if not isinstance(self.reason, ContinuityReason):
            raise ObservabilityTypeError("continue reason is closed")
        from .observations import parse_observed_at

        object.__setattr__(self, "requested_at", parse_observed_at(self.requested_at))

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CanaryRouteDecision:
    contract_version: str
    action: CanaryRouteAction
    promotion_allowed: bool
    stop_reason: StopReason | None
    precedence: tuple[StopReason, ...]
    receipt_scope: ReceiptScope | None
    receipt_valid: bool
    receipt_validation: tuple[ReceiptValidationCode, ...]
    alert_evaluations: tuple[AlertEvaluation, ...]
    authority: Literal[False]
    derived_as: str

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise ObservabilityTypeError("CanaryRouteDecision is a closed view type")

    def __post_init__(self) -> None:
        if self.authority is not False:
            raise ObservabilityTypeError("decision authority is permanently false")
        if self.derived_as != "view":
            raise ObservabilityValueError("decision derived_as must remain view")

    def to_dict(self) -> dict:
        return asdict(self)


def decide_canary_route(
    *,
    domain: str,
    route: str,
    release_version: str,
    observations: Iterable[Observation],
    alert_rules: Iterable[AlertRule],
    production_receipt: ObservationReceipt | None = None,
    explicit_stop: StopRequest | None = None,
    continue_request: ContinueRequest | None = None,
    previous_alert_states: Mapping[str, AlertState] | None = None,
) -> CanaryRouteDecision:
    normalized_domain = domain.strip().lower()
    normalized_route = route.strip().lower()
    normalized_release = release_version.strip()
    observation_items = tuple(observations)
    if not normalized_domain or not normalized_route or not normalized_release:
        raise ObservabilityValueError("decision domain, route, and release_version are required")

    precedence: list[StopReason] = []
    if explicit_stop is not None:
        if explicit_stop.release_version != normalized_release:
            raise ObservabilityValueError("explicit stop release_version mismatch")
        precedence.append(StopReason.EXPLICIT_STOP)

    receipt_validation: tuple[ReceiptValidationCode, ...] = (ReceiptValidationCode.CONTRACT_VERSION_INVALID,)
    if production_receipt is not None:
        receipt_validation = validate_production_receipt(
            production_receipt,
            observations=observation_items,
        )
        if receipt_validation != (ReceiptValidationCode.VALID,):
            if ReceiptValidationCode.WRONG_SCOPE in receipt_validation:
                precedence.append(StopReason.RECEIPT_SCOPE_NOT_PRODUCTION)
            elif set(receipt_validation).intersection(
                {
                    ReceiptValidationCode.CONTRACT_VERSION_INVALID,
                    ReceiptValidationCode.ARTIFACT_KIND_INVALID,
                    ReceiptValidationCode.ISSUER_MISSING,
                    ReceiptValidationCode.SOURCE_REF_MISSING,
                }
            ):
                precedence.append(StopReason.RECEIPT_CONTRACT_INVALID)
            else:
                precedence.append(StopReason.RECEIPT_BINDING_INVALID)

    production_receipt_valid = production_receipt is not None and receipt_validation == (ReceiptValidationCode.VALID,)
    # Runtime observations may always tighten the route by triggering a stop.
    # A valid production receipt is still required for CONTINUE, so an
    # unreceipted observation can never create promotion authority.
    receipt_bound_ids = (
        set(production_receipt.observation_ids) if production_receipt_valid else set()
    )
    usable_observations = tuple(
        observation
        for observation in observation_items
        if observation.domain == normalized_domain
        and observation.route == normalized_route
        and observation.release_version == normalized_release
        and (not production_receipt_valid or observation.observation_id in receipt_bound_ids)
    )

    previous_states = {} if previous_alert_states is None else dict(previous_alert_states)
    for state in previous_states.values():
        if not isinstance(state, AlertState):
            raise ObservabilityTypeError("previous alert state is closed")
    alert_evaluation_items: list[AlertEvaluation] = []
    for rule in alert_rules:
        previous_state = previous_states.get(rule.rule_id, AlertState.UNKNOWN)
        evaluation = evaluate_alert_rule(
            rule,
            usable_observations,
            previous_state=previous_state,
        )
        if (
            not production_receipt_valid
            and previous_state is AlertState.TRIGGERED
            # Absent observations stay unknown; only observed recovery is gated.
            and evaluation.observed_count > 0
            and evaluation.state is not AlertState.TRIGGERED
        ):
            evaluation = replace(
                evaluation,
                state=AlertState.TRIGGERED,
                transition=AlertTransition.NO_TRANSITION,
                reason=AlertTransitionReason.STILL_TRIGGERED,
            )
        alert_evaluation_items.append(evaluation)
    alert_evaluations = tuple(alert_evaluation_items)
    if any(evaluation.state.value == "triggered" for evaluation in alert_evaluations):
        precedence.append(StopReason.ALERT_TRIGGERED)

    if precedence:
        stop_reason = precedence[0]
        action = (
            CanaryRouteAction.ROLLBACK
            if any(
                reason in {StopReason.EXPLICIT_STOP, StopReason.ALERT_TRIGGERED}
                for reason in precedence
            )
            else CanaryRouteAction.HOLD
        )
        return CanaryRouteDecision(
            contract_version=CANARY_ROUTE_DECISION_CONTRACT_VERSION,
            action=action,
            promotion_allowed=False,
            stop_reason=stop_reason,
            precedence=tuple(precedence),
            receipt_scope=production_receipt.scope if production_receipt is not None else None,
            receipt_valid=production_receipt_valid,
            receipt_validation=receipt_validation,
            alert_evaluations=alert_evaluations,
            authority=False,
            derived_as="view",
        )

    if production_receipt is None:
        precedence.append(StopReason.MISSING_PRODUCTION_RECEIPT)
    elif not usable_observations:
        precedence.append(StopReason.NO_PRODUCTION_OBSERVATIONS)
    elif any(evaluation.state.value == "unknown" for evaluation in alert_evaluations):
        precedence.append(StopReason.ALERT_EVALUATION_UNKNOWN)
    elif continue_request is None:
        precedence.append(StopReason.CONTINUE_NOT_REQUESTED)
    else:
        if continue_request.release_version != normalized_release:
            raise ObservabilityValueError("continue release_version mismatch")
        if continue_request.reason not in set(ContinuityReason):
            raise ObservabilityValueError("continue reason is closed")

    if precedence:
        action = CanaryRouteAction.HOLD
        promotion_allowed = False
    else:
        action = CanaryRouteAction.CONTINUE
        promotion_allowed = True
    return CanaryRouteDecision(
        contract_version=CANARY_ROUTE_DECISION_CONTRACT_VERSION,
        action=action,
        promotion_allowed=promotion_allowed,
        stop_reason=precedence[0] if precedence else StopReason.NO_STOP_CONDITION,
        precedence=tuple(precedence) if precedence else (StopReason.NO_STOP_CONDITION,),
        receipt_scope=production_receipt.scope if production_receipt is not None else None,
        receipt_valid=production_receipt_valid,
        receipt_validation=receipt_validation,
        alert_evaluations=alert_evaluations,
        authority=False,
        derived_as="view",
    )


__all__ = [
    "CanaryRouteAction",
    "CanaryRouteDecision",
    "ContinueRequest",
    "StopRequest",
    "decide_canary_route",
]
