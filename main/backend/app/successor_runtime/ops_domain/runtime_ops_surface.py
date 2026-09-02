"""Typed runtime-ops read-only/control surface (ALL-SM-008).

Health, deep-health, metrics, dependency and process readback rows are typed
successor records.  Retry/cancel and service/probe execution are explicit
no-call control decisions: no executor, scheduler or probe is started here.
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

SURFACE_SCHEMA = "mrw.successor.ops-domain.runtime-ops.surface.v1"
MOVEMENT_IDS: tuple[str, ...] = ("ALL-SM-008",)
DECISION_OWNER = "MRW runtime ops owner (B-recheck); S2c decision owner"

RuntimeOpsReadKind = Literal[
    "app_health",
    "deep_health",
    "metrics",
    "process_readback",
    "process_history",
    "dependency_readback",
]
RuntimeStatus = Literal["passed", "degraded", "blocked", "unknown"]


@dataclass(frozen=True, slots=True)
class RuntimeOpsReadbackRow:
    """One typed runtime-ops readback row."""

    row_id: str
    read_kind: RuntimeOpsReadKind
    probe_name: str
    observed_at: str = ""
    status: RuntimeStatus = "unknown"
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "row_id", normalized_text(self.row_id, "row_id"))
        if self.read_kind not in RuntimeOpsReadKind.__args__:
            raise ValueError(f"unknown read_kind: {self.read_kind}")
        if self.status not in ("passed", "degraded", "blocked", "unknown"):
            raise ValueError(f"unknown status: {self.status}")
        object.__setattr__(
            self, "probe_name", normalized_text(self.probe_name, "probe_name")
        )
        object.__setattr__(
            self,
            "observed_at",
            normalized_text(self.observed_at, "observed_at", required=False),
        )
        object.__setattr__(
            self, "note", normalized_text(self.note, "note", required=False)
        )

    def to_plain(self) -> dict[str, Any]:
        return {
            "row_id": self.row_id,
            "read_kind": self.read_kind,
            "probe_name": self.probe_name,
            "observed_at": self.observed_at,
            "status": self.status,
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class RuntimeOpsNoCallDecision:
    """Explicit no-call decision for a control-plane execution action."""

    decision_id: str
    action_kind: str
    disposition: Literal["EXPLICITLY_REJECTED", "DECLARED_LOSS"]
    decision_owner: str
    reason_code: str = "NO_CALL_EXECUTOR_AUTHORITY_ABSENT"
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "decision_id", normalized_text(self.decision_id, "decision_id")
        )
        object.__setattr__(
            self, "action_kind", normalized_text(self.action_kind, "action_kind")
        )
        if self.disposition not in ("EXPLICITLY_REJECTED", "DECLARED_LOSS"):
            raise ValueError(f"unknown disposition: {self.disposition}")
        object.__setattr__(
            self,
            "decision_owner",
            normalized_text(self.decision_owner, "decision_owner"),
        )
        object.__setattr__(
            self,
            "reason_code",
            normalized_text(self.reason_code, "reason_code", required=False)
            or "NO_CALL_EXECUTOR_AUTHORITY_ABSENT",
        )
        object.__setattr__(
            self, "note", normalized_text(self.note, "note", required=False)
        )

    def to_plain(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "action_kind": self.action_kind,
            "disposition": self.disposition,
            "decision_owner": self.decision_owner,
            "reason_code": self.reason_code,
            "note": self.note,
        }


DEFAULT_NO_CALL_DECISIONS: tuple[RuntimeOpsNoCallDecision, ...] = (
    RuntimeOpsNoCallDecision(
        decision_id="ALL-SM-008.process-retry.explicitly-rejected.v1",
        action_kind="process_retry",
        disposition="EXPLICITLY_REJECTED",
        decision_owner=DECISION_OWNER,
        note="retry execution is not granted to this typed control surface",
    ),
    RuntimeOpsNoCallDecision(
        decision_id="ALL-SM-008.process-cancel.explicitly-rejected.v1",
        action_kind="process_cancel",
        disposition="EXPLICITLY_REJECTED",
        decision_owner=DECISION_OWNER,
        note="cancel execution is not granted to this typed control surface",
    ),
    RuntimeOpsNoCallDecision(
        decision_id="ALL-SM-008.probe-execution.explicitly-rejected.v1",
        action_kind="real_health_probe_execution",
        disposition="EXPLICITLY_REJECTED",
        decision_owner=DECISION_OWNER,
        note="real probes are not started by the pure surface module",
    ),
    RuntimeOpsNoCallDecision(
        decision_id="ALL-SM-008.service-lifecycle.explicitly-rejected.v1",
        action_kind="service_start_stop",
        disposition="EXPLICITLY_REJECTED",
        decision_owner=DECISION_OWNER,
        note="service lifecycle control is outside successor runtime-ops scope",
    ),
)


@dataclass(frozen=True, slots=True)
class RuntimeOpsSurfaceManifest:
    """Immutable runtime-ops readback/control projection."""

    schema: str
    movement_ids: tuple[str, ...]
    authority: dict[str, bool]
    readback_rows: tuple[RuntimeOpsReadbackRow, ...]
    no_call_decisions: tuple[RuntimeOpsNoCallDecision, ...]
    note: str = ""

    def __post_init__(self) -> None:
        if self.schema != SURFACE_SCHEMA:
            raise ValueError("RuntimeOpsSurfaceManifest.schema is not frozen")
        if self.movement_ids != MOVEMENT_IDS:
            raise ValueError("RuntimeOpsSurfaceManifest.movement_ids drift")
        require_authority_false(self.authority)
        object.__setattr__(self, "readback_rows", tuple(self.readback_rows))
        object.__setattr__(self, "no_call_decisions", tuple(self.no_call_decisions))
        object.__setattr__(
            self, "note", normalized_text(self.note, "note", required=False)
        )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "movement_ids": list(self.movement_ids),
            "authority": dict(self.authority),
            "readback_rows": [row.to_plain() for row in self.readback_rows],
            "no_call_decisions": [
                decision.to_plain() for decision in self.no_call_decisions
            ],
            "note": self.note,
        }

    def digest(self) -> str:
        return stable_sha256(self.to_plain())


def _merge_runtime_no_call(
    decisions: tuple[RuntimeOpsNoCallDecision, ...],
) -> tuple[RuntimeOpsNoCallDecision, ...]:
    by_id = {decision.decision_id: decision for decision in decisions}
    for decision in DEFAULT_NO_CALL_DECISIONS:
        by_id.setdefault(decision.decision_id, decision)
    return tuple(by_id.values())


def project_runtime_ops_surface(
    readback_rows: Any,
    no_call_decisions: Any = (),
) -> RuntimeOpsSurfaceManifest:
    """Project typed runtime readback rows and no-call decisions."""

    rows = tuple(
        row if isinstance(row, RuntimeOpsReadbackRow) else RuntimeOpsReadbackRow(**row)
        for row in readback_rows
    )
    supplied = tuple(
        decision
        if isinstance(decision, RuntimeOpsNoCallDecision)
        else RuntimeOpsNoCallDecision(**decision)
        for decision in no_call_decisions
    )
    decisions = _merge_runtime_no_call(supplied)
    for decision in decisions:
        if not decision.decision_owner:
            raise ValueError("no-call decision requires an explicit decision_owner")
    return RuntimeOpsSurfaceManifest(
        schema=SURFACE_SCHEMA,
        movement_ids=MOVEMENT_IDS,
        authority=authority_ceiling(),
        readback_rows=rows,
        no_call_decisions=decisions,
    )


__all__ = [
    "DECISION_OWNER",
    "DEFAULT_NO_CALL_DECISIONS",
    "MOVEMENT_IDS",
    "SURFACE_SCHEMA",
    "RuntimeOpsNoCallDecision",
    "RuntimeOpsReadKind",
    "RuntimeOpsReadbackRow",
    "RuntimeOpsSurfaceManifest",
    "RuntimeStatus",
    "project_runtime_ops_surface",
]
