"""Canonical project Document identity shared by structural projections."""

from __future__ import annotations
from datetime import date, datetime
from collections.abc import Mapping
from typing import Any


def document_identity(project_key: str, document_id: int, *, namespace: str = "documents") -> dict[str, str]:
    return {
        "project_key": project_key,
        "module_id": "documents",
        "namespace": namespace,
        "type_id": "document",
        "local_id": str(document_id),
    }


def document_revision(document: Any) -> str:
    updated = document.get("updated_at") if isinstance(document, Mapping) else getattr(document, "updated_at", None)
    if isinstance(updated, (datetime, date)):
        return updated.isoformat()
    digest = document.get("text_hash") if isinstance(document, Mapping) else getattr(document, "text_hash", None)
    return str(digest or "current")
