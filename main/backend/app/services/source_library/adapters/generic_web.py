"""Generic web tool adapters: rss / sitemap / search_template."""

from __future__ import annotations

from typing import Any, Dict, Iterable

from ...resource_pool.extract import append_url
from ...resource_pool.search_template_service import execute_feed_probe
from ...resource_pool.search_template_service import execute_search_template
from ...resource_pool.search_template_service import execute_sitemap_probe
from ...resource_pool.search_template_service import normalize_search_template_placeholders
from ...resource_pool.url_utils import domain_from_url


def _as_terms(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        s = raw.strip()
        return [s] if s else []
    if isinstance(raw, list):
        out: list[str] = []
        for x in raw:
            s = str(x).strip()
            if s:
                out.append(s)
        return list(dict.fromkeys(out))
    return []


def _source_library_item_context(params: Dict[str, Any]) -> dict[str, Any]:
    raw = params.get("_source_library_item")
    if not isinstance(raw, dict):
        return {}
    extra = raw.get("extra") if isinstance(raw.get("extra"), dict) else {}
    item_type = str(raw.get("item_type") or extra.get("item_type") or "").strip().lower() or None
    managed_by = str(raw.get("managed_by") or extra.get("managed_by") or "").strip().lower() or None
    return {
        "item_key": str(raw.get("item_key") or "").strip() or None,
        "channel_key": str(raw.get("channel_key") or "").strip() or None,
        "item_type": item_type,
        "managed_by": managed_by,
        "expected_entry_type": str(extra.get("expected_entry_type") or "").strip().lower() or None,
    }


def _build_capability_profile(*, source: str) -> dict[str, Any]:
    if source == "generic_web_rss":
        return {
            "entry_type": "rss",
            "source_mode": "site_search",
            "supports_query_terms": True,
            "supports_pagination": False,
            "extractor_kind": "rss_candidate_extractor",
            "fallback_policy": "term_match_then_feed_fallback",
        }
    if source == "generic_web_sitemap":
        return {
            "entry_type": "sitemap",
            "source_mode": "site_search",
            "supports_query_terms": True,
            "supports_pagination": True,
            "extractor_kind": "sitemap_candidate_extractor",
            "fallback_policy": "term_match_then_tree_fallback",
        }
    return {
        "entry_type": "search_template",
        "source_mode": "site_search",
        "supports_query_terms": True,
        "supports_pagination": True,
        "extractor_kind": "html_link_extractor",
        "fallback_policy": "term_match_then_search_template_fallback",
    }


def _adapter_taxonomy(*, source: str, params: Dict[str, Any]) -> dict[str, Any]:
    item_ctx = _source_library_item_context(params)
    return {
        "lane": "site_search_internal_adapter",
        "internal_adapter_only": True,
        "source_family": "generic_web",
        "entry_type": _build_capability_profile(source=source)["entry_type"],
        "item_key": item_ctx.get("item_key"),
        "item_type": item_ctx.get("item_type"),
        "managed_by": item_ctx.get("managed_by"),
    }


def _maybe_write_to_pool(urls: Iterable[str], *, params: Dict[str, Any], project_key: str | None, source: str) -> dict[str, int] | None:
    if not params.get("write_to_pool"):
        return None
    scope = str(params.get("pool_scope") or "project")
    if scope not in {"project", "shared"}:
        scope = "project"
    item_ctx = _source_library_item_context(params)
    capability_profile = _build_capability_profile(source=source)
    new_count = 0
    skipped = 0
    for url in urls:
        normalized_url = str(url or "").strip()
        source_ref = {
            "tool": source,
            "query_terms": _as_terms(params.get("query_terms")),
            "locator": normalized_url,
            "url": normalized_url,
            "domain": str(domain_from_url(normalized_url) or "").strip().lower() or None,
            "entrypoint": f"source_library.{source}",
            "source_mode": source,
            "project_key": str(project_key or "").strip() or None,
            "channel_key": item_ctx.get("channel_key"),
            "item_key": item_ctx.get("item_key"),
            "item_type": item_ctx.get("item_type"),
            "managed_by": item_ctx.get("managed_by"),
            "entry_type": item_ctx.get("expected_entry_type") or capability_profile["entry_type"],
            "source_family": "generic_web",
        }
        ok = append_url(
            url=normalized_url,
            source=source,
            source_ref=source_ref,
            scope=scope,
            project_key=(project_key or ""),
        )
        if ok:
            new_count += 1
        else:
            skipped += 1
    return {"urls_new": new_count, "urls_skipped": skipped}


def handle_generic_web_rss(params: Dict[str, Any], project_key: str | None) -> Dict[str, Any]:
    feed_url = str(params.get("feed_url") or params.get("site_url") or "").strip()
    if not feed_url:
        raise ValueError("generic_web.rss requires params.feed_url or params.site_url")
    execution = execute_feed_probe(
        feed_url=feed_url,
        query_terms=_as_terms(params.get("query_terms")),
        probe_timeout=float(params.get("probe_timeout") or 10),
        allow_term_fallback=bool(params.get("allow_term_fallback", True)),
    )
    candidates = [decision.url for decision in execution.selected_candidates if str(decision.url or "").strip()]
    capability_profile = _build_capability_profile(source="generic_web_rss")
    written = _maybe_write_to_pool(candidates, params=params, project_key=project_key, source="generic_web_rss")
    return {
        "inserted": len(candidates),
        "skipped": 0,
        "candidates": candidates,
        "written": written,
        "used_term_fallback": execution.used_term_fallback,
        "pages_scanned": execution.pages_scanned,
        "diagnostics": execution.diagnostics,
        "errors": execution.errors,
        "source_mode": "site_search",
        "capability_profile": capability_profile,
        "adapter_taxonomy": _adapter_taxonomy(source="generic_web_rss", params=params),
    }


def handle_generic_web_sitemap(params: Dict[str, Any], project_key: str | None) -> Dict[str, Any]:
    sitemap_url = str(params.get("sitemap_url") or params.get("site_url") or "").strip()
    if not sitemap_url:
        raise ValueError("generic_web.sitemap requires params.sitemap_url or params.site_url")
    execution = execute_sitemap_probe(
        sitemap_url=sitemap_url,
        query_terms=_as_terms(params.get("query_terms")),
        probe_timeout=float(params.get("probe_timeout") or 10),
        max_depth=int(params.get("max_depth") or 2),
        max_sitemaps=int(params.get("max_sitemaps") or 30),
        allow_term_fallback=bool(params.get("allow_term_fallback", True)),
    )
    candidates = [decision.url for decision in execution.selected_candidates if str(decision.url or "").strip()]
    capability_profile = _build_capability_profile(source="generic_web_sitemap")
    written = _maybe_write_to_pool(candidates, params=params, project_key=project_key, source="generic_web_sitemap")
    return {
        "inserted": len(candidates),
        "skipped": 0,
        "candidates": candidates,
        "written": written,
        "used_term_fallback": execution.used_term_fallback,
        "pages_scanned": execution.pages_scanned,
        "diagnostics": execution.diagnostics,
        "errors": execution.errors,
        "source_mode": "site_search",
        "capability_profile": capability_profile,
        "adapter_taxonomy": _adapter_taxonomy(source="generic_web_sitemap", params=params),
    }


def handle_generic_web_search_template(params: Dict[str, Any], project_key: str | None) -> Dict[str, Any]:
    template = normalize_search_template_placeholders(str(params.get("template") or params.get("site_url") or "").strip())
    if not template or "{{q}}" not in template:
        raise ValueError("generic_web.search_template requires params.template containing {{q}}")
    execution = execute_search_template(
        template=template,
        query_terms=_as_terms(params.get("query_terms")),
        params=params,
        probe_timeout=float(params.get("probe_timeout") or 10),
        allow_term_fallback=bool(params.get("allow_term_fallback", True)),
    )
    candidates = [decision.url for decision in execution.selected_candidates if str(decision.url or "").strip()]
    capability_profile = _build_capability_profile(source="generic_web_search_template")
    written = _maybe_write_to_pool(candidates, params=params, project_key=project_key, source="generic_web_search_template")
    return {
        "inserted": len(candidates),
        "skipped": 0,
        "candidates": candidates,
        "written": written,
        "used_term_fallback": execution.used_term_fallback,
        "pages_scanned": execution.pages_scanned,
        "search_urls": execution.search_urls,
        "diagnostics": execution.diagnostics,
        "errors": execution.errors,
        "source_mode": "site_search",
        "capability_profile": capability_profile,
        "adapter_taxonomy": _adapter_taxonomy(source="generic_web_search_template", params=params),
    }
