from __future__ import annotations

import hashlib
from typing import Any

from .base import BaseNodeExecutor, NodeExecutionContext


def _vector_search_service(query: str, state: str | None, top_k: int) -> list[dict[str, Any]]:
    from app.services.search.hybrid import vector_search

    return vector_search(query=query, state=state, top_k=top_k)


class VectorSearchExecutor(BaseNodeExecutor):
    node_type = "vector_search"

    def execute(self, node: dict[str, Any], context: NodeExecutionContext) -> dict[str, Any]:
        params = dict(node.get("params") or {})
        query = _first_nonempty(params.get("query"), context.inputs.get("query"), context.inputs.get("topic"))
        state = _as_str_or_none(params.get("state") or context.inputs.get("state"))
        top_k = _to_int(params.get("top_k"), default=3, min_value=1, max_value=50)

        try:
            hits = _vector_search_service(query=query, state=state, top_k=top_k)
            return {
                "node_type": self.node_type,
                "query": query,
                "state": state,
                "top_k": top_k,
                "hits": hits,
                "degraded": False,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "node_type": self.node_type,
                "query": query,
                "state": state,
                "top_k": top_k,
                "hits": [_fallback_hit(query=query, state=state)],
                "degraded": True,
                "degraded_reason": str(exc),
            }


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
    text = str(value or "").strip()
    return text or None


def _to_int(value: Any, *, default: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except Exception:  # noqa: BLE001
        parsed = default
    return max(min_value, min(max_value, parsed))
