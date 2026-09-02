"""Real-PostgreSQL delete/rebuild test for the C2.4 terminal projection.

The test owns a disposable database named ``mrw_p3_c2_worker_test``: it drops
any prior database, creates the family-local projection table, applies/rebuilds
/deletes the projection, and drops the database again on teardown.  No shared
migration, catalog, packet or aggregate evidence is touched.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import NullPool

from app.successor_runtime.capabilities.source_library_c2_2 import (
    CollectionCompleted,
)
from app.successor_runtime.capabilities.source_library_c2_4_projection import (
    SourceCollectionProjectionSource,
)
from app.successor_runtime.substrate.projections.source_library_terminal import (
    PostgresSourceLibraryTerminalProjector,
    ProjectionStaleError,
    build_source_library_terminal_table,
)

from .test_p3_c2_4_projection import SCOPE_DIGEST, _record, _terminal

pytestmark = pytest.mark.integration

DATABASE_NAME = "mrw_p3_c2_worker_test"
ENV_URL = "SUCCESSOR_TEST_DATABASE_URL"
_METADATA = sa.MetaData()
PROJECTION_TABLE = build_source_library_terminal_table(_METADATA)


def _server_url() -> str:
    env_url = __import__("os").environ.get(ENV_URL)
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


def _source(
    revision: int = 1, incarnation: str = "inc:p3-c2-4"
) -> SourceCollectionProjectionSource:
    return SourceCollectionProjectionSource(
        source_kind="RUNTIME_JOURNAL",
        source_ref="runtime-run:run:p3-c2-4-pg",
        run_id="run:p3-c2-4-pg",
        run_incarnation="run-inc:p3-c2-4-pg",
        source_revision=revision,
        source_incarnation=incarnation,
        source_digest="",
        project_key="demo_proj",
        project_scope_digest=SCOPE_DIGEST,
        source_mode="site_search",
        collection_outcome=CollectionCompleted(terminal=_terminal(records_count=1)),
        record_refs=(_record(0),),
        ordered_failures=(),
        provider_handoff=None,
        observed_at="2030-09-01T08:00:00Z",
    )


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
        PROJECTION_TABLE.create(connection)
    try:
        yield engine
    finally:
        engine.dispose()
        _drop_database(server)


def test_postgres_apply_rebuild_delete_are_digest_equivalent(
    disposable_database: Engine,
) -> None:
    source = _source()
    with disposable_database.connect() as connection:
        projector = PostgresSourceLibraryTerminalProjector(
            connection,
            project_key="demo_proj",
            table=PROJECTION_TABLE,
        )
        applied = projector.apply(source)
        rebuilt = projector.rebuild(source)
        assert (
            rebuilt.terminal["projection_digest"]
            == applied.terminal["projection_digest"]
        )
        assert rebuilt.compat["compat_digest"] == applied.compat["compat_digest"]
        assert (
            rebuilt.summary["projection_digest"] == applied.summary["projection_digest"]
        )
        assert rebuilt.generation == 1
        loaded = projector.load(source)
        assert (
            loaded.terminal["projection_digest"]
            == applied.terminal["projection_digest"]
        )
        projector.delete(source)
        with pytest.raises(KeyError):
            projector.load(source)


def test_postgres_stale_source_fails_closed(disposable_database: Engine) -> None:
    source = _source()
    with disposable_database.connect() as connection:
        projector = PostgresSourceLibraryTerminalProjector(
            connection,
            project_key="demo_proj",
            table=PROJECTION_TABLE,
        )
        projector.apply(source)
        import dataclasses

        stale_source = dataclasses.replace(
            source,
            source_incarnation="inc:new",
            source_digest="",
        )
        with pytest.raises(ProjectionStaleError):
            projector.apply(stale_source)
        with pytest.raises(ProjectionStaleError):
            projector.load(stale_source)
        wrong_project = dataclasses.replace(
            source,
            project_key="other_project",
            source_digest="",
        )
        with pytest.raises(ProjectionStaleError):
            projector.load(wrong_project)
