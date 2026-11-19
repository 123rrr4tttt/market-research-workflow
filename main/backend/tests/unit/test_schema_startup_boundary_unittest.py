"""Focused tests for the database schema startup effect boundary."""

# ruff: noqa: E402, TRY003

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BACKEND_ROOT.parent.parent
for path in (str(BACKEND_ROOT), str(REPOSITORY_ROOT / "src")):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.services.projects.schema_initialization import (
    DatabaseRevisionIncompatibleError,
    ensure_database_revision_compatible,
    initialize_cli_project_schema,
    initialize_default_project_schema,
    run_serialized_schema_ddl,
    schema_ddl_lock_scope,
)
from app.startup_hooks import register_startup_hooks


pytestmark = pytest.mark.unit


class _RecordingConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.executions: list[tuple[str, object]] = []
        self.table_catalog: set[tuple[str, str]] = set()

    def execute(self, statement: object, parameters: object = None) -> _ScalarResult:
        statement_text = str(statement)
        self.statements.append(statement_text)
        self.executions.append((statement_text, parameters))
        if "information_schema.tables" in statement_text and isinstance(parameters, dict):
            table_key = (str(parameters.get("schema_name")), str(parameters.get("table_name")))
            return _ScalarResult(table_key in self.table_catalog)
        return _ScalarResult(False)

    def begin_nested(self) -> _BeginContext:
        return _BeginContext(self)


class _BeginContext:
    def __init__(self, connection: _RecordingConnection) -> None:
        self.connection = connection

    def __enter__(self) -> _RecordingConnection:
        return self.connection

    def __exit__(self, *_args: object) -> None:
        return None


class _ScalarResult:
    def __init__(self, value: object) -> None:
        self.value = value

    def scalar(self) -> object:
        return self.value

    def fetchone(self) -> object:
        return self.value if isinstance(self.value, tuple) else None


class _RecordingEngine:
    def __init__(self) -> None:
        self.connection = _RecordingConnection()
        self.begin_calls = 0

    def begin(self) -> _BeginContext:
        self.begin_calls += 1
        return _BeginContext(self.connection)


class _FailingEngine:
    def __init__(self, failure: Exception) -> None:
        self.failure = failure

    def begin(self) -> None:
        raise self.failure


def _settings(*, env: str, active_project_key: str = "demo") -> SimpleNamespace:
    return SimpleNamespace(env=env, active_project_key=active_project_key)


def test_importing_models_base_never_opens_a_database_transaction() -> None:
    code = """
from sqlalchemy.engine import Engine

begin_calls = []

def forbidden_begin(self):
    begin_calls.append(self)
    raise AssertionError("models.base import attempted a database transaction")

Engine.begin = forbidden_begin
import app.models.base  # noqa: F401
assert begin_calls == []
"""
    env = os.environ.copy()
    python_path = os.pathsep.join((str(BACKEND_ROOT), str(REPOSITORY_ROOT / "src")))
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (python_path, env.get("PYTHONPATH", ""))))

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_explicit_schema_startup_only_validates_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.projects import schema_initialization as schema_module

    database_engine = _RecordingEngine()
    calls: list[object] = []
    monkeypatch.setattr(
        schema_module,
        "ensure_database_revision_compatible",
        lambda connection: calls.append(connection),
    )

    initialize_default_project_schema(
        database_engine=database_engine,
        settings_obj=_settings(env="dev", active_project_key="startup-demo"),
    )

    assert database_engine.begin_calls == 1
    assert calls == [database_engine.connection]
    assert database_engine.connection.statements == []


def test_revision_guard_compares_public_heads_and_reports_both_sets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.projects import schema_initialization as schema_module

    context = SimpleNamespace(get_current_heads=lambda: ("old_head",))
    configure = Mock(return_value=context)
    monkeypatch.setattr(schema_module.MigrationContext, "configure", configure)

    with pytest.raises(DatabaseRevisionIncompatibleError) as caught:
        ensure_database_revision_compatible(
            Mock(),
            expected_heads=frozenset({"new_head"}),
        )

    assert caught.value.actual == frozenset({"old_head"})
    assert caught.value.expected == frozenset({"new_head"})
    assert "actual=old_head expected=new_head" in str(caught.value)
    assert configure.call_args.kwargs["opts"] == {"version_table_schema": "public"}


def test_revision_incompatibility_is_not_swallowed_in_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.projects import schema_initialization as schema_module

    database_engine = _RecordingEngine()
    failure = DatabaseRevisionIncompatibleError(
        actual=frozenset({"old"}),
        expected=frozenset({"new"}),
    )
    monkeypatch.setattr(
        schema_module,
        "ensure_database_revision_compatible",
        Mock(side_effect=failure),
    )

    with pytest.raises(DatabaseRevisionIncompatibleError) as caught:
        initialize_default_project_schema(
            database_engine=database_engine,
            settings_obj=_settings(env="dev"),
        )

    assert caught.value is failure


def test_postgresql_schema_ddl_acquires_transaction_lock_before_operation() -> None:
    database_engine = _RecordingEngine()
    database_engine.dialect = SimpleNamespace(name="postgresql")

    run_serialized_schema_ddl(
        database_engine,
        schema_name="project_startup_demo",
        operation=lambda connection: connection.execute("DDL"),
        lock_timeout_ms=1234,
    )

    assert database_engine.connection.statements == [
        "SET LOCAL lock_timeout = 1234",
        "SELECT pg_advisory_xact_lock(hashtextextended(:lock_scope, 0))",
        "DDL",
    ]
    assert schema_ddl_lock_scope("project_startup_demo") == (
        "mrw.schema-ddl.v1:project_startup_demo"
    )


def test_failed_postgresql_schema_transaction_is_retryable() -> None:
    class _FlakyConnection(_RecordingConnection):
        def __init__(self) -> None:
            super().__init__()
            self.failures_remaining = 1

        def execute(self, statement: object, parameters: object = None) -> None:
            super().execute(statement, parameters)
            if str(statement) == "DDL" and self.failures_remaining:
                self.failures_remaining -= 1
                raise RuntimeError("injected DDL failure")

    class _FlakyEngine(_RecordingEngine):
        def __init__(self) -> None:
            super().__init__()
            self.connection = _FlakyConnection()
            self.dialect = SimpleNamespace(name="postgresql")

    database_engine = _FlakyEngine()

    with pytest.raises(RuntimeError, match="injected DDL failure"):
        run_serialized_schema_ddl(
            database_engine,
            schema_name="project_retry",
            operation=lambda connection: connection.execute("DDL"),
            lock_timeout_ms=1234,
        )
    run_serialized_schema_ddl(
        database_engine,
        schema_name="project_retry",
        operation=lambda connection: connection.execute("DDL"),
        lock_timeout_ms=1234,
    )

    assert database_engine.begin_calls == 2
    assert database_engine.connection.statements.count("SET LOCAL lock_timeout = 1234") == 2
    assert database_engine.connection.statements.count(
        "SELECT pg_advisory_xact_lock(hashtextextended(:lock_scope, 0))"
    ) == 2
    assert database_engine.connection.statements.count("DDL") == 2


def test_workflow_graph_compiled_schema_ddl_uses_the_public_schema_process_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.projects import schema_initialization as schema_module
    from app.services.workflow_graph import store as store_module

    database_engine = _RecordingEngine()
    database_engine.dialect = SimpleNamespace(name="postgresql")
    monkeypatch.setattr(store_module, "engine", database_engine)
    monkeypatch.setattr(schema_module.settings, "db_lock_timeout_ms", 1234)
    store_module.SqlCompiledGraphStore()

    assert database_engine.begin_calls == 1
    assert database_engine.connection.statements[:3] == [
        "SET LOCAL lock_timeout = 1234",
        "SELECT pg_advisory_xact_lock(hashtextextended(:lock_scope, 0))",
        'SET search_path TO "public"',
    ]
    assert "CREATE TABLE IF NOT EXISTS public.workflow_graph_compiled_artifacts" in (
        database_engine.connection.statements[-1]
    )


def test_cli_schema_preflight_is_explicit_and_fail_closed() -> None:
    calls: list[tuple[str, str | None]] = []

    def bootstrap(project_key: str, *, name: str | None = None) -> dict[str, str]:
        calls.append((project_key, name))
        return {"project_key": project_key, "schema_name": f"project_{project_key}"}

    result = initialize_cli_project_schema(
        project_key="cli_demo",
        name="CLI Demo",
        settings_obj=_settings(env="dev"),
        bootstrap=bootstrap,
    )

    assert result == {"project_key": "cli_demo", "schema_name": "project_cli_demo"}
    assert calls == [("cli_demo", "CLI Demo")]

    def fail_bootstrap(_project_key: str, *, name: str | None = None) -> dict[str, str]:
        del name
        raise RuntimeError("schema preflight failed")

    with pytest.raises(RuntimeError, match="schema preflight failed"):
        initialize_cli_project_schema(
            project_key="cli_demo",
            settings_obj=_settings(env="dev"),
            bootstrap=fail_bootstrap,
        )


def test_project_schema_cli_preflight_is_one_serialized_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.projects import bootstrap as bootstrap_module
    from app.services.projects import schema_initialization as schema_module

    database_engine = _RecordingEngine()
    database_engine.dialect = SimpleNamespace(name="postgresql")
    database_engine.connection.table_catalog.add(("public", "documents"))
    created: list[tuple[object, bool]] = []
    table = SimpleNamespace(
        name="documents",
        c={},
        create=lambda *, bind, checkfirst: created.append((bind, checkfirst)),
    )
    monkeypatch.setattr(bootstrap_module, "engine", database_engine)
    monkeypatch.setattr(bootstrap_module, "TENANT_TABLES", [table])
    monkeypatch.setattr(bootstrap_module, "normalize_project_key", lambda value: value)
    monkeypatch.setattr(
        bootstrap_module,
        "project_schema_name",
        lambda value: f"project_{value}",
    )
    monkeypatch.setattr(schema_module.settings, "db_lock_timeout_ms", 1234)
    monkeypatch.setattr(
        bootstrap_module,
        "ensure_database_revision_compatible",
        lambda _connection: frozenset({"head"}),
    )

    result = bootstrap_module.ensure_project_schema_ready("cli_demo", name="CLI Demo")

    assert result == {"project_key": "cli_demo", "schema_name": "project_cli_demo"}
    assert database_engine.begin_calls == 1
    assert database_engine.connection.statements[:3] == [
        "SET LOCAL lock_timeout = 1234",
        "SELECT pg_advisory_xact_lock(hashtextextended(:lock_scope, 0))",
        'SET search_path TO "public"',
    ]
    statements = database_engine.connection.statements
    assert statements[2] == 'SET search_path TO "public"'
    assert "SELECT project_key, schema_name FROM public.projects" in statements[3]
    assert "SELECT EXISTS (SELECT 1 FROM pg_class" in statements[4]
    assert statements[5:7] == [
        'CREATE SCHEMA IF NOT EXISTS "project_cli_demo"',
        'SET search_path TO "project_cli_demo", public',
    ]
    assert statements[-2] == 'SET search_path TO "public"'
    assert "INSERT INTO public.projects" in statements[-1]
    assert database_engine.connection.executions[-3][1] == {
        "schema_name": "project_cli_demo",
        "table_name": "documents",
    }
    assert created == [(database_engine.connection, False)]


def test_project_tenant_table_manifest_includes_mandatory_ingest_registry_once() -> None:
    from app.models.ingest_registry import IngestSubmissionRegistry
    from app.services.projects.bootstrap import TENANT_TABLES

    registry_tables = [
        table
        for table in TENANT_TABLES
        if table.name == "ingest_submission_registry"
    ]

    assert registry_tables == [IngestSubmissionRegistry.__table__]


def test_registered_project_uses_stored_schema_and_never_creates_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.projects import bootstrap as bootstrap_module

    database_engine = _RecordingEngine()
    database_engine.dialect = SimpleNamespace(name="postgresql")
    validated: list[str] = []
    monkeypatch.setattr(bootstrap_module, "engine", database_engine)
    monkeypatch.setattr(
        bootstrap_module,
        "ensure_database_revision_compatible",
        lambda _connection: frozenset({"head"}),
    )
    monkeypatch.setattr(
        bootstrap_module,
        "_registered_project",
        lambda _connection, _key: ("existing", "tenant_stored"),
    )
    monkeypatch.setattr(
        bootstrap_module,
        "validate_project_schema",
        lambda _connection, *, schema_name, tables=None: validated.append(schema_name),
    )

    result = bootstrap_module.ensure_project_schema_ready("existing")

    assert result == {"project_key": "existing", "schema_name": "tenant_stored"}
    assert validated == ["tenant_stored"]
    assert not any("CREATE SCHEMA" in statement for statement in database_engine.connection.statements)
    assert not any("INSERT INTO public.projects" in statement for statement in database_engine.connection.statements)


def test_registered_project_missing_required_column_is_validation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.projects import bootstrap as bootstrap_module

    table = SimpleNamespace(
        name="materials",
        columns=[SimpleNamespace(name="id"), SimpleNamespace(name="material_type")],
    )
    inspector = SimpleNamespace(
        has_table=lambda _name, *, schema: schema == "tenant_stored",
        get_columns=lambda _name, *, schema: [{"name": "id"}],
    )
    monkeypatch.setattr(bootstrap_module, "inspect", lambda _connection: inspector)

    with pytest.raises(bootstrap_module.ProjectSchemaIncompatibleError) as caught:
        bootstrap_module.validate_project_schema(
            Mock(),
            schema_name="tenant_stored",
            tables=[table],
        )

    assert caught.value.missing_columns == ("materials.material_type",)


def test_require_model_table_returns_native_table_identity() -> None:
    from sqlalchemy.sql.schema import Table

    from app.models.base import require_model_table
    from app.models.entities import Source

    table = Source.__table__

    assert isinstance(table, Table)
    assert require_model_table(table) is table


def test_schema_startup_rejects_non_table_model_before_ddl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import startup_hooks as startup_module

    database_engine = _RecordingEngine()
    monkeypatch.setattr(startup_module, "engine", database_engine)
    monkeypatch.setattr(startup_module, "build_topology_service", lambda: object())
    monkeypatch.setattr(
        startup_module, "AgentSession", SimpleNamespace(__table__=object())
    )
    app = FastAPI()
    startup_module.register_startup_hooks(app)
    handler = next(
        callback
        for callback in app.router.on_startup
        if callback.__name__ == "_ensure_shared_library_tables_ready"
    )

    with pytest.raises(TypeError, match="must be a SQLAlchemy Table"):
        handler()

    assert database_engine.begin_calls == 0
    assert database_engine.connection.statements == []


def test_schema_startup_uses_canonical_tenant_manifest_for_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import startup_hooks as startup_module

    database_engine = _RecordingEngine()
    database_engine.connection.execute = Mock(
        return_value=SimpleNamespace(fetchall=lambda: [])
    )
    validated: list[object] = []
    monkeypatch.setattr(startup_module, "engine", database_engine)
    monkeypatch.setattr(startup_module, "build_topology_service", lambda: object())
    monkeypatch.setattr(
        startup_module,
        "ensure_database_revision_compatible",
        lambda connection: validated.append(connection),
    )
    app = FastAPI()
    startup_module.register_startup_hooks(app)
    handler = next(
        callback
        for callback in app.router.on_startup
        if callback.__name__ == "_ensure_all_project_schemas_ready"
    )

    handler()

    assert validated == [database_engine.connection]
    assert database_engine.begin_calls == 1


def test_development_schema_startup_logs_classified_failure_and_continues() -> None:
    logger = Mock()

    initialize_default_project_schema(
        database_engine=_FailingEngine(ConnectionError("db unavailable")),
        settings_obj=_settings(env="dev"),
        logger_obj=logger,
    )

    logger.warning.assert_called_once()
    log_args = logger.warning.call_args.args
    assert log_args[0].startswith("db bootstrap skipped: %s")
    assert log_args[1].args == ("db unavailable",)
    assert log_args[3] is False
    assert log_args[4] == "application"
    assert log_args[5] is False
    assert log_args[7] == "ConnectionError"


@pytest.mark.parametrize("env", ["production", "prod"])
def test_production_schema_startup_logs_and_fails_closed(env: str) -> None:
    failure = RuntimeError("ddl denied")
    logger = Mock()

    with pytest.raises(RuntimeError, match="ddl denied") as caught:
        initialize_default_project_schema(
            database_engine=_FailingEngine(failure),
            settings_obj=_settings(env=env),
            logger_obj=logger,
        )

    assert caught.value is failure
    logger.warning.assert_called_once()
    assert logger.warning.call_args.args[0].startswith("db startup blocked: %s")
    assert logger.warning.call_args.args[3] is True


def test_api_startup_blocks_on_unavailable_database_then_recovers(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from app import startup_hooks as startup_module
    from app.services.projects import schema_initialization as schema_module

    failure = ConnectionError("db unavailable")
    schema_engine = _RecordingEngine()
    order: list[str] = []
    monkeypatch.setattr(schema_module, "settings", _settings(env="dev"))
    monkeypatch.setattr(schema_module, "engine", _FailingEngine(failure))
    monkeypatch.setattr(
        schema_module,
        "ensure_database_revision_compatible",
        lambda _connection: order.append("schema"),
    )
    monkeypatch.setattr(startup_module, "build_topology_service", lambda: object())

    app = FastAPI()
    app.router.add_event_handler("startup", lambda: order.append("downstream"))
    register_startup_hooks(app)
    # The existing DB-using downstream handlers have separate unit coverage.
    # Keep the real preflight and the callback registered before composition.
    del app.router.on_startup[2:]

    with pytest.raises(ConnectionError, match="db unavailable") as caught, TestClient(app):
        pytest.fail("API accepted startup without the primary database")
    assert caught.value is failure
    assert "db startup blocked: db unavailable" in caplog.text
    assert order == []

    monkeypatch.setattr(schema_module, "engine", schema_engine)
    with TestClient(app):
        assert order == ["schema", "downstream"]
    assert schema_engine.begin_calls == 1


def test_celery_worker_schema_boundary_blocks_before_pool_then_recovers() -> None:
    code = r'''
from contextlib import nullcontext
from types import SimpleNamespace

import langchain_community.cache as lc_cache
lc_cache.SQLiteCache = lambda *args, **kwargs: object()

from celery.exceptions import WorkerTerminate
import app.celery_app as celery_module
from app.services.projects import schema_initialization as schema_module

class SchemaEngine:
    failure = ConnectionError("db unavailable")

    def begin(self):
        calls.append("schema")
        if self.failure is not None:
            raise self.failure
        return nullcontext(object())

    def dispose(self):
        calls.append("dispose")

calls = []
engine = SchemaEngine()
schema_module.settings = SimpleNamespace(env="dev", active_project_key="demo")
schema_module.engine = celery_module.engine = engine
schema_module.ensure_database_revision_compatible = lambda _connection: calls.append("revision")

app = celery_module.celery_app
app.conf.broker_url = "memory://"
app.conf.result_backend = "cache+memory://"

# Exercise WorkController's real worker_init signal dispatch; stop at the
# blueprint boundary so no worker pool or consumer is constructed or started.
class ReachedBlueprint(Exception):
    pass

class ProbeWorker(app.WorkController):
    def on_init_blueprint(self):
        raise ReachedBlueprint

for pool in ("solo", "prefork"):
    calls.clear()
    engine.failure = ConnectionError("db unavailable")
    try:
        ProbeWorker(pool_cls=pool, concurrency=1, use_eventloop=False)
    except WorkerTerminate as exc:
        assert exc.code == 1
        assert exc.__cause__ is engine.failure
    else:
        raise AssertionError("DB failure did not stop worker startup")
    assert calls == ["schema"]

    calls.clear()
    engine.failure = None
    try:
        ProbeWorker(pool_cls=pool, concurrency=1, use_eventloop=False)
    except ReachedBlueprint:
        pass
    else:
        raise AssertionError("worker did not reach blueprint after DB recovery")
    assert calls == ["schema", "revision", "dispose"]
'''
    env = os.environ.copy()
    python_path = os.pathsep.join((str(BACKEND_ROOT), str(REPOSITORY_ROOT / "src")))
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (python_path, env.get("PYTHONPATH", ""))))

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Celery worker database startup failed" in result.stderr
    assert "ConnectionError: db unavailable" in result.stderr
