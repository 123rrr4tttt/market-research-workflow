from __future__ import annotations

import logging
from typing import Any, Dict, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..contracts import ErrorCode, error_response
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
    run_item_by_key,
    sync_shared_library_from_files,
)
from ..services.tasks import task_run_source_library_item
from ..settings.config import settings

ScopeType = Literal["shared", "project", "effective"]

router = APIRouter(prefix="/source_library", tags=["source_library"])
logger = logging.getLogger(__name__)


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
    extra: Dict[str, Any] = Field(default_factory=dict)


class RunItemPayload(BaseModel):
    project_key: str | None = None
    async_mode: bool = False
    override_params: Dict[str, Any] = Field(default_factory=dict)


class RefreshItemPayload(BaseModel):
    project_key: str
    incremental: bool = True
    max_site_entries: int = Field(default=500, ge=1, le=5000)


class SyncHandlerClustersPayload(BaseModel):
    project_key: str
    handlers: list[str] | None = None
    incremental: bool = True
    max_site_entries: int = Field(default=500, ge=1, le=5000)


def _require_project_key(project_key: str | None) -> str:
    key = (project_key or "").strip()
    if key:
        return key

    enforcement_mode = str(getattr(settings, "project_key_enforcement_mode", "warn")).strip().lower()
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


@router.get("/channels")
def list_channels(
    scope: ScopeType = Query(default="effective"),
    project_key: str | None = Query(default=None),
) -> dict:
    try:
        items = list_effective_channels(scope=scope, project_key=project_key)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"items": items, "scope": scope, "project_key": project_key}


@router.get("/items")
def list_items(
    scope: ScopeType = Query(default="effective"),
    project_key: str | None = Query(default=None),
) -> dict:
    try:
        items = list_effective_items(scope=scope, project_key=project_key)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"items": items, "scope": scope, "project_key": project_key}


@router.get("/items/by_symbol")
def list_items_by_symbol_api(
    scope: ScopeType = Query(default="effective"),
    project_key: str | None = Query(default=None),
) -> dict:
    """Items grouped by tag (symbol). For Phase 5 symbol clustering."""
    try:
        grouped = list_items_by_symbol(scope=scope, project_key=project_key)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"by_symbol": grouped, "scope": scope, "project_key": project_key}


@router.get("/channels/grouped")
def list_channels_grouped_api(
    scope: ScopeType = Query(default="effective"),
    project_key: str | None = Query(default=None),
) -> dict:
    """Channels grouped by provider (tool type). For Phase 5 handler clustering."""
    try:
        grouped = list_channels_grouped_by_provider(scope=scope, project_key=project_key)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"by_provider": grouped, "scope": scope, "project_key": project_key}


@router.get("/items/grouped")
def list_items_grouped_api(
    scope: ScopeType = Query(default="effective"),
    project_key: str | None = Query(default=None),
) -> dict:
    """Items grouped by resource parser handler (derived from bound site_entries.entry_type)."""
    try:
        items = list_effective_items(scope=scope, project_key=project_key)
        grouped: dict[str, list[dict]] = {}
        for it in items:
            for hk in _resource_handler_keys_for_item(it, project_key=project_key):
                grouped.setdefault(hk, []).append(it)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"by_handler": grouped, "scope": scope, "project_key": project_key}


def _resource_handler_keys_for_item(item: dict, *, project_key: str | None) -> list[str]:
    params = item.get("params") or {}
    if not isinstance(params, dict):
        return []
    raw_entries = params.get("site_entries") or params.get("site_entry_urls") or []
    urls: list[str] = []
    if isinstance(raw_entries, list):
        for x in raw_entries:
            if isinstance(x, str) and x.strip():
                urls.append(x.strip())
            elif isinstance(x, dict):
                u = str(x.get("site_url") or x.get("url") or "").strip()
                if u:
                    urls.append(u)
    elif isinstance(raw_entries, str) and raw_entries.strip():
        urls.append(raw_entries.strip())

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

    site_entries = params.get("site_entries") or []
    if not isinstance(site_entries, list):
        raise ValueError("handler-built item requires params.site_entries to be a list")
    if not site_entries:
        raise ValueError("handler-built item requires non-empty params.site_entries")
    if not expected_entry_type:
        raise ValueError("handler-built item requires extra.expected_entry_type")

    mismatches: list[str] = []
    for u in site_entries:
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
def upsert_project_item(payload: SourceLibraryItemUpsertPayload, project_key: str) -> dict:
    try:
        norm_params, _ = _normalize_item_site_entries(payload.params or {})
        _validate_handler_item_constraints(
            params=norm_params,
            extra=payload.extra or {},
            project_key=project_key,
        )
        with bind_project(project_key):
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
                row.enabled = payload.enabled
                row.extra = payload.extra
                session.commit()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"item_key": payload.item_key, "project_key": project_key, "ok": True}


@router.post("/items/{item_key}/refresh")
def refresh_item(item_key: str, payload: RefreshItemPayload) -> dict:
    try:
        project_key = str(payload.project_key or "").strip()
        if not project_key:
            raise HTTPException(status_code=400, detail="project_key is required.")
        with bind_project(project_key):
            with SessionLocal() as session:
                row = session.execute(
                    select(SourceLibraryItem).where(SourceLibraryItem.item_key == item_key)
                ).scalar_one_or_none()
                if row is None:
                    raise HTTPException(status_code=404, detail=f"item not found: {item_key}")
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
                return {"ok": True, "project_key": project_key, **result}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/handler_clusters/sync")
def sync_handler_clusters(payload: SyncHandlerClustersPayload) -> dict:
    try:
        project_key = str(payload.project_key or "").strip()
        if not project_key:
            raise HTTPException(status_code=400, detail="project_key is required.")

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
                    if extra.get("auto_maintain") is None:
                        extra["auto_maintain"] = True
                    row.extra = extra

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

        return {
            "ok": True,
            "project_key": project_key,
            "handler_count": len(processed),
            "results": processed,
        }
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/items/{item_key}/run")
def run_item(item_key: str, payload: RunItemPayload) -> dict:
    try:
        project_key = _require_project_key(payload.project_key)
        if payload.async_mode:
            task = task_run_source_library_item.delay(
                item_key,
                project_key,
                payload.override_params or {},
            )
            return {"task_id": task.id, "async": True, "item_key": item_key}

        result = run_item_by_key(
            item_key=item_key,
            project_key=project_key,
            override_params=payload.override_params or {},
        )
        return {"async": False, **result}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sync_shared_from_files")
def sync_shared_from_files(project_key: str | None = None) -> dict:
    try:
        resolved_project_key = _require_project_key(project_key)
        with bind_project(resolved_project_key):
            result = sync_shared_library_from_files()
            return {"ok": True, "project_key": resolved_project_key, **result}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
