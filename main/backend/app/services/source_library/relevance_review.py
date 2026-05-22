"""Deterministic relevance-review queue envelope for source-library candidates."""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from typing import Any
from urllib.parse import urlparse


CONTRACT_VERSION = "source_library.relevance_review_queue.v1"

REASON_CODE_ORDER = (
    "fallback_anchor_only_profile",
    "term_fallback_candidates",
    "low_confidence_candidate",
    "adapter_capability_review",
    "source_marked_review_required",
)

REVIEWER_FIELD_KEYS = (
    "url",
    "domain",
    "query_terms",
    "source_library_item_key",
    "project_key",
    "site_entry_url",
    "entry_domain",
    "site_policy",
    "search_service",
    "candidate_source",
    "matched_by",
    "candidate_quality",
    "route_kind",
    "parser_profile_resolved",
    "adapter_capability_status",
    "adapter_capability_reason",
)


def build_relevance_review_queue(
    *,
    project_key: str | None,
    item_key: str,
    query_terms: list[str] | str | None,
    candidates: list[str],
    candidate_refs: dict[str, dict[str, Any]] | None = None,
    runtime_diagnostics: list[dict[str, Any]] | None = None,
    errors: list[dict[str, Any]] | None = None,
    source_surface: str = "resource_pool.unified_search",
) -> dict[str, Any]:
    """Build a fail-closed review queue for low-confidence selected candidates.

    The queue is deterministic and intentionally does not represent completed
    human review or live public replay. It only makes records reviewer-ready.
    """

    terms = _as_terms(query_terms)
    refs = candidate_refs or {}
    runtime_by_site = _runtime_by_site_url(runtime_diagnostics or [])
    errors_by_site = _errors_by_site_url(errors or [])
    entries: list[dict[str, Any]] = []

    for position, raw_url in enumerate(candidates):
        url = _clean(raw_url)
        if not url:
            continue
        ref = dict(refs.get(url) or {})
        site_entry_url = _clean(ref.get("site_entry_url"))
        runtime = runtime_by_site.get(site_entry_url, {})
        local_errors = errors_by_site.get(site_entry_url, [])
        reason_codes = _review_reason_codes(ref=ref, runtime=runtime, errors=local_errors)
        if not reason_codes:
            continue
        entries.append(
            _queue_entry(
                project_key=_clean(project_key),
                item_key=_clean(item_key),
                query_terms=terms,
                url=url,
                position=position,
                ref=ref,
                runtime=runtime,
                errors=local_errors,
                reason_codes=reason_codes,
                source_surface=source_surface,
            )
        )

    return _queue_envelope(
        project_key=_clean(project_key),
        item_key=_clean(item_key),
        query_terms=terms,
        entries=entries,
        source_surface=source_surface,
    )


def merge_relevance_review_queues(
    queues: list[dict[str, Any]] | None,
    *,
    project_key: str | None,
    item_key: str,
    query_terms: list[str] | str | None,
    source_surface: str,
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for queue in queues or []:
        if not isinstance(queue, dict):
            continue
        for entry in queue.get("entries") or []:
            if not isinstance(entry, dict):
                continue
            queue_id = _clean(entry.get("queue_id"))
            if not queue_id or queue_id in seen:
                continue
            seen.add(queue_id)
            entries.append(dict(entry))
    entries.sort(key=lambda row: _clean(row.get("queue_id")))
    return _queue_envelope(
        project_key=_clean(project_key),
        item_key=_clean(item_key),
        query_terms=_as_terms(query_terms),
        entries=entries,
        source_surface=source_surface,
    )


def annotate_records_with_relevance_review_queue(
    records: list[dict[str, Any]],
    queue: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(queue, dict):
        return records
    by_url = {
        _clean((entry.get("reviewer_fields") or {}).get("url")): entry
        for entry in queue.get("entries") or []
        if isinstance(entry, dict)
    }
    if not by_url:
        return records

    annotated: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            annotated.append(record)
            continue
        url = _clean(record.get("url"))
        entry = by_url.get(url)
        if not entry:
            annotated.append(record)
            continue
        updated = dict(record)
        meta = dict(updated.get("record_meta") or {})
        meta["source_library_relevance_review"] = {
            "contract_version": CONTRACT_VERSION,
            "queue_id": _clean(entry.get("queue_id")),
            "state": "review_required",
            "reason_codes": list(entry.get("reason_codes") or []),
            "auto_accept_allowed": False,
            "auto_ingest_allowed": False,
            "review_completed": False,
            "live_public_replay_completed": False,
        }
        updated["record_meta"] = meta
        annotated.append(updated)
    return annotated


def _queue_envelope(
    *,
    project_key: str,
    item_key: str,
    query_terms: list[str],
    entries: list[dict[str, Any]],
    source_surface: str,
) -> dict[str, Any]:
    reason_counts: Counter[str] = Counter()
    for entry in entries:
        reason_counts.update(str(code) for code in entry.get("reason_codes") or [])
    return {
        "contract_version": CONTRACT_VERSION,
        "queue_state": "ready_for_review" if entries else "empty",
        "source_surface": _clean(source_surface),
        "project_key": project_key or None,
        "source_library_item_key": item_key,
        "query_terms": list(query_terms),
        "entries": entries,
        "summary": {
            "queued_count": len(entries),
            "reason_code_counts": dict(sorted(reason_counts.items())),
            "reviewer_ready_count": len(entries),
            "fail_closed": True,
            "auto_accept_allowed": False,
            "auto_ingest_allowed": False,
        },
        "gap_markers": _gap_markers(),
    }


def _queue_entry(
    *,
    project_key: str,
    item_key: str,
    query_terms: list[str],
    url: str,
    position: int,
    ref: dict[str, Any],
    runtime: dict[str, Any],
    errors: list[dict[str, Any]],
    reason_codes: list[str],
    source_surface: str,
) -> dict[str, Any]:
    reviewer_fields = {
        "url": url,
        "domain": _clean(ref.get("domain")) or _domain(url),
        "query_terms": list(query_terms),
        "source_library_item_key": item_key,
        "project_key": project_key or None,
        "site_entry_url": _clean(ref.get("site_entry_url")) or None,
        "entry_domain": _clean(ref.get("entry_domain")) or _clean(runtime.get("domain")) or None,
        "site_policy": _clean(ref.get("site_policy")) or _clean(runtime.get("site_policy")) or None,
        "search_service": _clean(ref.get("search_service")) or _clean(runtime.get("search_service")) or None,
        "candidate_source": _clean(ref.get("candidate_source")) or None,
        "matched_by": _clean(ref.get("matched_by")) or None,
        "candidate_quality": _clean(ref.get("candidate_quality")) or None,
        "route_kind": _clean(ref.get("route_kind")) or None,
        "parser_profile_resolved": _clean(ref.get("parser_profile_resolved"))
        or _clean(runtime.get("parser_profile_resolved"))
        or None,
        "adapter_capability_status": _clean(ref.get("adapter_capability_status"))
        or _clean(runtime.get("adapter_capability_status"))
        or None,
        "adapter_capability_reason": _clean(ref.get("adapter_capability_reason"))
        or _clean(runtime.get("adapter_capability_reason"))
        or None,
    }
    missing = [
        key
        for key in ("url", "domain", "query_terms", "source_library_item_key")
        if reviewer_fields.get(key) in (None, "", [])
    ]
    seed = {
        "contract_version": CONTRACT_VERSION,
        "item_key": item_key,
        "project_key": project_key,
        "query_terms": query_terms,
        "reason_codes": reason_codes,
        "site_entry_url": reviewer_fields["site_entry_url"],
        "url": url,
    }
    return {
        "queue_id": f"sl_review:{sha256(_stable_json(seed).encode('utf-8')).hexdigest()[:16]}",
        "contract_version": CONTRACT_VERSION,
        "queue_state": "review_required",
        "position": position,
        "reason_codes": list(reason_codes),
        "reviewer_ready": not missing,
        "reviewer_fields_missing": missing,
        "reviewer_fields": reviewer_fields,
        "source_trace": {
            "source_surface": _clean(source_surface),
            "runtime_relevance_review_reason": _clean(runtime.get("relevance_review_reason")) or None,
            "runtime_search_template_adapter": _clean(runtime.get("search_template_adapter")) or None,
            "runtime_search_template_adapter_mode": _clean(runtime.get("search_template_adapter_mode")) or None,
            "runtime_errors": [_public_error(row) for row in errors],
            "candidate_ref": _public_ref(ref),
        },
        "fail_closed": {
            "state": "review_required",
            "auto_accept_allowed": False,
            "auto_ingest_allowed": False,
            "requires_human_relevance_review": True,
        },
        "gap_markers": _gap_markers(),
    }


def _review_reason_codes(
    *,
    ref: dict[str, Any],
    runtime: dict[str, Any],
    errors: list[dict[str, Any]],
) -> list[str]:
    candidates: set[str] = set()
    parser_profile = _clean(ref.get("parser_profile_resolved")) or _clean(runtime.get("parser_profile_resolved"))
    adapter_status = _clean(ref.get("adapter_capability_status")) or _clean(runtime.get("adapter_capability_status"))
    adapter_reason = _clean(ref.get("adapter_capability_reason")) or _clean(runtime.get("adapter_capability_reason"))
    review_reason = _clean(ref.get("relevance_review_reason")) or _clean(runtime.get("relevance_review_reason"))
    matched_by_present = "matched_by" in ref
    matched_by = _clean(ref.get("matched_by"))
    quality_present = "candidate_quality" in ref
    quality = _clean(ref.get("candidate_quality")).lower()

    if parser_profile == "fallback_anchor_only" or adapter_reason == "low_confidence_anchor_only_profile":
        candidates.add("fallback_anchor_only_profile")
    if adapter_status == "review":
        candidates.add("adapter_capability_review")
    if "term_fallback" in review_reason or any(_clean(row.get("error")) == "url_term_filter_empty_fallback_used" for row in errors):
        candidates.add("term_fallback_candidates")
    if bool(ref.get("relevance_review_required")) or bool(runtime.get("relevance_review_required")):
        if not candidates:
            candidates.add("source_marked_review_required")
    if matched_by_present and matched_by in {"", "none"}:
        candidates.add("low_confidence_candidate")
    if quality_present and quality in {"", "low", "unknown", "none"}:
        candidates.add("low_confidence_candidate")
    if ref.get("usable_for_search") is False:
        candidates.add("low_confidence_candidate")

    return [code for code in REASON_CODE_ORDER if code in candidates]


def _runtime_by_site_url(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        site_url = _clean(row.get("site_url"))
        if site_url:
            out[site_url] = dict(row)
    return out


def _errors_by_site_url(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        site_url = _clean(row.get("site_url"))
        if site_url:
            out.setdefault(site_url, []).append(dict(row))
    return out


def _as_terms(value: list[str] | str | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _domain(url: str) -> str | None:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        return host[4:]
    return host or None


def _gap_markers() -> dict[str, Any]:
    return {
        "human_relevance_review_completed": False,
        "live_public_replay_completed": False,
        "review_completion_claim": "not_claimed",
        "public_replay_claim": "not_claimed",
        "live_replay_gap": "live_public_replay_not_run",
    }


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _public_error(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "site_url": _clean(row.get("site_url")) or None,
        "error": _clean(row.get("error")) or None,
        "error_class": _clean(row.get("error_class")) or None,
        "search_service_used": _clean(row.get("search_service_used")) or None,
    }


def _public_ref(ref: dict[str, Any]) -> dict[str, Any]:
    return {
        key: ref.get(key)
        for key in (
            "site_entry_url",
            "entry_type",
            "entry_domain",
            "candidate_source",
            "site_policy",
            "search_service",
            "matched_by",
            "route_kind",
            "candidate_quality",
            "usable_for_search",
            "adapter_capability_status",
            "parser_profile_resolved",
            "candidate_review_state",
            "relevance_review_required",
        )
        if key in ref
    }
