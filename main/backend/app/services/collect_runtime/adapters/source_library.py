from __future__ import annotations

from contextlib import nullcontext
import hashlib

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


def _as_bool(value, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    s = str(value).strip().lower()
    if s in {"1", "true", "yes", "on"}:
        return True
    if s in {"0", "false", "no", "off"}:
        return False
    return default


def _normalize_execution_mode(value) -> str:
    mode = str(value or "").strip().lower()
    if mode in {"dry_run", "dry-run", "preview"}:
        return "dry_run"
    return "apply"


def _normalize_explicit_candidate_ids(value) -> set[str]:
    if not isinstance(value, list):
        return set()
    out: set[str] = set()
    for item in value:
        s = str(item or "").strip().lower()
        if s:
            out.add(s)
    return out


def _candidate_id(url: str) -> str:
    return hashlib.sha1(str(url or "").strip().encode("utf-8")).hexdigest()[:12]


class SourceLibraryAdapter:
    def run(self, request: CollectRequest) -> CollectResult:
        from ...source_library.resolver import list_effective_items, run_item_by_key
        from ...resource_pool import append_url, unified_search_by_item_payload
        from ...ingest.url_pool import collect_urls_from_pool
        from ...ingest.meaningful_gate import normalize_reason_code

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
                override_params = dict(request.options.get("override_params") or {})
                trace_id = str(
                    override_params.get("_trace_id")
                    or request.options.get("trace_id")
                    or request.source_context.get("trace_id")
                    or ""
                ).strip()
                job_id = start_job(
                    "source_library_run",
                    {
                        "item_key": request.item_key,
                        "project_key": request.project_key,
                        **({"trace_id": trace_id} if trace_id else {}),
                        "display_meta": build_display_meta(request, None, summary=f"执行来源项 {request.item_key or '-'}"),
                    },
                )
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
                    sitemap_max_depth = max(0, int(override_params.get("sitemap_max_depth") or 2))
                    sitemap_max_sitemaps = max(1, int(override_params.get("sitemap_max_sitemaps") or 50))
                    execution_mode = _normalize_execution_mode(override_params.get("execution_mode"))
                    explicit_candidate_ids = _normalize_explicit_candidate_ids(
                        override_params.get("explicit_candidate_ids")
                    )
                    use_two_phase = execution_mode == "dry_run" or bool(explicit_candidate_ids)
                    auto_ingest_enabled = bool(override_params.get("auto_ingest", True))
                    pool_scope = str(override_params.get("pool_scope") or "project")
                    normalized_runs: list[dict] = []
                    all_candidate_records: list[dict] = []
                    seen_candidate_id: set[str] = set()
                    selected_candidate_ids: set[str] = set()
                    for batch_idx, term_batch in enumerate(term_batches):
                        batch_term_count = max(1, len(term_batch))
                        batch_max_candidates = min(global_max_candidates, per_keyword_limit * batch_term_count)
                        batch_ingest_limit = min(global_ingest_limit, per_keyword_limit * batch_term_count)
                        preview = unified_search_by_item_payload(
                            project_key=str(request.project_key or ""),
                            item=item,
                            query_terms=term_batch,
                            max_candidates=batch_max_candidates,
                            write_to_pool=(False if use_two_phase else bool(override_params.get("write_to_pool", True))),
                            pool_scope=pool_scope,
                            probe_timeout=float(override_params.get("probe_timeout") or 10.0),
                            sitemap_max_depth=sitemap_max_depth,
                            sitemap_max_sitemaps=sitemap_max_sitemaps,
                            auto_ingest=(False if use_two_phase else auto_ingest_enabled),
                            ingest_limit=batch_ingest_limit,
                            enable_extraction=bool(override_params.get("enable_extraction", True)),
                            allow_term_fallback=_as_bool(
                                override_params.get("allow_term_fallback"),
                                True,
                            ),
                            allow_entry_type_fallback=_as_bool(
                                override_params.get("allow_entry_type_fallback"),
                                True,
                            ),
                        )
                        run_site_entries = list(preview.site_entries_used or [])
                        run_candidates = [
                            str(u or "").strip()
                            for u in (preview.candidates or [])
                            if str(u or "").strip()
                        ]
                        run_errors = list(preview.errors or [])
                        run_written = dict(preview.written or {})
                        run_ingest_result = dict(preview.ingest_result or {})

                        if use_two_phase:
                            selected_urls: list[str] = []
                            for candidate_url in run_candidates:
                                cid = _candidate_id(candidate_url)
                                selected = bool(cid in explicit_candidate_ids) if explicit_candidate_ids else (execution_mode == "apply")
                                if cid not in seen_candidate_id:
                                    seen_candidate_id.add(cid)
                                    all_candidate_records.append(
                                        {"candidate_id": cid, "url": candidate_url, "selected": selected}
                                    )
                                if selected:
                                    selected_urls.append(candidate_url)
                                    selected_candidate_ids.add(cid)

                            run_written = {"urls_new": 0, "urls_skipped": 0}
                            run_ingest_result = {
                                "inserted": 0,
                                "updated": 0,
                                "skipped": 0,
                                "inserted_valid": 0,
                                "rejected_count": 0,
                                "rejection_breakdown": {},
                            }
                            if execution_mode == "apply" and selected_urls:
                                batch_source = (
                                    f"source_library.apply.{str(request.item_key or '').strip()}."
                                    f"{batch_idx + 1}.{_candidate_id('|'.join(term_batch))[:8]}"
                                )
                                urls_new = 0
                                urls_skipped = 0
                                for selected_url in selected_urls:
                                    wrote = append_url(
                                        url=selected_url,
                                        source=batch_source,
                                        source_ref={
                                            "item_key": str(request.item_key or ""),
                                            "query_terms": term_batch,
                                            "trace_id": trace_id,
                                        },
                                        scope=pool_scope,
                                        project_key=str(request.project_key or ""),
                                    )
                                    if wrote:
                                        urls_new += 1
                                    else:
                                        urls_skipped += 1
                                run_written = {"urls_new": urls_new, "urls_skipped": urls_skipped}
                                if auto_ingest_enabled:
                                    run_ingest_result = dict(
                                        collect_urls_from_pool(
                                            scope=pool_scope,
                                            project_key=str(request.project_key or ""),
                                            source_filter=batch_source,
                                            limit=min(batch_ingest_limit, max(1, len(selected_urls))),
                                            query_terms=term_batch,
                                            enable_extraction=bool(override_params.get("enable_extraction", True)),
                                            extra_params={
                                                "single_url_strict_mode": override_params.get("single_url_strict_mode"),
                                                "single_url_async": override_params.get("single_url_async"),
                                            },
                                        )
                                        or {}
                                    )
                            elif explicit_candidate_ids and execution_mode == "apply":
                                run_errors.append(
                                    {
                                        "phase": "explicit_candidate_ids",
                                        "error": "no candidate matched explicit_candidate_ids in current preview window",
                                    }
                                )
                        else:
                            for candidate_url in run_candidates:
                                cid = _candidate_id(candidate_url)
                                if cid in seen_candidate_id:
                                    continue
                                seen_candidate_id.add(cid)
                                all_candidate_records.append({"candidate_id": cid, "url": candidate_url, "selected": True})
                                selected_candidate_ids.add(cid)

                        normalized_runs.append(
                            {
                                "site_entries_used": run_site_entries,
                                "candidates": run_candidates,
                                "errors": run_errors,
                                "written": run_written,
                                "ingest_result": run_ingest_result,
                            }
                        )

                    benign_markers = {"url_term_filter_empty_fallback_used", "url_term_filter_empty_no_fallback"}
                    merged_site_entries = []
                    seen_entry = set()
                    merged_candidates = []
                    seen_cand = set()
                    merged_error_details = []
                    merged_errors = []
                    inserted_total = 0
                    updated_total = 0
                    skipped_total = 0
                    inserted_valid_total = 0
                    rejected_count_total = 0
                    rejection_breakdown_total: dict[str, int] = {}
                    degradation_flags_total: set[str] = set()
                    quality_scores: list[float] = []
                    written_urls_new = 0
                    written_urls_skipped = 0
                    ingest_inserted = 0
                    ingest_updated = 0
                    ingest_skipped = 0
                    for run in normalized_runs:
                        for e in (run.get("site_entries_used") or []):
                            key = str(e.get("site_url") or e.get("id") or "")
                            if key and key not in seen_entry:
                                seen_entry.add(key)
                                merged_site_entries.append(e)
                        for u in (run.get("candidates") or []):
                            s = str(u or "").strip()
                            if s and s not in seen_cand:
                                seen_cand.add(s)
                                merged_candidates.append(s)
                        for e in (run.get("errors") or []):
                            if not isinstance(e, dict):
                                continue
                            merged_error_details.append(e)
                            msg = str(e.get("error") or "").strip()
                            if msg and msg not in benign_markers:
                                merged_errors.append(msg)
                        w = run.get("written") or {}
                        written_urls_new += int(w.get("urls_new") or 0)
                        written_urls_skipped += int(w.get("urls_skipped") or 0)
                        ir = run.get("ingest_result") or {}
                        ingest_inserted += int(ir.get("inserted") or 0)
                        ingest_updated += int(ir.get("updated") or 0)
                        ingest_skipped += int(ir.get("skipped") or 0)
                        inserted_valid_total += int(ir.get("inserted_valid") or 0)
                        rejected_count_total += int(ir.get("rejected_count") or 0)
                        rb = ir.get("rejection_breakdown")
                        if isinstance(rb, dict):
                            for key, value in rb.items():
                                reason = normalize_reason_code(key, default="unknown_rejection_reason")
                                if not reason:
                                    continue
                                try:
                                    count = int(value or 0)
                                except Exception:
                                    count = 0
                                if count <= 0:
                                    continue
                                rejection_breakdown_total[reason] = int(rejection_breakdown_total.get(reason) or 0) + count
                        flags = ir.get("degradation_flags")
                        if isinstance(flags, list):
                            for flag in flags:
                                name = str(flag or "").strip()
                                if name:
                                    degradation_flags_total.add(name)
                        try:
                            qv = float(ir.get("quality_score"))
                        except Exception:
                            qv = None
                        if qv is not None and qv >= 0:
                            quality_scores.append(qv)
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
                            "inserted_valid": inserted_valid_total,
                            "rejected_count": rejected_count_total,
                            "rejection_breakdown": rejection_breakdown_total,
                            "degradation_flags": sorted(degradation_flags_total),
                            "quality_score": (sum(quality_scores) / len(quality_scores)) if quality_scores else None,
                            "errors": merged_errors,
                            "item_key": str(request.item_key or ""),
                            "query_terms": q,
                            "per_keyword_limit": per_keyword_limit,
                            "query_term_batches": term_batches,
                            "batches_total": len(term_batches),
                            "site_entries_used": merged_site_entries,
                            "candidates": merged_candidates,
                            "candidate_records": all_candidate_records,
                            "selected_candidate_ids": sorted(selected_candidate_ids),
                            "execution_mode": execution_mode,
                            "write_applied": execution_mode == "apply",
                            "explicit_candidate_ids": sorted(explicit_candidate_ids),
                            "written": {
                                "urls_new": written_urls_new,
                                "urls_skipped": written_urls_skipped,
                            },
                            "single_write_workflow": "single_url",
                            "ingest_result": {
                                "inserted": ingest_inserted,
                                "updated": ingest_updated,
                                "skipped": ingest_skipped,
                                "inserted_valid": inserted_valid_total,
                                "rejected_count": rejected_count_total,
                                "rejection_breakdown": rejection_breakdown_total,
                            },
                            "error_details": merged_error_details,
                        },
                    }
                else:
                    # Non-cluster path forces WF-1 guarded flow by default.
                    override_params.setdefault("force_single_url_flow", True)
                    override_params.setdefault("prefer_crawler_first", False)
                    override_params.setdefault("auto_ingest_crawler_output", False)
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
