from __future__ import annotations

from typing import Literal, TypeGuard

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..contracts import ErrorCode, error_response
from ..contracts.responses import ok
from ..services.projects import bind_project
from ..services.source_library import (
    list_channels_grouped_by_provider,
    list_effective_channels,
    list_effective_items,
    list_items_by_symbol,
    sync_shared_library_from_files,
)
from ..services.source_library.external_project import (
    build_external_project_summary,
    get_external_project_manifest,
    normalize_external_project_extra,
)
from ..services.source_library.external_integration import IntegrationSpec
from ..services.source_library.external_project_registration import synthesize_external_project_item
from ..services.source_library.item_plan import build_item_execution_plan
from ..services.source_library.item_writer import (
    ITEM_TYPE_SERVICE_AGGREGATED,
    ITEM_TYPE_USER_DEFINED,
    ItemType,
    SourceLibraryItemUpsertPayload,
    SourceLibraryJsonObject,
    SourceLibraryJsonValue,
    raise_mapped_error as _raise_mapped_error,
    refresh_project_item as _refresh_project_item,
    require_project_key as _require_project_key,
    sync_handler_cluster_items as _sync_handler_cluster_items,
    source_library_json_object as _json_object,
    upsert_project_item as _write_project_item,
)
from ..services.source_library.types import resolve_source_library_item_markers

ScopeType = Literal["shared", "project", "effective"]

router = APIRouter(prefix="/source_library", tags=["source_library"])


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
    hints: SourceLibraryJsonObject = Field(default_factory=dict)


def _attach_item_type(item: SourceLibraryJsonObject) -> SourceLibraryJsonObject:
    enriched = dict(item)
    extra = enriched.get("extra")
    if isinstance(extra, dict):
        next_extra: SourceLibraryJsonObject = dict(extra)
    else:
        next_extra = {}
    item_type, managed_by = resolve_source_library_item_markers(
        item_type=enriched.get("item_type"),
        managed_by=enriched.get("managed_by"),
        item_key=enriched.get("item_key"),
        channel_key=enriched.get("channel_key"),
        extra=next_extra,
    )
    next_extra["item_type"] = item_type
    next_extra["managed_by"] = managed_by
    enriched["extra"] = next_extra
    enriched["item_type"] = item_type
    enriched["managed_by"] = managed_by
    return enriched


def _build_definition_response(
    item_payload: SourceLibraryJsonObject,
) -> SourceLibraryJsonObject:
    definition = dict(item_payload)
    plan_input: dict[str, object] = {key: value for key, value in item_payload.items()}
    definition["execution_plan"] = _json_object(
        build_item_execution_plan(plan_input),
        path="source_library.execution_plan",
    )
    return _attach_item_type(definition)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _string_list(value: object) -> list[str]:
    if not _is_object_list(value):
        return []
    return [item for item in value if isinstance(item, str)]


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
) -> SourceLibraryJsonObject:
    try:
        resolved_project_key = _resolve_query_project_key(scope, project_key, request=request)
        raw_items = list_effective_channels(scope=scope, project_key=resolved_project_key)
        items: list[SourceLibraryJsonValue] = [
            _json_object(
                raw_item,
                path=f"source_library.channels[{index}]",
            )
            for index, raw_item in enumerate(raw_items)
        ]
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
) -> SourceLibraryJsonObject:
    try:
        resolved_project_key = _resolve_query_project_key(scope, project_key, request=request)
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
        if include_execution_plan:
            service_items = list_effective_items(
                scope=scope,
                project_key=resolved_project_key,
                include_execution_plan=True,
            )
        else:
            service_items = list_effective_items(
                scope=scope,
                project_key=resolved_project_key,
            )
        raw_items = [
            _json_object(
                raw_item,
                path=f"source_library.items[{index}]",
            )
            for index, raw_item in enumerate(service_items)
        ]
        selected_item_types = {item_type} if item_type is not None else allowed_item_types
        items: list[SourceLibraryJsonValue] = []
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
) -> SourceLibraryJsonObject:
    """Items grouped by tag (symbol). For Phase 5 symbol clustering."""
    try:
        resolved_project_key = _resolve_query_project_key(scope, project_key, request=request)
        grouped = _json_object(
            list_items_by_symbol(scope=scope, project_key=resolved_project_key),
            path="source_library.items_by_symbol",
        )
    except Exception as exc:  # noqa: BLE001
        _raise_mapped_error(exc)
    return ok({"by_symbol": grouped, "scope": scope, "project_key": resolved_project_key})


@router.get("/channels/grouped")
def list_channels_grouped_api(
    request: Request,
    scope: ScopeType = Query(default="effective"),
    project_key: str | None = Query(default=None),
) -> SourceLibraryJsonObject:
    """Channels grouped by provider (tool type). For Phase 5 handler clustering."""
    try:
        resolved_project_key = _resolve_query_project_key(scope, project_key, request=request)
        grouped = _json_object(
            list_channels_grouped_by_provider(
                scope=scope,
                project_key=resolved_project_key,
            ),
            path="source_library.channels_by_provider",
        )
    except Exception as exc:  # noqa: BLE001
        _raise_mapped_error(exc)
    return ok({"by_provider": grouped, "scope": scope, "project_key": resolved_project_key})


@router.get("/items/grouped")
def list_items_grouped_api(
    request: Request,
    scope: ScopeType = Query(default="effective"),
    project_key: str | None = Query(default=None),
) -> SourceLibraryJsonObject:
    """Items grouped by resource parser handler (derived from bound site_entries.entry_type)."""
    try:
        resolved_project_key = _resolve_query_project_key(scope, project_key, request=request)
        raw_items = list_effective_items(scope=scope, project_key=resolved_project_key)
        items = [
            _json_object(
                raw_item,
                path=f"source_library.grouped_items[{index}]",
            )
            for index, raw_item in enumerate(raw_items)
        ]
        grouped: dict[str, SourceLibraryJsonValue] = {}
        for item in items:
            for handler_key in _resource_handler_keys_for_item(
                item,
                project_key=resolved_project_key,
            ):
                grouped_items = grouped.setdefault(handler_key, [])
                if isinstance(grouped_items, list):
                    grouped_items.append(item)
    except Exception as exc:  # noqa: BLE001
        _raise_mapped_error(exc)
    return ok({"by_handler": grouped, "scope": scope, "project_key": resolved_project_key})


def _resource_handler_keys_for_item(
    item: SourceLibraryJsonObject,
    *,
    project_key: str | None,
) -> list[str]:
    raw_params = item.get("params")
    params = raw_params if isinstance(raw_params, dict) else {}
    raw_execution_plan = item.get("execution_plan")
    plan_input: dict[str, object] = {key: value for key, value in item.items()}
    execution_plan = (
        raw_execution_plan
        if isinstance(raw_execution_plan, dict)
        else _json_object(
            build_item_execution_plan(plan_input),
            path="source_library.execution_plan",
        )
    )
    plan_urls = execution_plan.get("site_entry_urls")
    urls: list[str] = []
    if isinstance(plan_urls, list):
        urls = [url.strip() for url in plan_urls if isinstance(url, str) and url.strip()]

    keys: list[str] = []
    if urls:
        from ..services.resource_pool.site_entries import get_site_entry_by_url

        for u in urls:
            entry = _json_object(
                get_site_entry_by_url(
                    scope="effective",
                    project_key=project_key,
                    site_url=u,
                )
                or {},
                path="source_library.site_entry",
            )
            raw_entry_type = entry.get("entry_type")
            et = raw_entry_type.strip().lower() if isinstance(raw_entry_type, str) else ""
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
    raw_urls = params.get("urls")
    if isinstance(raw_urls, list) and any(
        isinstance(url, str) and bool(url.strip()) for url in raw_urls
    ):
        return ["url_routing"]
    return []


@router.post("/items")
def upsert_project_item(
    payload: SourceLibraryItemUpsertPayload,
    request: Request,
    project_key: str | None = Query(default=None),
) -> dict[str, object]:
    try:
        resolved_project_key = _resolve_write_project_key(project_key, request=request)
        return _write_project_item(payload=payload, project_key=resolved_project_key)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        _raise_mapped_error(exc)

@router.get("/external-projects/integration-schema")
def external_integration_schema() -> dict[str, object]:
    return ok(IntegrationSpec.model_json_schema())


@router.post("/external-projects/prepare-integration")
async def prepare_external_integration(
    request: Request,
    project_key: str | None = Query(default=None),
) -> dict[str, object]:
    """Validate a declared spec without Cell synthesis, persistence or execution."""
    resolved_project_key = _resolve_write_project_key(project_key, request=request)
    try:
        # Parse here so FastAPI's general validation handler cannot echo secrets
        # from rejected credentials. The schema is exposed by the adjacent GET.
        spec = IntegrationSpec.model_validate(await request.json())
        item = _json_object(spec.to_mrw_item(), path="source_library.integration_item")
        raw_extra = item["extra"]
        item["extra"] = _json_object(normalize_external_project_extra(
            raw_extra if isinstance(raw_extra, dict) else {},
            item_key=spec.item_key, display_name=spec.name,
            channel_key="external_project.manifest", project_key=resolved_project_key,
        ), path="source_library.integration_extra")
    except ValueError:
        raise HTTPException(status_code=422, detail=error_response(
            ErrorCode.INVALID_INPUT, "Invalid integration specification or project binding",
        )) from None
    return ok({"item": item, "readiness": spec.integration.readiness(), "persisted": False})


@router.post("/external-projects/register")
def register_external_project(
    payload: ExternalProjectRegistrationPayload,
    request: Request,
    project_key: str | None = Query(default=None),
) -> SourceLibraryJsonObject:
    try:
        resolved_project_key = _resolve_write_project_key(project_key, request=request)
        item_payload = _json_object(
            synthesize_external_project_item(
                project_link=payload.project_link,
                item_key=payload.item_key,
                display_name=payload.name,
                description=payload.description,
                tags=payload.tags,
                hints=payload.hints,
            ),
            path="source_library.external_project_item",
        )
        item_payload["enabled"] = bool(payload.enabled)
        raw_registration_context = item_payload.get("registration_context")
        registration_context = _json_object(
            raw_registration_context if isinstance(raw_registration_context, dict) else {},
            path="source_library.registration_context",
        )
        raw_extra = item_payload.get("extra")
        manifest_extra: dict[str, object] = (
            {key: value for key, value in raw_extra.items()} if isinstance(raw_extra, dict) else {}
        )
        raw_manifest = get_external_project_manifest(
            manifest_extra,
            item_key=str(item_payload.get("item_key") or "").strip() or None,
            display_name=str(item_payload.get("name") or "").strip() or None,
        )
        manifest = (
            _json_object(raw_manifest, path="source_library.external_project_manifest")
            if raw_manifest is not None
            else None
        )
        if manifest is not None and "provider_binding" not in registration_context:
            raw_provider_binding = manifest.get("provider_binding")
            registration_context["provider_binding"] = _json_object(
                raw_provider_binding if isinstance(raw_provider_binding, dict) else {},
                path="source_library.provider_binding",
            )
        item_payload["registration_context"] = registration_context
        item_response = _build_definition_response(item_payload)
        raw_manifest_summary = build_external_project_summary(raw_manifest)
        manifest_summary = (
            _json_object(raw_manifest_summary, path="source_library.manifest_summary")
            if raw_manifest_summary is not None
            else None
        )
        if not payload.persist:
            return ok(
                {
                    "ok": True,
                    "persisted": False,
                    "project_key": resolved_project_key,
                    "item": item_response,
                    "registration_context": registration_context,
                    "manifest_summary": manifest_summary,
                }
            )

        raw_params = item_payload.get("params")
        upsert_payload = SourceLibraryItemUpsertPayload(
            item_key=str(item_payload.get("item_key") or ""),
            name=str(item_payload.get("name") or ""),
            channel_key=str(item_payload.get("channel_key") or ""),
            description=str(item_payload.get("description") or ""),
            params=_json_object(
                raw_params if isinstance(raw_params, dict) else {},
                path="source_library.params",
            ),
            tags=_string_list(item_payload.get("tags")),
            enabled=bool(item_payload.get("enabled", True)),
            item_type=ITEM_TYPE_USER_DEFINED,
            extra=_json_object(
                raw_extra if isinstance(raw_extra, dict) else {},
                path="source_library.extra",
            ),
        )
        _write_project_item(payload=upsert_payload, project_key=resolved_project_key)
        return ok(
            {
                "ok": True,
                "persisted": True,
                "project_key": resolved_project_key,
                "item": item_response,
                "registration_context": registration_context,
                "manifest_summary": manifest_summary,
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
) -> dict[str, object]:
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
def refresh_item(
    item_key: str,
    payload: RefreshItemPayload,
    request: Request,
) -> dict[str, object]:
    try:
        project_key = _resolve_write_project_key(payload.project_key, request=request)
        return _refresh_project_item(
            item_key=item_key,
            project_key=project_key,
            incremental=payload.incremental,
            max_site_entries=payload.max_site_entries,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        _raise_mapped_error(exc)


@router.post("/handler_clusters/sync")
def sync_handler_clusters(
    payload: SyncHandlerClustersPayload,
    request: Request,
) -> dict[str, object]:
    try:
        project_key = _resolve_write_project_key(payload.project_key, request=request)
        return _sync_handler_cluster_items(
            project_key=project_key,
            handlers=payload.handlers,
            incremental=payload.incremental,
            max_site_entries=payload.max_site_entries,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        _raise_mapped_error(exc)


@router.post("/sync_shared_from_files")
def sync_shared_from_files(
    request: Request,
    project_key: str | None = Query(default=None),
) -> SourceLibraryJsonObject:
    try:
        resolved_project_key = _resolve_write_project_key(project_key, request=request)
        with bind_project(resolved_project_key):
            result = _json_object(
                sync_shared_library_from_files(),
                path="source_library.sync_shared",
            )
            return ok({"ok": True, "project_key": resolved_project_key, **result})
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        _raise_mapped_error(exc)
