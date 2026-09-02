"""Project-scoped Research Ledger repositories.

The caller owns the :class:`sqlalchemy.engine.Connection` and its transaction.
This module never creates a session and never commits or rolls back.  Every
query is qualified by a server-created ``RuntimeScope``/``ProjectScopeRef`` and
the project tables' resolved schema is checked before SQL is emitted.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Table, insert, select
from sqlalchemy.engine import Connection

from app.successor_runtime.research.evidence import EvidenceQualification
from app.successor_runtime.research.identities import ResearchObjectRef
from app.successor_runtime.research.object_types import ObjectType
from app.successor_runtime.research.relations import ResearchRelation
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope


class ProjectRepositoryError(RuntimeError):
    """Base fail-closed project-plane repository error."""


class ProjectRecordNotFound(ProjectRepositoryError):
    pass


class ProjectScopeMismatch(ProjectRepositoryError):
    pass


class ProjectCASConflict(ProjectRepositoryError):
    pass


class ExactContentConflict(ProjectRepositoryError):
    pass


class OwnerBindingViolation(ProjectRepositoryError):
    pass


_FIRST_SLICE_LEDGER_OWNER_MATRIX: Mapping[str, tuple[str, str]] = {
    "ResearchIntent.v1": ("CANONICAL_OWNED", "ResearchLedger"),
    "Inquiry.v1": ("CANONICAL_OWNED", "ResearchLedger"),
    "ResearchPlan.v1": ("CANONICAL_OWNED", "ResearchLedger"),
    "SourceRef.v1": (
        "IMMUTABLE_EXTERNAL_REF",
        "legacy_source_or_document_locator",
    ),
    "MaterialRef.v1": ("IMMUTABLE_EXTERNAL_REF", "CapturedMaterialSnapshot"),
    "Claim.v1": ("CANONICAL_OWNED", "ResearchLedger"),
    "Gap.v1": ("CANONICAL_OWNED", "ResearchLedger"),
    "ResearchArtifact.v1": (
        "CANONICAL_OWNED",
        "ResearchLedger_plus_project_artifact_store",
    ),
    "DeliveryIntent.v1": ("CANONICAL_OWNED", "ResearchLedger"),
    "DeliveryReceiptRef.v1": (
        "IMMUTABLE_EXTERNAL_REF",
        "project_receipt_store",
    ),
}

_LEDGER_FORBIDDEN_OBJECT_TYPES = frozenset(
    {
        "CapturedMaterialSnapshot.v1",
        "DeliveryAttempt.v1",
        "Document",
        "Document.v1",
        "EvidenceQualification.v1",
    }
)


def assert_first_slice_owner_binding(
    object_type: str,
    owner_mode: str,
    owner_id: str,
) -> None:
    """Enforce the frozen P0 first-slice owner matrix.

    The matrix is deliberately closed: admitting a new object type or changing
    an owner requires a successor frozen contract/epoch, not a permissive
    repository call.
    """

    if object_type in _LEDGER_FORBIDDEN_OBJECT_TYPES:
        raise OwnerBindingViolation(
            f"{object_type} is not a Research Ledger object; store only its relation/ref"
        )
    expected = _FIRST_SLICE_LEDGER_OWNER_MATRIX.get(object_type)
    if expected is None:
        raise OwnerBindingViolation(
            f"{object_type} is not admitted by the frozen first-slice owner matrix"
        )
    expected_mode, expected_owner = expected
    if owner_mode != expected_mode:
        raise OwnerBindingViolation(
            f"{object_type} requires owner mode {expected_mode}, got {owner_mode}"
        )
    if owner_id != expected_owner:
        raise OwnerBindingViolation(
            f"{object_type} requires owner {expected_owner}, got {owner_id}"
        )


def utcnow() -> datetime:
    return datetime.now(UTC)


def scope_ref(scope: RuntimeScope | ProjectScopeRef) -> ProjectScopeRef:
    if isinstance(scope, RuntimeScope):
        return scope.project_scope
    if isinstance(scope, ProjectScopeRef):
        return scope
    raise TypeError("scope must be RuntimeScope or ProjectScopeRef")


def scope_actor(scope: RuntimeScope | ProjectScopeRef) -> str:
    return scope.actor_id if isinstance(scope, RuntimeScope) else "project-scope"


def project_table(tables: Any, name: str) -> Table:
    table = getattr(tables, name, None)
    if table is None and isinstance(tables, Mapping):
        table = tables.get(name)
    if not isinstance(table, Table):
        raise TypeError(f"missing or invalid project table: {name}")
    return table


def assert_table_scope(table: Table, scope: RuntimeScope | ProjectScopeRef) -> str:
    resolved = scope_ref(scope)
    if table.schema != resolved.resolved_schema:
        raise ProjectScopeMismatch(
            f"table schema {table.schema!r} does not match resolved schema "
            f"{resolved.resolved_schema!r}"
        )
    return resolved.project_key


def one_mapping(result: Any) -> Mapping[str, Any] | None:
    row = result.mappings().one_or_none()
    return None if row is None else row


def mapping_tuple(result: Any) -> tuple[Mapping[str, Any], ...]:
    return tuple(result.mappings().all())


def require_sha256(value: str, field_name: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field_name} must be canonical sha256 hex")


def object_ref_json(ref: ResearchObjectRef) -> dict[str, Any]:
    return {
        "object_id": ref.object_id,
        "object_type": ref.object_type.type_id,
        "project_key": ref.project_key,
        "revision": ref.revision,
        "incarnation": ref.incarnation,
        "owner_binding_ref": ref.owner_binding_ref,
        "content_ref": ref.content_ref,
        "content_digest": ref.content_digest,
    }


def object_ref_text(ref: ResearchObjectRef) -> str:
    return json.dumps(object_ref_json(ref), sort_keys=True, separators=(",", ":"))


def _object_from_row(row: Mapping[str, Any]) -> ResearchObjectRef:
    return ResearchObjectRef(
        object_id=row["object_id"],
        object_type=ObjectType(row["object_type"]),
        project_key=row["project_key"],
        revision=row["revision"],
        incarnation=row["incarnation"],
        owner_binding_ref=row["owner_binding_ref"],
        content_ref=row["content_ref"],
        content_digest=row["content_digest"],
        provenance_closure_digest=row["provenance_closure_digest"],
        valid_from=row["valid_from"],
        valid_to=row["valid_to"],
        lifecycle_state=row["lifecycle_state"],
    )


def _same_object(row: Mapping[str, Any], ref: ResearchObjectRef) -> bool:
    return all(
        row[name] == value
        for name, value in {
            "object_type": ref.object_type.type_id,
            "revision": ref.revision,
            "incarnation": ref.incarnation,
            "lifecycle_state": ref.lifecycle_state,
            "owner_binding_ref": ref.owner_binding_ref,
            "content_ref": ref.content_ref,
            "content_digest": ref.content_digest,
            "provenance_closure_digest": ref.provenance_closure_digest,
            "valid_from": ref.valid_from,
            "valid_to": ref.valid_to,
        }.items()
    )


class ResearchLedgerRepository:
    """CAS repository for canonical project research objects and relations."""

    def __init__(self, connection: Connection, tables: Any) -> None:
        self.connection = connection
        self.tables = tables

    def _current_owner(
        self,
        scope: RuntimeScope | ProjectScopeRef,
        object_type: str,
    ) -> Mapping[str, Any]:
        table = project_table(self.tables, "research_owner_bindings")
        project_key = assert_table_scope(table, scope)
        row = one_mapping(
            self.connection.execute(
                select(table)
                .where(
                    table.c.project_key == project_key,
                    table.c.object_type == object_type,
                    table.c.superseded_at.is_(None),
                )
                .order_by(table.c.owner_epoch.desc())
                .limit(1)
            )
        )
        if row is None:
            raise OwnerBindingViolation(f"no active owner binding for {object_type}")
        return row

    def put_object(
        self,
        scope: RuntimeScope | ProjectScopeRef,
        ref: ResearchObjectRef,
        *,
        expected_revision: int,
        expected_incarnation: str,
    ) -> ResearchObjectRef:
        """Append one exact canonical version after checking the owner matrix."""

        table = project_table(self.tables, "research_objects")
        project_key = assert_table_scope(table, scope)
        if ref.project_key != project_key:
            raise ProjectScopeMismatch("research object project_key does not match scope")
        type_id = ref.object_type.type_id
        if type_id in _LEDGER_FORBIDDEN_OBJECT_TYPES:
            raise OwnerBindingViolation(
                f"{type_id} is not a Research Ledger object; store only its relation/ref"
            )
        owner = self._current_owner(scope, type_id)
        assert_first_slice_owner_binding(
            type_id,
            str(owner["owner_mode"]),
            str(owner["owner_id"]),
        )
        if ref.owner_binding_ref != owner["owner_id"]:
            raise OwnerBindingViolation("research object owner binding is stale")
        require_sha256(ref.content_digest, "content_digest")
        require_sha256(ref.provenance_closure_digest, "provenance_closure_digest")

        current = one_mapping(
            self.connection.execute(
                select(table)
                .where(
                    table.c.project_key == project_key,
                    table.c.object_id == ref.object_id,
                )
                .order_by(table.c.revision.desc())
                .limit(1)
            )
        )
        if current is None:
            if expected_revision != 0 or ref.revision != 1:
                raise ProjectCASConflict("new research object requires expected revision 0")
            if ref.incarnation != expected_incarnation:
                raise ProjectCASConflict("new research object incarnation mismatch")
        else:
            if int(current["revision"]) != expected_revision:
                raise ProjectCASConflict("stale research object revision")
            if current["incarnation"] != expected_incarnation:
                raise ProjectCASConflict("stale research object incarnation")
            if ref.revision != expected_revision + 1:
                raise ProjectCASConflict("successor research object revision is not monotone")
            if ref.incarnation != expected_incarnation:
                raise ProjectCASConflict("successor research object changed incarnation")

        now = utcnow()
        self.connection.execute(
            insert(table).values(
                project_key=project_key,
                object_id=ref.object_id,
                object_type=type_id,
                revision=ref.revision,
                incarnation=ref.incarnation,
                lifecycle_state=ref.lifecycle_state,
                owner_binding_ref=ref.owner_binding_ref,
                content_ref=ref.content_ref,
                content_digest=ref.content_digest,
                provenance_closure_digest=ref.provenance_closure_digest,
                valid_from=ref.valid_from,
                valid_to=ref.valid_to,
                created_at=now,
                updated_at=now,
            )
        )
        return ref

    def get_object(
        self,
        scope: RuntimeScope | ProjectScopeRef,
        object_id: str,
        *,
        expected_revision: int,
        expected_incarnation: str,
    ) -> ResearchObjectRef:
        table = project_table(self.tables, "research_objects")
        project_key = assert_table_scope(table, scope)
        row = one_mapping(
            self.connection.execute(
                select(table).where(
                    table.c.project_key == project_key,
                    table.c.object_id == object_id,
                    table.c.revision == expected_revision,
                    table.c.incarnation == expected_incarnation,
                )
            )
        )
        if row is None:
            raise ProjectRecordNotFound(
                f"research object not found at exact CAS binding: {object_id}"
            )
        return _object_from_row(row)

    def put_relation(
        self,
        scope: RuntimeScope | ProjectScopeRef,
        relation: ResearchRelation,
        *,
        expected_revision: int,
        expected_incarnation: str,
    ) -> ResearchRelation:
        table = project_table(self.tables, "research_relations")
        project_key = assert_table_scope(table, scope)
        if relation.project_key != project_key:
            raise ProjectScopeMismatch("research relation project_key does not match scope")
        if relation.source_ref.project_key != project_key or relation.target_ref.project_key != project_key:
            raise ProjectScopeMismatch("research relation endpoint project drift")
        if relation.relation_type == "delivered_as" and (
            relation.source_ref.object_type.type_id != "ResearchArtifact.v1"
            or relation.target_ref.object_type.type_id != "DeliveryReceiptRef.v1"
        ):
            raise OwnerBindingViolation(
                "delivered_as requires ResearchArtifact.v1 -> DeliveryReceiptRef.v1"
            )
        self._assert_exact_endpoint(table, scope, relation.source_ref)
        self._assert_exact_endpoint(table, scope, relation.target_ref)
        if relation.relation_type == "delivered_as":
            self._assert_authoritative_delivery_receipt(scope, relation.target_ref)
        current = one_mapping(
            self.connection.execute(
                select(table)
                .where(
                    table.c.project_key == project_key,
                    table.c.relation_id == relation.relation_id,
                )
                .order_by(table.c.revision.desc())
                .limit(1)
            )
        )
        self._validate_version_cas(
            current,
            new_revision=relation.revision,
            new_incarnation=relation.incarnation,
            expected_revision=expected_revision,
            expected_incarnation=expected_incarnation,
            label="research relation",
        )
        now = utcnow()
        self.connection.execute(
            insert(table).values(
                project_key=project_key,
                relation_id=relation.relation_id,
                relation_type=relation.relation_type,
                source_object_ref=object_ref_text(relation.source_ref),
                target_object_ref=object_ref_text(relation.target_ref),
                direction=relation.direction or relation.relation_type.upper(),
                scope_ref=relation.scope_ref or "scope:unspecified",
                uncertainty_profile_ref=relation.uncertainty_profile_ref or "uncertainty:unspecified",
                validity_json={"value": relation.validity},
                provenance_closure_digest=relation.provenance_closure_digest,
                revision=relation.revision,
                incarnation=relation.incarnation,
                state=relation.state,
                created_at=now,
                updated_at=now,
            )
        )
        return relation

    def put_evidence_qualification(
        self,
        scope: RuntimeScope | ProjectScopeRef,
        qualification: EvidenceQualification,
        *,
        source_ref: ResearchObjectRef,
        target_ref: ResearchObjectRef,
        expected_revision: int,
        expected_incarnation: str,
    ) -> Mapping[str, Any]:
        """Persist EvidenceQualification in ``research_relations`` only."""

        table = project_table(self.tables, "research_relations")
        project_key = assert_table_scope(table, scope)
        if qualification.project_key != project_key:
            raise ProjectScopeMismatch("evidence qualification project_key does not match scope")
        self._assert_exact_endpoint(table, scope, source_ref)
        self._assert_exact_endpoint(table, scope, target_ref)
        current = one_mapping(
            self.connection.execute(
                select(table)
                .where(
                    table.c.project_key == project_key,
                    table.c.relation_id == qualification.qualification_id,
                )
                .order_by(table.c.revision.desc())
                .limit(1)
            )
        )
        self._validate_version_cas(
            current,
            new_revision=qualification.revision,
            new_incarnation=qualification.incarnation,
            expected_revision=expected_revision,
            expected_incarnation=expected_incarnation,
            label="evidence qualification",
        )
        now = utcnow()
        values = {
            "project_key": project_key,
            "relation_id": qualification.qualification_id,
            "relation_type": {
                "SUPPORTS": "supports",
                "CONTRADICTS": "contradicts",
                "CONTEXT": "derived_from",
                "INSUFFICIENT": "opens",
            }[qualification.direction],
            "source_object_ref": object_ref_text(source_ref),
            "target_object_ref": object_ref_text(target_ref),
            "direction": qualification.direction,
            "scope_ref": qualification.scope_statement_ref,
            "uncertainty_profile_ref": qualification.uncertainty_profile_ref,
            "validity_json": {
                "valid_from": qualification.validity.valid_from.isoformat()
                if qualification.validity.valid_from
                else None,
                "valid_to": qualification.validity.valid_to.isoformat()
                if qualification.validity.valid_to
                else None,
                "source_time": qualification.source_time.isoformat()
                if qualification.source_time
                else None,
                "observed_at": qualification.observed_at.isoformat()
                if qualification.observed_at
                else None,
                "claim_ref": qualification.claim_ref,
                "verifier_profile_ref": qualification.verifier_profile_ref,
            },
            "provenance_closure_digest": qualification.provenance_closure_digest,
            "revision": qualification.revision,
            "incarnation": qualification.incarnation,
            "state": qualification.state,
            "created_at": now,
            "updated_at": now,
        }
        self.connection.execute(insert(table).values(**values))
        return values

    def _assert_authoritative_delivery_receipt(
        self,
        scope: RuntimeScope | ProjectScopeRef,
        receipt_ref: ResearchObjectRef,
    ) -> None:
        receipt_table = project_table(self.tables, "successor_receipts")
        project_key = assert_table_scope(receipt_table, scope)
        row = one_mapping(
            self.connection.execute(
                select(receipt_table).where(
                    receipt_table.c.project_key == project_key,
                    receipt_table.c.receipt_id == receipt_ref.object_id,
                )
            )
        )
        if row is None:
            raise ProjectRecordNotFound(
                "delivered_as target lacks exact authoritative receipt readback: "
                f"{receipt_ref.object_id}"
            )

    def _assert_exact_endpoint(
        self,
        _relation_table: Table,
        scope: RuntimeScope | ProjectScopeRef,
        ref: ResearchObjectRef,
    ) -> None:
        object_table = project_table(self.tables, "research_objects")
        project_key = assert_table_scope(object_table, scope)
        row = one_mapping(self.connection.execute(select(object_table).where(
            object_table.c.project_key == project_key,
            object_table.c.object_id == ref.object_id,
            object_table.c.revision == ref.revision,
            object_table.c.incarnation == ref.incarnation,
            object_table.c.content_digest == ref.content_digest,
        )))
        if row is None or not _same_object(row, ref):
            raise ProjectRecordNotFound(
                f"relation endpoint is not authoritative at exact binding: {ref.object_id}"
            )

    @staticmethod
    def _validate_version_cas(
        current: Mapping[str, Any] | None,
        *,
        new_revision: int,
        new_incarnation: str,
        expected_revision: int,
        expected_incarnation: str,
        label: str,
    ) -> None:
        if current is None:
            if expected_revision != 0 or new_revision != 1:
                raise ProjectCASConflict(f"new {label} requires expected revision 0")
            if new_incarnation != expected_incarnation:
                raise ProjectCASConflict(f"new {label} incarnation mismatch")
            return
        if int(current["revision"]) != expected_revision:
            raise ProjectCASConflict(f"stale {label} revision")
        if current["incarnation"] != expected_incarnation:
            raise ProjectCASConflict(f"stale {label} incarnation")
        if new_revision != expected_revision + 1 or new_incarnation != expected_incarnation:
            raise ProjectCASConflict(f"invalid successor {label} binding")


__all__ = [
    "ExactContentConflict",
    "OwnerBindingViolation",
    "ProjectCASConflict",
    "ProjectRecordNotFound",
    "ProjectRepositoryError",
    "ProjectScopeMismatch",
    "ResearchLedgerRepository",
    "assert_first_slice_owner_binding",
    "assert_table_scope",
    "mapping_tuple",
    "one_mapping",
    "project_table",
    "require_sha256",
    "scope_actor",
    "scope_ref",
    "utcnow",
]
