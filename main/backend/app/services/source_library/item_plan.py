from __future__ import annotations

from typing import Annotated, TypeGuard
from urllib.parse import unquote

from .external_project import build_external_project_summary, get_external_project_manifest, is_external_project_item
from .external_integration import INTEGRATION_MANIFEST_VERSION
from .item_resolver import normalize_item_taxonomy

ITEM_EXECUTION_PLAN_CONTRACT_VERSION = "source_library.item_execution_plan.v1"
ITEM_QUERY_READINESS_CONTRACT_VERSION = "source_library.item_query_readiness.v1"
_SUPPORTED_QUERY_ROUTE_KINDS = {
    "search_template",
    "rss",
    "rss_feed",
    "sitemap",
    "official_api",
}
_ROUTE_KIND_ALIASES = {
    "rss_feed": "rss",
    "http_api": "official_api",
    "api": "official_api",
}

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


def _is_object(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _as_dict(value: object) -> dict[str, object]:
    return dict(value) if _is_object(value) else {}


def _normalize_site_entry_urls(value: object) -> list[str]:
    urls: list[str] = []
    if isinstance(value, str):
        raw_entries: list[object] = [value]
    elif _is_object_list(value):
        raw_entries = list(value)
    else:
        raw_entries = []
    for entry in raw_entries:
        entry_payload = _as_dict(entry)
        if entry_payload:
            site_url = str(entry_payload.get("site_url") or entry_payload.get("url") or "").strip()
        else:
            site_url = str(entry or "").strip()
        normalized = site_url
        if normalized and normalized not in urls:
            urls.append(normalized)
    return urls


def _search_template_has_query_placeholder(site_url: object) -> bool:
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


def _is_handler_cluster_search_template_item(item: dict[str, object]) -> bool:
    extra = _as_dict(item.get("extra"))
    params = _as_dict(item.get("params"))
    expected_entry_type = str(params.get("expected_entry_type") or extra.get("expected_entry_type") or "").strip().lower()
    return (
        str(item.get("item_key") or "").strip().lower() == "handler.cluster.search_template"
        and bool(extra.get("stable_handler_cluster"))
        and expected_entry_type == "search_template"
    )


def build_item_execution_plan(item: dict[str, object] | None) -> Annotated[
    dict[str, object],
    "kit:prepared-command effect_boundary=source_library.item_execution witness=test:test_derived_service_annotations_match_fact_sources",
]:
    from ..resource_pool.site_search_policy import resolve_site_search_policy

    source_item = dict(item or {})
    if is_external_project_item(source_item):
        manifest = get_external_project_manifest(
            _as_dict(source_item.get("extra")),
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
                "capabilities": _as_dict((manifest or {}).get("capabilities")),
                "accepted_inputs": _as_dict((manifest or {}).get("accepted_inputs")),
            },
        }

    params = _as_dict(source_item.get("params"))
    extra = _as_dict(source_item.get("extra"))
    expected_entry_type = str(params.get("expected_entry_type") or extra.get("expected_entry_type") or "").strip().lower()

    route_buckets = {
        "site_entries": _normalize_site_entry_urls(params.get("site_entries") or params.get("site_entry_urls")),
        "official_access_site_entries": _normalize_site_entry_urls(params.get("official_access_site_entries")),
    }
    plan_meta: dict[str, object] = {}

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


def _entry_supports_query(entry: dict[str, object]) -> bool:
    capabilities = entry.get("capabilities")
    if _is_object(capabilities):
        return capabilities.get("supports_query_terms") is True
    return entry.get("supports_query_terms") is True


def _entry_is_disabled(entry: dict[str, object]) -> bool:
    if entry.get("enabled") is False:
        return True
    lifecycle_state = str(entry.get("lifecycle_state") or "").strip().lower()
    return lifecycle_state == "disabled"


def _entry_route_kind(
    entry: dict[str, object],
    *,
    declared_entry_type: str,
) -> str:
    raw = entry.get("entry_type") or entry.get("route_kind") or declared_entry_type
    route_kind = str(raw or "").strip().lower()
    return _ROUTE_KIND_ALIASES.get(route_kind, route_kind)


def build_item_query_readiness(
    item: dict[str, object],
    *,
    site_entries: list[dict[str, object]] | None = None,
) -> Annotated[
    dict[str, object],
    "kit:non-authoritative derived_as=view fact_source=source_library.item_definition witness=test:test_query_readiness_uses_declared_static_routes_without_network",
]:
    """Derive static query readiness without reading a database or network."""

    source_item = dict(item or {})
    params = _as_dict(source_item.get("params"))
    extra = _as_dict(source_item.get("extra"))
    declared_entry_type = str(
        params.get("expected_entry_type") or extra.get("expected_entry_type") or ""
    ).strip().lower()
    item_disabled = source_item.get("enabled") is False

    if is_external_project_item(source_item):
        manifest = _as_dict(extra.get("external_project_manifest"))
        execution_mode = str(manifest.get("execution_mode") or "").strip().lower()
        route_kind = _ROUTE_KIND_ALIASES.get(execution_mode, execution_mode)
        if "integration" in manifest or manifest.get("contract_version") == INTEGRATION_MANIFEST_VERSION:
            status = "blocked"
            reasons = ["integration_runtime_not_connected"]
        elif item_disabled:
            status = "blocked"
            reasons = ["item_disabled"]
        elif route_kind in _SUPPORTED_QUERY_ROUTE_KINDS:
            status = "ready"
            reasons = ["declared_external_project_route"]
        elif route_kind:
            status = "not_applicable"
            reasons = ["external_project_mode_is_not_query_capability"]
        else:
            status = "discovery_required"
            reasons = ["external_project_execution_mode_not_declared"]
        entry_rows = [
            {
                "source_url": str(manifest.get("runner_ref") or "").strip(),
                "status": status,
                "route_kind": route_kind or None,
                "reasons": reasons,
            }
        ]
        counts = {
            "ready": int(status == "ready"),
            "discovery_required": int(status == "discovery_required"),
            "not_applicable": int(status == "not_applicable"),
            "blocked": int(status == "blocked"),
            "total": 1,
        }
        return _item_query_readiness_response(status, counts, entry_rows, reasons)

    raw_members = extra.get("members")
    declared_members = list(raw_members) if _is_object_list(raw_members) else []
    if site_entries is not None:
        resolved_entries = [dict(entry) for entry in site_entries]
    elif declared_members:
        resolved_entries = [dict(entry) if _is_object(entry) else {} for entry in declared_members]
    else:
        resolved_entries = [
            dict[str, object](site_url=url)
            for url in _normalize_site_entry_urls(
                params.get("site_entries") or params.get("site_entry_urls")
            )
        ]

    entry_rows: list[dict[str, object]] = []
    status_counts = {
        "ready": 0,
        "discovery_required": 0,
        "not_applicable": 0,
        "blocked": 0,
    }
    for entry in resolved_entries:
        source_url = str(
            entry.get("site_url") or entry.get("url") or entry.get("source_url") or ""
        ).strip()
        route_kind = _entry_route_kind(entry, declared_entry_type=declared_entry_type)
        reasons: list[str] = []
        roles = _entry_roles(entry)
        if roles:
            reasons.append(f"role={','.join(roles)}")

        if item_disabled:
            status = "blocked"
            reasons.append("item_disabled")
            status_counts[status] += 1
            entry_rows.append(
                {
                    "source_url": source_url,
                    "status": status,
                    "route_kind": route_kind or None,
                    "reasons": reasons,
                }
            )
            continue
        if _entry_is_disabled(entry):
            status = "blocked"
            reasons.append("entry_disabled")
            status_counts[status] += 1
            entry_rows.append(
                {
                    "source_url": source_url,
                    "status": status,
                    "route_kind": route_kind or None,
                    "reasons": reasons,
                }
            )
            continue

        if route_kind == "search_template":
            template = str(entry.get("template") or "").strip()
            template_source = "entry_template"
            if not template:
                template = source_url
                template_source = "source_url"
            normalized_template = unquote(template).lower()
            if "{{q}}" in normalized_template:
                status = "ready"
                reasons.append(f"declared_query_template:{template_source}")
            else:
                status = "blocked"
                reasons.append("search_template_missing_query_placeholder")
        elif route_kind in {"rss", "sitemap"}:
            status = "ready"
            reasons.append("declared_static_route")
        elif route_kind == "official_api":
            if _entry_supports_query(entry):
                status = "ready"
                reasons.append("declared_query_api")
            else:
                status = "discovery_required"
                reasons.append("api_query_support_not_declared")
        elif route_kind == "domain_root":
            status = "discovery_required"
            reasons.append("domain_root_query_contract_not_declared")
        elif route_kind:
            status = "not_applicable"
            reasons.append("entry_type_has_no_query_capability")
        elif source_url:
            status = "discovery_required"
            reasons.append("entry_type_not_declared")
        else:
            status = "blocked"
            reasons.append("site_entry_source_url_missing")

        status_counts[status] += 1
        entry_rows.append(
            {
                "source_url": source_url,
                "status": status,
                "route_kind": route_kind or None,
                "reasons": reasons,
            }
        )

    if status_counts["blocked"]:
        item_status = "blocked"
    elif status_counts["discovery_required"]:
        item_status = "discovery_required"
    elif status_counts["ready"]:
        item_status = "ready"
    elif item_disabled:
        item_status = "blocked"
    elif status_counts["not_applicable"]:
        item_status = "not_applicable"
    else:
        item_status = "not_applicable"

    top_level_reasons: list[str] = []
    if item_disabled:
        top_level_reasons.append("item_disabled")
    if not entry_rows:
        top_level_reasons.append("no_declared_site_entries")

    counts = {
        **status_counts,
        "total": len(entry_rows),
    }
    return _item_query_readiness_response(item_status, counts, entry_rows, top_level_reasons)


def _entry_roles(entry: dict[str, object]) -> list[str]:
    roles: list[str] = []
    raw_roles = entry.get("roles")
    if _is_object_list(raw_roles):
        roles.extend(str(value).strip().lower() for value in raw_roles if str(value or "").strip())
    raw_role = entry.get("role")
    if isinstance(raw_role, str) and raw_role.strip():
        roles.append(raw_role.strip().lower())
    raw_tags = entry.get("tags")
    if _is_object_list(raw_tags):
        roles.extend(
            str(value).strip().lower()
            for value in raw_tags
            if isinstance(value, str) and value.strip() in {"auxiliary_only", "review_only"}
        )
    return list(dict.fromkeys(role for role in roles if role))


def _item_query_readiness_response(
    status: str,
    counts: dict[str, int],
    entry_rows: list[dict[str, object]],
    reasons: list[str],
) -> dict[str, object]:
    return {
        "contract_version": ITEM_QUERY_READINESS_CONTRACT_VERSION,
        "status": status,
        "reasons": reasons,
        "entry_rows": entry_rows,
        "counts": counts,
        "automatic_assembly": True,
        "network_verified": False,
    }


def build_item_definition_view(
    item: dict[str, object] | None,
    *,
    include_execution_plan: bool = False,
) -> Annotated[
    dict[str, object],
    "kit:non-authoritative derived_as=view fact_source=source_library.item_definition witness=test:test_derived_service_annotations_match_fact_sources",
]:
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
        execution_plan = build_item_execution_plan(definition)
        execution_plan["plan_meta"] = {
            **_as_dict(execution_plan.get("plan_meta")),
            "query_readiness": build_item_query_readiness(definition),
        }
        normalized["execution_plan"] = execution_plan
    return normalized
