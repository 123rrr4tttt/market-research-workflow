from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from ...models.base import SessionLocal, run_with_session_retry
from ...models.writing_entities import WritingDocument, WritingDocumentDraft


class WritingVersionConflictError(ValueError):
    def __init__(self, *, expected_version: int | None, current_version: int, server_snapshot: dict[str, Any]) -> None:
        super().__init__("writing document version conflict")
        self.expected_version = expected_version
        self.current_version = current_version
        self.server_snapshot = server_snapshot


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compute_etag(*, body_md: str, version: int) -> str:
    payload = f"{version}:{body_md}".encode("utf-8", errors="ignore")
    return hashlib.sha1(payload).hexdigest()


def _serialize_document(row: WritingDocument) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "project_key": row.project_key,
        "title": row.title or "",
        "body_md": row.body_md or "",
        "status": row.status or "draft",
        "version": int(row.head_version or 1),
        "etag": row.etag or _compute_etag(body_md=row.body_md or "", version=int(row.head_version or 1)),
        "updated_by_user_id": row.updated_by_user_id,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "metadata_json": dict(row.metadata_json or {}),
    }


def _serialize_draft(row: WritingDocumentDraft) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "doc_id": int(row.doc_id),
        "project_key": row.project_key,
        "draft_body_md": row.draft_body_md or "",
        "selection_snapshot": dict(row.selection_snapshot or {}) if isinstance(row.selection_snapshot, dict) else row.selection_snapshot,
        "base_version": int(row.base_version or 1),
        "autosave_token": row.autosave_token,
        "request_id": row.request_id,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _build_conflict_details(row: WritingDocument, *, expected_version: int | None) -> dict[str, Any]:
    return {
        "conflict_code": "VERSION_CONFLICT",
        "expected_version": expected_version,
        "current_version": int(row.head_version or 1),
        "server_snapshot": _serialize_document(row),
        "updated_by_user_id": row.updated_by_user_id,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def create_document(
    *,
    project_key: str,
    title: str,
    body_md: str = "",
    updated_by_user_id: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    def _op(session) -> dict[str, Any]:
        row = WritingDocument(
            project_key=project_key,
            title=str(title or "").strip() or "Untitled",
            body_md=body_md or "",
            status="draft",
            head_version=1,
            updated_by_user_id=updated_by_user_id,
            metadata_json=metadata_json or {},
        )
        row.etag = _compute_etag(body_md=row.body_md or "", version=1)
        session.add(row)
        session.flush()
        session.refresh(row)
        return _serialize_document(row)

    return run_with_session_retry(_op, log_context={"operation": "create_writing_document", "project_key": project_key})


def list_documents(*, project_key: str, limit: int = 50) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        stmt = (
            select(WritingDocument)
            .where(WritingDocument.project_key == project_key, WritingDocument.deleted_at.is_(None))
            .order_by(WritingDocument.updated_at.desc().nullslast(), WritingDocument.id.desc())
            .limit(max(1, min(int(limit), 100)))
        )
        rows = session.execute(stmt).scalars().all()
        return [_serialize_document(row) for row in rows]


def get_document(*, doc_id: int, project_key: str) -> dict[str, Any]:
    with SessionLocal() as session:
        stmt = select(WritingDocument).where(
            WritingDocument.id == int(doc_id),
            WritingDocument.project_key == project_key,
            WritingDocument.deleted_at.is_(None),
        )
        row = session.execute(stmt).scalar_one_or_none()
        if row is None:
            raise KeyError(f"writing document not found: {doc_id}")
        return _serialize_document(row)


def save_document_with_conflict(
    *,
    doc_id: int,
    project_key: str,
    body_md: str,
    title: str | None = None,
    base_version: int | None = None,
    if_match: str | None = None,
    updated_by_user_id: str | None = None,
) -> dict[str, Any]:
    def _op(session) -> dict[str, Any]:
        stmt = select(WritingDocument).where(
            WritingDocument.id == int(doc_id),
            WritingDocument.project_key == project_key,
            WritingDocument.deleted_at.is_(None),
        )
        row = session.execute(stmt).scalar_one_or_none()
        if row is None:
            raise KeyError(f"writing document not found: {doc_id}")

        current_version = int(row.head_version or 1)
        current_etag = row.etag or _compute_etag(body_md=row.body_md or "", version=current_version)
        if base_version is not None and int(base_version) != current_version:
            raise WritingVersionConflictError(
                expected_version=int(base_version),
                current_version=current_version,
                server_snapshot=_build_conflict_details(row, expected_version=int(base_version)),
            )
        if if_match and if_match != current_etag:
            raise WritingVersionConflictError(
                expected_version=base_version,
                current_version=current_version,
                server_snapshot=_build_conflict_details(row, expected_version=base_version),
            )

        row.body_md = body_md or ""
        if title is not None:
            row.title = str(title or "").strip() or row.title or "Untitled"
        row.head_version = current_version + 1
        row.updated_by_user_id = updated_by_user_id
        row.etag = _compute_etag(body_md=row.body_md or "", version=int(row.head_version or current_version + 1))
        session.add(row)
        session.flush()
        session.refresh(row)
        return _serialize_document(row)

    return run_with_session_retry(_op, log_context={"operation": "save_writing_document", "doc_id": doc_id, "project_key": project_key})


def save_draft_autosave(
    *,
    doc_id: int,
    project_key: str,
    draft_body_md: str,
    base_version: int | None = None,
    autosave_token: str,
    request_id: str | None = None,
    selection_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    def _op(session) -> dict[str, Any]:
        doc_stmt = select(WritingDocument).where(
            WritingDocument.id == int(doc_id),
            WritingDocument.project_key == project_key,
            WritingDocument.deleted_at.is_(None),
        )
        document = session.execute(doc_stmt).scalar_one_or_none()
        if document is None:
            raise KeyError(f"writing document not found: {doc_id}")

        current_version = int(document.head_version or 1)
        expected_version = int(base_version) if base_version is not None else current_version
        if expected_version != current_version:
            raise WritingVersionConflictError(
                expected_version=expected_version,
                current_version=current_version,
                server_snapshot=_build_conflict_details(document, expected_version=expected_version),
            )

        draft_stmt = select(WritingDocumentDraft).where(
            WritingDocumentDraft.doc_id == int(doc_id),
            WritingDocumentDraft.project_key == project_key,
            WritingDocumentDraft.autosave_token == autosave_token,
        )
        row = session.execute(draft_stmt).scalar_one_or_none()
        if row is None:
            row = WritingDocumentDraft(
                doc_id=int(doc_id),
                project_key=project_key,
                autosave_token=autosave_token,
            )
        row.draft_body_md = draft_body_md or ""
        row.base_version = expected_version
        row.request_id = request_id
        row.selection_snapshot = selection_snapshot or {}
        session.add(row)
        session.flush()
        session.refresh(row)
        return _serialize_draft(row)

    return run_with_session_retry(_op, log_context={"operation": "autosave_writing_document", "doc_id": doc_id, "project_key": project_key})


def export_document_markdown(*, doc_id: int, project_key: str) -> dict[str, Any]:
    document = get_document(doc_id=doc_id, project_key=project_key)
    return {
        "doc_id": int(doc_id),
        "project_key": project_key,
        "filename": f"writing-document-{doc_id}.md",
        "markdown": document["body_md"],
        "exported_at": _utcnow_iso(),
    }
