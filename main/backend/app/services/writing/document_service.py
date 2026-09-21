from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, NoReturn

from functorial_kit import Failure
from mrw_functorial_kit.core.w04_service_semantics import writing_failures

from ...models.base import SessionLocal, run_with_session_retry
from ...models.writing_entities import WritingDocument, WritingDocumentDraft
from ..document_queries import (
    fetch_active_document,
    fetch_draft_by_autosave_token,
    list_active_documents,
)
from ..document_views import (
    build_writing_conflict_details,
    serialize_writing_document,
    serialize_writing_document_draft,
)


class WritingVersionConflictError(ValueError):
    def __init__(self, *, expected_version: int | None, current_version: int, server_snapshot: dict[str, Any]) -> None:
        super().__init__("writing document version conflict")
        self.expected_version = expected_version
        self.current_version = current_version
        self.server_snapshot = server_snapshot


_WRITING_FAILURE_CONTEXT_KEYS = frozenset({"owner", "public_exception", "public_message"})


def _writing_failure(
    code: str,
    message: str,
    *,
    owner: str,
    public_exception: type[Exception] | str,
    public_message: str | None = None,
    **details: Any,
) -> Failure:
    return writing_failures.fail(
        code,
        message,
        {
            "owner": owner,
            "public_exception": (
                public_exception.__name__ if isinstance(public_exception, type) else str(public_exception)
            ),
            "public_message": str(public_message if public_message is not None else message),
            **details,
        },
    )


def _raise_writing_legacy(failure: Failure, *, cause: BaseException | None = None) -> NoReturn:
    """Lift a closed writing failure exactly once at the public service boundary."""
    context = failure.context or {}
    if not writing_failures.matches(failure) or not _WRITING_FAILURE_CONTEXT_KEYS <= set(context):
        # kit:boundary owner=writing.document_service.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w04_writing_failure_core
        raise TypeError("writing failure lift context is incomplete or inconsistent")

    public_exception = str(context["public_exception"])
    message = str(context["public_message"])
    if public_exception == "KeyError":
        if cause is None:
            # kit:boundary owner=writing.document_service.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=writing.failure witness=test:test_w04_writing_failure_core
            raise KeyError(message)
        # kit:boundary owner=writing.document_service.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=writing.failure witness=test:test_w04_writing_failure_core
        raise KeyError(message) from cause
    if public_exception == "WritingVersionConflictError" and failure.code == "version_conflict":
        conflict = WritingVersionConflictError(
            expected_version=context.get("expected_version"),
            current_version=int(context.get("current_version", 0)),
            server_snapshot=dict(context.get("server_snapshot") or {}),
        )
        if cause is None:
            # kit:boundary owner=writing.document_service.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=writing.failure witness=test:test_w04_writing_failure_core
            raise conflict
        # kit:boundary owner=writing.document_service.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=writing.failure witness=test:test_w04_writing_failure_core
        raise conflict from cause
    if failure.code == "action_execution_failed" and isinstance(cause, BaseException):
        # kit:boundary owner=writing.document_service.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=writing.failure witness=test:test_w04_writing_failure_core
        raise cause
    # kit:boundary owner=writing.document_service.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w04_writing_failure_core
    raise TypeError(f"unsupported writing failure code: {failure.code}")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compute_etag(*, body_md: str, version: int) -> str:
    payload = f"{version}:{body_md}".encode("utf-8", errors="ignore")
    return hashlib.sha1(payload, usedforsecurity=False).hexdigest()


def _serialize_document(row: WritingDocument) -> dict[str, Any]:
    serialized = serialize_writing_document(row)
    serialized["etag"] = serialized.get("etag") or _compute_etag(
        body_md=row.body_md or "",
        version=int(row.head_version or 1),
    )
    return serialized


def _serialize_draft(row: WritingDocumentDraft) -> dict[str, Any]:
    return serialize_writing_document_draft(row)


def _build_conflict_details(row: WritingDocument, *, expected_version: int | None) -> dict[str, Any]:
    details = build_writing_conflict_details(row, expected_version=expected_version)
    details["server_snapshot"]["etag"] = details["server_snapshot"].get("etag") or _compute_etag(
        body_md=row.body_md or "",
        version=int(row.head_version or 1),
    )
    return details


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
        rows = list_active_documents(session, project_key=project_key, limit=limit)
        return [_serialize_document(row) for row in rows]


def try_get_document(*, doc_id: int, project_key: str) -> dict[str, Any] | Failure:
    with SessionLocal() as session:
        row = fetch_active_document(session, doc_id=doc_id, project_key=project_key)
        if row is None:
            return _writing_failure(
                "document_not_found",
                f"writing document not found: {doc_id}",
                owner="writing.document_service.get_document",
                public_exception=KeyError,
            )
        return _serialize_document(row)


def get_document(*, doc_id: int, project_key: str) -> dict[str, Any]:
    outcome = try_get_document(doc_id=doc_id, project_key=project_key)
    if isinstance(outcome, Failure):
        _raise_writing_legacy(outcome)
    return outcome


def try_delete_document(*, doc_id: int, project_key: str, updated_by_user_id: str | None = None) -> dict[str, Any] | Failure:
    def _op(session) -> dict[str, Any] | Failure:
        row = fetch_active_document(session, doc_id=doc_id, project_key=project_key)
        if row is None:
            return _writing_failure(
                "document_not_found",
                f"writing document not found: {doc_id}",
                owner="writing.document_service.delete_document",
                public_exception=KeyError,
            )

        row.status = "archived"
        row.deleted_at = datetime.now(timezone.utc)
        row.updated_by_user_id = updated_by_user_id
        session.add(row)
        session.flush()
        session.refresh(row)
        return _serialize_document(row)

    return run_with_session_retry(_op, log_context={"operation": "delete_writing_document", "doc_id": doc_id, "project_key": project_key})


def delete_document(*, doc_id: int, project_key: str, updated_by_user_id: str | None = None) -> dict[str, Any]:
    outcome = try_delete_document(doc_id=doc_id, project_key=project_key, updated_by_user_id=updated_by_user_id)
    if isinstance(outcome, Failure):
        _raise_writing_legacy(outcome)
    return outcome


def try_save_document_with_conflict(
    *,
    doc_id: int,
    project_key: str,
    body_md: str,
    title: str | None = None,
    base_version: int | None = None,
    if_match: str | None = None,
    updated_by_user_id: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> dict[str, Any] | Failure:
    def _op(session) -> dict[str, Any] | Failure:
        row = fetch_active_document(session, doc_id=doc_id, project_key=project_key)
        if row is None:
            return _writing_failure(
                "document_not_found",
                f"writing document not found: {doc_id}",
                owner="writing.document_service.save_document",
                public_exception=KeyError,
            )

        current_version = int(row.head_version or 1)
        current_etag = row.etag or _compute_etag(body_md=row.body_md or "", version=current_version)
        if base_version is not None and int(base_version) != current_version:
            return _writing_failure(
                "version_conflict",
                "writing document version conflict",
                owner="writing.document_service.save_document",
                public_exception="WritingVersionConflictError",
                expected_version=int(base_version),
                current_version=current_version,
                server_snapshot=_build_conflict_details(row, expected_version=int(base_version)),
            )
        if if_match and if_match != current_etag:
            return _writing_failure(
                "version_conflict",
                "writing document version conflict",
                owner="writing.document_service.save_document",
                public_exception="WritingVersionConflictError",
                expected_version=base_version,
                current_version=current_version,
                server_snapshot=_build_conflict_details(row, expected_version=base_version),
            )

        row.body_md = body_md or ""
        if title is not None:
            row.title = str(title or "").strip() or row.title or "Untitled"
        if metadata_json is not None:
            row.metadata_json = dict(metadata_json or {})
        row.head_version = current_version + 1
        row.updated_by_user_id = updated_by_user_id
        row.etag = _compute_etag(body_md=row.body_md or "", version=int(row.head_version or current_version + 1))
        session.add(row)
        session.flush()
        session.refresh(row)
        return _serialize_document(row)

    return run_with_session_retry(_op, log_context={"operation": "save_writing_document", "doc_id": doc_id, "project_key": project_key})


def save_document_with_conflict(
    *,
    doc_id: int,
    project_key: str,
    body_md: str,
    title: str | None = None,
    base_version: int | None = None,
    if_match: str | None = None,
    updated_by_user_id: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    outcome = try_save_document_with_conflict(
        doc_id=doc_id,
        project_key=project_key,
        body_md=body_md,
        title=title,
        base_version=base_version,
        if_match=if_match,
        updated_by_user_id=updated_by_user_id,
        metadata_json=metadata_json,
    )
    if isinstance(outcome, Failure):
        _raise_writing_legacy(outcome)
    return outcome


def try_save_draft_autosave(
    *,
    doc_id: int,
    project_key: str,
    draft_body_md: str,
    base_version: int | None = None,
    autosave_token: str,
    request_id: str | None = None,
    selection_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any] | Failure:
    def _op(session) -> dict[str, Any] | Failure:
        document = fetch_active_document(session, doc_id=doc_id, project_key=project_key)
        if document is None:
            return _writing_failure(
                "document_not_found",
                f"writing document not found: {doc_id}",
                owner="writing.document_service.save_draft_autosave",
                public_exception=KeyError,
            )

        current_version = int(document.head_version or 1)
        expected_version = int(base_version) if base_version is not None else current_version
        if expected_version != current_version:
            return _writing_failure(
                "version_conflict",
                "writing document version conflict",
                owner="writing.document_service.save_draft_autosave",
                public_exception="WritingVersionConflictError",
                expected_version=expected_version,
                current_version=current_version,
                server_snapshot=_build_conflict_details(document, expected_version=expected_version),
            )

        row = fetch_draft_by_autosave_token(
            session,
            doc_id=doc_id,
            project_key=project_key,
            autosave_token=autosave_token,
        )
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
    outcome = try_save_draft_autosave(
        doc_id=doc_id,
        project_key=project_key,
        draft_body_md=draft_body_md,
        base_version=base_version,
        autosave_token=autosave_token,
        request_id=request_id,
        selection_snapshot=selection_snapshot,
    )
    if isinstance(outcome, Failure):
        _raise_writing_legacy(outcome)
    return outcome


def export_document_markdown(*, doc_id: int, project_key: str) -> dict[str, Any]:
    document = get_document(doc_id=doc_id, project_key=project_key)
    return {
        "doc_id": int(doc_id),
        "project_key": project_key,
        "filename": f"writing-document-{doc_id}.md",
        "markdown": document["body_md"],
        "exported_at": _utcnow_iso(),
    }
