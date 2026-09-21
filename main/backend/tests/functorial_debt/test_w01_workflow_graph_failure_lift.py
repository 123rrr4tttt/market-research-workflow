"""W01 public ABI lift for W04 workflow-graph typed failures."""

from __future__ import annotations

import pytest
from functorial_kit import Failure

from app.api import workflow_graph
from app.services.workflow_graph.contracts import WorkflowGraphCompileError
from app.services.workflow_graph.curated_service import WorkflowGraphSyncConflictError


def _failure(*, code: str, public_exception: str, public_message: str, **context: object) -> Failure:
    return Failure(
        family="workflow_graph.failure",
        code=code,
        message="producer-only message",
        context={
            "owner": "workflow_graph.test",
            "operation": "workflow_graph.test",
            "public_exception": public_exception,
            "public_message": public_message,
            **context,
        },
    )


def test_w01_workflow_graph_failure_lift_preserves_explicit_compile_abi() -> None:
    failure = _failure(
        code="contract_invalid",
        public_exception="WorkflowGraphCompileError",
        public_message="dsl must be a mapping",
    )

    with pytest.raises(WorkflowGraphCompileError, match="^dsl must be a mapping$"):
        workflow_graph._unwrap_workflow_failure(failure)


def test_w01_workflow_graph_failure_lift_preserves_sync_revision_context() -> None:
    failure = _failure(
        code="revision_conflict",
        public_exception="WorkflowGraphSyncConflictError",
        public_message="conflict: revision mismatch expected=3 actual=5",
        expected_revision=3,
        actual_revision=5,
    )

    with pytest.raises(WorkflowGraphSyncConflictError) as raised:
        workflow_graph._unwrap_workflow_failure(failure)
    assert raised.value.to_details() == {
        "category": "version_conflict",
        "expected_revision": 3,
        "actual_revision": 5,
    }


def test_w01_workflow_graph_invocation_lift_precedes_normalization(monkeypatch: pytest.MonkeyPatch) -> None:
    failure = _failure(
        code="contract_invalid",
        public_exception="ValueError",
        public_message="node configuration is invalid",
    )
    monkeypatch.setattr(workflow_graph, "invoke_skill", lambda **_kwargs: {"result": failure})

    with pytest.raises(ValueError, match="^node configuration is invalid$"):
        workflow_graph._invoke_compile({"project_key": "demo"})


def test_w01_workflow_graph_failure_lift_rejects_incomplete_public_context() -> None:
    failure = Failure(
        family="workflow_graph.failure",
        code="contract_invalid",
        message="not externally serializable",
        context={"owner": "workflow_graph.test", "operation": "workflow_graph.test"},
    )

    with pytest.raises(TypeError, match="incomplete public ABI context"):
        workflow_graph._unwrap_workflow_failure(failure)
