from __future__ import annotations

from ...project_customization.service import get_project_customization


def normalize_material_type(material_type: str) -> str:
    normalized = (material_type or "").strip().lower()
    customization = get_project_customization()
    field_mapping = customization.get_field_mapping() or {}
    mapping = field_mapping.get("material_type_mapping") or {}
    if not isinstance(mapping, dict):
        return normalized
    return str(mapping.get(normalized, normalized))
