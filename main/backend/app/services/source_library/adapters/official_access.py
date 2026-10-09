"""Official access adapters."""

from __future__ import annotations

import time
from collections.abc import Mapping
from urllib.parse import quote_plus
from typing import Any, Dict, SupportsFloat, SupportsIndex, SupportsInt, TypeGuard
from typing_extensions import Buffer

from ...http.client import default_http_client
from ...ingest.adapters.http_utils import fetch_html
from ...resource_pool.search_template_service import execute_feed_probe
from ...resource_pool.search_template_service import extract_link_candidates_with_diagnostics_from_html
from ...resource_pool.search_template_service import normalize_candidate_url

_ARXIV_RESULT_CACHE_TTL_SECONDS = 900.0
_ARXIV_RESULT_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CROSSREF_RESULT_CACHE_TTL_SECONDS = 900.0
_CROSSREF_RESULT_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _is_object(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _object(value: object) -> dict[str, object]:
    return dict(value) if _is_object(value) else {}


def _object_list(value: object) -> list[object]:
    return list(value) if _is_object_list(value) else []


def _int(value: object) -> int:
    if not isinstance(value, int | float | str):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _strict_int(value: object) -> int:
    if not isinstance(value, (str, bytes, bytearray, SupportsInt, SupportsIndex, Buffer)):
        raise TypeError(
            "int() argument must be a string, a bytes-like object or a real number, "
            f"not '{type(value).__name__}'"
        )
    return int(value)


def _strict_float(value: object) -> float:
    if not isinstance(value, (str, bytes, bytearray, SupportsFloat, SupportsIndex, Buffer)):
        raise TypeError(
            "float() argument must be a string or a real number, "
            f"not '{type(value).__name__}'"
        )
    return float(value)


def _candidate_urls(value: object) -> list[str]:
    urls: list[str] = []
    for item in _object_list(value):
        url = str(getattr(item, "url", "") or "").strip()
        if url:
            urls.append(url)
    return urls


def _normalize_terms(raw: object) -> list[str]:
    if _is_object_list(raw):
        out: list[str] = []
        for item in raw:
            term = str(item or "").strip()
            if term and term not in out:
                out.append(term)
        return out
    term = str(raw or "").strip()
    return [term] if term else []


def _build_arxiv_query_url(*, query_terms: list[str], params: Mapping[object, object]) -> str:
    terms = [term for term in query_terms if term]
    if not terms:
        raise ValueError("official_access.api arxiv requires query_terms")
    search_fragments = [f"all:{quote_plus(term)}" for term in terms]
    search_query = "+AND+".join(search_fragments)
    start = max(0, _strict_int(params.get("start") or 0))
    max_results = max(1, min(_strict_int(params.get("max_results") or params.get("limit") or 10), 100))
    sort_by = str(params.get("sort_by") or "relevance").strip() or "relevance"
    sort_order = str(params.get("sort_order") or "descending").strip() or "descending"
    return (
        "https://export.arxiv.org/api/query"
        f"?search_query={search_query}&start={start}&max_results={max_results}"
        f"&sortBy={quote_plus(sort_by)}&sortOrder={quote_plus(sort_order)}"
    )


def _build_arxiv_html_search_url(*, query_terms: list[str], params: Mapping[object, object]) -> str:
    terms = [term for term in query_terms if term]
    if not terms:
        raise ValueError("official_access.api arxiv requires query_terms")
    query = " ".join(terms)
    size = max(1, min(_strict_int(params.get("max_results") or params.get("limit") or 10), 50))
    return (
        "https://arxiv.org/search/"
        f"?query={quote_plus(query)}&searchtype=all&abstracts=show&order=-announced_date_first&size={size}"
    )


def _build_crossref_query_params(*, query_terms: list[str], params: Mapping[object, object]) -> dict[str, Any]:
    terms = [term for term in query_terms if term]
    if not terms:
        raise ValueError("official_access.api crossref requires query_terms")
    rows = max(1, min(_strict_int(params.get("max_results") or params.get("limit") or 10), 100))
    query_params: dict[str, Any] = {
        "query": " ".join(terms),
        "rows": rows,
        "select": "DOI,title,URL,issued,published-print,published-online,container-title,type,publisher",
    }
    mailto = str(params.get("mailto") or params.get("contact_email") or "").strip()
    if mailto:
        query_params["mailto"] = mailto
    return query_params


def _candidate_url_from_crossref_item(item: object) -> str:
    if not _is_object(item):
        return ""
    direct_url = normalize_candidate_url(str(item.get("URL") or "").strip())
    if direct_url:
        return direct_url
    doi = str(item.get("DOI") or "").strip()
    if doi:
        return normalize_candidate_url(f"https://doi.org/{doi}") or ""
    return ""


def _extract_crossref_records(payload: object, *, max_results: int) -> list[dict[str, Any]]:
    message = _object(_object(payload).get("message"))
    items = _object_list(message.get("items"))
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_item in items:
        item = _object(raw_item)
        url = _candidate_url_from_crossref_item(item)
        if not url or url in seen:
            continue
        title_rows = _object_list(item.get("title"))
        title = str(title_rows[0] if title_rows else item.get("title") or "").strip()
        seen.add(url)
        records.append(
            {
                "url": url,
                "doi": str(item.get("DOI") or "").strip() or None,
                "title": title or None,
                "publisher": str(item.get("publisher") or "").strip() or None,
                "type": str(item.get("type") or "").strip() or None,
            }
        )
        if len(records) >= max_results:
            break
    return records


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
    params: Mapping[object, object],
) -> Dict[str, Any]:
    feed_url = _build_arxiv_query_url(query_terms=query_terms, params=params)
    execution = execute_feed_probe(
        feed_url=feed_url,
        query_terms=query_terms,
        probe_timeout=_strict_float(params.get("probe_timeout") or 10.0),
        allow_term_fallback=bool(params.get("allow_term_fallback", False)),
        params=params,
    )
    max_results = max(1, min(_strict_int(params.get("max_results") or params.get("limit") or 10), 100))
    raw_candidates = _candidate_urls(getattr(execution, "raw_candidates", None))
    selected_candidates = _candidate_urls(getattr(execution, "selected_candidates", None))
    candidates = list(dict.fromkeys(raw_candidates or selected_candidates))[:max_results]
    return {
        "strategy": "official_api_feed",
        "candidates": candidates,
        "used_term_fallback": execution.used_term_fallback,
        "pages_scanned": execution.pages_scanned,
        "diagnostics": {
            **dict(execution.diagnostics),
            "provider_key": "arxiv",
            "feed_url": feed_url,
            "selection_mode": "raw_feed_candidates" if raw_candidates else "selected_candidates",
        },
        "errors": list(execution.errors),
        "message": "official_access.api executed via arXiv API search",
    }


def _run_arxiv_html_fallback(
    *,
    query_terms: list[str],
    params: Mapping[object, object],
) -> Dict[str, Any]:
    max_results = max(1, min(_strict_int(params.get("max_results") or params.get("limit") or 10), 50))
    search_url = _build_arxiv_html_search_url(query_terms=query_terms, params=params)
    try:
        html_text, _response = fetch_html(
            search_url,
            timeout=_strict_float(params.get("probe_timeout") or 10.0),
            retries=max(0, _strict_int(params.get("fetch_retries") or 0)),
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


def _run_crossref_works_probe(
    *,
    query_terms: list[str],
    params: Mapping[object, object],
) -> Dict[str, Any]:
    endpoint = "https://api.crossref.org/works"
    query_params = _build_crossref_query_params(query_terms=query_terms, params=params)
    max_results = max(1, min(_strict_int(params.get("max_results") or params.get("limit") or 10), 100))
    try:
        payload: object = default_http_client.get_json(
            endpoint,
            params=query_params,
            timeout=_strict_float(params.get("probe_timeout") or 10.0),
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "strategy": "crossref_works_api",
            "candidates": [],
            "candidate_records": [],
            "used_term_fallback": False,
            "pages_scanned": 1,
            "diagnostics": {
                "provider_key": "crossref",
                "endpoint": endpoint,
                "query": query_params.get("query"),
                "rows": query_params.get("rows"),
                "credential_required": False,
                "public_api": True,
            },
            "errors": [{"site_url": endpoint, "error": str(exc), "error_class": "transport_failure"}],
            "message": "official_access.api Crossref works API failed",
        }

    records = _extract_crossref_records(payload, max_results=max_results)
    message = _object(_object(payload).get("message"))
    return {
        "strategy": "crossref_works_api",
        "candidates": [record["url"] for record in records],
        "candidate_records": records,
        "used_term_fallback": False,
        "pages_scanned": 1,
        "diagnostics": {
            "provider_key": "crossref",
            "endpoint": endpoint,
            "query": query_params.get("query"),
            "rows": query_params.get("rows"),
            "records_total": _int(message.get("total-results")),
            "selected_candidates": len(records),
            "credential_required": False,
            "public_api": True,
            "selection_mode": "crossref_message_items",
        },
        "errors": [],
        "message": "official_access.api executed via Crossref works API",
    }


def _resolve_official_provider(params: Mapping[object, object]) -> str:
    return str(
        params.get("provider_key")
        or params.get("provider")
        or params.get("api_name")
        or params.get("official_provider")
        or ""
    ).strip().lower()


def _make_arxiv_cache_key(*, query_terms: list[str], params: Mapping[object, object]) -> str:
    return "|".join(
        [
            ",".join(query_terms),
            str(_strict_int(params.get("max_results") or params.get("limit") or 10)),
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


def _make_crossref_cache_key(*, query_terms: list[str], params: Mapping[object, object]) -> str:
    return "|".join(
        [
            ",".join(query_terms),
            str(_strict_int(params.get("max_results") or params.get("limit") or 10)),
        ]
    )


def _read_crossref_cache(cache_key: str) -> dict[str, Any] | None:
    cached = _CROSSREF_RESULT_CACHE.get(cache_key)
    if not cached:
        return None
    cached_at, payload = cached
    if (time.monotonic() - float(cached_at)) > _CROSSREF_RESULT_CACHE_TTL_SECONDS:
        _CROSSREF_RESULT_CACHE.pop(cache_key, None)
        return None
    return dict(payload)


def _write_crossref_cache(cache_key: str, payload: dict[str, Any]) -> None:
    if payload.get("candidates"):
        _CROSSREF_RESULT_CACHE[cache_key] = (time.monotonic(), dict(payload))


def handle_official_access_api(params: Mapping[object, object], project_key: str | None) -> Dict[str, Any]:
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

    if provider in {"crossref", "crossref_api", "crossref_works"}:
        query_terms = _normalize_terms(
            params.get("query_terms")
            or params.get("keywords")
            or params.get("search_keywords")
            or params.get("base_keywords")
            or params.get("topic_keywords")
        )
        cache_key = _make_crossref_cache_key(query_terms=query_terms, params=params)
        cached = _read_crossref_cache(cache_key)
        if cached is not None:
            diagnostics = dict(cached.get("diagnostics") or {})
            diagnostics["cache_hit"] = True
            cached["diagnostics"] = diagnostics
            return cached
        chosen = _run_crossref_works_probe(query_terms=query_terms, params=params)
        response = {
            "inserted": len(chosen.get("candidates") or []),
            "skipped": 0,
            "candidates": list(chosen.get("candidates") or []),
            "candidate_records": list(chosen.get("candidate_records") or []),
            "written": None,
            "used_term_fallback": bool(chosen.get("used_term_fallback", False)),
            "pages_scanned": int(chosen.get("pages_scanned") or 1),
            "diagnostics": dict(chosen.get("diagnostics") or {}),
            "errors": list(chosen.get("errors") or []),
            "message": str(chosen.get("message") or "official_access.api executed via Crossref works API"),
        }
        _write_crossref_cache(cache_key, response)
        return response

    return {
        "inserted": 0,
        "skipped": 0,
        "candidates": [],
        "written": None,
        "message": "official_access.api adapter is a placeholder; provide project customization handler if needed.",
    }
