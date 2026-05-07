from __future__ import annotations

from sqlalchemy import select

from ...models.writing_entities import WritingDocument, WritingDocumentCitation, WritingDocumentDraft


def _active_document_stmt(*, project_key: str, doc_id: int | None = None):
    stmt = select(WritingDocument).where(
        WritingDocument.project_key == project_key,
        WritingDocument.deleted_at.is_(None),
    )
    if doc_id is not None:
        stmt = stmt.where(WritingDocument.id == int(doc_id))
    return stmt


def fetch_active_document(session, *, doc_id: int, project_key: str) -> WritingDocument | None:
    stmt = _active_document_stmt(project_key=project_key, doc_id=doc_id)
    return session.execute(stmt).scalar_one_or_none()


def require_active_document(session, *, doc_id: int, project_key: str) -> WritingDocument:
    row = fetch_active_document(session, doc_id=doc_id, project_key=project_key)
    if row is None:
        raise KeyError(f"writing document not found: {doc_id}")
    return row


def list_active_documents(session, *, project_key: str, limit: int = 50) -> list[WritingDocument]:
    stmt = (
        _active_document_stmt(project_key=project_key)
        .order_by(WritingDocument.updated_at.desc().nullslast(), WritingDocument.id.desc())
        .limit(max(1, min(int(limit), 100)))
    )
    return list(session.execute(stmt).scalars().all())


def fetch_draft_by_autosave_token(
    session,
    *,
    doc_id: int,
    project_key: str,
    autosave_token: str,
) -> WritingDocumentDraft | None:
    stmt = select(WritingDocumentDraft).where(
        WritingDocumentDraft.doc_id == int(doc_id),
        WritingDocumentDraft.project_key == project_key,
        WritingDocumentDraft.autosave_token == autosave_token,
    )
    return session.execute(stmt).scalar_one_or_none()


def list_citations_for_document(session, *, doc_id: int, project_key: str) -> list[WritingDocumentCitation]:
    stmt = (
        select(WritingDocumentCitation)
        .where(
            WritingDocumentCitation.doc_id == int(doc_id),
            WritingDocumentCitation.project_key == project_key,
        )
        .order_by(WritingDocumentCitation.id.asc())
    )
    return list(session.execute(stmt).scalars().all())
