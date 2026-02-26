from __future__ import annotations

from ..contracts import CollectRequest, CollectResult
from ..display_meta import build_display_meta


class SearchPolicyAdapter:
    def run(self, request: CollectRequest) -> CollectResult:
        from ...ingest.social import collect_policy_and_regulation

        result = collect_policy_and_regulation(
            keywords=request.query_terms,
            limit=int(request.limit or 20),
            enable_extraction=bool(request.options.get("enable_extraction", True)),
            provider=str(request.provider or "auto"),
            start_offset=request.options.get("start_offset"),
            days_back=request.options.get("days_back"),
            language=str(request.language or "en"),
        )
        cr = CollectResult(
            channel=request.channel or "search.policy",
            inserted=int(result.get("inserted") or 0),
            updated=int(result.get("updated") or 0),
            skipped=int(result.get("skipped") or 0),
            meta={"raw": result},
        )
        cr.display_meta = build_display_meta(request, cr, summary="政策/监管采集")
        return cr
