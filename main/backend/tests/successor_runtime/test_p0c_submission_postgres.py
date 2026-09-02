"""Real PostgreSQL submission and frozen Document-capture acceptance."""

from __future__ import annotations

import hashlib
from typing import Any

import pytest
import sqlalchemy as sa

from app.successor_migration.document_canonical_read import (
    PostgresLegacyDocumentCanonicalReadAdapter,
)
from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES
from app.successor_runtime.substrate.postgres.values import ValueRepository

from .p0c_postgres_fixture import (
    LEGACY_DOCUMENTS,
    PROJECT_KEY,
    SEED_CONTENT_BYTES,
    SEED_CONTENT_SHA256,
    LiveP0CDatabase,
    live_p0c_database,
    p0c_database,
    submission_command,
)

pytestmark = pytest.mark.integration


def _count(connection: sa.Connection, table: sa.Table) -> int:
    return int(connection.scalar(sa.select(sa.func.count()).select_from(table)) or 0)


def test_a02_a03_real_seed_documents_are_captured_once_without_ledger_content_copy(
    p0c_database: LiveP0CDatabase,
) -> None:
    submitted = p0c_database.submission_service().submit(submission_command())

    assert tuple(item.observation.document_id for item in submitted.captures) == (
        101,
        102,
    )
    for capture in submitted.captures:
        document_id = capture.observation.document_id
        exact = capture.observation.exact_bytes
        assert len(exact) == SEED_CONTENT_BYTES[document_id]
        assert hashlib.sha256(exact).hexdigest() == SEED_CONTENT_SHA256[document_id]
        assert capture.snapshot_value_ref.byte_size == len(exact)
        assert capture.snapshot_value_ref.content_digest == SEED_CONTENT_SHA256[document_id]
        stored = p0c_database.value_bytes(
            capture.snapshot_value_ref.value_id
        )
        assert stored == exact

    with p0c_database.engine.connect() as connection:
        runs = connection.execute(
            sa.select(PUBLIC_TABLES["runtime_runs"])
        ).mappings().all()
        events = connection.execute(
            sa.select(PUBLIC_TABLES["runtime_events"]).order_by(
                PUBLIC_TABLES["runtime_events"].c.seq
            )
        ).mappings().all()
        work = connection.execute(
            sa.select(PUBLIC_TABLES["runtime_work_items"])
        ).mappings().one()
        objects = connection.execute(
            sa.select(p0c_database.project_tables.research_objects)
        ).mappings().all()
        assert len(runs) == 1
        assert runs[0]["state"] == "SUBMITTED"
        assert [event["event_type"] for event in events] == ["ProgramAccepted"]
        assert work["assignment_kind"] == "COMPILE"
        assert work["assignment_digest"] == submitted.compile_assignment.assignment_digest
        object_types = {row["object_type"] for row in objects}
        assert "Document" not in object_types
        assert "Document.v1" not in object_types
        assert "CapturedMaterialSnapshot.v1" not in object_types
        assert "EvidenceQualification.v1" not in object_types
        assert object_types == {
            "ResearchIntent.v1",
            "Inquiry.v1",
            "ResearchPlan.v1",
            "SourceRef.v1",
            "MaterialRef.v1",
        }
        assert all(row["content_ref"].startswith("project-value:") for row in objects)


def test_a02_document_mutation_after_submission_cannot_change_captured_input(
    p0c_database: LiveP0CDatabase,
) -> None:
    submitted = p0c_database.submission_service().submit(submission_command())
    first_capture = submitted.captures[0]
    before = first_capture.observation.exact_bytes

    with p0c_database.engine.begin() as connection:
        connection.execute(
            sa.update(LEGACY_DOCUMENTS)
            .where(LEGACY_DOCUMENTS.c.id == 101)
            .values(content="mutated after immutable capture")
        )
    with p0c_database.engine.connect() as connection:
        current = PostgresLegacyDocumentCanonicalReadAdapter(connection).read_document(
            p0c_database.scope, 101
        )

    assert current.exact_bytes == b"mutated after immutable capture"
    assert current.exact_bytes != before
    stored = p0c_database.value_bytes(first_capture.snapshot_value_ref.value_id)
    assert stored == before
    assert hashlib.sha256(stored).hexdigest() == SEED_CONTENT_SHA256[101]


class _FailOnSecondDocument:
    def __init__(self, delegate: PostgresLegacyDocumentCanonicalReadAdapter) -> None:
        self.delegate = delegate

    def read_document(self, scope: object, document_id: int) -> Any:
        if document_id == 102:
            raise RuntimeError("CW01 injected before second snapshot commit")
        return self.delegate.read_document(scope, document_id)  # type: ignore[arg-type]


class _RejectRuntimePublication:
    def get_submission(self, _scope: object, _submission_id: str) -> None:
        return None

    def create_submitted(self, _scope: object, _packet: object) -> None:
        raise RuntimeError("CW02 injected before public ProgramRef")


def _assert_no_submission_authority_rows(database: LiveP0CDatabase) -> None:
    with database.engine.connect() as connection:
        assert _count(connection, database.project_tables.successor_values) == 0
        assert _count(connection, database.project_tables.research_objects) == 0
        assert _count(connection, database.project_tables.research_program_specs) == 0
        assert _count(connection, PUBLIC_TABLES["runtime_program_refs"]) == 0
        assert _count(connection, PUBLIC_TABLES["runtime_runs"]) == 0
        assert _count(connection, PUBLIC_TABLES["runtime_events"]) == 0
        assert _count(connection, PUBLIC_TABLES["runtime_work_items"]) == 0


def test_cw01_document_read_failure_rolls_back_snapshot_material_and_run(
    p0c_database: LiveP0CDatabase,
) -> None:
    service = p0c_database.submission_service(
        document_port=lambda uow: _FailOnSecondDocument(
            PostgresLegacyDocumentCanonicalReadAdapter(uow.connection)
        )
    )
    with pytest.raises(RuntimeError, match="CW01"):
        service.submit(submission_command())
    _assert_no_submission_authority_rows(p0c_database)


def test_cw02_pre_publication_failure_rolls_back_snapshot_and_research_rows(
    p0c_database: LiveP0CDatabase,
) -> None:
    service = p0c_database.submission_service(
        runtime_port=lambda _uow: _RejectRuntimePublication()
    )
    with pytest.raises(RuntimeError, match="CW02"):
        service.submit(submission_command())
    _assert_no_submission_authority_rows(p0c_database)


def test_cw03_work_item_insert_failure_rolls_back_program_run_and_event(
    p0c_database: LiveP0CDatabase,
) -> None:
    # A transaction-local PostgreSQL trigger fails the final work-item insert.
    # The production lifecycle method has already issued ProgramRef/run/event
    # writes at that point, so observing none afterwards proves the UoW edge.
    with p0c_database.engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE FUNCTION public.p0c_fail_work_insert() RETURNS trigger "
            "LANGUAGE plpgsql AS $$ BEGIN "
            "RAISE EXCEPTION 'CW03 injected work insert failure'; END $$"
        )
        connection.exec_driver_sql(
            "CREATE TRIGGER p0c_fail_work_insert BEFORE INSERT "
            "ON public.runtime_work_items FOR EACH ROW "
            "EXECUTE FUNCTION public.p0c_fail_work_insert()"
        )
    try:
        with pytest.raises(Exception, match="CW03 injected work insert failure"):
            p0c_database.submission_service().submit(submission_command())
        _assert_no_submission_authority_rows(p0c_database)
    finally:
        with p0c_database.engine.begin() as connection:
            connection.exec_driver_sql(
                "DROP TRIGGER IF EXISTS p0c_fail_work_insert "
                "ON public.runtime_work_items"
            )
            connection.exec_driver_sql(
                "DROP FUNCTION IF EXISTS public.p0c_fail_work_insert()"
            )


def test_public_control_plane_contains_only_opaque_refs_not_program_or_value_bytes(
    p0c_database: LiveP0CDatabase,
) -> None:
    p0c_database.submission_service().submit(submission_command())
    inspector = sa.inspect(p0c_database.engine)
    forbidden = {
        "program_json",
        "plan_json",
        "payload_bytes",
        "content_bytes",
        "value_bytes",
    }
    for table_name in PUBLIC_TABLES:
        columns = {
            column["name"]
            for column in inspector.get_columns(table_name, schema="public")
        }
        assert not columns & forbidden, (table_name, columns & forbidden)

    with p0c_database.engine.connect() as connection:
        work = connection.execute(
            sa.select(PUBLIC_TABLES["runtime_work_items"])
        ).mappings().one()
        assert work["payload_ref"] is None
        assert work["payload_digest"] is None
        assert work["assignment_binding_json"]["input_refs"]
        assert all(
            isinstance(ref, str) and ref.startswith("project-value:")
            for ref in work["assignment_binding_json"]["input_refs"]
        )


def test_value_repository_readback_is_exact_after_real_postgres_restart_boundary(
    p0c_database: LiveP0CDatabase,
) -> None:
    submitted = p0c_database.submission_service().submit(submission_command())
    capture = submitted.captures[1]
    p0c_database.engine.dispose()
    with p0c_database.engine.connect() as connection:
        exact = ValueRepository(
            connection, p0c_database.project_tables
        ).get_exact(
            p0c_database.scope,
            capture.snapshot_value_ref.value_id,
            expected_revision=1,
            expected_incarnation=(
                f"p0c:{submission_command().submission_id}:"
                f"{capture.snapshot_value_ref.value_id}"
            ),
            expected_digest=capture.snapshot_value_ref.content_digest,
        )
    assert exact == capture.observation.exact_bytes
    assert hashlib.sha256(exact).hexdigest() == SEED_CONTENT_SHA256[102]
