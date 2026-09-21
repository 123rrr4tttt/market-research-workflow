from __future__ import annotations

# ruff: noqa: TRY003

from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Literal

from app.services.ingest.canary_handoff import (
    CANARY_HANDOFF_CONTRACT_VERSION,
    CANARY_METRICS_SNAPSHOT_CONTRACT_VERSION,
    LIVE_CANARY_EVIDENCE_CONTRACT_VERSION,
)
from app.services.ingest.guardrail_rollout import ROLLOUT_CONTRACT_VERSION
from app.services.ingest.canary_metrics import CONTRACT_VERSION as CANARY_METRICS_READINESS_CONTRACT_VERSION
from app.services.ingest.canary_strict_promotion import (
    CONTRACT_VERSION as CANARY_STRICT_PROMOTION_CONTRACT_VERSION,
    PRODUCTION_24H_METRICS_CONTRACT_VERSION,
)


OBSERVABILITY_CONTRACT_VERSION = "production.observability.core.v1"
LOCAL_FIXTURE_RECEIPT_CONTRACT_VERSION = "production.observability.receipt.local_fixture.v1"
STAGING_RECEIPT_CONTRACT_VERSION = "production.observability.receipt.staging.v1"
PRODUCTION_RECEIPT_CONTRACT_VERSION = "production.observability.receipt.production.v1"
CANARY_ROUTE_DECISION_CONTRACT_VERSION = "production.observability.canary_route_decision.v1"
PRODUCTION_OBSERVABILITY_RUNTIME_CONTRACT_VERSION = "production.observability.runtime.v1"
PRODUCTION_HTTP_OBSERVATION_CONTRACT_VERSION = "production.observability.http-request.v1"
PRODUCTION_RUNTIME_HEALTH_OBSERVATION_CONTRACT_VERSION = (
    "production.observability.runtime-health.v1"
)

SOURCE_CONTRACT_VERSIONS: Final[frozenset[str]] = frozenset(
    {
        PRODUCTION_HTTP_OBSERVATION_CONTRACT_VERSION,
        CANARY_HANDOFF_CONTRACT_VERSION,
        CANARY_METRICS_SNAPSHOT_CONTRACT_VERSION,
        LIVE_CANARY_EVIDENCE_CONTRACT_VERSION,
        ROLLOUT_CONTRACT_VERSION,
        CANARY_METRICS_READINESS_CONTRACT_VERSION,
        CANARY_STRICT_PROMOTION_CONTRACT_VERSION,
        PRODUCTION_24H_METRICS_CONTRACT_VERSION,
        PRODUCTION_RUNTIME_HEALTH_OBSERVATION_CONTRACT_VERSION,
    }
)


class MetricFamily(StrEnum):
    DOMAIN_REJECTION_RATE = "domain.rejection_rate"
    ROUTE_ERROR_RATE = "route.error_rate"
    RELEASE_VERSION_ERROR_RATE = "release_version.error_rate"
    QUEUE_DEPTH = "queue.depth"
    DATABASE_CONNECTION_UNAVAILABLE = "database.connection_unavailable"
    PROVIDER_FAILURE = "provider.failure"
    AUTHORITY_MISMATCH = "authority.mismatch"
    PROJECTION_DRIFT = "projection.drift"
    REQUEST_LATENCY_BREACH_RATE = "request.latency_breach_rate"


class ReceiptScope(StrEnum):
    LOCAL_FIXTURE = "local_fixture"
    STAGING = "staging"
    PRODUCTION = "production"


class AlertState(StrEnum):
    UNKNOWN = "unknown"
    TRIGGERED = "triggered"
    RECOVERED = "recovered"


class AlertTransition(StrEnum):
    UNKNOWN = "unknown"
    TRIGGERED = "triggered"
    RECOVERED = "recovered"
    NO_TRANSITION = "no_transition"


class AlertTransitionReason(StrEnum):
    NO_PRODUCTION_OBSERVATIONS = "no_production_observations"
    TRIGGER_THRESHOLD_CROSSED = "trigger_threshold_crossed"
    RECOVER_THRESHOLD_CROSSED = "recover_threshold_crossed"
    STILL_TRIGGERED = "still_triggered"
    NO_PRIOR_ALERT = "no_prior_alert"


class AlertDirection(StrEnum):
    ABOVE = "above"
    BELOW = "below"


class ContinuityReason(StrEnum):
    OPERATOR_CONTINUE = "operator_continue"
    AUTOMATIC_POLICY_CONTINUE = "automatic_policy_continue"


class CanaryRouteAction(StrEnum):
    CONTINUE = "continue"
    HOLD = "hold"
    ROLLBACK = "rollback"


class StopReason(StrEnum):
    EXPLICIT_STOP = "explicit_stop"
    ALERT_TRIGGERED = "alert_triggered"
    RECEIPT_SCOPE_NOT_PRODUCTION = "receipt_scope_not_production"
    RECEIPT_CONTRACT_INVALID = "receipt_contract_invalid"
    RECEIPT_BINDING_INVALID = "receipt_binding_invalid"
    RECEIPT_TIME_INVALID = "receipt_time_invalid"
    MISSING_PRODUCTION_RECEIPT = "missing_production_receipt"
    NO_PRODUCTION_OBSERVATIONS = "no_production_observations"
    ALERT_EVALUATION_UNKNOWN = "alert_evaluation_unknown"
    CONTINUE_NOT_REQUESTED = "continue_not_requested"
    NO_STOP_CONDITION = "no_stop_condition"


ObservabilityContractVersion = Literal["production.observability.core.v1"]
ALERT_DIRECTION = AlertDirection
ALERT_STATE = AlertState
ALERT_TRANSITION = AlertTransition
CANARY_ROUTE_ACTION = CanaryRouteAction
CONTINUITY_REASON = ContinuityReason
METRIC_FAMILY = MetricFamily
RECEIPT_SCOPE = ReceiptScope
STOP_REASON = StopReason


@dataclass(frozen=True)
class LabelBinding:
    domain: str
    route: str
    release_version: str

    def normalized(self) -> LabelBinding:
        return LabelBinding(
            domain=self.domain.strip().lower(),
            route=self.route.strip().lower(),
            release_version=self.release_version.strip(),
        )


RECEIPT_CONTRACT_VERSIONS: Final[dict[ReceiptScope, str]] = {
    ReceiptScope.LOCAL_FIXTURE: LOCAL_FIXTURE_RECEIPT_CONTRACT_VERSION,
    ReceiptScope.STAGING: STAGING_RECEIPT_CONTRACT_VERSION,
    ReceiptScope.PRODUCTION: PRODUCTION_RECEIPT_CONTRACT_VERSION,
}

RECEIPT_ARTIFACT_KINDS: Final[dict[ReceiptScope, str]] = {
    ReceiptScope.LOCAL_FIXTURE: "local_fixture_observation_receipt",
    ReceiptScope.STAGING: "staging_observation_receipt",
    ReceiptScope.PRODUCTION: "production_observation_receipt",
}


__all__ = [
    "ALERT_DIRECTION",
    "ALERT_STATE",
    "ALERT_TRANSITION",
    "CANARY_ROUTE_DECISION_CONTRACT_VERSION",
    "CONTINUITY_REASON",
    "LOCAL_FIXTURE_RECEIPT_CONTRACT_VERSION",
    "METRIC_FAMILY",
    "OBSERVABILITY_CONTRACT_VERSION",
    "PRODUCTION_RECEIPT_CONTRACT_VERSION",
    "PRODUCTION_OBSERVABILITY_RUNTIME_CONTRACT_VERSION",
    "PRODUCTION_HTTP_OBSERVATION_CONTRACT_VERSION",
    "PRODUCTION_RUNTIME_HEALTH_OBSERVATION_CONTRACT_VERSION",
    "RECEIPT_SCOPE",
    "SOURCE_CONTRACT_VERSIONS",
    "STAGING_RECEIPT_CONTRACT_VERSION",
    "STOP_REASON",
    "AlertDirection",
    "AlertState",
    "AlertTransition",
    "AlertTransitionReason",
    "CanaryRouteAction",
    "ContinuityReason",
    "LabelBinding",
    "MetricFamily",
    "ObservabilityContractVersion",
    "ReceiptScope",
    "StopReason",
]
