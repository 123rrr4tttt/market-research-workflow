"""Official access adapters."""

from __future__ import annotations

import time
from urllib.parse import quote_plus
from typing import Any, Dict

from ...ingest.adapters.http_utils import fetch_html
from ...resource_pool.search_template_service import execute_feed_probe
from ...resource_pool.search_template_service import extract_link_candidates_with_diagnostics_from_html
from ...resource_pool.search_template_service import normalize_candidate_url

_ARXIV_RESULT_CACHE_TTL_SECONDS = 900.0
_ARXIV_RESULT_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _normalize_terms(raw: Any) -> list[str]:
    if isinstance(raw, list):
        out: list[str] = []
        for item in raw:
            term = str(item or "").strip()
            if term and term not in out:
                out.append(term)
        return out
    term = str(raw or "").strip()
    return [term] if term else []


def _build_arxiv_query_url(*, query_terms: list[str], params: Dict[str, Any]) -> str:
    terms = [term for term in query_terms if term]
    if not terms:
        raise ValueError("official_access.api arxiv requires query_terms")
    search_fragments = [f"all:{quote_plus(term)}" for term in terms]
    search_query = "+AND+".join(search_fragments)
    start = max(0, int(params.get("start") or 0))
    max_results = max(1, min(int(params.get("max_results") or params.get("limit") or 10), 100))
    sort_by = str(params.get("sort_by") or "relevance").strip() or "relevance"
    sort_order = str(params.get("sort_order") or "descending").strip() or "descending"
    return (
        "https://export.arxiv.org/api/query"
        f"?search_query={search_query}&start={start}&max_results={max_results}"
        f"&sortBy={quote_plus(sort_by)}&sortOrder={quote_plus(sort_order)}"
    )


def _build_arxiv_html_search_url(*, query_terms: list[str], params: Dict[str, Any]) -> str:
    terms = [term for term in query_terms if term]
    if not terms:
        raise ValueError("official_access.api arxiv requires query_terms")
    query = " ".join(terms)
    size = max(1, min(int(params.get("max_results") or params.get("limit") or 10), 50))
    return (
        "https://arxiv.org/search/"
        f"?query={quote_plus(query)}&searchtype=all&abstracts=show&order=-announced_date_first&size={size}"
    )


def _extract_arxiv_abs_candidates(html_text: str, *, search_url: str, max_results: int) -> list[str]:
    raw_candidates, _diagnostics = extract_link_candidates_with_diagnostics_from_html(
        html_text,
        base_url=search_url,
        entry_domain="arxiv.org",
        parser_profile="site_adaptive",
    )
    candidates: list[str] = []
    seen: set[str] = set()
    for item in raw_candidates:
        norm = normalize_candidate_url(str(getattr(item, "url", "") or "").strip())
        if not norm or norm in seen:
            continue
        if "/abs/" not in norm:
            continue
        seen.add(norm)
        candidates.append(norm)
        if len(candidates) >= max_results:
            break
    return candidates


def _run_arxiv_feed_probe(
    *,
    query_terms: list[str],
    params: Dict[str, Any],
) -> Dict[str, Any]:
    feed_url = _build_arxiv_query_url(query_terms=query_terms, params=params)
    execution = execute_feed_probe(
        feed_url=feed_url,
        query_terms=query_terms,
        probe_timeout=float(params.get("probe_timeout") or 10.0),
        allow_term_fallback=bool(params.get("allow_term_fallback", False)),
        params=params,
    )
    max_results = max(1, min(int(params.get("max_results") or params.get("limit") or 10), 100))
    raw_candidates = [
        str(getattr(item, "url", "") or "").strip()
        for item in (getattr(execution, "raw_candidates", None) or [])
        if str(getattr(item, "url", "") or "").strip()
    ]
    selected_candidates = [
        str(getattr(decision, "url", "") or "").strip()
        for decision in (getattr(execution, "selected_candidates", None) or [])
        if str(getattr(decision, "url", "") or "").strip()
    ]
    candidates = list(dict.fromkeys(raw_candidates or selected_candidates))[:max_results]
    return {
        "strategy": "official_api_feed",
        "candidates": candidates,
        "used_term_fallback": bool(getattr(execution, "used_term_fallback", False)),
        "pages_scanned": int(getattr(execution, "pages_scanned", 1) or 1),
        "diagnostics": {
            **dict(getattr(execution, "diagnostics", {}) or {}),
            "provider_key": "arxiv",
            "feed_url": feed_url,
            "selection_mode": "raw_feed_candidates" if raw_candidates else "selected_candidates",
        },
        "errors": list(getattr(execution, "errors", None) or []),
        "message": "official_access.api executed via arXiv API search",
    }


def _run_arxiv_html_fallback(
    *,
    query_terms: list[str],
    params: Dict[str, Any],
) -> Dict[str, Any]:
    max_results = max(1, min(int(params.get("max_results") or params.get("limit") or 10), 50))
    search_url = _build_arxiv_html_search_url(query_terms=query_terms, params=params)
    try:
        html_text, _response = fetch_html(
            search_url,
            timeout=float(params.get("probe_timeout") or 10.0),
            retries=max(0, int(params.get("fetch_retries") or 0)),
        )
        candidates = _extract_arxiv_abs_candidates(html_text, search_url=search_url, max_results=max_results)
        return {
            "strategy": "html_search_fallback",
            "candidates": candidates,
            "used_term_fallback": False,
            "pages_scanned": 1,
            "diagnostics": {
                "provider_key": "arxiv",
                "search_url": search_url,
                "entry_domain": "arxiv.org",
                "raw_candidates": len(candidates),
                "selected_candidates": len(candidates),
                "fallback_mode": "html_search",
            },
            "errors": [],
            "message": "official_access.api executed via arXiv HTML search fallback",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "strategy": "html_search_fallback",
            "candidates": [],
            "used_term_fallback": False,
            "pages_scanned": 1,
            "diagnostics": {
                "provider_key": "arxiv",
                "search_url": search_url,
                "entry_domain": "arxiv.org",
                "fallback_mode": "html_search",
            },
            "errors": [{"site_url": search_url, "error": str(exc), "error_class": "transport_failure"}],
            "message": "official_access.api arXiv HTML fallback failed",
        }


def _resolve_official_provider(params: Dict[str, Any]) -> str:
    return str(
        params.get("provider_key")
        or params.get("provider")
        or params.get("api_name")
        or params.get("official_provider")
        or ""
    ).strip().lower()


def _make_arxiv_cache_key(*, query_terms: list[str], params: Dict[str, Any]) -> str:
    return "|".join(
        [
            ",".join(query_terms),
            str(int(params.get("max_results") or params.get("limit") or 10)),
            str(params.get("sort_by") or "relevance"),
            str(params.get("sort_order") or "descending"),
        ]
    )


def _read_arxiv_cache(cache_key: str) -> dict[str, Any] | None:
    cached = _ARXIV_RESULT_CACHE.get(cache_key)
    if not cached:
        return None
    cached_at, payload = cached
    if (time.monotonic() - float(cached_at)) > _ARXIV_RESULT_CACHE_TTL_SECONDS:
        _ARXIV_RESULT_CACHE.pop(cache_key, None)
        return None
    return dict(payload)


def _write_arxiv_cache(cache_key: str, payload: dict[str, Any]) -> None:
    if payload.get("candidates"):
        _ARXIV_RESULT_CACHE[cache_key] = (time.monotonic(), dict(payload))


def handle_official_access_api(params: Dict[str, Any], project_key: str | None) -> Dict[str, Any]:
    provider = _resolve_official_provider(params)
    if provider in {"arxiv", "arxiv_api"}:
        query_terms = _normalize_terms(
            params.get("query_terms")
            or params.get("keywords")
            or params.get("search_keywords")
            or params.get("base_keywords")
            or params.get("topic_keywords")
        )
        cache_key = _make_arxiv_cache_key(query_terms=query_terms, params=params)
        cached = _read_arxiv_cache(cache_key)
        if cached is not None:
            diagnostics = dict(cached.get("diagnostics") or {})
            diagnostics["cache_hit"] = True
            cached["diagnostics"] = diagnostics
            return cached
        primary = _run_arxiv_feed_probe(query_terms=query_terms, params=params)
        fallback = None
        if not primary.get("candidates"):
            fallback = _run_arxiv_html_fallback(query_terms=query_terms, params=params)
        chosen = primary
        if not chosen.get("candidates") and fallback and fallback.get("candidates"):
            chosen = fallback
        errors = list(chosen.get("errors") or [])
        if chosen is primary and fallback and fallback.get("candidates"):
            diagnostics = dict(chosen.get("diagnostics") or {})
            diagnostics["fallback_candidates_available"] = len(fallback.get("candidates") or [])
        else:
            diagnostics = dict(chosen.get("diagnostics") or {})
        if chosen is fallback and primary.get("errors"):
            diagnostics["api_probe_failed"] = True
            diagnostics["api_probe_errors"] = len(primary.get("errors") or [])
        response = {
            "inserted": len(chosen.get("candidates") or []),
            "skipped": 0,
            "candidates": list(chosen.get("candidates") or []),
            "written": None,
            "used_term_fallback": bool(chosen.get("used_term_fallback", False)),
            "pages_scanned": int(chosen.get("pages_scanned") or 1),
            "diagnostics": diagnostics,
            "errors": errors,
            "message": str(chosen.get("message") or "official_access.api executed via arXiv search"),
        }
        _write_arxiv_cache(cache_key, response)
        return response

    return {
        "inserted": 0,
        "skipped": 0,
        "candidates": [],
        "written": None,
        "message": "official_access.api adapter is a placeholder; provide project customization handler if needed.",
    }
