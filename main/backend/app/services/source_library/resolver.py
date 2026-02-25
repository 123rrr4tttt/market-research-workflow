from __future__ import annotations

from contextlib import nullcontext
from typing import Any, Dict, List

from sqlalchemy import select

from ...models.base import SessionLocal
from ...models.entities import (
    IngestChannel,
    SharedIngestChannel,
    SharedSourceLibraryItem,
    SourceLibraryItem,
)
from ..projects import bind_project, bind_schema
from .loader import load_project_library_files
from .runner import run_channel


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _as_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    return {}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _channel_row_to_dict(row: Any, scope: str) -> Dict[str, Any]:
    return {
        "channel_key": row.channel_key,
        "name": row.name,
        "kind": row.kind,
        "provider": row.provider,
        "description": row.description,
        "credential_refs": _as_list(row.credential_refs),
        "default_params": _as_dict(row.default_params),
        "param_schema": _as_dict(row.param_schema),
        "extends_channel_key": row.extends_channel_key,
        "enabled": bool(row.enabled),
        "extra": _as_dict(row.extra),
        "scope": scope,
    }


def _item_row_to_dict(row: Any, scope: str) -> Dict[str, Any]:
    return {
        "item_key": row.item_key,
        "name": row.name,
        "channel_key": row.channel_key,
        "description": row.description,
        "params": _as_dict(row.params),
        "tags": _as_list(row.tags),
        "schedule": row.schedule,
        "extends_item_key": row.extends_item_key,
        "enabled": bool(row.enabled),
        "extra": _as_dict(row.extra),
        "scope": scope,
    }


def _load_shared_channels() -> List[Dict[str, Any]]:
    with bind_schema("public"):
        with SessionLocal() as session:
            rows = session.execute(select(SharedIngestChannel).order_by(SharedIngestChannel.id.asc())).scalars().all()
            return [_channel_row_to_dict(row, "shared") for row in rows]


def _load_project_channels(project_key: str | None) -> List[Dict[str, Any]]:
    file_rows: list[dict[str, Any]] = []
    file_data = load_project_library_files(project_key)
    for payload in file_data.get("channels", []):
        channel_key = str(payload.get("channel_key", "")).strip()
        if not channel_key:
            continue
        file_rows.append(
            {
                "channel_key": channel_key,
                "name": str(payload.get("name") or channel_key),
                "kind": str(payload.get("kind") or "unknown"),
                "provider": str(payload.get("provider") or "unknown"),
                "description": payload.get("description"),
                "credential_refs": _as_list(payload.get("credential_refs")),
                "default_params": _as_dict(payload.get("default_params")),
                "param_schema": _as_dict(payload.get("param_schema")),
                "extends_channel_key": payload.get("extends_channel_key"),
                "enabled": bool(payload.get("enabled", True)),
                "extra": _as_dict(payload.get("extra")),
                "scope": "project",
            }
        )
    if not project_key:
        return file_rows
    with bind_project(project_key):
        with SessionLocal() as session:
            rows = session.execute(select(IngestChannel).order_by(IngestChannel.id.asc())).scalars().all()
            db_rows = [_channel_row_to_dict(row, "project") for row in rows]
            return [*file_rows, *db_rows]


def _load_shared_items() -> List[Dict[str, Any]]:
    with bind_schema("public"):
        with SessionLocal() as session:
            rows = session.execute(
                select(SharedSourceLibraryItem).order_by(SharedSourceLibraryItem.id.asc())
            ).scalars().all()
            return [_item_row_to_dict(row, "shared") for row in rows]


def _load_project_items(project_key: str | None) -> List[Dict[str, Any]]:
    file_rows: list[dict[str, Any]] = []
    file_data = load_project_library_files(project_key)
    for payload in file_data.get("items", []):
        item_key = str(payload.get("item_key", "")).strip()
        channel_key = str(payload.get("channel_key", "")).strip()
        if not item_key or not channel_key:
            continue
        file_rows.append(
            {
                "item_key": item_key,
                "name": str(payload.get("name") or item_key),
                "channel_key": channel_key,
                "description": payload.get("description"),
                "params": _as_dict(payload.get("params")),
                "tags": _as_list(payload.get("tags")),
                "schedule": payload.get("schedule"),
                "extends_item_key": payload.get("extends_item_key"),
                "enabled": bool(payload.get("enabled", True)),
                "extra": _as_dict(payload.get("extra")),
                "scope": "project",
            }
        )
    if not project_key:
        return file_rows
    with bind_project(project_key):
        with SessionLocal() as session:
            rows = session.execute(select(SourceLibraryItem).order_by(SourceLibraryItem.id.asc())).scalars().all()
            db_rows = [_item_row_to_dict(row, "project") for row in rows]
            return [*file_rows, *db_rows]


def _merge_channels(
    shared_channels: List[Dict[str, Any]],
    project_channels: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    shared_map = {x["channel_key"]: x for x in shared_channels}
    effective = dict(shared_map)

    for pch in project_channels:
        base_key = pch.get("extends_channel_key") or pch["channel_key"]
        base = effective.get(base_key, {})
        merged = _deep_merge(base, pch) if base else dict(pch)
        merged["channel_key"] = pch["channel_key"]
        merged["scope"] = "project"
        effective[pch["channel_key"]] = merged

    return list(effective.values())


def _merge_items(
    shared_items: List[Dict[str, Any]],
    project_items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    shared_map = {x["item_key"]: x for x in shared_items}
    effective = dict(shared_map)

    for pit in project_items:
        base_key = pit.get("extends_item_key") or pit["item_key"]
        base = effective.get(base_key, {})
        merged = _deep_merge(base, pit) if base else dict(pit)
        merged["item_key"] = pit["item_key"]
        merged["scope"] = "project"
        effective[pit["item_key"]] = merged

    return list(effective.values())


def list_effective_channels(scope: str = "effective", project_key: str | None = None) -> List[Dict[str, Any]]:
    shared_channels = _load_shared_channels()
    project_channels = _load_project_channels(project_key)

    if scope == "shared":
        return shared_channels
    if scope == "project":
        return project_channels

    return _merge_channels(shared_channels, project_channels)


def list_effective_items(scope: str = "effective", project_key: str | None = None) -> List[Dict[str, Any]]:
    shared_items = _load_shared_items()
    project_items = _load_project_items(project_key)

    if scope == "shared":
        return shared_items
    if scope == "project":
        return project_items

    return _merge_items(shared_items, project_items)


def run_item_by_key(
    *,
    item_key: str,
    project_key: str | None = None,
    override_params: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    channels = list_effective_channels(scope="effective", project_key=project_key)
    items = list_effective_items(scope="effective", project_key=project_key)

    item_map = {x["item_key"]: x for x in items}
    channel_map = {x["channel_key"]: x for x in channels}

    item = item_map.get(item_key)
    if item is None:
        raise ValueError(f"source item not found: {item_key}")
    if not item.get("enabled", True):
        raise ValueError(f"source item disabled: {item_key}")

    channel_key = str(item.get("channel_key") or "").strip()
    channel = channel_map.get(channel_key)
    if channel is None:
        raise ValueError(f"channel not found for item {item_key}: {channel_key}")
    if not channel.get("enabled", True):
        raise ValueError(f"channel disabled for item {item_key}: {channel_key}")

    params = _deep_merge(channel.get("default_params") or {}, item.get("params") or {})
    if override_params:
        params = _deep_merge(params, override_params)

    with (bind_project(project_key) if project_key else nullcontext()):
        result = run_channel(channel=channel, params=params, project_key=project_key)

    return {
        "item_key": item_key,
        "channel_key": channel_key,
        "params": params,
        "result": result,
    }

