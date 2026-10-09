from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ...models.base import SessionLocal
from ...models.entities import Material
from ...models.entities import Source
from .material_type_mapper import normalize_material_type


def persist_terminal_material(payload: dict[str, Any]) -> dict[str, Any]:
    with SessionLocal() as session:
        result = persist_terminal_material_in_session(session, payload)
        session.commit()
        return result


def persist_terminal_material_in_session(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist the sole material body inside a caller-owned transaction."""
    normalized = dict(payload or {})
    material_type = normalize_material_type(str(normalized.get("material_type") or "unknown"))
    uri = str(normalized.get("uri") or "").strip() or None
    text_hash = str(normalized.get("text_hash") or "").strip() or None
    existing = None
    if uri:
        existing = session.query(Material).filter(Material.uri == uri).first()
    if existing is None and text_hash:
        existing = session.query(Material).filter(Material.text_hash == text_hash).first()
    if existing is not None and not (
        existing.status == "reference_only" and not existing.content and normalized.get("content")
    ):
        return {
            "material_id": int(existing.id),
            "inserted": 0,
            "skipped": 1,
            "reason": "skipped_exists",
            "material_type": material_type,
        }

    source = get_or_create_source(
        session,
        name=str(normalized.get("source_name") or "unknown"),
        kind=str(normalized.get("source_kind") or "external"),
        base_url=str(normalized.get("source_base_url") or ""),
    )
    if existing is not None:
        for key in ("title", "summary", "content", "publish_date", "state"):
            if normalized.get(key) is not None:
                setattr(existing, key, normalized[key])
        existing.source_id = source.id
        existing.material_type = material_type
        existing.status = normalized.get("status")
        existing.text_hash = text_hash
        existing.extracted_data = {**(existing.extracted_data or {}), **(normalized.get("extracted_data") or {})}
        session.flush()
        return {
            "material_id": int(existing.id),
            "inserted": 0,
            "updated": 1,
            "skipped": 0,
            "reason": "materialized_reference",
            "material_type": material_type,
        }
    material = Material(
        source_id=source.id,
        state=normalized.get("state"),
        material_type=material_type,
        title=normalized.get("title"),
        status=normalized.get("status"),
        publish_date=normalized.get("publish_date"),
        summary=normalized.get("summary"),
        content=normalized.get("content"),
        text_hash=text_hash,
        uri=uri,
        extracted_data=normalized.get("extracted_data"),
    )
    session.add(material)
    session.flush()
    return {
        "material_id": int(material.id),
        "inserted": 1,
        "skipped": 0,
        "reason": "inserted",
        "material_type": material_type,
    }


def get_or_create_source(session: Session, *, name: str, kind: str, base_url: str | None) -> Source:
    existing = session.query(Source).filter(Source.name == name, Source.kind == kind).first()
    if existing:
        return existing
    row = Source(name=name, kind=kind, base_url=base_url or "")
    session.add(row)
    session.flush()
    return row


_get_or_create_source = get_or_create_source

__all__ = [
    "get_or_create_source",
    "persist_terminal_material",
    "persist_terminal_material_in_session",
]
