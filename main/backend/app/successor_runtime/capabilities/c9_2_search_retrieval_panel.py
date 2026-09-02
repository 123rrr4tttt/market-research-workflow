"""C9.2 search retrieval-run panel successor (ALL-SM-003).

The module projects typed retrieval-run observations into the read-only panel
contract consumed by the C9.2 frontend namespace.  It does not read the donor
panel, run searches or touch the index.
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
SURFACE_SCHEMA = "mrw.successor.c9-2.search-retrieval-panel.surface.v1"
MOVEMENT_IDS: tuple[str, ...] = ("ALL-SM-003",)
DECISION_OWNER = (
    "MRW search/discovery worker lane owner (B-recheck); S2c decision owner"
)
RetrievalRunState = Literal["terminal", "running", "missing", "undecidable"]
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
class SearchRetrievalRunObservation:
    """One typed retrieval-run observation for the panel."""

    retrieval_run_id: str
    search_kind: str
    run_state: RetrievalRunState
    index_freshness: Literal["fresh", "stale", "unknown"]
    observed_at: str
    source_ref: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "retrieval_run_id",
            _text(self.retrieval_run_id, "retrieval_run_id"),
        )
        object.__setattr__(self, "search_kind", _text(self.search_kind, "search_kind"))
        if self.run_state not in ("terminal", "running", "missing", "undecidable"):
            raise ValueError(f"unknown run_state: {self.run_state}")
        if self.index_freshness not in ("fresh", "stale", "unknown"):
            raise ValueError(f"unknown index_freshness: {self.index_freshness}")
        object.__setattr__(self, "observed_at", _text(self.observed_at, "observed_at"))
        object.__setattr__(
            self,
            "source_ref",
            _text(self.source_ref, "source_ref", required=False),
        )

    def to_plain(self) -> dict[str, Any]:
        return {
            "retrieval_run_id": self.retrieval_run_id,
            "search_kind": self.search_kind,
            "run_state": self.run_state,
            "index_freshness": self.index_freshness,
            "observed_at": self.observed_at,
            "source_ref": self.source_ref,
        }


DECLARED_LOSS: tuple[str, ...] = (
    "dashboard-search-retrieval-run-panel-ui-byte-loss",
    "search-index-write-no-call",
)


@dataclass(frozen=True, slots=True)
class SearchRetrievalPanelPayload:
    """Immutable read-only C9.2 panel payload."""

    schema: str
    movement_ids: tuple[str, ...]
    authority: dict[str, bool]
    panel_status: Literal["READY", "DEGRADED", "BLOCKED", "NO_PANEL"]
    rows: tuple[SearchRetrievalRunObservation, ...]
    declared_loss: tuple[str, ...]
    no_fake_panel_success: bool = True

    def __post_init__(self) -> None:
        if self.schema != SURFACE_SCHEMA:
            raise ValueError("SearchRetrievalPanelPayload.schema is not frozen")
        if self.movement_ids != MOVEMENT_IDS:
            raise ValueError("SearchRetrievalPanelPayload.movement_ids drift")
        if any(value is not False for value in self.authority.values()):
            raise ValueError("search retrieval panel authority must be all false")
        if self.panel_status not in ("READY", "DEGRADED", "BLOCKED", "NO_PANEL"):
            raise ValueError(f"unknown panel_status: {self.panel_status}")
        object.__setattr__(self, "rows", tuple(self.rows))
        object.__setattr__(self, "declared_loss", tuple(self.declared_loss))
        if self.no_fake_panel_success is not True:
            raise ValueError("search panel must not fabricate success")

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "movement_ids": list(self.movement_ids),
            "authority": dict(self.authority),
            "panel_status": self.panel_status,
            "rows": [row.to_plain() for row in self.rows],
            "declared_loss": list(self.declared_loss),
            "no_fake_panel_success": self.no_fake_panel_success,
        }


def project_search_retrieval_panel(
    observations: Iterable[SearchRetrievalRunObservation],
) -> SearchRetrievalPanelPayload:
    """Project typed observations without reading or writing search state."""

    rows = tuple(
        row
        if isinstance(row, SearchRetrievalRunObservation)
        else SearchRetrievalRunObservation(**row)
        for row in observations
    )
    if not rows:
        status: Literal["READY", "DEGRADED", "BLOCKED", "NO_PANEL"] = "NO_PANEL"
    elif any(
        row.run_state == "undecidable" or row.index_freshness == "unknown"
        for row in rows
    ):
        status = "BLOCKED"
    elif any(
        row.run_state == "missing"
        or row.run_state == "terminal"
        and row.index_freshness == "stale"
        for row in rows
    ):
        status = "DEGRADED"
    elif all(
        row.run_state == "terminal" and row.index_freshness == "fresh" for row in rows
    ):
        status = "READY"
    else:
        status = "DEGRADED"
    return SearchRetrievalPanelPayload(
        schema=SURFACE_SCHEMA,
        movement_ids=MOVEMENT_IDS,
        authority=authority_ceiling(),
        panel_status=status,
        rows=rows,
        declared_loss=DECLARED_LOSS,
    )


__all__ = [
    "AUTHORITY_KEYS",
    "DECISION_OWNER",
    "DECLARED_LOSS",
    "MOVEMENT_IDS",
    "SURFACE_SCHEMA",
    "RetrievalRunState",
    "SearchRetrievalPanelPayload",
    "SearchRetrievalRunObservation",
    "authority_ceiling",
    "project_search_retrieval_panel",
]
