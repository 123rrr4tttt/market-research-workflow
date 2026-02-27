from __future__ import annotations

from contextlib import nullcontext

from ..contracts import CollectRequest, CollectResult
from ..display_meta import build_display_meta
from ...job_logger import complete_job, fail_job, start_job
from ...projects import bind_project


def _normalize_terms(value) -> list[str]:
    if isinstance(value, list):
        out = []
        for x in value:
            s = str(x or "").strip()
            if s and s not in out:
                out.append(s)
        return out
    s = str(value or "").strip()
    return [s] if s else []


def _split_batches(terms: list[str], chunk_size: int) -> list[list[str]]:
    clean = _normalize_terms(terms)
    if not clean:
        return [[]]
    size = max(1, int(chunk_size))
    return [clean[i : i + size] for i in range(0, len(clean), size)]


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
                    q_raw = (
                        override_params.get("query_terms")
                        or override_params.get("keywords")
                        or override_params.get("search_keywords")
                        or override_params.get("base_keywords")
                        or override_params.get("topic_keywords")
                        or []
                    )
                    q = _normalize_terms(q_raw)
                    batch_size = int(override_params.get("keyword_batch_size") or 4)
                    term_batches = _split_batches(q, batch_size)
                    per_keyword_limit = max(1, int(override_params.get("per_keyword_limit") or override_params.get("limit") or 5))
                    global_max_candidates = max(1, int(override_params.get("max_candidates") or 200))
                    global_ingest_limit = max(1, int(override_params.get("ingest_limit") or override_params.get("limit") or 20))
                    us_runs = []
                    for term_batch in term_batches:
                        batch_term_count = max(1, len(term_batch))
                        batch_max_candidates = min(global_max_candidates, per_keyword_limit * batch_term_count)
                        batch_ingest_limit = min(global_ingest_limit, per_keyword_limit * batch_term_count)
                        us_runs.append(
                            unified_search_by_item_payload(
                                project_key=str(request.project_key or ""),
                                item=item,
                                query_terms=term_batch,
                                max_candidates=batch_max_candidates,
                                # Handler-cluster runs are expected to produce downstream ingestable results.
                                # Default to write+ingest unless explicitly disabled.
                                write_to_pool=bool(override_params.get("write_to_pool", True)),
                                pool_scope=str(override_params.get("pool_scope") or "project"),
                                probe_timeout=float(override_params.get("probe_timeout") or 10.0),
                                auto_ingest=bool(override_params.get("auto_ingest", True)),
                                ingest_limit=batch_ingest_limit,
                                enable_extraction=bool(override_params.get("enable_extraction", True)),
                            )
                        )
                    benign_markers = {"url_term_filter_empty_fallback_used"}
                    merged_site_entries = []
                    seen_entry = set()
                    merged_candidates = []
                    seen_cand = set()
                    merged_error_details = []
                    merged_errors = []
                    inserted_total = 0
                    updated_total = 0
                    skipped_total = 0
                    written_urls_new = 0
                    written_urls_skipped = 0
                    ingest_inserted = 0
                    ingest_updated = 0
                    ingest_skipped = 0
                    for us in us_runs:
                        for e in (us.site_entries_used or []):
                            key = str(e.get("site_url") or e.get("id") or "")
                            if key and key not in seen_entry:
                                seen_entry.add(key)
                                merged_site_entries.append(e)
                        for u in (us.candidates or []):
                            s = str(u or "").strip()
                            if s and s not in seen_cand:
                                seen_cand.add(s)
                                merged_candidates.append(s)
                        for e in (us.errors or []):
                            if not isinstance(e, dict):
                                continue
                            merged_error_details.append(e)
                            msg = str(e.get("error") or "").strip()
                            if msg and msg not in benign_markers:
                                merged_errors.append(msg)
                        w = us.written or {}
                        written_urls_new += int(w.get("urls_new") or 0)
                        written_urls_skipped += int(w.get("urls_skipped") or 0)
                        ir = us.ingest_result or {}
                        ingest_inserted += int(ir.get("inserted") or 0)
                        ingest_updated += int(ir.get("updated") or 0)
                        ingest_skipped += int(ir.get("skipped") or 0)
                    # Prefer downstream ingest_result counters; fallback to written counters.
                    inserted_total = ingest_inserted or written_urls_new
                    updated_total = ingest_updated
                    skipped_total = ingest_skipped or written_urls_skipped
                    raw = {
                        "mode": "handler_url_cluster_batched" if len(term_batches) > 1 else "handler_url_cluster",
                        "handler_key": str((item_extra or {}).get("expected_entry_type") or (item_params or {}).get("expected_entry_type") or ""),
                        "site_entry_count": len(merged_site_entries),
                        "item_key": str(request.item_key or ""),
                        "channel_key": "handler.cluster",
                        "params": dict(item_params if isinstance(item_params, dict) else {}),
                        "result": {
                            "inserted": inserted_total,
                            "updated": updated_total,
                            "skipped": skipped_total,
                            "errors": merged_errors,
                            "item_key": str(request.item_key or ""),
                            "query_terms": q,
                            "per_keyword_limit": per_keyword_limit,
                            "query_term_batches": term_batches,
                            "batches_total": len(term_batches),
                            "site_entries_used": merged_site_entries,
                            "candidates": merged_candidates,
                            "written": {
                                "urls_new": written_urls_new,
                                "urls_skipped": written_urls_skipped,
                            },
                            "ingest_result": {
                                "inserted": ingest_inserted,
                                "updated": ingest_updated,
                                "skipped": ingest_skipped,
                            },
                            "error_details": merged_error_details,
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
