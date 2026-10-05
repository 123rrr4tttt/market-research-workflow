from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from app.services.workflow_graph.executors.join import run_join_kernel
from app.services.workflow_graph.executors.kernel import (
    NodeExecutionContext,
    execute_node,
    to_workflow_graph_failure,
)
from app.services.workflow_graph.executors.llm_call import run_llm_call_kernel
from app.services.workflow_graph.executors.vector_search import run_vector_search_kernel
from app.services.workflow_graph.contracts import (
    WorkflowGraphCompileError,
    raise_workflow_graph_legacy,
)


pytestmark = pytest.mark.unit


def _context(
    node_type: str,
    *,
    params: dict[str, Any] | None = None,
    inputs: dict[str, Any] | None = None,
    upstream: dict[str, Any] | None = None,
) -> NodeExecutionContext:
    return NodeExecutionContext(
        node_id="node-1",
        node_type=node_type,  # type: ignore[arg-type]
        params=params or {},
        inputs=inputs or {},
        input_trace={"query": {"source": "input"}},
        upstream_results=upstream or {},
        correlation_id="run-1",
    )


def test_join_kernel_is_pure_and_binds_node_identity() -> None:
    context = _context(
        "join",
        params={"field": "text"},
        upstream={"left": {"text": "a"}, "right": {"text": "b"}},
    )

    result = run_join_kernel(context)

    assert result.node_id == "node-1"
    assert result.node_type == "join"
    assert result.status == "SUCCEEDED"
    assert result.failure is None
    assert result.payload["values"] == ["a", "b"]
    assert result.payload["sources"] == ["left", "right"]


def test_vector_search_kernel_reports_success_without_runtime_state() -> None:
    context = _context(
        "vector_search",
        params={"query": "ai market", "top_k": 2, "state": "CA"},
    )

    with patch(
        "app.services.workflow_graph.executors.vector_search._vector_search_service",
        return_value=[{"document_id": "doc-1"}],
    ) as search:
        result = run_vector_search_kernel(context)

    assert result.status == "SUCCEEDED"
    assert result.payload["hits"] == [{"document_id": "doc-1"}]
    assert result.payload["degraded"] is False
    assert search.call_count == 1


def test_vector_search_kernel_returns_typed_degraded_result() -> None:
    context = _context("vector_search", params={"query": "unreachable"})

    with patch(
        "app.services.workflow_graph.executors.vector_search._vector_search_service",
        side_effect=RuntimeError("search unavailable"),
    ):
        result = run_vector_search_kernel(context)

    assert result.status == "DEGRADED"
    assert result.failure is not None
    assert result.failure.code == "vector_search_degraded"
    assert result.failure.cause_type == "RuntimeError"
    assert result.payload["hits"][0]["backend"] == "mock"
    assert result.payload["degraded"] is True


def test_llm_kernel_success_and_failure_are_directly_interpretable() -> None:
    context = _context("llm_call", params={"prompt": "hello"}, inputs={"trace_id": "trace-1"})

    with (
        patch(
            "app.services.workflow_graph.executors.llm_call.get_llm_config",
            return_value={"model": "cfg-model", "temperature": 0.3},
        ),
        patch(
            "app.services.workflow_graph.executors.llm_call._invoke_llm_via_skill",
            return_value="ok",
        ) as invoke,
    ):
        result = run_llm_call_kernel(context)

    assert result.status == "SUCCEEDED"
    assert result.payload["text"] == "ok"
    assert result.payload["model"] == "cfg-model"
    assert result.payload["trace_id"] == "trace-1"
    assert invoke.call_count == 1

    missing = _context(
        "llm_call",
        params={"prompt_template": "Answer {query}"},
        inputs={},
    )
    with patch(
        "app.services.workflow_graph.executors.llm_call._invoke_llm_via_skill",
    ) as invoke:
        failed = run_llm_call_kernel(missing)

    assert failed.status == "FAILED"
    assert failed.failure is not None
    assert failed.failure.code == "required_input_missing"
    assert failed.failure.details["missing"] == ["query"]
    projected = to_workflow_graph_failure(failed)
    assert projected is not None
    assert projected.code == "required_input_missing"
    assert projected.context["owner"] == "workflow_graph.kernel.llm_call"
    assert invoke.call_count == 0


def test_execute_node_dispatches_without_workflow_or_store() -> None:
    context = _context(
        "join",
        upstream={"left": {"value": 1}},
    )

    result = execute_node(context)

    assert result.payload["joined"] == {"left": {"value": 1}}
    assert not hasattr(context, "workflow")
    assert not hasattr(context, "run_id")


def test_typed_llm_failure_projects_to_current_workflow_failure_abi() -> None:
    missing = _context(
        "llm_call",
        params={"prompt_template": "Answer {query}"},
    )
    failed = run_llm_call_kernel(missing)

    with pytest.raises(WorkflowGraphCompileError) as caught:
        failure = to_workflow_graph_failure(failed)
        assert failure is not None
        raise_workflow_graph_legacy(failure)

    assert caught.value.workflow_failure.code == "required_input_missing"
