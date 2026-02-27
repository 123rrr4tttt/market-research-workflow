from __future__ import annotations

from dataclasses import replace
from math import ceil
from typing import Any

from .contracts import CollectRequest, CollectResult
from .adapters.search_market import SearchMarketAdapter
from .adapters.search_policy import SearchPolicyAdapter
from .adapters.source_library import SourceLibraryAdapter, to_source_library_response
from .adapters.url_pool import UrlPoolAdapter


_ADAPTERS = {
    "search.market": SearchMarketAdapter(),
    "search.policy": SearchPolicyAdapter(),
    "source_library": SourceLibraryAdapter(),
    "url_pool": UrlPoolAdapter(),
}

_AUTO_BATCH_CHANNELS = {"search.market", "search.policy"}


def run_collect(request: CollectRequest) -> CollectResult:
    batched = _maybe_run_auto_batched(request)
    if batched is not None:
        return batched
    adapter = _ADAPTERS.get(request.channel)
    if adapter is None:
        raise ValueError(f"unsupported collect channel: {request.channel}")
    return adapter.run(request)


def _should_auto_batch(request: CollectRequest) -> bool:
    if request.channel not in _AUTO_BATCH_CHANNELS:
        return False
    qn = len([x for x in (request.query_terms or []) if str(x).strip()])
    lim = int(request.limit or 0)
    return qn >= 6 or lim >= 60


def _split_query_terms(terms: list[str]) -> list[list[str]]:
    clean = [str(x).strip() for x in (terms or []) if str(x).strip()]
    if not clean:
        return [[]]
    chunk_size = 4 if len(clean) >= 8 else 5
    return [clean[i : i + chunk_size] for i in range(0, len(clean), chunk_size)]


def _merge_collect_results(parent_request: CollectRequest, batch_results: list[tuple[list[str], CollectResult]]) -> CollectResult:
    out = CollectResult(channel=parent_request.channel, status="completed")
    links_seen: set[str] = set()
    merged_links: list[str] = []
    raw_batches: list[dict[str, Any]] = []
    for terms, cr in batch_results:
        out.inserted += int(cr.inserted or 0)
        out.updated += int(cr.updated or 0)
        out.skipped += int(cr.skipped or 0)
        out.errors.extend(cr.errors or [])
        raw = dict((cr.meta or {}).get("raw") or {})
        raw_batches.append({"query_terms": terms, "result": raw})
        for link in (raw.get("links") or []):
            s = str(link or "").strip()
            if s and s not in links_seen:
                links_seen.add(s)
                merged_links.append(s)
    raw_merged = {
        "inserted": out.inserted,
        "updated": out.updated,
        "skipped": out.skipped,
        "errors": out.errors,
        "auto_batched": True,
        "batches_total": len(batch_results),
        "batches_completed": len(batch_results),
        "batch_results": raw_batches,
    }
    if merged_links:
        raw_merged["links"] = merged_links
    out.meta = {
        "raw": raw_merged,
        "auto_batched": True,
        "batches_total": len(batch_results),
        "query_term_batches": [terms for terms, _ in batch_results],
    }
    # Adapter-specific summary stays same; display_meta builder will fill standard stats.
    from .display_meta import build_display_meta
    summary = (parent_request.source_context or {}).get("summary")
    out.display_meta = build_display_meta(parent_request, out, summary=summary)
    return out


def _run_collect_no_batch(request: CollectRequest) -> CollectResult:
    adapter = _ADAPTERS.get(request.channel)
    if adapter is None:
        raise ValueError(f"unsupported collect channel: {request.channel}")
    return adapter.run(request)


def _maybe_run_auto_batched(request: CollectRequest) -> CollectResult | None:
    if not _should_auto_batch(request):
        return None
    term_batches = _split_query_terms(request.query_terms)
    if len(term_batches) <= 1:
        return None
    per_batch_limit = max(10, int(ceil(max(1, int(request.limit or 20)) / len(term_batches))))
    batch_results: list[tuple[list[str], CollectResult]] = []
    for terms in term_batches:
        sub = replace(
            request,
            query_terms=terms,
            limit=per_batch_limit,
            source_context={**(request.source_context or {}), "auto_batched_child": True},
        )
        batch_results.append((terms, _run_collect_no_batch(sub)))
    return _merge_collect_results(request, batch_results)


def normalize_query_terms(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    s = str(value).strip()
    return [s] if s else []


def _first_nonempty_terms(*values: Any) -> list[str]:
    for value in values:
        terms = normalize_query_terms(value)
        if terms:
            return terms
    return []


def normalize_urls(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for x in value:
        s = str(x or "").strip()
        if s.startswith(("http://", "https://")):
            out.append(s)
    return out


def normalize_limit(value: Any, default: int | None = None) -> int | None:
    if value is None:
        return default
    try:
        return max(1, int(value))
    except Exception:
        return default


def normalize_language(value: Any) -> str | None:
    s = str(value or "").strip().lower()
    return s or None


def normalize_provider(value: Any) -> str | None:
    s = str(value or "").strip().lower()
    return s or None


def collect_request_from_market_api(*, query_terms: list[str], max_items: int, project_key: str | None, provider: str | None = None, language: str | None = None, start_offset: int | None = None, days_back: int | None = None, enable_extraction: bool = True) -> CollectRequest:
    return CollectRequest(
        channel="search.market",
        project_key=project_key,
        query_terms=normalize_query_terms(query_terms),
        limit=normalize_limit(max_items, 20),
        provider=normalize_provider(provider),
        language=normalize_language(language) or "en",
        options={"start_offset": start_offset, "days_back": days_back, "enable_extraction": enable_extraction},
        source_context={"summary": "市场信息采集"},
    )


def collect_request_from_policy_api(*, query_terms: list[str], max_items: int, project_key: str | None, provider: str | None = None, language: str | None = None, start_offset: int | None = None, days_back: int | None = None, enable_extraction: bool = True) -> CollectRequest:
    return CollectRequest(
        channel="search.policy",
        project_key=project_key,
        query_terms=normalize_query_terms(query_terms),
        limit=normalize_limit(max_items, 20),
        provider=normalize_provider(provider),
        language=normalize_language(language) or "en",
        options={"start_offset": start_offset, "days_back": days_back, "enable_extraction": enable_extraction},
        source_context={"summary": "政策/监管采集"},
    )


def collect_request_from_source_library_api(*, item_key: str, project_key: str | None, override_params: dict | None = None) -> CollectRequest:
    ov = dict(override_params or {})
    return CollectRequest(
        channel="source_library",
        project_key=project_key,
        item_key=str(item_key or "").strip() or None,
        query_terms=_first_nonempty_terms(
            ov.get("query_terms"),
            ov.get("keywords"),
            ov.get("search_keywords"),
            ov.get("base_keywords"),
            ov.get("topic_keywords"),
        ),
        urls=normalize_urls(ov.get("urls")),
        limit=normalize_limit(ov.get("limit") or ov.get("max_items"), None),
        provider=normalize_provider(ov.get("provider")),
        language=normalize_language(ov.get("language")),
        scope=(str(ov.get("scope")).strip() if ov.get("scope") is not None else None),
        platforms=ov.get("platforms") if isinstance(ov.get("platforms"), list) else None,
        options={"override_params": ov},
        source_context={"summary": f"执行来源项 {item_key}"},
    )


def collect_request_from_url_pool(
    *,
    project_key: str | None,
    urls: list[str] | None = None,
    scope: str | None = None,
    limit: int | None = None,
    source_filter: str | None = None,
    domain: str | None = None,
    query_terms: list[str] | None = None,
    options: dict[str, Any] | None = None,
) -> CollectRequest:
    extra_options = dict(options or {})
    if source_filter is not None:
        extra_options["source_filter"] = source_filter
    if domain is not None:
        extra_options["domain"] = domain
    return CollectRequest(
        channel="url_pool",
        project_key=project_key,
        urls=normalize_urls(urls or []),
        query_terms=normalize_query_terms(query_terms or []),
        scope=(str(scope).strip() if scope else None),
        limit=normalize_limit(limit, 50),
        options=extra_options,
        source_context={"summary": "URL 池抓取并写入文档"},
    )


def run_source_library_item_compat(*, item_key: str, project_key: str | None = None, override_params: dict | None = None) -> dict:
    req = collect_request_from_source_library_api(item_key=item_key, project_key=project_key, override_params=override_params)
    result = run_collect(req)
    response = to_source_library_response(result)
    if isinstance(response, dict):
        response.setdefault("display_meta", result.display_meta)
    return response
