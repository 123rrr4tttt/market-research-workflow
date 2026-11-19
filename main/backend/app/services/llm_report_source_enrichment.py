from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import logging
import re
from typing import Any, Literal, TypeGuard

from sqlalchemy import select

from ..models.base import SessionLocal
from ..models.entities import Material, GraphNodeRecord
from .search.hybrid import observe_hybrid_search
from .search.web import ObservationRecord, search_sources


logger = logging.getLogger(__name__)

_DEFAULT_TARGET_SOURCES = 6

ReportSourceResolutionKind = Literal[
    "caller_supplied_only", "auto_enriched", "auto_empty", "auto_failed", "auto_partial"
]


@dataclass(frozen=True)
class ReportSourceFailure:
    owner: str
    code: str
    message: str
    provider: str | None = None
    exception_type: str | None = None

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ReportSourceResolution:
    sources: list[dict[str, Any]]
    failures: tuple[ReportSourceFailure, ...] = ()
    auto_attempted: bool = True

    @property
    def kind(self) -> ReportSourceResolutionKind:
        if not self.auto_attempted:
            return "caller_supplied_only"
        if self.failures:
            return "auto_partial" if self.sources else "auto_failed"
        return "auto_enriched" if self.sources else "auto_empty"


def _dependency_failure(owner: str, message: str, exc: Exception) -> ReportSourceFailure:
    logger.warning("Report source dependency failed (%s)", owner, exc_info=exc)
    return ReportSourceFailure(owner, "backend_unavailable", message, exception_type=type(exc).__name__)


def _is_string_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict)


def _string_object_dict(value: object) -> dict[str, object]:
    return value if _is_string_object_dict(value) else {}


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _int_or_none(value: object) -> int | None:
    if not isinstance(value, (str, int, float, bytes, bytearray)):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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


def _extract_graph_evidence_from_document(material: Material) -> str:
    extracted = _string_object_dict(material.extracted_data)
    snippets: list[str] = []

    er = _string_object_dict(extracted.get("entities_relations"))
    relations_value = er.get("relations")
    relations = relations_value if _is_object_list(relations_value) else []
    for rel in relations[:3]:
        if not _is_string_object_dict(rel):
            continue
        evidence = str(rel.get("evidence") or "").strip()
        if evidence:
            snippets.append(evidence)

    if not snippets:
        top_relations_value = extracted.get("relations")
        top_relations = top_relations_value if _is_object_list(top_relations_value) else []
        for rel in top_relations[:3]:
            if not _is_string_object_dict(rel):
                continue
            evidence = str(rel.get("evidence") or "").strip()
            if evidence:
                snippets.append(evidence)

    source_excerpt = str(extracted.get("source_excerpt") or "").strip()
    if source_excerpt and not snippets:
        snippets.append(source_excerpt[:240])

    if snippets:
        return "；".join(snippets[:2])
    return str(material.summary or "").strip()[:240]


def _source_from_document(material: Material, source_id: str) -> dict[str, Any] | None:
    uri = str(material.uri or "").strip()
    if not uri.startswith("http://") and not uri.startswith("https://"):
        return None

    extracted = _string_object_dict(material.extracted_data)
    publisher = (
        str(extracted.get("source_domain") or extracted.get("source") or material.material_type or "internal_rag").strip()
        or "internal_rag"
    )
    publish_date = material.publish_date.isoformat() if material.publish_date else None
    evidence = _extract_graph_evidence_from_document(material)

    return {
        "id": source_id,
        "title": str(material.title or f"Material {material.id}").strip() or f"Material {material.id}",
        "url": uri,
        "publisher": publisher,
        "published_at": publish_date,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "evidence": evidence,
    }


def _collect_from_rag_documents(
    topic: str, max_results: int, failures: list[ReportSourceFailure]
) -> list[dict[str, Any]]:
    try:
        observation = observe_hybrid_search(topic, state=None, top_k=max_results, mode="hybrid")
    except Exception as exc:  # noqa: BLE001
        failures.append(_dependency_failure("report_sources.rag_search", "Material search did not complete", exc))
        return []

    for failure in observation.failures:
        context = failure.context or {}
        provider = context.get("provider")
        exception_type = context.get("exception_type")
        failures.append(ReportSourceFailure(
            "report_sources.rag_search",
            failure.code,
            "Material search backend did not complete",
            provider if isinstance(provider, str) else None,
            exception_type if isinstance(exception_type, str) else None,
        ))

    doc_ids: list[int] = []
    for hit in observation.hits:
        material_id = _int_or_none(hit.get("material_id"))
        if material_id is None:
            continue
        if material_id not in doc_ids:
            doc_ids.append(material_id)
    if not doc_ids:
        return []

    try:
        with SessionLocal() as session:
            rows = session.execute(select(Material).where(Material.id.in_(doc_ids))).scalars().all()
    except Exception as exc:  # noqa: BLE001
        failures.append(_dependency_failure("report_sources.rag_load", "Materials could not be loaded", exc))
        return []

    docs_by_id = {int(row.id): row for row in rows}
    collected: list[dict[str, Any]] = []
    for rank, material_id in enumerate(doc_ids, start=1):
        material = docs_by_id.get(material_id)
        if material is None:
            continue
        source = _source_from_document(material, source_id=f"RAG{rank}")
        if source is not None:
            collected.append(source)
        if len(collected) >= max_results:
            break
    return collected


def _collect_from_graph_nodes(
    topic: str, max_results: int, start_index: int, failures: list[ReportSourceFailure]
) -> list[dict[str, Any]]:
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
        failures.append(_dependency_failure("report_sources.graph", "Graph lookup did not complete", exc))
        return []

    ranked: list[tuple[int, GraphNodeRecord]] = []
    for row in rows:
        props = _string_object_dict(row.properties)
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
        props = _string_object_dict(row.properties)
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


def _collect_from_web(
    topic: str, max_results: int, start_index: int, failures: list[ReportSourceFailure]
) -> list[dict[str, Any]]:
    if max_results <= 0:
        return []
    observations: list[ObservationRecord] = []
    try:
        rows = search_sources(
            topic=topic, language="en", max_results=max_results, provider="auto", exclude_existing=False,
            observation_sink=observations,
        )
    except Exception as exc:  # noqa: BLE001
        failures.append(_dependency_failure("report_sources.web", "Web search did not complete", exc))
        rows = []

    # Configured provider attempts can fail without search_sources raising. Repeated
    # failures across generated keywords do not need repeated public diagnostics.
    for observed in observations:
        if observed["status"] != "failed":
            continue
        kind = observed.get("failure_kind")
        provider = observed.get("provider")
        exception_type = observed.get("error_type")
        failure = ReportSourceFailure(
            "report_sources.web",
            kind if isinstance(kind, str) else "backend_unavailable",
            "Web search provider did not complete",
            provider if isinstance(provider, str) else None,
            exception_type if isinstance(exception_type, str) else None,
        )
        if failure not in failures:
            failures.append(failure)

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


def resolve_report_sources(
    topic: str,
    requested_sources: list[dict[str, Any]] | None,
    *,
    target_count: int = _DEFAULT_TARGET_SOURCES,
    auto_source_enabled: bool = True,
) -> ReportSourceResolution:
    manual_sources = list(requested_sources or [])
    if manual_sources or not auto_source_enabled:
        return ReportSourceResolution(manual_sources, auto_attempted=False)
    target_count = min(max(1, int(target_count or _DEFAULT_TARGET_SOURCES)), 20)

    failures: list[ReportSourceFailure] = []
    merged = _collect_from_rag_documents(topic, max_results=target_count, failures=failures)
    if len(merged) < target_count:
        merged.extend(_collect_from_graph_nodes(
            topic, max_results=target_count - len(merged), start_index=len(merged) + 1, failures=failures,
        ))
    if len(merged) < target_count:
        merged.extend(_collect_from_web(
            topic, max_results=target_count - len(merged), start_index=len(merged) + 1, failures=failures,
        ))
    return ReportSourceResolution(_dedupe_sources(merged)[:target_count], tuple(failures))
