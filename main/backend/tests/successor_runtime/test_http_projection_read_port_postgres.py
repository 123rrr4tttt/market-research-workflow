"""HTTP/read-facade projection wiring over real PostgreSQL material canonical.

The suite proves the registry-backed HTTP composition root can answer a
``projection_snapshot`` query with real committed successor data.  It commits
one C7 canonical acceptance document through the repository-owned production
admission runner on a disposable database, then reads it back twice:

1. directly through ``EngineBackedProjectionQueryReadPort`` (repository/facade
   boundary), and
2. through the app.state-backed production router as an HTTP query.

The responses must bind the exact committed content digest and carry
read-only/no-write markers.  No legacy table is created or written and the
   whole database is dropped on teardown.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from app.api import successor_runtime as api_module
from app.settings.config import settings as app_settings
from app.successor_runtime.assembly.app_assembly import (
    SUCCESSOR_DEPENDENCIES_STATE_ATTR,
    build_successor_registry_app_dependencies,
)
from app.successor_runtime.research.codec import canonical_bytes
from app.successor_runtime.runtime.facade_contracts import (
    FacadeQueryV2,
    QueryMetaV2,
)
from app.successor_runtime.substrate.postgres.c7_production_admission import (
    C7ProductionAdmissionInput,
    resolve_active_scope,
    run_c7_production_cutover_admission,
)
from app.successor_runtime.substrate.postgres.c7_projector_driver import (
    MATERIAL_CANONICAL_SOURCE_KIND,
    MATERIAL_PROJECTION_VALUE_PREFIX,
    MATERIAL_SEARCH_PROJECTION_ID,
    MATERIAL_SEARCH_PROJECTION_SCHEMA,
    MATERIAL_SEARCH_PROJECTOR_ID,
    MATERIAL_SEARCH_PROJECTOR_VERSION,
)
from app.successor_runtime.substrate.postgres.projection_sources import (
    build_project_source_closure,
    put_project_source_rows,
)
from app.successor_runtime.substrate.postgres.ingest_c7_movement_admission import (
    C7_MOVEMENT_CANONICAL_DOCUMENTS,
)
from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES, project_tables
from app.successor_runtime.substrate.postgres.projection_query_read_port import (
    ACTIVE_PROJECT_MATERIAL_PROJECTOR_ID,
    ACTIVE_PROJECT_MATERIAL_PROJECTOR_VERSION,
    MATERIAL_DOCUMENT_SOURCE_PREFIX,
    EngineBackedProjectionQueryReadPort,
)
from app.successor_runtime.substrate.postgres.session import compute_scope_digest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.integration

DATABASE_NAME = "mrw_http_projection_read_test"
ENV_URL = "SUCCESSOR_TEST_DATABASE_URL"
PROJECT_KEY = "http-projection-read-demo"
RESOLVED_SCHEMA = "mrw_http_projection_read_demo"
REGISTRY_REVISION = 1
INCARNATION = "scope-inc-http-projection-read"
SCOPE_DIGEST = compute_scope_digest(
    PROJECT_KEY,
    RESOLVED_SCHEMA,
    REGISTRY_REVISION,
    INCARNATION,
)
ACTOR_ID = "actor:http-projection-read"
APPROVAL_REF = "approval:http-projection-read-test"
TRACE_ID = "http-projection-read-acceptance-2026-09-03"
OBJECT_ID = f"ingest-doc:c7-http-projection:{TRACE_ID}"
RAW_BYTES = (
    b'{"title": "HTTP projection read acceptance", '
    b'"text": "Bounded successor read facade evidence on a disposable database."}'
)


def _server_url() -> str:
    env_url = os.environ.get(ENV_URL)
    if env_url:
        url = make_url(env_url)
        return url.set(database="postgres").render_as_string(hide_password=False)
    return "postgresql+psycopg2://localhost/postgres"


def _create_database() -> Engine:
    server = sa.create_engine(
        _server_url(),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    try:
        with server.connect() as connection:
            connection.execute(
                text("DROP DATABASE IF EXISTS " + DATABASE_NAME + " WITH (FORCE)")
            )
            connection.execute(text("CREATE DATABASE " + DATABASE_NAME))
    except OperationalError as exc:  # noqa: BLE001 - environment-dependent skip
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
    project_metadata = sa.MetaData()
    project_tables(project_metadata, RESOLVED_SCHEMA)
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{RESOLVED_SCHEMA}"'))
        for table in PUBLIC_TABLES.values():
            table.create(connection)
        C7_MOVEMENT_CANONICAL_DOCUMENTS.create(connection)
        project_metadata.create_all(connection)
        connection.execute(
            PUBLIC_TABLES["project_scope_registry"]
            .insert()
            .values(
                project_key=PROJECT_KEY,
                registry_revision=REGISTRY_REVISION,
                resolved_schema=RESOLVED_SCHEMA,
                scope_digest=SCOPE_DIGEST,
                incarnation=INCARNATION,
                state="ACTIVE",
                updated_by=ACTOR_ID,
                approval_ref=APPROVAL_REF,
            )
        )
    try:
        yield engine
    finally:
        engine.dispose()
        _drop_database(server)


def _admission_input() -> C7ProductionAdmissionInput:
    return C7ProductionAdmissionInput(
        project_key=PROJECT_KEY,
        trace_id=TRACE_ID,
        actor_id=ACTOR_ID,
        approval_ref=APPROVAL_REF,
        canonical_object_id=OBJECT_ID,
        source_locator="file://disposable/c7-http-projection-acceptance.json",
        raw_bytes=RAW_BYTES,
        raw_incarnation="raw-inc:http-projection-read",
        authority_epoch=1,
    )


def _committed_document(engine: Engine) -> dict[str, object]:
    with engine.connect() as connection:
        row = (
            connection.execute(
                sa.select(C7_MOVEMENT_CANONICAL_DOCUMENTS).where(
                    C7_MOVEMENT_CANONICAL_DOCUMENTS.c.project_key == PROJECT_KEY,
                    C7_MOVEMENT_CANONICAL_DOCUMENTS.c.object_id == OBJECT_ID,
                )
            )
            .mappings()
            .one()
        )
    return {
        "content_digest": str(row["content_digest"]),
        "incarnation": str(row["incarnation"]),
        "revision": int(row["revision"]),
    }


def _scope(engine: Engine):
    with engine.connect() as connection:
        return resolve_active_scope(
            connection,
            project_key=PROJECT_KEY,
            actor_id=ACTOR_ID,
        )


def _query(scope, source_incarnation: str) -> FacadeQueryV2:
    query_id = "q:http-projection-read"
    return FacadeQueryV2(
        query_id=query_id,
        query_kind="projection_snapshot",
        project_scope_ref=scope.project_scope,
        actor_ref=ACTOR_ID,
        meta=QueryMetaV2(
            project_key=scope.project_scope.project_key,
            trace_id="trace:http-projection-read:1",
            query_id=query_id,
            project_scope_ref=scope.project_scope,
        ),
        params={
            "params_kind": "projection_snapshot",
            "projection_id": MATERIAL_SEARCH_PROJECTION_ID,
            "projector_id": MATERIAL_SEARCH_PROJECTOR_ID,
            "projector_version": MATERIAL_SEARCH_PROJECTOR_VERSION,
            "source_kind": MATERIAL_CANONICAL_SOURCE_KIND,
            "source_ref": f"{MATERIAL_DOCUMENT_SOURCE_PREFIX}{OBJECT_ID}",
            "source_incarnation": source_incarnation,
            "page_size": 25,
        },
        read_only=True,
    )


def _active_material_query(scope) -> FacadeQueryV2:
    query_id = "q:http-active-material"
    return FacadeQueryV2(
        query_id=query_id,
        query_kind="projection_snapshot",
        project_scope_ref=scope.project_scope,
        actor_ref=ACTOR_ID,
        meta=QueryMetaV2(
            project_key=scope.project_scope.project_key,
            trace_id="trace:http-active-material",
            query_id=query_id,
            project_scope_ref=scope.project_scope,
        ),
        params={
            "params_kind": "projection_snapshot",
            "projection_id": ACTIVE_PROJECT_MATERIAL_PROJECTOR_ID,
            "projector_id": ACTIVE_PROJECT_MATERIAL_PROJECTOR_ID,
            "projector_version": ACTIVE_PROJECT_MATERIAL_PROJECTOR_VERSION,
            "source_kind": "material",
            "source_ref": f"material:{PROJECT_KEY}",
            "source_incarnation": f"active-project:{PROJECT_KEY}",
            "page_size": 25,
        },
        read_only=True,
    )


def test_committed_document_reads_through_registry_read_port(
    disposable_database: Engine,
) -> None:
    outcome = run_c7_production_cutover_admission(
        disposable_database,
        admission_input=_admission_input(),
    )
    assert outcome.status in {"COMMITTED", "REPLAYED_COMMITTED"}
    committed = _committed_document(disposable_database)
    scope = _scope(disposable_database)
    assert committed["incarnation"] == scope.project_scope.incarnation

    result = EngineBackedProjectionQueryReadPort(
        engine=disposable_database
    ).read(_query(scope, str(committed["incarnation"])))

    assert result.meta.source_digest == committed["content_digest"]
    assert result.meta.project_key == PROJECT_KEY
    assert result.meta.projection_id == MATERIAL_SEARCH_PROJECTION_ID
    assert result.meta.projector_id == MATERIAL_SEARCH_PROJECTOR_ID
    assert result.meta.source_kind == MATERIAL_CANONICAL_SOURCE_KIND
    assert result.meta.cursor == committed["revision"]
    assert result.data.source_digest == result.meta.source_digest
    assert result.data.candidate_values
    candidate = result.data.candidate_values[0]
    assert candidate.sink == "search"
    assert candidate.value_id.startswith(f"{MATERIAL_PROJECTION_VALUE_PREFIX}:search:")
    payload = candidate.payload
    assert candidate.content_digest == hashlib.sha256(
        canonical_bytes(payload)
    ).hexdigest()
    assert payload["schema_version"] == MATERIAL_SEARCH_PROJECTION_SCHEMA
    assert payload["no_postgres_write"] is True
    assert payload["read_only"] is True
    assert payload["document_ref"]["content_digest"] == committed["content_digest"]
    assert payload["document_ref"]["object_id"] == OBJECT_ID


def test_http_query_returns_real_committed_document(
    disposable_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outcome = run_c7_production_cutover_admission(
        disposable_database,
        admission_input=_admission_input(),
    )
    assert outcome.status in {"COMMITTED", "REPLAYED_COMMITTED"}
    committed = _committed_document(disposable_database)
    scope = _scope(disposable_database)

    monkeypatch.setattr(app_settings, "successor_mount_mode", "production_registry")
    monkeypatch.setattr(app_settings, "codex_auth_enabled", True)
    monkeypatch.setattr(app_settings, "successor_production_requires_auth", True)
    dependencies = build_successor_registry_app_dependencies(
        engine=disposable_database,
        actor_provider=lambda request: ACTOR_ID,
    )
    app = FastAPI()
    setattr(app.state, SUCCESSOR_DEPENDENCIES_STATE_ATTR, dependencies)
    app.include_router(
        api_module.create_successor_runtime_state_router(),
        prefix="/api/v1",
    )
    body = {
        "query_id": "q:http-query-real",
        "query_kind": "projection_snapshot",
        "project_locator": PROJECT_KEY,
        "trace_id": "trace:http-projection-read:2",
        "params": {
            "params_kind": "projection_snapshot",
            "projection_id": MATERIAL_SEARCH_PROJECTION_ID,
            "projector_id": MATERIAL_SEARCH_PROJECTOR_ID,
            "projector_version": MATERIAL_SEARCH_PROJECTOR_VERSION,
            "source_kind": MATERIAL_CANONICAL_SOURCE_KIND,
            "source_ref": f"{MATERIAL_DOCUMENT_SOURCE_PREFIX}{OBJECT_ID}",
            "source_incarnation": str(committed["incarnation"]),
            "page_size": 25,
        },
    }
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/material-projections/v2/queries",
            json=body,
        )
    assert response.status_code == 200
    envelope = response.json()
    assert envelope["status"] == "ok", envelope
    assert envelope["control_feedback"] is False
    assert envelope["error"] is None
    meta = envelope["meta"]
    assert meta["project_key"] == PROJECT_KEY
    assert meta["project_scope_ref"]["resolved_schema"] == scope.project_scope.resolved_schema
    assert meta["source_digest"] == committed["content_digest"]
    assert meta["projection_id"] == MATERIAL_SEARCH_PROJECTION_ID
    assert meta["projector_id"] == MATERIAL_SEARCH_PROJECTOR_ID
    assert meta["source_kind"] == MATERIAL_CANONICAL_SOURCE_KIND
    assert envelope["data"]["source_digest"] == committed["content_digest"]
    candidates = envelope["data"]["candidate_values"]
    assert len(candidates) == 1
    assert candidates[0]["sink"] == "search"
    assert candidates[0]["value_id"].startswith(
        f"{MATERIAL_PROJECTION_VALUE_PREFIX}:search:"
    )
    assert candidates[0]["payload"]["schema_version"] == (
        MATERIAL_SEARCH_PROJECTION_SCHEMA
    )
    assert candidates[0]["content_digest"] == hashlib.sha256(
        canonical_bytes(candidates[0]["payload"])
    ).hexdigest()
    assert candidates[0]["payload"]["document_ref"]["object_id"] == OBJECT_ID
    assert candidates[0]["payload"]["no_postgres_write"] is True


def test_active_material_selector_reads_persisted_source_through_http_without_write(
    disposable_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outcome = run_c7_production_cutover_admission(
        disposable_database,
        admission_input=_admission_input(),
    )
    assert outcome.status in {"COMMITTED", "REPLAYED_COMMITTED"}
    scope = _scope(disposable_database)
    with disposable_database.begin() as connection:
        closure = build_project_source_closure(connection, scope)
        persisted = put_project_source_rows(connection, scope, closure)
    assert persisted.closure_digest == closure.closure_digest

    direct = EngineBackedProjectionQueryReadPort(
        engine=disposable_database
    ).read(_active_material_query(scope))
    assert direct.meta.projection_id == ACTIVE_PROJECT_MATERIAL_PROJECTOR_ID
    assert direct.meta.projector_id == "projection.project-source-identity.v2"
    assert direct.meta.projector_version == "2.0.0"
    assert direct.meta.source_kind == "projection_source"
    assert direct.meta.source_ref == f"projection:{PROJECT_KEY}:source"
    assert direct.meta.source_incarnation == scope.project_scope.incarnation
    assert direct.meta.source_digest == closure.closure_digest
    assert len(direct.data.candidate_values) == 1
    direct_candidate = direct.data.candidate_values[0]
    assert direct_candidate.sink == "material"
    assert direct_candidate.payload["schema_version"] == (
        "mrw.projection.material-source.v2"
    )
    assert direct_candidate.payload["material_ref"] == f"material:{PROJECT_KEY}"

    project = project_tables(sa.MetaData(), RESOLVED_SCHEMA)
    with disposable_database.connect() as connection:
        before = {
            "values": connection.execute(
                sa.select(sa.func.count()).select_from(project.successor_values)
            ).scalar_one(),
            "offsets": connection.execute(
                sa.select(sa.func.count()).select_from(
                    PUBLIC_TABLES["runtime_projection_offsets"]
                )
            ).scalar_one(),
        }

    monkeypatch.setattr(app_settings, "successor_mount_mode", "production_registry")
    monkeypatch.setattr(app_settings, "codex_auth_enabled", True)
    monkeypatch.setattr(app_settings, "successor_production_requires_auth", True)
    dependencies = build_successor_registry_app_dependencies(
        engine=disposable_database,
        actor_provider=lambda request: ACTOR_ID,
    )
    app = FastAPI()
    setattr(app.state, SUCCESSOR_DEPENDENCIES_STATE_ATTR, dependencies)
    app.include_router(
        api_module.create_successor_runtime_state_router(),
        prefix="/api/v1",
    )
    query = _active_material_query(scope)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/material-projections/v2/queries",
            json={
                "query_id": query.query_id,
                "query_kind": query.query_kind,
                "project_locator": PROJECT_KEY,
                "trace_id": query.meta.trace_id,
                "params": dict(query.params),
            },
        )
    assert response.status_code == 200
    envelope = response.json()
    assert envelope["status"] == "ok"
    assert envelope["error"] is None
    assert envelope["meta"]["source_digest"] == closure.closure_digest
    assert envelope["meta"]["source_ref"] == f"projection:{PROJECT_KEY}:source"
    candidate = envelope["data"]["candidate_values"][0]
    assert candidate["sink"] == "material"
    assert candidate["payload"]["material_ref"] == f"material:{PROJECT_KEY}"
    assert candidate["payload"]["schema_version"] == (
        "mrw.projection.material-source.v2"
    )

    with disposable_database.connect() as connection:
        after = {
            "values": connection.execute(
                sa.select(sa.func.count()).select_from(project.successor_values)
            ).scalar_one(),
            "offsets": connection.execute(
                sa.select(sa.func.count()).select_from(
                    PUBLIC_TABLES["runtime_projection_offsets"]
                )
            ).scalar_one(),
        }
    assert after == before
