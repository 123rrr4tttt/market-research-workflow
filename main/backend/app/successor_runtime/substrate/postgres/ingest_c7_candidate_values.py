"""C7 structured candidate exact-value handoff into project values.

The family-local slice stores the canonical structured payload JSON of a
verified C7 candidate in the existing project ``successor_values`` table
through :class:`ValueRepository`.  The value identity is deterministic
``c7:structured:<candidate_id>``, the codec/object type are frozen, the stored
content digest must equal ``VerifiedMaterialCandidate.payload_content_digest``,
and the provenance is exact.  Values are creation-only revision 1 with a
non-reusable incarnation bound to the candidate digest.  This module performs
no network, provider, canonical document, promotion or live-authority work.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import MetaData, select
from sqlalchemy.engine import Connection

from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.ingest_c7_movements import (
    StructuredMaterialCandidate,
    VerifiedMaterialCandidate,
)
from app.successor_runtime.research.codec import canonical_bytes
from app.successor_runtime.runtime.ports import RuntimeScope
from app.successor_runtime.substrate.postgres.models import project_tables
from app.successor_runtime.substrate.postgres.research_ledger import (
    ExactContentConflict,
    ProjectCASConflict,
    ProjectRecordNotFound,
)
from app.successor_runtime.substrate.postgres.values import ValueRepository

__all__ = [
    "C7_STRUCTURED_VALUE_CODEC_ID",
    "C7_STRUCTURED_VALUE_OBJECT_TYPE",
    "C7_STRUCTURED_VALUE_SOURCE_KIND",
    "C7_STRUCTURED_VALUE_STATE",
    "C7StructuredValueRef",
    "C7ValueHandoffError",
    "C7ValueIntegrityError",
    "C7ValueMissingError",
    "candidate_value_id",
    "candidate_value_incarnation",
    "candidate_value_provenance",
    "candidate_value_ref",
    "load_candidate_value_row",
    "readback_candidate_value",
    "require_exact_candidate_pair",
    "store_candidate_value",
]

C7_STRUCTURED_VALUE_CODEC_ID = "mrw.successor.c7.structured-payload.canonical-json.v1"
C7_STRUCTURED_VALUE_OBJECT_TYPE = "StructuredMaterialCandidatePayload.v1"
C7_STRUCTURED_VALUE_SOURCE_KIND = "c7:structured-material-candidate"
C7_STRUCTURED_VALUE_STATE = "AVAILABLE"
_C7_VALUE_REF_PREFIX = "project-value:"


class C7ValueHandoffError(RuntimeError):
    """Base fail-closed C7 candidate value handoff error."""


class C7ValueIntegrityError(C7ValueHandoffError):
    """Stored value bytes/digest/provenance/identity drift."""


class C7ValueMissingError(C7ValueHandoffError):
    """Required candidate value row is absent."""


@dataclass(frozen=True, slots=True)
class C7StructuredValueRef:
    value_id: str
    value_ref: str
    revision: int
    incarnation: str
    content_digest: str
    provenance_digest: str
    source_ref: str


def candidate_value_id(candidate_id: str) -> str:
    return f"c7:structured:{candidate_id}"


def candidate_value_ref(value_id: str) -> str:
    return _C7_VALUE_REF_PREFIX + value_id


def candidate_value_incarnation(verified: VerifiedMaterialCandidate) -> str:
    return f"c7:structured:{verified.candidate_digest}"


def candidate_value_provenance(verified: VerifiedMaterialCandidate) -> dict[str, str]:
    return {
        "provenance_closure_digest": verified.provenance_closure_digest,
    }


def require_exact_candidate_pair(
    structured: StructuredMaterialCandidate,
    verified: VerifiedMaterialCandidate,
) -> None:
    """Fail closed unless the structured candidate and verified match exactly."""

    if not isinstance(structured, StructuredMaterialCandidate):
        raise C7ValueIntegrityError("structured candidate is not the concrete class")
    if not isinstance(verified, VerifiedMaterialCandidate):
        raise C7ValueIntegrityError("verified candidate is not the concrete class")
    checks = (
        ("candidate_id", structured.candidate_id, verified.candidate_id),
        ("candidate_digest", structured.candidate_digest, verified.candidate_digest),
        ("project_key", structured.project_key, verified.project_key),
        ("snapshot_ref", structured.snapshot_ref, verified.snapshot_ref),
        (
            "snapshot_identity_digest",
            structured.snapshot_identity_digest,
            verified.snapshot_identity_digest,
        ),
        (
            "raw_content_digest",
            structured.raw_content_digest,
            verified.raw_content_digest,
        ),
        ("envelope_digest", structured.envelope_digest, verified.envelope_digest),
        ("decision_digest", structured.decision_digest, verified.decision_digest),
        ("alternative", structured.alternative, verified.alternative),
        (
            "payload_content_digest",
            structured.payload_content_digest,
            verified.payload_content_digest,
        ),
        (
            "ordered_source_closure_digest",
            structured.ordered_source_closure_digest,
            verified.ordered_source_closure_digest,
        ),
        (
            "provenance_closure_digest",
            structured.provenance_closure_digest,
            verified.provenance_closure_digest,
        ),
    )
    for field, structured_value, verified_value in checks:
        if structured_value != verified_value:
            raise C7ValueIntegrityError(f"structured/verified candidate {field} drift")
    if content_digest(structured.structured_payload) != verified.payload_content_digest:
        raise C7ValueIntegrityError(
            "structured payload bytes do not match verified payload digest"
        )


def _project_value_table(scope: RuntimeScope):
    return project_tables(
        MetaData(), scope.project_scope.resolved_schema
    ).successor_values


def store_candidate_value(
    connection: Connection,
    *,
    scope: RuntimeScope,
    structured: StructuredMaterialCandidate,
    verified: VerifiedMaterialCandidate,
) -> C7StructuredValueRef:
    require_exact_candidate_pair(structured, verified)
    value_id = candidate_value_id(verified.candidate_id)
    incarnation = candidate_value_incarnation(verified)
    provenance = candidate_value_provenance(verified)
    provenance_digest = verified.provenance_closure_digest
    try:
        stored = ValueRepository(
            connection,
            project_tables(MetaData(), scope.project_scope.resolved_schema),
        ).put_exact(
            scope,
            value_id=value_id,
            object_type=C7_STRUCTURED_VALUE_OBJECT_TYPE,
            codec_id=C7_STRUCTURED_VALUE_CODEC_ID,
            content=dict(structured.structured_payload),
            expected_digest=verified.payload_content_digest,
            provenance_digest=provenance_digest,
            expected_revision=0,
            expected_incarnation=incarnation,
            source_ref=verified.snapshot_ref,
            provenance=provenance,
            state=C7_STRUCTURED_VALUE_STATE,
        )
    except (ExactContentConflict, ProjectCASConflict, ProjectRecordNotFound) as exc:
        raise C7ValueIntegrityError(str(exc)) from exc
    if stored.revision != 1:
        raise C7ValueIntegrityError("C7 structured value must be creation revision 1")
    return C7StructuredValueRef(
        value_id=value_id,
        value_ref=candidate_value_ref(value_id),
        revision=stored.revision,
        incarnation=stored.incarnation,
        content_digest=stored.content_digest,
        provenance_digest=provenance_digest,
        source_ref=verified.snapshot_ref,
    )


def load_candidate_value_row(
    connection: Connection,
    *,
    scope: RuntimeScope,
    value_id: str,
) -> Mapping[str, object]:
    table = _project_value_table(scope)
    row = (
        connection.execute(
            select(table).where(
                table.c.project_key == scope.project_scope.project_key,
                table.c.value_id == value_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise C7ValueMissingError(f"candidate value not found: {value_id}")
    return row


def readback_candidate_value(
    connection: Connection,
    *,
    scope: RuntimeScope,
    head: Mapping[str, object],
    candidate: VerifiedMaterialCandidate,
) -> Mapping[str, object]:
    """Cross-check the disposable head value closure against stored bytes."""

    value_ref = str(head["value_ref"])
    if not value_ref.startswith(_C7_VALUE_REF_PREFIX):
        raise C7ValueIntegrityError("head value ref is not a project-value ref")
    value_id = value_ref[len(_C7_VALUE_REF_PREFIX) :]
    row = load_candidate_value_row(connection, scope=scope, value_id=value_id)
    if (
        str(row["object_type"]) != C7_STRUCTURED_VALUE_OBJECT_TYPE
        or str(row["codec_id"]) != C7_STRUCTURED_VALUE_CODEC_ID
    ):
        raise C7ValueIntegrityError("candidate value codec/object type drift")
    checks = (
        ("value_id", row["value_id"], value_id),
        ("revision", int(row["revision"]), int(head["value_revision"])),
        ("incarnation", row["incarnation"], head["value_incarnation"]),
        ("content_digest", row["content_digest"], head["value_digest"]),
        (
            "provenance_digest",
            row["provenance_digest"],
            head["value_provenance_digest"],
        ),
        ("source_ref", row["source_ref"], head["snapshot_ref"]),
    )
    for field, stored, expected in checks:
        if stored != expected:
            raise C7ValueIntegrityError(f"head/value {field} drift")
    content = row["content_json"]
    if not isinstance(content, dict):
        raise C7ValueIntegrityError("candidate value is not stored as content_json")
    exact = canonical_bytes(dict(content))
    if hashlib.sha256(exact).hexdigest() != str(row["content_digest"]):
        raise C7ValueIntegrityError("stored value bytes fail digest readback")
    if str(row["content_digest"]) != str(head["value_digest"]):
        raise C7ValueIntegrityError("head value digest drift")
    provenance = row["provenance_json"]
    if not isinstance(provenance, dict):
        raise C7ValueIntegrityError("candidate value provenance is not an object")
    if str(head["value_provenance_digest"]) != candidate.provenance_closure_digest:
        raise C7ValueIntegrityError("head value provenance digest drift")
    if str(row["provenance_digest"]) != candidate.provenance_closure_digest:
        raise C7ValueIntegrityError("stored value provenance digest drift")
    if dict(provenance) != {
        "provenance_closure_digest": candidate.provenance_closure_digest
    }:
        raise C7ValueIntegrityError("stored value provenance record drift")
    if (
        row["state"] != C7_STRUCTURED_VALUE_STATE
        or row["source_ref"] != head["snapshot_ref"]
    ):
        raise C7ValueIntegrityError("candidate value state/source drift")
    return row
