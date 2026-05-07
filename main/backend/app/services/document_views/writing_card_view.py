from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from ...contracts.schemas.writing import KeywordCardItem


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_card_id(source_type: str, title: str, url: str | None, normalized_query: str) -> str:
    payload = f"{source_type}|{title}|{url or ''}|{normalized_query}"
    return hashlib.sha1(payload.encode("utf-8", errors="ignore")).hexdigest()[:24]


def build_keyword_card(
    *,
    source_type: str,
    title: str,
    snippet: str,
    url: str | None,
    score: float,
    publisher: str | None,
    published_at: str | None,
    evidence: str | None,
    normalized_query: str,
    extra: dict[str, Any] | None = None,
) -> KeywordCardItem:
    return KeywordCardItem(
        card_id=make_card_id(source_type, title, url, normalized_query),
        source_type=source_type,
        title=title[:300] or "Untitled",
        snippet=(snippet or evidence or "")[:2000],
        url=url,
        score=max(0.0, float(score or 0.0)),
        publisher=(publisher or "")[:255] or None,
        published_at=published_at,
        retrieved_at=now_iso(),
        evidence=(evidence or "")[:2000] or None,
        relevance_tags=[normalized_query] if normalized_query else [],
        credibility=min(1.0, max(0.0, float(score or 0.0))) if score is not None else None,
        quick_actions=["insert_quote", "insert_summary", "open_detail"],
        extra=extra or {},
    )


def build_keyword_card_from_hybrid_row(row: dict[str, Any], *, normalized_query: str) -> KeywordCardItem:
    title = str(row.get("title") or row.get("document_title") or row.get("id") or "Document").strip()
    snippet = str(row.get("snippet") or row.get("summary") or row.get("content") or "").strip()
    score = float(row.get("score") or row.get("_score") or 0.6)
    url = str(row.get("url") or row.get("uri") or "").strip() or None
    publisher = str(row.get("publisher") or row.get("source") or "document").strip() or None
    published_at = str(row.get("published_at") or row.get("publish_date") or "").strip() or None
    return build_keyword_card(
        source_type="document",
        title=title,
        snippet=snippet,
        url=url,
        score=score,
        publisher=publisher,
        published_at=published_at,
        evidence=str(row.get("evidence") or "").strip() or None,
        normalized_query=normalized_query,
        extra={"backend": row.get("backend"), "document_id": row.get("document_id")},
    )


def build_keyword_card_from_source_row(row: dict[str, Any], *, normalized_query: str) -> KeywordCardItem:
    publisher = str(row.get("publisher") or "").strip() or None
    source_type = "graph" if publisher and publisher.startswith("graph:") else "resource"
    score = 0.72 if source_type == "graph" else 0.65
    return build_keyword_card(
        source_type=source_type,
        title=str(row.get("title") or "Source").strip(),
        snippet=str(row.get("evidence") or "").strip(),
        url=str(row.get("url") or "").strip() or None,
        score=score,
        publisher=publisher,
        published_at=str(row.get("published_at") or "").strip() or None,
        evidence=str(row.get("evidence") or "").strip() or None,
        normalized_query=normalized_query,
        extra={"source_id": row.get("id")},
    )


def build_keyword_card_from_material_item(item: dict[str, Any], *, normalized_query: str) -> KeywordCardItem:
    title = str(item.get("name") or item.get("item_key") or "Material").strip()
    return build_keyword_card(
        source_type="resource",
        title=title,
        snippet=str(item.get("description") or item.get("item_key") or "").strip(),
        url=None,
        score=0.55,
        publisher="source_library",
        published_at=None,
        evidence=str(item.get("item_key") or "").strip() or None,
        normalized_query=normalized_query,
        extra={"item_key": item.get("item_key"), "channel_key": item.get("channel_key")},
    )


def build_keyword_card_from_graph_node(
    node: dict[str, Any],
    *,
    normalized_query: str,
    graph_context: dict[str, Any],
) -> KeywordCardItem:
    node_id = str(node.get("node_id") or "").strip()
    title = str(node.get("title") or node.get("label") or node_id or "Graph Node").strip()
    evidence = str(node.get("summary") or node.get("evidence") or "").strip()
    source_uri = str(node.get("source_uri") or node.get("uri") or "").strip() or None
    publisher = f"graph:{str(node.get('node_type') or 'node').strip() or 'node'}"
    return build_keyword_card(
        source_type="graph",
        title=title,
        snippet=evidence,
        url=source_uri,
        score=0.74,
        publisher=publisher,
        published_at=None,
        evidence=evidence or f"Graph node {node_id or title} selected by curated workflow graph.",
        normalized_query=normalized_query,
        extra={
            "graph_node_id": node_id or None,
            "context_boundary": "graph_context",
            "graph_contract_version": graph_context.get("contract_version"),
            "graph_revision": graph_context.get("revision"),
        },
    )
