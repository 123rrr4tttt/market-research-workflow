from __future__ import annotations

# ruff: noqa: TRY003

from dataclasses import asdict, dataclass
from collections.abc import Iterable, Mapping

from .errors import ObservabilityTypeError, ObservabilityValueError
from .contracts import AlertDirection, AlertState, AlertTransition, AlertTransitionReason, MetricFamily
from .observations import Observation


@dataclass(frozen=True)
class AlertRule:
    rule_id: str
    metric_family: MetricFamily
    domain: str
    route: str
    release_version: str
    trigger_threshold: float
    recover_threshold: float
    direction: AlertDirection = AlertDirection.ABOVE

    def __post_init__(self) -> None:
        if not self.rule_id.strip():
            raise ObservabilityValueError("rule_id is required")
        if not isinstance(self.metric_family, MetricFamily):
            raise ObservabilityTypeError("metric_family is closed")
        if not self.domain.strip() or not self.route.strip() or not self.release_version.strip():
            raise ObservabilityValueError("alert rule labels are required")
        if not (0 <= self.trigger_threshold <= 1) or not (0 <= self.recover_threshold <= 1):
            raise ObservabilityValueError("thresholds must be ratios in [0, 1]")
        if self.direction is AlertDirection.ABOVE and self.recover_threshold > self.trigger_threshold:
            raise ObservabilityValueError("above recovery threshold must not exceed trigger threshold")
        if self.direction is AlertDirection.BELOW and self.recover_threshold < self.trigger_threshold:
            raise ObservabilityValueError("below recovery threshold must not precede trigger threshold")

    def to_dict(self) -> dict:
        return asdict(self)

    def matches(self, observation: Observation) -> bool:
        return (
            observation.metric_family is self.metric_family
            and observation.domain == self.domain.strip().lower()
            and observation.route == self.route.strip().lower()
            and observation.release_version == self.release_version.strip()
        )


@dataclass(frozen=True)
class AlertEvaluation:
    rule_id: str
    release_version: str
    state: AlertState
    transition: AlertTransition
    reason: AlertTransitionReason
    observed_count: int
    latest_observation_id: str | None
    latest_value: float | None
    authority: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate_alert_rule(
    rule: AlertRule,
    observations: Iterable[Observation],
    *,
    previous_state: AlertState = AlertState.UNKNOWN,
) -> AlertEvaluation:
    if not isinstance(previous_state, AlertState):
        raise ObservabilityTypeError("previous alert state is closed")
    matching = sorted((item for item in observations if rule.matches(item)), key=lambda item: item.observed_at)
    if not matching:
        return AlertEvaluation(
            rule_id=rule.rule_id,
            release_version=rule.release_version,
            state=AlertState.UNKNOWN,
            transition=AlertTransition.UNKNOWN,
            reason=AlertTransitionReason.NO_PRODUCTION_OBSERVATIONS,
            observed_count=0,
            latest_observation_id=None,
            latest_value=None,
        )

    latest = matching[-1]
    if rule.direction is AlertDirection.ABOVE:
        trigger_hit = latest.value >= rule.trigger_threshold
        recover_hit = latest.value <= rule.recover_threshold
    else:
        trigger_hit = latest.value <= rule.trigger_threshold
        recover_hit = latest.value >= rule.recover_threshold

    if trigger_hit:
        if previous_state is AlertState.TRIGGERED:
            state, transition, reason = (
                AlertState.TRIGGERED,
                AlertTransition.NO_TRANSITION,
                AlertTransitionReason.STILL_TRIGGERED,
            )
        else:
            state, transition, reason = (
                AlertState.TRIGGERED,
                AlertTransition.TRIGGERED,
                AlertTransitionReason.TRIGGER_THRESHOLD_CROSSED,
            )
    elif previous_state is AlertState.TRIGGERED:
        if recover_hit:
            state, transition, reason = (
                AlertState.RECOVERED,
                AlertTransition.RECOVERED,
                AlertTransitionReason.RECOVER_THRESHOLD_CROSSED,
            )
        else:
            state, transition, reason = (
                AlertState.TRIGGERED,
                AlertTransition.NO_TRANSITION,
                AlertTransitionReason.STILL_TRIGGERED,
            )
    elif previous_state is AlertState.RECOVERED and not recover_hit:
        state, transition, reason = (
            AlertState.RECOVERED,
            AlertTransition.NO_TRANSITION,
            AlertTransitionReason.NO_PRIOR_ALERT,
        )
    else:
        state, transition, reason = (
            AlertState.RECOVERED,
            AlertTransition.NO_TRANSITION,
            AlertTransitionReason.NO_PRIOR_ALERT,
        )
    return AlertEvaluation(
        rule_id=rule.rule_id,
        release_version=rule.release_version,
        state=state,
        transition=transition,
        reason=reason,
        observed_count=len(matching),
        latest_observation_id=latest.observation_id,
        latest_value=latest.value,
    )


def alert_states_by_rule(evaluations: Iterable[AlertEvaluation]) -> Mapping[str, AlertState]:
    return {evaluation.rule_id: evaluation.state for evaluation in evaluations}


__all__ = [
    "AlertEvaluation",
    "AlertRule",
    "alert_states_by_rule",
    "evaluate_alert_rule",
]
