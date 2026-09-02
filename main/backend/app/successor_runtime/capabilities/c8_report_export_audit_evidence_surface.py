"""C8 report export-audit evidence consumption surface (ALL-SM-014).

The module consumes typed export-audit observations and renders dashboard
readback rows.  It never writes audit records, runs export delivery or claims
that degraded/local observations are durable proof.
"""

from __future__ import annotations

import re
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
SURFACE_SCHEMA = "mrw.successor.c8.report-export-audit.evidence-surface.v1"
MOVEMENT_IDS: tuple[str, ...] = ("ALL-SM-014",)
DECISION_OWNER = "MRW dashboard/report owner (B-recheck); S2c decision owner"

AuditOrigin = Literal[
    "durable_record",
    "degraded_memory",
    "local_deterministic_observation",
]
_DIGEST_RE = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
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


def _digest_text(value: Any, name: str) -> str:
    text = _text(value, name)
    if not _DIGEST_RE.match(text):
        raise ValueError(f"{name} must be 64 hex chars with optional sha256: prefix")
    return text


@dataclass(frozen=True, slots=True)
class ExportAuditObservation:
    """One typed export-audit observation supplied by the caller."""

    trace_id: str
    report_id: str
    export_outcome: str
    origin: AuditOrigin
    integrity_digest: str
    actor_digest: str
    observed_at: str
    source_ref: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "trace_id", _text(self.trace_id, "trace_id"))
        object.__setattr__(self, "report_id", _text(self.report_id, "report_id"))
        object.__setattr__(
            self,
            "export_outcome",
            _text(self.export_outcome, "export_outcome"),
        )
        if self.origin not in (
            "durable_record",
            "degraded_memory",
            "local_deterministic_observation",
        ):
            raise ValueError(f"unknown origin: {self.origin}")
        object.__setattr__(
            self,
            "integrity_digest",
            _digest_text(self.integrity_digest, "integrity_digest"),
        )
        object.__setattr__(
            self, "actor_digest", _digest_text(self.actor_digest, "actor_digest")
        )
        object.__setattr__(self, "observed_at", _text(self.observed_at, "observed_at"))
        object.__setattr__(
            self,
            "source_ref",
            _text(self.source_ref, "source_ref", required=False),
        )

    def to_plain(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "report_id": self.report_id,
            "export_outcome": self.export_outcome,
            "origin": self.origin,
            "integrity_digest": self.integrity_digest,
            "actor_digest": self.actor_digest,
            "observed_at": self.observed_at,
            "source_ref": self.source_ref,
        }


@dataclass(frozen=True, slots=True)
class ExportAuditEvidenceReadback:
    """Immutable evidence-consumption readback for ALL-SM-014."""

    schema: str
    movement_ids: tuple[str, ...]
    authority: dict[str, bool]
    observations: tuple[ExportAuditObservation, ...]
    durable_count: int
    degraded_count: int
    local_count: int
    digest_available: bool
    no_call_durable_write: bool = True
    degraded_is_not_durable_proof: bool = True
    no_call_reason: str = (
        "evidence consumption only; durable audit persistence/export is no-call"
    )

    def __post_init__(self) -> None:
        if self.schema != SURFACE_SCHEMA:
            raise ValueError("ExportAuditEvidenceReadback.schema is not frozen")
        if self.movement_ids != MOVEMENT_IDS:
            raise ValueError("ExportAuditEvidenceReadback.movement_ids drift")
        if any(value is not False for value in self.authority.values()):
            raise ValueError("audit evidence surface authority must be all false")
        object.__setattr__(self, "observations", tuple(self.observations))
        if self.no_call_durable_write is not True:
            raise ValueError("audit surface never grants durable write authority")
        if self.degraded_is_not_durable_proof is not True:
            raise ValueError("degraded/local evidence is never durable proof")

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "movement_ids": list(self.movement_ids),
            "authority": dict(self.authority),
            "observations": [row.to_plain() for row in self.observations],
            "durable_count": self.durable_count,
            "degraded_count": self.degraded_count,
            "local_count": self.local_count,
            "digest_available": self.digest_available,
            "no_call_durable_write": self.no_call_durable_write,
            "degraded_is_not_durable_proof": self.degraded_is_not_durable_proof,
            "no_call_reason": self.no_call_reason,
        }


def consume_export_audit_evidence(
    observations: Iterable[ExportAuditObservation],
) -> ExportAuditEvidenceReadback:
    """Classify typed export-audit observations without any runtime effect."""

    rows = tuple(
        row
        if isinstance(row, ExportAuditObservation)
        else ExportAuditObservation(**row)
        for row in observations
    )
    durable = sum(1 for row in rows if row.origin == "durable_record")
    degraded = sum(1 for row in rows if row.origin == "degraded_memory")
    local = sum(1 for row in rows if row.origin == "local_deterministic_observation")
    return ExportAuditEvidenceReadback(
        schema=SURFACE_SCHEMA,
        movement_ids=MOVEMENT_IDS,
        authority=authority_ceiling(),
        observations=rows,
        durable_count=durable,
        degraded_count=degraded,
        local_count=local,
        digest_available=durable > 0,
    )


def project_export_audit_dashboard_rows(
    readback: ExportAuditEvidenceReadback,
) -> tuple[dict[str, Any], ...]:
    """Render read-only dashboard rows from an evidence readback."""

    if not isinstance(readback, ExportAuditEvidenceReadback):
        raise TypeError("export audit dashboard rows require typed readback")
    return tuple(
        {
            "trace_id": row.trace_id,
            "report_id": row.report_id,
            "export_outcome": row.export_outcome,
            "origin": row.origin,
            "digest_available": row.origin == "durable_record",
            "degraded_warning": row.origin != "durable_record",
        }
        for row in readback.observations
    )


__all__ = [
    "AUTHORITY_KEYS",
    "DECISION_OWNER",
    "MOVEMENT_IDS",
    "SURFACE_SCHEMA",
    "AuditOrigin",
    "ExportAuditEvidenceReadback",
    "ExportAuditObservation",
    "authority_ceiling",
    "consume_export_audit_evidence",
    "project_export_audit_dashboard_rows",
]
