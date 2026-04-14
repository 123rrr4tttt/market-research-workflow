"""Import curated source presets derived from local open-source reference projects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .auto_classify import infer_keyword_capabilities
from .open_source_source_presets import get_open_source_preset_pack, list_open_source_preset_packs
from .site_entries import upsert_site_entry


@dataclass
class OpenSourceSourceImportResult:
    pack_key: str
    title: str
    scope: str
    project_key: str | None
    inserted_or_updated: list[dict[str, Any]]


def import_open_source_preset_pack(
    *,
    pack_key: str,
    scope: str,
    project_key: str | None,
    enabled: bool = True,
    extra_tags: list[str] | None = None,
) -> OpenSourceSourceImportResult:
    pack = get_open_source_preset_pack(pack_key)
    written: list[dict[str, Any]] = []
    tags_suffix = [str(tag or "").strip() for tag in (extra_tags or []) if str(tag or "").strip()]
    for entry in pack.entries:
        tags = list(dict.fromkeys([*entry.tags, *tags_suffix, "open_source_preset", pack.key]))
        row = upsert_site_entry(
            scope=scope,
            project_key=project_key,
            site_url=entry.site_url,
            entry_type=entry.entry_type,
            template=entry.template,
            name=entry.name,
            domain=entry.domain,
            capabilities=infer_keyword_capabilities(entry.entry_type, _entry_type_to_channel_key(entry.entry_type)),
            source="open_source_preset",
            source_ref={
                "service": "open_source_source_importer",
                "preset_pack": pack.key,
                "source_project": entry.source_project,
                "source_path": entry.source_path,
                "source_kind": entry.source_kind,
            },
            tags=tags,
            enabled=enabled,
            extra={
                "preset_pack": pack.key,
                "preset_title": pack.title,
                "curation_note": entry.note,
                "source_project": entry.source_project,
                "source_path": entry.source_path,
                "source_kind": entry.source_kind,
            },
        )
        written.append(row)
    return OpenSourceSourceImportResult(
        pack_key=pack.key,
        title=pack.title,
        scope=scope,
        project_key=project_key,
        inserted_or_updated=written,
    )


def _entry_type_to_channel_key(entry_type: str) -> str:
    normalized = str(entry_type or "").strip().lower()
    if normalized == "rss":
        return "generic_web.rss"
    if normalized == "sitemap":
        return "generic_web.sitemap"
    if normalized == "search_template":
        return "generic_web.search_template"
    if normalized == "official_api":
        return "official_access.api"
    return "url_pool"


__all__ = [
    "OpenSourceSourceImportResult",
    "import_open_source_preset_pack",
    "list_open_source_preset_packs",
]
