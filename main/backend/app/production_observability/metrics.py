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


__all__ = ["RUNTIME_HEALTH_GAUGE", "RUNTIME_HEALTH_METRIC_NAME"]
