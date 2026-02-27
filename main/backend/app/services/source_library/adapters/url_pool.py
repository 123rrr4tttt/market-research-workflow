"""URL pool channel adapter: wrap ingest.url_pool collect functions."""

from __future__ import annotations

from typing import Any, Dict


def handle_url_pool(params: Dict[str, Any], project_key: str | None) -> Dict[str, Any]:
    """
    URLs from channel.extra.urls or item.params.urls take precedence.
    Fallback: fetch from resource pool by scope/domain/source.
    """
    from ...collect_runtime import collect_request_from_url_pool, run_collect

    merged_params = dict(params or {})
    urls = merged_params.get("urls")
    if urls is None:
        single = merged_params.get("url")
        if single and isinstance(single, str) and str(single).strip():
            urls = [str(single).strip()]
    query_terms = (
        merged_params.get("query_terms")
        or merged_params.get("keywords")
        or merged_params.get("search_keywords")
        or merged_params.get("base_keywords")
        or merged_params.get("topic_keywords")
        or []
    )
    if isinstance(urls, list) and urls:
        req = collect_request_from_url_pool(
            project_key=project_key,
            urls=urls,
            limit=len(urls),
            query_terms=query_terms,
            options=merged_params,
        )
    else:
        req = collect_request_from_url_pool(
            project_key=project_key,
            scope=str(merged_params.get("scope") or "effective"),
            limit=int(merged_params.get("limit", 50)),
            source_filter=merged_params.get("source_filter") or merged_params.get("source") or None,
            domain=merged_params.get("domain") or None,
            query_terms=query_terms,
            options=merged_params,
        )
    result = run_collect(req)
    return dict((result.meta or {}).get("raw") or {"inserted": result.inserted, "updated": result.updated, "skipped": result.skipped})
