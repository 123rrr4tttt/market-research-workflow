"""Real-PostgreSQL C9 movement-closure backend tests.

The suite owns a disposable database ``mrw_c9_movement_closure_test``: it
drops any prior database, creates the shared public schema plus a
family-local project schema, seeds the exact scope/grant/approval authority,
and drops the database on teardown.  It exercises exact reserve/replay/
conflict/concurrent duplicate submission, effect-boundary scope/actor/
approval/expected-base gates, read-only snapshot queries, deterministic
generation rebuild with declared external loss, source-closure forgery
rejection, cross-source isolation, required-sink failure without activation,
prior-generation rollback and fresh-session readback.  No provider/network
effect runs and no shared migration/API/aggregate is touched.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import NullPool

import app.successor_runtime.substrate.postgres.facade_commands as facade_commands_module
import scripts.c9_projection_rebuild as rebuild_module
from app.successor_runtime.research.codec import canonical_bytes, sha256_hex
from app.successor_runtime.runtime.authority_grants import (
    AuthorityOperationScope,
    AuthorityResourceCeiling,
    AuthorityResourceLimit,
)
from app.successor_runtime.runtime.facade import SuccessorRuntimeFacade
from app.successor_runtime.runtime.facade_contracts import (
    C9CommandBaseConflict,
    C9CommandBlocked,
    C9CommandConflict,
    C9TransactionFatal,
    C9Unavailable,
    CommandMetaV2,
    FacadeCommandV2,
    FacadeQueryV2,
    QueryMetaV2,
    derive_c9_request_digest,
)
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
from app.successor_runtime.substrate.postgres.approvals import (
    ApprovalBinding,
    ApprovalRepository,
)
from app.successor_runtime.substrate.postgres.authority import (
    AuthorityGrant,
    AuthorityGrantRepository,
)
from app.successor_runtime.substrate.postgres.c9_projection_sources import (
    build_semantic_source_closure,
    load_exact_semantic_source_closure,
    put_semantic_source_rows,
)
from app.successor_runtime.substrate.postgres.facade_commands import (
    PostgresC9CommandRepository,
    PostgresC9QueryRepository,
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
    ProjectTables,
    project_tables,
)
from app.successor_runtime.substrate.postgres.projection_offsets import (
    ProjectionOffsetKey,
)
from app.successor_runtime.substrate.postgres.runtime_journal import (
    StaleRevisionError,
)
from app.successor_runtime.substrate.postgres.session import compute_scope_digest
from app.successor_runtime.substrate.postgres.values import (
    ReceiptRepository,
    ValueRepository,
)
from app.successor_runtime.substrate.projections import c9_sources as c9
from scripts.c9_projection_rebuild import (
    CANDIDATE_OBJECT_TYPES,
    EXTERNAL_DECLARED_LOSS_SINKS,
    REQUIRED_LOCAL_SINKS,
    PostgresC9ProjectionRebuilder,
    PostgresProjectionSinkWriter,
    build_loss_profile,
)

pytestmark = pytest.mark.integration

DATABASE_NAME = "mrw_c9_movement_closure_test"
ENV_URL = "SUCCESSOR_TEST_DATABASE_URL"
PROJECT_KEY = "p4-c9-movement-closure"
PROJECT_SCHEMA = "mrw_p9_c9_movement_closure"
REGISTRY_REVISION = 1
SCOPE_INCARNATION = "scope-inc-c9-pg"
SCOPE_DIGEST = compute_scope_digest(
    PROJECT_KEY,
    PROJECT_SCHEMA,
    REGISTRY_REVISION,
    SCOPE_INCARNATION,
)
ACTOR = "actor:c9-postgres"
SCOPE = RuntimeScope(
    project_scope=ProjectScopeRef(
        project_key=PROJECT_KEY,
        resolved_schema=PROJECT_SCHEMA,
        project_registry_revision=REGISTRY_REVISION,
        incarnation=SCOPE_INCARNATION,
        scope_digest=SCOPE_DIGEST,
    ),
    actor_id=ACTOR,
)
SOURCE_REF = f"project:{PROJECT_KEY}:semantic-sources"
SOURCE_REVISION = 0
PROJECTION_ID = "projection.c9-movement-closure.v1"
PROJECTOR_ID = "projector:c9-movement-closure"
PROJECTOR_VERSION = "1"
SOURCE_IDENTITY = {
    "projector_id": PROJECTOR_ID,
    "projector_version": PROJECTOR_VERSION,
    "source_kind": "successor_values",
    "source_ref": SOURCE_REF,
    "source_incarnation": SCOPE_INCARNATION,
}
RUN_ID = "run:c9:test"
PROGRAM_ID = "program:c9:test"
PLAN_ID = "plan:c9:test"
GRANT_ID = "grant:c9:test"
APPROVAL_ID = "approval:c9:grant"
NOW = datetime(2030, 9, 1, 8, 0, tzinfo=UTC)


def _server_url() -> str:
    env_url = os.environ.get(ENV_URL)
    if env_url:
        url = make_url(env_url)
        return url.set(database="postgres").render_as_string(hide_password=False)
    return "postgresql+psycopg2://localhost/postgres"


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
    finally:
        server.dispose()


@pytest.fixture(scope="module")
def database() -> Iterator[tuple[Engine, ProjectTables]]:
    server = _create_database()
    engine = sa.create_engine(
        make_url(_server_url())
        .set(database=DATABASE_NAME)
        .render_as_string(hide_password=False),
        poolclass=NullPool,
    )
    metadata = sa.MetaData(schema=PROJECT_SCHEMA)
    project = project_tables(metadata, PROJECT_SCHEMA)
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{PROJECT_SCHEMA}"'))
        metadata.create_all(connection)
        PUBLIC_METADATA.create_all(connection)
        C7_MOVEMENT_CANONICAL_DOCUMENTS.create(connection)
    try:
        yield engine, project
    finally:
        engine.dispose()
        _drop_database(server)


@pytest.fixture(autouse=True)
def _clean_tables(database: tuple[Engine, ProjectTables]) -> Iterator[None]:
    engine, project = database
    with engine.begin() as connection:
        for table in (
            project.successor_receipts,
            project.successor_values,
            project.research_relations,
            project.research_objects,
            project.research_owner_bindings,
            PUBLIC_TABLES["runtime_projection_offsets"],
            PUBLIC_TABLES["runtime_idempotency"],
            PUBLIC_TABLES["runtime_authority_grants"],
            PUBLIC_TABLES["runtime_approvals"],
            PUBLIC_TABLES["runtime_events"],
            PUBLIC_TABLES["runtime_steps"],
            PUBLIC_TABLES["runtime_runs"],
            PUBLIC_TABLES["runtime_program_refs"],
            PUBLIC_TABLES["project_scope_registry"],
            PUBLIC_TABLES["runtime_capability_authority"],
            C7_MOVEMENT_CANONICAL_DOCUMENTS,
        ):
            connection.execute(sa.delete(table))
    yield


def _seed_authority(connection: Any) -> None:
    connection.execute(
        sa.insert(PUBLIC_TABLES["project_scope_registry"]).values(
            project_key=PROJECT_KEY,
            registry_revision=REGISTRY_REVISION,
            resolved_schema=PROJECT_SCHEMA,
            scope_digest=SCOPE_DIGEST,
            incarnation=SCOPE_INCARNATION,
            state="ACTIVE",
            updated_by=ACTOR,
            approval_ref="approval:c9:scope",
            created_at=NOW,
            updated_at=NOW,
        )
    )
    program_digest = sha256_hex({"program": PROGRAM_ID})
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_program_refs"]).values(
            program_id=PROGRAM_ID,
            project_key=PROJECT_KEY,
            program_digest=program_digest,
            project_storage_ref=f"value:{PROJECT_SCHEMA}:program:{PROGRAM_ID}",
            contract_version="1",
            created_at=NOW,
            updated_at=NOW,
        )
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_runs"]).values(
            run_id=RUN_ID,
            project_key=PROJECT_KEY,
            project_registry_revision=REGISTRY_REVISION,
            project_scope_digest=SCOPE_DIGEST,
            resolved_schema=PROJECT_SCHEMA,
            program_id=PROGRAM_ID,
            program_digest=program_digest,
            plan_id=None,
            plan_digest=None,
            state="SUBMITTED",
            revision=0,
            next_event_seq=1,
            execution_epoch=0,
            incarnation="run-inc:c9:test",
            submission_authority_digest=sha256_hex({"submission": RUN_ID}),
            qualification_digest=None,
            cancellation_requested=False,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    ApprovalRepository(connection, SCOPE).decide(
        ApprovalBinding(
            approval_id=APPROVAL_ID,
            actor_id=ACTOR,
            run_id=RUN_ID,
            step_id="step:c9:grant",
            payload_digest=sha256_hex({"approval": APPROVAL_ID}),
            decision="APPROVED",
            expires_at=NOW + timedelta(hours=1),
            authority_digest=sha256_hex({"authority": APPROVAL_ID}),
        )
    )
    _seed_grant(connection)
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_capability_authority"]).values(
            project_key=PROJECT_KEY,
            capability_id="capability:successor-runtime:c9",
            mode="on",
            authority_epoch=1,
            successor_claim_enabled=True,
            legacy_claim_enabled=False,
            allowlist_digest=sha256_hex({"allowlist": "c9"}),
            config_digest=sha256_hex({"config": "c9"}),
            effective_at=NOW,
            updated_by=ACTOR,
            approval_ref="approval:c9:scope",
            rollback_target_ref="rollback:c9:test",
            revision=0,
            created_at=NOW,
            updated_at=NOW,
        )
    )


def _seed_grant(connection: Any) -> None:
    AuthorityGrantRepository(connection, SCOPE).create(
        AuthorityGrant(
            grant_id=GRANT_ID,
            actor_id=ACTOR,
            capability_id="capability:successor-runtime:c9",
            operation_scope_json=AuthorityOperationScope.from_content(
                operation_kinds=("rebuild_projection", "invalidate_projection"),
                project_scope_digest=SCOPE_DIGEST,
            ),
            resource_ceiling_json=AuthorityResourceCeiling.from_content(
                limits=(AuthorityResourceLimit(resource_class="projection", units=1),),
                max_active=1,
            ),
            credential_ref=None,
            grant_epoch=1,
            expires_at=NOW + timedelta(hours=1),
        )
    )


def _seed_approval_for_digest(
    connection: Any,
    approval_id: str,
    payload_digest: str,
) -> None:
    ApprovalRepository(connection, SCOPE).decide(
        ApprovalBinding(
            approval_id=approval_id,
            actor_id=ACTOR,
            run_id=RUN_ID,
            step_id="step:c9:exact",
            payload_digest=payload_digest,
            decision="APPROVED",
            expires_at=NOW + timedelta(hours=1),
            authority_digest=sha256_hex({"authority": approval_id}),
        )
    )


def _command(
    *,
    command_id: str = "cmd-c9-pg-001",
    actor_ref: str = ACTOR,
    payload: dict[str, Any] | None = None,
    request_digest: str | None = None,
    expected_base_token: str | None = None,
    approval_locator: str | None = None,
) -> FacadeCommandV2:
    payload = payload or {"projection_id": PROJECTION_ID, **SOURCE_IDENTITY}
    if request_digest is None:
        request_digest = derive_c9_request_digest(
            scope_digest=SCOPE_DIGEST,
            actor_ref=actor_ref,
            command_id=command_id,
            command_kind="rebuild_projection",
            payload=payload,
            expected_base_token=expected_base_token,
            approval_locator=approval_locator,
        )
    return FacadeCommandV2(
        command_id=command_id,
        command_kind="rebuild_projection",
        description="rebuild projection",
        project_scope_ref=SCOPE.project_scope,
        actor_ref=actor_ref,
        idempotency_key=request_digest,
        expected_base_token=expected_base_token,
        meta=CommandMetaV2(
            project_key=PROJECT_KEY,
            trace_id="trace-c9-pg",
            command_id=command_id,
            project_scope_ref=SCOPE.project_scope,
        ),
        approval_locator=approval_locator,
        payload=payload,
    )


def _query(**params: Any) -> FacadeQueryV2:
    values = {
        "projection_id": PROJECTION_ID,
        **SOURCE_IDENTITY,
    }
    values.update(params)
    return FacadeQueryV2(
        query_id="query-c9-pg-001",
        query_kind="projection_snapshot",
        project_scope_ref=SCOPE.project_scope,
        actor_ref=ACTOR,
        meta=QueryMetaV2(
            project_key=PROJECT_KEY,
            trace_id="trace-c9-pg",
            query_id="query-c9-pg-001",
            project_scope_ref=SCOPE.project_scope,
        ),
        params=values,
    )


def _key(source_ref: str = SOURCE_REF) -> ProjectionOffsetKey:
    return ProjectionOffsetKey(
        projector_id=PROJECTOR_ID,
        projector_version=PROJECTOR_VERSION,
        source_kind="successor_values",
        source_ref=source_ref,
        source_incarnation=SCOPE_INCARNATION,
    )


def _digest(label: str) -> str:
    return sha256_hex(label)


def _seed_source_tables(connection: Any, project: ProjectTables) -> None:
    for seq, event_kind in (
        (1, c9.SESSION_CREATED),
        (2, c9.SESSION_PROJECTION_REFRESHED),
    ):
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
        value_digest = hashlib.sha256(canonical_bytes(structured_payload)).hexdigest()
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


def _seed_sources(
    connection: Any,
    project: ProjectTables,
    *,
    source_ref: str = SOURCE_REF,
) -> tuple[str, int]:
    if source_ref != SOURCE_REF:
        raise AssertionError("official C9 semantic source closure is project-scoped")
    run_exists = connection.execute(
        sa.select(sa.func.count())
        .select_from(PUBLIC_TABLES["runtime_runs"])
        .where(
            PUBLIC_TABLES["runtime_runs"].c.project_key == PROJECT_KEY,
            PUBLIC_TABLES["runtime_runs"].c.run_id == RUN_ID,
        )
    ).scalar()
    if not run_exists:
        _seed_authority(connection)
    _seed_source_tables(connection, project)
    closure = build_semantic_source_closure(connection, SCOPE)
    put_semantic_source_rows(connection, SCOPE, closure)
    return closure.closure_digest, int(closure.revision)


def _gen0_candidate_value_id(
    connection: Any,
    project: ProjectTables,
    sink: str,
) -> str:
    object_type = {
        "agent_session": "AgentSessionLocalProjection.v1",
        "graph": "GraphLocalProjection.v1",
        "search": "SearchLocalProjection.v1",
    }[sink]
    rows = (
        connection.execute(
            sa.select(project.successor_values.c.value_id).where(
                project.successor_values.c.project_key == PROJECT_KEY,
                project.successor_values.c.object_type == object_type,
                project.successor_values.c.provenance_json[
                    "projection_generation"
                ].as_integer()
                == 0,
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    return rows[0]


def _gen0_receipt_id(
    connection: Any,
    project: ProjectTables,
    sink: str,
) -> str:
    rows = (
        connection.execute(
            sa.select(project.successor_receipts.c.receipt_id).where(
                project.successor_receipts.c.project_key == PROJECT_KEY,
                project.successor_receipts.c.receipt_id.like(
                    f"c9:{sink}:receipt:%:gen-0:%"
                ),
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    return rows[0]


def test_rollback_rejects_deleted_old_generation_candidate(
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, project = database
    with engine.begin() as connection:
        _ready_projection(connection, project)
        graph_value_id = _gen0_candidate_value_id(connection, project, "graph")
        connection.execute(
            sa.delete(project.successor_values).where(
                project.successor_values.c.project_key == PROJECT_KEY,
                project.successor_values.c.value_id == graph_value_id,
            )
        )
        rebuilder = PostgresC9ProjectionRebuilder(connection, SCOPE, tables=project)
        with pytest.raises(C9Unavailable):
            rebuilder.rollback_with_receipt(key=_key(), target_generation=0)
        assert rebuilder.readback(_key())["projection_generation"] == 1


def test_rollback_rejects_missing_old_generation_receipt(
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, project = database
    with engine.begin() as connection:
        _ready_projection(connection, project)
        receipt_id = _gen0_receipt_id(connection, project, "agent_session")
        connection.execute(
            sa.delete(project.successor_receipts).where(
                project.successor_receipts.c.project_key == PROJECT_KEY,
                project.successor_receipts.c.receipt_id == receipt_id,
            )
        )
        rebuilder = PostgresC9ProjectionRebuilder(connection, SCOPE, tables=project)
        with pytest.raises(C9Unavailable):
            rebuilder.rollback_with_receipt(key=_key(), target_generation=0)
        assert rebuilder.readback(_key())["projection_generation"] == 1


def test_rollback_rejects_duplicate_old_generation_receipt(
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, project = database
    with engine.begin() as connection:
        _ready_projection(connection, project)
        source_hash = rebuild_module._key_digest(_key())[:8]
        content = {
            "schema_version": "mrw.successor.c9.projection-receipt.v1",
            "sink": "graph",
            "projector_id": PROJECTOR_ID,
            "projector_version": PROJECTOR_VERSION,
            "source_kind": "successor_values",
            "source_ref": SOURCE_REF,
            "source_incarnation": SCOPE_INCARNATION,
            "projection_generation": 0,
            "rebuild_id": "rebuild:c9:duplicate-receipt",
            "candidate_value_id": _gen0_candidate_value_id(
                connection, project, "graph"
            ),
            "candidate_digest": "0" * 64,
        }
        ReceiptRepository(connection, project).put_exact(
            scope=SCOPE,
            receipt_id=f"c9:graph:receipt:{source_hash}:gen-0:duplicate",
            receipt_digest=sha256_hex(content),
            delivery_intent_ref="c9-local-projection:graph:gen-0",
            attempt_ref="rebuild:c9:duplicate-receipt",
            provider_locator=f"local:postgres:{PROJECT_SCHEMA}:graph",
            content=content,
            outcome_time=NOW,
        )
        rebuilder = PostgresC9ProjectionRebuilder(connection, SCOPE, tables=project)
        with pytest.raises(C9Unavailable):
            rebuilder.rollback_with_receipt(key=_key(), target_generation=0)
        assert rebuilder.readback(_key())["projection_generation"] == 1


def test_rollback_rejects_tampered_old_generation_receipt(
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, project = database
    with engine.begin() as connection:
        _ready_projection(connection, project)
        receipt_id = _gen0_receipt_id(connection, project, "search")
        content = dict(
            connection.execute(
                sa.select(project.successor_receipts.c.receipt_json).where(
                    project.successor_receipts.c.project_key == PROJECT_KEY,
                    project.successor_receipts.c.receipt_id == receipt_id,
                )
            ).scalar_one()
        )
        content["candidate_digest"] = "f" * 64
        connection.execute(
            sa.update(project.successor_receipts)
            .where(
                project.successor_receipts.c.project_key == PROJECT_KEY,
                project.successor_receipts.c.receipt_id == receipt_id,
            )
            .values(receipt_json=content)
        )
        rebuilder = PostgresC9ProjectionRebuilder(connection, SCOPE, tables=project)
        with pytest.raises(C9Unavailable):
            rebuilder.rollback_with_receipt(key=_key(), target_generation=0)
        assert rebuilder.readback(_key())["projection_generation"] == 1


def test_rollback_offset_and_receipt_are_atomic_on_failure(
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, project = database
    with engine.begin() as connection:
        _ready_projection(connection, project)
        rebuilder = PostgresC9ProjectionRebuilder(connection, SCOPE, tables=project)
        before = rebuilder.readback(_key())
        original = rebuild_module._put_receipt_idempotent

        def failing_put_receipt(*args: Any, **kwargs: Any) -> str:
            raise RuntimeError("injected rollback receipt failure")

        rebuild_module._put_receipt_idempotent = failing_put_receipt
        try:
            with pytest.raises(RuntimeError):
                rebuilder.rollback_with_receipt(key=_key(), target_generation=0)
        finally:
            rebuild_module._put_receipt_idempotent = original
        after = rebuilder.readback(_key())
        assert after["projection_generation"] == 1
        assert after["offset_revision"] == before["offset_revision"]
        rollback_receipts = connection.execute(
            sa.select(sa.func.count())
            .select_from(project.successor_receipts)
            .where(
                project.successor_receipts.c.project_key == PROJECT_KEY,
                project.successor_receipts.c.receipt_id.like("c9:rollback-receipt:%"),
            )
        ).scalar()
        assert rollback_receipts == 0
        result = rebuilder.rollback_with_receipt(key=_key(), target_generation=0)
        assert result.target_generation == 0
        assert rebuilder.readback(_key())["projection_generation"] == 0


def test_rollback_retry_returns_same_receipt_and_fresh_session_transition(
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, project = database
    with engine.begin() as connection:
        _ready_projection(connection, project)
        rebuilder = PostgresC9ProjectionRebuilder(connection, SCOPE, tables=project)
        first = rebuilder.rollback_with_receipt(key=_key(), target_generation=0)
        second = rebuilder.rollback_with_receipt(key=_key(), target_generation=0)
        assert second.receipt_id == first.receipt_id
        assert second.offset_revision == first.offset_revision
    with engine.connect() as connection:
        query_result = PostgresC9QueryRepository(connection, SCOPE).read(_query())
        assert query_result.data.projection_generation == 0
        assert query_result.data.rollback_transition is not None
        transition = query_result.data.rollback_transition
        assert transition["contract"] == "C9RollbackTransitionReceipt.v1"
        assert transition["ref"] == first.receipt_ref
        assert transition["to"]["offset_revision"] == first.offset_revision
        assert transition["to"]["projection_generation"] == 0
        assert transition["from"]["projection_generation"] == 1
        assert len(transition["generation_completeness_digest"]) == 64
        assert len(transition["digest"]) == 64
        assert len(query_result.data.candidate_values) == 3
        assert all(
            candidate.sink and candidate.payload
            for candidate in query_result.data.candidate_values
        )


def test_rollback_aba_cycle_produces_distinct_receipts(
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, project = database
    with engine.begin() as connection:
        _ready_projection(connection, project)
        rebuilder = PostgresC9ProjectionRebuilder(connection, SCOPE, tables=project)
        first = rebuilder.rollback_with_receipt(key=_key(), target_generation=0)
        source_digest, _ = _source_digest(connection, project)
        rebuilder.rebuild(
            key=_key(),
            source_revision=SOURCE_REVISION,
            source_digest=source_digest,
            source_ref=SOURCE_REF,
        )
        second = rebuilder.rollback_with_receipt(key=_key(), target_generation=0)
        assert second.receipt_id != first.receipt_id
        assert second.receipt_ref != first.receipt_ref
        third = rebuilder.rollback_with_receipt(key=_key(), target_generation=0)
        assert third.receipt_id == second.receipt_id
        assert third.offset_revision == second.offset_revision


def test_rollback_transition_tamper_fails_closed(
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, project = database
    with engine.begin() as connection:
        _ready_projection(connection, project)
        rebuilder = PostgresC9ProjectionRebuilder(connection, SCOPE, tables=project)
        rebuilder.rollback_with_receipt(key=_key(), target_generation=0)
        receipt_row = (
            connection.execute(
                sa.select(project.successor_receipts).where(
                    project.successor_receipts.c.project_key == PROJECT_KEY,
                    project.successor_receipts.c.receipt_id.like(
                        "c9:rollback-transition:%"
                    ),
                )
            )
            .mappings()
            .one()
        )
        original = dict(receipt_row["receipt_json"])
        mutations = (
            ("from", {"projection_generation": 7}),
            ("to", {"offset_ref": "value:tampered"}),
            ("generation_completeness_digest", "f" * 64),
            ("ref", "rollback:tampered"),
        )
        for field, value in mutations:
            content = dict(original)
            if field == "from":
                content["from"] = {**content["from"], "projection_generation": 7}
            elif field == "to":
                content["to"] = {**content["to"], "offset_ref": "value:tampered"}
            elif field == "generation_completeness_digest":
                content[field] = value
            else:
                content[field] = value
            connection.execute(
                sa.update(project.successor_receipts)
                .where(
                    project.successor_receipts.c.project_key == PROJECT_KEY,
                    project.successor_receipts.c.receipt_id
                    == receipt_row["receipt_id"],
                )
                .values(receipt_json=content)
            )
            with pytest.raises(C9Unavailable):
                PostgresC9QueryRepository(connection, SCOPE).read(_query())
            with pytest.raises(C9Unavailable):
                rebuilder.rollback_with_receipt(key=_key(), target_generation=0)
            connection.execute(
                sa.update(project.successor_receipts)
                .where(
                    project.successor_receipts.c.project_key == PROJECT_KEY,
                    project.successor_receipts.c.receipt_id
                    == receipt_row["receipt_id"],
                )
                .values(receipt_json=original)
            )
        transition = (
            PostgresC9QueryRepository(connection, SCOPE)
            .read(_query())
            .data.rollback_transition
        )
        assert transition is not None
        assert transition["ref"] == original["ref"]
        assert set(transition) == {
            "contract",
            "ref",
            "digest",
            "projection_id",
            "projector_id",
            "projector_version",
            "source_kind",
            "source_ref",
            "source_incarnation",
            "from",
            "to",
            "generation_completeness_digest",
        }


def _initialize_offset(
    connection: Any,
    project: ProjectTables,
    source_digest: str,
    *,
    projection_offset_id: str = "offset:c9-movement:001",
    source_ref: str = SOURCE_REF,
) -> None:
    PostgresC9ProjectionRebuilder(connection, SCOPE, tables=project).initialize(
        projection_offset_id=projection_offset_id,
        key=_key(source_ref),
        source_revision=SOURCE_REVISION,
        source_digest=source_digest,
        source_ref=source_ref,
    )


def _idempotency_row_count(connection: Any) -> int:
    table = PUBLIC_TABLES["runtime_idempotency"]
    return len(
        connection.execute(
            sa.select(table.c.idempotency_id).where(table.c.project_key == PROJECT_KEY)
        ).all()
    )


def _command_receipt_count(
    connection: Any,
    project: ProjectTables,
) -> int:
    return int(
        connection.execute(
            sa.select(sa.func.count())
            .select_from(project.successor_receipts)
            .where(project.successor_receipts.c.project_key == PROJECT_KEY)
        ).scalar()
    )


def test_command_repository_exact_reserve_replay_same_receipt(
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, _ = database
    with engine.begin() as connection:
        _seed_authority(connection)
        repo = PostgresC9CommandRepository(connection, SCOPE)
        first = repo.submit(_command())
        second = repo.submit(_command())
        assert first.receipt_ref == second.receipt_ref
        assert first.request_digest == second.request_digest
        assert first.state == "STARTED"
        assert first.authority_context_digest == second.authority_context_digest
        assert first.grant_epoch == 1
        assert first.grants_digest is not None
        assert first.observed_at is not None
        assert int(first.observed_at[:4]) > 1970
        assert _idempotency_row_count(connection) == 1


def test_command_repository_same_id_changed_body_conflict(
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, _ = database
    with engine.begin() as connection:
        _seed_authority(connection)
        repo = PostgresC9CommandRepository(connection, SCOPE)
        original = repo.submit(
            _command(command_id="cmd-c9-pg-conflict", request_digest="a" * 64)
        )
        assert original.receipt_ref
        with pytest.raises(C9CommandConflict):
            repo.submit(
                _command(
                    command_id="cmd-c9-pg-conflict",
                    request_digest="b" * 64,
                    payload={
                        "projection_id": "projection.changed.v1",
                        **SOURCE_IDENTITY,
                    },
                )
            )
        assert _idempotency_row_count(connection) == 1


def test_command_repository_concurrent_duplicate_is_one_receipt_one_row(
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, _ = database
    with engine.begin() as connection:
        _seed_authority(connection)
    command = _command(command_id="cmd-c9-pg-concurrent")

    def submit_once() -> str:
        with engine.connect() as connection, connection.begin():
            return (
                PostgresC9CommandRepository(connection, SCOPE)
                .submit(command)
                .receipt_ref
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(submit_once) for _ in range(2)]
        receipts = {future.result() for future in futures}
    assert len(receipts) == 1
    with engine.begin() as connection:
        assert _idempotency_row_count(connection) == 1


def test_command_repository_effect_boundary_rejects_scope_actor_approval_grant(
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, _ = database
    with engine.begin() as connection:
        _seed_authority(connection)
        repo = PostgresC9CommandRepository(connection, SCOPE)

        wrong_scope = RuntimeScope(
            project_scope=SCOPE.project_scope,
            actor_id="actor:different",
        )
        with pytest.raises(C9CommandBlocked):
            PostgresC9CommandRepository(connection, wrong_scope).submit(
                _command(actor_ref="actor:different")
            )

        with pytest.raises(C9CommandBlocked):
            repo.submit(_command(actor_ref="actor:smuggled"))

        with pytest.raises(C9CommandBlocked):
            repo.submit(_command(approval_locator="approval:missing"))

        connection.execute(
            sa.delete(PUBLIC_TABLES["runtime_authority_grants"]).where(
                PUBLIC_TABLES["runtime_authority_grants"].c.project_key == PROJECT_KEY
            )
        )
        with pytest.raises(C9CommandBlocked):
            repo.submit(_command(command_id="cmd-c9-pg-no-grant"))


def test_command_repository_expected_base_mismatch_is_typed_conflict(
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, project = database
    with engine.begin() as connection:
        _seed_authority(connection)
        _seed_sources(connection, project)
        source_digest, _ = _source_digest(connection, project)
        _initialize_offset(connection, project, source_digest)
        repo = PostgresC9CommandRepository(connection, SCOPE)
        matching = _command(
            expected_base_token=(
                f"generation:0|revision:0|incarnation:{SCOPE_INCARNATION}"
            )
        )
        assert repo.submit(matching).receipt_ref
        with pytest.raises(C9CommandBaseConflict):
            repo.submit(
                _command(
                    command_id="cmd-c9-pg-stale-base",
                    expected_base_token=(
                        f"generation:1|revision:1|incarnation:{SCOPE_INCARNATION}"
                    ),
                )
            )


def test_facade_effect_authority_failures_are_typed_envelopes(
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, _ = database
    with engine.begin() as connection:
        _seed_authority(connection)
        repo = PostgresC9CommandRepository(connection, SCOPE)
        facade = SuccessorRuntimeFacade(
            submission_port=repo,
            query_port=PostgresC9QueryRepository(connection, SCOPE),
        )
        blocked = facade.submit(
            _command(
                command_id="cmd-c9-pg-blocked",
                approval_locator="approval:missing",
            )
        )
        assert blocked.status == "blocked"
        assert blocked.error is not None
        assert blocked.error.code == "COMMAND_BLOCKED"
        assert blocked.data is None
        base_conflict = facade.submit(
            _command(
                command_id="cmd-c9-pg-base",
                expected_base_token="generation:9|revision:9|incarnation:wrong",
            )
        )
        assert base_conflict.status == "conflict"
        assert base_conflict.error is not None
        assert base_conflict.error.code == "COMMAND_BASE_CONFLICT"


def test_command_repository_replay_returns_persisted_authority_after_grant_change(
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, _ = database
    with engine.begin() as connection:
        _seed_authority(connection)
        repo = PostgresC9CommandRepository(connection, SCOPE)
        first = repo.submit(_command(command_id="cmd-c9-pg-auth-replay"))
        persisted_digest = first.authority_context_digest
        persisted_epoch = first.grant_epoch
        persisted_observed = first.observed_at
        assert persisted_digest is not None
        assert persisted_epoch == 1
        assert persisted_observed is not None
        connection.execute(
            sa.delete(PUBLIC_TABLES["runtime_authority_grants"]).where(
                PUBLIC_TABLES["runtime_authority_grants"].c.project_key == PROJECT_KEY
            )
        )
        second = repo.submit(_command(command_id="cmd-c9-pg-auth-replay"))
        assert second.authority_context_digest == persisted_digest
        assert second.grant_epoch == persisted_epoch
        assert second.observed_at == persisted_observed


def test_command_repository_rejects_foreign_request_scope(
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, _ = database
    foreign_scope = ProjectScopeRef(
        project_key="p4-c9-foreign",
        resolved_schema="mrw_p4_c9_foreign",
        project_registry_revision=1,
        incarnation="scope-inc-c9-foreign",
        scope_digest="e" * 64,
    )
    with engine.begin() as connection:
        _seed_authority(connection)
        repo = PostgresC9CommandRepository(connection, SCOPE)
        foreign_command = FacadeCommandV2(
            command_id="cmd-c9-pg-foreign",
            command_kind="rebuild_projection",
            description="foreign scope command",
            project_scope_ref=foreign_scope,
            actor_ref=ACTOR,
            idempotency_key="a" * 64,
            expected_base_token=None,
            meta=CommandMetaV2(
                project_key=foreign_scope.project_key,
                trace_id="trace-c9-pg",
                command_id="cmd-c9-pg-foreign",
                project_scope_ref=foreign_scope,
            ),
            payload={"projection_id": PROJECTION_ID, **SOURCE_IDENTITY},
        )
        with pytest.raises(C9CommandBlocked):
            repo.submit(foreign_command)

        foreign_query = _query()
        foreign_query = FacadeQueryV2(
            query_id=foreign_query.query_id,
            query_kind=foreign_query.query_kind,
            project_scope_ref=foreign_scope,
            actor_ref=ACTOR,
            meta=QueryMetaV2(
                project_key=foreign_scope.project_key,
                trace_id="trace-c9-pg",
                query_id=foreign_query.query_id,
                project_scope_ref=foreign_scope,
            ),
            params=foreign_query.params,
        )
        with pytest.raises(C9CommandBlocked):
            PostgresC9QueryRepository(connection, SCOPE).read(foreign_query)


def test_command_repository_approval_binds_exact_request_digest(
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, _ = database
    with engine.begin() as connection:
        _seed_authority(connection)
        repo = PostgresC9CommandRepository(connection, SCOPE)
        with pytest.raises(C9CommandBlocked):
            repo.submit(
                _command(
                    command_id="cmd-c9-pg-unrelated-approval",
                    approval_locator=APPROVAL_ID,
                )
            )
        _seed_approval_for_digest(connection, "approval:c9:exact", "a" * 64)
        receipt = repo.submit(
            _command(
                command_id="cmd-c9-pg-bound-approval",
                request_digest="a" * 64,
                approval_locator="approval:c9:exact",
            )
        )
        assert receipt.receipt_ref


def test_command_same_id_changed_base_or_approval_conflicts(
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, project = database
    with engine.begin() as connection:
        _seed_authority(connection)
        _seed_sources(connection, project)
        source_digest, _ = _source_digest(connection, project)
        _initialize_offset(connection, project, source_digest)
        repo = PostgresC9CommandRepository(connection, SCOPE)
        matching_base = f"generation:0|revision:0|incarnation:{SCOPE_INCARNATION}"
        assert repo.submit(
            _command(
                command_id="cmd-c9-pg-base-change",
                expected_base_token=matching_base,
            )
        ).receipt_ref
        with pytest.raises(C9CommandConflict):
            repo.submit(
                _command(
                    command_id="cmd-c9-pg-base-change",
                    expected_base_token=(
                        f"generation:1|revision:1|incarnation:{SCOPE_INCARNATION}"
                    ),
                )
            )

        _seed_approval_for_digest(connection, "approval:c9:exact-1", "a" * 64)
        _seed_approval_for_digest(connection, "approval:c9:exact-2", "b" * 64)
        assert repo.submit(
            _command(
                command_id="cmd-c9-pg-approval-change",
                request_digest="a" * 64,
                approval_locator="approval:c9:exact-1",
            )
        ).receipt_ref
        with pytest.raises(C9CommandConflict):
            repo.submit(
                _command(
                    command_id="cmd-c9-pg-approval-change",
                    request_digest="b" * 64,
                    approval_locator="approval:c9:exact-2",
                )
            )
        assert _idempotency_row_count(connection) == 2


def test_typed_rejection_leaves_zero_residue_and_same_id_can_succeed(
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, project = database
    foreign_scope = ProjectScopeRef(
        project_key="p4-c9-foreign-residue",
        resolved_schema="mrw_p4_c9_foreign_residue",
        project_registry_revision=1,
        incarnation="scope-inc-c9-foreign-residue",
        scope_digest="e" * 64,
    )
    with engine.begin() as connection:
        _seed_authority(connection)
        repo = PostgresC9CommandRepository(connection, SCOPE)

        def counts() -> tuple[int, int]:
            return (
                _idempotency_row_count(connection),
                _command_receipt_count(connection, project),
            )

        with pytest.raises(C9CommandBlocked):
            repo.submit(
                _command(
                    command_id="cmd-c9-pg-residue-approval",
                    approval_locator=APPROVAL_ID,
                )
            )
        assert counts() == (0, 0)

        with pytest.raises(C9CommandBaseConflict):
            repo.submit(
                _command(
                    command_id="cmd-c9-pg-residue-base",
                    expected_base_token=(
                        "generation:1|revision:1|incarnation:wrong-inc"
                    ),
                )
            )
        assert counts() == (0, 0)

        foreign_command = FacadeCommandV2(
            command_id="cmd-c9-pg-residue-foreign",
            command_kind="rebuild_projection",
            description="foreign scope command",
            project_scope_ref=foreign_scope,
            actor_ref=ACTOR,
            idempotency_key="a" * 64,
            expected_base_token=None,
            meta=CommandMetaV2(
                project_key=foreign_scope.project_key,
                trace_id="trace-c9-pg",
                command_id="cmd-c9-pg-residue-foreign",
                project_scope_ref=foreign_scope,
            ),
            payload={"projection_id": PROJECTION_ID, **SOURCE_IDENTITY},
        )
        with pytest.raises(C9CommandBlocked):
            repo.submit(foreign_command)
        assert counts() == (0, 0)

        connection.execute(
            sa.delete(PUBLIC_TABLES["runtime_authority_grants"]).where(
                PUBLIC_TABLES["runtime_authority_grants"].c.project_key == PROJECT_KEY
            )
        )
        with pytest.raises(C9CommandBlocked):
            repo.submit(_command(command_id="cmd-c9-pg-residue-auth"))
        assert counts() == (0, 0)

        _seed_grant(connection)
        receipt = repo.submit(_command(command_id="cmd-c9-pg-residue-approval"))
        assert receipt.receipt_ref
        assert counts() == (1, 1)

        with pytest.raises(C9CommandConflict):
            repo.submit(
                _command(
                    command_id="cmd-c9-pg-residue-approval",
                    request_digest="b" * 64,
                )
            )
        assert counts() == (1, 1)


def test_crash_window_rollback_leaves_no_partial_and_same_id_succeeds(
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, project = database
    command_id = "cmd-c9-pg-crash-window"
    with engine.connect() as connection, connection.begin() as transaction:
        _seed_authority(connection)
        PostgresC9CommandRepository(connection, SCOPE).submit(
            _command(command_id=command_id)
        )
        transaction.rollback()
    with engine.begin() as connection:
        assert _idempotency_row_count(connection) == 0
        assert _command_receipt_count(connection, project) == 0
        _seed_authority(connection)
        receipt = PostgresC9CommandRepository(connection, SCOPE).submit(
            _command(command_id=command_id)
        )
        assert receipt.receipt_ref
        assert _idempotency_row_count(connection) == 1
        assert _command_receipt_count(connection, project) == 1


class _FailingReceiptRepository:
    def __init__(self, connection: Any, tables: Any) -> None:
        pass

    def put_exact(self, **kwargs: Any) -> str:
        raise RuntimeError("injected receipt write failure")


def test_receipt_failure_inside_savepoint_commits_zero_partial(
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, project = database
    with engine.begin() as connection:
        _seed_authority(connection)
        repo = PostgresC9CommandRepository(connection, SCOPE)
        facade = SuccessorRuntimeFacade(
            submission_port=repo,
            query_port=PostgresC9QueryRepository(connection, SCOPE),
        )
        original = facade_commands_module.ReceiptRepository
        facade_commands_module.ReceiptRepository = _FailingReceiptRepository
        try:
            envelope = facade.submit(_command(command_id="cmd-c9-pg-fault"))
        finally:
            facade_commands_module.ReceiptRepository = original
        assert envelope.status == "error"
        assert envelope.error is not None
        assert envelope.error.code == "COMMAND_FAILED"
        assert _idempotency_row_count(connection) == 0
        assert _command_receipt_count(connection, project) == 0
    with engine.begin() as connection:
        assert _idempotency_row_count(connection) == 0
        assert _command_receipt_count(connection, project) == 0
        repo = PostgresC9CommandRepository(connection, SCOPE)
        receipt = repo.submit(_command(command_id="cmd-c9-pg-fault"))
        assert receipt.receipt_ref
        assert _idempotency_row_count(connection) == 1
        assert _command_receipt_count(connection, project) == 1


class _AckLossSavepoint:
    def __init__(self, real: Any) -> None:
        self._real = real

    @property
    def is_active(self) -> bool:
        return self._real.is_active

    def commit(self) -> None:
        self._real.commit()
        raise RuntimeError("simulated ACK loss after real commit")

    def rollback(self) -> None:
        self._real.rollback()


class _CommitFailureBeforeDurableSavepoint:
    def __init__(self, real: Any) -> None:
        self._real = real

    @property
    def is_active(self) -> bool:
        return self._real.is_active

    def commit(self) -> None:
        raise RuntimeError("simulated commit failure before durable")

    def rollback(self) -> None:
        self._real.rollback()


class _PartialCommitSavepoint:
    def __init__(
        self,
        real: Any,
        connection: Any,
        project: ProjectTables,
        receipt_id: str,
    ) -> None:
        self._real = real
        self._connection = connection
        self._project = project
        self._receipt_id = receipt_id

    @property
    def is_active(self) -> bool:
        return self._real.is_active

    def commit(self) -> None:
        self._real.commit()
        self._connection.execute(
            sa.delete(self._project.successor_receipts).where(
                self._project.successor_receipts.c.project_key == PROJECT_KEY,
                self._project.successor_receipts.c.receipt_id == self._receipt_id,
            )
        )
        raise RuntimeError("simulated ACK loss with partial committed state")

    def rollback(self) -> None:
        self._real.rollback()


def test_commit_ack_loss_after_real_commit_readback_first_returns_success(
    monkeypatch: pytest.MonkeyPatch,
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, project = database
    original = sa.engine.Connection.begin_nested

    def ack_loss_begin_nested(self: Any) -> Any:
        return _AckLossSavepoint(original(self))

    monkeypatch.setattr(sa.engine.Connection, "begin_nested", ack_loss_begin_nested)
    with engine.begin() as connection:
        _seed_authority(connection)
        repo = PostgresC9CommandRepository(connection, SCOPE)
        facade = SuccessorRuntimeFacade(
            submission_port=repo,
            query_port=PostgresC9QueryRepository(connection, SCOPE),
        )
        envelope = facade.submit(_command(command_id="cmd-c9-pg-ack-loss"))
        assert envelope.status in {"ok", "waiting"}
        assert envelope.error is None
        assert envelope.data is not None
        receipt_ref = envelope.data["receipt_ref"]
        assert _idempotency_row_count(connection) == 1
        assert _command_receipt_count(connection, project) == 1
    with engine.begin() as connection:
        assert _idempotency_row_count(connection) == 1
        assert _command_receipt_count(connection, project) == 1
        replayed = PostgresC9CommandRepository(connection, SCOPE).submit(
            _command(command_id="cmd-c9-pg-ack-loss")
        )
        assert replayed.receipt_ref == receipt_ref


def test_commit_failure_before_durable_is_error_and_zero_residue(
    monkeypatch: pytest.MonkeyPatch,
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, project = database
    original = sa.engine.Connection.begin_nested

    def failing_begin_nested(self: Any) -> Any:
        return _CommitFailureBeforeDurableSavepoint(original(self))

    monkeypatch.setattr(sa.engine.Connection, "begin_nested", failing_begin_nested)
    with engine.begin() as connection:
        _seed_authority(connection)
        repo = PostgresC9CommandRepository(connection, SCOPE)
        facade = SuccessorRuntimeFacade(
            submission_port=repo,
            query_port=PostgresC9QueryRepository(connection, SCOPE),
        )
        envelope = facade.submit(_command(command_id="cmd-c9-pg-commit-fail"))
        assert envelope.status == "error"
        assert envelope.error is not None
        assert envelope.error.code == "COMMAND_FAILED"
        assert _idempotency_row_count(connection) == 0
        assert _command_receipt_count(connection, project) == 0
    with engine.begin() as connection:
        assert _idempotency_row_count(connection) == 0
        assert _command_receipt_count(connection, project) == 0


def test_inconsistent_partial_commit_fatal_escapes_facade_and_outer_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, project = database
    original = sa.engine.Connection.begin_nested
    command = _command(command_id="cmd-c9-pg-fatal-partial")
    receipt_id = f"c9:command-receipt:{sha256_hex(command.command_id)[:16]}"

    def partial_begin_nested(self: Any) -> Any:
        return _PartialCommitSavepoint(original(self), self, project, receipt_id)

    monkeypatch.setattr(sa.engine.Connection, "begin_nested", partial_begin_nested)
    with pytest.raises(C9TransactionFatal), engine.begin() as connection:
        _seed_authority(connection)
        repo = PostgresC9CommandRepository(connection, SCOPE)
        facade = SuccessorRuntimeFacade(
            submission_port=repo,
            query_port=PostgresC9QueryRepository(connection, SCOPE),
        )
        facade.submit(command)
    with engine.begin() as connection:
        assert _idempotency_row_count(connection) == 0
        assert _command_receipt_count(connection, project) == 0


def test_rebuild_rejects_caller_forged_source_digest(
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, project = database
    with engine.begin() as connection:
        _seed_sources(connection, project)
        source_digest, _ = _source_digest(connection, project)
        _initialize_offset(connection, project, source_digest)
        rebuilder = PostgresC9ProjectionRebuilder(connection, SCOPE, tables=project)
        with pytest.raises(C9Unavailable) as excinfo:
            rebuilder.rebuild(
                key=_key(),
                source_revision=SOURCE_REVISION,
                source_digest="f" * 64,
                source_ref=SOURCE_REF,
            )
        assert "forged" in str(excinfo.value)
        assert rebuilder.readback(_key())["projection_generation"] == 0


def test_rebuild_offset_a_rejects_source_b_activation(
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, project = database
    other_ref = "project:other:semantic-sources"
    with engine.begin() as connection:
        _seed_sources(connection, project)
        digest_a, _ = _source_digest(connection, project)
        _initialize_offset(connection, project, digest_a)
        rebuilder = PostgresC9ProjectionRebuilder(connection, SCOPE, tables=project)
        with pytest.raises(C9Unavailable) as excinfo:
            rebuilder.rebuild(
                key=_key(),
                source_revision=SOURCE_REVISION,
                source_digest=digest_a,
                source_ref=other_ref,
            )
        assert "offset A cannot be activated by source B" in str(excinfo.value)
        assert rebuilder.readback(_key())["projection_generation"] == 0


def test_rebuild_rollback_restores_prior_source_binding(
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, project = database
    with engine.begin() as connection:
        _seed_sources(connection, project)
        digest0, _ = _source_digest(connection, project)
        _initialize_offset(connection, project, digest0)
        rebuilder = PostgresC9ProjectionRebuilder(connection, SCOPE, tables=project)
        outcome = rebuilder.rebuild(
            key=_key(),
            source_revision=SOURCE_REVISION,
            source_digest=digest0,
            source_ref=SOURCE_REF,
        )
        assert outcome.generation_activated is True
        assert outcome.generation == 1
        assert outcome.source_digest == digest0
        rolled = rebuilder.rollback(key=_key(), target_generation=0)
        assert int(rolled["projection_generation"]) == 0
        assert rolled["source_digest"] == digest0
        assert "c9:generation:0:" in rolled["offset_ref"]
        active = rebuilder.readback(_key())
        assert active["projection_generation"] == 0
        assert active["source_digest"] == digest0
        assert len(active["candidates"]) == 3
        assert len(rebuilder.readback(_key(), generation=1)["candidates"]) == 3


def test_rebuild_full_activation_candidates_receipts_and_declared_loss(
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, project = database
    with engine.begin() as connection:
        _seed_sources(connection, project)
        source_digest, _ = _source_digest(connection, project)
        _initialize_offset(connection, project, source_digest)
        rebuilder = PostgresC9ProjectionRebuilder(connection, SCOPE, tables=project)
        outcome = rebuilder.rebuild(
            key=_key(),
            source_revision=SOURCE_REVISION,
            source_digest=source_digest,
            source_ref=SOURCE_REF,
        )
        assert outcome.generation_activated is True
        assert outcome.generation == 1
        assert outcome.activated_offset is not None
        assert int(outcome.activated_offset["projection_generation"]) == 1
        written = {
            status.sink
            for status in outcome.sink_statuses
            if status.outcome == "LOCAL_WRITTEN"
        }
        assert written == set(REQUIRED_LOCAL_SINKS)
        declared = {
            status.sink
            for status in outcome.sink_statuses
            if status.outcome == "DECLARED_LOSS_NO_CALL"
        }
        assert declared == set(EXTERNAL_DECLARED_LOSS_SINKS)
        assert "graph_provider" in declared
        for status in outcome.sink_statuses:
            assert status.declared_loss == build_loss_profile(status.sink)
            if status.outcome == "DECLARED_LOSS_NO_CALL":
                assert status.declared_loss == ("DECLARED_LOSS", "no provider call")
        candidates = (
            connection.execute(
                sa.select(project.successor_values.c.value_id).where(
                    project.successor_values.c.project_key == PROJECT_KEY,
                    project.successor_values.c.object_type.in_(
                        tuple(CANDIDATE_OBJECT_TYPES.values())
                    ),
                )
            )
            .scalars()
            .all()
        )
        assert len(candidates) == 6
        receipts = (
            connection.execute(
                sa.select(
                    project.successor_receipts.c.receipt_id,
                    project.successor_receipts.c.receipt_digest,
                    project.successor_receipts.c.receipt_json,
                    project.successor_receipts.c.outcome_time,
                ).where(project.successor_receipts.c.project_key == PROJECT_KEY)
            )
            .mappings()
            .all()
        )
        assert len(receipts) == 6
        for receipt in receipts:
            assert receipt["outcome_time"].year > 1970
            content = dict(receipt["receipt_json"])
            assert "observed_at" not in content
            assert "outcome_time" not in content
            assert sha256_hex(content) == receipt["receipt_digest"]


class FailingSinkWriter:
    def __init__(self, delegate: Any, fail_sinks: set[str]) -> None:
        self.delegate = delegate
        self.fail_sinks = fail_sinks

    def write_candidate(self, **kwargs: Any) -> Any:
        if kwargs["sink"] in self.fail_sinks:
            raise RuntimeError("required sink failed")
        return self.delegate.write_candidate(**kwargs)

    def write_receipt(self, **kwargs: Any) -> str:
        return self.delegate.write_receipt(**kwargs)


def test_rebuild_required_sink_failure_does_not_activate_and_retry_is_idempotent(
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, project = database
    with engine.begin() as connection:
        _seed_sources(connection, project)
        source_digest, _ = _source_digest(connection, project)
        _initialize_offset(connection, project, source_digest)
        rebuilder = PostgresC9ProjectionRebuilder(connection, SCOPE, tables=project)
        failing = FailingSinkWriter(
            PostgresProjectionSinkWriter(connection, SCOPE, project),
            {"graph"},
        )
        outcome = rebuilder.rebuild(
            key=_key(),
            source_revision=SOURCE_REVISION,
            source_digest=source_digest,
            source_ref=SOURCE_REF,
            writer=failing,
        )
        assert outcome.generation_activated is False
        assert "c9:repair:required-sink:graph" in outcome.repair_refs
        offset = rebuilder.readback(_key())
        assert offset["projection_generation"] == 0

        healthy_first = rebuilder.rebuild(
            key=_key(),
            source_revision=SOURCE_REVISION,
            source_digest=source_digest,
            source_ref=SOURCE_REF,
        )
        healthy_second = rebuilder.rebuild(
            key=_key(),
            source_revision=SOURCE_REVISION,
            source_digest=source_digest,
            source_ref=SOURCE_REF,
        )
        assert outcome.rebuild_id == healthy_first.rebuild_id
        assert healthy_first.generation_activated is True
        assert healthy_first.generation == 1
        assert healthy_second.generation == 2
        first_refs = {
            status.receipt_ref
            for status in healthy_first.sink_statuses
            if status.receipt_ref is not None
        }
        assert len(first_refs) == 3
        receipts = (
            connection.execute(
                sa.select(project.successor_receipts.c.receipt_id).where(
                    project.successor_receipts.c.project_key == PROJECT_KEY
                )
            )
            .scalars()
            .all()
        )
        assert len(receipts) == 9


def test_rebuild_prior_generation_rollback_and_readback(
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, project = database
    with engine.begin() as connection:
        _seed_sources(connection, project)
        source_digest, _ = _source_digest(connection, project)
        _initialize_offset(connection, project, source_digest)
        rebuilder = PostgresC9ProjectionRebuilder(connection, SCOPE, tables=project)
        rebuilder.rebuild(
            key=_key(),
            source_revision=SOURCE_REVISION,
            source_digest=source_digest,
            source_ref=SOURCE_REF,
        )
        active = rebuilder.readback(_key())
        assert active["projection_generation"] == 1
        rolled = rebuilder.rollback(key=_key(), target_generation=0)
        assert int(rolled["projection_generation"]) == 0
        assert "c9:generation:0:" in rolled["offset_ref"]
        receipt_count = connection.execute(
            sa.select(sa.func.count())
            .select_from(project.successor_receipts)
            .where(project.successor_receipts.c.project_key == PROJECT_KEY)
        ).scalar()
        assert receipt_count == 7
        source_count = connection.execute(
            sa.select(sa.func.count())
            .select_from(project.successor_values)
            .where(
                project.successor_values.c.project_key == PROJECT_KEY,
                project.successor_values.c.value_id.like("c9:semantic-source:%"),
            )
        ).scalar()
        # Three immutable typed source rows plus one immutable exact-closure
        # manifest remain available across projection rollback.
        assert source_count == 4
        rolled_back = rebuilder.readback(_key())
        assert rolled_back["projection_generation"] == 0
        assert len(rolled_back["candidates"]) == 3
        retried = rebuilder.rollback_with_receipt(key=_key(), target_generation=0)
        assert retried.offset_revision == int(rolled["revision"])


def test_rebuild_activation_cas_rejects_stale_expectation(
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, project = database
    with engine.begin() as connection:
        _seed_sources(connection, project)
        source_digest, _ = _source_digest(connection, project)
        _initialize_offset(connection, project, source_digest)
        rebuilder = PostgresC9ProjectionRebuilder(connection, SCOPE, tables=project)
        rebuilder.rebuild(
            key=_key(),
            source_revision=SOURCE_REVISION,
            source_digest=source_digest,
            source_ref=SOURCE_REF,
        )
        stale = dict(
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_projection_offsets"]).where(
                    PUBLIC_TABLES["runtime_projection_offsets"].c.project_key
                    == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_projection_offsets"].c.projector_id
                    == _key().projector_id,
                    PUBLIC_TABLES["runtime_projection_offsets"].c.projector_version
                    == _key().projector_version,
                    PUBLIC_TABLES["runtime_projection_offsets"].c.source_kind
                    == _key().source_kind,
                    PUBLIC_TABLES["runtime_projection_offsets"].c.source_ref
                    == _key().source_ref,
                    PUBLIC_TABLES["runtime_projection_offsets"].c.source_incarnation
                    == _key().source_incarnation,
                )
            )
            .mappings()
            .one()
        )
        stale["revision"] = 0
        with pytest.raises(StaleRevisionError):
            rebuilder._activate_generation(
                stale,
                key=_key(),
                next_generation=2,
                source_revision=SOURCE_REVISION,
                source_digest=source_digest,
                offset_ref="value:stale:generation:2",
            )
        fresh = rebuilder.readback(_key())
        assert fresh["projection_generation"] == 1


def test_rebuild_isolates_candidates_by_source_key_and_generation(
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, project = database
    other_ref = "project:other:semantic-sources"
    with engine.begin() as connection:
        _seed_sources(connection, project)
        first_digest, _ = _source_digest(connection, project)
        _initialize_offset(connection, project, first_digest)
        rebuilder = PostgresC9ProjectionRebuilder(connection, SCOPE, tables=project)
        rebuilder.rebuild(
            key=_key(),
            source_revision=SOURCE_REVISION,
            source_digest=first_digest,
            source_ref=SOURCE_REF,
        )
        with pytest.raises(C9Unavailable):
            rebuilder.rebuild(
                key=_key(other_ref),
                source_revision=SOURCE_REVISION,
                source_digest=first_digest,
                source_ref=other_ref,
            )
        first_readback = rebuilder.readback(_key())
        assert first_readback["projection_generation"] == 1
        assert len(first_readback["candidates"]) == 3
        rebuilder.rollback(key=_key(), target_generation=0)
        assert rebuilder.readback(_key())["projection_generation"] == 0
        assert len(rebuilder.readback(_key())["candidates"]) == 3


def test_query_repository_fresh_session_readback_no_memory_fallback(
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, project = database
    with engine.begin() as connection:
        _seed_authority(connection)
        _seed_sources(connection, project)
        source_digest, _ = _source_digest(connection, project)
        _initialize_offset(connection, project, source_digest)
        PostgresC9ProjectionRebuilder(connection, SCOPE, tables=project).rebuild(
            key=_key(),
            source_revision=SOURCE_REVISION,
            source_digest=source_digest,
            source_ref=SOURCE_REF,
        )
        first = PostgresC9ProjectionRebuilder(
            connection, SCOPE, tables=project
        ).readback(_key())
    with engine.connect() as connection:
        second = PostgresC9ProjectionRebuilder(
            connection, SCOPE, tables=project
        ).readback(_key())
        query_result = PostgresC9QueryRepository(connection, SCOPE).read(_query())
    assert first["projection_generation"] == 1
    assert second["projection_generation"] == 1
    assert second["candidates"] == first["candidates"]
    assert second["fresh_session"] is True
    assert query_result.data.projection_generation == 1
    assert query_result.data.offset_revision == 1
    assert query_result.data.source_ref == SOURCE_REF
    assert query_result.data.source_incarnation == SCOPE_INCARNATION
    assert query_result.data.projector_id == PROJECTOR_ID
    assert query_result.data.projection_revision == 1
    assert query_result.data.source_digest == source_digest
    assert query_result.data.cursor == SOURCE_REVISION
    assert query_result.data.candidate_values
    candidate = query_result.data.candidate_values[0]
    assert candidate.value_id
    assert candidate.value_ref.startswith(f"value:{PROJECT_SCHEMA}:")
    assert len(candidate.content_digest) == 64
    assert candidate.byte_size >= 0
    assert query_result.meta.projector_id == query_result.data.projector_id
    assert query_result.meta.projector_version == query_result.data.projector_version
    assert query_result.meta.source_kind == query_result.data.source_kind
    assert query_result.meta.source_ref == query_result.data.source_ref
    assert query_result.meta.source_incarnation == query_result.data.source_incarnation
    assert query_result.meta.projection_generation == 1
    assert query_result.meta.offset_revision == 1
    assert query_result.meta.source_digest == source_digest
    assert query_result.meta.projection_revision == 1


def _ready_projection(
    connection: Any,
    project: ProjectTables,
) -> tuple[str, str]:
    _seed_authority(connection)
    _seed_sources(connection, project)
    source_digest, _ = _source_digest(connection, project)
    _initialize_offset(connection, project, source_digest)
    PostgresC9ProjectionRebuilder(connection, SCOPE, tables=project).rebuild(
        key=_key(),
        source_revision=SOURCE_REVISION,
        source_digest=source_digest,
        source_ref=SOURCE_REF,
    )
    query_result = PostgresC9QueryRepository(connection, SCOPE).read(_query())
    assert len(query_result.data.candidate_values) == 3
    graph_value_id = next(
        value.value_id
        for value in query_result.data.candidate_values
        if value.value_id.startswith("c9:graph:")
    )
    return source_digest, graph_value_id


def _query_facade(connection: Any) -> SuccessorRuntimeFacade:
    return SuccessorRuntimeFacade(
        submission_port=PostgresC9CommandRepository(connection, SCOPE),
        query_port=PostgresC9QueryRepository(connection, SCOPE),
    )


def test_query_rejects_missing_required_sink_candidate(
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, project = database
    with engine.begin() as connection:
        _, graph_value_id = _ready_projection(connection, project)
        connection.execute(
            sa.delete(project.successor_values).where(
                project.successor_values.c.project_key == PROJECT_KEY,
                project.successor_values.c.value_id == graph_value_id,
            )
        )
        with pytest.raises(C9Unavailable):
            PostgresC9QueryRepository(connection, SCOPE).read(_query())
        envelope = _query_facade(connection).query(_query())
        assert envelope.status == "unavailable"
        assert envelope.error is not None
        assert envelope.error.code == "QUERY_UNAVAILABLE"
        remaining = connection.execute(
            sa.select(sa.func.count())
            .select_from(project.successor_values)
            .where(project.successor_values.c.project_key == PROJECT_KEY)
        ).scalar()
        # The versioned semantic-source closure adds one immutable manifest;
        # deleting a projection candidate must not delete that source identity.
        assert remaining == 11


def test_query_rejects_duplicate_required_sink_candidate(
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, project = database
    with engine.begin() as connection:
        _, _ = _ready_projection(connection, project)
        provenance = {
            "projector_id": PROJECTOR_ID,
            "projector_version": PROJECTOR_VERSION,
            "source_kind": "successor_values",
            "source_ref": SOURCE_REF,
            "source_incarnation": SCOPE_INCARNATION,
            "projection_offset_id": "offset:c9-movement:001",
            "sink": "graph",
            "projection_generation": 1,
            "rebuild_id": "rebuild:c9:duplicate",
        }
        content = {
            "schema_version": "mrw.successor.c9.projection-candidate.v1",
            "projection_id": PROJECTION_ID,
            "sink": "graph",
            "projector_id": PROJECTOR_ID,
            "projector_version": PROJECTOR_VERSION,
            "source_kind": "successor_values",
            "source_ref": SOURCE_REF,
            "source_incarnation": SCOPE_INCARNATION,
            "projection_offset_id": "offset:c9-movement:001",
            "projection_generation": 1,
            "source_revision": SOURCE_REVISION,
            "source_digest": sha256_hex({"source": SOURCE_REF}),
            "canonical_source_ref": SOURCE_REF,
            "inputs": [],
            "declared_losses": ["LOCAL_EXACT", "duplicate"],
        }
        digest = sha256_hex(content)
        ValueRepository(connection, project).put_exact(
            scope=SCOPE,
            value_id="c9:graph:duplicate:gen-1:dup",
            object_type="GraphLocalProjection.v1",
            codec_id="mrw.successor.c9.projection-candidate.canonical-json.v1",
            content=content,
            expected_digest=digest,
            provenance_digest=sha256_hex(provenance),
            expected_revision=0,
            expected_incarnation=SCOPE_INCARNATION,
            source_ref=SOURCE_REF,
            provenance=provenance,
            state="AVAILABLE",
        )
        with pytest.raises(C9Unavailable):
            PostgresC9QueryRepository(connection, SCOPE).read(_query())


def test_query_rejects_tampered_candidate_content(
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, project = database
    with engine.begin() as connection:
        _, graph_value_id = _ready_projection(connection, project)
        connection.execute(
            sa.update(project.successor_values)
            .where(
                project.successor_values.c.project_key == PROJECT_KEY,
                project.successor_values.c.value_id == graph_value_id,
            )
            .values(content_json={"tampered": True})
        )
        with pytest.raises(C9Unavailable):
            PostgresC9QueryRepository(connection, SCOPE).read(_query())


def test_query_rejects_wrong_generation_candidate(
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, project = database
    with engine.begin() as connection:
        _, graph_value_id = _ready_projection(connection, project)
        graph_row = connection.execute(
            sa.select(project.successor_values.c.provenance_json).where(
                project.successor_values.c.project_key == PROJECT_KEY,
                project.successor_values.c.value_id == graph_value_id,
            )
        ).scalar_one()
        provenance = dict(graph_row)
        provenance["projection_generation"] = 2
        connection.execute(
            sa.update(project.successor_values)
            .where(
                project.successor_values.c.project_key == PROJECT_KEY,
                project.successor_values.c.value_id == graph_value_id,
            )
            .values(provenance_json=provenance)
        )
        with pytest.raises(C9Unavailable):
            PostgresC9QueryRepository(connection, SCOPE).read(_query())


def test_query_rejects_wrong_source_candidate(
    database: tuple[Engine, ProjectTables],
) -> None:
    engine, project = database
    other_ref = "c9:source-closure:wrong"
    with engine.begin() as connection:
        _, graph_value_id = _ready_projection(connection, project)
        graph_row = connection.execute(
            sa.select(project.successor_values.c.provenance_json).where(
                project.successor_values.c.project_key == PROJECT_KEY,
                project.successor_values.c.value_id == graph_value_id,
            )
        ).scalar_one()
        provenance = dict(graph_row)
        provenance["source_ref"] = other_ref
        connection.execute(
            sa.update(project.successor_values)
            .where(
                project.successor_values.c.project_key == PROJECT_KEY,
                project.successor_values.c.value_id == graph_value_id,
            )
            .values(provenance_json=provenance)
        )
        with pytest.raises(C9Unavailable):
            PostgresC9QueryRepository(connection, SCOPE).read(_query())


def _source_digest(
    connection: Any,
    project: ProjectTables,
    *,
    source_ref: str = SOURCE_REF,
) -> tuple[str, int]:
    assert source_ref == SOURCE_REF
    closure = load_exact_semantic_source_closure(connection, SCOPE)
    return closure.closure_digest, int(closure.revision)
