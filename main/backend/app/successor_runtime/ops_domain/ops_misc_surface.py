"""Per-group ops-misc surface for ALL-SM-018.

Remaining backend capability groups receive explicit successor dispositions:
typed read-only surfaces, explicit rejection or declared loss.  No group gets
a silent no-call and no group receives write/execution authority here.
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

SURFACE_SCHEMA = "mrw.successor.ops-domain.ops-misc.surface.v1"
MOVEMENT_IDS: tuple[str, ...] = ("ALL-SM-018",)
DECISION_OWNER = "MRW admin/ops owner (B-recheck); S2c decision owner"

OpsMiscGroup = Literal[
    "admin_raw_data",
    "admin_graphs",
    "crawler",
    "clue_chains",
    "codex_auth",
    "keywords",
    "stats",
    "skills",
    "project_customization",
]
GROUP_COVERAGE: tuple[str, ...] = (
    "admin_raw_data",
    "admin_graphs",
    "crawler",
    "clue_chains",
    "codex_auth",
    "keywords",
    "stats",
    "skills",
    "project_customization",
)


@dataclass(frozen=True, slots=True)
class OpsMiscGroupDecision:
    """One explicit per-group ALL-SM-018 disposition."""

    group: OpsMiscGroup
    disposition: Literal[
        "REIMPLEMENTED_AS_TYPED_READONLY_SURFACE",
        "EXPLICITLY_REJECTED",
        "DECLARED_LOSS",
    ]
    decision_owner: str
    reason_code: str
    surface_id: str
    note: str = ""

    def __post_init__(self) -> None:
        if self.group not in GROUP_COVERAGE:
            raise ValueError(f"unknown group: {self.group}")
        if self.disposition not in (
            "REIMPLEMENTED_AS_TYPED_READONLY_SURFACE",
            "EXPLICITLY_REJECTED",
            "DECLARED_LOSS",
        ):
            raise ValueError(f"unknown disposition: {self.disposition}")
        object.__setattr__(
            self,
            "decision_owner",
            normalized_text(self.decision_owner, "decision_owner"),
        )
        object.__setattr__(
            self, "reason_code", normalized_text(self.reason_code, "reason_code")
        )
        object.__setattr__(
            self, "surface_id", normalized_text(self.surface_id, "surface_id")
        )
        object.__setattr__(
            self, "note", normalized_text(self.note, "note", required=False)
        )

    def to_plain(self) -> dict[str, Any]:
        return {
            "group": self.group,
            "disposition": self.disposition,
            "decision_owner": self.decision_owner,
            "reason_code": self.reason_code,
            "surface_id": self.surface_id,
            "note": self.note,
        }


DEFAULT_GROUP_DECISIONS: tuple[OpsMiscGroupDecision, ...] = (
    OpsMiscGroupDecision(
        group="admin_raw_data",
        disposition="REIMPLEMENTED_AS_TYPED_READONLY_SURFACE",
        decision_owner=DECISION_OWNER,
        reason_code="ADMIN_RAW_DATA_READBACK_ONLY",
        surface_id="ops-misc.admin_raw_data.readback.v1",
    ),
    OpsMiscGroupDecision(
        group="admin_graphs",
        disposition="REIMPLEMENTED_AS_TYPED_READONLY_SURFACE",
        decision_owner=DECISION_OWNER,
        reason_code="ADMIN_GRAPHS_READBACK_ONLY",
        surface_id="ops-misc.admin_graphs.readback.v1",
    ),
    OpsMiscGroupDecision(
        group="crawler",
        disposition="REIMPLEMENTED_AS_TYPED_READONLY_SURFACE",
        decision_owner=DECISION_OWNER,
        reason_code="CRAWLER_READBACK_ONLY_CONTROL_NO_CALL",
        surface_id="ops-misc.crawler.readback.v1",
        note="crawler management readback only; start/stop execution is no-call",
    ),
    OpsMiscGroupDecision(
        group="clue_chains",
        disposition="REIMPLEMENTED_AS_TYPED_READONLY_SURFACE",
        decision_owner=DECISION_OWNER,
        reason_code="CLUE_CHAIN_READBACK_ONLY_GRAPH_SUBMIT_NO_CALL",
        surface_id="ops-misc.clue_chains.readback.v1",
        note="clue-chain graph submit/write stays legacy-only",
    ),
    OpsMiscGroupDecision(
        group="codex_auth",
        disposition="REIMPLEMENTED_AS_TYPED_READONLY_SURFACE",
        decision_owner=DECISION_OWNER,
        reason_code="CODEX_AUTH_STRUCTURAL_STATUS_ONLY_CREDENTIAL_READ_FALSE",
        surface_id="ops-misc.codex_auth.structural_status.v1",
        note="no credential value is read or copied",
    ),
    OpsMiscGroupDecision(
        group="keywords",
        disposition="REIMPLEMENTED_AS_TYPED_READONLY_SURFACE",
        decision_owner=DECISION_OWNER,
        reason_code="KEYWORD_READBACK_ONLY",
        surface_id="ops-misc.keywords.readback.v1",
    ),
    OpsMiscGroupDecision(
        group="stats",
        disposition="REIMPLEMENTED_AS_TYPED_READONLY_SURFACE",
        decision_owner=DECISION_OWNER,
        reason_code="STATS_READBACK_ONLY",
        surface_id="ops-misc.stats.readback.v1",
    ),
    OpsMiscGroupDecision(
        group="skills",
        disposition="EXPLICITLY_REJECTED",
        decision_owner=DECISION_OWNER,
        reason_code="NO_CALL_SKILLS_INVOCATION_RUNTIME",
        surface_id="ops-misc.skills.invocation.explicitly-rejected.v1",
        note="legacy skills invocation runtime is not carried by successor",
    ),
    OpsMiscGroupDecision(
        group="project_customization",
        disposition="DECLARED_LOSS",
        decision_owner=DECISION_OWNER,
        reason_code="PROJECT_CUSTOMIZATION_EXECUTION_LOSS_READBACK_FOLDED",
        surface_id="ops-misc.project_customization.declared-loss.v1",
        note="typed readback is folded into projects_config_surface",
    ),
)


@dataclass(frozen=True, slots=True)
class OpsMiscSurfaceManifest:
    """Immutable per-group disposition manifest for ALL-SM-018."""

    schema: str
    movement_ids: tuple[str, ...]
    authority: dict[str, bool]
    group_decisions: tuple[OpsMiscGroupDecision, ...]
    note: str = ""

    def __post_init__(self) -> None:
        if self.schema != SURFACE_SCHEMA:
            raise ValueError("OpsMiscSurfaceManifest.schema is not frozen")
        if self.movement_ids != MOVEMENT_IDS:
            raise ValueError("OpsMiscSurfaceManifest.movement_ids drift")
        require_authority_false(self.authority)
        object.__setattr__(self, "group_decisions", tuple(self.group_decisions))
        object.__setattr__(
            self, "note", normalized_text(self.note, "note", required=False)
        )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "movement_ids": list(self.movement_ids),
            "authority": dict(self.authority),
            "group_decisions": [
                decision.to_plain() for decision in self.group_decisions
            ],
            "note": self.note,
        }

    def digest(self) -> str:
        return stable_sha256(self.to_plain())


def project_ops_misc_surface(
    group_decisions: Any = (),
) -> OpsMiscSurfaceManifest:
    """Merge defaults and caller decisions, requiring all nine groups."""

    merged: dict[str, OpsMiscGroupDecision] = {
        decision.group: decision for decision in DEFAULT_GROUP_DECISIONS
    }
    for decision in group_decisions:
        item = (
            decision
            if isinstance(decision, OpsMiscGroupDecision)
            else OpsMiscGroupDecision(**decision)
        )
        merged[item.group] = item
    missing = tuple(group for group in GROUP_COVERAGE if group not in merged)
    if missing:
        raise ValueError("ops-misc surface requires groups: " + ",".join(missing))
    decisions = tuple(merged[group] for group in GROUP_COVERAGE)
    for decision in decisions:
        if not decision.decision_owner:
            raise ValueError("group decision requires an explicit decision_owner")
    return OpsMiscSurfaceManifest(
        schema=SURFACE_SCHEMA,
        movement_ids=MOVEMENT_IDS,
        authority=authority_ceiling(),
        group_decisions=decisions,
    )


__all__ = [
    "DECISION_OWNER",
    "DEFAULT_GROUP_DECISIONS",
    "GROUP_COVERAGE",
    "MOVEMENT_IDS",
    "SURFACE_SCHEMA",
    "OpsMiscGroup",
    "OpsMiscGroupDecision",
    "OpsMiscSurfaceManifest",
    "project_ops_misc_surface",
]
