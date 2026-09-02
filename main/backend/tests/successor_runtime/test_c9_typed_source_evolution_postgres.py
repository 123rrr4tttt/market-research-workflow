"""C9 typed semantic-source evolution regression (exclusive disposable DB).

Covers the P0 fix contract: immutable content/revision/incarnation-bound value
rows, an immutable per-closure manifest, and the canonical project-scoped
current-closure pointer in ``runtime_projection_offsets``.  Legal Research
Ledger advances write new versions; same-closure puts are idempotent; old
versions stay immutable and auditable; ABA reversion, payload tamper and
cross-scope reads/writes fail closed.
"""

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
    C9_CLOSURE_MANIFEST_OBJECT_TYPE,
    C9_TYPED_SOURCE_PROJECTOR_ID,
    C9SourceClosureDriftError,
    C9SourceMissingRowError,
    C9SourceProvenanceDriftError,
    C9SourceValueConflictError,
    build_semantic_source_closure,
    load_exact_semantic_source_closure,
    put_semantic_source_rows,
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

DATABASE_NAME = "mrw_c9_typed_source_evolution_test"
DATABASE_ENV = "SUCCESSOR_TEST_DATABASE_URL"
PROJECT_KEY = "c9-typed-source-evolution"
OTHER_PROJECT_KEY = "c9-typed-source-other"
PROJECT_SCHEMA = "mrw_c9_typed_source_evolution"
OTHER_PROJECT_SCHEMA = "mrw_c9_typed_source_evolution_other"
REGISTRY_REVISION = 1
SCOPE_INCARNATION = "scope-inc-c9-typed"
OTHER_INCARNATION = "scope-inc-c9-typed-other"
SCOPE_DIGEST = compute_scope_digest(
    PROJECT_KEY,
    PROJECT_SCHEMA,
    REGISTRY_REVISION,
    SCOPE_INCARNATION,
)
OTHER_SCOPE_DIGEST = compute_scope_digest(
    OTHER_PROJECT_KEY,
    OTHER_PROJECT_SCHEMA,
    REGISTRY_REVISION,
    OTHER_INCARNATION,
)
ACTOR = "actor:c9-typed-source-evolution"
RUN_ID = "run:c9-typed-source-evolution"
NOW = datetime(2030, 9, 1, 8, 0, tzinfo=UTC)


def _digest(label: str) -> str:
    return sha256_hex(bytes(label, "utf-8"))


def _scope(
    *,
    project_key: str = PROJECT_KEY,
    scope_digest: str = SCOPE_DIGEST,
    incarnation: str = SCOPE_INCARNATION,
    resolved_schema: str = PROJECT_SCHEMA,
) -> RuntimeScope:
    return RuntimeScope(
        project_scope=ProjectScopeRef(
            project_key=project_key,
            resolved_schema=resolved_schema,
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


def _seed_runtime_project(
    connection: sa.Connection,
    *,
    revision: int = 0,
    event_count: int = 2,
) -> None:
    connection.execute(
        PUBLIC_TABLES["project_scope_registry"]
        .insert()
        .values(
            project_key=PROJECT_KEY,
            registry_revision=REGISTRY_REVISION,
            resolved_schema=PROJECT_SCHEMA,
            scope_digest=SCOPE_DIGEST,
            incarnation=SCOPE_INCARNATION,
            state="ACTIVE",
            updated_by=ACTOR,
            approval_ref=f"approval:{PROJECT_KEY}",
            created_at=NOW,
            updated_at=NOW,
        )
    )
    program_id = f"program:{PROJECT_KEY}"
    plan_id = f"plan:{PROJECT_KEY}"
    connection.execute(
        PUBLIC_TABLES["runtime_program_refs"]
        .insert()
        .values(
            program_id=program_id,
            project_key=PROJECT_KEY,
            program_digest=_digest(f"{PROJECT_KEY}:program"),
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
            project_key=PROJECT_KEY,
            plan_digest=_digest(f"{PROJECT_KEY}:plan"),
            program_id=program_id,
            program_digest=_digest(f"{PROJECT_KEY}:program"),
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
            run_id=RUN_ID,
            project_key=PROJECT_KEY,
            project_registry_revision=REGISTRY_REVISION,
            project_scope_digest=SCOPE_DIGEST,
            resolved_schema=PROJECT_SCHEMA,
            program_id=program_id,
            program_digest=_digest(f"{PROJECT_KEY}:program"),
            plan_id=plan_id,
            plan_digest=_digest(f"{PROJECT_KEY}:plan"),
            state="READY",
            revision=revision,
            next_event_seq=event_count + 1,
            execution_epoch=0,
            incarnation="run-inc:c9-typed-source-evolution",
            submission_authority_digest=_digest("submission-authority"),
            qualification_digest=_digest("qualification"),
            cancellation_requested=False,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    for seq in range(1, event_count + 1):
        event_kind = c9.SESSION_CREATED if seq == 1 else c9.SESSION_PROJECTION_REFRESHED
        connection.execute(
            PUBLIC_TABLES["runtime_events"]
            .insert()
            .values(
                project_key=PROJECT_KEY,
                run_id=RUN_ID,
                seq=seq,
                event_type=event_kind,
                schema_version="mrw.runtime.event.v1",
                step_id="step:1",
                attempt_id=None,
                event_metadata_json={"kind": event_kind},
                payload_ref=f"value:event:{seq}",
                payload_digest=_digest(f"{PROJECT_KEY}:event:{seq}"),
                authority_digest=_digest(f"{PROJECT_KEY}:authority:{seq}"),
                created_at=NOW,
                updated_at=NOW,
            )
        )


def _seed_project_rows(connection: sa.Connection, project: Any) -> None:
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
    for index in (1, 2):
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
        candidate_id = f"candidate:c7:{index}"
        value_id = f"c7:structured:{candidate_id}"
        value_ref = f"project-value:{value_id}"
        value_digest = sha256_hex(canonical_bytes(structured_payload))
        value_incarnation = f"c7:structured:{candidate_id}"
        provenance_closure_digest = _digest(f"c7-provenance:{index}")
        connection.execute(
            project.successor_values.insert().values(
                project_key=PROJECT_KEY,
                value_id=value_id,
                object_type=C7_STRUCTURED_VALUE_OBJECT_TYPE,
                codec_id=C7_STRUCTURED_VALUE_CODEC_ID,
                content_digest=value_digest,
                byte_size=len(canonical_bytes(structured_payload)),
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
            "candidate_id": candidate_id,
            "snapshot_ref": f"snapshot:c7:{index}",
            "alternative": "EXTRACT",
            "verification_profile_ref": (
                "mrw.successor.ingest-c7.verification.profile.v1"
            ),
            "verification_receipt": f"receipt:c7:{index}",
            "evidence_digest": _digest(f"evidence:{index}"),
            "provenance_digest": _digest(f"provenance:{index}"),
            "candidate_receipt_digest": _digest(f"candidate-receipt:{index}"),
            "value_ref": value_ref,
            "value_revision": 1,
            "value_incarnation": value_incarnation,
            "value_digest": value_digest,
            "value_provenance_digest": provenance_closure_digest,
            "canonical_commit_ref": f"commit:c7:{index}",
            "receipt_digest": _digest(f"receipt:{index}"),
            "head_closure_digest": _digest(f"head-closure:{index}"),
        }
        connection.execute(C7_MOVEMENT_CANONICAL_DOCUMENTS.insert().values(**values))


def _reset(engine: Engine) -> None:
    public_names = (
        "runtime_events",
        "runtime_runs",
        "runtime_projection_offsets",
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
        _seed_runtime_project(connection)
        _seed_project_rows(connection, project)


@pytest.fixture(autouse=True)
def clean_database(disposable_database: Engine) -> Iterator[None]:
    _reset(disposable_database)
    yield


def _project_metadata() -> tuple[sa.MetaData, Any]:
    metadata = sa.MetaData()
    return metadata, project_tables(metadata, PROJECT_SCHEMA)


def _pointer_rows(connection: sa.Connection) -> list[dict[str, Any]]:
    table = PUBLIC_TABLES["runtime_projection_offsets"]
    rows = connection.execute(
        sa.select(table).where(
            table.c.project_key == PROJECT_KEY,
            table.c.projector_id == C9_TYPED_SOURCE_PROJECTOR_ID,
        )
    )
    return [dict(row) for row in rows.mappings().all()]


def test_same_closure_put_is_idempotent_and_loads_exact(
    disposable_database: Engine,
) -> None:
    _, project = _project_metadata()
    with disposable_database.begin() as connection:
        scope = _scope()
        closure = build_semantic_source_closure(connection, scope)
        first = put_semantic_source_rows(connection, scope, closure)
        second = put_semantic_source_rows(connection, scope, closure)
    assert first.changed is True
    assert second.changed is False
    assert first.value_ids == second.value_ids
    assert len(first.value_ids) == 3
    assert len(set(first.value_ids)) == 3
    assert first.manifest_value_id == second.manifest_value_id
    assert first.pointer_ref == second.pointer_ref == first.manifest_value_id
    with disposable_database.connect() as connection:
        loaded = load_exact_semantic_source_closure(connection, scope)
        pointers = _pointer_rows(connection)
        manifest_rows = (
            connection.execute(
                sa.select(project.successor_values).where(
                    project.successor_values.c.project_key == PROJECT_KEY,
                    project.successor_values.c.object_type
                    == C9_CLOSURE_MANIFEST_OBJECT_TYPE,
                )
            )
            .mappings()
            .all()
        )
    assert loaded == closure
    assert len(pointers) == 1
    assert pointers[0]["source_digest"] == closure.closure_digest
    assert pointers[0]["offset_ref"] == first.manifest_value_id
    assert pointers[0]["revision"] == 0
    assert len(manifest_rows) == 1
    assert manifest_rows[0]["value_id"] == first.manifest_value_id


def test_legitimate_advance_writes_new_versions_retains_old_and_loads_current(
    disposable_database: Engine,
) -> None:
    _, project = _project_metadata()
    with disposable_database.begin() as connection:
        scope = _scope()
        closure_a = build_semantic_source_closure(connection, scope)
        first = put_semantic_source_rows(connection, scope, closure_a)
        # Legal Research Ledger advance: new runtime revision/event and graph row.
        connection.execute(
            sa.update(PUBLIC_TABLES["runtime_runs"])
            .where(PUBLIC_TABLES["runtime_runs"].c.project_key == PROJECT_KEY)
            .values(revision=1, next_event_seq=4)
        )
        connection.execute(
            PUBLIC_TABLES["runtime_events"]
            .insert()
            .values(
                project_key=PROJECT_KEY,
                run_id=RUN_ID,
                seq=3,
                event_type=c9.SESSION_PROJECTION_REFRESHED,
                schema_version="mrw.runtime.event.v1",
                step_id="step:1",
                attempt_id=None,
                event_metadata_json={"kind": c9.SESSION_PROJECTION_REFRESHED},
                payload_ref="value:event:3",
                payload_digest=_digest(f"{PROJECT_KEY}:event:3"),
                authority_digest=_digest(f"{PROJECT_KEY}:authority:3"),
                created_at=NOW,
                updated_at=NOW,
            )
        )
        connection.execute(
            project.research_objects.insert().values(
                project_key=PROJECT_KEY,
                object_id="object:3",
                object_type="research_note",
                revision=3,
                incarnation="object-inc:3",
                lifecycle_state="ADMITTED",
                owner_binding_ref="owner:object:3",
                content_ref="content:object:3",
                content_digest=_digest("object:3"),
                provenance_closure_digest=_digest("object-provenance:3"),
                created_at=NOW,
                updated_at=NOW,
            )
        )
        closure_b = build_semantic_source_closure(connection, scope)
        assert closure_b.closure_digest != closure_a.closure_digest
        second = put_semantic_source_rows(connection, scope, closure_b)
        loaded = load_exact_semantic_source_closure(connection, scope)
        rows = (
            connection.execute(
                sa.select(project.successor_values).where(
                    project.successor_values.c.project_key == PROJECT_KEY,
                    project.successor_values.c.source_ref
                    == f"c9:semantic-source:{PROJECT_KEY}",
                )
            )
            .mappings()
            .all()
        )
        old_manifest = (
            connection.execute(
                sa.select(project.successor_values).where(
                    project.successor_values.c.project_key == PROJECT_KEY,
                    project.successor_values.c.value_id == first.manifest_value_id,
                )
            )
            .mappings()
            .one()
        )
        pointers = _pointer_rows(connection)
    assert second.changed is True
    assert loaded == closure_b
    assert second.value_ids != first.value_ids
    assert second.manifest_value_id != first.manifest_value_id
    by_id = {str(row["value_id"]): dict(row) for row in rows}
    assert set(by_id) == set(first.value_ids) | set(second.value_ids)
    for value_id in first.value_ids:
        old = by_id[value_id]
        assert old["value_id"] == value_id
        assert old["revision"] == 1
    assert old_manifest["object_type"] == C9_CLOSURE_MANIFEST_OBJECT_TYPE
    assert len(pointers) == 1
    assert pointers[0]["source_digest"] == closure_b.closure_digest
    assert pointers[0]["offset_ref"] == second.manifest_value_id
    assert pointers[0]["source_revision"] == 1
    assert pointers[0]["revision"] == 1


def test_reversion_to_old_closure_fails_closed(
    disposable_database: Engine,
) -> None:
    _, project = _project_metadata()
    with disposable_database.begin() as connection:
        scope = _scope()
        closure_a = build_semantic_source_closure(connection, scope)
        put_semantic_source_rows(connection, scope, closure_a)
        connection.execute(
            sa.update(PUBLIC_TABLES["runtime_runs"])
            .where(PUBLIC_TABLES["runtime_runs"].c.project_key == PROJECT_KEY)
            .values(revision=1, next_event_seq=4)
        )
        connection.execute(
            PUBLIC_TABLES["runtime_events"]
            .insert()
            .values(
                project_key=PROJECT_KEY,
                run_id=RUN_ID,
                seq=3,
                event_type=c9.SESSION_PROJECTION_REFRESHED,
                schema_version="mrw.runtime.event.v1",
                step_id="step:1",
                attempt_id=None,
                event_metadata_json={"kind": c9.SESSION_PROJECTION_REFRESHED},
                payload_ref="value:event:3",
                payload_digest=_digest(f"{PROJECT_KEY}:event:3"),
                authority_digest=_digest(f"{PROJECT_KEY}:authority:3"),
                created_at=NOW,
                updated_at=NOW,
            )
        )
        closure_b = build_semantic_source_closure(connection, scope)
        put_semantic_source_rows(connection, scope, closure_b)
        with pytest.raises(C9SourceValueConflictError):
            put_semantic_source_rows(connection, scope, closure_a)
        loaded = load_exact_semantic_source_closure(connection, scope)
        rows = (
            connection.execute(
                sa.select(project.successor_values).where(
                    project.successor_values.c.project_key == PROJECT_KEY,
                    project.successor_values.c.source_ref
                    == f"c9:semantic-source:{PROJECT_KEY}",
                )
            )
            .mappings()
            .all()
        )
    assert loaded == closure_b
    digests = {str(row["content_digest"]) for row in rows}
    assert closure_a.closure_digest in {
        str(dict(row["provenance_json"])["closure_digest"]) for row in rows
    }
    assert len(digests) == 6


def test_payload_tamper_fails_closed(disposable_database: Engine) -> None:
    _, project = _project_metadata()
    with disposable_database.begin() as connection:
        scope = _scope()
        closure = build_semantic_source_closure(connection, scope)
        result = put_semantic_source_rows(connection, scope, closure)
        stored = (
            connection.execute(
                sa.select(project.successor_values).where(
                    project.successor_values.c.project_key == PROJECT_KEY,
                    project.successor_values.c.value_id == result.value_ids[0],
                )
            )
            .mappings()
            .one()
        )
        tampered = dict(stored["content_json"])
        tampered["session_ref"] = "run:tampered"
        connection.execute(
            sa.update(project.successor_values)
            .where(
                project.successor_values.c.project_key == PROJECT_KEY,
                project.successor_values.c.value_id == result.value_ids[0],
            )
            .values(content_json=tampered)
        )
        with pytest.raises(C9SourceClosureDriftError):
            load_exact_semantic_source_closure(connection, scope)


def test_cross_scope_read_and_closure_identity_write_fail_closed(
    disposable_database: Engine,
) -> None:
    with disposable_database.connect() as connection:
        scope = _scope()
        foreign_scope = _scope(
            project_key=OTHER_PROJECT_KEY,
            scope_digest=OTHER_SCOPE_DIGEST,
            incarnation=OTHER_INCARNATION,
            resolved_schema=OTHER_PROJECT_SCHEMA,
        )
        with pytest.raises(C9SourceMissingRowError):
            load_exact_semantic_source_closure(connection, foreign_scope)
    with disposable_database.begin() as connection:
        scope = _scope()
        local_closure = build_semantic_source_closure(connection, scope)
        foreign_closure = c9.C9SemanticSourceClosureV1(
            schema_version=c9.C9_SEMANTIC_SOURCE_CLOSURE_SCHEMA,
            project_scope_ref=local_closure.project_scope_ref,
            closure_id=f"project:{OTHER_PROJECT_KEY}:semantic-sources",
            revision=local_closure.revision,
            incarnation=local_closure.incarnation,
            runtime_session_source=local_closure.runtime_session_source,
            research_graph_source=local_closure.research_graph_source,
            c7_search_source=local_closure.c7_search_source,
        )
        with pytest.raises(C9SourceProvenanceDriftError):
            put_semantic_source_rows(connection, scope, foreign_closure)
