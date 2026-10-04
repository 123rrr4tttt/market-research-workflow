from __future__ import annotations

from typing import Any

from ...models.base import SessionLocal
from ...models.entities import Document, Source
from .doc_type_mapper import normalize_doc_type


def persist_terminal_document(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload or {})
    normalized_doc_type = normalize_doc_type(str(normalized.get("doc_type") or "unknown"))
    uri = str(normalized.get("uri") or "").strip() or None
    text_hash = str(normalized.get("text_hash") or "").strip() or None
    with SessionLocal() as session:
        source = _get_or_create_source(
            session,
            name=str(normalized.get("source_name") or "unknown"),
            kind=str(normalized.get("source_kind") or "external"),
            base_url=str(normalized.get("source_base_url") or ""),
        )
        existing = None
        if uri:
            existing = session.query(Document).filter(Document.uri == uri).first()
        if existing is None and text_hash:
            existing = session.query(Document).filter(Document.text_hash == text_hash).first()
        if existing is not None:
            return {
                "doc_id": int(existing.id),
                "inserted": 0,
                "skipped": 1,
                "reason": "skipped_exists",
                "doc_type": normalized_doc_type,
            }

        document = Document(
            source_id=source.id,
            state=normalized.get("state"),
            doc_type=normalized_doc_type,
            title=normalized.get("title"),
            status=normalized.get("status"),
            publish_date=normalized.get("publish_date"),
            summary=normalized.get("summary"),
            content=normalized.get("content"),
            text_hash=text_hash,
            uri=uri,
            extracted_data=normalized.get("extracted_data"),
        )
        session.add(document)
        session.commit()
        return {
            "doc_id": int(document.id),
            "inserted": 1,
            "skipped": 0,
            "reason": "inserted",
            "doc_type": normalized_doc_type,
        }


def _get_or_create_source(session: Any, *, name: str, kind: str, base_url: str | None) -> Source:
    existing = session.query(Source).filter(Source.name == name, Source.kind == kind).first()
    if existing:
        return existing
    row = Source(name=name, kind=kind, base_url=base_url or "")
    session.add(row)
    session.flush()
    return row


__all__ = ["persist_terminal_document"]
