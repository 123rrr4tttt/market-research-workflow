"""Read-only, rebuildable projection of one complete Research Ledger snapshot.

The first P0-D research projection is deliberately an immutable digest artifact,
not another database truth source.  One PostgreSQL statement reads only the
project-scoped ``research_objects`` and ``research_relations`` authorities.  The
caller owns the connection and transaction; this module has no write, commit,
offset, runtime-snapshot, or reverse-control path.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from app.successor_runtime.research.codec import is_sha256_hex, sha256_hex
from app.successor_runtime.runtime.ports import RuntimeScope
from app.successor_runtime.substrate.postgres.research_ledger import (
    assert_table_scope,
    project_table,
)
from app.successor_runtime.substrate.postgres.session import (
    validate_project_scope_ref,
)


class ResearchLedgerProjectionError(RuntimeError):
    """The canonical Ledger rows cannot form one exact projection closure."""


@dataclass(frozen=True, slots=True)
class ResearchLedgerObjectRecord:
    project_key: str
    object_id: str
    object_type: str
    revision: int
    incarnation: str
    lifecycle_state: str
    owner_binding_ref: str
    content_ref: str
    content_digest: str
    provenance_closure_digest: str
    valid_from: datetime | None
    valid_to: datetime | None
    record_digest: str

    def to_json(self) -> dict[str, object]:
        return {
            "project_key": self.project_key,
            "object_id": self.object_id,
            "object_type": self.object_type,
            "revision": self.revision,
            "incarnation": self.incarnation,
            "lifecycle_state": self.lifecycle_state,
            "owner_binding_ref": self.owner_binding_ref,
            "content_ref": self.content_ref,
            "content_digest": self.content_digest,
            "provenance_closure_digest": self.provenance_closure_digest,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "record_digest": self.record_digest,
        }


@dataclass(frozen=True, slots=True)
class ResearchLedgerRelationRecord:
    relation_id: str
    relation_type: str
    revision: int
    incarnation: str
    state: str
    source_object_ref: Mapping[str, object]
    target_object_ref: Mapping[str, object]
    direction: str
    scope_ref: str
    uncertainty_profile_ref: str
    validity: Mapping[str, object]
    provenance_closure_digest: str
    record_digest: str

    def to_json(self) -> dict[str, object]:
        return {
            "relation_id": self.relation_id,
            "relation_type": self.relation_type,
            "revision": self.revision,
            "incarnation": self.incarnation,
            "state": self.state,
            "source_object_ref": dict(self.source_object_ref),
            "target_object_ref": dict(self.target_object_ref),
            "direction": self.direction,
            "scope_ref": self.scope_ref,
            "uncertainty_profile_ref": self.uncertainty_profile_ref,
            "validity": dict(self.validity),
            "provenance_closure_digest": self.provenance_closure_digest,
            "record_digest": self.record_digest,
        }


@dataclass(frozen=True, slots=True)
class ResearchLedgerProjection:
    project_key: str
    resolved_schema: str
    project_registry_revision: int
    scope_incarnation: str
    scope_digest: str
    objects: tuple[ResearchLedgerObjectRecord, ...]
    relations: tuple[ResearchLedgerRelationRecord, ...]
    object_set_digest: str
    relation_set_digest: str
    source_closure_digest: str
    projection_digest: str
    schema: str = "mrw.research-ledger.full-snapshot-projection.v1"
    source_kind: str = "research_ledger"

    def to_json(self) -> dict[str, object]:
        """Return metadata and exact refs only; canonical value bytes stay external."""

        return {
            "schema": self.schema,
            "source_kind": self.source_kind,
            "source_tables": ["research_objects", "research_relations"],
            "scope": {
                "project_key": self.project_key,
                "resolved_schema": self.resolved_schema,
                "project_registry_revision": self.project_registry_revision,
                "incarnation": self.scope_incarnation,
                "scope_digest": self.scope_digest,
            },
            "objects": [record.to_json() for record in self.objects],
            "relations": [record.to_json() for record in self.relations],
            "object_count": len(self.objects),
            "relation_count": len(self.relations),
            "object_set_digest": self.object_set_digest,
            "relation_set_digest": self.relation_set_digest,
            "source_closure_digest": self.source_closure_digest,
            "projection_digest": self.projection_digest,
        }


class PostgresResearchLedgerProjector:
    """Build a disposable full-snapshot artifact from canonical Ledger tables."""

    projector_id = "successor-research-ledger-projector"
    projector_version = "1.0.0"
    source_kind = "research_ledger"

    def __init__(
        self,
        connection: Connection,
        tables: object,
        scope: RuntimeScope,
    ) -> None:
        self.connection = connection
        self.tables = tables
        self.scope = scope

    def rebuild(self) -> ResearchLedgerProjection:
        """Read both authorities in one statement and derive an immutable closure."""

        project_scope = validate_project_scope_ref(self.scope.project_scope)
        objects_table = project_table(self.tables, "research_objects")
        relations_table = project_table(self.tables, "research_relations")
        object_project_key = assert_table_scope(objects_table, self.scope)
        relation_project_key = assert_table_scope(relations_table, self.scope)
        if object_project_key != relation_project_key:
            raise ResearchLedgerProjectionError("Ledger authority scopes disagree")

        rows = tuple(
            self.connection.execute(
                _full_snapshot_statement(
                    objects_table,
                    relations_table,
                    project_scope.project_key,
                )
            ).mappings()
        )
        objects: list[ResearchLedgerObjectRecord] = []
        relations: list[ResearchLedgerRelationRecord] = []
        for row in rows:
            kind = row["record_kind"]
            if kind == "object":
                objects.append(_object_record(row, project_scope.project_key))
            elif kind == "relation":
                relations.append(_relation_record(row, project_scope.project_key))
            else:
                raise ResearchLedgerProjectionError(
                    f"unknown Ledger projection record kind: {kind!r}"
                )

        object_ref_keys = {_object_record_ref_key(record) for record in objects}
        for relation in relations:
            if _mapping_ref_key(relation.source_object_ref) not in object_ref_keys:
                raise ResearchLedgerProjectionError(
                    f"relation source ref is outside the full Ledger snapshot: "
                    f"{relation.relation_id}"
                )
            if _mapping_ref_key(relation.target_object_ref) not in object_ref_keys:
                raise ResearchLedgerProjectionError(
                    f"relation target ref is outside the full Ledger snapshot: "
                    f"{relation.relation_id}"
                )

        object_json = [record.to_json() for record in objects]
        relation_json = [record.to_json() for record in relations]
        object_set_digest = sha256_hex(object_json)
        relation_set_digest = sha256_hex(relation_json)
        source_payload = {
            "schema": "mrw.research-ledger.full-snapshot-source-closure.v1",
            "source_kind": self.source_kind,
            "source_tables": ["research_objects", "research_relations"],
            "scope": {
                "project_key": project_scope.project_key,
                "resolved_schema": project_scope.resolved_schema,
                "project_registry_revision": project_scope.project_registry_revision,
                "incarnation": project_scope.incarnation,
                "scope_digest": project_scope.scope_digest,
            },
            "objects": object_json,
            "relations": relation_json,
            "object_set_digest": object_set_digest,
            "relation_set_digest": relation_set_digest,
        }
        source_closure_digest = sha256_hex(source_payload)
        projection_digest = sha256_hex(
            {
                "schema": "mrw.research-ledger.projection-digest.v1",
                "projector_id": self.projector_id,
                "projector_version": self.projector_version,
                "source_closure_digest": source_closure_digest,
            }
        )
        return ResearchLedgerProjection(
            project_key=project_scope.project_key,
            resolved_schema=project_scope.resolved_schema,
            project_registry_revision=project_scope.project_registry_revision,
            scope_incarnation=project_scope.incarnation,
            scope_digest=project_scope.scope_digest,
            objects=tuple(objects),
            relations=tuple(relations),
            object_set_digest=object_set_digest,
            relation_set_digest=relation_set_digest,
            source_closure_digest=source_closure_digest,
            projection_digest=projection_digest,
        )


def _full_snapshot_statement(
    objects: sa.Table,
    relations: sa.Table,
    project_key: str,
) -> sa.Select:
    """Return one statement so both authority tables share one MVCC snapshot."""

    def null_as(column: sa.Column[Any]) -> Any:
        return sa.cast(sa.null(), column.type)

    object_rows = sa.select(
        sa.literal("object").label("record_kind"),
        objects.c.object_id.label("record_id"),
        objects.c.object_type.label("record_type"),
        objects.c.revision,
        objects.c.incarnation,
        objects.c.lifecycle_state.label("state"),
        null_as(relations.c.source_object_ref).label("source_object_ref"),
        null_as(relations.c.target_object_ref).label("target_object_ref"),
        null_as(relations.c.direction).label("direction"),
        null_as(relations.c.scope_ref).label("scope_ref"),
        null_as(relations.c.uncertainty_profile_ref).label("uncertainty_profile_ref"),
        null_as(relations.c.validity_json).label("validity_json"),
        objects.c.owner_binding_ref,
        objects.c.content_ref,
        objects.c.content_digest,
        objects.c.provenance_closure_digest,
        objects.c.valid_from,
        objects.c.valid_to,
    ).where(objects.c.project_key == project_key)
    relation_rows = sa.select(
        sa.literal("relation").label("record_kind"),
        relations.c.relation_id.label("record_id"),
        relations.c.relation_type.label("record_type"),
        relations.c.revision,
        relations.c.incarnation,
        relations.c.state,
        relations.c.source_object_ref,
        relations.c.target_object_ref,
        relations.c.direction,
        relations.c.scope_ref,
        relations.c.uncertainty_profile_ref,
        relations.c.validity_json,
        null_as(objects.c.owner_binding_ref).label("owner_binding_ref"),
        null_as(objects.c.content_ref).label("content_ref"),
        null_as(objects.c.content_digest).label("content_digest"),
        relations.c.provenance_closure_digest,
        null_as(objects.c.valid_from).label("valid_from"),
        null_as(objects.c.valid_to).label("valid_to"),
    ).where(relations.c.project_key == project_key)
    snapshot = sa.union_all(object_rows, relation_rows).subquery()
    return sa.select(snapshot).order_by(
        snapshot.c.record_kind,
        snapshot.c.record_id,
        snapshot.c.revision,
        snapshot.c.incarnation,
    )


def _required_text(row: Mapping[str, Any], name: str) -> str:
    value = row[name]
    if not isinstance(value, str) or not value:
        raise ResearchLedgerProjectionError(f"Ledger {name} is not exact text")
    return value


def _revision(row: Mapping[str, Any]) -> int:
    value = row["revision"]
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ResearchLedgerProjectionError("Ledger revision must be an integer >= 1")
    return value


def _digest(row: Mapping[str, Any], name: str) -> str:
    value = _required_text(row, name)
    if not is_sha256_hex(value):
        raise ResearchLedgerProjectionError(f"Ledger {name} is not canonical sha256")
    return value


def _object_record(
    row: Mapping[str, Any], project_key: str
) -> ResearchLedgerObjectRecord:
    payload = {
        "project_key": project_key,
        "object_id": _required_text(row, "record_id"),
        "object_type": _required_text(row, "record_type"),
        "revision": _revision(row),
        "incarnation": _required_text(row, "incarnation"),
        "lifecycle_state": _required_text(row, "state"),
        "owner_binding_ref": _required_text(row, "owner_binding_ref"),
        "content_ref": _required_text(row, "content_ref"),
        "content_digest": _digest(row, "content_digest"),
        "provenance_closure_digest": _digest(row, "provenance_closure_digest"),
        "valid_from": row["valid_from"],
        "valid_to": row["valid_to"],
    }
    if payload["valid_from"] is not None and not isinstance(
        payload["valid_from"], datetime
    ):
        raise ResearchLedgerProjectionError("Ledger valid_from is not a datetime")
    if payload["valid_to"] is not None and not isinstance(
        payload["valid_to"], datetime
    ):
        raise ResearchLedgerProjectionError("Ledger valid_to is not a datetime")
    return ResearchLedgerObjectRecord(
        **payload,
        record_digest=sha256_hex(
            {"schema": "mrw.research-ledger.object-record.v1", **payload}
        ),
    )


_OBJECT_REF_FIELDS = frozenset(
    {
        "object_id",
        "object_type",
        "project_key",
        "revision",
        "incarnation",
        "owner_binding_ref",
        "content_ref",
        "content_digest",
    }
)


def _exact_object_ref(value: object, project_key: str) -> Mapping[str, object]:
    if not isinstance(value, str):
        raise ResearchLedgerProjectionError("relation object ref is not encoded text")
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError) as exc:
        raise ResearchLedgerProjectionError(
            "relation object ref is invalid JSON"
        ) from exc
    if not isinstance(decoded, dict) or frozenset(decoded) != _OBJECT_REF_FIELDS:
        raise ResearchLedgerProjectionError(
            "relation object ref has an inexact identity"
        )
    for name in (
        "object_id",
        "object_type",
        "project_key",
        "incarnation",
        "owner_binding_ref",
        "content_ref",
    ):
        if not isinstance(decoded[name], str) or not decoded[name]:
            raise ResearchLedgerProjectionError(
                f"relation object ref {name} is invalid"
            )
    if decoded["project_key"] != project_key:
        raise ResearchLedgerProjectionError("relation object ref crosses project scope")
    revision = decoded["revision"]
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise ResearchLedgerProjectionError("relation object ref revision is invalid")
    content_digest = decoded["content_digest"]
    if not isinstance(content_digest, str) or not is_sha256_hex(content_digest):
        raise ResearchLedgerProjectionError(
            "relation object ref content_digest is invalid"
        )
    return MappingProxyType(decoded)


def _relation_record(
    row: Mapping[str, Any], project_key: str
) -> ResearchLedgerRelationRecord:
    validity = row["validity_json"]
    if not isinstance(validity, Mapping):
        raise ResearchLedgerProjectionError("relation validity_json is not an object")
    payload = {
        "relation_id": _required_text(row, "record_id"),
        "relation_type": _required_text(row, "record_type"),
        "revision": _revision(row),
        "incarnation": _required_text(row, "incarnation"),
        "state": _required_text(row, "state"),
        "source_object_ref": _exact_object_ref(row["source_object_ref"], project_key),
        "target_object_ref": _exact_object_ref(row["target_object_ref"], project_key),
        "direction": _required_text(row, "direction"),
        "scope_ref": _required_text(row, "scope_ref"),
        "uncertainty_profile_ref": _required_text(row, "uncertainty_profile_ref"),
        "validity": MappingProxyType(dict(validity)),
        "provenance_closure_digest": _digest(row, "provenance_closure_digest"),
    }
    return ResearchLedgerRelationRecord(
        **payload,
        record_digest=sha256_hex(
            {"schema": "mrw.research-ledger.relation-record.v1", **payload}
        ),
    )


def _object_record_ref_key(record: ResearchLedgerObjectRecord) -> tuple[object, ...]:
    return (
        record.object_id,
        record.object_type,
        record.project_key,
        record.revision,
        record.incarnation,
        record.owner_binding_ref,
        record.content_ref,
        record.content_digest,
    )


def _mapping_ref_key(ref: Mapping[str, object]) -> tuple[object, ...]:
    return (
        ref["object_id"],
        ref["object_type"],
        ref["project_key"],
        ref["revision"],
        ref["incarnation"],
        ref["owner_binding_ref"],
        ref["content_ref"],
        ref["content_digest"],
    )


__all__ = [
    "PostgresResearchLedgerProjector",
    "ResearchLedgerObjectRecord",
    "ResearchLedgerProjection",
    "ResearchLedgerProjectionError",
    "ResearchLedgerRelationRecord",
]
