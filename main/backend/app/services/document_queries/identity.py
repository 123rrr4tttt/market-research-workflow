"""Canonical material addresses and explicit legacy document transport."""

from __future__ import annotations
from datetime import date, datetime
from collections.abc import Mapping
from typing import Any


def document_identity(project_key: str, document_id: int, *, namespace: str = "documents") -> dict[str, str]:
    """Historical address accepted by compatibility readers only."""
    return {
        "project_key": project_key,
        "module_id": "documents",
        "namespace": namespace,
        "type_id": "document",
        "local_id": str(document_id),
    }


def material_identity(project_key: str, material_id: int, *, namespace: str = "materials") -> dict[str, str]:
    return {
        "project_key": project_key,
        "module_id": "materials",
        "namespace": namespace,
        "type_id": "material",
        "local_id": str(material_id),
    }


def canonical_material_identity(project_key: str, ref: Mapping[str, Any]) -> dict[str, str] | None:
    local_id = ref.get("local_id")
    if not isinstance(local_id, str) or not local_id.isdigit() or int(local_id) <= 0:
        return None
    canonical = material_identity(project_key, int(local_id))
    if dict(ref) not in (canonical, document_identity(project_key, int(local_id))):
        return None
    return canonical


def document_revision(document: Any) -> str:
    updated = document.get("updated_at") if isinstance(document, Mapping) else getattr(document, "updated_at", None)
    if isinstance(updated, (datetime, date)):
        return updated.isoformat()
    digest = document.get("text_hash") if isinstance(document, Mapping) else getattr(document, "text_hash", None)
    return str(digest or "current")


material_revision = document_revision
