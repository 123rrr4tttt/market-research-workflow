"""Typed dashboard/admin/governance read-only surface (ALL-SM-006).

Dashboard read projections, aggregator sync status and retention status are
carried as typed successor readback records.  Report-from-filter synthesis and
admin/governance mutation actions are explicit no-call decisions with named
owners; this module never executes retention, sync, document or graph actions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .base import (
    authority_ceiling,
    normalized_string_tuple,
    normalized_text,
    require_authority_false,
    stable_sha256,
)

SURFACE_SCHEMA = "mrw.successor.ops-domain.dashboard-admin.surface.v1"
MOVEMENT_IDS: tuple[str, ...] = ("ALL-SM-006",)
DECISION_OWNER = "MRW dashboard/admin/governance owner (B-recheck); S2c decision owner"

DashboardReadKind = Literal[
    "dashboard_read_projection",
    "report_readback",
    "admin_readback",
    "aggregator_sync_status",
    "retention_status",
]


@dataclass(frozen=True, slots=True)
class DashboardAdminReadbackRow:
    """One typed dashboard/admin readback row."""

    row_id: str
    read_kind: DashboardReadKind
    surface_key: str
    source_refs: tuple[str, ...] = ()
    observed_at: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "row_id", normalized_text(self.row_id, "row_id"))
        if self.read_kind not in DashboardReadKind.__args__:
            raise ValueError(f"unknown read_kind: {self.read_kind}")
        object.__setattr__(
            self,
            "surface_key",
            normalized_text(self.surface_key, "surface_key"),
        )
        object.__setattr__(
            self,
            "source_refs",
            normalized_string_tuple(self.source_refs, "source_refs"),
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
            "surface_key": self.surface_key,
            "source_refs": list(self.source_refs),
            "observed_at": self.observed_at,
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class DashboardAdminNoCallDecision:
    """One explicit no-call decision on a legacy action surface."""

    decision_id: str
    action_kind: str
    disposition: Literal["EXPLICITLY_REJECTED", "DECLARED_LOSS"]
    decision_owner: str
    reason_code: str
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
            normalized_text(self.reason_code, "reason_code"),
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


REPORT_CLOSURE_DECISION = DashboardAdminNoCallDecision(
    decision_id="ALL-SM-006.report-from-filter-synthesis.explicitly-rejected.v1",
    action_kind="report_from_filter_synthesis",
    disposition="EXPLICITLY_REJECTED",
    decision_owner=DECISION_OWNER,
    reason_code="NO_CALL_REPORT_FROM_FILTER_SYNTHESIS",
    note="Legacy report-from-filter synthesis is not reimplemented by successor",
)

DEFAULT_NO_CALL_DECISIONS: tuple[DashboardAdminNoCallDecision, ...] = (
    DashboardAdminNoCallDecision(
        decision_id="ALL-SM-006.admin-document-action.explicitly-rejected.v1",
        action_kind="admin_document_action",
        disposition="EXPLICITLY_REJECTED",
        decision_owner=DECISION_OWNER,
        reason_code="NO_CALL_ADMIN_MUTATION_AUTHORITY_ABSENT",
    ),
    DashboardAdminNoCallDecision(
        decision_id="ALL-SM-006.admin-graph-action.explicitly-rejected.v1",
        action_kind="admin_graph_action",
        disposition="EXPLICITLY_REJECTED",
        decision_owner=DECISION_OWNER,
        reason_code="NO_CALL_ADMIN_MUTATION_AUTHORITY_ABSENT",
    ),
    DashboardAdminNoCallDecision(
        decision_id="ALL-SM-006.retention-cleanup.explicitly-rejected.v1",
        action_kind="retention_cleanup",
        disposition="EXPLICITLY_REJECTED",
        decision_owner=DECISION_OWNER,
        reason_code="NO_CALL_RETENTION_WRITE_AUTHORITY_ABSENT",
    ),
    DashboardAdminNoCallDecision(
        decision_id="ALL-SM-006.aggregator-sync-write.explicitly-rejected.v1",
        action_kind="aggregator_sync_write",
        disposition="EXPLICITLY_REJECTED",
        decision_owner=DECISION_OWNER,
        reason_code="NO_CALL_AGGREGATOR_SYNC_WRITE_AUTHORITY_ABSENT",
    ),
)


@dataclass(frozen=True, slots=True)
class DashboardAdminSurfaceManifest:
    """Immutable dashboard/admin surface projection for ALL-SM-006."""

    schema: str
    movement_ids: tuple[str, ...]
    authority: dict[str, bool]
    readback_rows: tuple[DashboardAdminReadbackRow, ...]
    no_call_decisions: tuple[DashboardAdminNoCallDecision, ...]
    note: str = ""

    def __post_init__(self) -> None:
        if self.schema != SURFACE_SCHEMA:
            raise ValueError("DashboardAdminSurfaceManifest.schema is not frozen")
        if self.movement_ids != MOVEMENT_IDS:
            raise ValueError("DashboardAdminSurfaceManifest.movement_ids drift")
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


def _merge_no_call(
    decisions: tuple[DashboardAdminNoCallDecision, ...],
) -> tuple[DashboardAdminNoCallDecision, ...]:
    by_id = {decision.decision_id: decision for decision in decisions}
    for decision in (REPORT_CLOSURE_DECISION,) + DEFAULT_NO_CALL_DECISIONS:
        by_id.setdefault(decision.decision_id, decision)
    return tuple(by_id.values())


def project_dashboard_admin_surface(
    readback_rows: Any,
    no_call_decisions: Any = (),
) -> DashboardAdminSurfaceManifest:
    """Project typed rows and no-call decisions into one immutable manifest."""

    rows = tuple(
        row
        if isinstance(row, DashboardAdminReadbackRow)
        else DashboardAdminReadbackRow(**row)
        for row in readback_rows
    )
    supplied = tuple(
        decision
        if isinstance(decision, DashboardAdminNoCallDecision)
        else DashboardAdminNoCallDecision(**decision)
        for decision in no_call_decisions
    )
    decisions = _merge_no_call(supplied)
    for decision in decisions:
        if not decision.decision_owner:
            raise ValueError("no-call decision requires an explicit decision_owner")
    return DashboardAdminSurfaceManifest(
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
    "REPORT_CLOSURE_DECISION",
    "SURFACE_SCHEMA",
    "DashboardAdminNoCallDecision",
    "DashboardAdminReadbackRow",
    "DashboardAdminSurfaceManifest",
    "DashboardReadKind",
    "project_dashboard_admin_surface",
]
