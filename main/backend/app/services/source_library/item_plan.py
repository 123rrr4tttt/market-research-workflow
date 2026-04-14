from __future__ import annotations

from typing import Any, Dict
from urllib.parse import unquote

from .external_project import build_external_project_summary, get_external_project_manifest, is_external_project_item
from .item_resolver import normalize_item_taxonomy

ITEM_EXECUTION_PLAN_CONTRACT_VERSION = "source_library.item_execution_plan.v1"

_VALIDATED_HANDLER_CLUSTER_SEARCH_TEMPLATE_URLS = {
    "https://venturebeat.com/?s=%7B%7Bq%7D%7D",
    "https://www.pymnts.com/?s=%7B%7Bq%7D%7D",
    "https://commercialobserver.com/?s=%7B%7Bq%7D%7D",
    "https://www.investopedia.com/search?q=%7B%7Bq%7D%7D",
}

_HANDLER_CLUSTER_SEARCH_TEMPLATE_SKIP_DOMAINS = {
    "finextra.com",
    "reddit.com",
    "x.com",
    "linkedin.com",
    "youtube.com",
    "news.cn",
    "iyiou.com",
    "stcn.com",
    "hai.stanford.edu",
    "actiontoaction.ai",
    "news.google.com",
    "dcrainmaker.com",
    "thequalityedit.com",
    "cybernews.com",
    "gizmodo.com",
    "supernote.com",
    "androidpolice.com",
    "moorinsightsstrategy.com",
    "cosmopolitan.com",
    "howtogeek.com",
    "theverge.com",
    "laptopmag.com",
    "arstechnica.com",
    "slashgear.com",
}

_DERIVED_ITEM_PARAM_FIELDS = {
    "official_access_site_entries",
}

_DERIVED_ITEM_EXTRA_FIELDS = {
    "search_template_source_set",
    "search_template_source_set_counts",
    "search_template_source_set_drop_reasons",
}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _normalize_site_entry_urls(value: Any) -> list[str]:
    urls: list[str] = []
    if isinstance(value, str):
        raw_entries: list[Any] = [value]
    elif isinstance(value, list):
        raw_entries = value
    else:
        raw_entries = []
    for entry in raw_entries:
        if isinstance(entry, dict):
            site_url = str(entry.get("site_url") or entry.get("url") or "").strip()
        else:
            site_url = str(entry or "").strip()
        normalized = site_url
        if normalized and normalized not in urls:
            urls.append(normalized)
    return urls


def _search_template_has_query_placeholder(site_url: Any) -> bool:
    raw = str(site_url or "").strip()
    if not raw:
        return False
    normalized = unquote(raw).lower()
    return "{{q}}" in normalized


def _site_entry_domain(site_url: str) -> str:
    normalized = str(site_url or "").strip().lower()
    if "://" in normalized:
        normalized = normalized.split("://", 1)[1]
    normalized = normalized.split("/", 1)[0].split("?", 1)[0]
    return normalized[4:] if normalized.startswith("www.") else normalized


def _dedupe_urls(*groups: list[str]) -> list[str]:
    urls: list[str] = []
    for group in groups:
        for site_url in group:
            if site_url and site_url not in urls:
                urls.append(site_url)
    return urls


def _is_handler_cluster_search_template_item(item: dict[str, Any]) -> bool:
    extra = _as_dict(item.get("extra"))
    params = _as_dict(item.get("params"))
    expected_entry_type = str(params.get("expected_entry_type") or extra.get("expected_entry_type") or "").strip().lower()
    return (
        str(item.get("item_key") or "").strip().lower() == "handler.cluster.search_template"
        and bool(extra.get("stable_handler_cluster"))
        and expected_entry_type == "search_template"
    )


def build_item_execution_plan(item: dict[str, Any] | None) -> dict[str, Any]:
    from ..resource_pool.site_search_policy import resolve_site_search_policy

    source_item = dict(item or {})
    if is_external_project_item(source_item):
        manifest = get_external_project_manifest(
            source_item.get("extra") if isinstance(source_item.get("extra"), dict) else {},
            item_key=str(source_item.get("item_key") or "").strip() or None,
            display_name=str(source_item.get("name") or "").strip() or None,
        )
        return {
            "contract_version": ITEM_EXECUTION_PLAN_CONTRACT_VERSION,
            "item_key": str(source_item.get("item_key") or "").strip(),
            "expected_entry_type": None,
            "route_buckets": {
                "site_entries": [],
                "official_access_site_entries": [],
            },
            "site_entry_urls": [],
            "route_bucket_counts": {
                "site_entries": 0,
                "official_access_site_entries": 0,
                "total": 0,
            },
            "plan_meta": {
                "execution_family": "external_project",
                "external_project": build_external_project_summary(manifest) or {},
                "capabilities": dict((manifest or {}).get("capabilities") or {}),
                "accepted_inputs": dict((manifest or {}).get("accepted_inputs") or {}),
            },
        }

    params = _as_dict(source_item.get("params"))
    extra = _as_dict(source_item.get("extra"))
    expected_entry_type = str(params.get("expected_entry_type") or extra.get("expected_entry_type") or "").strip().lower()

    route_buckets = {
        "site_entries": _normalize_site_entry_urls(params.get("site_entries") or params.get("site_entry_urls")),
        "official_access_site_entries": _normalize_site_entry_urls(params.get("official_access_site_entries")),
    }
    plan_meta: dict[str, Any] = {}

    if _is_handler_cluster_search_template_item(source_item):
        site_entries = list(route_buckets["site_entries"])
        official_access_entries: list[str] = []
        curated_entries: list[str] = []
        retained_entries: list[str] = []
        dropped_reasons: dict[str, int] = {}
        seen: set[str] = set()

        for site_url in site_entries:
            if not _search_template_has_query_placeholder(site_url):
                dropped_reasons["missing_query_placeholder"] = int(dropped_reasons.get("missing_query_placeholder") or 0) + 1
                continue
            if _site_entry_domain(site_url) in _HANDLER_CLUSTER_SEARCH_TEMPLATE_SKIP_DOMAINS:
                dropped_reasons["policy_deprioritized"] = int(dropped_reasons.get("policy_deprioritized") or 0) + 1
                continue
            if site_url in seen:
                dropped_reasons["duplicate_site_entry"] = int(dropped_reasons.get("duplicate_site_entry") or 0) + 1
                continue
            seen.add(site_url)
            if resolve_site_search_policy(site_url).category == "api_preferred":
                official_access_entries.append(site_url)
                dropped_reasons["api_preferred_rerouted"] = int(dropped_reasons.get("api_preferred_rerouted") or 0) + 1
                continue
            if site_url in _VALIDATED_HANDLER_CLUSTER_SEARCH_TEMPLATE_URLS:
                curated_entries.append(site_url)
            else:
                retained_entries.append(site_url)

        route_buckets["site_entries"] = [*curated_entries, *retained_entries]
        route_buckets["official_access_site_entries"] = official_access_entries
        plan_meta = {
            "search_template_source_set": "validated_query_capable",
            "search_template_source_set_counts": {
                "input": len(site_entries),
                "official_access": len(official_access_entries),
                "validated": len(curated_entries),
                "retained": len(route_buckets["site_entries"]),
                "dropped": max(len(site_entries) - len(route_buckets["site_entries"]) - len(official_access_entries), 0),
            },
            "search_template_source_set_drop_reasons": dropped_reasons,
        }

    site_entry_urls = _dedupe_urls(
        route_buckets["site_entries"],
        route_buckets["official_access_site_entries"],
    )
    return {
        "contract_version": ITEM_EXECUTION_PLAN_CONTRACT_VERSION,
        "item_key": str(source_item.get("item_key") or "").strip(),
        "expected_entry_type": expected_entry_type or None,
        "route_buckets": route_buckets,
        "site_entry_urls": site_entry_urls,
        "route_bucket_counts": {
            "site_entries": len(route_buckets["site_entries"]),
            "official_access_site_entries": len(route_buckets["official_access_site_entries"]),
            "total": len(site_entry_urls),
        },
        "plan_meta": plan_meta,
    }


def build_item_definition_view(
    item: dict[str, Any] | None,
    *,
    include_execution_plan: bool = False,
) -> dict[str, Any]:
    definition = dict(item or {})
    params = _as_dict(definition.get("params"))
    extra = _as_dict(definition.get("extra"))

    for key in _DERIVED_ITEM_PARAM_FIELDS:
        params.pop(key, None)
    for key in _DERIVED_ITEM_EXTRA_FIELDS:
        extra.pop(key, None)

    definition["params"] = params
    definition["extra"] = extra
    normalized = normalize_item_taxonomy(definition)
    if include_execution_plan:
        normalized["execution_plan"] = build_item_execution_plan(definition)
    return normalized
