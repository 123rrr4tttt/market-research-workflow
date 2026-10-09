"""Canonical material addresses."""

from __future__ import annotations
from datetime import date, datetime
from collections.abc import Mapping
from typing import Protocol


MaterialIdentity = dict[str, str]


class MaterialRevisionSource(Protocol):
    updated_at: datetime | date | None
    text_hash: str | None


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
    exact_keys = set(ref) == set(canonical)
    matches_canonical = exact_keys and all(ref.get(key) == value for key, value in canonical.items())
    if not matches_canonical:
        return None
    return canonical


def material_revision(material: Mapping[str, object] | MaterialRevisionSource) -> str:
    updated = material.get("updated_at") if isinstance(material, Mapping) else material.updated_at
    if isinstance(updated, (datetime, date)):
        return updated.isoformat()
    digest = material.get("text_hash") if isinstance(material, Mapping) else material.text_hash
    return str(digest or "current")
