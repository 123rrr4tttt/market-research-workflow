"""Pure projection of prepared text into the existing frontdoor payload shape."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from typing import Annotated, Any, Mapping

from .material_input import PreparedMaterial


@dataclass(frozen=True, slots=True)
class MaterialSourceContext:
    source_name: str
    source_kind: str
    uri: str | None
    platform: str
    entrypoint: str
    source_mode: str
    http_status: int | None = None


@dataclass(frozen=True, slots=True)
class MaterialTargetSpec:
    doc_type: str
    title: str | None
    summary: str | None
    publish_date: date | None
    state: str | None
    extraction_enabled: bool
    extraction_mode: str
    chunks: tuple[str, ...]
    extraction_flags: Mapping[str, Any]


def build_material_frontdoor_payload(
    prepared: PreparedMaterial,
    *,
    target: MaterialTargetSpec,
    source: MaterialSourceContext,
    extracted_data_base: Mapping[str, Any] | None = None,
) -> Annotated[
    dict[str, dict[str, Any]],
    "kit:non-authoritative derived_as=view fact_source=prepared_material+target_spec+source_context+extracted_data_base witness=test:test_frontdoor_payload_is_pure_and_uses_target_and_source_decisions",
]:
    """Build deterministic consumer fields; performs no fetch or persistence."""

    candidate = {
        "source_name": source.source_name,
        "source_kind": source.source_kind,
        "source_base_url": None,
        "state": target.state,
        "doc_type": target.doc_type,
        "title": target.title,
        "publish_date": target.publish_date,
        "content": prepared.text,
        "summary": target.summary,
        "text_hash": sha256(prepared.text.encode("utf-8")).hexdigest(),
        "uri": source.uri,
        "status": None,
        "extracted_data_base": dict(extracted_data_base or {}),
    }
    terminal_context = {
        "platform": source.platform,
        "ingestion_entrypoint": source.entrypoint,
        "source_mode": source.source_mode,
        "quality_score": 0.0,
        "degradation_flags": [],
        "http_status": source.http_status,
        "capability_profile": {},
        "light_filter": {},
    }
    extraction_plan = {
        "enabled": target.extraction_enabled,
        "mode": target.extraction_mode,
        "chunks": list(target.chunks),
        **{
            name: bool(target.extraction_flags.get(name))
            for name in (
                "include_policy", "include_market", "include_sentiment",
                "include_company", "include_product", "include_operation",
            )
        },
    }
    return {
        "document_candidate": candidate,
        "terminal_context": terminal_context,
        "extraction_plan": extraction_plan,
    }


__all__ = [
    "MaterialSourceContext",
    "MaterialTargetSpec",
    "build_material_frontdoor_payload",
]
