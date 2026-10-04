from __future__ import annotations

from prometheus_client import Gauge


RUNTIME_HEALTH_METRIC_NAME = "market_api_production_observability_runtime_health"
RUNTIME_HEALTH_GAUGE = Gauge(
    RUNTIME_HEALTH_METRIC_NAME,
    "Current normalized runtime-health observation by metric family",
    (
        "domain",
        "route",
        "release_version",
        "metric_family",
        "rule_id",
    ),
)

ALERT_STATE_METRIC_NAME = "market_api_production_observability_alert_state"
ALERT_STATE_GAUGE = Gauge(
    ALERT_STATE_METRIC_NAME,
    "Current non-authoritative R7 alert state, one-hot by rule and state",
    ("rule_id", "state"),
)


__all__ = [
    "ALERT_STATE_GAUGE",
    "ALERT_STATE_METRIC_NAME",
    "RUNTIME_HEALTH_GAUGE",
    "RUNTIME_HEALTH_METRIC_NAME",
]
