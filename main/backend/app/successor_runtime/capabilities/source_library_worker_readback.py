"""Source-library resource worker readback surface (ALL-SM-004).

The module projects typed source-library worker observations into a successor
line readback.  An admitted provider-dispatch-boundary observation is only a
readback record; it never dispatches a provider.
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
SURFACE_SCHEMA = "mrw.successor.c2.source-library-worker-readback.surface.v1"
MOVEMENT_IDS: tuple[str, ...] = ("ALL-SM-004",)
DECISION_OWNER = (
    "MRW source-library/resource lane owner (B-recheck); S2c decision owner"
)
GuardDecision = Literal["admitted", "rejected", "missing"]
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
    if any(marker in text.lower() for marker in _CREDENTIAL_MARKERS):
        raise ValueError(f"{name} must not carry credential-like raw material")
    return text


@dataclass(frozen=True, slots=True)
class SourceLibraryWorkerObservation:
    """One typed source-library worker observation."""

    item_key: str
    plan_mode: Literal["resolver", "runner", "sync", "review"]
    phase: Literal[
        "planned",
        "provider_dispatch_boundary",
        "completed_readback",
    ]
    guard_decision: GuardDecision
    observed_at: str
    source_ref: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "item_key", _text(self.item_key, "item_key"))
        if self.plan_mode not in ("resolver", "runner", "sync", "review"):
            raise ValueError(f"unknown plan_mode: {self.plan_mode}")
        if self.phase not in (
            "planned",
            "provider_dispatch_boundary",
            "completed_readback",
        ):
            raise ValueError(f"unknown phase: {self.phase}")
        if self.guard_decision not in ("admitted", "rejected", "missing"):
            raise ValueError(f"unknown guard_decision: {self.guard_decision}")
        object.__setattr__(self, "observed_at", _text(self.observed_at, "observed_at"))
        object.__setattr__(
            self,
            "source_ref",
            _text(self.source_ref, "source_ref", required=False),
        )

    def to_plain(self) -> dict[str, Any]:
        return {
            "item_key": self.item_key,
            "plan_mode": self.plan_mode,
            "phase": self.phase,
            "guard_decision": self.guard_decision,
            "observed_at": self.observed_at,
            "source_ref": self.source_ref,
        }


@dataclass(frozen=True, slots=True)
class SourceLibraryWorkerReadback:
    """Immutable worker line readback for ALL-SM-004."""

    schema: str
    movement_ids: tuple[str, ...]
    authority: dict[str, bool]
    rows: tuple[SourceLibraryWorkerObservation, ...]
    admitted_count: int
    rejected_or_missing_count: int
    provider_dispatch_count: int = 0
    execution_fact_consumed: bool = False
    line_guard_fail_closed: bool = True

    def __post_init__(self) -> None:
        if self.schema != SURFACE_SCHEMA:
            raise ValueError("SourceLibraryWorkerReadback.schema is not frozen")
        if self.movement_ids != MOVEMENT_IDS:
            raise ValueError("SourceLibraryWorkerReadback.movement_ids drift")
        if any(value is not False for value in self.authority.values()):
            raise ValueError("source-library readback authority must be all false")
        object.__setattr__(self, "rows", tuple(self.rows))
        if self.provider_dispatch_count != 0:
            raise ValueError("source-library readback never dispatches providers")
        if self.line_guard_fail_closed is not True:
            raise ValueError("source-library line guard must stay fail-closed")

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "movement_ids": list(self.movement_ids),
            "authority": dict(self.authority),
            "rows": [row.to_plain() for row in self.rows],
            "admitted_count": self.admitted_count,
            "rejected_or_missing_count": self.rejected_or_missing_count,
            "provider_dispatch_count": self.provider_dispatch_count,
            "execution_fact_consumed": self.execution_fact_consumed,
            "line_guard_fail_closed": self.line_guard_fail_closed,
        }


def project_source_library_worker_readback(
    records: Iterable[SourceLibraryWorkerObservation],
) -> SourceLibraryWorkerReadback:
    """Project typed observations without dispatching any provider."""

    rows = tuple(
        row
        if isinstance(row, SourceLibraryWorkerObservation)
        else SourceLibraryWorkerObservation(**row)
        for row in records
    )
    admitted = sum(1 for row in rows if row.guard_decision == "admitted")
    rejected_or_missing = len(rows) - admitted
    execution_fact_consumed = any(
        row.guard_decision == "admitted"
        and row.phase in ("provider_dispatch_boundary", "completed_readback")
        for row in rows
    )
    return SourceLibraryWorkerReadback(
        schema=SURFACE_SCHEMA,
        movement_ids=MOVEMENT_IDS,
        authority=authority_ceiling(),
        rows=rows,
        admitted_count=admitted,
        rejected_or_missing_count=rejected_or_missing,
        provider_dispatch_count=0,
        execution_fact_consumed=execution_fact_consumed,
        line_guard_fail_closed=True,
    )


def project_source_library_matrix_row(
    readback: SourceLibraryWorkerReadback,
) -> dict[str, Any]:
    """Render the resource_source_library evidence-matrix row payload."""

    if not isinstance(readback, SourceLibraryWorkerReadback):
        raise TypeError("source-library matrix row requires typed readback")
    if readback.rejected_or_missing_count:
        status = "blocked"
        reason_code = "source_library_guard_blocked_or_missing"
    elif not readback.rows:
        status = "unknown"
        reason_code = "source_library_readback_missing"
    else:
        status = "passed"
        reason_code = "source_library_worker_readback_passed"
    return {
        "line_key": "resource_source_library",
        "status": status,
        "reason_code": reason_code,
        "execution_fact_consumed": readback.execution_fact_consumed,
        "provider_dispatch_count": readback.provider_dispatch_count,
        "authority": dict(readback.authority),
    }


__all__ = [
    "AUTHORITY_KEYS",
    "DECISION_OWNER",
    "MOVEMENT_IDS",
    "SURFACE_SCHEMA",
    "GuardDecision",
    "SourceLibraryWorkerObservation",
    "SourceLibraryWorkerReadback",
    "authority_ceiling",
    "project_source_library_matrix_row",
    "project_source_library_worker_readback",
]
