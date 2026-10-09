from __future__ import annotations

import hashlib

from ..contracts import WorkflowJsonObject, WorkflowJsonValue
from .kernel import (
    NodeExecutionContext,
    NodeEffectFailure,
    NodeEffectResult,
    node_degraded,
    node_success,
)


def _vector_search_service(
    query: str,
    state: str | None,
    top_k: int,
) -> list[WorkflowJsonObject]:
    from app.services.search.hybrid import vector_search

    return [
        hit
        for hit in vector_search(query=query, state=state, top_k=top_k)
    ]


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
        hits: list[WorkflowJsonValue] = [
            hit for hit in _vector_search_service(query=query, state=state, top_k=top_k)
        ]
        payload = dict(base_payload)
        payload.update({"hits": hits, "degraded": False})
        return node_success(context, payload)
    except Exception as exc:  # noqa: BLE001
        fallback_hits: list[WorkflowJsonValue] = [_fallback_hit(query=query, state=state)]
        payload = dict(base_payload)
        payload.update(
            {
                "hits": fallback_hits,
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


def _fallback_hit(*, query: str, state: str | None) -> WorkflowJsonObject:
    digest = hashlib.sha1(
        (query or "").encode("utf-8", errors="ignore"),
        usedforsecurity=False,
    ).hexdigest()[:10]
    return {
        "material_id": f"mock-{digest}",
        "score": 1.0,
        "title": f"Mock vector hit for: {query or 'empty-query'}",
        "summary": "fallback vector search result",
        "state": state,
        "backend": "mock",
        "mode": "vector",
    }


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
