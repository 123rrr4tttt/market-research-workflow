from __future__ import annotations

import hashlib
from typing import Any

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
) -> list[dict[str, Any]]:
    from app.services.search.hybrid import vector_search

    return vector_search(query=query, state=state, top_k=top_k)


def run_vector_search_kernel(context: NodeExecutionContext) -> NodeEffectResult:
    query = _first_nonempty(
        context.params.get("query"),
        context.inputs.get("query"),
        context.inputs.get("topic"),
    )
    state = _as_str_or_none(context.params.get("state") or context.inputs.get("state"))
    top_k = _to_int(context.params.get("top_k"), default=3, min_value=1, max_value=50)
    base_payload: dict[str, Any] = {
        "node_type": "vector_search",
        "query": query,
        "state": state,
        "top_k": top_k,
    }
    try:
        hits = _vector_search_service(query=query, state=state, top_k=top_k)
        return node_success(context, {**base_payload, "hits": hits, "degraded": False})
    except Exception as exc:  # noqa: BLE001
        return node_degraded(
            context,
            {
                **base_payload,
                "hits": [_fallback_hit(query=query, state=state)],
                "degraded": True,
                "degraded_reason": str(exc),
            },
            NodeEffectFailure(
                code="vector_search_degraded",
                message=str(exc),
                owner="workflow_graph.kernel.vector_search",
                details={},
                cause_type=type(exc).__name__,
                cause_message=str(exc),
            ),
        )


def _fallback_hit(*, query: str, state: str | None) -> dict[str, Any]:
    digest = hashlib.sha1(
        (query or "").encode("utf-8", errors="ignore"),
        usedforsecurity=False,
    ).hexdigest()[:10]
    return {
        "document_id": f"mock-{digest}",
        "score": 1.0,
        "title": f"Mock vector hit for: {query or 'empty-query'}",
        "summary": "fallback vector search result",
        "state": state,
        "backend": "mock",
        "mode": "vector",
    }


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return "empty-query"


def _as_str_or_none(value: Any) -> str | None:
    return text or None if (text := str(value or "").strip()) else None


def _to_int(value: Any, *, default: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except Exception:  # noqa: BLE001
        parsed = default
    return max(min_value, min(max_value, parsed))
