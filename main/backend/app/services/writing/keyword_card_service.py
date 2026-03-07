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
from ..llm_report_source_enrichment import resolve_report_sources
from ..search.hybrid import get_last_used_backends, hybrid_search
from ..source_library.resolver import list_effective_items

_CARD_CACHE: dict[str, dict[str, Any]] = {}
_SELECTION_CACHE: dict[str, KeywordCardListResponse] = {}
_CACHE_TTL_MS = 10_000
_QUERY_SPLIT_RE = re.compile(r"\s+")


def normalize_and_rewrite_query(text: str) -> str:
    normalized = " ".join(_QUERY_SPLIT_RE.split(str(text or "").strip().lower()))
    return normalized


def _selection_hash(project_key: str, query: str) -> str:
    payload = f"{project_key}:{normalize_and_rewrite_query(query)}"
    return hashlib.sha1(payload.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _remember_card(item: KeywordCardItem, *, normalized_query: str, raw: dict[str, Any]) -> None:
    _CARD_CACHE[item.card_id] = {
        "item": item.model_dump(),
        "normalized_query": normalized_query,
        "raw": raw,
        "cached_at": _now_iso(),
    }


def _make_card_id(source_type: str, title: str, url: str | None, normalized_query: str) -> str:
    payload = f"{source_type}|{title}|{url or ''}|{normalized_query}"
    return hashlib.sha1(payload.encode("utf-8", errors="ignore")).hexdigest()[:24]


def _build_card(
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
    card_id = _make_card_id(source_type, title, url, normalized_query)
    return KeywordCardItem(
        card_id=card_id,
        source_type=source_type,
        title=title[:300] or "Untitled",
        snippet=(snippet or evidence or "")[:2000],
        url=url,
        score=max(0.0, float(score or 0.0)),
        publisher=(publisher or "")[:255] or None,
        published_at=published_at,
        retrieved_at=_now_iso(),
        evidence=(evidence or "")[:2000] or None,
        relevance_tags=[normalized_query] if normalized_query else [],
        credibility=min(1.0, max(0.0, float(score or 0.0))) if score is not None else None,
        quick_actions=["insert_quote", "insert_summary", "open_detail"],
        extra=extra or {},
    )


def _cards_from_hybrid(query: str, limit: int) -> list[tuple[KeywordCardItem, dict[str, Any]]]:
    normalized_query = normalize_and_rewrite_query(query)
    rows = hybrid_search(query, state=None, top_k=limit, mode="hybrid")
    cards: list[tuple[KeywordCardItem, dict[str, Any]]] = []
    for row in rows:
        title = str(row.get("title") or row.get("document_title") or row.get("id") or "Document").strip()
        snippet = str(row.get("snippet") or row.get("summary") or row.get("content") or "").strip()
        score = float(row.get("score") or row.get("_score") or 0.6)
        url = str(row.get("url") or row.get("uri") or "").strip() or None
        publisher = str(row.get("publisher") or row.get("source") or "document").strip() or None
        published_at = str(row.get("published_at") or row.get("publish_date") or "").strip() or None
        card = _build_card(
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
        cards.append((card, row))
    return cards


def _cards_from_sources(query: str, limit: int) -> list[tuple[KeywordCardItem, dict[str, Any]]]:
    normalized_query = normalize_and_rewrite_query(query)
    rows = resolve_report_sources(query, None, target_count=limit)
    cards: list[tuple[KeywordCardItem, dict[str, Any]]] = []
    for row in rows:
        publisher = str(row.get("publisher") or "").strip() or None
        source_type = "graph" if publisher and publisher.startswith("graph:") else "resource"
        score = 0.72 if source_type == "graph" else 0.65
        card = _build_card(
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
        cards.append((card, row))
    return cards


def _cards_from_source_library(project_key: str, query: str, limit: int) -> list[tuple[KeywordCardItem, dict[str, Any]]]:
    normalized_query = normalize_and_rewrite_query(query)
    items = list_effective_items(project_key=project_key)
    cards: list[tuple[KeywordCardItem, dict[str, Any]]] = []
    for item in items:
        blob = " ".join(
            [
                str(item.get("item_key") or ""),
                str(item.get("name") or ""),
                str(item.get("description") or ""),
            ]
        ).lower()
        if normalized_query and normalized_query not in blob:
            continue
        title = str(item.get("name") or item.get("item_key") or "Material").strip()
        card = _build_card(
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
        cards.append((card, item))
        if len(cards) >= limit:
            break
    return cards


def dedupe_and_score(cards: list[tuple[KeywordCardItem, dict[str, Any]]], query: str, project_key: str) -> KeywordCardListResponse:
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
        cache_hit=False,
        cache_ttl_ms=_CACHE_TTL_MS,
    )
    _SELECTION_CACHE[selection_hash] = response
    return response


def aggregate_cards(payload: KeywordCardRequest) -> KeywordCardListResponse:
    query = payload.query.strip()
    cards: list[tuple[KeywordCardItem, dict[str, Any]]] = []
    cards.extend(_cards_from_hybrid(query, payload.limit))
    cards.extend(_cards_from_sources(query, payload.limit))
    cards.extend(_cards_from_source_library(payload.project_key, query, payload.limit))
    return dedupe_and_score(cards[: payload.limit * 3], query, payload.project_key)


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
