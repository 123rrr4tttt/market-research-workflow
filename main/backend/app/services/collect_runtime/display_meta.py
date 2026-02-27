from __future__ import annotations

from typing import Any

from .contracts import ALLOWED_COLLECT_FLOWS, CollectRequest, CollectResult, FLOW_COLLECT, FLOW_SOURCE_COLLECT


def _dedup_text_list(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    out: list[str] = []
    for v in values:
        s = str(v or "").strip()
        if s and s not in out:
            out.append(s)
    return out or None


def build_display_meta(request: CollectRequest, result: CollectResult | None = None, *, summary: str | None = None) -> dict[str, Any]:
    flow = str(request.flow or "").strip() or FLOW_COLLECT
    if flow not in ALLOWED_COLLECT_FLOWS:
        flow = FLOW_COLLECT
    meta: dict[str, Any] = {
        "version": 1,
        "flow": flow,
        "channel": request.channel,
        "summary": summary or request.source_context.get("summary") or request.channel,
        "project_key": request.project_key,
        "item_key": request.item_key,
        "resource_id": request.resource_id,
        "provider": request.provider,
        "language": request.language,
        "scope": request.scope,
        "platforms": _dedup_text_list(request.platforms),
        "query_terms_count": len(request.query_terms or []),
        "url_count": len(request.urls or []),
        "limit": request.limit,
        "tags": _dedup_text_list(request.source_context.get("tags") if isinstance(request.source_context, dict) else None),
    }
    if result is not None:
        meta.update(
            {
                "status": result.status,
                "inserted": result.inserted,
                "updated": result.updated,
                "skipped": result.skipped,
                "errors_count": len(result.errors or []),
            }
        )
    return {k: v for k, v in meta.items() if v is not None}


def infer_display_meta_from_celery_task(name: str, args: list[Any], kwargs: dict[str, Any] | None) -> dict[str, Any] | None:
    k = kwargs or {}
    n = str(name or "")
    if "task_ingest_market" in n:
        query_terms = k.get("query_terms") or (args[0] if len(args) > 0 and isinstance(args[0], list) else [])
        req = CollectRequest(
            channel="search.market",
            project_key=k.get("project_key") or (args[3] if len(args) > 3 else None),
            query_terms=list(query_terms or []),
            limit=k.get("max_items") or (args[1] if len(args) > 1 else None),
            provider=k.get("provider") or (args[7] if len(args) > 7 else None),
            language=k.get("language") or (args[6] if len(args) > 6 else None),
            source_context={"summary": "市场信息采集"},
        )
        return build_display_meta(req)
    if "task_collect_policy_regulation" in n:
        keywords = k.get("keywords") or (args[0] if len(args) > 0 and isinstance(args[0], list) else [])
        req = CollectRequest(
            channel="search.policy",
            project_key=k.get("project_key") or (args[3] if len(args) > 3 else None),
            query_terms=list(keywords or []),
            limit=k.get("limit") or (args[1] if len(args) > 1 else None),
            provider=k.get("provider") or (args[7] if len(args) > 7 else None),
            language=k.get("language") or (args[6] if len(args) > 6 else None),
            source_context={"summary": "政策/监管采集"},
        )
        return build_display_meta(req)
    if "task_run_source_library_item" in n:
        item_key = k.get("item_key") or (args[0] if len(args) > 0 else None)
        req = CollectRequest(
            flow=FLOW_SOURCE_COLLECT,
            channel="source_library",
            project_key=k.get("project_key") or (args[1] if len(args) > 1 else None),
            item_key=item_key,
            source_context={"summary": f"执行来源项 {item_key or '-'}"},
        )
        return build_display_meta(req)
    return None


def extract_display_meta_from_params(params: dict[str, Any] | None) -> dict[str, Any] | None:
    p = params or {}
    dm = p.get("display_meta")
    return dm if isinstance(dm, dict) else None
