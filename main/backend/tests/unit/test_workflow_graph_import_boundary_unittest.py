"""Focused tests for lazy workflow-graph runtime effects."""

# ruff: noqa: E402

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BACKEND_ROOT.parent.parent
for path in (str(BACKEND_ROOT), str(REPOSITORY_ROOT / "src")):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.services import workflow_graph as workflow_graph_module
from app.services.workflow_graph import WorkflowGraphCompilerService, WorkflowGraphRuntimeService
from app.services.workflow_graph import handoff_store as handoff_store_module
from app.services.workflow_graph.handoff_store import WorkflowGraphHandoffStore


pytestmark = pytest.mark.unit


def test_importing_workflow_graph_package_never_opens_a_database_transaction() -> None:
    code = """
from sqlalchemy.engine import Engine

begin_calls = []

def forbidden_begin(self):
    begin_calls.append(self)
    raise AssertionError("workflow_graph import attempted a database transaction")

Engine.begin = forbidden_begin
import app.services.workflow_graph  # noqa: F401
import app.services.workflow_graph.handoff_store  # noqa: F401
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


def test_compiler_store_is_built_only_when_a_store_operation_is_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build_store = Mock(side_effect=RuntimeError("compiled store unavailable"))
    monkeypatch.setattr(workflow_graph_module, "build_compiled_graph_store", build_store)

    service = WorkflowGraphCompilerService()

    build_store.assert_not_called()
    with pytest.raises(RuntimeError, match="compiled store unavailable"):
        service.get_compiled("graph-1")
    build_store.assert_called_once()


def test_runtime_store_is_built_only_when_a_runtime_operation_is_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build_store = Mock(side_effect=RuntimeError("run store unavailable"))
    monkeypatch.setattr(workflow_graph_module, "build_run_store", build_store)

    service = WorkflowGraphRuntimeService()

    build_store.assert_not_called()
    with pytest.raises(RuntimeError, match="run store unavailable"):
        service.get_run("run-1")
    build_store.assert_called_once()


def test_handoff_store_is_built_only_when_a_handoff_operation_is_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build_store = Mock(side_effect=RuntimeError("handoff store unavailable"))
    monkeypatch.setattr(handoff_store_module, "build_run_store", build_store)

    service = WorkflowGraphHandoffStore()

    build_store.assert_not_called()
    with pytest.raises(RuntimeError, match="handoff store unavailable"):
        service.list_handoffs(run_id="run-1")
    build_store.assert_called_once()
