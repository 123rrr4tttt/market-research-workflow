"""Typed runtime health-matrix surface (ALL-SM-017 and ALL-GAP-002).

This module classifies caller-supplied probe observations into a deterministic
health-matrix result.  It never starts a probe, reads process state, starts
Docker or writes latest-runtime-health-matrix.json.  ALL-GAP-002 is folded
into the ALL-SM-008/ALL-SM-017 shared runtime-ops health-matrix lane.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .base import (
    authority_ceiling,
    normalized_text,
    require_authority_false,
    stable_sha256,
)

SURFACE_SCHEMA = "mrw.successor.ops-domain.health-matrix.surface.v1"
MOVEMENT_IDS: tuple[str, ...] = ("ALL-SM-017", "ALL-GAP-002")
DECISION_OWNER = "MRW runtime ops owner (B-recheck); S2c decision owner"
HEALTH_MATRIX_FOLD_NOTE = (
    "ALL-GAP-002 folds into the ALL-SM-008/ALL-SM-017 shared health-matrix "
    "surface; no duplicate implementation is introduced"
)

HealthMatrixRunMode = Literal["docker", "local", "mixed", "not_run"]
HealthProbeStatus = Literal["passed", "degraded", "blocked", "unknown"]
HealthProbeKind = Literal[
    "dependency",
    "endpoint",
    "port",
    "worker_process",
    "readiness_artifact",
]


@dataclass(frozen=True, slots=True)
class ProbeObservation:
    """One typed probe observation already supplied by the caller."""

    check_id: str
    probe_kind: HealthProbeKind
    status: HealthProbeStatus = "unknown"
    detail: str = ""
    observed_at: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "check_id", normalized_text(self.check_id, "check_id"))
        if self.probe_kind not in HealthProbeKind.__args__:
            raise ValueError(f"unknown probe_kind: {self.probe_kind}")
        if self.status not in ("passed", "degraded", "blocked", "unknown"):
            raise ValueError(f"unknown status: {self.status}")
        object.__setattr__(
            self, "detail", normalized_text(self.detail, "detail", required=False)
        )
        object.__setattr__(
            self,
            "observed_at",
            normalized_text(self.observed_at, "observed_at", required=False),
        )

    def to_plain(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "probe_kind": self.probe_kind,
            "status": self.status,
            "detail": self.detail,
            "observed_at": self.observed_at,
        }


@dataclass(frozen=True, slots=True)
class RuntimeHealthMatrixResult:
    """Deterministic health-matrix classification result."""

    schema: str
    movement_ids: tuple[str, ...]
    authority: dict[str, bool]
    run_mode: HealthMatrixRunMode
    overall_status: HealthProbeStatus
    rows: tuple[ProbeObservation, ...]
    nominal_exit_code: int
    no_probe_execution: bool = True
    note: str = ""

    def __post_init__(self) -> None:
        if self.schema != SURFACE_SCHEMA:
            raise ValueError("RuntimeHealthMatrixResult.schema is not frozen")
        if self.movement_ids != MOVEMENT_IDS:
            raise ValueError("RuntimeHealthMatrixResult.movement_ids drift")
        if self.run_mode not in ("docker", "local", "mixed", "not_run"):
            raise ValueError(f"unknown run_mode: {self.run_mode}")
        if self.overall_status not in (
            "passed",
            "degraded",
            "blocked",
            "unknown",
        ):
            raise ValueError(f"unknown overall_status: {self.overall_status}")
        require_authority_false(self.authority)
        if self.no_probe_execution is not True:
            raise ValueError("health matrix never executes probes")
        object.__setattr__(self, "rows", tuple(self.rows))
        object.__setattr__(
            self, "note", normalized_text(self.note, "note", required=False)
        )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "movement_ids": list(self.movement_ids),
            "authority": dict(self.authority),
            "run_mode": self.run_mode,
            "overall_status": self.overall_status,
            "rows": [row.to_plain() for row in self.rows],
            "nominal_exit_code": self.nominal_exit_code,
            "no_probe_execution": self.no_probe_execution,
            "note": self.note,
        }

    def digest(self) -> str:
        return stable_sha256(self.to_plain())


def project_runtime_health_matrix(
    run_mode: HealthMatrixRunMode,
    observations: Any = (),
) -> RuntimeHealthMatrixResult:
    """Classify typed observations into a passive health-matrix result."""

    if run_mode not in ("docker", "local", "mixed", "not_run"):
        raise ValueError(f"unknown run_mode: {run_mode}")
    rows = tuple(
        row if isinstance(row, ProbeObservation) else ProbeObservation(**row)
        for row in observations
    )
    if run_mode == "not_run" or not rows:
        overall: HealthProbeStatus = "unknown"
        exit_code = 3
    elif any(row.status == "blocked" for row in rows):
        overall = "blocked"
        exit_code = 3
    elif any(row.status == "degraded" for row in rows):
        overall = "degraded"
        exit_code = 1
    elif all(row.status == "passed" for row in rows):
        overall = "passed"
        exit_code = 0
    else:
        overall = "unknown"
        exit_code = 3
    return RuntimeHealthMatrixResult(
        schema=SURFACE_SCHEMA,
        movement_ids=MOVEMENT_IDS,
        authority=authority_ceiling(),
        run_mode=run_mode,
        overall_status=overall,
        rows=rows,
        nominal_exit_code=exit_code,
        note=HEALTH_MATRIX_FOLD_NOTE,
    )


__all__ = [
    "DECISION_OWNER",
    "HEALTH_MATRIX_FOLD_NOTE",
    "MOVEMENT_IDS",
    "SURFACE_SCHEMA",
    "HealthMatrixRunMode",
    "HealthProbeKind",
    "HealthProbeStatus",
    "ProbeObservation",
    "RuntimeHealthMatrixResult",
    "project_runtime_health_matrix",
]
