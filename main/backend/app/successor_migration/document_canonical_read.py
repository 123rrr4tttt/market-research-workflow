"""Authoritative, read-only access to legacy-owned ``documents`` rows.

This sibling adapter is deliberately the only place where the first successor
specimen knows how a legacy Document is stored.  It verifies the complete
server-owned project-scope identity against the current public registry row and
then captures one row observation with one schema-qualified SELECT.  It owns no
transaction and never locks, commits, rolls back, or writes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import MultipleResultsFound

from app.successor_runtime.runtime.ports import (
    CanonicalDocumentRead,
    ProjectScopeRef,
    RuntimeScope,
)
from app.successor_runtime.substrate.postgres.session import (
    ProjectScopeValidationError,
    validate_project_scope_ref,
)


class LegacyDocumentCanonicalReadError(RuntimeError):
    """Base class for fail-closed legacy Document observations."""


class LegacyDocumentScopeMismatch(LegacyDocumentCanonicalReadError):
    """The supplied scope is malformed, stale, or not the current binding."""


class LegacyDocumentNotFound(LegacyDocumentCanonicalReadError):
    """No Document exists at the requested current project scope."""


class LegacyDocumentInvalidObservation(LegacyDocumentCanonicalReadError):
    """A Document row cannot form a complete canonical observation."""


class PostgresLegacyDocumentCanonicalReadAdapter:
    """Implement ``DocumentCanonicalReadPort`` over an enlisted connection.

    The caller owns the connection and its transaction.  The returned bytes are
    an immutable copy of the row observation, so later mutation of the legacy
    row cannot alter the captured value held by the caller.
    """

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def _require_current_scope(self, scope: RuntimeScope) -> ProjectScopeRef:
        if not isinstance(scope, RuntimeScope) or not isinstance(
            scope.project_scope, ProjectScopeRef
        ):
            raise LegacyDocumentScopeMismatch(
                "legacy Document read requires a typed RuntimeScope"
            )

        supplied = scope.project_scope
        try:
            validate_project_scope_ref(supplied)
        except (ProjectScopeValidationError, KeyError, TypeError, ValueError) as exc:
            raise LegacyDocumentScopeMismatch(
                "project scope identity could not be validated"
            ) from exc
        return supplied

    def read_document(
        self, scope: RuntimeScope, document_id: int
    ) -> CanonicalDocumentRead:
        if (
            not isinstance(document_id, int)
            or isinstance(document_id, bool)
            or document_id <= 0
        ):
            raise ValueError("document_id must be a positive non-boolean integer")

        current = self._require_current_scope(scope)
        schema = current.resolved_schema
        # ``validate_project_scope_ref`` admits only lower-case PostgreSQL
        # project identifiers and rejects public/control schemas.  The exact
        # ref is then checked against the ACTIVE registry row below.  Quoting
        # still makes qualification explicit and independent of search_path.
        # Scope validation and Document observation deliberately share one SQL
        # statement/MVCC snapshot.  The exact ACTIVE registry binding is the
        # left side of the join, closing the validate-then-read race without a
        # lock.  A valid scope with no Document yields one row with a null id;
        # an invalid/stale/ABA scope yields no row.
        statement = text(
            "SELECT scope_registry.scope_digest AS validated_scope_digest, "
            "legacy_document.id, legacy_document.text_hash, "
            "legacy_document.updated_at, "
            "convert_to(legacy_document.content,'UTF8') AS exact_bytes "
            "FROM public.project_scope_registry AS scope_registry "
            f'LEFT JOIN "{schema}"."documents" AS legacy_document '
            "ON legacy_document.id = :document_id "
            "WHERE scope_registry.project_key = :project_key "
            "AND scope_registry.registry_revision = :project_registry_revision "
            "AND scope_registry.resolved_schema = :resolved_schema "
            "AND scope_registry.scope_digest = :scope_digest "
            "AND scope_registry.incarnation = :incarnation "
            "AND scope_registry.state = 'ACTIVE'"
        )
        try:
            row = (
                self._connection.execute(
                    statement,
                    {
                        "document_id": document_id,
                        "project_key": current.project_key,
                        "project_registry_revision": (
                            current.project_registry_revision
                        ),
                        "resolved_schema": current.resolved_schema,
                        "scope_digest": current.scope_digest,
                        "incarnation": current.incarnation,
                    },
                )
                .mappings()
                .one_or_none()
            )
        except MultipleResultsFound as exc:
            raise LegacyDocumentScopeMismatch(
                "registry-backed Document observation was not unique"
            ) from exc

        if row is None:
            raise LegacyDocumentScopeMismatch(
                "RuntimeScope is stale or does not match the current registry binding"
            )

        try:
            validated_scope_digest: Any = row["validated_scope_digest"]
            observed_id: Any = row["id"]
            text_hash: Any = row["text_hash"]
            updated_at: Any = row["updated_at"]
            exact_bytes: Any = row["exact_bytes"]
        except (KeyError, TypeError) as exc:
            raise LegacyDocumentInvalidObservation(
                "Document row is missing canonical observation fields"
            ) from exc

        if validated_scope_digest != current.scope_digest:
            raise LegacyDocumentScopeMismatch(
                "registry-backed Document observation changed scope identity"
            )
        if observed_id is None:
            raise LegacyDocumentNotFound(
                f"Document {document_id} was not found in the validated project scope"
            )

        if (
            not isinstance(observed_id, int)
            or isinstance(observed_id, bool)
            or observed_id != document_id
        ):
            raise LegacyDocumentInvalidObservation(
                "Document row identity does not match the requested positive integer"
            )
        if text_hash is not None and not isinstance(text_hash, str):
            raise LegacyDocumentInvalidObservation(
                "Document text_hash must be a string or null"
            )
        if not isinstance(updated_at, datetime):
            raise LegacyDocumentInvalidObservation(
                "Document updated_at must be a datetime"
            )
        try:
            offset = updated_at.utcoffset()
        except (OverflowError, ValueError) as exc:
            raise LegacyDocumentInvalidObservation(
                "Document updated_at has an invalid timezone"
            ) from exc
        if updated_at.tzinfo is None or offset is None:
            raise LegacyDocumentInvalidObservation(
                "Document updated_at must be timezone-aware"
            )
        if exact_bytes is None:
            raise LegacyDocumentInvalidObservation(
                "Document content is null and cannot be captured"
            )
        if not isinstance(exact_bytes, (bytes, bytearray, memoryview)):
            raise LegacyDocumentInvalidObservation(
                "Document content readback did not return bytes"
            )

        return CanonicalDocumentRead(
            document_id=observed_id,
            text_hash=text_hash,
            updated_at=updated_at.astimezone(UTC),
            exact_bytes=bytes(exact_bytes),
        )
