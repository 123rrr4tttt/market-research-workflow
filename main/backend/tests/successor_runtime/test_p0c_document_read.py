"""P0-C authoritative legacy Document read adapter."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.exc import MultipleResultsFound

from app.successor_migration.document_canonical_read import (
    LegacyDocumentInvalidObservation,
    LegacyDocumentNotFound,
    LegacyDocumentScopeMismatch,
    PostgresLegacyDocumentCanonicalReadAdapter,
)
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
from app.successor_runtime.substrate.postgres.session import compute_scope_digest

PROJECT_KEY = "p0c-demo"
PROJECT_SCHEMA = "mrw_p_p0c_demo"
REGISTRY_REVISION = 4
INCARNATION = "scope-incarnation:p0c-demo:4"
SCOPE_DIGEST = compute_scope_digest(
    PROJECT_KEY,
    PROJECT_SCHEMA,
    REGISTRY_REVISION,
    INCARNATION,
)


def _registry_row(**updates: Any) -> dict[str, Any]:
    row = {
        "project_key": PROJECT_KEY,
        "resolved_schema": PROJECT_SCHEMA,
        "registry_revision": REGISTRY_REVISION,
        "incarnation": INCARNATION,
        "scope_digest": SCOPE_DIGEST,
        "state": "ACTIVE",
    }
    row.update(updates)
    if "scope_digest" not in updates:
        row["scope_digest"] = compute_scope_digest(
            row["project_key"],
            row["resolved_schema"],
            row["registry_revision"],
            row["incarnation"],
        )
    return row


def _scope(**updates: Any) -> RuntimeScope:
    values = {
        "project_key": PROJECT_KEY,
        "resolved_schema": PROJECT_SCHEMA,
        "project_registry_revision": REGISTRY_REVISION,
        "incarnation": INCARNATION,
        "scope_digest": SCOPE_DIGEST,
    }
    values.update(updates)
    if "scope_digest" not in updates:
        values["scope_digest"] = compute_scope_digest(
            values["project_key"],
            values["resolved_schema"],
            values["project_registry_revision"],
            values["incarnation"],
        )
    return RuntimeScope(
        project_scope=ProjectScopeRef(**values),
        actor_id="p0c-submit",
    )


class _MappingsResult:
    def __init__(
        self, rows: list[Mapping[str, Any]], *, multiple: bool = False
    ) -> None:
        self._rows = rows
        self._multiple = multiple

    def all(self) -> list[Mapping[str, Any]]:
        return list(self._rows)

    def one_or_none(self) -> Mapping[str, Any] | None:
        if self._multiple or len(self._rows) > 1:
            raise MultipleResultsFound("fake duplicate row")
        return self._rows[0] if self._rows else None


class _Result:
    def __init__(
        self, rows: list[Mapping[str, Any]], *, multiple: bool = False
    ) -> None:
        self._rows = rows
        self._multiple = multiple

    def mappings(self) -> _MappingsResult:
        return _MappingsResult(self._rows, multiple=self._multiple)


class _FakeConnection:
    def __init__(
        self,
        *,
        registry_rows: list[Mapping[str, Any]] | None = None,
        document_rows: list[Mapping[str, Any]] | None = None,
        duplicate_document: bool = False,
    ) -> None:
        self.registry_rows = registry_rows or []
        self.document_rows = document_rows or []
        self.duplicate_document = duplicate_document
        self.calls: list[tuple[str, Mapping[str, Any] | None]] = []

    def execute(
        self,
        statement: object,
        parameters: Mapping[str, Any] | None = None,
    ) -> _Result:
        sql = str(statement)
        self.calls.append((sql, parameters))
        if (
            "public.project_scope_registry" in sql
            and '."documents"' in sql
            and parameters is not None
        ):
            matching_scope = [
                row
                for row in self.registry_rows
                if row["project_key"] == parameters["project_key"]
                and row["registry_revision"] == parameters["project_registry_revision"]
                and row["resolved_schema"] == parameters["resolved_schema"]
                and row["scope_digest"] == parameters["scope_digest"]
                and row["incarnation"] == parameters["incarnation"]
                and row["state"] == "ACTIVE"
            ]
            if len(matching_scope) != 1:
                return _Result([], multiple=len(matching_scope) > 1)
            if not self.document_rows:
                return _Result(
                    [
                        {
                            "validated_scope_digest": matching_scope[0]["scope_digest"],
                            "id": None,
                            "text_hash": None,
                            "updated_at": None,
                            "exact_bytes": None,
                        }
                    ]
                )
            joined = [
                {
                    "validated_scope_digest": matching_scope[0]["scope_digest"],
                    **row,
                }
                for row in self.document_rows
            ]
            return _Result(joined, multiple=self.duplicate_document)
        raise AssertionError(f"unexpected SQL: {sql}")


def _document_row(**updates: Any) -> dict[str, Any]:
    row = {
        "id": 101,
        "text_hash": "a" * 64,
        "updated_at": datetime(2026, 8, 30, 15, 20, tzinfo=UTC),
        "exact_bytes": bytearray("first specimen 文档".encode()),
    }
    row.update(updates)
    return row


def test_read_validates_current_scope_and_returns_independent_exact_bytes() -> None:
    mutable_readback = bytearray("first specimen 文档".encode())
    connection = _FakeConnection(
        registry_rows=[_registry_row()],
        document_rows=[_document_row(exact_bytes=mutable_readback)],
    )

    observed = PostgresLegacyDocumentCanonicalReadAdapter(connection).read_document(
        _scope(),
        101,
    )

    assert observed.document_id == 101
    assert observed.text_hash == "a" * 64
    assert observed.updated_at == datetime(2026, 8, 30, 15, 20, tzinfo=UTC)
    assert observed.exact_bytes == "first specimen 文档".encode()
    assert isinstance(observed.exact_bytes, bytes)

    mutable_readback[:] = b"legacy row mutated after capture"
    assert observed.exact_bytes == "first specimen 文档".encode()

    assert len(connection.calls) == 1
    document_sql, document_params = connection.calls[0]
    assert "FROM public.project_scope_registry AS scope_registry" in document_sql
    assert (
        "legacy_document.id, legacy_document.text_hash, legacy_document.updated_at"
    ) in document_sql
    assert "convert_to(legacy_document.content,'UTF8') AS exact_bytes" in document_sql
    assert 'LEFT JOIN "mrw_p_p0c_demo"."documents" AS legacy_document' in document_sql
    assert "scope_registry.state = 'ACTIVE'" in document_sql
    assert document_params == {
        "document_id": 101,
        "project_key": PROJECT_KEY,
        "project_registry_revision": REGISTRY_REVISION,
        "resolved_schema": PROJECT_SCHEMA,
        "scope_digest": SCOPE_DIGEST,
        "incarnation": INCARNATION,
    }
    all_sql = "\n".join(sql.upper() for sql, _ in connection.calls)
    assert "FOR UPDATE" not in all_sql
    assert " INSERT " not in f" {all_sql} "
    assert " UPDATE " not in f" {all_sql} "
    assert " DELETE " not in f" {all_sql} "


@pytest.mark.parametrize("document_id", [True, False, 0, -1, 1.0, "101", None])
def test_document_id_must_be_positive_int_not_bool(document_id: object) -> None:
    connection = _FakeConnection(registry_rows=[_registry_row()])
    with pytest.raises(ValueError, match="positive non-boolean integer"):
        PostgresLegacyDocumentCanonicalReadAdapter(connection).read_document(
            _scope(),
            document_id,  # type: ignore[arg-type]
        )
    assert connection.calls == []


def test_missing_document_fails_closed() -> None:
    connection = _FakeConnection(registry_rows=[_registry_row()])
    with pytest.raises(LegacyDocumentNotFound):
        PostgresLegacyDocumentCanonicalReadAdapter(connection).read_document(
            _scope(), 101
        )


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"exact_bytes": None}, "content is null"),
        ({"exact_bytes": "not bytes"}, "did not return bytes"),
        ({"updated_at": None}, "must be a datetime"),
        (
            {"updated_at": datetime(2026, 8, 30, 15, 20)},
            "timezone-aware",
        ),
        ({"id": 102}, "identity does not match"),
        ({"id": True}, "identity does not match"),
        ({"text_hash": 123}, "string or null"),
    ],
)
def test_malformed_or_null_observation_fails_closed(
    updates: Mapping[str, Any], message: str
) -> None:
    connection = _FakeConnection(
        registry_rows=[_registry_row()],
        document_rows=[_document_row(**updates)],
    )
    with pytest.raises(LegacyDocumentInvalidObservation, match=message):
        PostgresLegacyDocumentCanonicalReadAdapter(connection).read_document(
            _scope(), 101
        )


def test_nullable_legacy_text_hash_is_preserved_as_an_observation() -> None:
    connection = _FakeConnection(
        registry_rows=[_registry_row()],
        document_rows=[_document_row(text_hash=None)],
    )
    observed = PostgresLegacyDocumentCanonicalReadAdapter(connection).read_document(
        _scope(), 101
    )
    assert observed.text_hash is None


def test_duplicate_document_identity_fails_closed() -> None:
    connection = _FakeConnection(
        registry_rows=[_registry_row()],
        document_rows=[_document_row(), _document_row()],
        duplicate_document=True,
    )
    with pytest.raises(LegacyDocumentScopeMismatch, match="not unique"):
        PostgresLegacyDocumentCanonicalReadAdapter(connection).read_document(
            _scope(), 101
        )


@pytest.mark.parametrize(
    "scope",
    [
        _scope(project_registry_revision=3),
        _scope(resolved_schema="mrw_p_stale"),
        _scope(incarnation="scope-incarnation:p0c-demo:stale"),
    ],
)
def test_stale_or_aba_scope_fails_before_document_read(scope: RuntimeScope) -> None:
    connection = _FakeConnection(registry_rows=[_registry_row()])
    with pytest.raises(LegacyDocumentScopeMismatch, match="stale"):
        PostgresLegacyDocumentCanonicalReadAdapter(connection).read_document(scope, 101)
    assert len(connection.calls) == 1
    assert "project_scope_registry" in connection.calls[0][0]


def test_registry_digest_tamper_or_non_unique_current_scope_fails_closed() -> None:
    bad_digest = _registry_row(scope_digest="f" * 64)
    for rows in ([bad_digest], [_registry_row(), _registry_row()]):
        connection = _FakeConnection(registry_rows=rows)
        with pytest.raises(LegacyDocumentScopeMismatch):
            PostgresLegacyDocumentCanonicalReadAdapter(connection).read_document(
                _scope(), 101
            )
        assert len(connection.calls) == 1


def test_malformed_runtime_scope_fails_before_any_query() -> None:
    malformed = RuntimeScope(project_scope="caller-chosen", actor_id="actor")  # type: ignore[arg-type]
    connection = _FakeConnection(registry_rows=[_registry_row()])
    with pytest.raises(LegacyDocumentScopeMismatch, match="typed RuntimeScope"):
        PostgresLegacyDocumentCanonicalReadAdapter(connection).read_document(
            malformed, 101
        )
    assert connection.calls == []
