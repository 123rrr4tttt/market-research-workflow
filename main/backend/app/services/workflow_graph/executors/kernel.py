from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from functorial_kit import Failure

from ..contracts import WorkflowJsonObject


NodeEffectStatus = Literal["SUCCEEDED", "DEGRADED", "FAILED"]
WorkflowNodeType = Literal["vector_search", "llm_call", "join"]


@dataclass(frozen=True, slots=True)
class NodeExecutionContext:
    """Caller-owned inputs for one node effect."""

    node_id: str
    node_type: WorkflowNodeType
    params: WorkflowJsonObject
    inputs: WorkflowJsonObject
    input_trace: WorkflowJsonObject
    upstream_results: WorkflowJsonObject
    correlation_id: str = ""


@dataclass(frozen=True, slots=True)
class NodeEffectFailure:
    code: str
    message: str
    owner: str
    details: WorkflowJsonObject
    cause_type: str | None = None
    cause_message: str | None = None


@dataclass(frozen=True, slots=True)
class NodeEffectResult:
    node_id: str
    node_type: WorkflowNodeType
    status: NodeEffectStatus
    payload: WorkflowJsonObject
    failure: NodeEffectFailure | None = None

    @property
    def legacy_payload(self) -> WorkflowJsonObject:
        return self.payload


def node_success(
    context: NodeExecutionContext,
    payload: WorkflowJsonObject,
) -> NodeEffectResult:
    return NodeEffectResult(
        node_id=context.node_id,
        node_type=context.node_type,
        status="SUCCEEDED",
        payload=payload,
    )


def node_degraded(
    context: NodeExecutionContext,
    payload: WorkflowJsonObject,
    failure: NodeEffectFailure,
) -> NodeEffectResult:
    return NodeEffectResult(
        node_id=context.node_id,
        node_type=context.node_type,
        status="DEGRADED",
        payload=payload,
        failure=failure,
    )


def node_failed(
    context: NodeExecutionContext,
    code: str,
    message: str,
    *,
    owner: str,
    details: WorkflowJsonObject,
) -> NodeEffectResult:
    return NodeEffectResult(
        node_id=context.node_id,
        node_type=context.node_type,
        status="FAILED",
        payload={},
        failure=NodeEffectFailure(
            code=code,
            message=message,
            owner=owner,
            details=details,
        ),
    )


def execute_node(context: NodeExecutionContext) -> NodeEffectResult:
    if context.node_type == "join":
        from .join import run_join_kernel

        return run_join_kernel(context)
    if context.node_type == "llm_call":
        from .llm_call import run_llm_call_kernel

        return run_llm_call_kernel(context)
    from .vector_search import run_vector_search_kernel

    return run_vector_search_kernel(context)


def to_workflow_graph_failure(result: NodeEffectResult) -> Failure | None:
    """Project one typed kernel failure onto the current workflow failure ABI."""

    from ..contracts import WorkflowGraphCompileError, workflow_graph_failure

    if result.failure is None:
        return None
    return workflow_graph_failure(
        result.failure.code,
        result.failure.message,
        owner=result.failure.owner,
        public_exception=WorkflowGraphCompileError,
        public_message=result.failure.message,
        **dict(result.failure.details),
    )
