from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select

from ...models.base import SessionLocal, run_with_session_retry
from ...models.writing_entities import WritingDocument, WritingDocumentCitation


def _serialize_citation(row: WritingDocumentCitation) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "doc_id": int(row.doc_id),
        "project_key": row.project_key,
        "source_doc_id": row.source_doc_id,
        "source_uri": row.source_uri,
        "source_title": row.source_title,
        "quote_text": row.quote_text,
        "position_anchor": row.position_anchor,
        "card_id": row.card_id,
        "metadata_json": dict(row.metadata_json or {}) if isinstance(row.metadata_json, dict) else row.metadata_json,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _ensure_document_exists(session, *, doc_id: int, project_key: str) -> None:
    stmt = select(WritingDocument.id).where(
        WritingDocument.id == int(doc_id),
        WritingDocument.project_key == project_key,
        WritingDocument.deleted_at.is_(None),
    )
    row = session.execute(stmt).scalar_one_or_none()
    if row is None:
        raise KeyError(f"writing document not found: {doc_id}")


def list_citations(*, doc_id: int, project_key: str) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        _ensure_document_exists(session, doc_id=doc_id, project_key=project_key)
        stmt = (
            select(WritingDocumentCitation)
            .where(
                WritingDocumentCitation.doc_id == int(doc_id),
                WritingDocumentCitation.project_key == project_key,
            )
            .order_by(WritingDocumentCitation.id.asc())
        )
        rows = session.execute(stmt).scalars().all()
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
