"""Canonical material addresses and explicit legacy document transport."""

from __future__ import annotations
from datetime import date, datetime
from collections.abc import Mapping
from typing import Protocol


MaterialIdentity = dict[str, str]


class DocumentRevisionSource(Protocol):
    updated_at: datetime | date | None
    text_hash: str | None


def document_identity(project_key: str, document_id: int, *, namespace: str = "documents") -> MaterialIdentity:
    """Historical address accepted by compatibility readers only."""
    return {
        "project_key": project_key,
        "module_id": "documents",
        "namespace": namespace,
        "type_id": "document",
        "local_id": str(document_id),
    }


def material_identity(project_key: str, material_id: int, *, namespace: str = "materials") -> MaterialIdentity:
    return {
        "project_key": project_key,
        "module_id": "materials",
        "namespace": namespace,
        "type_id": "material",
        "local_id": str(material_id),
    }


def canonical_material_identity(project_key: str, ref: Mapping[str, object]) -> MaterialIdentity | None:
    local_id = ref.get("local_id")
    if not isinstance(local_id, str) or not local_id.isdigit() or int(local_id) <= 0:
        return None
    canonical = material_identity(project_key, int(local_id))
    legacy = document_identity(project_key, int(local_id))
    exact_keys = set(ref) == set(canonical)
    matches_canonical = exact_keys and all(ref.get(key) == value for key, value in canonical.items())
    matches_legacy = exact_keys and all(ref.get(key) == value for key, value in legacy.items())
    if not (matches_canonical or matches_legacy):
        return None
    return canonical


def document_revision(document: Mapping[str, object] | DocumentRevisionSource) -> str:
    updated = document.get("updated_at") if isinstance(document, Mapping) else document.updated_at
    if isinstance(updated, (datetime, date)):
        return updated.isoformat()
    digest = document.get("text_hash") if isinstance(document, Mapping) else document.text_hash
    return str(digest or "current")


material_revision = document_revision
