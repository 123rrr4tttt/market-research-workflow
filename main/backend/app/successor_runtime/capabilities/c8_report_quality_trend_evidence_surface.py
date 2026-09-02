"""C8 report quality/export trend evidence-consumption surface (ALL-SM-016).

The module consumes typed report-quality trend observations and renders a
degraded/no-call readback.  It never writes or aggregates durable trend
records.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal

AUTHORITY_KEYS: tuple[str, ...] = (
    "canonical_write",
    "live_provider",
    "external_delivery",
    "cutover",
    "authority_transfer",
    "scheduler",
    "executor",
    "credential_read",
)
SURFACE_SCHEMA = "mrw.successor.c8.report-quality-trend.evidence-surface.v1"
MOVEMENT_IDS: tuple[str, ...] = ("ALL-SM-016",)
DECISION_OWNER = "MRW report trend owner (B-recheck); S2c decision owner"
QualityTrendOutcome = Literal["passed", "held", "blocked", "unknown"]
_CREDENTIAL_MARKERS = ("secret", "token", "password", "api_key", "apikey")


def authority_ceiling() -> dict[str, bool]:
    return {name: False for name in AUTHORITY_KEYS}


def _text(value: Any, name: str, *, required: bool = True) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    text = value.strip()
    if not text and required:
        raise ValueError(f"{name} must not be blank")
    lowered = text.lower()
    if any(marker in lowered for marker in _CREDENTIAL_MARKERS):
        raise ValueError(f"{name} must not carry credential-like raw material")
    return text


@dataclass(frozen=True, slots=True)
class ReportQualityTrendObservation:
    """One typed quality/export trend observation."""

    report_id: str
    trace_id: str
    outcome: QualityTrendOutcome
    gate_mode: str
    fallback_used: bool
    coverage_count: int
    observed_at: str
    source_ref: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "report_id", _text(self.report_id, "report_id"))
        object.__setattr__(self, "trace_id", _text(self.trace_id, "trace_id"))
        if self.outcome not in ("passed", "held", "blocked", "unknown"):
            raise ValueError(f"unknown outcome: {self.outcome}")
        object.__setattr__(self, "gate_mode", _text(self.gate_mode, "gate_mode"))
        if not isinstance(self.fallback_used, bool):
            raise TypeError("fallback_used must be bool")
        if (
            not isinstance(self.coverage_count, int)
            or isinstance(self.coverage_count, bool)
            or self.coverage_count < 0
        ):
            raise ValueError("coverage_count must be a non-negative integer")
        object.__setattr__(self, "observed_at", _text(self.observed_at, "observed_at"))
        object.__setattr__(
            self,
            "source_ref",
            _text(self.source_ref, "source_ref", required=False),
        )

    def to_plain(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "trace_id": self.trace_id,
            "outcome": self.outcome,
            "gate_mode": self.gate_mode,
            "fallback_used": self.fallback_used,
            "coverage_count": self.coverage_count,
            "observed_at": self.observed_at,
            "source_ref": self.source_ref,
        }


@dataclass(frozen=True, slots=True)
class ReportQualityTrendReadback:
    """Immutable trend evidence-consumption readback for ALL-SM-016."""

    schema: str
    movement_ids: tuple[str, ...]
    authority: dict[str, bool]
    observations: tuple[ReportQualityTrendObservation, ...]
    outcome_counts: dict[str, int]
    total_count: int
    degraded_readback: bool
    no_call_durable_aggregation: bool = True
    aggregation_writer_called: bool = False
    no_call_reason: str = (
        "evidence consumption only; durable trend aggregation is no-call"
    )

    def __post_init__(self) -> None:
        if self.schema != SURFACE_SCHEMA:
            raise ValueError("ReportQualityTrendReadback.schema is not frozen")
        if self.movement_ids != MOVEMENT_IDS:
            raise ValueError("ReportQualityTrendReadback.movement_ids drift")
        if any(value is not False for value in self.authority.values()):
            raise ValueError("trend evidence surface authority must be all false")
        object.__setattr__(self, "observations", tuple(self.observations))
        if self.no_call_durable_aggregation is not True:
            raise ValueError("trend surface never grants durable aggregation")
        if self.aggregation_writer_called is not False:
            raise ValueError("trend surface must never call an aggregation writer")

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "movement_ids": list(self.movement_ids),
            "authority": dict(self.authority),
            "observations": [row.to_plain() for row in self.observations],
            "outcome_counts": dict(self.outcome_counts),
            "total_count": self.total_count,
            "degraded_readback": self.degraded_readback,
            "no_call_durable_aggregation": self.no_call_durable_aggregation,
            "aggregation_writer_called": self.aggregation_writer_called,
            "no_call_reason": self.no_call_reason,
        }


def consume_report_quality_trend_evidence(
    observations: Iterable[ReportQualityTrendObservation],
) -> ReportQualityTrendReadback:
    """Classify typed trend observations without any aggregation effect."""

    rows = tuple(
        row
        if isinstance(row, ReportQualityTrendObservation)
        else ReportQualityTrendObservation(**row)
        for row in observations
    )
    counts = {outcome: 0 for outcome in ("passed", "held", "blocked", "unknown")}
    for row in rows:
        counts[row.outcome] += 1
    degraded = any(
        row.fallback_used or row.outcome in ("held", "blocked", "unknown")
        for row in rows
    )
    return ReportQualityTrendReadback(
        schema=SURFACE_SCHEMA,
        movement_ids=MOVEMENT_IDS,
        authority=authority_ceiling(),
        observations=rows,
        outcome_counts=counts,
        total_count=len(rows),
        degraded_readback=degraded,
    )


def project_quality_trend_summary(
    readback: ReportQualityTrendReadback,
) -> dict[str, Any]:
    """Render a deterministic summary payload."""

    if not isinstance(readback, ReportQualityTrendReadback):
        raise TypeError("quality trend summary requires typed readback")
    return {
        "schema": readback.schema,
        "movement_ids": list(readback.movement_ids),
        "outcome_counts": dict(readback.outcome_counts),
        "total_count": readback.total_count,
        "degraded_readback": readback.degraded_readback,
        "no_call_durable_aggregation": readback.no_call_durable_aggregation,
        "aggregation_writer_called": readback.aggregation_writer_called,
    }


__all__ = [
    "AUTHORITY_KEYS",
    "DECISION_OWNER",
    "MOVEMENT_IDS",
    "SURFACE_SCHEMA",
    "QualityTrendOutcome",
    "ReportQualityTrendObservation",
    "ReportQualityTrendReadback",
    "authority_ceiling",
    "consume_report_quality_trend_evidence",
    "project_quality_trend_summary",
]
