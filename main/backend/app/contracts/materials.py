"""Canonical source vocabulary for material bodies across retrieval consumers."""

from typing import Any


def normalize_material_source_type(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def normalize_material_dataset(value: Any) -> str:
    return str(value or "").strip()
