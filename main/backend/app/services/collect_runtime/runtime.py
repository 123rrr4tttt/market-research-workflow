from __future__ import annotations

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


def run_collect(request: CollectRequest) -> CollectResult:
    adapter = _ADAPTERS.get(request.channel)
    if adapter is None:
        raise ValueError(f"unsupported collect channel: {request.channel}")
    return adapter.run(request)


def normalize_query_terms(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    s = str(value).strip()
    return [s] if s else []


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
        query_terms=normalize_query_terms(ov.get("query_terms") or ov.get("keywords")),
        urls=normalize_urls(ov.get("urls")),
        limit=normalize_limit(ov.get("limit") or ov.get("max_items"), None),
        provider=normalize_provider(ov.get("provider")),
        language=normalize_language(ov.get("language")),
        scope=(str(ov.get("scope")).strip() if ov.get("scope") is not None else None),
        platforms=ov.get("platforms") if isinstance(ov.get("platforms"), list) else None,
        options={"override_params": ov},
        source_context={"summary": f"执行来源项 {item_key}"},
    )


def collect_request_from_url_pool(*, project_key: str | None, urls: list[str] | None = None, scope: str | None = None, limit: int | None = None, source_filter: str | None = None, domain: str | None = None) -> CollectRequest:
    return CollectRequest(
        channel="url_pool",
        project_key=project_key,
        urls=normalize_urls(urls or []),
        scope=(str(scope).strip() if scope else None),
        limit=normalize_limit(limit, 50),
        options={"source_filter": source_filter, "domain": domain},
        source_context={"summary": "URL 池抓取并写入文档"},
    )


def run_source_library_item_compat(*, item_key: str, project_key: str | None = None, override_params: dict | None = None) -> dict:
    req = collect_request_from_source_library_api(item_key=item_key, project_key=project_key, override_params=override_params)
    result = run_collect(req)
    response = to_source_library_response(result)
    if isinstance(response, dict):
        response.setdefault("display_meta", result.display_meta)
    return response
