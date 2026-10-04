"""Search retrieval-run panel projection (historical movement ALL-SM-003).

The module projects typed retrieval-run observations into the read-only panel
contract consumed by the projection client namespace.  It does not read the
donor panel, run searches or touch the index.  Historical v1 payloads are
decoded only from their exact stored bytes and digest.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import hashlib
import json
from collections.abc import Mapping
from typing import Any, Literal, NoReturn

from functorial_kit import Failure

from mrw_functorial_kit.core.w06_semantics import (
    projection_evidence_surface_failures,
)

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
SURFACE_SCHEMA = "mrw.projection.search-retrieval-panel.surface.v2"
LEGACY_SURFACE_SCHEMA_V1 = (
    "mrw.successor.c9-2.search-retrieval-panel.surface.v1"
)
MOVEMENT_IDS: tuple[str, ...] = ("ALL-SM-003",)
DECISION_OWNER = "MRW search/discovery worker lane owner (B-recheck); S2c decision owner"
RetrievalRunState = Literal["terminal", "running", "missing", "undecidable"]
_CREDENTIAL_MARKERS = ("secret", "token", "password", "api_key", "apikey")
_FAILURE_WITNESS = "test:test_w06_c2_total_core_failure_lifts"


def _failure(
    code: str, message: str, *, public_exception: str = "ValueError", site: str = "c9_2_search_retrieval_panel"
) -> Failure:
    return projection_evidence_surface_failures.fail(
        code,
        message,
        {
            "owner": "successor_runtime.capabilities.c9_2_search_retrieval_panel",
            "site": site,
            "public_exception": public_exception,
            "public_message": message,
            "witness": _FAILURE_WITNESS,
        },
    )


def _raise_contract_failure(failure: Failure, exception_type: type[Exception] = ValueError) -> NoReturn:
    context = failure.context or {}
    if (
        failure.family != projection_evidence_surface_failures.name
        or context.get("public_exception") != exception_type.__name__
    ):
        # kit:boundary owner=c9_2_search_retrieval_panel.py class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w06_c2_total_core_failure_lifts
        raise TypeError("C9.2 contract lift context is incomplete")  # noqa: TRY003
    # kit:boundary owner=c9_2_search_retrieval_panel.py class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=projection.evidence-surface.failure witness=test:test_w06_c2_total_core_failure_lifts
    raise exception_type(str(context.get("public_message", failure.message)))


def _reject(message: str, exception_type: type[Exception] = ValueError) -> NoReturn:
    _raise_contract_failure(
        _failure("surface_contract_invalid", message, public_exception=exception_type.__name__), exception_type
    )


def authority_ceiling() -> dict[str, bool]:
    return {name: False for name in AUTHORITY_KEYS}


def _text(value: Any, name: str, *, required: bool = True) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str):
        _reject(f"{name} must be a string", TypeError)
    text = value.strip()
    if not text and required:
        _reject(f"{name} must not be blank")
    if any(marker in text.lower() for marker in _CREDENTIAL_MARKERS):
        _reject(f"{name} must not carry credential-like raw material")
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
            _reject(f"unknown run_state: {self.run_state}")
        if self.index_freshness not in ("fresh", "stale", "unknown"):
            _reject(f"unknown index_freshness: {self.index_freshness}")
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
            _reject("SearchRetrievalPanelPayload.schema is not frozen")
        if self.movement_ids != MOVEMENT_IDS:
            _reject("SearchRetrievalPanelPayload.movement_ids drift")
        if any(value is not False for value in self.authority.values()):
            _reject("search retrieval panel authority must be all false")
        if self.panel_status not in ("READY", "DEGRADED", "BLOCKED", "NO_PANEL"):
            _reject(f"unknown panel_status: {self.panel_status}")
        object.__setattr__(self, "rows", tuple(self.rows))
        object.__setattr__(self, "declared_loss", tuple(self.declared_loss))
        if self.no_fake_panel_success is not True:
            _reject("search panel must not fabricate success")

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
        row if isinstance(row, SearchRetrievalRunObservation) else SearchRetrievalRunObservation(**row)
        for row in observations
    )
    if not rows:
        status: Literal["READY", "DEGRADED", "BLOCKED", "NO_PANEL"] = "NO_PANEL"
    elif any(row.run_state == "undecidable" or row.index_freshness == "unknown" for row in rows):
        status = "BLOCKED"
    elif any(
        row.run_state == "missing" or row.run_state == "terminal" and row.index_freshness == "stale" for row in rows
    ):
        status = "DEGRADED"
    elif all(row.run_state == "terminal" and row.index_freshness == "fresh" for row in rows):
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


@dataclass(frozen=True, slots=True)
class LegacySearchRetrievalPanelReadbackV1:
    """Exact historical v1 readback; the stored document is never re-encoded."""

    raw_bytes: bytes
    content_digest: str
    payload: Mapping[str, Any]
    rows: tuple[SearchRetrievalRunObservation, ...]


def decode_legacy_search_retrieval_panel_v1(
    content: bytes,
    *,
    expected_digest: str,
) -> LegacySearchRetrievalPanelReadbackV1:
    """Decode a v1 payload only after exact byte-digest verification.

    The returned ``payload`` retains the parsed historical document.  The
    current constructor never accepts it, and no v2 digest is calculated.
    """

    if not isinstance(content, bytes):
        _reject("legacy search panel content must be exact bytes", TypeError)
    if not isinstance(expected_digest, str):
        _reject("legacy search panel digest must be a string", TypeError)
    digest = hashlib.sha256(content).hexdigest()
    if expected_digest != digest:
        _reject("legacy search panel exact bytes do not match the stored digest")
    try:
        decoded = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _reject(f"legacy search panel bytes are not UTF-8 JSON: {exc}")
    if not isinstance(decoded, dict):
        _reject("legacy search panel payload must be a JSON object")
    schema = decoded.get("schema")
    if schema != LEGACY_SURFACE_SCHEMA_V1:
        _reject(f"unsupported legacy search panel schema version: {schema}")
    raw_rows = decoded.get("rows", [])
    if not isinstance(raw_rows, list):
        _reject("legacy search panel rows must be a list")
    rows = tuple(
        row if isinstance(row, SearchRetrievalRunObservation) else SearchRetrievalRunObservation(**row)
        for row in raw_rows
    )
    return LegacySearchRetrievalPanelReadbackV1(
        raw_bytes=content,
        content_digest=expected_digest,
        payload=decoded,
        rows=rows,
    )


__all__ = [
    "AUTHORITY_KEYS",
    "DECISION_OWNER",
    "DECLARED_LOSS",
    "MOVEMENT_IDS",
    "SURFACE_SCHEMA",
    "LEGACY_SURFACE_SCHEMA_V1",
    "LegacySearchRetrievalPanelReadbackV1",
    "RetrievalRunState",
    "SearchRetrievalPanelPayload",
    "SearchRetrievalRunObservation",
    "authority_ceiling",
    "decode_legacy_search_retrieval_panel_v1",
    "project_search_retrieval_panel",
]
