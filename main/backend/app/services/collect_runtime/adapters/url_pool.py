from __future__ import annotations

from ..contracts import CollectRequest, CollectResult
from ..display_meta import build_display_meta


class UrlPoolAdapter:
    def run(self, request: CollectRequest) -> CollectResult:
        from ...ingest.url_pool import collect_urls_from_list, collect_urls_from_pool

        query_terms = list(request.query_terms or [])
        if request.urls:
            result = collect_urls_from_list(
                request.urls,
                project_key=request.project_key,
                query_terms=query_terms,
                extra_params=dict(request.options or {}),
                enable_extraction=bool(request.options.get("enable_extraction", True)),
            )
        else:
            result = collect_urls_from_pool(
                scope=str(request.scope or "effective"),
                project_key=request.project_key,
                domain=request.options.get("domain"),
                source_filter=request.options.get("source_filter") or request.options.get("source"),
                limit=int(request.limit or 50),
                query_terms=query_terms,
                extra_params=dict(request.options or {}),
                enable_extraction=bool(request.options.get("enable_extraction", True)),
            )
        cr = CollectResult(
            channel=request.channel or "url_pool",
            inserted=int(result.get("inserted") or 0),
            updated=int(result.get("updated") or 0),
            skipped=int(result.get("skipped") or 0),
            meta={"raw": result},
        )
        cr.display_meta = build_display_meta(request, cr, summary="URL 池抓取并写入文档")
        return cr
