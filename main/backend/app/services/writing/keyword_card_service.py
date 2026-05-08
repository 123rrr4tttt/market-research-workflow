from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

from ...contracts.schemas.writing import (
    KeywordCardDetailRequest,
    KeywordCardDetailResponse,
    KeywordCardItem,
    KeywordCardListResponse,
    KeywordCardPreviewRequest,
    KeywordCardPreviewResponse,
    KeywordCardRequest,
)
from ..document_queries import (
    query_hybrid_document_rows,
    query_report_source_rows,
    query_source_library_material_rows,
)
from ..document_views import (
    build_keyword_card_from_graph_node,
    build_keyword_card_from_hybrid_row,
    build_keyword_card_from_material_item,
    build_keyword_card_from_source_row,
)
from ..search.hybrid import get_last_used_backends

_CARD_CACHE: dict[str, dict[str, Any]] = {}
_SELECTION_CACHE: dict[str, KeywordCardListResponse] = {}
_CACHE_TTL_MS = 10_000
_QUERY_SPLIT_RE = re.compile(r"\s+")


def normalize_and_rewrite_query(text: str) -> str:
    normalized = " ".join(_QUERY_SPLIT_RE.split(str(text or "").strip().lower()))
    return normalized


def _selection_hash(project_key: str, query: str) -> str:
    payload = f"{project_key}:{normalize_and_rewrite_query(query)}"
    return hashlib.sha1(
        payload.encode("utf-8", errors="ignore"),
        usedforsecurity=False,
    ).hexdigest()[:16]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _remember_card(item: KeywordCardItem, *, normalized_query: str, raw: dict[str, Any]) -> None:
    _CARD_CACHE[item.card_id] = {
        "item": item.model_dump(),
        "normalized_query": normalized_query,
        "raw": raw,
        "cached_at": _now_iso(),
    }


def _cards_from_hybrid(query: str, limit: int) -> list[tuple[KeywordCardItem, dict[str, Any]]]:
    normalized_query = normalize_and_rewrite_query(query)
    rows = query_hybrid_document_rows(query, limit=limit)
    cards: list[tuple[KeywordCardItem, dict[str, Any]]] = []
    for row in rows:
        card = build_keyword_card_from_hybrid_row(row, normalized_query=normalized_query)
        cards.append((card, row))
    return cards


def _cards_from_sources(query: str, limit: int) -> list[tuple[KeywordCardItem, dict[str, Any]]]:
    normalized_query = normalize_and_rewrite_query(query)
    rows = query_report_source_rows(query, limit=limit)
    cards: list[tuple[KeywordCardItem, dict[str, Any]]] = []
    for row in rows:
        card = build_keyword_card_from_source_row(row, normalized_query=normalized_query)
        cards.append((card, row))
    return cards


def _cards_from_source_library(project_key: str, query: str, limit: int) -> list[tuple[KeywordCardItem, dict[str, Any]]]:
    normalized_query = normalize_and_rewrite_query(query)
    items = query_source_library_material_rows(project_key, query=query)
    cards: list[tuple[KeywordCardItem, dict[str, Any]]] = []
    for item in items:
        card = build_keyword_card_from_material_item(item, normalized_query=normalized_query)
        cards.append((card, item))
        if len(cards) >= limit:
            break
    return cards


def _extract_graph_context(payload: KeywordCardRequest) -> dict[str, Any]:
    if isinstance(payload.context, dict):
        nested = payload.context.get("graph_context")
        if isinstance(nested, dict):
            return nested
    if getattr(payload, "context", None) is not None and isinstance(payload.context.graph_context, dict):
        return payload.context.graph_context
    return payload.graph_context if isinstance(payload.graph_context, dict) else {}


def _cards_from_graph_context(payload: KeywordCardRequest, limit: int) -> list[tuple[KeywordCardItem, dict[str, Any]]]:
    graph_context = _extract_graph_context(payload)
    selected_nodes = graph_context.get("selected_nodes") if isinstance(graph_context.get("selected_nodes"), list) else []
    if not selected_nodes:
        return []
    normalized_query = normalize_and_rewrite_query(payload.query)
    cards: list[tuple[KeywordCardItem, dict[str, Any]]] = []
    for node in selected_nodes:
        if not isinstance(node, dict):
            continue
        card = build_keyword_card_from_graph_node(
            node,
            normalized_query=normalized_query,
            graph_context=graph_context,
        )
        cards.append((card, node))
        if len(cards) >= limit:
            break
    return cards


def dedupe_and_score(
    cards: list[tuple[KeywordCardItem, dict[str, Any]]],
    query: str,
    project_key: str,
    *,
    graph_context_attached: bool = False,
    accepted_citation_count: int = 0,
) -> KeywordCardListResponse:
    normalized_query = normalize_and_rewrite_query(query)
    selection_hash = _selection_hash(project_key, query)
    if selection_hash in _SELECTION_CACHE:
        cached = _SELECTION_CACHE[selection_hash]
        cached.cache_hit = True
        return cached

    deduped: list[KeywordCardItem] = []
    seen: set[str] = set()
    score_snapshot: dict[str, Any] = {}
    for item, raw in cards:
        dedupe_key = f"{item.url or ''}|{item.title.lower()}|{item.source_type}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        deduped.append(item)
        _remember_card(item, normalized_query=normalized_query, raw=raw)
        score_snapshot[item.card_id] = {"score": item.score, "source_type": item.source_type}

    response = KeywordCardListResponse(
        cards=deduped,
        selection_hash=selection_hash,
        suggested_queries=[normalized_query] if normalized_query else [],
        search_backends_used=[str(item) for item in get_last_used_backends()],
        source_count={
            "document": sum(1 for item in deduped if item.source_type == "document"),
            "resource": sum(1 for item in deduped if item.source_type == "resource"),
            "graph": sum(1 for item in deduped if item.source_type == "graph"),
        },
        dedupe_count=max(0, len(cards) - len(deduped)),
        score_snapshot=score_snapshot,
        context_boundary={
            "contract_version": "writing.context_boundary.e3.v1",
            "selection_context_attached": bool(normalized_query),
            "evidence_context_count": len(deduped),
            "accepted_citation_context_count": max(0, int(accepted_citation_count or 0)),
            "graph_context_attached": graph_context_attached,
            "graph_context_optional": True,
            "graph_boundary_rule": "consume_graph_context_adapter_only",
        },
        dependency_gate={
            "contract_version": "writing.cross_theme_gate.e8.v1",
            "passed": True,
            "topology": ["writing<->graph", "writing<->llm", "writing<->frontend"],
            "graph": {
                "mode": "optional_consume_only",
                "attached": graph_context_attached,
            },
            "llm": {
                "mode": "consume_only",
                "consumer": "writing.llm_action",
            },
            "frontend": {
                "mode": "placement_boundary_only",
                "surface": "writing.workbench",
            },
        },
        cache_hit=False,
        cache_ttl_ms=_CACHE_TTL_MS,
    )
    _SELECTION_CACHE[selection_hash] = response
    return response


def aggregate_cards(payload: KeywordCardRequest) -> KeywordCardListResponse:
    query = payload.query.strip()
    cards: list[tuple[KeywordCardItem, dict[str, Any]]] = []
    requested_sources = set(payload.sources or [])
    graph_context = _extract_graph_context(payload)
    graph_context_attached = bool(graph_context.get("selected_nodes")) if isinstance(graph_context, dict) else False
    accepted_citation_count = 0
    if payload.context is not None and isinstance(payload.context.accepted_citation_context, dict):
        citation_items = payload.context.accepted_citation_context.get("citations")
        if isinstance(citation_items, list):
            accepted_citation_count = len(citation_items)
    if graph_context_attached and (not requested_sources or "graph" in requested_sources):
        cards.extend(_cards_from_graph_context(payload, payload.limit))
    if not requested_sources or "document" in requested_sources:
        cards.extend(_cards_from_hybrid(query, payload.limit))
    if not requested_sources or bool({"resource", "graph"} & requested_sources):
        cards.extend(_cards_from_sources(query, payload.limit))
    if not requested_sources or "resource" in requested_sources:
        cards.extend(_cards_from_source_library(payload.project_key, query, payload.limit))
    if requested_sources:
        cards = [(item, raw) for item, raw in cards if item.source_type in requested_sources]
    return dedupe_and_score(
        cards[: payload.limit * 3],
        query,
        payload.project_key,
        graph_context_attached=graph_context_attached,
        accepted_citation_count=accepted_citation_count,
    )


def get_card_preview(payload: KeywordCardPreviewRequest) -> KeywordCardPreviewResponse:
    cached = _CARD_CACHE.get(payload.card_id)
    if cached is None:
        raise KeyError(f"card not found: {payload.card_id}")
    item = cached["item"]
    return KeywordCardPreviewResponse(
        card_id=item["card_id"],
        title=item["title"],
        url=item.get("url"),
        publisher=item.get("publisher"),
        snippet=item.get("snippet") or "",
        score=float(item.get("score") or 0.0),
        source_type=item["source_type"],
        quick_actions=item.get("quick_actions") or [],
    )


def get_card_detail(payload: KeywordCardDetailRequest) -> KeywordCardDetailResponse:
    cached = _CARD_CACHE.get(payload.card_id)
    if cached is None:
        raise KeyError(f"card not found: {payload.card_id}")
    item = cached["item"]
    raw = cached["raw"] if isinstance(cached.get("raw"), dict) else {}
    provenance = {
        "cached_at": cached.get("cached_at"),
        "raw_keys": sorted(raw.keys())[: payload.max_provenance_items],
        "project_key": payload.project_key,
    }
    return KeywordCardDetailResponse(
        card_id=item["card_id"],
        title=item["title"],
        url=item.get("url"),
        score=float(item.get("score") or 0.0),
        evidence=item.get("evidence"),
        publisher=item.get("publisher"),
        published_at=item.get("published_at"),
        retrieved_at=item.get("retrieved_at"),
        normalized_query=cached.get("normalized_query"),
        dedupe_trace=[{"card_id": item["card_id"], "strategy": "url+title+source_type"}],
        provenance=provenance if payload.include_provenance else {},
        selection_matches={"query": cached.get("normalized_query"), "request_id": payload.request_id},
        source_type=item["source_type"],
    )
