from __future__ import annotations

from ...project_customization.service import get_project_customization


def normalize_doc_type(doc_type: str) -> str:
    normalized = (doc_type or "").strip().lower()
    customization = get_project_customization()
    field_mapping = customization.get_field_mapping() or {}
    doc_type_mapping = field_mapping.get("doc_type_mapping") or {}
    if not isinstance(doc_type_mapping, dict):
        return normalized
    return str(doc_type_mapping.get(normalized, normalized))
