"""C8.1 exact C7 material and staged knowledge value PostgreSQL effect slice.

The slice reads the admitted C7 disposable head and the exact project
``successor_values`` row in one transaction, issues a deterministic
``CanonicalMaterialRead``, forms a typed knowledge candidate under a named
formation profile, and stages the exact candidate value through
:class:`ValueRepository`.  It owns no production authority, registry or
witness; the family production composition root issues those.  All reads are
exact and read-only; forged, missing, stale, ABA and cross-project reads fail
closed.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import MetaData, select
from sqlalchemy.engine import Connection

from app.successor_runtime.capabilities import c8_common as c8
from app.successor_runtime.capabilities.checksum import (
    canonical_json,
    content_digest,
    sha256_hex,
)
from app.successor_runtime.runtime.assignments import canonical_digest
from app.successor_runtime.runtime.ports import RuntimeScope
from app.successor_runtime.substrate.postgres.ingest_c7_candidate_values import (
    C7_STRUCTURED_VALUE_CODEC_ID,
    C7_STRUCTURED_VALUE_OBJECT_TYPE,
    C7_STRUCTURED_VALUE_STATE,
    C7ValueMissingError,
    load_candidate_value_row,
)
from app.successor_runtime.substrate.postgres.ingest_c7_movement_admission import (
    C7_MOVEMENT_CANONICAL_DOCUMENTS,
)
from app.successor_runtime.substrate.postgres.models import project_tables
from app.successor_runtime.substrate.postgres.research_ledger import (
    ExactContentConflict,
    ProjectCASConflict,
    ProjectRecordNotFound,
)
from app.successor_runtime.substrate.postgres.values import ValueRepository

__all__ = [
    "C8_KNOWLEDGE_VALUE_CODEC_ID",
    "C8_KNOWLEDGE_VALUE_OBJECT_TYPE",
    "C8_KNOWLEDGE_VALUE_SCHEMA",
    "C8_KNOWLEDGE_VALUE_STATE",
    "C8_VALUE_REF_PREFIX",
    "C8MaterialHandlerError",
    "C8MaterialIntegrityError",
    "C8MaterialMissingError",
    "C8MaterialProjectMismatchError",
    "C8StoredKnowledgeValue",
    "form_knowledge_candidate",
    "knowledge_value_id",
    "read_canonical_material",
    "read_staged_knowledge_value",
    "stage_knowledge_value",
]

C8_KNOWLEDGE_VALUE_SCHEMA = "mrw.successor.c8.knowledge-value.v1"
C8_KNOWLEDGE_VALUE_OBJECT_TYPE = "C8TypedKnowledgeCandidate.v1"
C8_KNOWLEDGE_VALUE_CODEC_ID = (
    "mrw.successor.c8.typed-knowledge-candidate.canonical-json.v1"
)
C8_KNOWLEDGE_VALUE_STATE = "AVAILABLE"
C8_VALUE_REF_PREFIX = "project-value:"


class C8MaterialHandlerError(RuntimeError):
    """Base fail-closed C8 canonical material effect error."""


class C8MaterialMissingError(C8MaterialHandlerError):
    """Required C7 head or project value is absent."""


class C8MaterialIntegrityError(C8MaterialHandlerError):
    """Head/value closure, digest, provenance or identity drift."""


class C8MaterialProjectMismatchError(C8MaterialHandlerError):
    """Material read crosses the validated project scope."""


@dataclass(frozen=True, slots=True)
class C8StoredKnowledgeValue:
    value_id: str
    value_ref: str
    revision: int
    incarnation: str
    content_digest: str
    provenance_digest: str
    source_ref: str


def _head_closure_digest(head: Mapping[str, object]) -> str:
    fields = {key: value for key, value in head.items() if key != "head_closure_digest"}
    return canonical_digest(fields)


def _material_identity(head: Mapping[str, object]) -> str:
    return f"material:c7:{head['object_id']}"


def _require_head(head: Mapping[str, object], scope: RuntimeScope) -> None:
    if str(head["project_key"]) != scope.project_scope.project_key:
        raise C8MaterialProjectMismatchError(
            "canonical C7 head belongs to a different project scope"
        )
    if str(head["head_closure_digest"]) != _head_closure_digest(head):
        raise C8MaterialIntegrityError("C7 head closure digest drift")


def _read_head(
    connection: Connection,
    *,
    scope: RuntimeScope,
    candidate_id: str | None,
    object_id: str | None,
) -> dict[str, object]:
    if (candidate_id is None) == (object_id is None):
        raise ValueError("exactly one of candidate_id or object_id is required")
    statement = select(C7_MOVEMENT_CANONICAL_DOCUMENTS).where(
        C7_MOVEMENT_CANONICAL_DOCUMENTS.c.project_key == scope.project_scope.project_key
    )
    if object_id is not None:
        statement = statement.where(
            C7_MOVEMENT_CANONICAL_DOCUMENTS.c.object_id == object_id
        )
    else:
        statement = statement.where(
            C7_MOVEMENT_CANONICAL_DOCUMENTS.c.candidate_id == candidate_id
        )
    row = connection.execute(statement).mappings().one_or_none()
    if row is None:
        key = object_id if object_id is not None else candidate_id
        raise C8MaterialMissingError(f"admitted C7 head not found: {key}")
    return dict(row)


def _value_row_from_head(
    connection: Connection,
    *,
    scope: RuntimeScope,
    head: Mapping[str, object],
) -> Mapping[str, object]:
    value_ref = str(head["value_ref"])
    if not value_ref.startswith(C8_VALUE_REF_PREFIX):
        raise C8MaterialIntegrityError("C7 head value ref is not a project-value ref")
    value_id = value_ref[len(C8_VALUE_REF_PREFIX) :]
    try:
        row = load_candidate_value_row(connection, scope=scope, value_id=value_id)
    except C7ValueMissingError as exc:
        raise C8MaterialMissingError(f"candidate value not found: {value_id}") from exc
    checks = (
        ("value_id", row["value_id"], value_id),
        ("object_type", row["object_type"], C7_STRUCTURED_VALUE_OBJECT_TYPE),
        ("codec_id", row["codec_id"], C7_STRUCTURED_VALUE_CODEC_ID),
        ("revision", int(row["revision"]), int(head["value_revision"])),
        ("incarnation", row["incarnation"], head["value_incarnation"]),
        ("content_digest", row["content_digest"], head["value_digest"]),
        (
            "provenance_digest",
            row["provenance_digest"],
            head["value_provenance_digest"],
        ),
        ("source_ref", row["source_ref"], head["snapshot_ref"]),
        ("state", row["state"], C7_STRUCTURED_VALUE_STATE),
    )
    for field, stored, expected in checks:
        if stored != expected:
            raise C8MaterialIntegrityError(f"C7 head/value {field} drift")
    content = row["content_json"]
    if not isinstance(content, dict):
        raise C8MaterialIntegrityError("C7 structured payload is not content_json")
    try:
        recomputed = c8.c8_canonical_digest(dict(content))
    except (TypeError, ValueError) as exc:
        raise C8MaterialIntegrityError(
            "stored C7 payload is not deep-freeze canonical"
        ) from exc
    if recomputed != str(row["content_digest"]):
        raise C8MaterialIntegrityError("stored C7 value bytes fail digest readback")
    if str(row["content_digest"]) != str(head["value_digest"]):
        raise C8MaterialIntegrityError("C7 head value digest drift")
    provenance = row["provenance_json"]
    if not isinstance(provenance, dict):
        raise C8MaterialIntegrityError("C7 value provenance is not an object")
    if dict(provenance) != {
        "provenance_closure_digest": str(head["value_provenance_digest"])
    }:
        raise C8MaterialIntegrityError("stored C7 value provenance record drift")
    return row


def read_canonical_material(
    connection: Connection,
    *,
    scope: RuntimeScope,
    candidate_id: str | None = None,
    object_id: str | None = None,
) -> c8.CanonicalMaterialRead:
    """Exact-read one admitted C7 material; no writes and no authority."""

    head = _read_head(
        connection,
        scope=scope,
        candidate_id=candidate_id,
        object_id=object_id,
    )
    _require_head(head, scope)
    value_row = _value_row_from_head(connection, scope=scope, head=head)
    material = c8.CanonicalMaterialRead(
        material_identity=_material_identity(head),
        project_key=str(head["project_key"]),
        candidate_id=str(head["candidate_id"]),
        document_identity=str(head["object_id"]),
        head_revision=int(head["revision"]),
        head_incarnation=str(head["incarnation"]),
        head_closure_digest=str(head["head_closure_digest"]),
        value_revision=int(head["value_revision"]),
        value_incarnation=str(head["value_incarnation"]),
        value_digest=str(head["value_digest"]),
        snapshot_ref=str(head["snapshot_ref"]),
        provenance_digest=str(head["value_provenance_digest"]),
        structured_payload=dict(value_row["content_json"]),
    )
    try:
        c8.validate_canonical_material(
            material,
            project_key=scope.project_scope.project_key,
        )
    except c8.C8ProjectionError as exc:
        raise C8MaterialIntegrityError(str(exc)) from exc
    return material


def form_knowledge_candidate(
    material: c8.CanonicalMaterialRead,
    *,
    formation_profile: c8.FormationProfile,
    candidate_id: str,
    canonical_statement: str,
    primary_type_node_key: str,
    evidence_refs: tuple[str, ...],
) -> c8.TypedKnowledgeCandidate:
    """Deterministic formation of a staged knowledge candidate."""

    return c8.form_typed_knowledge_candidate(
        material,
        formation_profile=formation_profile,
        candidate_id=candidate_id,
        canonical_statement=canonical_statement,
        primary_type_node_key=primary_type_node_key,
        evidence_refs=evidence_refs,
    )


def knowledge_value_id(candidate_id: str) -> str:
    return f"c8:knowledge:{candidate_id}"


def _knowledge_body(candidate: c8.TypedKnowledgeCandidate) -> dict[str, object]:
    return {
        name: value
        for name, value in dataclasses.asdict(candidate).items()
        if name != "candidate_digest"
    }


def _knowledge_bytes(candidate: c8.TypedKnowledgeCandidate) -> bytes:
    return canonical_json(_knowledge_body(candidate)).encode("utf-8")


def _knowledge_provenance(
    material: c8.CanonicalMaterialRead,
    candidate: c8.TypedKnowledgeCandidate,
) -> dict[str, object]:
    return {
        "schema": C8_KNOWLEDGE_VALUE_SCHEMA,
        "material_identity": material.material_identity,
        "candidate_id": candidate.candidate_id,
        "snapshot_ref": material.snapshot_ref,
        "material_value_digest": material.value_digest,
        "material_provenance_digest": material.provenance_digest,
    }


def stage_knowledge_value(
    connection: Connection,
    *,
    scope: RuntimeScope,
    material: c8.CanonicalMaterialRead,
    candidate: c8.TypedKnowledgeCandidate,
) -> C8StoredKnowledgeValue:
    """Write the exact staged knowledge candidate value (write path only)."""

    try:
        c8.validate_typed_knowledge_candidate(
            candidate,
            material=material,
            project_key=scope.project_scope.project_key,
        )
    except c8.C8ProjectionError as exc:
        raise C8MaterialIntegrityError(str(exc)) from exc
    value_id = knowledge_value_id(candidate.candidate_id)
    exact = _knowledge_bytes(candidate)
    if sha256_hex(exact) != candidate.candidate_digest:
        raise C8MaterialIntegrityError(
            "knowledge candidate bytes do not match candidate digest"
        )
    incarnation = f"c8:knowledge:{candidate.candidate_digest}"
    provenance = _knowledge_provenance(material, candidate)
    provenance_digest = content_digest(provenance)
    try:
        stored = ValueRepository(
            connection,
            project_tables(MetaData(), scope.project_scope.resolved_schema),
        ).put_exact(
            scope,
            value_id=value_id,
            object_type=C8_KNOWLEDGE_VALUE_OBJECT_TYPE,
            codec_id=C8_KNOWLEDGE_VALUE_CODEC_ID,
            content=exact,
            expected_digest=candidate.candidate_digest,
            provenance_digest=provenance_digest,
            expected_revision=0,
            expected_incarnation=incarnation,
            source_ref=material.snapshot_ref,
            provenance=provenance,
            state=C8_KNOWLEDGE_VALUE_STATE,
        )
    except (
        ExactContentConflict,
        ProjectCASConflict,
        ProjectRecordNotFound,
    ) as exc:
        raise C8MaterialIntegrityError(str(exc)) from exc
    if stored.revision != 1:
        raise C8MaterialIntegrityError(
            "staged knowledge value must be creation revision 1"
        )
    return C8StoredKnowledgeValue(
        value_id=value_id,
        value_ref=C8_VALUE_REF_PREFIX + value_id,
        revision=stored.revision,
        incarnation=stored.incarnation,
        content_digest=stored.content_digest,
        provenance_digest=provenance_digest,
        source_ref=material.snapshot_ref,
    )


def read_staged_knowledge_value(
    connection: Connection,
    *,
    scope: RuntimeScope,
    material: c8.CanonicalMaterialRead,
    candidate: c8.TypedKnowledgeCandidate,
    expected_value: C8StoredKnowledgeValue | None = None,
) -> bytes:
    """Exact-read the staged knowledge value before handle issuance."""

    value_id = knowledge_value_id(candidate.candidate_id)
    if expected_value is not None and expected_value.value_id != value_id:
        raise C8MaterialIntegrityError("staged knowledge value identity drift")
    try:
        exact = ValueRepository(
            connection,
            project_tables(MetaData(), scope.project_scope.resolved_schema),
        ).get_exact(
            scope,
            value_id,
            expected_revision=1,
            expected_incarnation=f"c8:knowledge:{candidate.candidate_digest}",
            expected_digest=candidate.candidate_digest,
        )
    except (ProjectRecordNotFound, ExactContentConflict, ProjectCASConflict) as exc:
        raise C8MaterialIntegrityError(
            "staged knowledge value is absent or drifted"
        ) from exc
    if exact != _knowledge_bytes(candidate):
        raise C8MaterialIntegrityError("staged knowledge value bytes drift")
    if expected_value is not None and expected_value.content_digest != sha256_hex(
        exact
    ):
        raise C8MaterialIntegrityError(
            "staged knowledge value digest drifted since issuance"
        )
    return exact
