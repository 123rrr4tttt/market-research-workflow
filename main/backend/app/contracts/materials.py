"""Canonical source vocabulary for material bodies across retrieval consumers."""

from typing import Any


def normalize_material_source_type(value: Any) -> str:
    source_type = " ".join(str(value or "").strip().split())
    return "material" if source_type == "document" else source_type


def normalize_material_dataset(value: Any) -> str:
    dataset = str(value or "").strip()
    return "materials" if dataset == "documents" else dataset
