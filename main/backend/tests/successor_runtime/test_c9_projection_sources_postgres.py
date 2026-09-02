"""Disposable PostgreSQL evidence for the C9 pure-source effect adapter."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import NullPool

from app.successor_runtime.capabilities.checksum import sha256_hex
from app.successor_runtime.research.codec import canonical_bytes
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
from app.successor_runtime.substrate.postgres.c9_projection_sources import (
    C7_SEARCH_SOURCE_OBJECT_TYPE,
    RESEARCH_GRAPH_SOURCE_OBJECT_TYPE,
    RUNTIME_SESSION_SOURCE_OBJECT_TYPE,
    C9SourceClosureDriftError,
    C9SourceDuplicateComponentError,
    C9SourceEventGapError,
    C9SourceMissingRowError,
    C9SourceProvenanceDriftError,
    C9SourceStaleClosureError,
    C9SourceTypeDriftError,
    C9SourceUnavailableError,
    C9SourceValueConflictError,
    build_semantic_source_closure,
    load_exact_semantic_source_closure,
    put_semantic_source_rows,
    read_c7_search_source,
    read_research_graph_source,
    read_runtime_session_source,
)
from app.successor_runtime.substrate.postgres.ingest_c7_candidate_values import (
    C7_STRUCTURED_VALUE_CODEC_ID,
    C7_STRUCTURED_VALUE_OBJECT_TYPE,
    C7_STRUCTURED_VALUE_STATE,
)
from app.successor_runtime.substrate.postgres.ingest_c7_movement_admission import (
    C7_MOVEMENT_CANONICAL_DOCUMENTS,
)
from app.successor_runtime.substrate.postgres.models import (
    PUBLIC_METADATA,
    PUBLIC_TABLES,
    project_tables,
)
from app.successor_runtime.substrate.postgres.session import compute_scope_digest
from app.successor_runtime.substrate.projections import c9_sources as c9

pytestmark = pytest.mark.integration

DATABASE_NAME = "mrw_c9_projection_sources_test"
DATABASE_ENV = "SUCCESSOR_TEST_DATABASE_URL"
PROJECT_KEY = "c9-projection-sources"
MISSING_PROJECT_KEY = "c9-missing-project"
PROJECT_SCHEMA = "mrw_c9_projection_sources"
REGISTRY_REVISION = 1
SCOPE_INCARNATION = "scope-inc-c9"
SCOPE_DIGEST = compute_scope_digest(
    PROJECT_KEY,
    PROJECT_SCHEMA,
    REGISTRY_REVISION,
    SCOPE_INCARNATION,
)
MISSING_SCOPE_DIGEST = compute_scope_digest(
    MISSING_PROJECT_KEY,
    PROJECT_SCHEMA,
    REGISTRY_REVISION,
    "scope-inc-missing",
)
ACTOR = "actor:c9-projection-sources"
RUN_ID = "run:c9-projection-sources"
PROGRAM_ID = "program:c9-projection-sources"
PLAN_ID = "plan:c9-projection-sources"
NOW = datetime(2030, 9, 1, 8, 0, tzinfo=UTC)


def _digest(label: str) -> str:
    return sha256_hex(bytes(label, "utf-8"))


def _scope(
    *,
    project_key: str = PROJECT_KEY,
    scope_digest: str = SCOPE_DIGEST,
    incarnation: str = SCOPE_INCARNATION,
) -> RuntimeScope:
    return RuntimeScope(
        project_scope=ProjectScopeRef(
            project_key=project_key,
            resolved_schema=PROJECT_SCHEMA,
            project_registry_revision=REGISTRY_REVISION,
            incarnation=incarnation,
            scope_digest=scope_digest,
        ),
        actor_id=ACTOR,
    )


def _server_url() -> str:
    env_url = os.environ.get(DATABASE_ENV)
    if env_url:
        url = make_url(env_url)
        return url.set(database="postgres").render_as_string(hide_password=False)
    return "postgresql+psycopg2://localhost/postgres"


def _assert_database_absent(server: Engine) -> None:
    with server.connect() as connection:
        row = connection.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :database_name"),
            {"database_name": DATABASE_NAME},
        ).scalar_one_or_none()
        assert row is None


def _create_database() -> Engine:
    server = sa.create_engine(
        _server_url(), isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    try:
        with server.connect() as connection:
            connection.execute(
                text("DROP DATABASE IF EXISTS " + DATABASE_NAME + " WITH (FORCE)")
            )
            connection.execute(text("CREATE DATABASE " + DATABASE_NAME))
    except Exception as exc:  # noqa: BLE001 - environment-dependent skip
        server.dispose()
        pytest.skip(f"cannot create disposable database {DATABASE_NAME}: {exc}")
    return server


def _drop_database(server: Engine) -> None:
    try:
        with server.connect() as connection:
            connection.execute(
                text("DROP DATABASE IF EXISTS " + DATABASE_NAME + " WITH (FORCE)")
            )
        _assert_database_absent(server)
    finally:
        server.dispose()


@pytest.fixture(scope="module")
def disposable_database() -> Iterator[Engine]:
    server = _create_database()
    engine = sa.create_engine(
        make_url(_server_url())
        .set(database=DATABASE_NAME)
        .render_as_string(hide_password=False),
        poolclass=NullPool,
    )
    project_metadata = sa.MetaData()
    project_tables(project_metadata, PROJECT_SCHEMA)
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{PROJECT_SCHEMA}"'))
            PUBLIC_METADATA.create_all(connection)
            project_metadata.create_all(connection)
            C7_MOVEMENT_CANONICAL_DOCUMENTS.create(connection)
        yield engine
    finally:
        engine.dispose()
        _drop_database(server)


def _reset(engine: Engine) -> None:
    public_names = (
        "runtime_events",
        "runtime_steps",
        "runtime_runs",
        "runtime_plan_refs",
        "runtime_program_refs",
        "project_scope_registry",
    )
    project_metadata = sa.MetaData()
    project = project_tables(project_metadata, PROJECT_SCHEMA)
    project_names = (
        "successor_values",
        "research_relations",
        "research_objects",
        "research_owner_bindings",
        "research_program_specs",
        "research_execution_plans",
        "successor_receipts",
    )
    qualified = (
        ", ".join(f'"public"."{name}"' for name in public_names)
        + ", "
        + ", ".join(f'"{PROJECT_SCHEMA}"."{name}"' for name in project_names)
    )
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE TABLE {qualified} RESTART IDENTITY CASCADE"))
        connection.execute(
            text("TRUNCATE TABLE public.c7_movement_canonical_documents")
        )
        _seed_base(connection, project)


@pytest.fixture(autouse=True)
def clean_database(disposable_database: Engine) -> Iterator[None]:
    _reset(disposable_database)
    yield


def _seed_runtime_project(
    connection: sa.Connection,
    *,
    project_key: str,
    run_id: str,
    scope_digest: str,
) -> None:
    connection.execute(
        PUBLIC_TABLES["project_scope_registry"]
        .insert()
        .values(
            project_key=project_key,
            registry_revision=REGISTRY_REVISION,
            resolved_schema=PROJECT_SCHEMA,
            scope_digest=scope_digest,
            incarnation=SCOPE_INCARNATION
            if project_key == PROJECT_KEY
            else "scope-inc-missing",
            state="ACTIVE",
            updated_by=ACTOR,
            approval_ref=f"approval:{project_key}",
            created_at=NOW,
            updated_at=NOW,
        )
    )
    program_id = f"program:{project_key}"
    plan_id = f"plan:{project_key}"
    connection.execute(
        PUBLIC_TABLES["runtime_program_refs"]
        .insert()
        .values(
            program_id=program_id,
            project_key=project_key,
            program_digest=_digest(f"{project_key}:program"),
            project_storage_ref=f"value:{program_id}",
            contract_version="mrw.successor.program.v1",
            created_at=NOW,
            updated_at=NOW,
        )
    )
    connection.execute(
        PUBLIC_TABLES["runtime_plan_refs"]
        .insert()
        .values(
            plan_id=plan_id,
            project_key=project_key,
            plan_digest=_digest(f"{project_key}:plan"),
            program_id=program_id,
            program_digest=_digest(f"{project_key}:program"),
            project_storage_ref=f"value:{plan_id}",
            compiler_id="compiler:c9",
            compiler_version="1",
            operation_catalog_id="catalog:c9",
            catalog_version="1",
            catalog_digest=_digest("catalog"),
            effect_closure_digest=_digest("effect-closure"),
            authority_closure_digest=_digest("authority-closure"),
            resource_closure_digest=_digest("resource-closure"),
            created_at=NOW,
            updated_at=NOW,
        )
    )
    connection.execute(
        PUBLIC_TABLES["runtime_runs"]
        .insert()
        .values(
            run_id=run_id,
            project_key=project_key,
            project_registry_revision=REGISTRY_REVISION,
            project_scope_digest=scope_digest,
            resolved_schema=PROJECT_SCHEMA,
            program_id=program_id,
            program_digest=_digest(f"{project_key}:program"),
            plan_id=plan_id,
            plan_digest=_digest(f"{project_key}:plan"),
            state="READY",
            revision=0,
            next_event_seq=3,
            execution_epoch=0,
            incarnation="run-inc:c9-projection-sources",
            submission_authority_digest=_digest("submission-authority"),
            qualification_digest=_digest("qualification"),
            cancellation_requested=False,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    for seq, event_kind in (
        (1, c9.SESSION_CREATED),
        (2, c9.SESSION_PROJECTION_REFRESHED),
    ):
        connection.execute(
            PUBLIC_TABLES["runtime_events"]
            .insert()
            .values(
                project_key=project_key,
                run_id=run_id,
                seq=seq,
                event_type=event_kind,
                schema_version="mrw.runtime.event.v1",
                step_id="step:1",
                attempt_id=None,
                event_metadata_json={"kind": event_kind},
                payload_ref=f"value:event:{seq}",
                payload_digest=_digest(f"{project_key}:event:{seq}"),
                authority_digest=_digest(f"{project_key}:authority:{seq}"),
                created_at=NOW,
                updated_at=NOW,
            )
        )


def _seed_base(connection: sa.Connection, project: Any) -> None:
    _seed_runtime_project(
        connection,
        project_key=PROJECT_KEY,
        run_id=RUN_ID,
        scope_digest=SCOPE_DIGEST,
    )
    for step_id in ("step:1", "step:2"):
        connection.execute(
            PUBLIC_TABLES["runtime_steps"]
            .insert()
            .values(
                project_key=PROJECT_KEY,
                run_id=RUN_ID,
                step_id=step_id,
                operation_id="op.c9.projection",
                operation_kind="op.c9.projection.v1",
                operation_version="1.0.0",
                state="SUCCEEDED",
                revision=int(step_id[-1]),
                execution_epoch=1,
                input_digest=_digest(f"input:{step_id}"),
                output_digest=_digest(f"output:{step_id}"),
                failure_digest=None,
                effect_class="EFFECTFUL",
                resource_class="CPU_LIGHT",
                concurrency_key="c9:read",
                capability_id="capability:successor-runtime:c9",
                claim_owner="successor",
                claim_authority_epoch=1,
                claim_policy_digest=_digest("claim-policy"),
                attempt_count=0,
                max_attempts=1,
                created_at=NOW,
                updated_at=NOW,
            )
        )
    for index in (1, 2):
        connection.execute(
            project.research_objects.insert().values(
                project_key=PROJECT_KEY,
                object_id=f"object:{index}",
                object_type="research_note",
                revision=index,
                incarnation=f"object-inc:{index}",
                lifecycle_state="ADMITTED",
                owner_binding_ref=f"owner:object:{index}",
                content_ref=f"content:object:{index}",
                content_digest=_digest(f"object:{index}"),
                provenance_closure_digest=_digest(f"object-provenance:{index}"),
                created_at=NOW,
                updated_at=NOW,
            )
        )
    connection.execute(
        project.research_relations.insert().values(
            project_key=PROJECT_KEY,
            relation_id="relation:1",
            relation_type="cites",
            source_object_ref="object:1",
            target_object_ref="object:2",
            direction="forward",
            scope_ref="scope:c9",
            uncertainty_profile_ref="uncertainty:c9",
            validity_json={},
            provenance_closure_digest=_digest("relation-provenance"),
            revision=1,
            incarnation="relation-inc:1",
            state="ACTIVE",
            created_at=NOW,
            updated_at=NOW,
        )
    )
    c7_values = {}
    for index in (1, 2):
        candidate_id = f"candidate:c7:{index}"
        structured_payload = {
            "schema_version": "mrw.successor.c7.structured-payload.v1",
            "source_locator": f"https://example.invalid/c7-{index}",
            "source_domain": "example.invalid",
            "language": "zh",
            "title": f"C7 searchable title {index}",
            "summary": f"C7 searchable summary body {index}",
            "effective_time": "2026-09-01T08:00:00Z",
            "text": f"C7 full searchable text {index}",
            "nested": {"body": f"nested searchable body {index}"},
        }
        value_id = f"c7:structured:{candidate_id}"
        value_ref = f"project-value:{value_id}"
        value_digest = sha256_hex(canonical_bytes(structured_payload))
        provenance_closure_digest = _digest(f"c7-provenance:{index}")
        value_incarnation = f"c7:structured:{candidate_id}"
        byte_size = len(canonical_bytes(structured_payload))
        connection.execute(
            project.successor_values.insert().values(
                project_key=PROJECT_KEY,
                value_id=value_id,
                object_type=C7_STRUCTURED_VALUE_OBJECT_TYPE,
                codec_id=C7_STRUCTURED_VALUE_CODEC_ID,
                content_digest=value_digest,
                byte_size=byte_size,
                content_json=structured_payload,
                source_ref=f"snapshot:c7:{index}",
                provenance_json={
                    "provenance_closure_digest": provenance_closure_digest
                },
                provenance_digest=provenance_closure_digest,
                state=C7_STRUCTURED_VALUE_STATE,
                revision=1,
                incarnation=value_incarnation,
                write_intent_digest=_digest(f"c7-write-intent:{index}"),
                created_at=NOW,
                updated_at=NOW,
            )
        )
        c7_values[index] = {
            "candidate_id": candidate_id,
            "value_ref": value_ref,
            "value_revision": 1,
            "value_incarnation": value_incarnation,
            "value_digest": value_digest,
            "value_provenance_digest": provenance_closure_digest,
        }
    for index in (1, 2):
        value = c7_values[index]
        values = {
            "project_key": PROJECT_KEY,
            "object_id": f"c7-document:{index}",
            "commit_intent_id": f"commit:c7:{index}",
            "canonical_owner": "document.canonical.v1",
            "run_id": RUN_ID,
            "step_id": "step:1",
            "attempt_id": f"attempt:c7:{index}",
            "capability_id": "ingest_index.c7.v2.verify_admit",
            "actor_id": ACTOR,
            "program_digest": _digest("program"),
            "plan_digest": _digest("plan"),
            "step_revision": 1,
            "attempt_revision": 1,
            "execution_epoch": 1,
            "attempt_incarnation": f"attempt-inc:{index}",
            "assignment_digest": _digest(f"assignment:{index}"),
            "handler_binding_digest": _digest(f"handler-binding:{index}"),
            "handler_realization_digest": _digest(f"handler-realization:{index}"),
            "input_closure_digest": _digest(f"input-closure:{index}"),
            "revision": index,
            "incarnation": f"document-inc:{index}",
            "expected_base_revision": 0,
            "expected_base_incarnation": "base-inc:0",
            "content_digest": _digest(f"content:{index}"),
            "snapshot_identity_digest": _digest(f"snapshot-identity:{index}"),
            "raw_content_digest": _digest(f"raw-content:{index}"),
            "envelope_digest": _digest(f"envelope:{index}"),
            "payload_content_digest": _digest(f"payload-content:{index}"),
            "ordered_source_closure_digest": _digest(f"source-closure:{index}"),
            "provenance_closure_digest": _digest(f"provenance:{index}"),
            "decision_digest": _digest(f"decision:{index}"),
            "candidate_digest": _digest(f"candidate:{index}"),
            "candidate_verification_digest": _digest(f"candidate-verification:{index}"),
            "ordered_event_closure_digest": _digest(f"event-closure:{index}"),
            "verification_digest": _digest(f"verification:{index}"),
            "authority_digest": _digest(f"authority:{index}"),
            "authority_epoch": 1,
            "candidate_id": value["candidate_id"],
            "snapshot_ref": f"snapshot:c7:{index}",
            "alternative": "EXTRACT",
            "verification_profile_ref": "mrw.successor.ingest-c7.verification.profile.v1",
            "verification_receipt": f"receipt:c7:{index}",
            "evidence_digest": _digest(f"evidence:{index}"),
            "provenance_digest": _digest(f"provenance:{index}"),
            "candidate_receipt_digest": _digest(f"candidate-receipt:{index}"),
            "value_ref": value["value_ref"],
            "value_revision": value["value_revision"],
            "value_incarnation": value["value_incarnation"],
            "value_digest": value["value_digest"],
            "value_provenance_digest": value["value_provenance_digest"],
            "canonical_commit_ref": f"commit:c7:{index}",
            "receipt_digest": _digest(f"receipt:{index}"),
            "head_closure_digest": _digest(f"head-closure:{index}"),
        }
        connection.execute(C7_MOVEMENT_CANONICAL_DOCUMENTS.insert().values(**values))


def _assert_exact_closure(closure: c9.C9SemanticSourceClosureV1) -> None:
    assert isinstance(closure, c9.C9SemanticSourceClosureV1)
    assert isinstance(closure.runtime_session_source, c9.RuntimeSessionSourceV1)
    assert isinstance(closure.research_graph_source, c9.ResearchGraphSourceV1)
    assert isinstance(closure.c7_search_source, c9.C7SearchSourceV1)
    assert len(closure.closure_digest) == 64
    for source in (
        closure.runtime_session_source,
        closure.research_graph_source,
        closure.c7_search_source,
    ):
        assert len(source.source_digest) == 64
        assert source.project_scope_ref == closure.project_scope_ref
        assert source.revision == closure.revision
        assert source.incarnation == closure.incarnation


def test_build_semantic_source_closure_exact_three_typed_rows(
    disposable_database: Engine,
) -> None:
    with disposable_database.connect() as connection:
        closure = build_semantic_source_closure(connection, _scope())
    _assert_exact_closure(closure)
    assert len(closure.runtime_session_source.events) == 2
    assert closure.runtime_session_source.events[0].event_kind == c9.SESSION_CREATED
    assert (
        closure.runtime_session_source.events[1].event_kind
        == c9.SESSION_PROJECTION_REFRESHED
    )
    assert closure.runtime_session_source.session_ref == f"run:{RUN_ID}"
    assert {obj.object_id for obj in closure.research_graph_source.objects} == {
        "object:1",
        "object:2",
    }
    assert closure.research_graph_source.relations[0].source_object_id == "object:1"
    assert {segment.segment_id for segment in closure.c7_search_source.segments} == {
        "document:c7-document:1:structured_payload.text",
        "document:c7-document:2:structured_payload.text",
        "document:c7-document:1:structured_payload.title",
        "document:c7-document:2:structured_payload.title",
        "document:c7-document:1:structured_payload.summary",
        "document:c7-document:2:structured_payload.summary",
        "document:c7-document:1:structured_payload.language",
        "document:c7-document:2:structured_payload.language",
        "document:c7-document:1:structured_payload.source_domain",
        "document:c7-document:2:structured_payload.source_domain",
        "document:c7-document:1:structured_payload.effective_time",
        "document:c7-document:2:structured_payload.effective_time",
        "document:c7-document:1:structured_payload.nested.body",
        "document:c7-document:2:structured_payload.nested.body",
    }
    assert any(
        segment.segment_text == "C7 full searchable text 1"
        and segment.field_path == "structured_payload.text"
        for segment in closure.c7_search_source.segments
    )
    assert all(
        "snapshot:c7:" not in segment.segment_text
        and "content_digest" not in segment.field_path
        for segment in closure.c7_search_source.segments
    )
    assert all(
        segment.provider_status == c9.NOT_EXECUTED
        and segment.vectorization_status == c9.NOT_EXECUTED
        for segment in closure.c7_search_source.segments
    )


def test_readers_return_pure_types_and_source_digest_changes_on_tamper(
    disposable_database: Engine,
) -> None:
    with disposable_database.connect() as connection:
        scope = _scope()
        runtime_source = read_runtime_session_source(connection, scope)
        graph_source = read_research_graph_source(connection, scope)
        c7_source = read_c7_search_source(connection, scope)
        assert isinstance(runtime_source, c9.RuntimeSessionSourceV1)
        assert isinstance(graph_source, c9.ResearchGraphSourceV1)
        assert isinstance(c7_source, c9.C7SearchSourceV1)
        before = runtime_source.source_digest
    with disposable_database.begin() as connection:
        connection.execute(
            sa.update(PUBLIC_TABLES["runtime_events"])
            .where(
                PUBLIC_TABLES["runtime_events"].c.project_key == PROJECT_KEY,
                PUBLIC_TABLES["runtime_events"].c.seq == 1,
            )
            .values(payload_digest=_digest("tampered-event"))
        )
        after = read_runtime_session_source(connection, scope).source_digest
    assert before != after


def test_put_load_roundtrip_and_same_closure_no_change(
    disposable_database: Engine,
) -> None:
    with disposable_database.begin() as connection:
        closure = build_semantic_source_closure(connection, _scope())
        first = put_semantic_source_rows(connection, _scope(), closure)
    assert first.changed is True
    assert len(first.value_ids) == 3
    assert len(set(first.value_ids)) == 3
    with disposable_database.connect() as connection:
        loaded = load_exact_semantic_source_closure(connection, _scope())
    assert loaded == closure
    assert loaded.closure_digest == closure.closure_digest
    with disposable_database.begin() as connection:
        second = put_semantic_source_rows(connection, _scope(), closure)
    assert second.changed is False
    assert second.closure_digest == closure.closure_digest


def test_pure_builders_consume_closure_sources_directly(
    disposable_database: Engine,
) -> None:
    with disposable_database.connect() as connection:
        closure = build_semantic_source_closure(connection, _scope())
    session_payload = c9.build_agent_session_payload(
        closure.runtime_session_source,
        declared_losses=(
            c9.ProjectionFieldLossV1(
                schema_version=c9.PROJECTION_FIELD_LOSS_SCHEMA,
                field_path="events.terminal_ref",
                loss_kind=c9.LOSS_KIND_NOT_EXECUTED,
                reason="bounded local projection",
            ),
        ),
    )
    graph_payload = c9.build_research_graph_payload(
        closure.research_graph_source,
        declared_losses=(
            c9.ProjectionFieldLossV1(
                schema_version=c9.PROJECTION_FIELD_LOSS_SCHEMA,
                field_path="objects.label",
                loss_kind=c9.LOSS_KIND_DECLARED,
                reason="bounded labels",
            ),
        ),
    )
    search_payload = c9.build_search_payload(
        closure.c7_search_source,
        declared_losses=(
            c9.ProjectionFieldLossV1(
                schema_version=c9.PROJECTION_FIELD_LOSS_SCHEMA,
                field_path="segments.text",
                loss_kind=c9.LOSS_KIND_OMITTED_FIELD,
                reason="bounded segments",
            ),
        ),
    )
    assert session_payload.session_ref == f"run:{RUN_ID}"
    assert graph_payload.graph_ref == f"project:{PROJECT_KEY}:research-graph"
    assert search_payload.search_ref == f"project:{PROJECT_KEY}:c7-search"
    assert all(
        len(payload.payload_digest) == 64
        for payload in (
            session_payload,
            graph_payload,
            search_payload,
        )
    )


def test_put_writes_three_typed_rows_without_duplicate_canonical_owner(
    disposable_database: Engine,
) -> None:
    project_metadata = sa.MetaData()
    project = project_tables(project_metadata, PROJECT_SCHEMA)
    with disposable_database.begin() as connection:
        closure = build_semantic_source_closure(connection, _scope())
        put_semantic_source_rows(connection, _scope(), closure)
        rows = (
            connection.execute(
                sa.select(project.successor_values).where(
                    project.successor_values.c.project_key == PROJECT_KEY
                )
            )
            .mappings()
            .all()
        )
    c9_rows = [
        row
        for row in rows
        if str(row["source_ref"]) == f"c9:semantic-source:{PROJECT_KEY}"
    ]
    assert len(c9_rows) == 3
    assert {str(row["object_type"]) for row in c9_rows} == {
        RUNTIME_SESSION_SOURCE_OBJECT_TYPE,
        RESEARCH_GRAPH_SOURCE_OBJECT_TYPE,
        C7_SEARCH_SOURCE_OBJECT_TYPE,
    }
    assert len({str(row["value_id"]) for row in c9_rows}) == 3


def test_missing_c7_searchable_content_is_unavailable_without_fabrication(
    disposable_database: Engine,
) -> None:
    scope = _scope(
        project_key=MISSING_PROJECT_KEY,
        scope_digest=MISSING_SCOPE_DIGEST,
        incarnation="scope-inc-missing",
    )
    with disposable_database.begin() as connection:
        _seed_runtime_project(
            connection,
            project_key=MISSING_PROJECT_KEY,
            run_id=f"run:{MISSING_PROJECT_KEY}",
            scope_digest=MISSING_SCOPE_DIGEST,
        )
        graph = read_research_graph_source(connection, scope)
        assert graph.objects == ()
        assert graph.relations == ()
        with pytest.raises(C9SourceUnavailableError):
            read_c7_search_source(connection, scope)
        with pytest.raises(C9SourceUnavailableError):
            build_semantic_source_closure(connection, scope)


def test_event_gap_fails_closed(disposable_database: Engine) -> None:
    with disposable_database.begin() as connection:
        connection.execute(
            PUBLIC_TABLES["runtime_events"]
            .insert()
            .values(
                project_key=PROJECT_KEY,
                run_id=RUN_ID,
                seq=4,
                event_type=c9.SESSION_PROJECTION_REFRESHED,
                schema_version="mrw.runtime.event.v1",
                step_id="step:1",
                attempt_id=None,
                event_metadata_json={},
                payload_ref="value:event:4",
                payload_digest=_digest("event:4"),
                authority_digest=_digest("authority:4"),
                created_at=NOW,
                updated_at=NOW,
            )
        )
        with pytest.raises(C9SourceEventGapError):
            read_runtime_session_source(connection, _scope())


def test_duplicate_component_fails_closed(disposable_database: Engine) -> None:
    project_metadata = sa.MetaData()
    project = project_tables(project_metadata, PROJECT_SCHEMA)
    with disposable_database.begin() as connection:
        connection.execute(
            project.research_objects.insert().values(
                project_key=PROJECT_KEY,
                object_id="object:1",
                object_type="research_note",
                revision=99,
                incarnation="object-inc:dup",
                lifecycle_state="ADMITTED",
                owner_binding_ref="owner:dup",
                content_ref="content:dup",
                content_digest=_digest("dup"),
                provenance_closure_digest=_digest("dup-provenance"),
                created_at=NOW,
                updated_at=NOW,
            )
        )
        with pytest.raises(C9SourceDuplicateComponentError):
            read_research_graph_source(connection, _scope())


def test_wrong_persisted_type_fails_closed(disposable_database: Engine) -> None:
    project_metadata = sa.MetaData()
    project = project_tables(project_metadata, PROJECT_SCHEMA)
    with disposable_database.begin() as connection:
        closure = build_semantic_source_closure(connection, _scope())
        persisted = put_semantic_source_rows(connection, _scope(), closure)
        runtime_session_value_id = persisted.value_ids[0]
        connection.execute(
            sa.update(project.successor_values)
            .where(
                project.successor_values.c.project_key == PROJECT_KEY,
                project.successor_values.c.value_id == runtime_session_value_id,
            )
            .values(object_type="legacy.wrong.type")
        )
        with pytest.raises(C9SourceTypeDriftError):
            load_exact_semantic_source_closure(connection, _scope())


def test_source_tamper_changes_closure_and_load_fails_closed(
    disposable_database: Engine,
) -> None:
    with disposable_database.begin() as connection:
        scope = _scope()
        closure = build_semantic_source_closure(connection, scope)
        put_semantic_source_rows(connection, scope, closure)
        connection.execute(
            sa.update(PUBLIC_TABLES["runtime_events"])
            .where(
                PUBLIC_TABLES["runtime_events"].c.project_key == PROJECT_KEY,
                PUBLIC_TABLES["runtime_events"].c.seq == 1,
            )
            .values(payload_digest=_digest("tampered-event"))
        )
        tampered = build_semantic_source_closure(connection, scope)
    assert tampered.closure_digest != closure.closure_digest
    with disposable_database.connect() as connection:
        with pytest.raises(C9SourceClosureDriftError):
            load_exact_semantic_source_closure(connection, _scope())
        with pytest.raises(C9SourceValueConflictError):
            put_semantic_source_rows(connection, _scope(), tampered)


def test_c7_value_tamper_fails_head_value_binding(
    disposable_database: Engine,
) -> None:
    project_metadata = sa.MetaData()
    project = project_tables(project_metadata, PROJECT_SCHEMA)
    with disposable_database.begin() as connection:
        connection.execute(
            sa.update(project.successor_values)
            .where(
                project.successor_values.c.project_key == PROJECT_KEY,
                project.successor_values.c.value_id == "c7:structured:candidate:c7:1",
            )
            .values(
                content_json={
                    "text": "tampered search text",
                }
            )
        )
        with pytest.raises(C9SourceClosureDriftError):
            read_c7_search_source(connection, _scope())


def test_c7_missing_value_and_stale_head_fail_closed(
    disposable_database: Engine,
) -> None:
    project_metadata = sa.MetaData()
    project = project_tables(project_metadata, PROJECT_SCHEMA)
    with disposable_database.begin() as connection:
        connection.execute(
            sa.delete(project.successor_values).where(
                project.successor_values.c.project_key == PROJECT_KEY,
                project.successor_values.c.value_id == "c7:structured:candidate:c7:2",
            )
        )
        with pytest.raises(C9SourceMissingRowError):
            read_c7_search_source(connection, _scope())
    with disposable_database.begin() as connection:
        connection.execute(
            sa.update(C7_MOVEMENT_CANONICAL_DOCUMENTS)
            .where(
                C7_MOVEMENT_CANONICAL_DOCUMENTS.c.project_key == PROJECT_KEY,
                C7_MOVEMENT_CANONICAL_DOCUMENTS.c.object_id == "c7-document:1",
            )
            .values(value_revision=99)
        )
        with pytest.raises(C9SourceProvenanceDriftError):
            read_c7_search_source(connection, _scope())


def test_missing_persisted_row_fails_closed(disposable_database: Engine) -> None:
    project_metadata = sa.MetaData()
    project = project_tables(project_metadata, PROJECT_SCHEMA)
    with disposable_database.begin() as connection:
        closure = build_semantic_source_closure(connection, _scope())
        persisted = put_semantic_source_rows(connection, _scope(), closure)
        c7_search_value_id = persisted.value_ids[2]
        connection.execute(
            sa.delete(project.successor_values).where(
                project.successor_values.c.project_key == PROJECT_KEY,
                project.successor_values.c.value_id == c7_search_value_id,
            )
        )
        with pytest.raises(C9SourceMissingRowError):
            load_exact_semantic_source_closure(connection, _scope())


def test_stored_incarnation_drift_fails_closed(disposable_database: Engine) -> None:
    project_metadata = sa.MetaData()
    project = project_tables(project_metadata, PROJECT_SCHEMA)
    with disposable_database.begin() as connection:
        closure = build_semantic_source_closure(connection, _scope())
        put_semantic_source_rows(connection, _scope(), closure)
        connection.execute(
            sa.update(project.successor_values)
            .where(project.successor_values.c.project_key == PROJECT_KEY)
            .values(incarnation="stale-incarnation")
        )
        with pytest.raises(C9SourceStaleClosureError):
            load_exact_semantic_source_closure(connection, _scope())


def test_provenance_drift_fails_closed(disposable_database: Engine) -> None:
    project_metadata = sa.MetaData()
    project = project_tables(project_metadata, PROJECT_SCHEMA)
    with disposable_database.begin() as connection:
        closure = build_semantic_source_closure(connection, _scope())
        persisted = put_semantic_source_rows(connection, _scope(), closure)
        runtime_session_value_id = persisted.value_ids[0]
        stored = (
            connection.execute(
                sa.select(project.successor_values).where(
                    project.successor_values.c.project_key == PROJECT_KEY,
                    project.successor_values.c.value_id == runtime_session_value_id,
                )
            )
            .mappings()
            .one()
        )
        original = dict(stored["provenance_json"])
        connection.execute(
            sa.update(project.successor_values)
            .where(project.successor_values.c.project_key == PROJECT_KEY)
            .values(
                provenance_json={
                    "closure_digest": original["closure_digest"],
                    "source_ref": "drifted",
                    "incarnation": original["incarnation"],
                    "source_kind": "runtime_session",
                }
            )
        )
        with pytest.raises(C9SourceProvenanceDriftError):
            load_exact_semantic_source_closure(connection, _scope())


def test_legacy_tables_are_never_sources(disposable_database: Engine) -> None:
    legacy_metadata = sa.MetaData(schema=PROJECT_SCHEMA)
    legacy_sources = sa.Table(
        "sources",
        legacy_metadata,
        sa.Column("project_key", sa.String(128), primary_key=True),
        sa.Column("source_id", sa.String(128), primary_key=True),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("payload_json", sa.dialects.postgresql.JSONB, nullable=True),
    )
    legacy_documents = sa.Table(
        "documents",
        legacy_metadata,
        sa.Column("project_key", sa.String(128), primary_key=True),
        sa.Column("document_id", sa.String(128), primary_key=True),
        sa.Column("content_digest", sa.String(64), nullable=False),
    )
    with disposable_database.begin() as connection:
        legacy_metadata.create_all(connection, checkfirst=True)
        baseline = build_semantic_source_closure(connection, _scope())
        connection.execute(
            legacy_sources.insert().values(
                project_key=PROJECT_KEY,
                source_id="legacy-source:1",
                content_digest=_digest("legacy-source"),
                payload_json={"legacy": True},
            )
        )
        connection.execute(
            legacy_documents.insert().values(
                project_key=PROJECT_KEY,
                document_id="legacy-document:1",
                content_digest=_digest("legacy-document"),
            )
        )
        after = build_semantic_source_closure(connection, _scope())
    assert after == baseline


def test_teardown_drops_disposable_database() -> None:
    server = sa.create_engine(
        _server_url(), isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    try:
        with server.connect() as connection:
            connection.execute(
                text("DROP DATABASE IF EXISTS " + DATABASE_NAME + " WITH (FORCE)")
            )
        _assert_database_absent(server)
    finally:
        server.dispose()
