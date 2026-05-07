#!/usr/bin/env python3
"""External smoke: keyword -> source library -> structured project material.

This is intentionally a real-chain smoke, not a unit test. It imports a curated
source preset pack, creates a temporary source-library item, then verifies the
keyword collection service can find candidates and push material into the
project document pipeline.

Usage:
  PROJECT_KEY=online_lottery python -m scripts.test_source_library_keyword_collect_smoke

Useful knobs:
  SOURCE_LIBRARY_SMOKE_QUERY="artificial intelligence startup funding"
  SOURCE_LIBRARY_SMOKE_MIN_CANDIDATES=3
  SOURCE_LIBRARY_SMOKE_MIN_VALID=1
  SOURCE_LIBRARY_SMOKE_INGEST_LIMIT=5
"""

from __future__ import annotations

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PROJECT_KEY = os.environ.get("PROJECT_KEY", "online_lottery")
PACK_KEY = os.environ.get("SOURCE_LIBRARY_SMOKE_PACK", "keyword_research_foundation")
ITEM_KEY = os.environ.get("SOURCE_LIBRARY_SMOKE_ITEM_KEY", "smoke.keyword_research_foundation")
QUERY = os.environ.get("SOURCE_LIBRARY_SMOKE_QUERY", "artificial intelligence startup funding")
MAX_CANDIDATES = int(os.environ.get("SOURCE_LIBRARY_SMOKE_MAX_CANDIDATES", "80"))
INGEST_LIMIT = int(os.environ.get("SOURCE_LIBRARY_SMOKE_INGEST_LIMIT", "5"))
MIN_CANDIDATES = int(os.environ.get("SOURCE_LIBRARY_SMOKE_MIN_CANDIDATES", "3"))
MIN_VALID = int(os.environ.get("SOURCE_LIBRARY_SMOKE_MIN_VALID", "1"))


def _terms(raw: str) -> list[str]:
    out = []
    for chunk in str(raw or "").replace(";", ",").split(","):
        value = " ".join(chunk.split()).strip()
        if value and value not in out:
            out.append(value)
    return out or ["artificial intelligence startup funding"]


def _ensure_smoke_item(*, project_key: str, item_key: str, site_entries: list[str]) -> None:
    from app.models.base import SessionLocal
    from app.models.entities import SourceLibraryItem
    from app.services.projects import bind_project

    with bind_project(project_key):
        with SessionLocal() as session:
            row = session.query(SourceLibraryItem).filter(SourceLibraryItem.item_key == item_key).first()
            if row is None:
                row = SourceLibraryItem(item_key=item_key)
                session.add(row)
            row.name = "Smoke Keyword Research Foundation"
            row.channel_key = "handler.cluster"
            row.description = "Temporary real-chain smoke item for keyword source-library collection."
            row.params = {
                "site_entries": site_entries,
                "candidate_target_config": {
                    "mode": "equal_domain_mix",
                    "target_per_bucket": 2,
                    "allow_wave_early_stop": True,
                },
            }
            row.tags = ["smoke", "keyword_research", "temporary"]
            row.enabled = True
            row.extra = {
                "item_type": "service_aggregated",
                "managed_by": "system",
                "stable_handler_cluster": True,
                "creation_handler": "handler.entry_type.keyword_research_smoke",
                "allow_mixed_entry_types": True,
            }
            session.commit()


def _remove_smoke_item(*, project_key: str, item_key: str) -> None:
    from app.models.base import SessionLocal
    from app.models.entities import SourceLibraryItem
    from app.services.projects import bind_project

    with bind_project(project_key):
        with SessionLocal() as session:
            session.query(SourceLibraryItem).filter(SourceLibraryItem.item_key == item_key).delete()
            session.commit()


def run_smoke() -> dict:
    from app.services.projects.bootstrap import ensure_project_schema_ready
    from app.services.resource_pool.open_source_source_importer import import_open_source_preset_pack
    from app.services.resource_pool.open_source_source_presets import get_open_source_preset_pack
    from app.services.resource_pool.unified_search import unified_search_by_item

    query_terms = _terms(QUERY)
    ensure_project_schema_ready(PROJECT_KEY, name="Online Lottery")
    logger.info("Importing source preset pack=%s project_key=%s", PACK_KEY, PROJECT_KEY)
    imported = import_open_source_preset_pack(
        pack_key=PACK_KEY,
        scope="project",
        project_key=PROJECT_KEY,
        enabled=True,
        extra_tags=["keyword_collect_smoke"],
    )
    pack = get_open_source_preset_pack(PACK_KEY)
    site_entries = [entry.site_url for entry in pack.entries if str(entry.site_url or "").strip()]
    if not site_entries:
        raise RuntimeError(f"preset pack has no site entries: {PACK_KEY}")

    _ensure_smoke_item(project_key=PROJECT_KEY, item_key=ITEM_KEY, site_entries=site_entries)
    try:
        logger.info(
            "Running keyword collection item=%s terms=%s max_candidates=%d ingest_limit=%d",
            ITEM_KEY,
            query_terms,
            MAX_CANDIDATES,
            INGEST_LIMIT,
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
            enable_extraction=True,
            allow_term_fallback=True,
        )
    finally:
        if os.environ.get("SOURCE_LIBRARY_SMOKE_KEEP_ITEM", "").strip().lower() not in {"1", "true", "yes"}:
            _remove_smoke_item(project_key=PROJECT_KEY, item_key=ITEM_KEY)

    ingest_result = result.ingest_result if isinstance(result.ingest_result, dict) else {}
    inserted = int(ingest_result.get("inserted") or 0)
    inserted_valid = int(ingest_result.get("inserted_valid") or inserted or 0)
    queued = int(ingest_result.get("queued") or 0)
    summary = {
        "project_key": PROJECT_KEY,
        "pack_key": imported.pack_key,
        "item_key": ITEM_KEY,
        "query_terms": result.query_terms,
        "site_entries_used": len(result.site_entries_used or []),
        "candidates_found": len(result.candidates or []),
        "urls_written": result.written,
        "documents_inserted": inserted,
        "documents_inserted_valid": inserted_valid,
        "documents_queued": queued,
        "errors": result.errors,
        "thresholds": {
            "min_candidates": MIN_CANDIDATES,
            "min_valid": MIN_VALID,
        },
    }
    logger.info("Smoke summary: %s", summary)

    if summary["candidates_found"] < MIN_CANDIDATES:
        raise RuntimeError(
            f"candidate threshold failed: found={summary['candidates_found']} min={MIN_CANDIDATES}; errors={result.errors}"
        )
    if inserted_valid + queued < MIN_VALID:
        raise RuntimeError(
            f"valid material threshold failed: valid_or_queued={inserted_valid + queued} min={MIN_VALID}; "
            f"ingest_result={ingest_result}; errors={result.errors}"
        )
    return summary


def main() -> int:
    try:
        run_smoke()
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.exception("source library keyword collect smoke failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
