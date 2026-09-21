"""Isolated contract-13 witnesses for startup and lazy DB boundaries.

These tests use only injected stores, fail-fast transaction guards, and threads.
They do not connect to a database or network service.
"""

# ruff: noqa: E402, E731, TRY003

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPOSITORY_ROOT / "main" / "backend"
for path in (str(BACKEND_ROOT), str(REPOSITORY_ROOT / "src")):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.services import workflow_graph as workflow_graph_module
from app.services.workflow_graph import WorkflowGraphCompilerService, WorkflowGraphRuntimeService
from app.services.workflow_graph import handoff_store as handoff_store_module
from app.services.workflow_graph.handoff_store import WorkflowGraphHandoffStore
from app.services.workflow_graph import store as store_module
from app.startup_hooks import register_startup_hooks


def test_register_startup_hooks_places_default_schema_first() -> None:
    app = FastAPI()

    register_startup_hooks(app)

    assert [callback.__name__ for callback in app.router.on_startup] == [
        "_ensure_default_project_schema",
        "_ensure_bootstrap_projects",
        "_ensure_all_project_schemas_ready",
        "_sync_llm_prompts_from_files",
        "_ensure_shared_library_tables_ready",
    ]


def test_composed_fastapi_app_keeps_schema_first_and_production_gate_last() -> None:
    code = r'''
from sqlalchemy.engine import Engine
import langchain_community.cache as lc_cache

# Isolate FastAPI registration from the unrelated local LLM SQLite cache.
lc_cache.SQLiteCache = lambda *args, **kwargs: object()
begin_calls = []
connect_calls = []

def forbidden_begin(self, *args, **kwargs):
    begin_calls.append(type(self).__name__)
    raise AssertionError("app.main import attempted a DB transaction")

def forbidden_connect(self, *args, **kwargs):
    connect_calls.append(type(self).__name__)
    raise AssertionError("app.main import attempted a DB connection")

Engine.begin = forbidden_begin
Engine.connect = forbidden_connect
import app.main as main_module
names = [callback.__name__ for callback in main_module.app.router.on_startup]
assert names == [
    "_ensure_default_project_schema",
    "_ensure_bootstrap_projects",
    "_ensure_all_project_schemas_ready",
    "_sync_llm_prompts_from_files",
    "_ensure_shared_library_tables_ready",
    "_validate_production_composition",
]
assert begin_calls == []
assert connect_calls == []
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


def _concurrent_results(resolve: object) -> list[object]:
    with ThreadPoolExecutor(max_workers=12) as pool:
        return list(pool.map(lambda _index: resolve(), range(24)))


def test_compiler_first_use_has_one_in_process_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()
    calls = 0

    def build() -> object:
        nonlocal calls
        calls += 1
        time.sleep(0.01)
        return sentinel

    monkeypatch.setattr(workflow_graph_module, "build_compiled_graph_store", build)
    service = WorkflowGraphCompilerService()

    results = _concurrent_results(service._resolved_store)

    assert calls == 1
    assert all(result is sentinel for result in results)


def test_runtime_first_use_has_one_in_process_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel_store = object()
    calls = 0

    def build() -> object:
        nonlocal calls
        calls += 1
        time.sleep(0.01)
        return sentinel_store

    monkeypatch.setattr(workflow_graph_module, "build_run_store", build)
    monkeypatch.setattr(
        workflow_graph_module,
        "WorkflowGraphRuntime",
        lambda *, store: SimpleNamespace(store=store),
    )
    service = WorkflowGraphRuntimeService()

    results = _concurrent_results(service._resolved_engine)

    assert calls == 1
    assert all(result.store is sentinel_store for result in results)


def test_handoff_first_use_has_one_in_process_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()
    calls = 0

    def build() -> object:
        nonlocal calls
        calls += 1
        time.sleep(0.01)
        return sentinel

    monkeypatch.setattr(handoff_store_module, "build_run_store", build)
    service = WorkflowGraphHandoffStore()

    results = _concurrent_results(service._resolved_store)

    assert calls == 1
    assert all(result is sentinel for result in results)


@pytest.mark.parametrize("kind", ["compiler", "runtime", "handoff"])
def test_fail_closed_first_use_leaves_field_unset_and_next_use_retries(
    kind: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = object()
    calls = 0

    def build() -> object:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("first SQL initialization failed")
        return sentinel

    if kind == "compiler":
        monkeypatch.setattr(workflow_graph_module, "build_compiled_graph_store", build)
        service = WorkflowGraphCompilerService()
        resolve = service._resolved_store
        read_field = lambda: service._store
        unwrap = lambda value: value
    elif kind == "runtime":
        monkeypatch.setattr(workflow_graph_module, "build_run_store", build)
        monkeypatch.setattr(
            workflow_graph_module,
            "WorkflowGraphRuntime",
            lambda *, store: SimpleNamespace(store=store),
        )
        service = WorkflowGraphRuntimeService()
        resolve = service._resolved_engine
        read_field = lambda: service._engine
        unwrap = lambda value: value.store
    else:
        monkeypatch.setattr(handoff_store_module, "build_run_store", build)
        service = WorkflowGraphHandoffStore()
        resolve = service._resolved_store
        read_field = lambda: service._store
        unwrap = lambda value: value

    with pytest.raises(RuntimeError, match="first SQL initialization failed"):
        resolve()
    assert read_field() is None
    assert unwrap(resolve()) is sentinel
    assert calls == 2


@pytest.mark.parametrize(
    ("builder_name", "sql_store_name", "memory_store_name"),
    [
        ("build_run_store", "SqlRunStore", "InMemoryRunStore"),
        ("build_compiled_graph_store", "SqlCompiledGraphStore", "InMemoryCompiledGraphStore"),
    ],
)
def test_store_builder_preserves_fail_closed_and_fallback_policy(
    builder_name: str,
    sql_store_name: str,
    memory_store_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_sql_init() -> None:
        raise ConnectionError("SQL unavailable")

    monkeypatch.setattr(store_module.settings, "workflow_graph_db_store_enabled", True)
    monkeypatch.setattr(store_module, sql_store_name, fail_sql_init)
    builder = getattr(store_module, builder_name)

    monkeypatch.setattr(store_module.settings, "workflow_graph_db_store_fail_closed", True)
    with pytest.raises(RuntimeError, match="fail-closed") as caught:
        builder()
    failure = getattr(caught.value, "workflow_failure", None)
    assert failure is not None
    assert failure.code == "store_unavailable"

    monkeypatch.setattr(store_module.settings, "workflow_graph_db_store_fail_closed", False)
    fallback = builder()
    assert fallback.__class__.__name__ == memory_store_name


def test_selected_fallback_is_sticky_for_service_lifetime(monkeypatch: pytest.MonkeyPatch) -> None:
    fallback = object()
    build = Mock(return_value=fallback)
    monkeypatch.setattr(workflow_graph_module, "build_compiled_graph_store", build)
    service = WorkflowGraphCompilerService()

    assert service._resolved_store() is fallback
    assert service._resolved_store() is fallback
    build.assert_called_once_with()


def test_celery_and_cli_imports_do_not_initialize_default_schema() -> None:
    code = r'''
import runpy
from sqlalchemy.engine import Engine
import langchain_community.cache as lc_cache

# Celery currently imports the pre-existing local LLM SQLite cache. Replace that
# unrelated effect so this witness can isolate the default-project schema path.
lc_cache.SQLiteCache = lambda *args, **kwargs: object()

begin_calls = []
connect_calls = []

def forbidden_begin(self, *args, **kwargs):
    begin_calls.append(type(self).__name__)
    raise AssertionError("Celery/CLI import attempted a DB transaction")

def forbidden_connect(self, *args, **kwargs):
    connect_calls.append(type(self).__name__)
    raise AssertionError("Celery/CLI import attempted a DB connection")

Engine.begin = forbidden_begin
Engine.connect = forbidden_connect
import app.celery_app  # noqa: F401
runpy.run_path("scripts/workflow_graph_smoke_local.py", run_name="contract13_import_witness")
assert begin_calls == []
assert connect_calls == []
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
