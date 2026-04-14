"""Handler-cluster channel adapter: execute resource-pool unified search through source_library front door."""

from __future__ import annotations

from typing import Any, Dict


def _normalize_terms(value: Any) -> list[str]:
    if isinstance(value, list):
        out: list[str] = []
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


def handle_handler_cluster(params: Dict[str, Any], project_key: str | None) -> Dict[str, Any]:
    from ...resource_pool import unified_search_by_item_payload

    merged_params = dict(params or {})
    terminal_output_only = bool(merged_params.get("source_library_terminal_output_only")) or str(
        merged_params.get("source_library_execution_layer") or ""
    ).strip().lower() == "terminal_output_only"
    item_key = str(merged_params.pop("_item_key", "") or "").strip()
    item_params = {k: v for k, v in merged_params.items() if not str(k).startswith("_")}
    item = {
        "item_key": item_key or "_anonymous_handler_cluster",
        "params": item_params,
        "extra": {"expected_entry_type": item_params.get("expected_entry_type")},
    }

    q_raw = (
        item_params.get("query_terms")
        or item_params.get("keywords")
        or item_params.get("search_keywords")
        or item_params.get("base_keywords")
        or item_params.get("topic_keywords")
        or []
    )
    q = _normalize_terms(q_raw)
    batch_size = int(item_params.get("keyword_batch_size") or 4)
    term_batches = _split_batches(q, batch_size)
    per_keyword_limit = max(1, int(item_params.get("per_keyword_limit") or item_params.get("limit") or 5))
    global_max_candidates = max(1, int(item_params.get("max_candidates") or 200))
    global_ingest_limit = max(1, int(item_params.get("ingest_limit") or item_params.get("limit") or 20))
    sitemap_max_depth = max(0, int(item_params.get("sitemap_max_depth") or 2))
    sitemap_max_sitemaps = max(1, int(item_params.get("sitemap_max_sitemaps") or 50))

    us_runs = []
    for term_batch in term_batches:
        batch_term_count = max(1, len(term_batch))
        batch_max_candidates = min(global_max_candidates, per_keyword_limit * batch_term_count)
        batch_ingest_limit = min(global_ingest_limit, per_keyword_limit * batch_term_count)
        us_runs.append(
            unified_search_by_item_payload(
                project_key=str(project_key or ""),
                item=item,
                query_terms=term_batch,
                max_candidates=batch_max_candidates,
                write_to_pool=bool(item_params.get("write_to_pool", True)),
                pool_scope=str(item_params.get("pool_scope") or "project"),
                probe_timeout=float(item_params.get("probe_timeout") or 10.0),
                sitemap_max_depth=sitemap_max_depth,
                sitemap_max_sitemaps=sitemap_max_sitemaps,
                auto_ingest=False if terminal_output_only else bool(item_params.get("auto_ingest", True)),
                ingest_limit=batch_ingest_limit,
                enable_extraction=bool(item_params.get("enable_extraction", True)),
                allow_term_fallback=bool(item_params.get("allow_term_fallback", False)),
            )
        )

    benign_markers = {"url_term_filter_empty_fallback_used", "url_term_filter_empty_no_fallback"}
    merged_site_entries = []
    seen_entry = set()
    merged_candidates = []
    seen_cand = set()
    merged_error_details = []
    merged_errors = []
    written_urls_new = 0
    written_urls_skipped = 0
    ingest_inserted = 0
    ingest_updated = 0
    ingest_skipped = 0
    inserted_valid_total = 0
    rejected_count_total = 0
    rejection_breakdown_total: dict[str, int] = {}

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
        if terminal_output_only:
            continue
        ir = us.ingest_result or {}
        ingest_inserted += int(ir.get("inserted") or 0)
        ingest_updated += int(ir.get("updated") or 0)
        ingest_skipped += int(ir.get("skipped") or 0)
        inserted_valid_total += int(ir.get("inserted_valid") or 0)
        rejected_count_total += int(ir.get("rejected_count") or 0)
        rb = ir.get("rejection_breakdown")
        if isinstance(rb, dict):
            for key, value in rb.items():
                reason = str(key or "").strip()
                if not reason:
                    continue
                try:
                    count = int(value or 0)
                except Exception:
                    count = 0
                if count <= 0:
                    continue
                rejection_breakdown_total[reason] = int(rejection_breakdown_total.get(reason) or 0) + count

    records = [
        {
            "record_id": f"candidate:{idx}:{url}",
            "url": url,
            "title": None,
            "content_text": None,
            "summary": None,
            "published_at": None,
            "author": None,
            "language": None,
            "source_label": "handler.cluster",
            "record_meta": {"origin": "unified_search.candidate"},
            "raw_ref": {"source": "candidates", "index": idx},
        }
        for idx, url in enumerate(merged_candidates)
        if str(url or "").strip()
    ]

    response = {
        "record_stats": {
            "fetched": len(merged_candidates),
            "normalized": len(records),
            "dropped": max(len(merged_candidates) - len(records), 0),
            "errors": len(merged_errors),
        },
        "errors": merged_errors,
        "query_terms": q,
        "per_keyword_limit": per_keyword_limit,
        "query_term_batches": term_batches,
        "batches_total": len(term_batches),
        "site_entries_used": merged_site_entries,
        "candidates": merged_candidates,
        "records": records,
        "fetch_diagnostics": {
            "urls_new": written_urls_new,
            "urls_skipped": written_urls_skipped,
        },
        "single_write_workflow": "terminal_output_only" if terminal_output_only else "url_routing",
        "execution_layer": "terminal_output_only" if terminal_output_only else "execute",
        "error_details": merged_error_details,
    }
    if not terminal_output_only:
        response["legacy_ingest_result"] = {
            "inserted": ingest_inserted,
            "updated": ingest_updated,
            "skipped": ingest_skipped,
            "inserted_valid": inserted_valid_total,
            "rejected_count": rejected_count_total,
            "rejection_breakdown": rejection_breakdown_total,
        }
    return response
