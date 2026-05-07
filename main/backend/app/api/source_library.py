from __future__ import annotations

import logging
from typing import Any, Dict, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..contracts import ErrorCode, error_response, map_exception_to_error
from ..contracts.responses import ok
from ..models.base import SessionLocal
from ..models.entities import SourceLibraryItem
from ..services.projects import bind_project, current_project_key
from ..services.resource_pool import get_site_entry_by_url, list_site_entries
from ..services.resource_pool.url_utils import normalize_url
from ..services.source_library import (
    list_channels_grouped_by_provider,
    list_effective_channels,
    list_effective_items,
    list_items_by_symbol,
    sync_shared_library_from_files,
)
from ..services.source_library.external_project import (
    EXTERNAL_PROJECT_CHANNEL_KEY,
    build_external_project_summary,
    get_external_project_manifest,
    normalize_external_project_extra,
)
from ..services.source_library.external_project_registration import synthesize_external_project_item
from ..services.source_library.item_plan import build_item_execution_plan
from ..services.streamplus.contracts import SOURCE_ITEM_CAPABILITY_DEFAULT
from ..settings.config import get_effective_project_key_enforcement_mode, settings

ScopeType = Literal["shared", "project", "effective"]
ItemType = Literal["user_defined", "service_aggregated"]
ITEM_TYPE_USER_DEFINED: ItemType = "user_defined"
ITEM_TYPE_SERVICE_AGGREGATED: ItemType = "service_aggregated"

router = APIRouter(prefix="/source_library", tags=["source_library"])
logger = logging.getLogger(__name__)


def _raise_mapped_error(exc: Exception) -> None:
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


class SourceLibraryItemUpsertPayload(BaseModel):
    item_key: str = Field(..., min_length=1, max_length=128)
    name: str = Field(..., min_length=1, max_length=255)
    channel_key: str = Field(..., min_length=1, max_length=128)
    description: str | None = None
    params: Dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    schedule: str | None = None
    extends_item_key: str | None = None
    enabled: bool = True
    item_type: ItemType = ITEM_TYPE_USER_DEFINED
    extra: Dict[str, Any] = Field(default_factory=dict)


class RefreshItemPayload(BaseModel):
    project_key: str | None = None
    incremental: bool = True
    max_site_entries: int = Field(default=500, ge=1, le=5000)


class SyncHandlerClustersPayload(BaseModel):
    project_key: str | None = None
    handlers: list[str] | None = None
    incremental: bool = True
    max_site_entries: int = Field(default=500, ge=1, le=5000)


class ExternalProjectRegistrationPayload(BaseModel):
    project_link: str = Field(..., min_length=1, max_length=2048)
    item_key: str | None = Field(default=None, min_length=1, max_length=128)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True
    persist: bool = True
    hints: Dict[str, Any] = Field(default_factory=dict)


def _normalize_source_item_capability(extra: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(extra or {})
    capability = out.get("capability") if isinstance(out.get("capability"), dict) else {}
    merged = dict(SOURCE_ITEM_CAPABILITY_DEFAULT)
    merged.update(capability)
    merged["supports_incremental"] = bool(merged.get("supports_incremental", True))
    merged["supports_backfill"] = bool(merged.get("supports_backfill", False))
    merged["rate_limit_class"] = str(merged.get("rate_limit_class") or "normal").strip().lower()
    out["capability"] = merged
    return out


def _resolve_item_type_from_extra(extra: dict[str, Any] | None) -> ItemType:
    payload = extra if isinstance(extra, dict) else {}
    declared = str(payload.get("item_type") or "").strip().lower()
    if declared == ITEM_TYPE_SERVICE_AGGREGATED:
        return ITEM_TYPE_SERVICE_AGGREGATED
    if declared == ITEM_TYPE_USER_DEFINED:
        return ITEM_TYPE_USER_DEFINED
    if bool(payload.get("stable_handler_cluster")):
        return ITEM_TYPE_SERVICE_AGGREGATED
    creation_handler = str(payload.get("creation_handler") or "").strip().lower()
    if creation_handler.startswith("handler.entry_type"):
        return ITEM_TYPE_SERVICE_AGGREGATED
    return ITEM_TYPE_USER_DEFINED


def _resolve_item_type(item: dict[str, Any]) -> ItemType:
    declared = str(item.get("item_type") or "").strip().lower()
    if declared in {ITEM_TYPE_USER_DEFINED, ITEM_TYPE_SERVICE_AGGREGATED}:
        return declared  # type: ignore[return-value]
    return _resolve_item_type_from_extra(item.get("extra") if isinstance(item, dict) else {})


def _resolve_managed_by(item: dict[str, Any], item_type: ItemType) -> str:
    declared = str(item.get("managed_by") or "").strip().lower()
    if declared in {"user", "system"}:
        return declared
    extra = item.get("extra") if isinstance(item.get("extra"), dict) else {}
    declared_extra = str((extra or {}).get("managed_by") or "").strip().lower()
    if declared_extra in {"user", "system"}:
        return declared_extra
    return "system" if item_type == ITEM_TYPE_SERVICE_AGGREGATED else "user"


def _attach_item_type(item: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(item or {})
    extra = enriched.get("extra")
    item_type = _resolve_item_type(enriched)
    managed_by = _resolve_managed_by(enriched, item_type)
    if isinstance(extra, dict):
        next_extra = dict(extra)
    else:
        next_extra = {}
    next_extra["item_type"] = item_type
    next_extra["managed_by"] = managed_by
    enriched["extra"] = next_extra
    enriched["item_type"] = item_type
    enriched["managed_by"] = managed_by
    return enriched


def _normalize_upsert_item_type(
    *,
    payload_item_type: ItemType,
    normalized_extra: dict[str, Any],
    allow_system_item_type: bool,
) -> ItemType:
    extra_item_type = str(normalized_extra.get("item_type") or "").strip().lower()
    requested_item_type = str(payload_item_type or ITEM_TYPE_USER_DEFINED).strip().lower()
    if extra_item_type in {ITEM_TYPE_USER_DEFINED, ITEM_TYPE_SERVICE_AGGREGATED} and extra_item_type != requested_item_type:
        raise HTTPException(
            status_code=400,
            detail=error_response(
                ErrorCode.INVALID_INPUT,
                "item_type conflict between payload.item_type and payload.extra.item_type",
            ),
        )
    if requested_item_type not in {ITEM_TYPE_USER_DEFINED, ITEM_TYPE_SERVICE_AGGREGATED}:
        raise HTTPException(
            status_code=400,
            detail=error_response(
                ErrorCode.INVALID_INPUT,
                "item_type must be one of: user_defined, service_aggregated",
            ),
        )
    if requested_item_type == ITEM_TYPE_SERVICE_AGGREGATED and not allow_system_item_type:
        raise HTTPException(
            status_code=403,
            detail=error_response(
                ErrorCode.INVALID_INPUT,
                "service_aggregated item_type is system-managed and cannot be written via user API",
            ),
        )
    normalized_extra["item_type"] = requested_item_type
    return requested_item_type  # keep explicit return for future internal branching


def _require_project_key(project_key: str | None) -> str:
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
        logger.warning("project_key_fallback_used endpoint=source_library resolved_project_key=%s", fallback)
        return fallback

    raise HTTPException(
        status_code=400,
        detail=error_response(
            ErrorCode.PROJECT_KEY_REQUIRED,
            "project_key is required. Please select a project first.",
        ),
    )


def _build_definition_response(item_payload: dict[str, Any]) -> dict[str, Any]:
    definition = dict(item_payload or {})
    definition["execution_plan"] = build_item_execution_plan(item_payload)
    return _attach_item_type(definition)


def _resolve_query_project_key(
    scope: ScopeType,
    project_key: str | None,
    *,
    request: Request | None = None,
) -> str | None:
    explicit = str(project_key or "").strip()
    if explicit:
        return explicit
    if request is not None:
        source = str(getattr(getattr(request, "state", None), "project_key_source", "") or "").strip().lower()
        resolved = str(getattr(getattr(request, "state", None), "project_key_resolved", "") or "").strip()
        if source in {"header", "query"} and resolved:
            return resolved
    resolved_scope = str(scope or "effective").strip().lower()
    if resolved_scope == "shared":
        return None
    return _require_project_key(None)


def _resolve_write_project_key(
    project_key: str | None,
    *,
    request: Request | None = None,
) -> str:
    explicit = str(project_key or "").strip()
    if explicit:
        return explicit
    if request is not None:
        source = str(getattr(getattr(request, "state", None), "project_key_source", "") or "").strip().lower()
        resolved = str(getattr(getattr(request, "state", None), "project_key_resolved", "") or "").strip()
        if source in {"header", "query"} and resolved:
            return resolved
    return _require_project_key(None)


@router.get("/channels")
def list_channels(
    request: Request,
    scope: ScopeType = Query(default="effective"),
    project_key: str | None = Query(default=None),
) -> dict:
    try:
        resolved_project_key = _resolve_query_project_key(scope, project_key, request=request)
        items = list_effective_channels(scope=scope, project_key=resolved_project_key)
    except Exception as exc:  # noqa: BLE001
        _raise_mapped_error(exc)
    return ok({"items": items, "scope": scope, "project_key": resolved_project_key})


@router.get("/items")
def list_items(
    request: Request,
    scope: ScopeType = Query(default="effective"),
    project_key: str | None = Query(default=None),
    item_type: ItemType | None = Query(default=None),
    include_system: bool = Query(default=False),
    include_execution_plan: bool = Query(default=False),
) -> dict:
    try:
        resolved_project_key = _resolve_query_project_key(scope, project_key, request=request)
        if include_execution_plan:
            raw_items = list_effective_items(scope=scope, project_key=resolved_project_key, include_execution_plan=True)
        else:
            raw_items = list_effective_items(scope=scope, project_key=resolved_project_key)
        allowed_item_types = {ITEM_TYPE_USER_DEFINED}
        if include_system:
            allowed_item_types.add(ITEM_TYPE_SERVICE_AGGREGATED)
        if item_type is not None and item_type not in allowed_item_types:
            raise HTTPException(
                status_code=400,
                detail=error_response(
                    ErrorCode.INVALID_INPUT,
                    "item_type=service_aggregated requires include_system=true",
                ),
            )
        selected_item_types = {item_type} if item_type is not None else allowed_item_types
        items = []
        for row in raw_items:
            enriched = _attach_item_type(row)
            resolved_item_type = str(enriched.get("item_type") or ITEM_TYPE_USER_DEFINED)
            if resolved_item_type in selected_item_types:
                items.append(enriched)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        _raise_mapped_error(exc)
    return ok(
        {
            "items": items,
            "scope": scope,
            "project_key": resolved_project_key,
            "item_type": item_type,
            "include_system": include_system,
            "include_execution_plan": include_execution_plan,
        }
    )


@router.get("/items/by_symbol")
def list_items_by_symbol_api(
    request: Request,
    scope: ScopeType = Query(default="effective"),
    project_key: str | None = Query(default=None),
) -> dict:
    """Items grouped by tag (symbol). For Phase 5 symbol clustering."""
    try:
        resolved_project_key = _resolve_query_project_key(scope, project_key, request=request)
        grouped = list_items_by_symbol(scope=scope, project_key=resolved_project_key)
    except Exception as exc:  # noqa: BLE001
        _raise_mapped_error(exc)
    return ok({"by_symbol": grouped, "scope": scope, "project_key": resolved_project_key})


@router.get("/channels/grouped")
def list_channels_grouped_api(
    request: Request,
    scope: ScopeType = Query(default="effective"),
    project_key: str | None = Query(default=None),
) -> dict:
    """Channels grouped by provider (tool type). For Phase 5 handler clustering."""
    try:
        resolved_project_key = _resolve_query_project_key(scope, project_key, request=request)
        grouped = list_channels_grouped_by_provider(scope=scope, project_key=resolved_project_key)
    except Exception as exc:  # noqa: BLE001
        _raise_mapped_error(exc)
    return ok({"by_provider": grouped, "scope": scope, "project_key": resolved_project_key})


@router.get("/items/grouped")
def list_items_grouped_api(
    request: Request,
    scope: ScopeType = Query(default="effective"),
    project_key: str | None = Query(default=None),
) -> dict:
    """Items grouped by resource parser handler (derived from bound site_entries.entry_type)."""
    try:
        resolved_project_key = _resolve_query_project_key(scope, project_key, request=request)
        items = list_effective_items(scope=scope, project_key=resolved_project_key)
        grouped: dict[str, list[dict]] = {}
        for it in items:
            for hk in _resource_handler_keys_for_item(it, project_key=resolved_project_key):
                grouped.setdefault(hk, []).append(it)
    except Exception as exc:  # noqa: BLE001
        _raise_mapped_error(exc)
    return ok({"by_handler": grouped, "scope": scope, "project_key": resolved_project_key})


def _resource_handler_keys_for_item(item: dict, *, project_key: str | None) -> list[str]:
    params = item.get("params") or {}
    if not isinstance(params, dict):
        params = {}
    execution_plan = item.get("execution_plan") if isinstance(item.get("execution_plan"), dict) else build_item_execution_plan(item)
    plan_urls = execution_plan.get("site_entry_urls") if isinstance(execution_plan, dict) else None
    urls: list[str] = []
    if isinstance(plan_urls, list):
        urls = [str(u).strip() for u in plan_urls if str(u).strip()]

    keys: list[str] = []
    if urls:
        from ..services.resource_pool.site_entries import get_site_entry_by_url

        for u in urls:
            entry = get_site_entry_by_url(scope="effective", project_key=project_key, site_url=u) or {}
            et = str(entry.get("entry_type") or "").strip().lower()
            if not et:
                su = str(u).lower()
                if "{{q}}" in su or "search" in su:
                    et = "search_template"
                elif "sitemap" in su:
                    et = "sitemap"
                elif "rss" in su or "feed" in su or "atom" in su:
                    et = "rss"
                else:
                    et = "domain_root"
            if et not in keys:
                keys.append(et)
        return keys

    # URL-pool routed item: URLs exist but per-URL parser will be resolved at runtime.
    raw_urls = params.get("urls") or []
    if isinstance(raw_urls, list) and any(str(x or "").strip() for x in raw_urls):
        return ["url_routing"]
    return []


def _normalize_item_site_entries(params: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    out = dict(params or {})
    raw = out.get("site_entries")
    if raw is None:
        raw = out.get("site_entry_urls")
    if raw is None:
        return out, []

    urls: list[str] = []
    if isinstance(raw, str):
        raw_list: list[Any] = [raw]
    elif isinstance(raw, list):
        raw_list = raw
    else:
        raw_list = []

    for x in raw_list:
        u = ""
        if isinstance(x, str):
            u = x.strip()
        elif isinstance(x, dict):
            u = str(x.get("site_url") or x.get("url") or "").strip()
        else:
            u = str(x or "").strip()
        norm = normalize_url(u)
        if norm and norm not in urls:
            urls.append(norm)

    out["site_entries"] = urls
    if "site_entry_urls" in out:
        out.pop("site_entry_urls", None)
    return out, urls


def _validate_handler_item_constraints(*, params: dict[str, Any], extra: dict[str, Any], project_key: str) -> None:
    extra = extra if isinstance(extra, dict) else {}
    creation_handler = str(extra.get("creation_handler") or extra.get("builder_handler") or "").strip()
    expected_entry_type = str(extra.get("expected_entry_type") or "").strip().lower()
    is_handler_item = creation_handler.startswith("handler") or bool(expected_entry_type)
    if not is_handler_item:
        return

    raw_site_entries = [
        *(params.get("site_entries") or [] if isinstance(params.get("site_entries"), list) else []),
        *(params.get("official_access_site_entries") or [] if isinstance(params.get("official_access_site_entries"), list) else []),
    ]
    if not raw_site_entries and not isinstance(params.get("site_entries"), list):
        raise ValueError("handler-built item requires params.site_entries to be a list")
    if not raw_site_entries:
        raise ValueError("handler-built item requires non-empty params.site_entries")
    if not expected_entry_type:
        raise ValueError("handler-built item requires extra.expected_entry_type")

    mismatches: list[str] = []
    for u in raw_site_entries:
        entry = get_site_entry_by_url(scope="effective", project_key=project_key, site_url=str(u)) or {}
        et = str(entry.get("entry_type") or "").strip().lower()
        if et and et != expected_entry_type:
            mismatches.append(f"{u}({et})")
    if mismatches:
        raise ValueError(
            f"handler-built item site_entries must all match expected_entry_type={expected_entry_type}; "
            f"mismatches={', '.join(mismatches[:8])}"
        )


def _refresh_handler_item_site_entries(*, row: SourceLibraryItem, project_key: str, incremental: bool, max_site_entries: int) -> dict[str, Any]:
    extra = row.extra or {}
    params = row.params or {}
    if not isinstance(extra, dict):
        extra = {}
    if not isinstance(params, dict):
        params = {}

    expected_entry_type = str(extra.get("expected_entry_type") or "").strip().lower()
    if not expected_entry_type:
        raise ValueError("item.extra.expected_entry_type is required for handler refresh")

    # Optional automated filters stored in item.extra
    domains = extra.get("domains") or []
    if isinstance(domains, str):
        domains = [domains]
    domains = [str(x).strip().lower() for x in domains if str(x or "").strip()]

    tag_filters = extra.get("site_entry_tags") or []
    if isinstance(tag_filters, str):
        tag_filters = [tag_filters]
    tag_filters = [str(x).strip().lower() for x in tag_filters if str(x or "").strip()]

    page = 1
    candidates: list[str] = []
    while len(candidates) < max_site_entries:
        items, total = list_site_entries(
            scope="effective",
            project_key=project_key,
            entry_type=expected_entry_type,
            enabled=True,
            page=page,
            page_size=min(100, max_site_entries),
        )
        for ent in items:
            u = str(ent.get("site_url") or "").strip()
            d = str(ent.get("domain") or "").strip().lower()
            tags = [str(t).strip().lower() for t in (ent.get("tags") or []) if str(t or "").strip()]
            if domains and d not in domains:
                continue
            if tag_filters and not any(t in tags for t in tag_filters):
                continue
            if u and u not in candidates:
                candidates.append(u)
            if len(candidates) >= max_site_entries:
                break
        if not items or len(candidates) >= max_site_entries or (page * min(100, max_site_entries) >= total):
            break
        page += 1

    norm_params, old_urls = _normalize_item_site_entries(params)
    if incremental:
        merged = list(old_urls)
        for u in candidates:
            if u not in merged:
                merged.append(u)
        new_urls = merged
    else:
        new_urls = candidates
    norm_params["site_entries"] = new_urls
    row.params = norm_params
    return {
        "item_key": row.item_key,
        "expected_entry_type": expected_entry_type,
        "incremental": incremental,
        "domains": domains,
        "site_entry_tags": tag_filters,
        "site_entries_before": len(old_urls),
        "site_entries_after": len(new_urls),
        "added": max(0, len(new_urls) - len(old_urls)) if incremental else len([u for u in new_urls if u not in old_urls]),
    }


@router.post("/items")
def upsert_project_item(
    payload: SourceLibraryItemUpsertPayload,
    request: Request,
    project_key: str | None = Query(default=None),
) -> dict:
    try:
        resolved_project_key = _resolve_write_project_key(project_key, request=request)
        norm_params, _ = _normalize_item_site_entries(payload.params or {})
        normalized_extra = _normalize_source_item_capability(payload.extra or {})
        normalized_extra = normalize_external_project_extra(
            normalized_extra,
            item_key=payload.item_key,
            display_name=payload.name,
            channel_key=payload.channel_key,
        )
        resolved_item_type = _normalize_upsert_item_type(
            payload_item_type=payload.item_type,
            normalized_extra=normalized_extra,
            allow_system_item_type=False,
        )
        channel_key = str(payload.channel_key or "").strip().lower()
        if resolved_item_type == ITEM_TYPE_USER_DEFINED and channel_key.startswith("generic_web."):
            raise HTTPException(
                status_code=400,
                detail=error_response(
                    ErrorCode.INVALID_INPUT,
                    "generic_web.* is internal adapter-only and cannot be directly created as user_defined item",
                ),
            )
        if channel_key == EXTERNAL_PROJECT_CHANNEL_KEY and "external_project_manifest" not in normalized_extra:
            raise HTTPException(
                status_code=400,
                detail=error_response(
                    ErrorCode.INVALID_INPUT,
                    f"{EXTERNAL_PROJECT_CHANNEL_KEY} requires payload.extra.external_project_manifest",
                ),
            )
        _validate_handler_item_constraints(
            params=norm_params,
            extra=normalized_extra,
            project_key=resolved_project_key,
        )
        with bind_project(resolved_project_key):
            with SessionLocal() as session:
                row = session.execute(
                    select(SourceLibraryItem).where(SourceLibraryItem.item_key == payload.item_key)
                ).scalar_one_or_none()
                if row is None:
                    row = SourceLibraryItem(item_key=payload.item_key)
                    session.add(row)

                row.name = payload.name
                row.channel_key = payload.channel_key
                row.description = payload.description
                row.params = norm_params
                row.tags = payload.tags
                row.schedule = payload.schedule
                row.extends_item_key = payload.extends_item_key
                if hasattr(row, "item_type"):
                    row.item_type = resolved_item_type
                if hasattr(row, "managed_by"):
                    row.managed_by = "system" if resolved_item_type == ITEM_TYPE_SERVICE_AGGREGATED else "user"
                row.enabled = payload.enabled
                row.extra = normalized_extra
                session.commit()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        _raise_mapped_error(exc)

    return ok({"item_key": payload.item_key, "project_key": resolved_project_key, "ok": True})


@router.post("/external-projects/register")
def register_external_project(
    payload: ExternalProjectRegistrationPayload,
    request: Request,
    project_key: str | None = Query(default=None),
) -> dict:
    try:
        resolved_project_key = _resolve_write_project_key(project_key, request=request)
        item_payload = synthesize_external_project_item(
            project_link=payload.project_link,
            item_key=payload.item_key,
            display_name=payload.name,
            description=payload.description,
            tags=payload.tags,
            hints=payload.hints,
        )
        item_payload["enabled"] = bool(payload.enabled)
        registration_context = dict(item_payload.get("registration_context") or {})
        manifest = get_external_project_manifest(
            item_payload.get("extra") if isinstance(item_payload.get("extra"), dict) else {},
            item_key=str(item_payload.get("item_key") or "").strip() or None,
            display_name=str(item_payload.get("name") or "").strip() or None,
        )
        if manifest is not None and "provider_binding" not in registration_context:
            registration_context["provider_binding"] = dict((manifest.get("provider_binding") or {}))
        item_payload["registration_context"] = registration_context
        item_response = _build_definition_response(item_payload)
        if not payload.persist:
            return ok(
                {
                    "ok": True,
                    "persisted": False,
                    "project_key": resolved_project_key,
                    "item": item_response,
                    "registration_context": registration_context,
                    "manifest_summary": build_external_project_summary(manifest),
                }
            )

        upsert_payload = SourceLibraryItemUpsertPayload(
            item_key=str(item_payload.get("item_key") or ""),
            name=str(item_payload.get("name") or ""),
            channel_key=str(item_payload.get("channel_key") or ""),
            description=str(item_payload.get("description") or ""),
            params=dict(item_payload.get("params") or {}),
            tags=list(item_payload.get("tags") or []),
            enabled=bool(item_payload.get("enabled", True)),
            item_type=ITEM_TYPE_USER_DEFINED,
            extra=dict(item_payload.get("extra") or {}),
        )
        upsert_project_item(payload=upsert_payload, project_key=resolved_project_key)
        return ok(
            {
                "ok": True,
                "persisted": True,
                "project_key": resolved_project_key,
                "item": item_response,
                "registration_context": registration_context,
                "manifest_summary": build_external_project_summary(manifest),
            }
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        _raise_mapped_error(exc)


@router.put("/items/{item_key}")
def update_project_item(
    item_key: str,
    payload: SourceLibraryItemUpsertPayload,
    request: Request,
    project_key: str | None = Query(default=None),
) -> dict:
    payload_item_key = str(payload.item_key or "").strip()
    if payload_item_key != str(item_key or "").strip():
        raise HTTPException(
            status_code=400,
            detail=error_response(
                ErrorCode.INVALID_INPUT,
                "path item_key must equal payload.item_key",
            ),
        )
    return upsert_project_item(payload=payload, request=request, project_key=project_key)


@router.post("/items/{item_key}/refresh")
def refresh_item(item_key: str, payload: RefreshItemPayload, request: Request) -> dict:
    try:
        project_key = _resolve_write_project_key(payload.project_key, request=request)
        with bind_project(project_key):
            with SessionLocal() as session:
                row = session.execute(
                    select(SourceLibraryItem).where(SourceLibraryItem.item_key == item_key)
                ).scalar_one_or_none()
                if row is None:
                    raise HTTPException(
                        status_code=404,
                        detail=error_response(
                            ErrorCode.NOT_FOUND,
                            f"item not found: {item_key}",
                            details={"item_key": item_key},
                        ),
                    )
                result = _refresh_handler_item_site_entries(
                    row=row,
                    project_key=project_key,
                    incremental=bool(payload.incremental),
                    max_site_entries=int(payload.max_site_entries),
                )
                _validate_handler_item_constraints(
                    params=row.params or {},
                    extra=row.extra or {},
                    project_key=project_key,
                )
                session.commit()
                return ok({"ok": True, "project_key": project_key, **result})
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        _raise_mapped_error(exc)


@router.post("/handler_clusters/sync")
def sync_handler_clusters(payload: SyncHandlerClustersPayload, request: Request) -> dict:
    try:
        project_key = _resolve_write_project_key(payload.project_key, request=request)

        requested = [str(x).strip().lower() for x in (payload.handlers or []) if str(x or "").strip()]
        requested_set = set(requested)

        page = 1
        page_size = 200
        entry_types: set[str] = set()
        while True:
            rows, total = list_site_entries(
                scope="effective",
                project_key=project_key,
                enabled=True,
                page=page,
                page_size=page_size,
            )
            for r in rows:
                et = str(r.get("entry_type") or "").strip().lower()
                if not et:
                    continue
                if et == "url_routing":
                    continue
                if requested_set and et not in requested_set:
                    continue
                entry_types.add(et)
            if not rows or page * page_size >= int(total or 0):
                break
            page += 1

        processed: list[dict[str, Any]] = []
        with bind_project(project_key):
            with SessionLocal() as session:
                for handler_key in sorted(entry_types):
                    item_key = f"handler.cluster.{handler_key}"
                    row = session.execute(
                        select(SourceLibraryItem).where(SourceLibraryItem.item_key == item_key)
                    ).scalar_one_or_none()
                    if row is None:
                        row = SourceLibraryItem(item_key=item_key)
                        session.add(row)
                        row.name = f"Handler Cluster {handler_key}"
                        row.channel_key = "handler.cluster"
                        row.enabled = True
                        row.tags = ["handler_cluster", handler_key]
                    else:
                        row.name = row.name or f"Handler Cluster {handler_key}"
                        row.channel_key = row.channel_key or "handler.cluster"
                        row.enabled = row.enabled is not False
                        row.tags = list(dict.fromkeys([*(row.tags or []), "handler_cluster", handler_key]))

                    extra = row.extra if isinstance(row.extra, dict) else {}
                    extra = dict(extra)
                    extra["creation_handler"] = "handler.entry_type"
                    extra["expected_entry_type"] = handler_key
                    extra["stable_handler_cluster"] = True
                    extra["item_type"] = ITEM_TYPE_SERVICE_AGGREGATED
                    extra["managed_by"] = "system"
                    if extra.get("auto_maintain") is None:
                        extra["auto_maintain"] = True
                    row.extra = extra
                    if hasattr(row, "item_type"):
                        row.item_type = ITEM_TYPE_SERVICE_AGGREGATED
                    if hasattr(row, "managed_by"):
                        row.managed_by = "system"

                    params = row.params if isinstance(row.params, dict) else {}
                    params = dict(params)
                    params["expected_entry_type"] = handler_key
                    if not isinstance(params.get("site_entries"), list):
                        params["site_entries"] = []
                    row.params = params

                    refresh_result = _refresh_handler_item_site_entries(
                        row=row,
                        project_key=project_key,
                        incremental=bool(payload.incremental),
                        max_site_entries=int(payload.max_site_entries),
                    )
                    _validate_handler_item_constraints(
                        params=row.params or {},
                        extra=row.extra or {},
                        project_key=project_key,
                    )
                    processed.append(
                        {
                            "handler_key": handler_key,
                            "item_key": item_key,
                            **refresh_result,
                        }
                    )
                session.commit()

        return ok(
            {
                "ok": True,
                "project_key": project_key,
                "handler_count": len(processed),
                "results": processed,
            }
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        _raise_mapped_error(exc)


@router.post("/sync_shared_from_files")
def sync_shared_from_files(request: Request, project_key: str | None = Query(default=None)) -> dict:
    try:
        resolved_project_key = _resolve_write_project_key(project_key, request=request)
        with bind_project(resolved_project_key):
            result = sync_shared_library_from_files()
            return ok({"ok": True, "project_key": resolved_project_key, **result})
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        _raise_mapped_error(exc)
