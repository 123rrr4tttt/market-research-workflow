"""Generic web tool adapters: rss / sitemap / search_template."""

from __future__ import annotations

from typing import Any, Dict, Iterable

from ...resource_pool.extract import append_url
from ...resource_pool.search_template_service import execute_feed_probe
from ...resource_pool.search_template_service import execute_search_template
from ...resource_pool.search_template_service import execute_sitemap_probe
from ...resource_pool.search_template_service import normalize_search_template_placeholders


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


def _maybe_write_to_pool(urls: Iterable[str], *, params: Dict[str, Any], project_key: str | None, source: str) -> dict[str, int] | None:
    if not params.get("write_to_pool"):
        return None
    scope = str(params.get("pool_scope") or "project")
    if scope not in {"project", "shared"}:
        scope = "project"
    new_count = 0
    skipped = 0
    for url in urls:
        ok = append_url(
            url=url,
            source=source,
            source_ref={"tool": source, "query_terms": _as_terms(params.get("query_terms"))},
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
    }
