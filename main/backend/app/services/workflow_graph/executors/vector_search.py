from __future__ import annotations

from typing import TYPE_CHECKING

from ...search.hybrid import search_failure_payload

if TYPE_CHECKING:
    from ...search.hybrid import SearchInvocationObservation

from ..contracts import WorkflowJsonObject, WorkflowJsonValue
from .kernel import (
    NodeExecutionContext,
    NodeEffectFailure,
    NodeEffectResult,
    node_degraded,
    node_success,
)

def run_vector_search_kernel(context: NodeExecutionContext) -> NodeEffectResult:
    query = _first_nonempty(
        context.params.get("query"),
        context.inputs.get("query"),
        context.inputs.get("topic"),
    )
    state = _as_str_or_none(context.params.get("state") or context.inputs.get("state"))
    top_k = _to_int(context.params.get("top_k"), default=3, min_value=1, max_value=50)
    base_payload: WorkflowJsonObject = {
        "node_type": "vector_search",
        "query": query,
        "state": state,
        "top_k": top_k,
    }
    try:
        observation = _observe_vector_search_service(query=query, state=state, top_k=top_k)
        hits: list[WorkflowJsonValue] = [hit for hit in observation.hits]
        failures: list[WorkflowJsonValue] = [
            search_failure_payload(failure) for failure in observation.failures
        ]
        payload = dict(base_payload)
        payload["hits"] = hits
        payload["used_backends"] = list(observation.used_backends)
        payload["failures"] = failures
        payload["degraded"] = bool(failures and not hits and not observation.used_backends)
        if payload["degraded"]:
            return node_degraded(
                context,
                payload,
                NodeEffectFailure(
                    code="vector_search_degraded",
                    message="; ".join(
                        failure.message
                        for failure in observation.failures
                    ),
                    owner="workflow_graph.kernel.vector_search",
                    details={},
                    cause_type="SearchBackendFailure",
                    cause_message="all vector search backends failed",
                ),
            )
        return node_success(context, payload)
    except Exception as exc:  # noqa: BLE001
        payload = dict(base_payload)
        payload.update(
            {
                "hits": [],
                "used_backends": [],
                "failures": [
                    {
                        "code": "vector_search_failed",
                        "message": str(exc),
                        "provider": "unknown",
                        "owner": "workflow_graph.kernel.vector_search",
                        "exception_type": type(exc).__name__,
                    }
                ],
                "degraded": True,
                "degraded_reason": str(exc),
            }
        )
        return node_degraded(
            context,
            payload,
            NodeEffectFailure(
                code="vector_search_degraded",
                message=str(exc),
                owner="workflow_graph.kernel.vector_search",
                details={},
                cause_type=type(exc).__name__,
                cause_message=str(exc),
            ),
        )


def _observe_vector_search_service(
    *, query: str, state: str | None, top_k: int
) -> SearchInvocationObservation:
    from app.services.search.hybrid import observe_vector_search

    return observe_vector_search(query=query, state=state, top_k=top_k)


def _first_nonempty(*values: object) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return "empty-query"


def _as_str_or_none(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _to_int(value: object, *, default: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value) if isinstance(value, str | int | float) and not isinstance(value, bool) else default
    except (TypeError, ValueError):
        parsed = default
    return max(min_value, min(max_value, parsed))
