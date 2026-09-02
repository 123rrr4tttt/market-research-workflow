"""Typed projects/config/workflow read-only surface (ALL-SM-005).

The surface re-expresses project/config/process-history readbacks as typed
successor records.  Legacy mutation/execution workflows are recorded as
explicit no-call decisions: this module grants no write authority and performs
no runtime effect.  It is exposed through the C9.1 horizontal assembly
namespace without changing the 30-cell topology.
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

SURFACE_SCHEMA = "mrw.successor.ops-domain.projects-config.surface.v1"
MOVEMENT_IDS: tuple[str, ...] = ("ALL-SM-005",)
DECISION_OWNER = "MRW project/config workflow owner (B-recheck); S2c decision owner"

ProjectConfigReadKind = Literal[
    "project_readback",
    "config_readback",
    "llm_config_readback",
    "process_history_readback",
    "customization_readback",
]
ProjectConfigMutationKind = Literal[
    "project_create",
    "project_update",
    "project_archive",
    "project_activate",
    "project_delete",
    "config_write",
    "llm_config_write",
    "customization_apply",
    "customization_rollback",
    "customization_promote",
]
NoCallDisposition = Literal["EXPLICITLY_REJECTED", "DECLARED_LOSS"]


@dataclass(frozen=True, slots=True)
class ProjectConfigReadbackRow:
    """One typed project/config/workflow readback row."""

    row_id: str
    project_key: str
    read_kind: ProjectConfigReadKind
    source_refs: tuple[str, ...] = ()
    observed_at: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "row_id", normalized_text(self.row_id, "row_id"))
        object.__setattr__(
            self, "project_key", normalized_text(self.project_key, "project_key")
        )
        if self.read_kind not in ProjectConfigReadKind.__args__:
            raise ValueError(f"unknown read_kind: {self.read_kind}")
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
            "project_key": self.project_key,
            "read_kind": self.read_kind,
            "source_refs": list(self.source_refs),
            "observed_at": self.observed_at,
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class ProjectConfigNoCallDecision:
    """Explicit no-call decision for one legacy mutation/workflow action."""

    decision_id: str
    mutation_kind: ProjectConfigMutationKind
    disposition: NoCallDisposition
    decision_owner: str
    reason_code: str = "NO_CALL_MUTATION_WRITE_AUTHORITY_ABSENT"
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "decision_id", normalized_text(self.decision_id, "decision_id")
        )
        if self.mutation_kind not in ProjectConfigMutationKind.__args__:
            raise ValueError(f"unknown mutation_kind: {self.mutation_kind}")
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
            or "NO_CALL_MUTATION_WRITE_AUTHORITY_ABSENT",
        )
        object.__setattr__(
            self, "note", normalized_text(self.note, "note", required=False)
        )

    def to_plain(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "mutation_kind": self.mutation_kind,
            "disposition": self.disposition,
            "decision_owner": self.decision_owner,
            "reason_code": self.reason_code,
            "note": self.note,
        }


DEFAULT_NO_CALL_DECISIONS: tuple[ProjectConfigNoCallDecision, ...] = (
    ProjectConfigNoCallDecision(
        decision_id="ALL-SM-005.project-crud.explicitly-rejected.v1",
        mutation_kind="project_create",
        disposition="EXPLICITLY_REJECTED",
        decision_owner=DECISION_OWNER,
        note="project CRUD writes are not implemented in this local typed surface",
    ),
    ProjectConfigNoCallDecision(
        decision_id="ALL-SM-005.config-write.explicitly-rejected.v1",
        mutation_kind="config_write",
        disposition="EXPLICITLY_REJECTED",
        decision_owner=DECISION_OWNER,
        note="config/env writes stay legacy-only",
    ),
    ProjectConfigNoCallDecision(
        decision_id="ALL-SM-005.customization-promote.declared-loss.v1",
        mutation_kind="customization_promote",
        disposition="DECLARED_LOSS",
        decision_owner=DECISION_OWNER,
        note="customization promote execution is not carried by successor",
    ),
)


@dataclass(frozen=True, slots=True)
class ProjectConfigSurfaceManifest:
    """Immutable read-only surface projection for ALL-SM-005."""

    schema: str
    movement_ids: tuple[str, ...]
    authority: dict[str, bool]
    readback_rows: tuple[ProjectConfigReadbackRow, ...]
    no_call_decisions: tuple[ProjectConfigNoCallDecision, ...]
    note: str = ""

    def __post_init__(self) -> None:
        if self.schema != SURFACE_SCHEMA:
            raise ValueError("ProjectConfigSurfaceManifest.schema is not frozen")
        if self.movement_ids != MOVEMENT_IDS:
            raise ValueError("ProjectConfigSurfaceManifest.movement_ids drift")
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


def project_projects_config_surface(
    readback_rows: Any,
    no_call_decisions: Any = (),
) -> ProjectConfigSurfaceManifest:
    """Project caller-typed records into one immutable read-only manifest."""

    rows = tuple(
        row
        if isinstance(row, ProjectConfigReadbackRow)
        else ProjectConfigReadbackRow(**row)
        for row in readback_rows
    )
    decisions = tuple(
        decision
        if isinstance(decision, ProjectConfigNoCallDecision)
        else ProjectConfigNoCallDecision(**decision)
        for decision in no_call_decisions
    )
    for decision in decisions:
        if not decision.decision_owner:
            raise ValueError("no-call decision requires an explicit decision_owner")
    return ProjectConfigSurfaceManifest(
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
    "NoCallDisposition",
    "ProjectConfigMutationKind",
    "ProjectConfigNoCallDecision",
    "ProjectConfigReadKind",
    "ProjectConfigReadbackRow",
    "ProjectConfigSurfaceManifest",
    "project_projects_config_surface",
]
