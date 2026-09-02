"""Disposable PostgreSQL coverage for C7.2/C7.3/C7.4 readback and offsets."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import NullPool

from app.successor_migration.document_repository_c7 import (
    CanonicalCommitReadback,
    CanonicalDocumentState,
    document_ref_from_readback,
)
from app.successor_migration.ingest_recovery_c7 import C7ReconciliationPolicy
from app.successor_migration.search_projector_c7 import (
    SEARCH_PROJECTOR_ID,
    SEARCH_PROJECTOR_VERSION,
    SEARCH_SOURCE_KIND,
    rebuild_search_projection,
)
from app.successor_runtime.capabilities import ingest_c7_common as c7
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
from app.successor_runtime.runtime.transitions import EffectDisposition
from app.successor_runtime.substrate.postgres.commit_intents import (
    CommitIntentBinding,
    CommitIntentRepository,
    CommitIntentStatus,
)
from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES
from app.successor_runtime.substrate.postgres.projection_offsets import (
    ProjectionOffsetKey,
    ProjectionOffsetRepository,
)
from app.successor_runtime.substrate.postgres.runtime_journal import (
    StaleRevisionError,
)
from tests.successor_runtime.p4_c7_fixture import (
    AUTHORITY_DIGEST,
    PROJECT_KEY,
    REGISTRY_REVISION,
    RESOLVED_SCHEMA,
    SCOPE_DIGEST,
    SCOPE_INCARNATION,
    canonical_commit_readback,
    document_ref,
    normalized,
    verification_binding,
)

pytestmark = pytest.mark.integration

DATABASE_NAME = "mrw_p4_c7_worker_test"
ENV_URL = "SUCCESSOR_TEST_DATABASE_URL"

CANONICAL_DOCUMENT_TABLE = sa.Table(
    "c7_canonical_documents",
    sa.MetaData(),
    sa.Column("project_key", sa.String(128), primary_key=True),
    sa.Column("object_id", sa.String(128), primary_key=True),
    sa.Column("revision", sa.BigInteger, nullable=False),
    sa.Column("incarnation", sa.String(128), nullable=False),
    sa.Column("content_digest", sa.String(64), nullable=False),
    sa.Column("canonical_commit_ref", sa.String(256), nullable=False),
)


def _server_url() -> str:
    env_url = os.environ.get(ENV_URL)
    if env_url:
        url = make_url(env_url)
        return url.set(database="postgres").render_as_string(hide_password=False)
    return "postgresql+psycopg2://localhost/postgres"


def _create_database() -> Engine:
    server_url = _server_url()
    server = sa.create_engine(
        server_url, isolation_level="AUTOCOMMIT", poolclass=NullPool
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
    with engine.begin() as connection:
        for table in PUBLIC_TABLES.values():
            table.create(connection)
        CANONICAL_DOCUMENT_TABLE.create(connection)
        _seed_scope_and_run(connection)
        _seed_canonical_document(connection)
    try:
        yield engine
    finally:
        engine.dispose()
        _drop_database(server)


def _seed_scope_and_run(connection: sa.Connection) -> None:
    connection.execute(
        PUBLIC_TABLES["project_scope_registry"]
        .insert()
        .values(
            project_key=PROJECT_KEY,
            registry_revision=REGISTRY_REVISION,
            resolved_schema=RESOLVED_SCHEMA,
            scope_digest=SCOPE_DIGEST,
            incarnation=SCOPE_INCARNATION,
            state="ACTIVE",
            updated_by="c7-postgres",
            approval_ref=None,
        )
    )
    connection.execute(
        PUBLIC_TABLES["runtime_program_refs"]
        .insert()
        .values(
            program_id="program:p4-c7-postgres",
            project_key=PROJECT_KEY,
            program_digest=AUTHORITY_DIGEST,
            project_storage_ref="project-value:program:p4-c7-postgres",
            contract_version="mrw.functorial-successor.program-spec.v1",
        )
    )
    connection.execute(
        PUBLIC_TABLES["runtime_runs"]
        .insert()
        .values(
            run_id="run:p4-c7-postgres",
            project_key=PROJECT_KEY,
            project_registry_revision=REGISTRY_REVISION,
            project_scope_digest=SCOPE_DIGEST,
            resolved_schema=RESOLVED_SCHEMA,
            program_id="program:p4-c7-postgres",
            program_digest=AUTHORITY_DIGEST,
            plan_id=None,
            plan_digest=None,
            state="SUBMITTED",
            revision=0,
            next_event_seq=1,
            execution_epoch=1,
            incarnation="run-inc:p4-c7-postgres",
            submission_authority_digest=AUTHORITY_DIGEST,
            qualification_digest=None,
        )
    )
    connection.execute(
        PUBLIC_TABLES["runtime_steps"]
        .insert()
        .values(
            project_key=PROJECT_KEY,
            run_id="run:p4-c7-postgres",
            step_id="step:p4-c7-postgres",
            operation_id="ingest_index.stage_candidate",
            operation_kind="ingest_index.stage_candidate.v1",
            operation_version="1.0.0",
            state="SUCCEEDED",
            revision=0,
            execution_epoch=1,
            input_digest=AUTHORITY_DIGEST,
            output_digest=AUTHORITY_DIGEST,
            effect_class=c7.build_ingest_c7_bundle().profiles["effect"].execution_class,
            resource_class="CPU_LIGHT",
            capability_id="ingest_index.c7.v1",
            claim_owner="successor",
            claim_authority_epoch=1,
            claim_policy_digest=AUTHORITY_DIGEST,
        )
    )


def _scope() -> RuntimeScope:
    return RuntimeScope(
        project_scope=ProjectScopeRef(
            project_key=PROJECT_KEY,
            resolved_schema=RESOLVED_SCHEMA,
            project_registry_revision=REGISTRY_REVISION,
            incarnation=SCOPE_INCARNATION,
            scope_digest=SCOPE_DIGEST,
        ),
        actor_id="actor:p4-c7-postgres",
    )


def _seed_canonical_document(connection: sa.Connection) -> None:
    connection.execute(
        CANONICAL_DOCUMENT_TABLE.insert().values(
            project_key=PROJECT_KEY,
            object_id=verification_binding().canonical_object_id,
            revision=1,
            incarnation=SCOPE_INCARNATION,
            content_digest=normalized().content_digest,
            canonical_commit_ref="canonical:document:p4-c7-postgres",
        )
    )


def _read_canonical_document(
    connection: sa.Connection,
    object_id: str,
) -> CanonicalDocumentState | None:
    row = (
        connection.execute(
            sa.select(CANONICAL_DOCUMENT_TABLE).where(
                CANONICAL_DOCUMENT_TABLE.c.project_key == PROJECT_KEY,
                CANONICAL_DOCUMENT_TABLE.c.object_id == object_id,
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    return CanonicalDocumentState(
        project_key=row["project_key"],
        object_id=row["object_id"],
        revision=row["revision"],
        incarnation=row["incarnation"],
        content_digest=row["content_digest"],
        canonical_commit_ref=row["canonical_commit_ref"],
    )


def _commit_binding() -> CommitIntentBinding:
    binding = verification_binding()
    return CommitIntentBinding(
        commit_intent_id="commit:p4-c7-postgres",
        run_id="run:p4-c7-postgres",
        step_id="step:p4-c7-postgres",
        capability_id="ingest_index.c7.v1",
        canonical_owner_ref=c7.DOCUMENT_CANONICAL_OWNER,
        object_identity_ref=binding.canonical_object_id,
        expected_base_revision=0,
        expected_base_incarnation=SCOPE_INCARNATION,
        content_digest=binding.output_content_digest,
        event_digest=binding.ordered_event_payload_closure_digest,
        verification_digest=binding.binding_digest,
        authority_digest=AUTHORITY_DIGEST,
        idempotency_key="idem:p4-c7-postgres",
    )


def test_c7_2_commit_intent_prepare_commit_and_typed_readback(
    disposable_database: Engine,
) -> None:
    assert c7.build_ingest_c7_bundle().profiles["effect"].execution_class == (
        "EFFECTFUL"
    )
    with disposable_database.connect() as connection:
        repo = CommitIntentRepository(connection, _scope())
        prepared = repo.prepare(_commit_binding())
        assert prepared["state"] == "PREPARED"
        committed = repo.record_result(
            prepared["commit_intent_id"],
            expected_revision=0,
            status=CommitIntentStatus.COMMITTED,
            canonical_commit_ref="canonical:document:p4-c7-postgres",
            receipt_digest=AUTHORITY_DIGEST,
        )
        assert committed["state"] == "COMMITTED"
        readback = repo.find_for_readback(
            "ingest_index.c7.v1",
            "idem:p4-c7-postgres",
        )
        assert readback["content_digest"] == _commit_binding().content_digest
        assert readback["verification_digest"] == _commit_binding().verification_digest
        assert readback["canonical_commit_ref"] == ("canonical:document:p4-c7-postgres")
        document = _read_canonical_document(
            connection,
            _commit_binding().object_identity_ref,
        )
        assert document is not None
        canonical_readback = CanonicalCommitReadback(
            commit_intent_id=readback["commit_intent_id"],
            idempotency_key="idem:p4-c7-postgres",
            capability_id="ingest_index.c7.v1",
            project_key=PROJECT_KEY,
            object_id=readback["object_identity_ref"],
            committed_revision=document.revision,
            committed_incarnation=document.incarnation,
            content_digest=document.content_digest,
            canonical_commit_ref=document.canonical_commit_ref,
        )
        ref = document_ref_from_readback(canonical_readback)
        assert ref.revision == document.revision
        assert ref.incarnation == document.incarnation
        assert ref.content_digest == document.content_digest
        assert ref.project_key == PROJECT_KEY


def test_c7_3_projection_offset_exact_cas_and_rebuild(
    disposable_database: Engine,
) -> None:
    with disposable_database.connect() as connection:
        object_id = verification_binding().canonical_object_id
        with connection.begin():
            connection.execute(
                CANONICAL_DOCUMENT_TABLE.update()
                .where(
                    CANONICAL_DOCUMENT_TABLE.c.project_key == PROJECT_KEY,
                    CANONICAL_DOCUMENT_TABLE.c.object_id == object_id,
                )
                .values(revision=2)
            )
        document = _read_canonical_document(connection, object_id)
        assert document is not None
        readback = canonical_commit_readback(committed_revision=document.revision)
        ref = document_ref_from_readback(readback)
        assert ref.revision == document.revision
        assert ref.incarnation == document.incarnation
        assert ref.content_digest == document.content_digest
        key = ProjectionOffsetKey(
            projector_id=SEARCH_PROJECTOR_ID,
            projector_version=SEARCH_PROJECTOR_VERSION,
            source_kind=SEARCH_SOURCE_KIND,
            source_ref=f"document:{ref.object_id}",
            source_incarnation=ref.incarnation,
        )
        offsets = ProjectionOffsetRepository(connection, _scope())
        created = offsets.create(
            projection_offset_id="offset:p4-c7-postgres",
            key=key,
            projection_generation=0,
            source_revision=document.revision,
            source_digest=ref.content_digest,
            offset_ref=f"document-revision:{document.revision}",
        )
        assert created["source_revision"] == document.revision
        assert created["source_digest"] == document.content_digest
        with pytest.raises(StaleRevisionError):
            offsets.advance(
                "offset:p4-c7-postgres",
                key=key,
                expected_revision=0,
                expected_generation=0,
                expected_source_revision=1,
                expected_source_digest=ref.content_digest,
                source_revision=3,
                source_digest=ref.content_digest,
                offset_ref="document-revision:3",
            )
        loaded = offsets.load_source(key)
        assert loaded is not None
        assert loaded["offset_ref"] == f"document-revision:{document.revision}"
        assert loaded["source_revision"] == document.revision
        assert loaded["source_digest"] == document.content_digest
        assert loaded["source_incarnation"] == document.incarnation
        rebuilt = rebuild_search_projection(ref)
        assert rebuilt.projection_digest


def test_c7_4_outcome_unknown_readback_recovery_never_starts_new_attempt(
    disposable_database: Engine,
) -> None:
    with disposable_database.connect() as connection:
        repo = CommitIntentRepository(connection, _scope())
        prepared = repo.prepare(_commit_binding())
        unknown = repo.record_result(
            prepared["commit_intent_id"],
            expected_revision=0,
            status=CommitIntentStatus.UNKNOWN,
        )
        assert unknown["state"] == "OUTCOME_UNKNOWN"
        recovered = repo.record_result(
            prepared["commit_intent_id"],
            expected_revision=1,
            status=CommitIntentStatus.REJECTED,
            canonical_commit_ref=None,
            receipt_digest=None,
        )
        assert recovered["state"] == "REJECTED"
        readback = repo.find_for_readback(
            "ingest_index.c7.v1",
            "idem:p4-c7-postgres",
        )
        assert readback["state"] == "REJECTED"
        decision = C7ReconciliationPolicy().terminal_decision(EffectDisposition.FAILED)
        assert decision.new_attempt_allowed is False


def test_c7_3_projector_offset_source_matches_shared_key_shape(
    disposable_database: Engine,
) -> None:
    projection = rebuild_search_projection(document_ref())
    fields = projection.source.to_offset_key()
    assert set(fields) == {
        "projector_id",
        "projector_version",
        "source_kind",
        "source_ref",
        "source_incarnation",
    }
