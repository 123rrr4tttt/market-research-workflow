from __future__ import annotations

from datetime import datetime, timezone
import logging
import re
from typing import Any

from sqlalchemy import select

from ..models.base import SessionLocal
from ..models.entities import Document, GraphNodeRecord
from .search.hybrid import hybrid_search
from .search.web import search_sources


logger = logging.getLogger(__name__)

_DEFAULT_TARGET_SOURCES = 6


def _topic_terms(topic: str) -> list[str]:
    text = str(topic or "").strip().lower()
    if not text:
        return []
    terms = [t for t in re.split(r"[\s,，。；;:：/|()（）\-]+", text) if t]
    if not terms:
        return [text]
    if len(text) <= 64:
        terms.append(text)
    deduped: list[str] = []
    seen: set[str] = set()
    for term in terms:
        if term in seen:
            continue
        seen.add(term)
        deduped.append(term)
    return deduped


def _score_text_match(text: str, topic: str) -> int:
    lowered = str(text or "").lower()
    if not lowered:
        return 0
    return sum(1 for term in _topic_terms(topic) if term and term in lowered)


def _extract_graph_evidence_from_document(document: Document) -> str:
    extracted = document.extracted_data if isinstance(document.extracted_data, dict) else {}
    snippets: list[str] = []

    er = extracted.get("entities_relations") if isinstance(extracted.get("entities_relations"), dict) else {}
    relations = er.get("relations") if isinstance(er.get("relations"), list) else []
    for rel in relations[:3]:
        if not isinstance(rel, dict):
            continue
        evidence = str(rel.get("evidence") or "").strip()
        if evidence:
            snippets.append(evidence)

    if not snippets:
        top_relations = extracted.get("relations") if isinstance(extracted.get("relations"), list) else []
        for rel in top_relations[:3]:
            if not isinstance(rel, dict):
                continue
            evidence = str(rel.get("evidence") or "").strip()
            if evidence:
                snippets.append(evidence)

    source_excerpt = str(extracted.get("source_excerpt") or "").strip()
    if source_excerpt and not snippets:
        snippets.append(source_excerpt[:240])

    if snippets:
        return "；".join(snippets[:2])
    return str(document.summary or "").strip()[:240]


def _source_from_document(document: Document, source_id: str) -> dict[str, Any] | None:
    uri = str(document.uri or "").strip()
    if not uri.startswith("http://") and not uri.startswith("https://"):
        return None

    extracted = document.extracted_data if isinstance(document.extracted_data, dict) else {}
    publisher = (
        str(extracted.get("source_domain") or extracted.get("source") or document.doc_type or "internal_rag").strip()
        or "internal_rag"
    )
    publish_date = document.publish_date.isoformat() if document.publish_date else None
    evidence = _extract_graph_evidence_from_document(document)

    return {
        "id": source_id,
        "title": str(document.title or f"Document {document.id}").strip() or f"Document {document.id}",
        "url": uri,
        "publisher": publisher,
        "published_at": publish_date,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "evidence": evidence,
    }


def _collect_from_rag_documents(topic: str, max_results: int) -> list[dict[str, Any]]:
    try:
        rag_hits = hybrid_search(topic, state=None, top_k=max_results, mode="hybrid")
    except Exception as exc:  # noqa: BLE001
        logger.info("llm_report_source_enrichment: rag search unavailable: %s", exc)
        return []

    doc_ids: list[int] = []
    for hit in rag_hits:
        try:
            doc_id = int(hit.get("document_id"))
        except Exception:  # noqa: BLE001
            continue
        if doc_id not in doc_ids:
            doc_ids.append(doc_id)
    if not doc_ids:
        return []

    try:
        with SessionLocal() as session:
            rows = session.execute(select(Document).where(Document.id.in_(doc_ids))).scalars().all()
    except Exception as exc:  # noqa: BLE001
        logger.info("llm_report_source_enrichment: failed loading rag docs: %s", exc)
        return []

    docs_by_id = {int(row.id): row for row in rows}
    collected: list[dict[str, Any]] = []
    for rank, doc_id in enumerate(doc_ids, start=1):
        document = docs_by_id.get(doc_id)
        if document is None:
            continue
        source = _source_from_document(document, source_id=f"RAG{rank}")
        if source is not None:
            collected.append(source)
        if len(collected) >= max_results:
            break
    return collected


def _collect_from_graph_nodes(topic: str, max_results: int, start_index: int) -> list[dict[str, Any]]:
    if max_results <= 0:
        return []
    try:
        with SessionLocal() as session:
            rows = session.execute(
                select(GraphNodeRecord)
                .order_by(GraphNodeRecord.updated_at.desc())
                .limit(300)
            ).scalars().all()
    except Exception as exc:  # noqa: BLE001
        logger.info("llm_report_source_enrichment: graph nodes unavailable: %s", exc)
        return []

    ranked: list[tuple[int, GraphNodeRecord]] = []
    for row in rows:
        props = row.properties if isinstance(row.properties, dict) else {}
        blob = " ".join(
            [
                str(row.display_name or ""),
                str(props.get("title") or ""),
                str(props.get("name") or ""),
                str(props.get("label") or ""),
                str(props.get("summary") or ""),
                str(props.get("text") or ""),
            ]
        )
        score = _score_text_match(blob, topic)
        if score > 0:
            ranked.append((score, row))
    ranked.sort(key=lambda item: item[0], reverse=True)

    sources: list[dict[str, Any]] = []
    for idx, (_, row) in enumerate(ranked[: max_results * 3], start=start_index):
        props = row.properties if isinstance(row.properties, dict) else {}
        url = str(props.get("source_uri") or props.get("uri") or "").strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            continue
        evidence = str(props.get("summary") or props.get("text") or "").strip()[:240]
        title = (
            str(row.display_name or props.get("title") or props.get("name") or props.get("label") or "").strip()
            or f"{row.node_type} {row.canonical_id}"
        )
        sources.append(
            {
                "id": f"GRAPH{idx}",
                "title": title,
                "url": url,
                "publisher": f"graph:{row.node_type}",
                "published_at": None,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "evidence": evidence or f"图谱节点({row.node_type})与主题“{topic}”相关",
            }
        )
        if len(sources) >= max_results:
            break
    return sources


def _collect_from_web(topic: str, max_results: int, start_index: int) -> list[dict[str, Any]]:
    if max_results <= 0:
        return []
    try:
        rows = search_sources(topic=topic, language="en", max_results=max_results, provider="auto", exclude_existing=False)
    except Exception as exc:  # noqa: BLE001
        logger.info("llm_report_source_enrichment: web fallback unavailable: %s", exc)
        return []

    sources: list[dict[str, Any]] = []
    for idx, row in enumerate(rows, start=start_index):
        url = str(row.get("canonical_link") or row.get("link") or "").strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            continue
        title = str(row.get("title") or "").strip() or f"Web Source {idx}"
        snippet = str(row.get("snippet") or "").strip()
        sources.append(
            {
                "id": f"WEB{idx}",
                "title": title,
                "url": url,
                "publisher": str(row.get("source") or "web").strip() or "web",
                "published_at": None,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "evidence": snippet[:240] if snippet else f"来自网络检索结果：{title}",
            }
        )
        if len(sources) >= max_results:
            break
    return sources


def _dedupe_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in sources:
        url = str(source.get("url") or "").strip().lower()
        title = str(source.get("title") or "").strip().lower()
        if not url:
            continue
        key = f"{url}|{title}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(source)
    return deduped


def resolve_report_sources(topic: str, requested_sources: list[dict[str, Any]] | None, *, target_count: int = _DEFAULT_TARGET_SOURCES) -> list[dict[str, Any]]:
    manual_sources = list(requested_sources or [])
    if manual_sources:
        return manual_sources
    target_count = min(max(1, int(target_count or _DEFAULT_TARGET_SOURCES)), 20)

    merged: list[dict[str, Any]] = []
    merged.extend(_collect_from_rag_documents(topic, max_results=target_count))
    if len(merged) < target_count:
        merged.extend(_collect_from_graph_nodes(topic, max_results=target_count - len(merged), start_index=len(merged) + 1))
    if len(merged) < target_count:
        merged.extend(_collect_from_web(topic, max_results=target_count - len(merged), start_index=len(merged) + 1))
    return _dedupe_sources(merged)[:target_count]
