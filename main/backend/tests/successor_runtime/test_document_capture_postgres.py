"""Real PostgreSQL witnesses for atomic frozen Document capture."""

from __future__ import annotations

import hashlib
from typing import Any

import pytest
import sqlalchemy as sa

from app.successor_migration.document_canonical_read import (
    PostgresLegacyDocumentCanonicalReadAdapter,
)
from app.successor_runtime.substrate.postgres.values import ValueRepository

from .research_runtime_postgres_fixture import (
    LEGACY_DOCUMENTS,
    SEED_CONTENT_BYTES,
    SEED_CONTENT_SHA256,
    LiveResearchRuntimeDatabase,
)

pytestmark = pytest.mark.integration
pytest_plugins = ("tests.successor_runtime.research_runtime_postgres_fixture",)


class _CountingDocuments:
    def __init__(self, delegate: PostgresLegacyDocumentCanonicalReadAdapter) -> None:
        self.delegate = delegate
        self.reads: list[int] = []

    def read_document(self, scope: object, document_id: int) -> Any:
        self.reads.append(document_id)
        return self.delegate.read_document(scope, document_id)  # type: ignore[arg-type]


class _FailOnSecondDocument(_CountingDocuments):
    def read_document(self, scope: object, document_id: int) -> Any:
        if document_id == 102:
            self.reads.append(document_id)
            raise RuntimeError("injected before second capture commit")
        return super().read_document(scope, document_id)


def _capture_rows(database: LiveResearchRuntimeDatabase) -> tuple[sa.RowMapping, ...]:
    with database.engine.connect() as connection:
        return tuple(
            connection.execute(
                sa.select(database.project_tables.successor_values).order_by(
                    database.project_tables.successor_values.c.value_id
                )
            ).mappings()
        )


def test_two_real_seed_documents_are_captured_atomically_with_typed_refs(
    research_runtime_database: LiveResearchRuntimeDatabase,
) -> None:
    captures = research_runtime_database.capture_documents()

    assert tuple(item.observation.document_id for item in captures) == (101, 102)
    for capture in captures:
        document_id = capture.observation.document_id
        exact = capture.observation.exact_bytes
        assert len(exact) == SEED_CONTENT_BYTES[document_id]
        assert hashlib.sha256(exact).hexdigest() == SEED_CONTENT_SHA256[document_id]
        assert capture.snapshot_value_ref.byte_size == len(exact)
        assert capture.snapshot_value_ref.content_digest == SEED_CONTENT_SHA256[document_id]
        assert research_runtime_database.value_bytes(capture.snapshot_value_ref.value_id) == exact

    with research_runtime_database.engine.connect() as connection:
        objects = tuple(
            connection.execute(
                sa.select(research_runtime_database.project_tables.research_objects)
            ).mappings()
        )
    assert {row["object_type"] for row in objects} == {"MaterialRef.v1"}
    assert all(row["content_ref"].startswith("project-value:") for row in objects)


def test_document_mutation_after_capture_cannot_change_stored_input(
    research_runtime_database: LiveResearchRuntimeDatabase,
) -> None:
    first = research_runtime_database.capture_documents()[0]
    before = first.observation.exact_bytes
    with research_runtime_database.engine.begin() as connection:
        connection.execute(
            sa.update(LEGACY_DOCUMENTS)
            .where(LEGACY_DOCUMENTS.c.id == 101)
            .values(content="mutated after immutable capture")
        )
    assert research_runtime_database.value_bytes(first.snapshot_value_ref.value_id) == before


def test_second_document_failure_rolls_back_all_capture_values_and_objects(
    research_runtime_database: LiveResearchRuntimeDatabase,
) -> None:
    port: _FailOnSecondDocument | None = None

    def factory(uow: object) -> _FailOnSecondDocument:
        nonlocal port
        port = _FailOnSecondDocument(
            PostgresLegacyDocumentCanonicalReadAdapter(uow.connection)  # type: ignore[attr-defined]
        )
        return port

    with pytest.raises(RuntimeError, match="second capture"):
        research_runtime_database.capture_documents(document_port=factory)
    assert port is not None and port.reads == [101, 102]
    assert _capture_rows(research_runtime_database) == ()
    with research_runtime_database.engine.connect() as connection:
        count = connection.scalar(
            sa.select(sa.func.count()).select_from(
                research_runtime_database.project_tables.research_objects
            )
        )
    assert count == 0


def test_capture_retry_returns_durable_closure_without_document_reread(
    research_runtime_database: LiveResearchRuntimeDatabase,
) -> None:
    port: _CountingDocuments | None = None

    def factory(uow: object) -> _CountingDocuments:
        nonlocal port
        port = _CountingDocuments(
            PostgresLegacyDocumentCanonicalReadAdapter(uow.connection)  # type: ignore[attr-defined]
        )
        return port

    first = research_runtime_database.capture_documents(document_port=factory)
    assert port is not None and port.reads == [101, 102]
    second = research_runtime_database.capture_documents(document_port=factory)
    assert port.reads == [101, 102]
    assert second == first


def test_capture_value_readback_is_exact_after_engine_restart(
    research_runtime_database: LiveResearchRuntimeDatabase,
) -> None:
    capture = research_runtime_database.capture_documents()[1]
    research_runtime_database.engine.dispose()
    with research_runtime_database.engine.connect() as connection:
        exact = ValueRepository(
            connection, research_runtime_database.project_tables
        ).get_exact(
            research_runtime_database.scope,
            capture.snapshot_value_ref.value_id,
            expected_revision=1,
            expected_incarnation=(
                f"capture:1:{capture.snapshot_value_ref.value_id}"
            ),
            expected_digest=capture.snapshot_value_ref.content_digest,
        )
    assert exact == capture.observation.exact_bytes
    assert hashlib.sha256(exact).hexdigest() == SEED_CONTENT_SHA256[102]
