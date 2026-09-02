"""P0-B greenfield durable substrate: session, UoW, and blob store."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.pool import StaticPool

from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
from app.successor_runtime.substrate.blob.store import (
    BLOB_ROOT,
    BlobDigestMismatch,
    BlobNotFound,
    ProjectBlobStore,
    blob_path,
    compute_digest,
    project_blob_root,
)
from app.successor_runtime.substrate.postgres.authority import (
    ProjectScopeRegistryRepository,
)
from app.successor_runtime.substrate.postgres.session import (
    ProjectScopeStale,
    ProjectScopeValidationError,
    RuntimeSessionLocal,
    ServerProjectScopeResolver,
    compute_scope_digest,
    create_runtime_engine,
    default_project_schema_name,
    runtime_connect_args,
    validate_project_schema_identifier,
)
from app.successor_runtime.substrate.postgres.unit_of_work import (
    RuntimeUnitOfWork,
    UnitOfWorkClosed,
)


class _TestRegistryReader:
    def __init__(self, rows: tuple[Mapping[str, Any], ...] = ()) -> None:
        self._rows = rows

    @staticmethod
    def _default_row(project_key: str, revision: int = 0) -> Mapping[str, Any]:
        schema = default_project_schema_name(project_key)
        incarnation = f"scope-incarnation:{project_key}:{revision}"
        return {
            "project_key": project_key,
            "resolved_schema": schema,
            "registry_revision": revision,
            "incarnation": incarnation,
            "scope_digest": compute_scope_digest(
                project_key, schema, revision, incarnation
            ),
            "state": "ACTIVE",
        }

    def current(self, project_key: str) -> Mapping[str, Any]:
        matching = tuple(
            row
            for row in self._rows
            if row["project_key"] == project_key and row["state"] == "ACTIVE"
        )
        if not self._rows:
            return self._default_row(project_key)
        if len(matching) != 1:
            raise ProjectScopeValidationError("test registry current lookup failed")
        return matching[0]

    def expected(
        self, project_key: str, registry_revision: int
    ) -> Mapping[str, Any]:
        matching = tuple(
            row
            for row in self._rows
            if row["project_key"] == project_key
            and row["registry_revision"] == registry_revision
        )
        if not self._rows and registry_revision == 0:
            return self._default_row(project_key, registry_revision)
        if len(matching) != 1:
            raise ProjectScopeValidationError("test registry expected lookup failed")
        return matching[0]


def _resolver(
    rows: tuple[Mapping[str, Any], ...] = (),
) -> ServerProjectScopeResolver:
    return ServerProjectScopeResolver(registry_reader=_TestRegistryReader(rows))


def _scope(resolver: ServerProjectScopeResolver, project_key: str) -> ProjectScopeRef:
    return resolver.resolve(project_key)


def _memory_engine():
    return create_runtime_engine(
        "sqlite+pysqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )


def _create_tables(engine) -> None:
    with RuntimeUnitOfWork(engine=engine) as uow:
        uow.connection.execute(
            text(
                "CREATE TABLE public_runtime "
                "(id INTEGER PRIMARY KEY, payload TEXT)"
            )
        )
        uow.connection.execute(
            text(
                "CREATE TABLE project_values "
                "(id INTEGER PRIMARY KEY, payload TEXT)"
            )
        )
        uow.commit()


class _RecordingRepository:
    def __init__(self, connection, handle, label: str = "default") -> None:
        self.connection = connection
        self.handle = handle
        self.label = label


@pytest.mark.unit
def test_runtime_session_factory_is_fixed_public_and_legacy_free() -> None:
    source = (
        Path(__file__).resolve().parents[2]
        / "app/successor_runtime/substrate/postgres/session.py"
    ).read_text(encoding="utf-8")
    assert "from app.models.base" not in source
    assert "import app.models.base" not in source
    assert "from contextvars import" not in source
    assert "import contextvars" not in source
    assert "current_project_schema" not in source
    assert runtime_connect_args("postgresql+psycopg://u:p@db/app")[
        "options"
    ] == "-c search_path=public"
    assert runtime_connect_args("sqlite+pysqlite://") == {}

    from app.successor_runtime.substrate.postgres.session import RuntimeSession

    engine = _memory_engine()
    local = RuntimeSessionLocal(engine)
    session = local()
    assert isinstance(session, RuntimeSession)
    assert session.autoflush is False
    assert session.get_bind() is engine
    session.close()
    engine.dispose()


@pytest.mark.unit
def test_project_scope_resolver_validates_schema_identifier_and_digest() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        ServerProjectScopeResolver()

    resolver = _resolver()
    ref = _scope(resolver, "demo_proj")
    assert ref.resolved_schema == default_project_schema_name("demo_proj")
    assert ref.resolved_schema.startswith("mrw_p_")
    assert validate_project_schema_identifier(ref.resolved_schema) == ref.resolved_schema
    assert ref.scope_digest == compute_scope_digest(
        ref.project_key,
        ref.resolved_schema,
        ref.project_registry_revision,
        ref.incarnation,
    )

    expected = resolver.resolve_expected(
        ref.project_key, ref.project_registry_revision, ref.scope_digest
    )
    assert expected == ref
    stale = resolver.resolve_expected(
        ref.project_key, ref.project_registry_revision, "0" * 64
    )
    assert isinstance(stale, ProjectScopeStale)
    assert stale.observed_digest == "0" * 64


@pytest.mark.unit
def test_project_scope_identity_rejects_schema_name_aba() -> None:
    project_key = "demo_proj"
    old_schema = "project_old"
    middle_schema = "project_middle"
    old_digest = compute_scope_digest(project_key, old_schema, 1, "scope-inc-1")
    middle_digest = compute_scope_digest(
        project_key, middle_schema, 2, "scope-inc-2"
    )
    aba_digest = compute_scope_digest(project_key, old_schema, 3, "scope-inc-3")
    same_revision_new_incarnation = compute_scope_digest(
        project_key, old_schema, 1, "scope-inc-recreated"
    )

    assert len({old_digest, middle_digest, aba_digest}) == 3
    assert same_revision_new_incarnation != old_digest


@pytest.mark.unit
def test_registry_backed_resolver_and_append_only_scope_successor() -> None:
    engine = _memory_engine()
    connection = engine.connect()
    connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS public")
    connection.exec_driver_sql(
        """
        CREATE TABLE public.project_scope_registry (
            project_key TEXT NOT NULL,
            registry_revision INTEGER NOT NULL,
            resolved_schema TEXT NOT NULL,
            scope_digest TEXT NOT NULL,
            incarnation TEXT NOT NULL,
            state TEXT NOT NULL,
            updated_by TEXT NOT NULL,
            approval_ref TEXT,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL,
            PRIMARY KEY (project_key, registry_revision),
            UNIQUE (project_key, scope_digest),
            UNIQUE (resolved_schema, incarnation)
        )
        """
    )
    old_digest = compute_scope_digest(
        "demo_proj", "project_old", 1, "scope-inc-1"
    )
    connection.execute(
        text(
            """
            INSERT INTO public.project_scope_registry (
                project_key, registry_revision, resolved_schema, scope_digest,
                incarnation, state, updated_by, approval_ref, created_at, updated_at
            ) VALUES (
                'demo_proj', 1, 'project_old', :scope_digest,
                'scope-inc-1', 'ACTIVE', 'bootstrap', 'approval:1',
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        ),
        {"scope_digest": old_digest},
    )
    connection.commit()

    resolver = ServerProjectScopeResolver(connection=connection)
    old_ref = resolver.resolve("demo_proj")
    assert old_ref.incarnation == "scope-inc-1"
    old_scope = RuntimeScope(project_scope=old_ref, actor_id="scope-admin")
    connection.commit()

    middle_digest = compute_scope_digest(
        "demo_proj", "project_middle", 2, "scope-inc-2"
    )
    with connection.begin():
        middle_row = ProjectScopeRegistryRepository(connection, old_scope).revise(
            expected_revision=1,
            resolved_schema="project_middle",
            registry_revision=2,
            scope_digest=middle_digest,
            incarnation="scope-inc-2",
            state="ACTIVE",
            approval_ref="approval:2",
        )
    assert middle_row["registry_revision"] == 2

    # Historical resolution remains possible for runs bound to revision 1.
    historical_row = ProjectScopeRegistryRepository(
        connection, old_scope
    ).require_exact()
    assert historical_row["state"] == "RETIRED"
    assert historical_row["incarnation"] == old_ref.incarnation
    historical = resolver.resolve_expected("demo_proj", 1, old_digest)
    assert historical == old_ref
    middle_ref = resolver.resolve("demo_proj")
    assert middle_ref.project_registry_revision == 2
    assert middle_ref.incarnation == "scope-inc-2"
    connection.commit()

    aba_digest = compute_scope_digest(
        "demo_proj", "project_old", 3, "scope-inc-3"
    )
    with connection.begin():
        ProjectScopeRegistryRepository(
            connection,
            RuntimeScope(project_scope=middle_ref, actor_id="scope-admin"),
        ).revise(
            expected_revision=2,
            resolved_schema="project_old",
            registry_revision=3,
            scope_digest=aba_digest,
            incarnation="scope-inc-3",
            state="ACTIVE",
            approval_ref="approval:3",
        )
    aba_ref = resolver.resolve("demo_proj")
    assert aba_ref.resolved_schema == old_ref.resolved_schema
    assert aba_ref.incarnation != old_ref.incarnation
    assert aba_ref.scope_digest != old_ref.scope_digest

    rows = connection.execute(
        text(
            "SELECT registry_revision, state FROM public.project_scope_registry "
            "WHERE project_key = 'demo_proj' ORDER BY registry_revision"
        )
    ).all()
    assert rows == [(1, "RETIRED"), (2, "RETIRED"), (3, "ACTIVE")]
    connection.close()
    engine.dispose()


@pytest.mark.unit
def test_registry_resolver_fails_closed_for_missing_or_tampered_binding() -> None:
    schema = "project_alpha"
    incarnation = "scope-inc-alpha"
    digest = compute_scope_digest("alpha", schema, 7, incarnation)
    tampered = {
        "project_key": "alpha",
        "resolved_schema": schema,
        "registry_revision": 7,
        "incarnation": incarnation,
        "scope_digest": "0" * 64,
        "state": "ACTIVE",
    }
    with pytest.raises(ProjectScopeValidationError, match="invalid identity digest"):
        _resolver((tampered,)).resolve("alpha")

    valid = {**tampered, "scope_digest": digest, "state": "RETIRED"}
    resolver = _resolver((valid,))
    with pytest.raises(ProjectScopeValidationError, match="current lookup failed"):
        resolver.resolve("alpha")
    with pytest.raises(ProjectScopeValidationError, match="expected lookup failed"):
        resolver.resolve_expected("alpha", 8, digest)


@pytest.mark.unit
@pytest.mark.parametrize(
    "schema",
    [
        "",
        "public",
        "pg_catalog",
        "information_schema",
        "BadSchema",
        "bad-schema",
        "1schema",
        'bad"schema',
        "x" * 64,
    ],
)
def test_project_schema_identifier_rejects_untrusted_names(schema: str) -> None:
    with pytest.raises(ProjectScopeValidationError):
        validate_project_schema_identifier(schema)


@pytest.mark.unit
def test_uow_shares_one_connection_and_transaction_across_handles() -> None:
    resolver = _resolver()
    scope = _scope(resolver, "demo_proj")
    engine = _memory_engine()
    _create_tables(engine)

    with RuntimeUnitOfWork(engine=engine) as uow:
        connection = uow.connection
        public = uow.public_handle()
        project = uow.project_handle(scope)
        assert public.connection is connection
        assert project.connection is connection
        assert uow.in_transaction
        assert connection.in_transaction()
        assert public.qualified("runtime_values") == '"public"."runtime_values"'
        assert (
            project.qualified("successor_values")
            == f'"{scope.resolved_schema}"."successor_values"'
        )
        public.execute(
            text("INSERT INTO public_runtime (id, payload) VALUES (1, 'a')")
        )
        project.execute(
            text("INSERT INTO project_values (id, payload) VALUES (1, 'b')")
        )
        uow.rollback()

    with RuntimeUnitOfWork(engine=engine) as uow:
        public_count = uow.connection.execute(
            text("SELECT count(*) FROM public_runtime")
        ).scalar_one()
        project_count = uow.connection.execute(
            text("SELECT count(*) FROM project_values")
        ).scalar_one()
        assert public_count == 0
        assert project_count == 0


@pytest.mark.unit
def test_uow_commit_persists_across_reopen() -> None:
    resolver = _resolver()
    scope = _scope(resolver, "demo_proj")
    engine = _memory_engine()
    _create_tables(engine)

    with RuntimeUnitOfWork(engine=engine) as uow:
        public = uow.public_handle()
        project = uow.project_handle(scope)
        public.execute(text("INSERT INTO public_runtime (id, payload) VALUES (1, 'a')"))
        project.execute(text("INSERT INTO project_values (id, payload) VALUES (1, 'b')"))
        uow.commit()

    with RuntimeUnitOfWork(engine=engine) as uow:
        assert (
            uow.connection.execute(
                text("SELECT payload FROM public_runtime WHERE id = 1")
            ).scalar_one()
            == "a"
        )
        assert (
            uow.connection.execute(
                text("SELECT payload FROM project_values WHERE id = 1")
            ).scalar_one()
            == "b"
        )


@pytest.mark.unit
def test_uow_session_factory_owns_transaction_before_requesting_connection() -> None:
    """Regression: Session.connection() autobegin must not be begun again."""

    engine = _memory_engine()
    _create_tables(engine)
    local = RuntimeSessionLocal(engine)

    with RuntimeUnitOfWork(session_factory=local._factory) as uow:
        assert uow.connection.in_transaction()
        uow.connection.execute(
            text("INSERT INTO public_runtime (id, payload) VALUES (1, 'session')")
        )
        uow.commit()

    with RuntimeUnitOfWork(engine=engine) as uow:
        assert (
            uow.connection.execute(
                text("SELECT payload FROM public_runtime WHERE id = 1")
            ).scalar_one()
            == "session"
        )


@pytest.mark.unit
def test_uow_caller_connection_uses_savepoint_and_leaves_outer_owner_open() -> None:
    engine = _memory_engine()
    _create_tables(engine)

    with engine.connect() as connection:
        outer = connection.begin()
        # Materialize SQLite's otherwise deferred outer DBAPI transaction
        # before the UoW creates its savepoint.
        connection.execute(
            text("INSERT INTO public_runtime (id, payload) VALUES (99, 'outer')")
        )
        with RuntimeUnitOfWork(connection=connection) as uow:
            assert uow.connection is connection
            uow.connection.execute(
                text("INSERT INTO public_runtime (id, payload) VALUES (1, 'nested')")
            )
            uow.commit()
        assert not connection.closed
        assert outer.is_active
        outer.rollback()

    with RuntimeUnitOfWork(engine=engine) as uow:
        assert (
            uow.connection.execute(
                text("SELECT count(*) FROM public_runtime WHERE id IN (1, 99)")
            ).scalar_one()
            == 0
        )


@pytest.mark.unit
def test_uow_engine_closes_owned_connection_after_transaction_completion() -> None:
    engine = _memory_engine()
    uow = RuntimeUnitOfWork(engine=engine)
    with uow:
        connection = uow.connection
        assert not connection.closed
        uow.commit()
    assert connection.closed


@pytest.mark.unit
def test_uow_caller_connection_without_outer_transaction_remains_open() -> None:
    engine = _memory_engine()
    _create_tables(engine)
    with engine.connect() as connection:
        with RuntimeUnitOfWork(connection=connection) as uow:
            uow.connection.execute(
                text("INSERT INTO public_runtime (id, payload) VALUES (1, 'caller')")
            )
            uow.commit()
        assert not connection.closed
        assert not connection.in_transaction()
        assert connection.execute(
            text("SELECT payload FROM public_runtime WHERE id = 1")
        ).scalar_one() == "caller"


@pytest.mark.unit
def test_uow_session_transaction_finishes_before_session_close() -> None:
    events: list[str] = []

    class _Dialect:
        name = "sqlite"

    class _Connection:
        dialect = _Dialect()

    class _Transaction:
        is_active = True

        def commit(self) -> None:
            events.append("commit")
            self.is_active = False

        def rollback(self) -> None:
            events.append("rollback")
            self.is_active = False

    class _Session:
        def __init__(self) -> None:
            self.transaction = _Transaction()

        def in_transaction(self) -> bool:
            return False

        def begin(self) -> _Transaction:
            events.append("begin")
            return self.transaction

        def connection(self) -> _Connection:
            events.append("connection")
            return _Connection()

        def close(self) -> None:
            events.append("close")

    session = _Session()
    with RuntimeUnitOfWork(session_factory=lambda: session) as uow:
        uow.commit()

    assert events == ["begin", "connection", "commit", "close"]
    with pytest.raises(UnitOfWorkClosed):
        uow.commit()


@pytest.mark.unit
def test_uow_session_rollback_finishes_before_session_close() -> None:
    events: list[str] = []

    class _Dialect:
        name = "sqlite"

    class _Connection:
        dialect = _Dialect()

    class _Transaction:
        is_active = True

        def rollback(self) -> None:
            events.append("rollback")
            self.is_active = False

    class _Session:
        def __init__(self) -> None:
            self.transaction = _Transaction()

        def in_transaction(self) -> bool:
            return False

        def begin(self) -> _Transaction:
            events.append("begin")
            return self.transaction

        def connection(self) -> _Connection:
            events.append("connection")
            return _Connection()

        def close(self) -> None:
            events.append("close")

    session = _Session()
    with RuntimeUnitOfWork(session_factory=lambda: session):
        pass

    assert events == ["begin", "connection", "rollback", "close"]


@pytest.mark.integration
def test_uow_session_factory_real_postgresql_smoke() -> None:
    """Run only against an explicitly supplied disposable PostgreSQL database."""

    database_url = os.environ.get("SUCCESSOR_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("SUCCESSOR_TEST_DATABASE_URL is not set")
    if "postgresql" not in database_url:
        pytest.skip("SUCCESSOR_TEST_DATABASE_URL is not PostgreSQL")

    engine = create_runtime_engine(database_url)
    local = RuntimeSessionLocal(engine)
    try:
        with RuntimeUnitOfWork(session_factory=local._factory) as uow:
            assert uow.connection.dialect.name == "postgresql"
            assert uow.connection.execute(
                text("SELECT current_schema()")
            ).scalar_one() == "public"
            uow.connection.execute(
                text(
                    "CREATE TEMPORARY TABLE successor_uow_smoke "
                    "(id INTEGER PRIMARY KEY) ON COMMIT DROP"
                )
            )
            uow.connection.execute(
                text("INSERT INTO successor_uow_smoke (id) VALUES (1)")
            )
            uow.commit()

        with engine.connect() as connection:
            outer = connection.begin()
            with RuntimeUnitOfWork(connection=connection) as uow:
                assert uow.connection is connection
                assert uow.connection.execute(text("SELECT 1")).scalar_one() == 1
                uow.commit()
            assert outer.is_active
            outer.rollback()
    finally:
        engine.dispose()


@pytest.mark.unit
def test_uow_exit_without_commit_rolls_back() -> None:
    engine = _memory_engine()
    _create_tables(engine)
    with RuntimeUnitOfWork(engine=engine) as uow:
        uow.connection.execute(
            text("INSERT INTO public_runtime (id, payload) VALUES (1, 'x')")
        )

    with RuntimeUnitOfWork(engine=engine) as uow:
        count = uow.connection.execute(
            text("SELECT count(*) FROM public_runtime")
        ).scalar_one()
        assert count == 0


@pytest.mark.unit
def test_uow_commit_after_close_is_a_negative_case() -> None:
    engine = _memory_engine()
    uow = RuntimeUnitOfWork(engine=engine)
    with uow:
        uow.commit()
    with pytest.raises(UnitOfWorkClosed):
        uow.rollback()
    with pytest.raises(UnitOfWorkClosed):
        uow.connection
    with pytest.raises(UnitOfWorkClosed):
        with uow:
            pass


@pytest.mark.unit
def test_uow_rollback_after_context_close_is_a_negative_case() -> None:
    engine = _memory_engine()
    uow = RuntimeUnitOfWork(engine=engine)
    with uow:
        pass
    with pytest.raises(UnitOfWorkClosed):
        uow.commit()
    with pytest.raises(UnitOfWorkClosed):
        uow.rollback()


@pytest.mark.unit
def test_repository_binding_requires_explicit_connection_not_implicit_session() -> None:
    resolver = _resolver()
    scope = _scope(resolver, "demo_proj")
    engine = _memory_engine()

    with RuntimeUnitOfWork(engine=engine) as uow:
        repository = uow.bind_repository(
            _RecordingRepository, scope=scope, label="ledger"
        )
        assert repository.connection is uow.connection
        assert repository.handle.connection is uow.connection
        assert repository.handle.schema == scope.resolved_schema
        assert repository.label == "ledger"
        assert uow.bound_repositories == (repository,)

        def requires_session(session, handle):  # noqa: ANN001
            return session, handle

        with pytest.raises(TypeError):
            uow.bind_repository(requires_session, scope=scope)


@pytest.mark.unit
def test_uow_rejects_unvalidated_project_scope_ref() -> None:
    resolver = _resolver()
    valid = _scope(resolver, "demo_proj")
    engine = _memory_engine()

    with RuntimeUnitOfWork(engine=engine) as uow:
        wrong_digest = ProjectScopeRef(
            project_key=valid.project_key,
            resolved_schema=valid.resolved_schema,
            project_registry_revision=valid.project_registry_revision,
            incarnation=valid.incarnation,
            scope_digest="0" * 64,
        )
        with pytest.raises(ProjectScopeValidationError):
            uow.project_handle(wrong_digest)
        bad_schema = ProjectScopeRef(
            project_key=valid.project_key,
            resolved_schema="bad-schema",
            project_registry_revision=valid.project_registry_revision,
            incarnation=valid.incarnation,
            scope_digest=valid.scope_digest,
        )
        with pytest.raises(ProjectScopeValidationError):
            uow.project_handle(bad_schema)


@pytest.mark.unit
def test_blob_path_contract_uses_var_lib_and_scope_digest() -> None:
    scope_digest = "a" * 64
    digest = "b" * 64
    assert project_blob_root(BLOB_ROOT, scope_digest) == Path(
        "/var/lib/mrw/runtime-artifacts/projects"
    ) / scope_digest / "sha256"
    assert blob_path(BLOB_ROOT, scope_digest, digest) == (
        Path("/var/lib/mrw/runtime-artifacts")
        / "projects"
        / scope_digest
        / "sha256"
        / digest[:2]
        / digest
    )


@pytest.mark.unit
def test_blob_store_roundtrip_and_readback_digest_verification(tmp_path: Path) -> None:
    resolver = _resolver()
    scope = _scope(resolver, "demo_proj")
    store = ProjectBlobStore(tmp_path)
    data = b"exact captured material bytes"

    ref = store.store(scope, data)
    assert ref.digest == compute_digest(data)
    assert ref.byte_size == len(data)
    assert ref.scope_digest == scope.scope_digest
    assert ref.storage_ref == (
        f"projects/{scope.scope_digest}/sha256/{ref.digest[:2]}/{ref.digest}"
    )

    readback = store.readback(scope, ref.digest)
    assert readback.data == data
    assert readback.byte_size == len(data)

    ref.path.write_bytes(b"tampered")
    with pytest.raises(BlobDigestMismatch):
        store.readback(scope, ref.digest)


@pytest.mark.unit
def test_blob_prepare_temp_fsync_digest_size_then_atomic_finalize(
    tmp_path: Path,
) -> None:
    resolver = _resolver()
    scope = _scope(resolver, "demo_proj")
    store = ProjectBlobStore(tmp_path)
    data = b"pdf bytes"

    prepared = store.prepare(scope, data)
    assert prepared.temp_path.exists()
    assert prepared.temp_path.parent == prepared.final_path.parent
    assert prepared.digest == compute_digest(data)
    assert prepared.byte_size == len(data)

    ref = store.finalize(prepared)
    assert ref.path == prepared.final_path
    assert not prepared.temp_path.exists()
    assert store.readback(scope, ref.digest).data == data
    remaining = list(ref.path.parent.iterdir())
    assert remaining == [ref.path]


@pytest.mark.unit
def test_blob_orphan_reconciliation_protects_retention_refs(tmp_path: Path) -> None:
    resolver = _resolver()
    scope = _scope(resolver, "demo_proj")
    store = ProjectBlobStore(tmp_path)
    retained = store.store(scope, b"still referenced")
    orphan = store.store(scope, b"no longer referenced")

    removed = store.reconcile_orphans(scope, retained={retained.digest})
    assert removed == [orphan.digest]
    assert store.readback(scope, retained.digest).data == b"still referenced"
    with pytest.raises(BlobNotFound):
        store.readback(scope, orphan.digest)


@pytest.mark.unit
def test_blob_store_is_scoped_by_project_scope_digest(tmp_path: Path) -> None:
    resolver = _resolver()
    scope_a = _scope(resolver, "demo_proj")
    scope_b = _scope(resolver, "other_proj")
    assert scope_a.scope_digest != scope_b.scope_digest
    store = ProjectBlobStore(tmp_path)
    data = b"same content"

    ref_a = store.store(scope_a, data)
    ref_b = store.store(scope_b, data)
    assert ref_a.path != ref_b.path
    assert ref_a.scope_digest == scope_a.scope_digest
    assert ref_b.scope_digest == scope_b.scope_digest

    removed = store.reconcile_orphans(scope_a, retained=set())
    assert removed == [ref_a.digest]
    with pytest.raises(BlobNotFound):
        store.readback(scope_a, ref_a.digest)
    assert store.readback(scope_b, ref_b.digest).data == data


@pytest.mark.unit
@pytest.mark.parametrize(
    "scope_digest,digest",
    [
        ("x" * 64, "a" * 64),
        ("a" * 64, "xyz"),
        ("a" * 64, "B" * 64),
    ],
)
def test_blob_path_rejects_invalid_digests(
    scope_digest: str, digest: str
) -> None:
    with pytest.raises(ValueError):
        blob_path(BLOB_ROOT, scope_digest, digest)
