"""URL pool channel adapter: wrap ingest.url_pool collect functions."""

from __future__ import annotations

from typing import Any, Dict


def handle_url_pool(params: Dict[str, Any], project_key: str | None) -> Dict[str, Any]:
    """
    URLs from channel.extra.urls or item.params.urls take precedence.
    Fallback: fetch from resource pool by scope/domain/source.
    """
    from ...collect_runtime import collect_request_from_url_pool, run_collect

    urls = params.get("urls")
    if urls is None:
        single = params.get("url")
        if single and isinstance(single, str) and str(single).strip():
            urls = [str(single).strip()]
    if isinstance(urls, list) and urls:
        req = collect_request_from_url_pool(project_key=project_key, urls=urls, limit=len(urls))
    else:
        req = collect_request_from_url_pool(
            project_key=project_key,
            scope=str(params.get("scope") or "effective"),
            limit=int(params.get("limit", 50)),
            source_filter=params.get("source") or None,
            domain=params.get("domain") or None,
        )
    result = run_collect(req)
    return dict((result.meta or {}).get("raw") or {"inserted": result.inserted, "updated": result.updated, "skipped": result.skipped})
