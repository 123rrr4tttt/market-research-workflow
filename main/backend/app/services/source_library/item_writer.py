from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import NoReturn, TypeAlias, TypeGuard

from fastapi import HTTPException
from pydantic import BaseModel, Field, JsonValue
from sqlalchemy import select

from ...contracts import ErrorCode, error_response, map_exception_to_error
from ...contracts.responses import ok
from ...models.base import SessionLocal
from ...models.entities import SourceLibraryItem
from ...settings.config import get_effective_project_key_enforcement_mode
from ..projects import bind_project, current_project_key
from ..resource_pool import get_site_entry_by_url, list_site_entries
from ..resource_pool.url_utils import normalize_url
from .external_project import (
    EXTERNAL_PROJECT_CHANNEL_KEY,
    normalize_external_project_extra,
)
from .types import ItemType, is_system_managed_source_library_item

SourceLibraryJsonValue: TypeAlias = JsonValue
SourceLibraryJsonObject: TypeAlias = dict[str, SourceLibraryJsonValue]
SourceLibraryWriteResponse: TypeAlias = dict[str, object]

ITEM_TYPE_USER_DEFINED: ItemType = "user_defined"
ITEM_TYPE_SERVICE_AGGREGATED: ItemType = "service_aggregated"

SOURCE_ITEM_CAPABILITY_DEFAULT: dict[str, object] = {
    "supports_incremental": True,
    "supports_backfill": False,
    "rate_limit_class": "normal",
}

logger = logging.getLogger(__name__)


class SourceLibraryItemUpsertPayload(BaseModel):
    item_key: str = Field(..., min_length=1, max_length=128)
    name: str = Field(..., min_length=1, max_length=255)
    channel_key: str = Field(..., min_length=1, max_length=128)
    description: str | None = None
    params: SourceLibraryJsonObject = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    schedule: str | None = None
    extends_item_key: str | None = None
    enabled: bool = True
    item_type: ItemType = ITEM_TYPE_USER_DEFINED
    extra: SourceLibraryJsonObject = Field(default_factory=dict)


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _raise_value_error(message: str) -> NoReturn:
    raise ValueError(message)


def _raise_invalid_input(message: str, *, status_code: int = 400) -> NoReturn:
    raise HTTPException(
        status_code=status_code,
        detail=error_response(ErrorCode.INVALID_INPUT, message),
    )


def _raise_not_found(item_key: str) -> NoReturn:
    raise HTTPException(
        status_code=404,
        detail=error_response(
            ErrorCode.NOT_FOUND,
            f"item not found: {item_key}",
            details={"item_key": item_key},
        ),
    )


def _set_row_value(row: object, field_name: str, value: object) -> None:
    setattr(row, field_name, value)


def _row_json_object(row: object, field_name: str) -> SourceLibraryJsonObject:
    return _json_object(
        getattr(row, field_name, None) or {},
        path=f"source_library.item.{field_name}",
    )


def _row_string_list(row: object, field_name: str) -> list[str]:
    raw_value = getattr(row, field_name, None)
    if not _is_object_list(raw_value):
        return []
    return [item for item in raw_value if isinstance(item, str)]


def _row_is_system_managed(row: object) -> bool:
    raw_extra = getattr(row, "extra", None)
    extra: dict[str, object] = {}
    if _is_object_mapping(raw_extra):
        extra = {
            key: value
            for key, value in raw_extra.items()
            if isinstance(key, str)
        }
    return is_system_managed_source_library_item(
        item_type=getattr(row, "item_type", None),
        managed_by=getattr(row, "managed_by", None),
        item_key=getattr(row, "item_key", None),
        channel_key=getattr(row, "channel_key", None),
        extra=extra,
    )


def _json_value(value: object, *, path: str) -> SourceLibraryJsonValue:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if _is_object_list(value):
        return [
            _json_value(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    if _is_object_mapping(value):
        normalized: SourceLibraryJsonObject = {}
        for key, item in value.items():
            if not isinstance(key, str):
                _raise_value_error(f"{path} keys must be strings")
            normalized[key] = _json_value(item, path=f"{path}.{key}")
        return normalized
    _raise_value_error(f"{path} must contain JSON-compatible values")


def _json_object(value: object, *, path: str) -> SourceLibraryJsonObject:
    normalized = _json_value(value, path=path)
    if not isinstance(normalized, dict):
        _raise_value_error(f"{path} must be an object")
    return normalized


def source_library_json_object(
    value: object,
    *,
    path: str,
) -> SourceLibraryJsonObject:
    return _json_object(value, path=path)


def raise_mapped_error(exc: Exception) -> NoReturn:
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, ValueError):
        raise HTTPException(
            status_code=400,
            detail=error_response(
                ErrorCode.INVALID_INPUT,
                str(exc) or "Invalid source library request.",
                details={"exception_type": exc.__class__.__name__},
            ),
        ) from exc
    code, message, details = map_exception_to_error(exc)
    status_code = 503 if code == ErrorCode.UPSTREAM_ERROR else 500
    raise HTTPException(
        status_code=status_code,
        detail=error_response(code, message, details=details),
    ) from exc


def require_project_key(project_key: str | None) -> str:
    key = (project_key or "").strip()
    if key:
        return key

    enforcement_mode = get_effective_project_key_enforcement_mode()
    if enforcement_mode == "require":
        raise HTTPException(
            status_code=400,
            detail=error_response(
                ErrorCode.PROJECT_KEY_REQUIRED,
                "project_key is required. Please select a project first.",
            ),
        )

    fallback = (current_project_key() or "").strip()
    if fallback:
        logger.warning(
            "project_key_fallback_used endpoint=source_library resolved_project_key=%s",
            fallback,
        )
        return fallback

    raise HTTPException(
        status_code=400,
        detail=error_response(
            ErrorCode.PROJECT_KEY_REQUIRED,
            "project_key is required. Please select a project first.",
        ),
    )


def normalize_item_site_entries(
    params: SourceLibraryJsonObject,
) -> tuple[SourceLibraryJsonObject, list[str]]:
    normalized = dict(params)
    raw = normalized.get("site_entries")
    if raw is None:
        raw = normalized.get("site_entry_urls")
    if raw is None:
        return normalized, []

    if isinstance(raw, str):
        raw_entries: list[SourceLibraryJsonValue] = [raw]
    elif isinstance(raw, list):
        raw_entries = raw
    else:
        raw_entries = []

    urls: list[str] = []
    for entry in raw_entries:
        candidate = ""
        if isinstance(entry, str):
            candidate = entry.strip()
        elif isinstance(entry, dict):
            raw_url = entry.get("site_url") or entry.get("url") or ""
            candidate = str(raw_url).strip()
        else:
            candidate = str(entry or "").strip()
        normalized_url = normalize_url(candidate)
        if normalized_url and normalized_url not in urls:
            urls.append(normalized_url)

    normalized_urls: list[SourceLibraryJsonValue] = list(urls)
    normalized["site_entries"] = normalized_urls
    normalized.pop("site_entry_urls", None)
    return normalized, urls


def normalize_source_item_capability(
    extra: SourceLibraryJsonObject,
) -> SourceLibraryJsonObject:
    normalized = dict(extra)
    raw_capability = normalized.get("capability")
    capability = raw_capability if isinstance(raw_capability, dict) else {}
    merged = _json_object(
        SOURCE_ITEM_CAPABILITY_DEFAULT,
        path="source_library.capability.default",
    )
    merged.update(capability)
    merged["supports_incremental"] = bool(merged.get("supports_incremental", True))
    merged["supports_backfill"] = bool(merged.get("supports_backfill", False))
    raw_rate_limit_class = merged.get("rate_limit_class")
    merged["rate_limit_class"] = (
        raw_rate_limit_class.strip().lower()
        if isinstance(raw_rate_limit_class, str) and raw_rate_limit_class.strip()
        else "normal"
    )
    normalized["capability"] = merged
    return normalized


def normalize_upsert_item_type(
    *,
    payload_item_type: ItemType,
    normalized_extra: SourceLibraryJsonObject,
    allow_system_item_type: bool,
) -> ItemType:
    raw_extra_item_type = normalized_extra.get("item_type")
    extra_item_type = (
        raw_extra_item_type.strip().lower()
        if isinstance(raw_extra_item_type, str)
        else ""
    )
    requested_item_type: ItemType = payload_item_type
    if (
        extra_item_type in {ITEM_TYPE_USER_DEFINED, ITEM_TYPE_SERVICE_AGGREGATED}
        and extra_item_type != requested_item_type
    ):
        _raise_invalid_input(
            "item_type conflict between payload.item_type and payload.extra.item_type",
        )
    if requested_item_type == ITEM_TYPE_SERVICE_AGGREGATED and not allow_system_item_type:
        _raise_invalid_input(
            "service_aggregated item_type is system-managed and cannot be written via user API",
            status_code=403,
        )
    normalized_extra["item_type"] = requested_item_type
    return requested_item_type


def validate_handler_item_constraints(
    *,
    params: SourceLibraryJsonObject,
    extra: SourceLibraryJsonObject,
    project_key: str,
) -> None:
    raw_creation_handler = extra.get("creation_handler") or extra.get("builder_handler")
    creation_handler = (
        raw_creation_handler.strip()
        if isinstance(raw_creation_handler, str)
        else ""
    )
    raw_expected_entry_type = extra.get("expected_entry_type")
    expected_entry_type = (
        raw_expected_entry_type.strip().lower()
        if isinstance(raw_expected_entry_type, str)
        else ""
    )
    is_handler_item = creation_handler.startswith("handler") or bool(expected_entry_type)
    if not is_handler_item:
        return

    raw_site_entries: list[SourceLibraryJsonValue] = []
    for key in ("site_entries", "official_access_site_entries"):
        entries = params.get(key)
        if isinstance(entries, list):
            raw_site_entries.extend(entries)
    if not raw_site_entries and not isinstance(params.get("site_entries"), list):
        _raise_value_error("handler-built item requires params.site_entries to be a list")
    if not raw_site_entries:
        _raise_value_error("handler-built item requires non-empty params.site_entries")
    if not expected_entry_type:
        _raise_value_error("handler-built item requires extra.expected_entry_type")

    mismatches: list[str] = []
    for raw_url in raw_site_entries:
        url = str(raw_url).strip()
        entry = _json_object(
            get_site_entry_by_url(
                scope="effective",
                project_key=project_key,
                site_url=url,
            )
            or {},
            path="source_library.site_entry",
        )
        raw_entry_type = entry.get("entry_type")
        entry_type = (
            raw_entry_type.strip().lower()
            if isinstance(raw_entry_type, str)
            else ""
        )
        if entry_type and entry_type != expected_entry_type:
            mismatches.append(f"{url}({entry_type})")
    if mismatches:
        _raise_value_error(
            "handler-built item site_entries must all match "
            f"expected_entry_type={expected_entry_type}; "
            f"mismatches={', '.join(mismatches[:8])}"
        )


def refresh_handler_item_site_entries(
    *,
    row: object,
    project_key: str,
    incremental: bool,
    max_site_entries: int,
) -> SourceLibraryJsonObject:
    extra = _row_json_object(row, "extra")
    params = _row_json_object(row, "params")

    raw_expected_entry_type = extra.get("expected_entry_type")
    expected_entry_type = (
        raw_expected_entry_type.strip().lower()
        if isinstance(raw_expected_entry_type, str)
        else ""
    )
    if not expected_entry_type:
        _raise_value_error(
            "item.extra.expected_entry_type is required for handler refresh"
        )

    raw_domains = extra.get("domains")
    if isinstance(raw_domains, str):
        domains = [raw_domains.strip().lower()] if raw_domains.strip() else []
    elif isinstance(raw_domains, list):
        domains = [
            str(item).strip().lower()
            for item in raw_domains
            if str(item or "").strip()
        ]
    else:
        domains = []

    raw_tag_filters = extra.get("site_entry_tags")
    if isinstance(raw_tag_filters, str):
        tag_filters = (
            [raw_tag_filters.strip().lower()]
            if raw_tag_filters.strip()
            else []
        )
    elif isinstance(raw_tag_filters, list):
        tag_filters = [
            str(item).strip().lower()
            for item in raw_tag_filters
            if str(item or "").strip()
        ]
    else:
        tag_filters = []

    page = 1
    candidates: list[str] = []
    while len(candidates) < max_site_entries:
        raw_items, total = list_site_entries(
            scope="effective",
            project_key=project_key,
            entry_type=expected_entry_type,
            enabled=True,
            page=page,
            page_size=min(100, max_site_entries),
        )
        items = [
            _json_object(
                raw_item,
                path=f"source_library.site_entries[{index}]",
            )
            for index, raw_item in enumerate(raw_items)
        ]
        for entry in items:
            raw_url = entry.get("site_url")
            url = str(raw_url or "").strip()
            raw_domain = entry.get("domain")
            domain = str(raw_domain or "").strip().lower()
            raw_tags = entry.get("tags")
            tags = (
                [
                    str(item).strip().lower()
                    for item in raw_tags
                    if str(item or "").strip()
                ]
                if isinstance(raw_tags, list)
                else []
            )
            if domains and domain not in domains:
                continue
            if tag_filters and not any(tag in tags for tag in tag_filters):
                continue
            if url and url not in candidates:
                candidates.append(url)
            if len(candidates) >= max_site_entries:
                break
        if (
            not items
            or len(candidates) >= max_site_entries
            or page * min(100, max_site_entries) >= total
        ):
            break
        page += 1

    normalized_params, old_urls = normalize_item_site_entries(params)
    if incremental:
        new_urls = list(old_urls)
        for url in candidates:
            if url not in new_urls:
                new_urls.append(url)
    else:
        new_urls = candidates
    normalized_urls: list[SourceLibraryJsonValue] = list(new_urls)
    normalized_params["site_entries"] = normalized_urls
    _set_row_value(row, "params", normalized_params)
    item_key = getattr(row, "item_key", "")
    resolved_item_key = item_key if isinstance(item_key, str) else str(item_key)
    added = (
        max(0, len(new_urls) - len(old_urls))
        if incremental
        else len([url for url in new_urls if url not in old_urls])
    )
    return {
        "item_key": resolved_item_key,
        "expected_entry_type": expected_entry_type,
        "incremental": incremental,
        "domains": list(domains),
        "site_entry_tags": list(tag_filters),
        "site_entries_before": len(old_urls),
        "site_entries_after": len(new_urls),
        "added": added,
    }


def refresh_project_item(
    *,
    item_key: str,
    project_key: str,
    incremental: bool,
    max_site_entries: int,
) -> SourceLibraryWriteResponse:
    try:
        resolved_project_key = require_project_key(project_key)
        with bind_project(resolved_project_key):
            with SessionLocal() as session:
                row = session.execute(
                    select(SourceLibraryItem).where(
                        SourceLibraryItem.item_key == item_key
                    )
                ).scalar_one_or_none()
                if row is None:
                    _raise_not_found(item_key)
                result = refresh_handler_item_site_entries(
                    row=row,
                    project_key=resolved_project_key,
                    incremental=incremental,
                    max_site_entries=max_site_entries,
                )
                validate_handler_item_constraints(
                    params=_row_json_object(row, "params"),
                    extra=_row_json_object(row, "extra"),
                    project_key=resolved_project_key,
                )
                session.commit()
    except Exception as exc:  # noqa: BLE001
        raise_mapped_error(exc)
    return ok({"ok": True, "project_key": resolved_project_key, **result})


def sync_handler_cluster_items(
    *,
    project_key: str,
    handlers: list[str] | None,
    incremental: bool,
    max_site_entries: int,
) -> SourceLibraryWriteResponse:
    try:
        resolved_project_key = require_project_key(project_key)
        requested = [item.strip().lower() for item in handlers or [] if item.strip()]
        requested_set = set(requested)

        page = 1
        page_size = 200
        entry_types: set[str] = set()
        while True:
            raw_rows, total = list_site_entries(
                scope="effective",
                project_key=resolved_project_key,
                enabled=True,
                page=page,
                page_size=page_size,
            )
            rows = [
                _json_object(
                    raw_row,
                    path=f"source_library.handler_entries[{index}]",
                )
                for index, raw_row in enumerate(raw_rows)
            ]
            for row_payload in rows:
                raw_entry_type = row_payload.get("entry_type")
                entry_type = (
                    raw_entry_type.strip().lower()
                    if isinstance(raw_entry_type, str)
                    else ""
                )
                if not entry_type or entry_type == "url_routing":
                    continue
                if requested_set and entry_type not in requested_set:
                    continue
                entry_types.add(entry_type)
            if not rows or page * page_size >= total:
                break
            page += 1

        processed: list[SourceLibraryJsonValue] = []
        with bind_project(resolved_project_key):
            with SessionLocal() as session:
                for handler_key in sorted(entry_types):
                    item_key = f"handler.cluster.{handler_key}"
                    row = session.execute(
                        select(SourceLibraryItem).where(
                            SourceLibraryItem.item_key == item_key
                        )
                    ).scalar_one_or_none()
                    if row is None:
                        row = SourceLibraryItem()
                        _set_row_value(row, "item_key", item_key)
                        session.add(row)
                        _set_row_value(row, "name", f"Handler Cluster {handler_key}")
                        _set_row_value(row, "channel_key", "handler.cluster")
                        _set_row_value(row, "enabled", True)
                        _set_row_value(
                            row,
                            "tags",
                            ["handler_cluster", handler_key],
                        )
                    else:
                        raw_name = getattr(row, "name", None)
                        name = (
                            raw_name
                            if isinstance(raw_name, str) and raw_name
                            else f"Handler Cluster {handler_key}"
                        )
                        raw_channel_key = getattr(row, "channel_key", None)
                        channel_key = (
                            raw_channel_key
                            if isinstance(raw_channel_key, str) and raw_channel_key
                            else "handler.cluster"
                        )
                        _set_row_value(row, "name", name)
                        _set_row_value(row, "channel_key", channel_key)
                        _set_row_value(
                            row,
                            "enabled",
                            getattr(row, "enabled", None) is not False,
                        )
                        _set_row_value(
                            row,
                            "tags",
                            list(
                                dict.fromkeys(
                                    [
                                        *_row_string_list(row, "tags"),
                                        "handler_cluster",
                                        handler_key,
                                    ]
                                )
                            ),
                        )

                    extra = _row_json_object(row, "extra")
                    extra["creation_handler"] = "handler.entry_type"
                    extra["expected_entry_type"] = handler_key
                    extra["stable_handler_cluster"] = True
                    extra["item_type"] = ITEM_TYPE_SERVICE_AGGREGATED
                    extra["managed_by"] = "system"
                    if extra.get("auto_maintain") is None:
                        extra["auto_maintain"] = True
                    _set_row_value(row, "extra", extra)
                    _set_row_value(
                        row,
                        "item_type",
                        ITEM_TYPE_SERVICE_AGGREGATED,
                    )
                    _set_row_value(row, "managed_by", "system")

                    params = _row_json_object(row, "params")
                    params["expected_entry_type"] = handler_key
                    if not isinstance(params.get("site_entries"), list):
                        params["site_entries"] = []
                    _set_row_value(row, "params", params)

                    refresh_result = refresh_handler_item_site_entries(
                        row=row,
                        project_key=resolved_project_key,
                        incremental=incremental,
                        max_site_entries=max_site_entries,
                    )
                    validate_handler_item_constraints(
                        params=_row_json_object(row, "params"),
                        extra=_row_json_object(row, "extra"),
                        project_key=resolved_project_key,
                    )
                    processed.append(
                        {
                            "handler_key": handler_key,
                            "item_key": item_key,
                            **refresh_result,
                        }
                    )
                session.commit()
    except Exception as exc:  # noqa: BLE001
        raise_mapped_error(exc)

    return ok(
        {
            "ok": True,
            "project_key": resolved_project_key,
            "handler_count": len(processed),
            "results": processed,
        }
    )


def upsert_project_item(
    *,
    payload: SourceLibraryItemUpsertPayload,
    project_key: str,
) -> SourceLibraryWriteResponse:
    try:
        resolved_project_key = require_project_key(project_key)
        normalized_params, _ = normalize_item_site_entries(payload.params)
        normalized_extra = normalize_source_item_capability(payload.extra)
        normalized_extra = _json_object(
            normalize_external_project_extra(
                normalized_extra,
                item_key=payload.item_key,
                display_name=payload.name,
                channel_key=payload.channel_key,
            ),
            path="source_library.extra",
        )
        resolved_item_type = normalize_upsert_item_type(
            payload_item_type=payload.item_type,
            normalized_extra=normalized_extra,
            allow_system_item_type=False,
        )
        channel_key = payload.channel_key.strip().lower()
        if (
            resolved_item_type == ITEM_TYPE_USER_DEFINED
            and channel_key.startswith("generic_web.")
        ):
            _raise_invalid_input(
                "generic_web.* is internal adapter-only and cannot be directly created as user_defined item",
            )
        if (
            channel_key == EXTERNAL_PROJECT_CHANNEL_KEY
            and "external_project_manifest" not in normalized_extra
        ):
            _raise_invalid_input(
                f"{EXTERNAL_PROJECT_CHANNEL_KEY} requires payload.extra.external_project_manifest",
            )
        with bind_project(resolved_project_key):
            with SessionLocal() as session:
                row = session.execute(
                    select(SourceLibraryItem).where(
                        SourceLibraryItem.item_key == payload.item_key
                    )
                ).scalar_one_or_none()
                if row is not None and _row_is_system_managed(row):
                    _raise_invalid_input(
                        "system-managed source library item cannot be updated via user API",
                        status_code=403,
                    )
                validate_handler_item_constraints(
                    params=normalized_params,
                    extra=normalized_extra,
                    project_key=resolved_project_key,
                )
                if row is None:
                    row = SourceLibraryItem()
                    _set_row_value(row, "item_key", payload.item_key)
                    session.add(row)

                _set_row_value(row, "name", payload.name)
                _set_row_value(row, "channel_key", payload.channel_key)
                _set_row_value(row, "description", payload.description)
                _set_row_value(row, "params", normalized_params)
                _set_row_value(row, "tags", list(payload.tags))
                _set_row_value(row, "schedule", payload.schedule)
                _set_row_value(row, "extends_item_key", payload.extends_item_key)
                _set_row_value(row, "item_type", resolved_item_type)
                _set_row_value(
                    row,
                    "managed_by",
                    "system"
                    if resolved_item_type == ITEM_TYPE_SERVICE_AGGREGATED
                    else "user",
                )
                _set_row_value(row, "enabled", payload.enabled)
                _set_row_value(row, "extra", normalized_extra)
                session.commit()
    except Exception as exc:  # noqa: BLE001
        raise_mapped_error(exc)

    return ok(
        {
            "item_key": payload.item_key,
            "project_key": resolved_project_key,
            "ok": True,
        }
    )


__all__ = [
    "ITEM_TYPE_SERVICE_AGGREGATED",
    "ITEM_TYPE_USER_DEFINED",
    "ItemType",
    "SourceLibraryItemUpsertPayload",
    "SourceLibraryJsonObject",
    "SourceLibraryJsonValue",
    "normalize_item_site_entries",
    "normalize_source_item_capability",
    "normalize_upsert_item_type",
    "raise_mapped_error",
    "refresh_handler_item_site_entries",
    "refresh_project_item",
    "require_project_key",
    "sync_handler_cluster_items",
    "source_library_json_object",
    "upsert_project_item",
    "validate_handler_item_constraints",
]
