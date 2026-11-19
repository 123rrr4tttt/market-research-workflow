from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.search.hybrid import SearchInvocationObservation
from app.services.skill_runtime import invoke_skill
from app.services.workflow_graph.executors.join import run_join_kernel
from app.services.workflow_graph.executors.kernel import (
    NodeExecutionContext,
    WorkflowNodeType,
    execute_node,
    to_workflow_graph_failure,
)
from app.services.workflow_graph.executors.llm_call import run_llm_call_kernel
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
        "app.services.workflow_graph.executors.vector_search._observe_vector_search_service",
        return_value=SearchInvocationObservation([{"material_id": "material-1"}], ("qdrant",), ()),
    ) as search:
        result = run_vector_search_kernel(context)

    assert result.status == "SUCCEEDED"
    assert result.payload["hits"] == [{"material_id": "material-1"}]
    assert result.payload["degraded"] is False
    assert search.call_count == 1


def test_vector_search_kernel_returns_typed_degraded_result() -> None:
    context = _context("vector_search", params={"query": "unreachable"})

    with patch(
        "app.services.workflow_graph.executors.vector_search._observe_vector_search_service",
        side_effect=RuntimeError("search unavailable"),
    ):
        result = run_vector_search_kernel(context)

    assert result.status == "DEGRADED"
    assert result.failure is not None
    assert result.failure.code == "vector_search_degraded"
    assert result.failure.cause_type == "RuntimeError"
    hits = result.payload["hits"]
    assert isinstance(hits, list)
    assert hits == []
    assert result.payload["used_backends"] == []
    assert result.payload["degraded"] is True


def test_llm_kernel_missing_cell_binding_is_a_failure_not_an_output() -> None:
    result = execute_node(_context("llm_call", params={"prompt": "hello"}))

    assert result.status == "FAILED"
    assert result.payload == {}
    failure = to_workflow_graph_failure(result)
    assert failure is not None
    assert failure.code == "executor_not_registered"
    assert failure.context is not None
    assert failure.context["capability"] == "workflow.llm_call"
    assert failure.context["binding"] == "agent_cell"


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"prompt": "hello", "model": "requested-model"}, "executor_not_registered"),
        ({"prompt": "  "}, "contract_invalid"),
        ([], "contract_invalid"),
    ],
)
def test_registered_llm_skill_preserves_contract_errors_and_fails_without_a_cell(
    payload: object,
    code: str,
) -> None:
    with (
        patch("app.services.llm.ports.resolve_llm_provider") as provider,
        pytest.raises(WorkflowGraphCompileError) as caught,
    ):
        invoke_skill(
            skill_id="workflow.llm_call",
            payload=payload,
            context={"actor_role": "orchestration_runtime", "permissions": ["workflow.llm_call"]},
        )
    provider.assert_not_called()
    assert caught.value.workflow_failure.code == code


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
    context = caught.value.workflow_failure.context
    assert context["owner"] == "workflow_graph.kernel.llm_call"
    assert context["missing"] == ["query"]
