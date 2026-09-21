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


BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BACKEND_ROOT.parent.parent
for path in (str(BACKEND_ROOT), str(REPOSITORY_ROOT / "src")):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.services.projects.schema_initialization import (
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

    def execute(self, statement: object, _parameters: object = None) -> None:
        self.statements.append(str(statement))

    def begin_nested(self) -> _BeginContext:
        return _BeginContext(self)


class _BeginContext:
    def __init__(self, connection: _RecordingConnection) -> None:
        self.connection = connection

    def __enter__(self) -> _RecordingConnection:
        return self.connection

    def __exit__(self, *_args: object) -> None:
        return None


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


def test_explicit_schema_startup_creates_the_configured_schema() -> None:
    database_engine = _RecordingEngine()

    initialize_default_project_schema(
        database_engine=database_engine,
        settings_obj=_settings(env="dev", active_project_key="startup-demo"),
    )

    assert database_engine.begin_calls == 1
    assert database_engine.connection.statements == [
        'CREATE SCHEMA IF NOT EXISTS "project_startup_demo"'
    ]


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


@pytest.mark.parametrize("store_name", ["SqlRunStore", "SqlCompiledGraphStore"])
def test_workflow_graph_schema_ddl_uses_the_public_schema_process_lock(
    store_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.projects import schema_initialization as schema_module
    from app.services.workflow_graph import store as store_module

    database_engine = _RecordingEngine()
    database_engine.dialect = SimpleNamespace(name="postgresql")
    create_all = Mock()
    monkeypatch.setattr(store_module, "engine", database_engine)
    monkeypatch.setattr(store_module.Base.metadata, "create_all", create_all)
    monkeypatch.setattr(schema_module.settings, "db_lock_timeout_ms", 1234)

    getattr(store_module, store_name)()

    assert database_engine.begin_calls == 1
    assert database_engine.connection.statements[:3] == [
        "SET LOCAL lock_timeout = 1234",
        "SELECT pg_advisory_xact_lock(hashtextextended(:lock_scope, 0))",
        'SET search_path TO "public"',
    ]
    if store_name == "SqlRunStore":
        create_all.assert_called_once()
    else:
        create_all.assert_not_called()
        assert "CREATE TABLE IF NOT EXISTS workflow_graph_compiled_artifacts" in (
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
    created: list[tuple[object, bool]] = []
    table = SimpleNamespace(
        name="documents",
        c={},
        create=lambda *, bind, checkfirst: created.append((bind, checkfirst)),
    )
    monkeypatch.setattr(bootstrap_module, "engine", database_engine)
    monkeypatch.setattr(bootstrap_module, "TENANT_TABLES", [table])
    monkeypatch.setattr(bootstrap_module, "_normalize_project_key", lambda value: value)
    monkeypatch.setattr(
        bootstrap_module,
        "project_schema_name",
        lambda value: f"project_{value}",
    )
    monkeypatch.setattr(schema_module.settings, "db_lock_timeout_ms", 1234)

    result = bootstrap_module.ensure_project_schema_ready("cli_demo", name="CLI Demo")

    assert result == {"project_key": "cli_demo", "schema_name": "project_cli_demo"}
    assert database_engine.begin_calls == 1
    assert database_engine.connection.statements[:3] == [
        "SET LOCAL lock_timeout = 1234",
        "SELECT pg_advisory_xact_lock(hashtextextended(:lock_scope, 0))",
        'SET search_path TO "public"',
    ]
    assert "INSERT INTO public.projects" in database_engine.connection.statements[3]
    assert database_engine.connection.statements[-2:] == [
        'CREATE SCHEMA IF NOT EXISTS "project_cli_demo"',
        'SET search_path TO "project_cli_demo"',
    ]
    assert created == [(database_engine.connection, True)]


def test_database_cli_wrapper_runs_preflight_before_command(monkeypatch: pytest.MonkeyPatch) -> None:
    from main.backend.scripts import _cli_runtime

    order: list[str] = []
    monkeypatch.setattr(
        _cli_runtime,
        "initialize_database_cli",
        lambda **_kwargs: order.append("schema"),
    )

    result = _cli_runtime.run_database_cli(
        lambda: order.append("command") or 17,
        project_key="cli_demo",
    )

    assert result == 17
    assert order == ["schema", "command"]

    def fail_preflight(**_kwargs: object) -> None:
        raise RuntimeError("preflight failed")

    monkeypatch.setattr(_cli_runtime, "initialize_database_cli", fail_preflight)
    with pytest.raises(RuntimeError, match="preflight failed"):
        _cli_runtime.run_database_cli(
            lambda: order.append("must_not_run"),
            project_key="cli_demo",
        )
    assert order == ["schema", "command"]


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
    assert logger.warning.call_args.args[3] is True


def test_register_startup_hooks_exposes_schema_bootstrap_as_explicit_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()
    bootstrap = Mock()
    monkeypatch.setattr("app.startup_hooks.initialize_default_project_schema", bootstrap)

    register_startup_hooks(app)

    handler = next(
        callback
        for callback in app.router.on_startup
        if callback.__name__ == "_ensure_default_project_schema"
    )
    handler()
    bootstrap.assert_called_once()


def test_celery_worker_schema_boundary_and_production_termination() -> None:
    code = r'''
import langchain_community.cache as lc_cache
lc_cache.SQLiteCache = lambda *args, **kwargs: object()

from celery.exceptions import WorkerTerminate
import app.celery_app as celery_module

calls = []
celery_module.initialize_default_project_schema = lambda: calls.append("schema") or True
assert celery_module.initialize_celery_worker_schema() is True
assert calls == ["schema"]

def fail():
    raise RuntimeError("production DDL denied")

celery_module.initialize_default_project_schema = fail
try:
    celery_module.initialize_celery_worker_schema()
except WorkerTerminate as exc:
    assert exc.code == 1
    assert isinstance(exc.__cause__, RuntimeError)
else:
    raise AssertionError("production failure did not terminate worker child")

assert issubclass(WorkerTerminate, BaseException)
assert not issubclass(WorkerTerminate, Exception)
assert any(
    receiver is celery_module._initialize_celery_worker_schema
    for receiver in celery_module.signals.worker_process_init._live_receivers(None)
)
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
