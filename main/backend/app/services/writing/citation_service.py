from __future__ import annotations

from typing import Any

from sqlalchemy import delete

from ...models.base import SessionLocal, run_with_session_retry
from ...models.writing_entities import WritingDocumentCitation
from ..document_queries import list_citations_for_document, require_active_document
from ..document_views import serialize_writing_citation


def _serialize_citation(row: WritingDocumentCitation) -> dict[str, Any]:
    return serialize_writing_citation(row)


def _ensure_document_exists(session, *, doc_id: int, project_key: str) -> None:
    require_active_document(session, doc_id=doc_id, project_key=project_key)


def list_citations(*, doc_id: int, project_key: str) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        _ensure_document_exists(session, doc_id=doc_id, project_key=project_key)
        rows = list_citations_for_document(session, doc_id=doc_id, project_key=project_key)
        return [_serialize_citation(row) for row in rows]


def upsert_citations(*, doc_id: int, project_key: str, citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def _op(session) -> list[dict[str, Any]]:
        _ensure_document_exists(session, doc_id=doc_id, project_key=project_key)
        session.execute(
            delete(WritingDocumentCitation).where(
                WritingDocumentCitation.doc_id == int(doc_id),
                WritingDocumentCitation.project_key == project_key,
            )
        )
        rows: list[WritingDocumentCitation] = []
        for item in citations:
            row = WritingDocumentCitation(
                doc_id=int(doc_id),
                project_key=project_key,
                source_doc_id=item.get("source_doc_id"),
                source_uri=str(item.get("source_uri") or "").strip() or None,
                source_title=str(item.get("source_title") or "").strip() or None,
                quote_text=str(item.get("quote_text") or "").strip() or None,
                position_anchor=str(item.get("position_anchor") or "").strip() or None,
                card_id=str(item.get("card_id") or "").strip() or None,
                metadata_json=item.get("metadata_json") if isinstance(item.get("metadata_json"), dict) else {},
            )
            session.add(row)
            rows.append(row)
        session.flush()
        return [_serialize_citation(row) for row in rows]

    return run_with_session_retry(_op, log_context={"operation": "upsert_writing_citations", "doc_id": doc_id, "project_key": project_key})


def rebuild_markdown_with_citations(*, body_md: str, citations: list[dict[str, Any]]) -> str:
    normalized_body = str(body_md or "")
    if not citations:
        return normalized_body

    lines = [normalized_body.rstrip(), "", "## References"]
    for idx, item in enumerate(citations, start=1):
        title = str(item.get("source_title") or item.get("card_id") or f"Reference {idx}").strip()
        uri = str(item.get("source_uri") or "").strip()
        quote = str(item.get("quote_text") or "").strip()
        line = f"[{idx}] {title}"
        if uri:
            line += f" - {uri}"
        if quote:
            line += f" - {quote}"
        lines.append(line)
    return "\n".join(lines).strip()
