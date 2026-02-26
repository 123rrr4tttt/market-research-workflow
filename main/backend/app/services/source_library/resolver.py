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
from ..ingest_config.service import get_config as get_ingest_config
from ..projects import bind_project, bind_schema
from .loader import load_project_library_files
from .runner import run_channel
from .url_router import resolve_channel_for_url


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


def _inject_url_params_for_channel(
    *,
    channel: Dict[str, Any],
    per_url_params: Dict[str, Any],
    url_str: str,
) -> Dict[str, Any]:
    """Map a routed URL into channel-specific params for tool channels."""
    provider = str(channel.get("provider") or "").strip().lower()
    kind = str(channel.get("kind") or "").strip().lower()

    # Preserve raw URL for adapters that directly consume url/urls.
    per_url_params.setdefault("url", url_str)
    per_url_params["urls"] = [url_str]

    if provider == "generic_web":
        per_url_params.setdefault("site_url", url_str)
        if kind == "rss":
            per_url_params.setdefault("feed_url", url_str)
        elif kind == "sitemap":
            per_url_params.setdefault("sitemap_url", url_str)
        elif kind == "search_template":
            # Search template usually needs a {{q}} template string; only infer when obvious.
            if "{{q}}" in url_str and "template" not in per_url_params:
                per_url_params["template"] = url_str
    return per_url_params


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


_URL_POOL_CHANNEL: Dict[str, Any] = {
    "channel_key": "url_pool",
    "name": "URL 资源池",
    "kind": "urls",
    "provider": "url_pool",
    "description": "从 URL 资源池取 URL 抓取入库，params: scope, domain, source, limit",
    "credential_refs": [],
    "default_params": {"scope": "effective", "limit": 50},
    "param_schema": {},
    "extends_channel_key": None,
    "enabled": True,
    "extra": {},
    "scope": "builtin",
}

_GENERIC_WEB_RSS_CHANNEL: Dict[str, Any] = {
    "channel_key": "generic_web.rss",
    "name": "Generic Web RSS",
    "kind": "rss",
    "provider": "generic_web",
    "description": "Tool channel: fetch RSS/Atom feed and emit candidate URLs.",
    "credential_refs": [],
    "default_params": {"probe_timeout": 10, "write_to_pool": False, "pool_scope": "project"},
    "param_schema": {"required": ["feed_url"]},
    "extends_channel_key": None,
    "enabled": True,
    "extra": {},
    "scope": "builtin",
}

_GENERIC_WEB_SITEMAP_CHANNEL: Dict[str, Any] = {
    "channel_key": "generic_web.sitemap",
    "name": "Generic Web Sitemap",
    "kind": "sitemap",
    "provider": "generic_web",
    "description": "Tool channel: parse sitemap/sitemapindex and emit candidate URLs.",
    "credential_refs": [],
    "default_params": {"probe_timeout": 10, "max_depth": 2, "max_sitemaps": 30, "write_to_pool": False, "pool_scope": "project"},
    "param_schema": {"required": ["sitemap_url"]},
    "extends_channel_key": None,
    "enabled": True,
    "extra": {},
    "scope": "builtin",
}

_GENERIC_WEB_SEARCH_TEMPLATE_CHANNEL: Dict[str, Any] = {
    "channel_key": "generic_web.search_template",
    "name": "Generic Web Search Template",
    "kind": "search_template",
    "provider": "generic_web",
    "description": "Tool channel: render template with {{q}}/{{page}} and parse result links.",
    "credential_refs": [],
    "default_params": {"probe_timeout": 10, "page": 1, "write_to_pool": False, "pool_scope": "project"},
    "param_schema": {"required": ["template", "query_terms"]},
    "extends_channel_key": None,
    "enabled": True,
    "extra": {},
    "scope": "builtin",
}

_OFFICIAL_ACCESS_API_CHANNEL: Dict[str, Any] = {
    "channel_key": "official_access.api",
    "name": "Official Access API",
    "kind": "api",
    "provider": "official_access",
    "description": "Tool channel placeholder for official APIs. Project customization can override.",
    "credential_refs": [],
    "default_params": {},
    "param_schema": {},
    "extends_channel_key": None,
    "enabled": True,
    "extra": {},
    "scope": "builtin",
}

_SPECIAL_WEB_JS_RENDER_CHANNEL: Dict[str, Any] = {
    "channel_key": "special_web.js_render",
    "name": "Special Web JS Render",
    "kind": "js_render",
    "provider": "special_web",
    "description": "Tool channel placeholder for JS-rendered pages. Handler not implemented yet.",
    "credential_refs": [],
    "default_params": {},
    "param_schema": {},
    "extends_channel_key": None,
    "enabled": True,
    "extra": {},
    "scope": "builtin",
}

_SPECIAL_WEB_ANTI_BOT_CHANNEL: Dict[str, Any] = {
    "channel_key": "special_web.anti_bot",
    "name": "Special Web Anti-Bot",
    "kind": "anti_bot",
    "provider": "special_web",
    "description": "Tool channel placeholder for anti-bot protected pages. Handler not implemented yet.",
    "credential_refs": [],
    "default_params": {},
    "param_schema": {},
    "extends_channel_key": None,
    "enabled": True,
    "extra": {},
    "scope": "builtin",
}

_BUILTIN_TOOL_CHANNELS: list[dict[str, Any]] = [
    _URL_POOL_CHANNEL,
    _GENERIC_WEB_RSS_CHANNEL,
    _GENERIC_WEB_SITEMAP_CHANNEL,
    _GENERIC_WEB_SEARCH_TEMPLATE_CHANNEL,
    _OFFICIAL_ACCESS_API_CHANNEL,
    _SPECIAL_WEB_JS_RENDER_CHANNEL,
    _SPECIAL_WEB_ANTI_BOT_CHANNEL,
]


def list_effective_channels(scope: str = "effective", project_key: str | None = None) -> List[Dict[str, Any]]:
    shared_channels = _load_shared_channels()
    project_channels = _load_project_channels(project_key)

    # Inject built-in tool channels if not present (unified channels list)
    shared_keys = {x["channel_key"] for x in shared_channels}
    for ch in _BUILTIN_TOOL_CHANNELS:
        if ch["channel_key"] not in shared_keys:
            shared_channels = [*shared_channels, dict(ch)]
            shared_keys.add(ch["channel_key"])

    if scope == "shared":
        return shared_channels
    if scope == "project":
        return project_channels

    return _merge_channels(shared_channels, project_channels)


_URL_POOL_DEFAULT_ITEM: Dict[str, Any] = {
    "item_key": "url_pool.default",
    "name": "URL 资源池（默认）",
    "channel_key": "url_pool",
    "description": "从 effective 范围抓取 URL 池中的 URL",
    "params": {"scope": "effective", "limit": 50},
    "tags": [],
    "schedule": None,
    "extends_item_key": None,
    "enabled": True,
    "extra": {},
    "scope": "builtin",
}


def list_items_by_symbol(scope: str = "effective", project_key: str | None = None) -> Dict[str, List[Dict[str, Any]]]:
    """Group items by tag (symbol). Items with no tags go under '_untagged'."""
    items = list_effective_items(scope=scope, project_key=project_key)
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for it in items:
        tags = it.get("tags") or []
        if not tags:
            key = "_untagged"
        else:
            for t in tags:
                key = str(t).strip()
                if not key:
                    continue
                if key not in grouped:
                    grouped[key] = []
                grouped[key].append(it)
        if not tags:
            if "_untagged" not in grouped:
                grouped["_untagged"] = []
            grouped["_untagged"].append(it)
    return grouped


def list_channels_grouped_by_provider(scope: str = "effective", project_key: str | None = None) -> Dict[str, List[Dict[str, Any]]]:
    """Group channels by provider (tool type: url_pool, generic_web, official_access, special_web, etc.)."""
    channels = list_effective_channels(scope=scope, project_key=project_key)
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for ch in channels:
        prov = str(ch.get("provider") or "unknown").strip()
        if prov not in grouped:
            grouped[prov] = []
        grouped[prov].append(ch)
    return grouped


def list_items_grouped_by_channel(scope: str = "effective", project_key: str | None = None) -> Dict[str, List[Dict[str, Any]]]:
    """Group items by handler key (provider/kind), fallback channel_key."""
    items = list_effective_items(scope=scope, project_key=project_key)
    channels = list_effective_channels(scope=scope, project_key=project_key)
    channel_map = {str(ch.get("channel_key") or "").strip(): ch for ch in channels}
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for it in items:
        channel_key = str(it.get("channel_key") or "").strip()
        ch = channel_map.get(channel_key) or {}
        provider = str(ch.get("provider") or "").strip().lower()
        kind = str(ch.get("kind") or "").strip().lower()
        if provider and kind:
            handler_key = f"{provider}/{kind}"
        else:
            handler_key = str(channel_key or "unknown").strip() or "unknown"
        if handler_key not in grouped:
            grouped[handler_key] = []
        grouped[handler_key].append(it)
    return grouped


def list_effective_items(scope: str = "effective", project_key: str | None = None) -> List[Dict[str, Any]]:
    shared_items = _load_shared_items()
    project_items = _load_project_items(project_key)

    # Inject built-in url_pool.default item if channel exists and no url_pool item present
    shared_keys = {x["item_key"] for x in shared_items}
    project_keys = {x["item_key"] for x in project_items}
    if "url_pool.default" not in shared_keys and "url_pool.default" not in project_keys:
        shared_items = [*shared_items, dict(_URL_POOL_DEFAULT_ITEM)]

    if scope == "shared":
        return shared_items
    if scope == "project":
        return project_items

    return _merge_items(shared_items, project_items)


def run_item_with_url_routing(
    *,
    item: Dict[str, Any],
    params: Dict[str, Any],
    project_key: str | None,
    channel_map: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Run item with per-URL channel routing. Resolves channel per URL via url_router.
    Returns aggregated { inserted, skipped, by_url }.
    """
    urls = params.get("urls")
    if not isinstance(urls, list) or not urls:
        raise ValueError("params.urls must be a non-empty list for URL routing")

    inserted_total = 0
    skipped_total = 0
    by_url: List[Dict[str, Any]] = []
    errors: List[str] = []
    query_terms = params.get("query_terms") or params.get("keywords") or params.get("search_keywords") or params.get("base_keywords") or params.get("topic_keywords")
    has_query_terms = isinstance(query_terms, list) and any(str(x or "").strip() for x in query_terms)

    for url in urls:
        url_str = str(url).strip() if url else ""
        if not url_str or not url_str.startswith(("http://", "https://")):
            by_url.append({"url": url_str or str(url), "channel_key": None, "error": "invalid url", "result": None})
            continue

        channel_key = resolve_channel_for_url(url_str, project_key, has_query_terms=has_query_terms)
        channel = channel_map.get(channel_key)
        if channel is None:
            channel = channel_map.get("url_pool")
        if channel is None:
            by_url.append({"url": url_str, "channel_key": channel_key, "error": "channel not found", "result": None})
            continue
        if not channel.get("enabled", True):
            by_url.append({"url": url_str, "channel_key": channel_key, "error": "channel disabled", "result": None})
            continue

        per_url_params = _deep_merge(channel.get("default_params") or {}, params)
        per_url_params = {k: v for k, v in per_url_params.items() if k != "urls"}
        per_url_params = _inject_url_params_for_channel(
            channel=channel,
            per_url_params=per_url_params,
            url_str=url_str,
        )

        try:
            with (bind_project(project_key) if project_key else nullcontext()):
                result = run_channel(channel=channel, params=per_url_params, project_key=project_key)
            inserted_total += result.get("inserted", 0)
            skipped_total += result.get("skipped", 0)
            by_url.append({"url": url_str, "channel_key": channel_key, "error": None, "result": result})
        except Exception as exc:
            errors.append(f"{url_str[:80]}: {exc}")
            by_url.append({"url": url_str, "channel_key": channel_key, "error": str(exc), "result": None})

    return {
        "inserted": inserted_total,
        "skipped": skipped_total,
        "by_url": by_url,
        "errors": errors,
    }


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
    return run_item_payload(item=item, channels=channels, project_key=project_key, override_params=override_params)


def run_item_payload(
    *,
    item: Dict[str, Any],
    channels: List[Dict[str, Any]] | None = None,
    project_key: str | None = None,
    override_params: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    if not item.get("enabled", True):
        raise ValueError(f"source item disabled: {item.get('item_key')}")

    channels = channels if channels is not None else list_effective_channels(scope="effective", project_key=project_key)
    channel_map = {x["channel_key"]: x for x in channels}
    item_key = str(item.get("item_key") or "").strip() or "_anonymous"
    # Base params: item.params + ingest_config + override (no channel yet)
    params = dict(item.get("params") or {})
    if project_key:
        config = get_ingest_config(project_key, "social_forum")
        if config and config.get("payload"):
            params = _deep_merge(params, config["payload"])
    if override_params:
        params = _deep_merge(params, override_params)

    # URL-routing branch: params.urls present -> resolve channel per URL
    urls = params.get("urls")
    if isinstance(urls, list) and urls:
        result = run_item_with_url_routing(
            item=item,
            params=params,
            project_key=project_key,
            channel_map=channel_map,
        )
        return {
            "item_key": item_key,
            "channel_key": None,
            "params": params,
            "result": result,
        }

    # Single-channel branch: resolve channel by item.channel_key
    channel_key = str(item.get("channel_key") or "").strip()
    channel = channel_map.get(channel_key)
    if channel is None:
        raise ValueError(f"channel not found for item {item_key}: {channel_key}")
    if not channel.get("enabled", True):
        raise ValueError(f"channel disabled for item {item_key}: {channel_key}")

    params = _deep_merge(channel.get("default_params") or {}, params)

    with (bind_project(project_key) if project_key else nullcontext()):
        result = run_channel(channel=channel, params=params, project_key=project_key)

    return {
        "item_key": item_key,
        "channel_key": channel_key,
        "params": params,
        "result": result,
    }
