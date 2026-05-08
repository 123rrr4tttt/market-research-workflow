from __future__ import annotations

from typing import Any


def _iso_or_none(value: Any) -> str | None:
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return isoformat()
    return str(value)


def serialize_writing_document(row: Any) -> dict[str, Any]:
    version = int(getattr(row, "head_version", 1) or 1)
    body_md = getattr(row, "body_md", "") or ""
    return {
        "id": int(getattr(row, "id")),
        "project_key": getattr(row, "project_key", None),
        "title": getattr(row, "title", "") or "",
        "body_md": body_md,
        "status": getattr(row, "status", None) or "draft",
        "version": version,
        "etag": getattr(row, "etag", None),
        "updated_by_user_id": getattr(row, "updated_by_user_id", None),
        "updated_at": _iso_or_none(getattr(row, "updated_at", None)),
        "created_at": _iso_or_none(getattr(row, "created_at", None)),
        "metadata_json": dict(getattr(row, "metadata_json", None) or {}),
    }


def serialize_writing_document_draft(row: Any) -> dict[str, Any]:
    selection_snapshot = getattr(row, "selection_snapshot", None)
    return {
        "id": int(getattr(row, "id")),
        "doc_id": int(getattr(row, "doc_id")),
        "project_key": getattr(row, "project_key", None),
        "draft_body_md": getattr(row, "draft_body_md", "") or "",
        "selection_snapshot": dict(selection_snapshot or {}) if isinstance(selection_snapshot, dict) else selection_snapshot,
        "base_version": int(getattr(row, "base_version", 1) or 1),
        "autosave_token": getattr(row, "autosave_token", None),
        "request_id": getattr(row, "request_id", None),
        "updated_at": _iso_or_none(getattr(row, "updated_at", None)),
        "created_at": _iso_or_none(getattr(row, "created_at", None)),
    }


def serialize_writing_citation(row: Any) -> dict[str, Any]:
    metadata_json = getattr(row, "metadata_json", None)
    return {
        "id": int(getattr(row, "id")),
        "doc_id": int(getattr(row, "doc_id")),
        "project_key": getattr(row, "project_key", None),
        "source_doc_id": getattr(row, "source_doc_id", None),
        "source_uri": getattr(row, "source_uri", None),
        "source_title": getattr(row, "source_title", None),
        "quote_text": getattr(row, "quote_text", None),
        "position_anchor": getattr(row, "position_anchor", None),
        "card_id": getattr(row, "card_id", None),
        "metadata_json": dict(metadata_json or {}) if isinstance(metadata_json, dict) else metadata_json,
        "created_at": _iso_or_none(getattr(row, "created_at", None)),
        "updated_at": _iso_or_none(getattr(row, "updated_at", None)),
    }


def build_writing_conflict_details(row: Any, *, expected_version: int | None) -> dict[str, Any]:
    serialized = serialize_writing_document(row)
    return {
        "conflict_code": "VERSION_CONFLICT",
        "expected_version": expected_version,
        "current_version": serialized["version"],
        "server_snapshot": serialized,
        "updated_by_user_id": serialized["updated_by_user_id"],
        "updated_at": serialized["updated_at"],
    }
