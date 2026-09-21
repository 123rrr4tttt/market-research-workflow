from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest
from functorial_kit import Failure
from mrw_functorial_kit.core.w04_service_semantics import workflow_graph_failures

os.environ["WORKFLOW_GRAPH_DB_STORE_ENABLED"] = "false"

from app.services.workflow_graph.compiler import compile_workflow_graph, try_compile_workflow_graph
from app.services.workflow_graph.contracts import WorkflowGraphCompileError, raise_workflow_graph_legacy
from app.services.workflow_graph.contracts import workflow_graph_failure
from app.services.workflow_graph.executors.base import BaseNodeExecutor
from app.services.workflow_graph.runtime import WorkflowGraphRuntime
from app.services.workflow_graph.store import InMemoryRunStore
from app.services.workflow_graph.schema import parse_workflow_graph_dsl, try_parse_workflow_graph_dsl


REPO_ROOT = Path(__file__).resolve().parents[4]


def test_typed_schema_failure_has_exact_family_and_context() -> None:
    failure = try_parse_workflow_graph_dsl({"nodes": "bad"})
    assert isinstance(failure, Failure)
    assert workflow_graph_failures.matches(failure)
    assert (failure.family, failure.code, failure.message) == (
        "workflow_graph.failure",
        "contract_invalid",
        "nodes must be a list",
    )
    assert failure.context == {
        "owner": "workflow_graph.schema",
        "public_exception": "WorkflowGraphCompileError",
        "public_message": "nodes must be a list",
        "index": -1,
        "field": "nodes",
    }


def test_typed_compile_failures_and_schema_failures_are_propagated() -> None:
    duplicate = try_compile_workflow_graph(
        {"nodes": [{"id": "a", "node_type": "join"}, {"id": "a", "node_type": "join"}]}
    )
    assert isinstance(duplicate, Failure)
    assert duplicate.code == "contract_invalid"
    assert duplicate.context["field"] == "node_id"

    cycle = try_compile_workflow_graph(
        {
            "nodes": [
                {"id": "a", "node_type": "join"},
                {"id": "b", "node_type": "join"},
            ],
            "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "a"}],
        }
    )
    assert isinstance(cycle, Failure)
    assert cycle.code == "integrity_invalid"
    assert cycle.context["field"] == "edges"


def test_public_compile_abi_and_topology_checksum_are_preserved() -> None:
    with pytest.raises(WorkflowGraphCompileError, match="nodes must be a list"):
        parse_workflow_graph_dsl({"nodes": "bad"})

    with pytest.raises(WorkflowGraphCompileError, match="duplicate node_id: a"):
        compile_workflow_graph(
            {"nodes": [{"id": "a", "node_type": "join"}, {"id": "a", "node_type": "join"}]}
        )

    graph = compile_workflow_graph(
        {
            "version": "1.0",
            "options": {"mode": "test"},
            "nodes": [
                {"id": "a", "node_type": "join"},
                {"id": "b", "node_type": "join"},
            ],
            "edges": [{"from": "a", "to": "b"}],
        }
    )
    assert graph.topo_order == ("a", "b")
    assert graph.outgoing_edges == {"a": ("b",), "b": ()}
    assert graph.incoming_edges == {"a": (), "b": ("a",)}
    assert len(graph.checksum) == 64


def test_legacy_lift_rejects_wrong_family_as_programmer_defect() -> None:
    failure = Failure(
        family="other.failure",
        code="contract_invalid",
        message="bad",
        context={
            "owner": "workflow_graph.schema",
            "public_exception": "WorkflowGraphCompileError",
            "public_message": "bad",
        },
    )
    with pytest.raises(TypeError, match="failure lift context"):
        raise_workflow_graph_legacy(failure)


def test_workflow_graph_legacy_lift_with_exception_kwargs() -> None:
    class CustomError(ValueError):
        def __init__(self, *, marker: str):
            super().__init__(marker)

    failure = workflow_graph_failure(
        "contract_invalid",
        "bad",
        owner="workflow_graph.test",
        public_exception=CustomError,
        public_message="bad",
    )
    with pytest.raises(CustomError, match="marker") as raised:
        raise_workflow_graph_legacy(
            failure,
            exception_type=CustomError,
            exception_kwargs={"marker": "marker"},
        )
    assert getattr(raised.value, "workflow_failure") is failure


def test_workflow_graph_legacy_lift_with_exception_kwargs_and_cause() -> None:
    class CustomError(ValueError):
        def __init__(self, *, marker: str):
            super().__init__(marker)

    failure = workflow_graph_failure(
        "contract_invalid",
        "bad",
        owner="workflow_graph.test",
        public_exception=CustomError,
        public_message="bad",
    )
    cause = RuntimeError("cause")
    with pytest.raises(CustomError, match="marker") as raised:
        raise_workflow_graph_legacy(
            failure,
            exception_type=CustomError,
            cause=cause,
            exception_kwargs={"marker": "marker"},
        )
    assert raised.value.__cause__ is cause


def test_workflow_graph_legacy_lift_preserves_cause() -> None:
    failure = workflow_graph_failure(
        "contract_invalid",
        "bad",
        owner="workflow_graph.test",
        public_exception=WorkflowGraphCompileError,
        public_message="bad",
    )
    cause = RuntimeError("cause")
    with pytest.raises(WorkflowGraphCompileError, match="bad") as raised:
        raise_workflow_graph_legacy(failure, cause=cause)
    assert raised.value.__cause__ is cause


def test_contract_core_raise_sites_are_only_centralized_lifts() -> None:
    paths = (
        REPO_ROOT / "main/backend/app/services/workflow_graph/contracts.py",
        REPO_ROOT / "main/backend/app/services/workflow_graph/schema.py",
        REPO_ROOT / "main/backend/app/services/workflow_graph/compiler.py",
    )
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        raises = [node for node in ast.walk(tree) if isinstance(node, ast.Raise)]
        if path.name != "contracts.py":
            assert not raises
        else:
            parent: dict[ast.AST, ast.AST] = {}
            for node in ast.walk(tree):
                for child in ast.iter_child_nodes(node):
                    parent[child] = node
            enclosing_names: list[str] = []
            for node in raises:
                current = parent.get(node)
                while current is not None and not isinstance(
                    current, (ast.FunctionDef, ast.AsyncFunctionDef)
                ):
                    current = parent.get(current)
                assert isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef))
                enclosing_names.append(current.name)
            assert set(enclosing_names) == {"raise_workflow_graph_legacy"}


def test_workflow_graph_raise_inventory_has_only_shared_lift_and_abstract_boundary() -> None:
    owned = (
        "__init__.py",
        "curated_service.py",
        "edit_contract.py",
        "executors/base.py",
        "executors/llm_call.py",
        "governance_contract.py",
        "handoff_store.py",
        "runtime.py",
        "store.py",
        "templates.py",
    )
    root = REPO_ROOT / "main/backend/app/services/workflow_graph"
    for name in owned:
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        raises = [node for node in ast.walk(tree) if isinstance(node, ast.Raise)]
        if name == "executors/base.py":
            assert len(raises) == 1
            source = (root / name).read_text(encoding="utf-8")
            assert "class=PROGRAMMER_DEFECT" in source
        else:
            assert not raises


def test_runtime_events_preserve_known_failure_provenance() -> None:
    class FailingExecutor(BaseNodeExecutor):
        node_type = "join"

        def execute(self, node, context):
            failure = workflow_graph_failure(
                "required_input_missing",
                "required input missing: x",
                owner="workflow_graph.test_executor",
                public_exception=WorkflowGraphCompileError,
                public_message="required input missing: x",
                field="input",
                index=-1,
            )
            raise_workflow_graph_legacy(failure)

    runtime = WorkflowGraphRuntime(store=InMemoryRunStore(), executors=[FailingExecutor()])
    snapshot = runtime.run({"workflow_id": "g", "nodes": [{"id": "n", "node_type": "join"}]})
    failed = [event for event in snapshot["events"] if event["type"] == "node.failed"][0]
    assert failed["payload"]["failure_family"] == "workflow_graph.failure"
    assert failed["payload"]["failure_code"] == "required_input_missing"
    assert failed["payload"]["failure_context"]["owner"] == "workflow_graph.test_executor"


def test_base_node_executor_abstract_execute_is_not_implemented() -> None:
    class BareExecutor(BaseNodeExecutor):
        node_type = "join"

        def execute(self, node, context):
            return super().execute(node, context)

    executor = BareExecutor()
    with pytest.raises(NotImplementedError):
        executor.execute({}, None)
