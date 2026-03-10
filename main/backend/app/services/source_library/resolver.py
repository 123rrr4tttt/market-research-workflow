from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
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
from .types import FrontDoorExecutionProtocol, derive_source_tiering
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


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    s = str(value or "").strip().lower()
    if s in {"1", "true", "yes", "on"}:
        return True
    if s in {"0", "false", "no", "off"}:
        return False
    return default


def _clamp_int(value: Any, default: int, *, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = int(default)
    return max(min_value, min(max_value, parsed))


def _normalize_terms(value: Any) -> list[str]:
    if isinstance(value, list):
        out: list[str] = []
        for x in value:
            s = str(x or "").strip()
            if s and s not in out:
                out.append(s)
        return out
    s = str(value or "").strip()
    return [s] if s else []


def _split_batches(terms: list[str], chunk_size: int) -> list[list[str]]:
    clean = _normalize_terms(terms)
    if not clean:
        return [[]]
    size = max(1, int(chunk_size))
    return [clean[i : i + size] for i in range(0, len(clean), size)]


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

    # Crawler providers consume runtime payload from params.arguments.
    provider_type = str(channel.get("provider_type") or "").strip().lower()
    if provider_type in {"scrapy", "crawlee", "meltano"}:
        arguments = _as_dict(per_url_params.get("arguments"))
        arguments.setdefault("url", url_str)
        arguments.setdefault("urls", [url_str])
        per_url_params["arguments"] = arguments

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


def _extract_source_tiering_from_extra(extra: Dict[str, Any]) -> tuple[Any, Any]:
    tier = extra.get("source_tier")
    priority = extra.get("onboarding_priority")
    source_tiering = extra.get("source_tiering")
    if isinstance(source_tiering, dict):
        if source_tiering.get("tier") is not None:
            tier = source_tiering.get("tier")
        if source_tiering.get("onboarding_priority") is not None:
            priority = source_tiering.get("onboarding_priority")
    return tier, priority


def _attach_source_tiering(channel: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(channel)
    extra = _as_dict(normalized.get("extra"))
    explicit_tier, explicit_priority = _extract_source_tiering_from_extra(extra)
    tiering = derive_source_tiering(
        provider=normalized.get("provider"),
        provider_type=normalized.get("provider_type"),
        explicit_tier=explicit_tier,
        explicit_priority=explicit_priority,
    )
    tiering_payload = {
        "tier": tiering.tier.value,
        "onboarding_priority": tiering.onboarding_priority.value,
        "reason": tiering.reason,
    }
    extra["source_tiering"] = tiering_payload
    extra.setdefault("source_tier", tiering.tier.value)
    extra.setdefault("onboarding_priority", tiering.onboarding_priority.value)
    normalized["extra"] = extra
    normalized["source_tier"] = tiering.tier.value
    normalized["onboarding_priority"] = tiering.onboarding_priority.value
    return normalized


def _is_crawler_channel(channel: Dict[str, Any] | None) -> bool:
    if not isinstance(channel, dict):
        return False
    provider_type = str(channel.get("provider_type") or "").strip().lower()
    return provider_type in {"scrapy", "crawlee", "meltano"}


def _prefer_crawler_channel_key(
    *,
    channel_map: Dict[str, Dict[str, Any]],
    project_key: str | None,
) -> str | None:
    candidates: list[str] = []
    for channel_key, channel in channel_map.items():
        if not channel.get("enabled", True):
            continue
        if _is_crawler_channel(channel):
            candidates.append(str(channel_key))
    if not candidates:
        return None

    pk = str(project_key or "").strip().lower()

    def _score(key: str) -> tuple[int, str]:
        lowered = key.lower()
        if pk and lowered == f"crawler.{pk}":
            return (0, lowered)
        if pk and lowered.startswith(f"crawler.{pk}."):
            return (1, lowered)
        if lowered.startswith("crawler."):
            return (2, lowered)
        return (3, lowered)

    return sorted(candidates, key=_score)[0]


def _is_retryable_crawler_runtime_error(exc: Exception) -> bool:
    message = str(exc or "").strip().lower()
    if not message:
        return False
    return (
        "crawler provider '" in message and " is unavailable" in message
    ) or ("unsupported crawler provider_type" in message)


def _is_handler_cluster_item(item: Dict[str, Any] | None) -> bool:
    extra = (item or {}).get("extra") or {}
    if not isinstance(extra, dict):
        return False
    return bool(
        extra.get("stable_handler_cluster")
        or str(extra.get("creation_handler") or "").startswith("handler.entry_type")
    )


def _has_site_entries(params: Dict[str, Any] | None) -> bool:
    if not isinstance(params, dict):
        return False
    raw = params.get("site_entries") or params.get("site_entry_urls")
    return isinstance(raw, list) and any(str(x or "").strip() for x in raw)


def _normalize_site_entries(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for entry in value:
        site_url = str(entry or "").strip()
        if site_url and site_url not in out:
            out.append(site_url)
    return out


def _build_frontdoor_protocol(
    *,
    item: Dict[str, Any],
    params: Dict[str, Any],
    project_key: str | None,
    candidate_urls: List[str] | None = None,
) -> FrontDoorExecutionProtocol:
    item_key = str(item.get("item_key") or "").strip() or "_anonymous"
    item_channel_key = str(item.get("channel_key") or "").strip()
    item_params = _as_dict(item.get("params"))
    item_extra = _as_dict(item.get("extra"))
    source_tier = str(item_extra.get("source_tier") or "").strip()
    onboarding_priority = str(item_extra.get("onboarding_priority") or "").strip()
    source_tiering = item_extra.get("source_tiering")
    if isinstance(source_tiering, dict):
        source_tier = str(source_tiering.get("tier") or source_tier).strip()
        onboarding_priority = str(source_tiering.get("onboarding_priority") or onboarding_priority).strip()
    query_terms = _normalize_terms(
        params.get("query_terms")
        or params.get("keywords")
        or params.get("search_keywords")
        or params.get("base_keywords")
        or params.get("topic_keywords")
        or []
    )
    site_entries = _normalize_site_entries(params.get("site_entries") or params.get("site_entry_urls") or item_params.get("site_entries") or item_params.get("site_entry_urls"))
    routed_urls = _normalize_site_entries(candidate_urls if candidate_urls is not None else params.get("urls"))
    write_to_pool = _as_bool(params.get("write_to_pool"), True)
    auto_ingest = _as_bool(params.get("auto_ingest"), True)
    default_force_single_url_flow = item_channel_key.lower() == "url_pool" or item_key.lower().startswith("url_pool.")
    force_single_url_flow = _as_bool(params.get("force_single_url_flow"), default_force_single_url_flow)
    prefer_crawler_first = _as_bool(params.get("prefer_crawler_first"), False) and not force_single_url_flow
    search_parallelism = _clamp_int(params.get("search_parallelism"), 3, min_value=1, max_value=8)
    routing_parallelism = _resolve_url_routing_parallelism(
        params,
        len(routed_urls) if routed_urls else len(site_entries),
    )
    execution_mode = "single_channel"
    route_decision = "channel_direct"
    write_mode = "channel_direct"
    if routed_urls:
        execution_mode = "url_routing"
        route_decision = "front_door_url_routing"
        write_mode = "front_door_url_routing"
    elif _is_handler_cluster_item(item) or site_entries:
        execution_mode = "search_then_route"
        route_decision = "handler_cluster_search"
        write_mode = "front_door_url_routing"

    return FrontDoorExecutionProtocol(
        item_key=item_key,
        item_channel_key=item_channel_key,
        project_key=str(project_key or "").strip() or None,
        front_door_owner="run_item_payload",
        execution_mode=execution_mode,
        write_mode=write_mode,
        route_decision=route_decision,
        query_terms=query_terms,
        site_entries=site_entries,
        candidate_urls=routed_urls,
        expected_entry_type=str(item_extra.get("expected_entry_type") or item_params.get("expected_entry_type") or "").strip() or None,
        write_to_pool=write_to_pool,
        auto_ingest=auto_ingest,
        ingest_limit=max(1, int(params.get("ingest_limit") or params.get("limit") or 20)),
        force_single_url_flow=force_single_url_flow,
        prefer_crawler_first=prefer_crawler_first,
        search_parallelism=search_parallelism,
        routing_parallelism=routing_parallelism,
        source_tier=source_tier,
        onboarding_priority=onboarding_priority,
    )


def _protocol_to_dict(protocol: FrontDoorExecutionProtocol) -> Dict[str, Any]:
    return {
        "item_key": protocol.item_key,
        "item_channel_key": protocol.item_channel_key,
        "project_key": protocol.project_key,
        "front_door_owner": protocol.front_door_owner,
        "execution_mode": protocol.execution_mode,
        "write_mode": protocol.write_mode,
        "route_decision": protocol.route_decision,
        "query_terms": list(protocol.query_terms),
        "site_entries": list(protocol.site_entries),
        "candidate_urls": list(protocol.candidate_urls),
        "expected_entry_type": protocol.expected_entry_type,
        "write_to_pool": protocol.write_to_pool,
        "auto_ingest": protocol.auto_ingest,
        "ingest_limit": protocol.ingest_limit,
        "force_single_url_flow": protocol.force_single_url_flow,
        "prefer_crawler_first": protocol.prefer_crawler_first,
        "search_parallelism": protocol.search_parallelism,
        "routing_parallelism": protocol.routing_parallelism,
        "source_tier": protocol.source_tier,
        "onboarding_priority": protocol.onboarding_priority,
    }


def _resolve_url_routing_parallelism(params: Dict[str, Any], total_urls: int) -> int:
    if total_urls <= 1:
        return 1
    return _clamp_int(
        params.get("url_routing_parallelism") if params.get("url_routing_parallelism") is not None else params.get("routing_parallelism"),
        min(4, total_urls),
        min_value=1,
        max_value=max(1, total_urls),
    )


def _run_single_routed_url(
    *,
    url: Any,
    item: Dict[str, Any],
    params: Dict[str, Any],
    project_key: str | None,
    channel_map: Dict[str, Dict[str, Any]],
    has_query_terms: bool,
    force_single_url_flow: bool,
    preferred_crawler_channel_key: str | None,
    fallback_crawler_channel_key: str | None,
    force_crawler_fallback_on_empty: bool,
) -> Dict[str, Any]:
    url_str = str(url).strip() if url else ""
    if not url_str or not url_str.startswith(("http://", "https://")):
        return {"url": url_str or str(url), "channel_key": None, "error": "invalid url", "result": None}

    default_channel_key = "url_pool" if force_single_url_flow else resolve_channel_for_url(
        url_str,
        project_key,
        has_query_terms=has_query_terms,
    )
    channel_key = "url_pool" if force_single_url_flow else (preferred_crawler_channel_key or default_channel_key)
    channel = channel_map.get(channel_key)
    if channel is None:
        channel = channel_map.get("url_pool")
        if channel is not None:
            channel_key = "url_pool"
    if channel is None:
        return {"url": url_str, "channel_key": channel_key, "error": "channel not found", "result": None}
    if not channel.get("enabled", True):
        return {"url": url_str, "channel_key": channel_key, "error": "channel disabled", "result": None}

    per_url_params = _deep_merge(channel.get("default_params") or {}, params)
    per_url_params = {k: v for k, v in per_url_params.items() if k != "urls"}
    per_url_params = _inject_url_params_for_channel(
        channel=channel,
        per_url_params=per_url_params,
        url_str=url_str,
    )

    try:
        with (bind_project(project_key) if project_key else nullcontext()):
            result = run_channel(
                channel=channel,
                params=per_url_params,
                project_key=project_key,
                item_key=str(item.get("item_key") or "").strip() or None,
            )
        if (
            force_crawler_fallback_on_empty
            and isinstance(result, dict)
            and not _is_crawler_channel(channel)
            and int(result.get("inserted") or 0) + int(result.get("updated") or 0) <= 0
            and fallback_crawler_channel_key
            and fallback_crawler_channel_key != channel_key
        ):
            fallback_crawler_channel = channel_map.get(fallback_crawler_channel_key)
            if fallback_crawler_channel is not None and fallback_crawler_channel.get("enabled", True):
                fallback_crawler_params = _deep_merge(fallback_crawler_channel.get("default_params") or {}, params)
                fallback_crawler_params = {k: v for k, v in fallback_crawler_params.items() if k != "urls"}
                fallback_crawler_params = _inject_url_params_for_channel(
                    channel=fallback_crawler_channel,
                    per_url_params=fallback_crawler_params,
                    url_str=url_str,
                )
                try:
                    with (bind_project(project_key) if project_key else nullcontext()):
                        fallback_crawler_result = run_channel(
                            channel=fallback_crawler_channel,
                            params=fallback_crawler_params,
                            project_key=project_key,
                            item_key=str(item.get("item_key") or "").strip() or None,
                        )
                    return {
                        "url": url_str,
                        "channel_key": fallback_crawler_channel_key,
                        "fallback_from_channel_key": channel_key,
                        "fallback_reason": "mechanical_no_results",
                        "error": None,
                        "result": fallback_crawler_result,
                    }
                except Exception:
                    pass
        return {"url": url_str, "channel_key": channel_key, "error": None, "result": result}
    except Exception as exc:
        if (
            preferred_crawler_channel_key
            and channel_key == preferred_crawler_channel_key
            and default_channel_key
            and default_channel_key != channel_key
            and _is_retryable_crawler_runtime_error(exc)
        ):
            fallback_channel = channel_map.get(default_channel_key)
            if fallback_channel is not None and fallback_channel.get("enabled", True):
                fallback_params = _deep_merge(fallback_channel.get("default_params") or {}, params)
                fallback_params = {k: v for k, v in fallback_params.items() if k != "urls"}
                fallback_params = _inject_url_params_for_channel(
                    channel=fallback_channel,
                    per_url_params=fallback_params,
                    url_str=url_str,
                )
                try:
                    with (bind_project(project_key) if project_key else nullcontext()):
                        fallback_result = run_channel(
                            channel=fallback_channel,
                            params=fallback_params,
                            project_key=project_key,
                            item_key=str(item.get("item_key") or "").strip() or None,
                        )
                    return {
                        "url": url_str,
                        "channel_key": default_channel_key,
                        "fallback_from_channel_key": channel_key,
                        "fallback_reason": str(exc),
                        "error": None,
                        "result": fallback_result,
                    }
                except Exception:
                    pass
        return {"url": url_str, "channel_key": channel_key, "error": str(exc), "result": None}


def _channel_row_to_dict(row: Any, scope: str) -> Dict[str, Any]:
    return _attach_source_tiering({
        "channel_key": row.channel_key,
        "name": row.name,
        "kind": row.kind,
        "provider": row.provider,
        "provider_type": str(getattr(row, "provider_type", None) or "native"),
        "provider_config": _as_dict(getattr(row, "provider_config", None)),
        "execution_policy": _as_dict(getattr(row, "execution_policy", None)),
        "description": row.description,
        "credential_refs": _as_list(row.credential_refs),
        "default_params": _as_dict(row.default_params),
        "param_schema": _as_dict(row.param_schema),
        "extends_channel_key": row.extends_channel_key,
        "enabled": bool(row.enabled),
        "extra": _as_dict(row.extra),
        "scope": scope,
    })


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
            _attach_source_tiering(
                {
                    "channel_key": channel_key,
                    "name": str(payload.get("name") or channel_key),
                    "kind": str(payload.get("kind") or "unknown"),
                    "provider": str(payload.get("provider") or "unknown"),
                    "provider_type": str(payload.get("provider_type") or "native"),
                    "provider_config": _as_dict(payload.get("provider_config")),
                    "execution_policy": _as_dict(payload.get("execution_policy")),
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
    "provider_type": "native",
    "provider_config": {},
    "execution_policy": {},
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
    "provider_type": "native",
    "provider_config": {},
    "execution_policy": {},
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
    "provider_type": "native",
    "provider_config": {},
    "execution_policy": {},
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
    "provider_type": "native",
    "provider_config": {},
    "execution_policy": {},
    "description": "Tool channel: render template with {{q}}/{{page}} and parse result links.",
    "credential_refs": [],
    "default_params": {"probe_timeout": 10, "page": 1, "write_to_pool": False, "pool_scope": "project"},
    "param_schema": {"required": ["template", "query_terms"]},
    "extends_channel_key": None,
    "enabled": True,
    "extra": {},
    "scope": "builtin",
}

_HANDLER_CLUSTER_CHANNEL: Dict[str, Any] = {
    "channel_key": "handler.cluster",
    "name": "Handler Cluster",
    "kind": "cluster",
    "provider": "handler",
    "provider_type": "native",
    "provider_config": {},
    "execution_policy": {},
    "description": "Front-door channel for resource-pool handler clusters (search_template/rss/sitemap).",
    "credential_refs": [],
    "default_params": {
        "probe_timeout": 10,
        "pool_scope": "project",
        "write_to_pool": True,
        "auto_ingest": True,
        "enable_extraction": True,
        "allow_term_fallback": False,
        "prefer_crawler_first": False,
        "keyword_batch_size": 4,
        "search_parallelism": 3,
        "url_routing_parallelism": 4,
        "limit": 20,
        "max_candidates": 200,
        "ingest_limit": 20,
        "sitemap_max_depth": 2,
        "sitemap_max_sitemaps": 50,
    },
    "param_schema": {"required": ["site_entries", "expected_entry_type"]},
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
    "provider_type": "native",
    "provider_config": {},
    "execution_policy": {},
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
    "provider_type": "native",
    "provider_config": {},
    "execution_policy": {},
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
    "provider_type": "native",
    "provider_config": {},
    "execution_policy": {},
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
    _HANDLER_CLUSTER_CHANNEL,
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
        return [_attach_source_tiering(x) for x in shared_channels]
    if scope == "project":
        return [_attach_source_tiering(x) for x in project_channels]

    return [_attach_source_tiering(x) for x in _merge_channels(shared_channels, project_channels)]


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
    updated_total = 0
    skipped_total = 0
    by_url: List[Dict[str, Any]] = []
    errors: List[str] = []
    protocol = _build_frontdoor_protocol(item=item, params=params, project_key=project_key)
    has_query_terms = bool(protocol.query_terms)
    force_single_url_flow = protocol.force_single_url_flow
    prefer_crawler_first = protocol.prefer_crawler_first
    force_crawler_fallback_on_empty = _as_bool(params.get("force_crawler_fallback_on_empty"), True)
    preferred_crawler_channel_key: str | None = None
    fallback_crawler_channel_key: str | None = None
    if prefer_crawler_first:
        item_channel_key = str(item.get("channel_key") or "").strip()
        item_channel = channel_map.get(item_channel_key)
        if item_channel_key and item_channel and item_channel.get("enabled", True) and _is_crawler_channel(item_channel):
            preferred_crawler_channel_key = item_channel_key
        else:
            preferred_crawler_channel_key = _prefer_crawler_channel_key(
                channel_map=channel_map,
                project_key=project_key,
            )
    if force_crawler_fallback_on_empty:
        fallback_crawler_channel_key = _prefer_crawler_channel_key(
            channel_map=channel_map,
            project_key=project_key,
        )

    max_workers = _resolve_url_routing_parallelism(params, len(urls))
    if max_workers <= 1:
        rows = [
            _run_single_routed_url(
                url=url,
                item=item,
                params=params,
                project_key=project_key,
                channel_map=channel_map,
                has_query_terms=has_query_terms,
                force_single_url_flow=force_single_url_flow,
                preferred_crawler_channel_key=preferred_crawler_channel_key,
                fallback_crawler_channel_key=fallback_crawler_channel_key,
                force_crawler_fallback_on_empty=force_crawler_fallback_on_empty,
            )
            for url in urls
        ]
    else:
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="url-routing") as executor:
            futures = [
                executor.submit(
                    _run_single_routed_url,
                    url=url,
                    item=item,
                    params=params,
                    project_key=project_key,
                    channel_map=channel_map,
                    has_query_terms=has_query_terms,
                    force_single_url_flow=force_single_url_flow,
                    preferred_crawler_channel_key=preferred_crawler_channel_key,
                    fallback_crawler_channel_key=fallback_crawler_channel_key,
                    force_crawler_fallback_on_empty=force_crawler_fallback_on_empty,
                )
                for url in urls
            ]
            rows = [future.result() for future in futures]

    for row in rows:
        result = row.get("result")
        if isinstance(result, dict):
            inserted_total += int(result.get("inserted") or 0)
            updated_total += int(result.get("updated") or 0)
            skipped_total += int(result.get("skipped") or 0)
        else:
            error_text = str(row.get("error") or "").strip()
            if error_text:
                errors.append(f"{str(row.get('url') or '')[:80]}: {error_text}")
        by_url.append(row)

    return {
        "inserted": inserted_total,
        "updated": updated_total,
        "skipped": skipped_total,
        "by_url": by_url,
        "errors": errors,
        "middle_layer_protocol": _protocol_to_dict(protocol),
        "url_routing_parallelism": max_workers,
    }


def _summarize_routed_results(routed: Dict[str, Any]) -> Dict[str, Any]:
    inserted = int(routed.get("inserted") or 0)
    updated = int(routed.get("updated") or 0)
    skipped = int(routed.get("skipped") or 0)
    errors = [str(x) for x in (routed.get("errors") or []) if str(x or "").strip()]
    by_url = routed.get("by_url") or []

    inserted_valid = 0
    rejected_count = 0
    rejection_breakdown: Dict[str, int] = {}
    error_details: list[dict[str, Any]] = []
    channels_used: list[str] = []

    for row in by_url:
        if not isinstance(row, dict):
            continue
        channel_key = str(row.get("channel_key") or "").strip()
        if channel_key and channel_key not in channels_used:
            channels_used.append(channel_key)
        if row.get("error"):
            error_details.append(
                {
                    "url": str(row.get("url") or ""),
                    "channel_key": channel_key or None,
                    "error": str(row.get("error") or ""),
                }
            )
        result = row.get("result")
        if not isinstance(result, dict):
            continue
        valid = int(result.get("inserted_valid") or 0)
        inserted_valid += valid if valid > 0 else int(result.get("inserted") or 0)
        rejected_count += int(result.get("rejected_count") or 0)
        rb = result.get("rejection_breakdown")
        if isinstance(rb, dict):
            for key, value in rb.items():
                reason = str(key or "").strip()
                if not reason:
                    continue
                try:
                    count = int(value or 0)
                except Exception:
                    count = 0
                if count <= 0:
                    continue
                rejection_breakdown[reason] = int(rejection_breakdown.get(reason) or 0) + count

    if inserted_valid <= 0:
        inserted_valid = inserted

    return {
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "inserted_valid": inserted_valid,
        "rejected_count": rejected_count,
        "rejection_breakdown": rejection_breakdown,
        "errors": errors,
        "error_details": error_details,
        "channels_used": channels_used,
        "by_url": by_url,
    }


def _run_handler_cluster_item(
    *,
    item: Dict[str, Any],
    params: Dict[str, Any],
    project_key: str | None,
    channel_map: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    from ..resource_pool import unified_search_by_item_payload

    item_extra = (item or {}).get("extra") or {}
    item_params = (item or {}).get("params") or {}
    is_handler_cluster = _is_handler_cluster_item(item)
    protocol = _build_frontdoor_protocol(item=item, params=params, project_key=project_key)
    q = list(protocol.query_terms)
    batch_size = int(params.get("keyword_batch_size") or 4)
    term_batches = _split_batches(q, batch_size)
    search_parallelism = _clamp_int(
        params.get("search_parallelism"),
        3,
        min_value=1,
        max_value=8,
    )
    per_keyword_limit = max(1, int(params.get("per_keyword_limit") or params.get("limit") or 5))
    global_max_candidates = max(1, int(params.get("max_candidates") or 200))
    sitemap_max_depth = max(0, int(params.get("sitemap_max_depth") or 2))
    sitemap_max_sitemaps = max(1, int(params.get("sitemap_max_sitemaps") or 50))

    def _run_search_batch(term_batch: list[str]):
        batch_term_count = max(1, len(term_batch))
        batch_max_candidates = min(global_max_candidates, per_keyword_limit * batch_term_count)
        return unified_search_by_item_payload(
            project_key=str(project_key or ""),
            item=item,
            query_terms=term_batch,
            max_candidates=batch_max_candidates,
            write_to_pool=bool(params.get("write_to_pool", True)),
            pool_scope=str(params.get("pool_scope") or "project"),
            probe_timeout=float(params.get("probe_timeout") or 10.0),
            sitemap_max_depth=sitemap_max_depth,
            sitemap_max_sitemaps=sitemap_max_sitemaps,
            auto_ingest=False,
            ingest_limit=max(1, int(params.get("ingest_limit") or params.get("limit") or 20)),
            enable_extraction=bool(params.get("enable_extraction", True)),
            allow_term_fallback=bool(params.get("allow_term_fallback", False)),
        )

    if len(term_batches) <= 1 or search_parallelism <= 1:
        us_runs = [_run_search_batch(term_batch) for term_batch in term_batches]
    else:
        max_workers = min(search_parallelism, len(term_batches))
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="handler-search") as executor:
            us_runs = list(executor.map(_run_search_batch, term_batches))

    benign_markers = {"url_term_filter_empty_fallback_used", "url_term_filter_empty_no_fallback"}
    merged_site_entries: list[dict[str, Any]] = []
    seen_entry: set[str] = set()
    merged_candidates: list[str] = []
    seen_cand: set[str] = set()
    merged_error_details: list[dict[str, Any]] = []
    merged_errors: list[str] = []
    written_urls_new = 0
    written_urls_skipped = 0

    for us in us_runs:
        for e in (us.site_entries_used or []):
            key = str(e.get("site_url") or e.get("id") or "")
            if key and key not in seen_entry:
                seen_entry.add(key)
                merged_site_entries.append(e)
        for u in (us.candidates or []):
            s = str(u or "").strip()
            if s and s not in seen_cand:
                seen_cand.add(s)
                merged_candidates.append(s)
        for e in (us.errors or []):
            if not isinstance(e, dict):
                continue
            merged_error_details.append(e)
            msg = str(e.get("error") or "").strip()
            if msg and msg not in benign_markers and msg not in merged_errors:
                merged_errors.append(msg)
        w = us.written or {}
        written_urls_new += int(w.get("urls_new") or 0)
        written_urls_skipped += int(w.get("urls_skipped") or 0)

    routed_result = {
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [],
        "by_url": [],
    }
    routed_summary = {
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "inserted_valid": 0,
        "rejected_count": 0,
        "rejection_breakdown": {},
        "errors": [],
        "error_details": [],
        "channels_used": [],
        "by_url": [],
    }
    if merged_candidates:
        routing_params = dict(params)
        routing_params["urls"] = list(merged_candidates)
        # Handler cluster is the only clustering layer; downstream url_pool should execute only.
        routing_params["disable_site_seed_expansion"] = True
        routing_params["cluster_layer_separated"] = True
        routing_protocol = _build_frontdoor_protocol(
            item=item,
            params=routing_params,
            project_key=project_key,
            candidate_urls=merged_candidates,
        )
        routed_result = run_item_with_url_routing(
            item=item,
            params=routing_params,
            project_key=project_key,
            channel_map=channel_map,
        )
        routed_summary = _summarize_routed_results(routed_result)
        for detail in routed_summary["error_details"]:
            if detail not in merged_error_details:
                merged_error_details.append(detail)
        for msg in routed_summary["errors"]:
            if msg not in merged_errors:
                merged_errors.append(msg)

    return {
        "item_key": str(item.get("item_key") or ""),
        "channel_key": "handler.cluster" if is_handler_cluster else str(item.get("channel_key") or ""),
        "params": params,
        "result": {
            "inserted": int(routed_summary["inserted"] or 0),
            "updated": int(routed_summary["updated"] or 0),
            "skipped": int(routed_summary["skipped"] or 0),
            "errors": merged_errors,
            "item_key": str(item.get("item_key") or ""),
            "query_terms": q,
            "per_keyword_limit": per_keyword_limit,
            "query_term_batches": term_batches,
            "batches_total": len(term_batches),
            "search_parallelism": search_parallelism,
            "site_entries_used": merged_site_entries,
            "site_entry_count": len(merged_site_entries),
            "candidates": merged_candidates,
            "written": {
                "urls_new": written_urls_new,
                "urls_skipped": written_urls_skipped,
            },
            "single_write_workflow": protocol.write_mode,
            "channels_used": routed_summary["channels_used"],
            "middle_layer_protocol": _protocol_to_dict(routing_protocol if merged_candidates else protocol),
            "url_routing_parallelism": int(routed_result.get("url_routing_parallelism") or protocol.routing_parallelism),
            "ingest_result": {
                "inserted": int(routed_summary["inserted"] or 0),
                "updated": int(routed_summary["updated"] or 0),
                "skipped": int(routed_summary["skipped"] or 0),
                "inserted_valid": int(routed_summary["inserted_valid"] or 0),
                "rejected_count": int(routed_summary["rejected_count"] or 0),
                "rejection_breakdown": dict(routed_summary["rejection_breakdown"] or {}),
            },
            "routing_result": routed_result,
            "error_details": merged_error_details,
            "handler_key": str((item_extra or {}).get("expected_entry_type") or (item_params or {}).get("expected_entry_type") or ""),
        },
    }


def _enrich_item_with_channel_tiering(
    *,
    item: Dict[str, Any],
    channel_map: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    enriched = dict(item)
    extra = _as_dict(enriched.get("extra"))
    channel_key = str(enriched.get("channel_key") or "").strip()
    channel = channel_map.get(channel_key) or {}
    if not str(extra.get("source_tier") or "").strip():
        extra["source_tier"] = str(channel.get("source_tier") or "").strip()
    if not str(extra.get("onboarding_priority") or "").strip():
        extra["onboarding_priority"] = str(channel.get("onboarding_priority") or "").strip()
    source_tiering = channel.get("extra", {}).get("source_tiering") if isinstance(channel.get("extra"), dict) else None
    if isinstance(source_tiering, dict) and not isinstance(extra.get("source_tiering"), dict):
        extra["source_tiering"] = dict(source_tiering)
    enriched["extra"] = extra
    return enriched


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
    item = _enrich_item_with_channel_tiering(item=item, channel_map=channel_map)
    item_key = str(item.get("item_key") or "").strip() or "_anonymous"
    # Base params: item.params + ingest_config + override (no channel yet)
    params = dict(item.get("params") or {})
    if project_key:
        config = get_ingest_config(project_key, "social_forum")
        if config and config.get("payload"):
            params = _deep_merge(params, config["payload"])
    if override_params:
        params = _deep_merge(params, override_params)

    # Keep static URL-list items on the same front-door path as runtime-provided URLs.
    # Operators can still explicitly freeze legacy fixed lists when needed.
    item_key_lower = str(item.get("item_key") or "").strip().lower()
    item_channel_key_lower = str(item.get("channel_key") or "").strip().lower()
    if item_channel_key_lower == "url_pool" or item_key_lower.startswith("url_pool."):
        allow_legacy_url_list = _as_bool(params.get("enable_legacy_url_list"), True)
        if not allow_legacy_url_list and isinstance(params.get("urls"), list):
            params = dict(params)
            params.pop("urls", None)
            params["legacy_url_list_frozen"] = True

    # URL-routing branch: params.urls present -> resolve channel per URL
    urls = params.get("urls")
    if isinstance(urls, list) and urls:
        protocol = _build_frontdoor_protocol(item=item, params=params, project_key=project_key)
        result = run_item_with_url_routing(
            item=item,
            params=params,
            project_key=project_key,
            channel_map=channel_map,
        )
        if isinstance(result, dict) and "middle_layer_protocol" not in result:
            result["middle_layer_protocol"] = _protocol_to_dict(protocol)
        return {
            "item_key": item_key,
            "channel_key": None,
            "params": params,
            "result": result,
        }

    if _is_handler_cluster_item(item) or _has_site_entries(params):
        return _run_handler_cluster_item(
            item=item,
            params=params,
            project_key=project_key,
            channel_map=channel_map,
        )

    # Single-channel branch: resolve channel by item.channel_key
    channel_key = str(item.get("channel_key") or "").strip()
    channel = channel_map.get(channel_key)
    if channel is None:
        raise ValueError(f"channel not found for item {item_key}: {channel_key}")
    if not channel.get("enabled", True):
        raise ValueError(f"channel disabled for item {item_key}: {channel_key}")

    params = _deep_merge(channel.get("default_params") or {}, params)
    if channel_key == "handler.cluster":
        params = dict(params)
        params.setdefault("_item_key", item_key)

    with (bind_project(project_key) if project_key else nullcontext()):
        result = run_channel(
            channel=channel,
            params=params,
            project_key=project_key,
            item_key=item_key,
        )

    return {
        "item_key": item_key,
        "channel_key": channel_key,
        "params": params,
        "result": result,
    }
