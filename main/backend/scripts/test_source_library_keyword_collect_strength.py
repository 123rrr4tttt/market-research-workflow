#!/usr/bin/env python3
"""Strength profile: keyword -> source library -> many candidates -> project material.

This profile is intentionally heavier than smoke. It is meant for answering:
"Given user keywords/basic info, how much material can the source library find
and push into downstream project flows?"

Usage:
  PROJECT_KEY=online_lottery python -m scripts.test_source_library_keyword_collect_strength

Useful knobs:
  SOURCE_LIBRARY_STRENGTH_QUERY="artificial intelligence startup funding"
  SOURCE_LIBRARY_STRENGTH_MAX_CANDIDATES=500
  SOURCE_LIBRARY_STRENGTH_INGEST_LIMIT=50
  SOURCE_LIBRARY_STRENGTH_MIN_CANDIDATES=100
  SOURCE_LIBRARY_STRENGTH_MIN_VALID=20
"""

from __future__ import annotations

from collections import Counter
import json
import logging
import os
import sys
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.test_source_library_keyword_collect_smoke import (  # noqa: E402
    _ensure_smoke_item,
    _remove_smoke_item,
    _terms,
)


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PROJECT_KEY = os.environ.get("PROJECT_KEY", "online_lottery")
PACK_KEY = os.environ.get("SOURCE_LIBRARY_STRENGTH_PACK", "keyword_research_foundation")
ITEM_KEY = os.environ.get("SOURCE_LIBRARY_STRENGTH_ITEM_KEY", "strength.keyword_research_foundation")
QUERY = os.environ.get("SOURCE_LIBRARY_STRENGTH_QUERY", "artificial intelligence startup funding")
MAX_CANDIDATES = int(os.environ.get("SOURCE_LIBRARY_STRENGTH_MAX_CANDIDATES", "500"))
INGEST_LIMIT = int(os.environ.get("SOURCE_LIBRARY_STRENGTH_INGEST_LIMIT", "50"))
MIN_CANDIDATES = int(os.environ.get("SOURCE_LIBRARY_STRENGTH_MIN_CANDIDATES", "100"))
MIN_VALID = int(os.environ.get("SOURCE_LIBRARY_STRENGTH_MIN_VALID", "20"))
ENABLE_EXTRACTION = os.environ.get("SOURCE_LIBRARY_STRENGTH_ENABLE_EXTRACTION", "true").strip().lower() not in {
    "0",
    "false",
    "no",
}


def _domain(url: str) -> str:
    try:
        return (urlsplit(url).netloc or "").lower()
    except Exception:
        return ""


def _error_key(error: dict) -> str:
    return str(error.get("error_class") or error.get("error") or error.get("phase") or "unknown").strip() or "unknown"


def _top(counter: Counter, limit: int = 12) -> list[dict[str, int | str]]:
    return [{"key": key, "count": count} for key, count in counter.most_common(limit)]


def run_strength() -> dict:
    from app.services.projects.bootstrap import ensure_project_schema_ready
    from app.services.resource_pool.open_source_source_importer import import_open_source_preset_pack
    from app.services.resource_pool.open_source_source_presets import get_open_source_preset_pack
    from app.services.resource_pool.unified_search import unified_search_by_item

    query_terms = _terms(QUERY)
    ensure_project_schema_ready(PROJECT_KEY, name="Online Lottery")
    imported = import_open_source_preset_pack(
        pack_key=PACK_KEY,
        scope="project",
        project_key=PROJECT_KEY,
        enabled=True,
        extra_tags=["keyword_collect_strength"],
    )
    pack = get_open_source_preset_pack(PACK_KEY)
    site_entries = [entry.site_url for entry in pack.entries if str(entry.site_url or "").strip()]
    if not site_entries:
        raise RuntimeError(f"preset pack has no site entries: {PACK_KEY}")

    _ensure_smoke_item(project_key=PROJECT_KEY, item_key=ITEM_KEY, site_entries=site_entries)
    try:
        logger.info(
            "Running strength profile item=%s terms=%s max_candidates=%d ingest_limit=%d extraction=%s",
            ITEM_KEY,
            query_terms,
            MAX_CANDIDATES,
            INGEST_LIMIT,
            ENABLE_EXTRACTION,
        )
        result = unified_search_by_item(
            project_key=PROJECT_KEY,
            item_key=ITEM_KEY,
            query_terms=query_terms,
            max_candidates=MAX_CANDIDATES,
            write_to_pool=True,
            pool_scope="project",
            auto_ingest=True,
            ingest_limit=INGEST_LIMIT,
            enable_extraction=ENABLE_EXTRACTION,
            allow_term_fallback=True,
        )
    finally:
        if os.environ.get("SOURCE_LIBRARY_STRENGTH_KEEP_ITEM", "").strip().lower() not in {"1", "true", "yes"}:
            _remove_smoke_item(project_key=PROJECT_KEY, item_key=ITEM_KEY)

    candidates = list(result.candidates or [])
    ingest_result = result.ingest_result if isinstance(result.ingest_result, dict) else {}
    debug = ingest_result.get("debug") if isinstance(ingest_result.get("debug"), dict) else {}
    metrics = ingest_result.get("metrics_payload") if isinstance(ingest_result.get("metrics_payload"), dict) else {}
    inserted = int(ingest_result.get("inserted") or 0)
    inserted_valid = int(ingest_result.get("inserted_valid") or inserted or 0)
    queued = int(ingest_result.get("queued") or 0)
    errors = [e for e in (result.errors or []) if isinstance(e, dict)]
    source_domains = Counter(_domain(str(e.get("site_url") or "")) for e in (result.site_entries_used or []))
    candidate_domains = Counter(_domain(url) for url in candidates)

    summary = {
        "contract_version": "source_library.keyword_collect.strength.v1",
        "project_key": PROJECT_KEY,
        "pack_key": imported.pack_key,
        "item_key": ITEM_KEY,
        "query_terms": result.query_terms,
        "config": {
            "max_candidates": MAX_CANDIDATES,
            "ingest_limit": INGEST_LIMIT,
            "enable_extraction": ENABLE_EXTRACTION,
        },
        "source_coverage": {
            "site_entries_used": len(result.site_entries_used or []),
            "source_domains": _top(source_domains),
            "candidate_domains": _top(candidate_domains),
            "candidate_domain_count": len([k for k in candidate_domains if k]),
        },
        "candidate_summary": {
            "found": len(candidates),
            "unique_urls": len(set(candidates)),
        },
        "write_summary": result.written or {},
        "ingest_summary": {
            "inserted": inserted,
            "inserted_valid": inserted_valid,
            "queued": queued,
            "skipped": int(ingest_result.get("skipped") or 0),
            "rejected_count": int(ingest_result.get("rejected_count") or 0),
            "urls_attempted": int(ingest_result.get("urls") or 0),
            "url_only_document_rate": metrics.get("url_only_document_rate"),
            "empty_body_rate": metrics.get("empty_body_rate"),
            "ingest_candidates_count": debug.get("ingest_candidates_count"),
        },
        "error_summary": {
            "total": len(errors),
            "top_errors": _top(Counter(_error_key(e) for e in errors)),
            "top_error_domains": _top(Counter(_domain(str(e.get("site_url") or "")) for e in errors)),
        },
        "thresholds": {
            "min_candidates": MIN_CANDIDATES,
            "min_valid": MIN_VALID,
        },
        "ready_for_project_flows": bool(inserted_valid + queued >= MIN_VALID),
    }
    logger.info("Strength summary:\n%s", json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))

    if summary["candidate_summary"]["found"] < MIN_CANDIDATES:
        raise RuntimeError(
            f"candidate threshold failed: found={summary['candidate_summary']['found']} min={MIN_CANDIDATES}"
        )
    if inserted_valid + queued < MIN_VALID:
        raise RuntimeError(f"valid material threshold failed: valid_or_queued={inserted_valid + queued} min={MIN_VALID}")
    return summary


def main() -> int:
    try:
        run_strength()
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.exception("source library keyword collect strength failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
