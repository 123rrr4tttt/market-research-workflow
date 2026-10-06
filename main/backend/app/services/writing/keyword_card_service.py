from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TypeAlias

from functorial_kit import Failure

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
    DocumentQueryJsonObject,
    DocumentQueryRow,
    coerce_document_query_result_row,
    query_hybrid_document_rows,
    query_report_source_rows,
    query_source_library_material_rows,
)
from ..document_views import (
    build_keyword_card_from_graph_node,
    build_keyword_card_from_hybrid_row,
    build_keyword_card_from_material_item,
    build_keyword_card_from_source_row,
    build_keyword_card_from_typed_knowledge_handoff,
)
from ..search.hybrid import get_last_used_backends
from ..typed_knowledge.contracts import parse_writing_knowledge_context_envelope
from .document_service import raise_writing_legacy, writing_failure


@dataclass(frozen=True, slots=True)
class CardCacheEntry:
    item: KeywordCardItem
    normalized_query: str
    raw: DocumentQueryRow
    cached_at: str


CardWithRaw: TypeAlias = tuple[KeywordCardItem, DocumentQueryRow]


_CARD_CACHE: dict[str, CardCacheEntry] = {}
_SELECTION_CACHE: dict[str, KeywordCardListResponse] = {}
_CACHE_TTL_MS = 10_000
_QUERY_SPLIT_RE = re.compile(r"\s+")


def normalize_and_rewrite_query(text: str) -> str:
    normalized = " ".join(_QUERY_SPLIT_RE.split(str(text or "").strip().lower()))
    return normalized


def _selection_hash(project_key: str | None, query: str) -> str:
    payload = f"{project_key}:{normalize_and_rewrite_query(query)}"
    return hashlib.sha1(
        payload.encode("utf-8", errors="ignore"),
        usedforsecurity=False,
    ).hexdigest()[:16]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _remember_card(item: KeywordCardItem, *, normalized_query: str, raw: DocumentQueryRow) -> None:
    _CARD_CACHE[item.card_id] = CardCacheEntry(
        item=item,
        normalized_query=normalized_query,
        raw=raw,
        cached_at=_now_iso(),
    )


def _cards_from_hybrid(query: str, limit: int) -> list[CardWithRaw]:
    normalized_query = normalize_and_rewrite_query(query)
    rows = query_hybrid_document_rows(query, limit=limit)
    cards: list[CardWithRaw] = []
    for row in rows:
        card = build_keyword_card_from_hybrid_row(row, normalized_query=normalized_query)
        cards.append((card, row))
    return cards


def _cards_from_sources(query: str, limit: int) -> list[CardWithRaw]:
    normalized_query = normalize_and_rewrite_query(query)
    rows = query_report_source_rows(query, limit=limit)
    cards: list[CardWithRaw] = []
    for row in rows:
        card = build_keyword_card_from_source_row(row, normalized_query=normalized_query)
        cards.append((card, row))
    return cards


def _cards_from_source_library(project_key: str, query: str, limit: int) -> list[CardWithRaw]:
    normalized_query = normalize_and_rewrite_query(query)
    items = query_source_library_material_rows(project_key, query=query)
    cards: list[CardWithRaw] = []
    for item in items:
        card = build_keyword_card_from_material_item(item, normalized_query=normalized_query)
        cards.append((card, item))
        if len(cards) >= limit:
            break
    return cards


def _extract_graph_context(payload: KeywordCardRequest) -> DocumentQueryJsonObject:
    context = payload.context
    if context is not None and context.graph_context is not None:
        return coerce_document_query_result_row(context.graph_context)
    if payload.graph_context is not None:
        return coerce_document_query_result_row(payload.graph_context)
    return {}


def _extract_typed_knowledge_context(payload: KeywordCardRequest) -> DocumentQueryJsonObject:
    context = payload.context
    nested = context.typed_knowledge_context if context is not None else None
    if nested is None:
        return {}
    return coerce_document_query_result_row(nested.model_dump(mode="json"))


def _cards_from_graph_context(payload: KeywordCardRequest, limit: int) -> list[CardWithRaw]:
    graph_context = _extract_graph_context(payload)
    selected_nodes_value = graph_context.get("selected_nodes")
    selected_nodes = selected_nodes_value if isinstance(selected_nodes_value, list) else []
    if not selected_nodes:
        return []
    normalized_query = normalize_and_rewrite_query(payload.query)
    cards: list[CardWithRaw] = []
    for node_value in selected_nodes:
        if not isinstance(node_value, dict):
            continue
        node = coerce_document_query_result_row(node_value)
        card = build_keyword_card_from_graph_node(
            node,
            normalized_query=normalized_query,
            graph_context=graph_context,
        )
        cards.append((card, node))
        if len(cards) >= limit:
            break
    return cards


def _cards_from_typed_knowledge_context(
    payload: KeywordCardRequest,
    limit: int,
) -> list[CardWithRaw]:
    typed_context = _extract_typed_knowledge_context(payload)
    if not typed_context:
        return []
    normalized_query = normalize_and_rewrite_query(payload.query)
    cards: list[CardWithRaw] = []
    for handoff in parse_writing_knowledge_context_envelope(typed_context):
        card = build_keyword_card_from_typed_knowledge_handoff(handoff, normalized_query=normalized_query)
        cards.append((card, {"typed_knowledge_context": typed_context}))
        if len(cards) >= limit:
            break
    return cards


def dedupe_and_score(
    cards: list[CardWithRaw],
    query: str,
    project_key: str | None,
    *,
    graph_context_attached: bool = False,
    accepted_citation_count: int = 0,
    typed_knowledge_context_count: int = 0,
    source_filter: tuple[str, ...] = (),
) -> KeywordCardListResponse:
    normalized_query = normalize_and_rewrite_query(query)
    selection_hash = _selection_hash(project_key, query)
    cache_key = f"{selection_hash}:{int(graph_context_attached)}:{int(accepted_citation_count)}:{typed_knowledge_context_count}:{','.join(source_filter)}"
    if cache_key in _SELECTION_CACHE:
        cached = _SELECTION_CACHE[cache_key]
        cached.cache_hit = True
        return cached

    deduped: list[KeywordCardItem] = []
    seen: set[str] = set()
    score_snapshot: DocumentQueryJsonObject = {}
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
            "material": sum(1 for item in deduped if item.source_type == "material"),
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
            "typed_knowledge_context_attached": typed_knowledge_context_count > 0,
            "typed_knowledge_context_count": max(0, int(typed_knowledge_context_count or 0)),
            "typed_knowledge_boundary_rule": "consume_typed_knowledge_handoff_as_resource_card_only",
        },
        dependency_gate={
            "contract_version": "writing.cross_theme_gate.e8.v1",
            "passed": True,
            "topology": ["writing<->graph", "writing<->typed_knowledge", "writing<->llm", "writing<->frontend"],
            "graph": {
                "mode": "optional_consume_only",
                "attached": graph_context_attached,
            },
            "typed_knowledge": {
                "mode": "optional_consume_only",
                "attached": typed_knowledge_context_count > 0,
                "consumer": "writing.keyword_card",
                "card_source_type": "resource",
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
    _SELECTION_CACHE[cache_key] = response
    return response


def aggregate_cards(payload: KeywordCardRequest) -> KeywordCardListResponse:
    query = payload.query.strip()
    cards: list[CardWithRaw] = []
    requested_sources = set(payload.sources or [])
    graph_context = _extract_graph_context(payload)
    graph_context_attached = bool(graph_context.get("selected_nodes"))
    accepted_citation_count = 0
    if payload.context is not None:
        accepted_citations = coerce_document_query_result_row(payload.context.accepted_citation_context)
        citation_items = accepted_citations.get("citations")
        if isinstance(citation_items, list):
            accepted_citation_count = len(citation_items)
    if graph_context_attached and (not requested_sources or "graph" in requested_sources):
        cards.extend(_cards_from_graph_context(payload, payload.limit))
    typed_knowledge_cards: list[CardWithRaw] = []
    if not requested_sources or "resource" in requested_sources:
        typed_knowledge_cards = _cards_from_typed_knowledge_context(payload, payload.limit)
        cards.extend(typed_knowledge_cards)
    if not requested_sources or "material" in requested_sources:
        cards.extend(_cards_from_hybrid(query, payload.limit))
    if not requested_sources or bool({"resource", "graph"} & requested_sources):
        cards.extend(_cards_from_sources(query, payload.limit))
    if (not requested_sources or "resource" in requested_sources) and payload.project_key is not None:
        cards.extend(_cards_from_source_library(payload.project_key, query, payload.limit))
    if requested_sources:
        cards = [(item, raw) for item, raw in cards if item.source_type in requested_sources]
    return dedupe_and_score(
        cards[: payload.limit * 3],
        query,
        payload.project_key,
        graph_context_attached=graph_context_attached,
        accepted_citation_count=accepted_citation_count,
        typed_knowledge_context_count=len(typed_knowledge_cards),
        source_filter=tuple(sorted(requested_sources)),
    )


def try_get_card_preview(payload: KeywordCardPreviewRequest) -> KeywordCardPreviewResponse | Failure:
    cached = _CARD_CACHE.get(payload.card_id)
    if cached is None:
        return writing_failure(
            "card_not_found",
            f"card not found: {payload.card_id}",
            owner="writing.keyword_card_service.get_card_preview",
            public_exception=KeyError,
        )
    item = cached.item
    return KeywordCardPreviewResponse(
        card_id=item.card_id,
        title=item.title,
        url=item.url,
        publisher=item.publisher,
        snippet=item.snippet,
        score=item.score,
        source_type=item.source_type,
        quick_actions=item.quick_actions,
    )


def get_card_preview(payload: KeywordCardPreviewRequest) -> KeywordCardPreviewResponse:
    outcome = try_get_card_preview(payload)
    if isinstance(outcome, Failure):
        raise_writing_legacy(outcome)
    return outcome


def try_get_card_detail(payload: KeywordCardDetailRequest) -> KeywordCardDetailResponse | Failure:
    cached = _CARD_CACHE.get(payload.card_id)
    if cached is None:
        return writing_failure(
            "card_not_found",
            f"card not found: {payload.card_id}",
            owner="writing.keyword_card_service.get_card_detail",
            public_exception=KeyError,
        )
    item = cached.item
    provenance = coerce_document_query_result_row(
        {
            "cached_at": cached.cached_at,
            "raw_keys": sorted(cached.raw.keys())[: payload.max_provenance_items],
            "project_key": payload.project_key,
        }
    )
    return KeywordCardDetailResponse(
        card_id=item.card_id,
        title=item.title,
        url=item.url,
        score=item.score,
        evidence=item.evidence,
        publisher=item.publisher,
        published_at=item.published_at,
        retrieved_at=item.retrieved_at,
        normalized_query=cached.normalized_query,
        dedupe_trace=[{"card_id": item.card_id, "strategy": "url+title+source_type"}],
        provenance=provenance if payload.include_provenance else {},
        selection_matches={"query": cached.normalized_query, "request_id": payload.request_id},
        source_type=item.source_type,
    )


def get_card_detail(payload: KeywordCardDetailRequest) -> KeywordCardDetailResponse:
    outcome = try_get_card_detail(payload)
    if isinstance(outcome, Failure):
        raise_writing_legacy(outcome)
    return outcome
