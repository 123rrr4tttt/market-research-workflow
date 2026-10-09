from __future__ import annotations

from collections.abc import Iterator, Mapping

# ruff: noqa: TRY003
from dataclasses import dataclass
from typing import Protocol, TypeGuard, runtime_checkable

from .alerts import AlertRule
from .contracts import PRODUCTION_OBSERVABILITY_RUNTIME_CONTRACT_VERSION, AlertDirection, MetricFamily
from .errors import ObservabilityTypeError, ObservabilityValueError

LOCAL_RUNTIME_BOOLEAN_TRIGGER_RATIO = 1.0
LOCAL_RUNTIME_BOOLEAN_RECOVER_RATIO = 0.0
LOCAL_RUNTIME_LATENCY_BREACH_SECONDS = 0.25
LOCAL_RUNTIME_ALERT_THRESHOLD_PROVENANCE = "local_runtime_validation_non_production.v2"


@runtime_checkable
class ObjectIterable(Protocol):
    def __iter__(self) -> Iterator[object]: ...


def _is_text(value: object) -> TypeGuard[str]:
    return isinstance(value, str)


def _is_bool(value: object) -> TypeGuard[bool]:
    return isinstance(value, bool)


def _is_ratio(value: object) -> TypeGuard[int | float]:
    return not isinstance(value, bool) and isinstance(value, (int, float))


def _is_object_tuple(value: object) -> TypeGuard[tuple[object, ...]]:
    return isinstance(value, tuple)


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _is_config_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    return _is_object_mapping(value) and all(isinstance(key, str) for key in value)


def _is_nonempty_tuple(value: object) -> TypeGuard[tuple[AlertRule, ...]]:
    if not _is_object_tuple(value):
        return False
    return bool(value) and all(isinstance(item, AlertRule) for item in value)


@dataclass(frozen=True, slots=True)
class ProductionObservabilityConfig:
    contract_version: str
    runtime_id: str
    domain: str
    route: str
    release_version: str
    canary_route_enabled: bool
    alert_rules: tuple[AlertRule, ...]

    def __post_init__(self) -> None:
        if not _is_text(self.contract_version):
            raise ObservabilityTypeError("config contract_version must be text")
        if self.contract_version != PRODUCTION_OBSERVABILITY_RUNTIME_CONTRACT_VERSION:
            raise ObservabilityValueError("config contract_version is closed")
        if not _is_text(self.runtime_id) or not self.runtime_id.strip():
            raise ObservabilityValueError("runtime_id is required")
        binding = (self.domain, self.route, self.release_version)
        if any(not _is_text(value) or not value.strip() for value in binding):
            raise ObservabilityValueError("config domain, route, and release_version are required")
        if not _is_bool(self.canary_route_enabled):
            raise ObservabilityTypeError("canary_route_enabled must be boolean")
        if not _is_nonempty_tuple(self.alert_rules):
            raise ObservabilityValueError("at least one alert rule is required")
        rule_ids = [rule.rule_id for rule in self.alert_rules]
        if len(rule_ids) != len(set(rule_ids)):
            raise ObservabilityValueError("alert rule_id must be unique")
        normalized_domain = self.domain.strip().lower()
        normalized_route = self.route.strip().lower()
        normalized_release = self.release_version.strip()
        for rule in self.alert_rules:
            if rule.domain != normalized_domain or rule.route != normalized_route:
                raise ObservabilityValueError("alert rule domain and route must match config")
            if rule.release_version != normalized_release:
                raise ObservabilityValueError("alert rule release_version must match config")

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "runtime_id": self.runtime_id,
            "domain": self.domain.strip().lower(),
            "route": self.route.strip().lower(),
            "release_version": self.release_version.strip(),
            "canary_route_enabled": self.canary_route_enabled,
            "alert_rules": [rule.to_dict() for rule in self.alert_rules],
        }


def _required(mapping: Mapping[str, object], key: str) -> object:
    if key not in mapping:
        raise ObservabilityValueError(f"config field is required: {key}")
    return mapping[key]


def _required_text(mapping: Mapping[str, object], key: str) -> str:
    value = _required(mapping, key)
    if not _is_text(value):
        raise ObservabilityTypeError(f"config {key} must be text")
    return value


def _alert_rule(value: object) -> AlertRule:
    if not _is_config_mapping(value):
        raise ObservabilityTypeError("alert rule must be a mapping")
    fields = {
        "rule_id",
        "metric_family",
        "domain",
        "route",
        "release_version",
        "trigger_threshold",
        "recover_threshold",
        "direction",
    }
    unknown_fields = set(value.keys()) - fields
    if unknown_fields:
        raise ObservabilityValueError(f"alert rule has unknown fields: {sorted(unknown_fields)}")
    missing_fields = fields - set(value.keys()) - {"direction"}
    if missing_fields:
        raise ObservabilityValueError(f"alert rule fields are required: {sorted(missing_fields)}")
    raw_family = _required(value, "metric_family")
    family = raw_family if isinstance(raw_family, MetricFamily) else MetricFamily(raw_family)
    raw_direction = value["direction"] if "direction" in value else AlertDirection.ABOVE
    direction = raw_direction if isinstance(raw_direction, AlertDirection) else AlertDirection(raw_direction)
    trigger = _required(value, "trigger_threshold")
    recover = _required(value, "recover_threshold")
    if not _is_ratio(trigger):
        raise ObservabilityTypeError("alert trigger_threshold must be numeric")
    if not _is_ratio(recover):
        raise ObservabilityTypeError("alert recover_threshold must be numeric")
    return AlertRule(
        rule_id=_required_text(value, "rule_id"),
        metric_family=family,
        domain=_required_text(value, "domain"),
        route=_required_text(value, "route"),
        release_version=_required_text(value, "release_version"),
        trigger_threshold=trigger,
        recover_threshold=recover,
        direction=direction,
    )


def _required_bool(mapping: Mapping[str, object], key: str) -> bool:
    value = _required(mapping, key)
    if not _is_bool(value):
        raise ObservabilityTypeError(f"config {key} must be boolean")
    return value


def parse_production_observability_config(value: object) -> ProductionObservabilityConfig:
    if not _is_config_mapping(value):
        raise ObservabilityTypeError("production observability config must be a mapping")
    fields = {
        "contract_version",
        "runtime_id",
        "domain",
        "route",
        "release_version",
        "canary_route_enabled",
        "alert_rules",
    }
    unknown_fields = set(value.keys()) - fields
    if unknown_fields:
        raise ObservabilityValueError(f"config has unknown fields: {sorted(unknown_fields)}")
    raw_rules = _required(value, "alert_rules")
    if isinstance(raw_rules, (str, bytes)) or not isinstance(raw_rules, ObjectIterable):
        raise ObservabilityTypeError("alert_rules must be a sequence")
    rules = tuple(_alert_rule(rule) for rule in raw_rules)
    return ProductionObservabilityConfig(
        contract_version=_required_text(value, "contract_version"),
        runtime_id=_required_text(value, "runtime_id"),
        domain=_required_text(value, "domain"),
        route=_required_text(value, "route"),
        release_version=_required_text(value, "release_version"),
        canary_route_enabled=_required_bool(value, "canary_route_enabled"),
        alert_rules=rules,
    )


def production_observability_config_from_settings(
    settings_obj: object,
    *,
    release_version: str,
) -> ProductionObservabilityConfig:
    """Build the one platform-level R7 control binding from explicit settings."""

    runtime_id = str(
        getattr(settings_obj, "production_observability_runtime_id", "") or ""
    ).strip()
    if not runtime_id:
        raise ObservabilityValueError("production observability runtime_id is required")
    domain = "platform"
    route = "production-api"
    pairs = (
        (
            "domain-rejection",
            MetricFamily.DOMAIN_REJECTION_RATE,
            "production_domain_rejection_trigger_ratio",
            "production_domain_rejection_recover_ratio",
        ),
        (
            "route-error",
            MetricFamily.ROUTE_ERROR_RATE,
            "production_route_error_trigger_ratio",
            "production_route_error_recover_ratio",
        ),
        (
            "release-error",
            MetricFamily.RELEASE_VERSION_ERROR_RATE,
            "production_release_error_trigger_ratio",
            "production_release_error_recover_ratio",
        ),
    )
    local_gap_pairs = (
        ("local-runtime-queue.v2", MetricFamily.QUEUE_DEPTH),
        ("local-runtime-db-connection.v2", MetricFamily.DATABASE_CONNECTION_UNAVAILABLE),
        ("local-runtime-provider-failure.v2", MetricFamily.PROVIDER_FAILURE),
        ("local-runtime-authority-mismatch.v2", MetricFamily.AUTHORITY_MISMATCH),
        ("local-runtime-request-latency.v2", MetricFamily.REQUEST_LATENCY_BREACH_RATE),
    )
    for _rule_id, _family, trigger_name, recover_name in pairs:
        if not _is_ratio(getattr(settings_obj, trigger_name)) or not _is_ratio(
            getattr(settings_obj, recover_name)
        ):
            raise ObservabilityValueError(
                "production observability trigger and recover settings must be numeric"
            )
    existing_rules = tuple(
        AlertRule(
            rule_id=rule_id,
            metric_family=family,
            domain=domain,
            route=route,
            release_version=release_version,
            trigger_threshold=float(getattr(settings_obj, trigger_name)),
            recover_threshold=float(getattr(settings_obj, recover_name)),
        )
        for rule_id, family, trigger_name, recover_name in pairs
    )
    local_rules = tuple(
        AlertRule(
            rule_id=rule_id,
            metric_family=family,
            domain=domain,
            route=route,
            release_version=release_version,
            trigger_threshold=LOCAL_RUNTIME_BOOLEAN_TRIGGER_RATIO,
            recover_threshold=LOCAL_RUNTIME_BOOLEAN_RECOVER_RATIO,
        )
        for rule_id, family in local_gap_pairs
    )
    rules = existing_rules + local_rules
    canary_route_enabled = getattr(
        settings_obj, "production_canary_route_enabled", False
    )
    if not _is_bool(canary_route_enabled):
        raise ObservabilityTypeError("production canary route setting must be boolean")
    return ProductionObservabilityConfig(
        contract_version=PRODUCTION_OBSERVABILITY_RUNTIME_CONTRACT_VERSION,
        runtime_id=runtime_id,
        domain=domain,
        route=route,
        release_version=release_version,
        canary_route_enabled=canary_route_enabled,
        alert_rules=rules,
    )


__all__ = [
    "LOCAL_RUNTIME_ALERT_THRESHOLD_PROVENANCE",
    "LOCAL_RUNTIME_BOOLEAN_RECOVER_RATIO",
    "LOCAL_RUNTIME_BOOLEAN_TRIGGER_RATIO",
    "LOCAL_RUNTIME_LATENCY_BREACH_SECONDS",
    "PRODUCTION_OBSERVABILITY_RUNTIME_CONTRACT_VERSION",
    "ProductionObservabilityConfig",
    "parse_production_observability_config",
    "production_observability_config_from_settings",
]
