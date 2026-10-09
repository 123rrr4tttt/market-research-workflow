from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.llm.ports import ChatModelOptions
from app.services.workflow_graph.executors.join import run_join_kernel
from app.services.workflow_graph.executors.kernel import (
    NodeExecutionContext,
    WorkflowNodeType,
    execute_node,
    to_workflow_graph_failure,
)
from app.services.workflow_graph.executors.llm_call import (
    invoke_workflow_llm_call_skill,
    run_llm_call_kernel,
)
from app.services.workflow_graph.executors.vector_search import run_vector_search_kernel
from app.services.workflow_graph.contracts import (
    WorkflowGraphCompileError,
    WorkflowJsonObject,
    raise_workflow_graph_legacy,
)


pytestmark = pytest.mark.unit


def _context(
    node_type: WorkflowNodeType,
    *,
    params: WorkflowJsonObject | None = None,
    inputs: WorkflowJsonObject | None = None,
    upstream: WorkflowJsonObject | None = None,
) -> NodeExecutionContext:
    return NodeExecutionContext(
        node_id="node-1",
        node_type=node_type,
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
        return_value=[{"material_id": "material-1"}],
    ) as search:
        result = run_vector_search_kernel(context)

    assert result.status == "SUCCEEDED"
    assert result.payload["hits"] == [{"material_id": "material-1"}]
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
    hits = result.payload["hits"]
    assert isinstance(hits, list)
    first_hit = hits[0]
    assert isinstance(first_hit, dict)
    assert first_hit["backend"] == "mock"
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
    assert projected.context is not None
    assert projected.context["owner"] == "workflow_graph.kernel.llm_call"
    assert invoke.call_count == 0


def test_llm_skill_passes_validated_options_to_registered_provider() -> None:
    captured: list[ChatModelOptions] = []

    class _Chat:
        def invoke(self, prompt: str) -> SimpleNamespace:
            return SimpleNamespace(content=f"provider:{prompt}")

    class _Provider:
        def get_chat_model(self, options: ChatModelOptions) -> _Chat:
            captured.append(options)
            return _Chat()

    with patch(
        "app.services.llm.ports.resolve_llm_provider",
        return_value=_Provider(),
    ):
        result = invoke_workflow_llm_call_skill(
            {
                "prompt": "hello",
                "model": "typed-model",
                "temperature": 0.25,
                "extra": {"seed": 7},
            }
        )

    assert result == {"text": "provider:hello"}
    assert len(captured) == 1
    assert captured[0].model == "typed-model"
    assert captured[0].temperature == 0.25
    assert captured[0].extra == {"seed": 7}


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

    assert str(caught.value) == "prompt_template_missing_inputs:query"
