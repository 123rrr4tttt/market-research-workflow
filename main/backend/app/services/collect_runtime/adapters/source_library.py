from __future__ import annotations

from contextlib import nullcontext

from ..contracts import CollectRequest, CollectResult
from ..display_meta import build_display_meta
from ...job_logger import complete_job, fail_job, start_job
from ...projects import bind_project


class SourceLibraryAdapter:
    def run(self, request: CollectRequest) -> CollectResult:
        from ...source_library.resolver import list_effective_items, run_item_by_key
        from ...resource_pool import unified_search_by_item_payload

        job_id = None
        try:
            with (bind_project(request.project_key) if request.project_key else nullcontext()):
                items = list_effective_items(scope="effective", project_key=request.project_key)
                item_map = {str(x.get("item_key") or ""): x for x in items if isinstance(x, dict)}
                item = item_map.get(str(request.item_key or ""))
                item_extra = (item or {}).get("extra") or {}
                item_params = (item or {}).get("params") or {}
                is_handler_cluster_item = bool(
                    isinstance(item_extra, dict)
                    and (
                        bool(item_extra.get("stable_handler_cluster"))
                        or str(item_extra.get("creation_handler") or "").startswith("handler.entry_type")
                    )
                )
                job_id = start_job(
                    "source_library_run",
                    {
                        "item_key": request.item_key,
                        "project_key": request.project_key,
                        "display_meta": build_display_meta(request, None, summary=f"执行来源项 {request.item_key or '-'}"),
                    },
                )
                override_params = dict(request.options.get("override_params") or {})
                if is_handler_cluster_item and item:
                    q = (
                        override_params.get("query_terms")
                        or override_params.get("keywords")
                        or override_params.get("search_keywords")
                        or override_params.get("base_keywords")
                        or override_params.get("topic_keywords")
                        or []
                    )
                    us = unified_search_by_item_payload(
                        project_key=str(request.project_key or ""),
                        item=item,
                        query_terms=q,
                        max_candidates=int(override_params.get("max_candidates") or 200),
                        write_to_pool=bool(override_params.get("write_to_pool")),
                        pool_scope=str(override_params.get("pool_scope") or "project"),
                        probe_timeout=float(override_params.get("probe_timeout") or 10.0),
                        auto_ingest=bool(override_params.get("auto_ingest")),
                        ingest_limit=int(override_params.get("ingest_limit") or 10),
                    )
                    errors = [e.get("error") for e in (us.errors or []) if isinstance(e, dict) and e.get("error")]
                    raw = {
                        "mode": "handler_url_cluster",
                        "handler_key": str((item_extra or {}).get("expected_entry_type") or (item_params or {}).get("expected_entry_type") or ""),
                        "site_entry_count": len(us.site_entries_used or []),
                        "item_key": str(request.item_key or ""),
                        "channel_key": "handler.cluster",
                        "params": dict(item_params if isinstance(item_params, dict) else {}),
                        "result": {
                            "inserted": int((us.written or {}).get("inserted") or 0),
                            "updated": int((us.written or {}).get("updated") or 0),
                            "skipped": int((us.written or {}).get("skipped") or 0),
                            "errors": errors,
                            "item_key": us.item_key,
                            "query_terms": us.query_terms,
                            "site_entries_used": us.site_entries_used,
                            "candidates": us.candidates,
                            "written": us.written,
                            "ingest_result": us.ingest_result,
                            "error_details": us.errors,
                        },
                    }
                else:
                    raw = run_item_by_key(
                        item_key=str(request.item_key or ""),
                        project_key=request.project_key,
                        override_params=override_params,
                    )
            nested = raw.get("result") if isinstance(raw, dict) else {}
            cr = CollectResult(
                channel=request.channel or "source_library",
                inserted=int((nested or {}).get("inserted") or 0),
                updated=int((nested or {}).get("updated") or 0),
                skipped=int((nested or {}).get("skipped") or 0),
                errors=[{"message": e} for e in ((nested or {}).get("errors") or []) if isinstance(e, str)],
                meta={"raw": raw},
            )
            cr.display_meta = build_display_meta(request, cr, summary=f"执行来源项 {request.item_key or '-'}")
            with (bind_project(request.project_key) if request.project_key else nullcontext()):
                complete_job(job_id, result={
                    "inserted": cr.inserted,
                    "updated": cr.updated,
                    "skipped": cr.skipped,
                    "display_meta": cr.display_meta,
                })
            return cr
        except Exception as exc:  # noqa: BLE001
            if job_id is not None:
                with (bind_project(request.project_key) if request.project_key else nullcontext()):
                    fail_job(job_id, str(exc))
            raise


def to_source_library_response(raw_collect_result: CollectResult) -> dict:
    raw = (raw_collect_result.meta or {}).get("raw")
    if isinstance(raw, dict):
        return raw
    return {
        "item_key": None,
        "channel_key": None,
        "params": {},
        "result": {
            "inserted": raw_collect_result.inserted,
            "updated": raw_collect_result.updated,
            "skipped": raw_collect_result.skipped,
            "errors": [e.get("message") for e in raw_collect_result.errors if isinstance(e, dict)],
        },
        "display_meta": raw_collect_result.display_meta,
    }
