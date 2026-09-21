from __future__ import annotations

# ruff: noqa: TRY003

from dataclasses import asdict, dataclass, field
from datetime import datetime
import math
from threading import RLock
from collections.abc import Iterable, Mapping
from typing import Any, Literal

from .config import (
    LOCAL_STAGE5_LATENCY_BREACH_SECONDS,
    ProductionObservabilityConfig,
    parse_production_observability_config,
)
from .contracts import (
    AlertState,
    CanaryRouteAction,
    CANARY_ROUTE_DECISION_CONTRACT_VERSION,
    MetricFamily,
    PRODUCTION_HTTP_OBSERVATION_CONTRACT_VERSION,
    PRODUCTION_RUNTIME_HEALTH_OBSERVATION_CONTRACT_VERSION,
)
from .decision import (
    CanaryRouteDecision,
    ContinueRequest,
    StopRequest,
    decide_canary_route,
)
from .errors import ObservabilityTypeError, ObservabilityValueError
from .health import (
    ProjectionDriftStatus,
    ProjectionReadStatus,
    ProviderRuntimeStatus,
    QueueReadStatus,
    RuntimeBindingStatus,
    RuntimeAuthorityReadStatus,
    RuntimeHealthSnapshot,
)
from .metrics import RUNTIME_HEALTH_GAUGE
from .observations import Observation, make_observation, parse_observed_at, utc_now
from .receipts import ObservationReceipt, make_observation_receipt


RUNTIME_STATE_KEY = "production_observability_r7"
RUNTIME_PROJECTION_CONTRACT_VERSION = "production.observability.runtime_projection.v1"


@dataclass(frozen=True, slots=True)
class CanaryRouteAdvice:
    canary_route_enabled: bool
    action: CanaryRouteAction
    promotion_allowed: bool
    authority: Literal[False] = False
    derived_as: Literal["advice"] = "advice"

    def __post_init__(self) -> None:
        if self.authority is not False:
            raise ObservabilityTypeError("canary route advice is non-authoritative")
        if self.derived_as != "advice":
            raise ObservabilityValueError("canary route derived_as must remain advice")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RuntimeEvaluation:
    projection_contract_version: str
    decision_contract_version: str
    decision: CanaryRouteDecision
    receipt: ObservationReceipt
    canary_route: CanaryRouteAdvice
    authority: Literal[False] = False
    derived_as: Literal["projection"] = "projection"

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise ObservabilityTypeError("RuntimeEvaluation is a closed projection type")

    def __post_init__(self) -> None:
        if self.authority is not False:
            raise ObservabilityTypeError("runtime evaluation is non-authoritative")
        if self.derived_as != "projection":
            raise ObservabilityValueError("runtime evaluation derived_as must remain projection")
        if self.projection_contract_version != RUNTIME_PROJECTION_CONTRACT_VERSION:
            raise ObservabilityValueError("runtime projection contract_version is closed")
        if self.decision_contract_version != CANARY_ROUTE_DECISION_CONTRACT_VERSION:
            raise ObservabilityValueError("decision contract_version is closed")
        if self.decision.authority is not False or self.decision.derived_as != "view":
            raise ObservabilityTypeError("runtime decision must remain a non-authoritative view")
        if self.canary_route.action is not self.decision.action:
            raise ObservabilityValueError("canary route advice must match decision action")
        if self.canary_route.promotion_allowed is not self.decision.promotion_allowed:
            raise ObservabilityValueError("canary route advice must match promotion_allowed")

    def to_dict(self) -> dict[str, Any]:
        return {
            "projection_contract_version": self.projection_contract_version,
            "decision_contract_version": self.decision_contract_version,
            "decision": self.decision.to_dict(),
            "receipt": self.receipt.to_dict(),
            "canary_route": self.canary_route.to_dict(),
            "authority": self.authority,
            "derived_as": self.derived_as,
        }


@dataclass(frozen=True, slots=True)
class ProductionObservabilityController:
    config: ProductionObservabilityConfig
    _lock: RLock = field(default_factory=RLock, repr=False, compare=False)
    _alert_states: dict[str, AlertState] = field(
        default_factory=dict,
        repr=False,
        compare=False,
    )
    _explicit_stop: StopRequest | None = field(default=None, repr=False, compare=False)
    _evaluation_count: int = field(default=0, repr=False, compare=False)
    _last_evaluation: RuntimeEvaluation | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.config, ProductionObservabilityConfig):
            raise ObservabilityTypeError("controller requires parsed production observability config")

    def request_stop(
        self,
        *,
        request_id: str,
        requested_by: str,
        requested_at: datetime | str | None = None,
        reason: str,
    ) -> StopRequest:
        request = StopRequest(
            request_id=request_id,
            requested_by=requested_by,
            requested_at=requested_at or utc_now(),
            release_version=self.config.release_version.strip(),
            reason=reason,
        )
        with self._lock:
            if self._explicit_stop is not None:
                raise ObservabilityValueError("explicit stop is already recorded")
            object.__setattr__(self, "_explicit_stop", request)
        return request

    def latch_runtime_failure(
        self,
        *,
        request_id: str,
        reason: str,
        observed_at: datetime | str | None = None,
    ) -> StopRequest:
        """Latch an internal observation failure without masking an HTTP response."""

        request = StopRequest(
            request_id=request_id,
            requested_by=self.config.runtime_id.strip(),
            requested_at=observed_at or utc_now(),
            release_version=self.config.release_version.strip(),
            reason=reason,
        )
        with self._lock:
            if self._explicit_stop is None:
                object.__setattr__(self, "_explicit_stop", request)
                return request
            return self._explicit_stop

    def evaluate(
        self,
        *,
        observations: Iterable[Observation] = (),
        production_receipt: ObservationReceipt | None = None,
        continue_request: ContinueRequest | None = None,
        evaluated_at: datetime | str | None = None,
    ) -> RuntimeEvaluation:
        observation_items = tuple(observations)
        evaluation_time = parse_observed_at(evaluated_at) if evaluated_at is not None else utc_now()
        binding = self.config
        normalized_domain = binding.domain.strip().lower()
        normalized_route = binding.route.strip().lower()
        normalized_release = binding.release_version.strip()
        for observation in observation_items:
            if (
                observation.domain != normalized_domain
                or observation.route != normalized_route
                or observation.release_version != normalized_release
            ):
                raise ObservabilityValueError("observation binding does not match runtime config")
            if observation.observed_at > evaluation_time:
                raise ObservabilityValueError("observation time is after evaluation time")
        if production_receipt is not None:
            if production_receipt.observed_at > evaluation_time:
                raise ObservabilityValueError("receipt time is after evaluation time")

        with self._lock:
            explicit_stop = self._explicit_stop
            previous_alert_states = dict(self._alert_states)
            evaluation_count = self._evaluation_count + 1
            object.__setattr__(self, "_evaluation_count", evaluation_count)
            sequence = self._evaluation_count
            decision = decide_canary_route(
                domain=normalized_domain,
                route=normalized_route,
                release_version=normalized_release,
                observations=observation_items,
                alert_rules=binding.alert_rules,
                production_receipt=production_receipt,
                explicit_stop=explicit_stop,
                continue_request=continue_request if binding.canary_route_enabled else None,
                previous_alert_states=previous_alert_states,
            )
            derived_receipt = make_observation_receipt(
                scope="production",
                receipt_id=f"{binding.runtime_id.strip()}:derived:{sequence}",
                observed_at=evaluation_time,
                domain=normalized_domain,
                route=normalized_route,
                release_version=normalized_release,
                issuer=binding.runtime_id.strip(),
                source_ref=f"runtime-projection:{binding.runtime_id.strip()}:{sequence}",
                observations=observation_items,
            )
            evaluation = RuntimeEvaluation(
                projection_contract_version=RUNTIME_PROJECTION_CONTRACT_VERSION,
                decision_contract_version=CANARY_ROUTE_DECISION_CONTRACT_VERSION,
                decision=decision,
                receipt=derived_receipt,
                canary_route=CanaryRouteAdvice(
                    canary_route_enabled=binding.canary_route_enabled,
                    action=decision.action,
                    promotion_allowed=decision.promotion_allowed,
                ),
            )
            object.__setattr__(
                self,
                "_alert_states",
                {
                    item.rule_id: item.state for item in decision.alert_evaluations
                },
            )
            object.__setattr__(self, "_last_evaluation", evaluation)
            return evaluation

    def observe_http_request(
        self,
        *,
        observation_id: str,
        status_code: int,
        observed_at: datetime | str | None = None,
        terminal_outcome: str | None = None,
        latency_seconds: float | None = None,
        production_receipt: ObservationReceipt | None = None,
    ) -> RuntimeEvaluation:
        """Record one platform request as stable R7 metric observations.

        Stream routes provide ``terminal_outcome`` through a route-local side
        channel after their iterator is consumed.  It is intentionally not
        inferred from response bytes.
        """

        if not isinstance(status_code, int) or isinstance(status_code, bool):
            raise ObservabilityTypeError("HTTP status_code must be an integer")
        if latency_seconds is not None and (
            isinstance(latency_seconds, bool)
            or not isinstance(latency_seconds, (int, float))
            or not math.isfinite(float(latency_seconds))
            or latency_seconds < 0
        ):
            raise ObservabilityValueError("latency_seconds must be finite and non-negative")
        if terminal_outcome not in {
            None,
            "success",
            "application_error",
            "iterator_failure",
            "terminal_failure",
        }:
            raise ObservabilityValueError("unknown terminal_outcome")
        timestamp = observed_at or utc_now()
        if terminal_outcome in {"iterator_failure", "terminal_failure"}:
            self.latch_runtime_failure(
                request_id=f"{observation_id}:stream-terminal-failure",
                reason="SSE iterator failed",
                observed_at=timestamp,
            )
        values = (
            (
                MetricFamily.DOMAIN_REJECTION_RATE,
                1.0 if status_code == 403 else 0.0,
                {},
            ),
            (
                MetricFamily.ROUTE_ERROR_RATE,
                1.0
                if status_code >= 500
                or terminal_outcome in {"application_error", "iterator_failure", "terminal_failure"}
                else 0.0,
                {},
            ),
            (
                MetricFamily.RELEASE_VERSION_ERROR_RATE,
                1.0
                if status_code >= 500
                or terminal_outcome in {"application_error", "iterator_failure", "terminal_failure"}
                else 0.0,
                {},
            ),
        )
        if latency_seconds is not None:
            values = (
                *values,
                (
                    MetricFamily.REQUEST_LATENCY_BREACH_RATE,
                    1.0 if latency_seconds >= LOCAL_STAGE5_LATENCY_BREACH_SECONDS else 0.0,
                    {
                        "latency_seconds": f"{float(latency_seconds):.6f}",
                        "threshold_seconds": str(LOCAL_STAGE5_LATENCY_BREACH_SECONDS),
                        "threshold_provenance": "local_stage5_validation_non_production",
                    },
                ),
            )
        observations = tuple(
            make_observation(
                observation_id=f"{observation_id}:{family.value}",
                observed_at=timestamp,
                source_contract_version=PRODUCTION_HTTP_OBSERVATION_CONTRACT_VERSION,
                metric_family=family,
                domain=self.config.domain,
                route=self.config.route,
                release_version=self.config.release_version,
                value=value,
                sample_count=1,
                labels=labels,
            )
            for family, value, labels in values
        )
        return self.evaluate(
            observations=observations,
            production_receipt=production_receipt,
            evaluated_at=timestamp,
        )


    def observe_runtime_health(
        self,
        *,
        observation_id: str,
        snapshot: RuntimeHealthSnapshot,
        production_receipt: ObservationReceipt | None = None,
    ) -> RuntimeEvaluation:
        """Observe typed runtime-health signals as closed normalized ratios.

        Raw signals stay bound to their runtime sources; conversion uses the
        declared Stage 5 local validation thresholds.
        """

        if not isinstance(snapshot, RuntimeHealthSnapshot):
            raise ObservabilityTypeError("runtime health snapshot is closed")
        timestamp = snapshot.observed_at
        database = snapshot.database
        provider = snapshot.provider
        runtime_binding = snapshot.runtime_binding
        projection = snapshot.projection
        values: list[tuple[MetricFamily, float, dict[str, str]]] = [
            (
                MetricFamily.QUEUE_DEPTH,
                1.0
                if snapshot.queue.depth > 0 or snapshot.queue.read_status is QueueReadStatus.ERROR
                else 0.0,
                {
                    "source": snapshot.queue.source,
                    "read_status": snapshot.queue.read_status.value,
                    "depth": str(snapshot.queue.depth),
                    "threshold": "1",
                    "threshold_provenance": "local_stage5_validation_non_production",
                },
            ),
            (
                MetricFamily.DATABASE_CONNECTION_UNAVAILABLE,
                1.0 if database.connection_status != "ok" or database.pool_status != "ok" else 0.0,
                {
                    "source": database.source,
                    "connection_status": database.connection_status,
                    "pool_status": database.pool_status,
                    "pool_size": str(database.pool_size),
                    "checked_out": str(database.checked_out),
                    "pool_limit": str(database.pool_limit),
                },
            ),
            (
                MetricFamily.PROVIDER_FAILURE,
                1.0 if provider.status is ProviderRuntimeStatus.SIMULATED_FAILURE else 0.0,
                {
                    "source": provider.source,
                    "status": provider.status.value,
                    "simulated": "true",
                },
            ),
        ]
        authority_read = runtime_binding.authority_read
        authority_known = (
            runtime_binding.authority_status
            in (RuntimeBindingStatus.BOUND, RuntimeBindingStatus.MISMATCH)
            and authority_read is not None
            and authority_read.read_status
            in (
                RuntimeAuthorityReadStatus.OBSERVED,
                RuntimeAuthorityReadStatus.MISMATCH,
            )
        )
        if authority_known:
            assert authority_read is not None
            values.append(
                (
                    MetricFamily.AUTHORITY_MISMATCH,
                    1.0
                    if runtime_binding.authority_status is RuntimeBindingStatus.MISMATCH
                    else 0.0,
                {
                    "source": runtime_binding.source,
                    "authority_status": runtime_binding.authority_status.value,
                    **(
                        {
                            "authority_read_status": authority_read.read_status.value,
                            "authority_task_observed": str(authority_read.task_id is not None).lower(),
                            "authority_tenant_observed": str(authority_read.tenant_id is not None).lower(),
                            "authority_project_scope_observed": str(
                                authority_read.project_scope_digest is not None
                                and authority_read.project_registry_revision is not None
                            ).lower(),
                            "authority_capability_observed": str(
                                authority_read.capability_id is not None
                            ).lower(),
                            "authority_step_observed": str(
                                authority_read.step_id is not None
                            ).lower(),
                            "authority_epoch_observed": str(
                                authority_read.claim_authority_epoch is not None
                                and authority_read.expected_claim_authority_epoch is not None
                            ).lower(),
                            "authority_mismatch_fields": ",".join(
                                authority_read.mismatch_fields
                            ),
                            "authority_not_observed_fields": ",".join(
                                authority_read.not_observed_fields
                            ),
                        }
                    ),
                },
                ),
            )
        projection_drift_known = (
            projection.read_status is ProjectionReadStatus.OK
        )
        if projection_drift_known:
            values.append(
                (
                    MetricFamily.PROJECTION_DRIFT,
                    1.0
                    if projection.drift_status is ProjectionDriftStatus.MISMATCH
                    else 0.0,
                    {
                        "source": projection.source,
                        "read_status": projection.read_status.value,
                        "drift_status": projection.drift_status.value,
                        "active_source_digest": projection.active_source_digest,
                        "expected_source_digest": projection.expected_source_digest,
                        "projection_generation": str(projection.projection_generation),
                        "offset_revision": str(projection.offset_revision),
                        "source_revision": str(projection.source_revision),
                        "offset_ref": projection.offset_ref,
                        "status_detail": projection.status_detail,
                    },
                ),
            )
        source_labels = {f"source_{key}": value for key, value in snapshot.labels.items()}
        observations = tuple(
            make_observation(
                observation_id=f"{observation_id}:{family.value}",
                observed_at=timestamp,
                source_contract_version=PRODUCTION_RUNTIME_HEALTH_OBSERVATION_CONTRACT_VERSION,
                metric_family=family,
                domain=self.config.domain,
                route=self.config.route,
                release_version=self.config.release_version,
                value=value,
                sample_count=1,
                labels={**labels, **source_labels},
            )
            for family, value, labels in values
        )
        evaluation = self.evaluate(
            observations=observations,
            production_receipt=production_receipt,
            evaluated_at=timestamp,
        )
        runtime_health_families = {family for family, _, _ in values}
        for alert in evaluation.decision.alert_evaluations:
            if alert.latest_value is None:
                continue
            rule = next((item for item in self.config.alert_rules if item.rule_id == alert.rule_id), None)
            if rule is None or rule.metric_family not in runtime_health_families:
                continue
            RUNTIME_HEALTH_GAUGE.labels(
                domain=self.config.domain,
                route=self.config.route,
                release_version=self.config.release_version,
                metric_family=rule.metric_family.value,
                rule_id=rule.rule_id,
            ).set(alert.latest_value)
        return evaluation

    @property
    def last_evaluation(self) -> RuntimeEvaluation | None:
        with self._lock:
            return self._last_evaluation

    @property
    def route_advice(self) -> CanaryRouteAdvice:
        with self._lock:
            explicit_stop = self._explicit_stop
            last = self._last_evaluation
        if explicit_stop is not None:
            return CanaryRouteAdvice(
                canary_route_enabled=self.config.canary_route_enabled,
                action=CanaryRouteAction.ROLLBACK,
                promotion_allowed=False,
            )
        if last is None:
            return CanaryRouteAdvice(
                canary_route_enabled=self.config.canary_route_enabled,
                action=CanaryRouteAction.HOLD,
                promotion_allowed=False,
            )
        return last.canary_route


def install_production_observability(
    target: Any,
    config: ProductionObservabilityConfig | Mapping[str, Any],
) -> ProductionObservabilityController:
    parsed = (
        config
        if isinstance(config, ProductionObservabilityConfig)
        else parse_production_observability_config(config)
    )
    state = getattr(target, "state", None)
    if state is None:
        raise ObservabilityTypeError("composition root target must expose state")
    existing = getattr(state, RUNTIME_STATE_KEY, None)
    if existing is not None:
        raise ObservabilityValueError("production observability runtime is already installed")
    controller = ProductionObservabilityController(parsed)
    setattr(state, RUNTIME_STATE_KEY, controller)
    return controller


__all__ = [
    "CANARY_ROUTE_DECISION_CONTRACT_VERSION",
    "RUNTIME_PROJECTION_CONTRACT_VERSION",
    "RUNTIME_STATE_KEY",
    "CanaryRouteAdvice",
    "ProductionObservabilityController",
    "RuntimeEvaluation",
    "install_production_observability",
]
