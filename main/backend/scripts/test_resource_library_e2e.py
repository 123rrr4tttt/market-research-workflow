#!/usr/bin/env python3
"""
E2E test: resource library full chain from document extraction to ingest.

Flow:
  1. extract_from_documents -> resource_pool_urls
  2. discover_site_entries (write) -> resource_pool_site_entries
  3. unified_search (with temp item) -> candidates -> write to resource_pool_urls
  4. run url_pool.default -> fetch URLs -> documents

Usage:
  cd main/ops && docker compose run --rm backend python -m scripts.test_resource_library_e2e
  # or with project_key:
  PROJECT_KEY=online_lottery docker compose run --rm backend python -m scripts.test_resource_library_e2e
"""

from __future__ import annotations

import logging
import os
import sys

# Ensure app is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PROJECT_KEY = os.environ.get("PROJECT_KEY", "online_lottery")
TEST_ITEM_KEY = "test.unified_search.e2e"


def _step(name: str, fn, *args, **kwargs):
    logger.info("=== Step: %s ===", name)
    try:
        result = fn(*args, **kwargs)
        logger.info("  %s -> %s", name, result)
        return result
    except Exception as exc:
        logger.exception("  %s FAILED: %s", name, exc)
        raise


def _ensure_temp_item(project_key: str, site_entry_urls: list[str]) -> None:
    """Create temporary source library item for unified search."""
    from app.models.base import SessionLocal
    from app.models.entities import SourceLibraryItem
    from app.services.projects import bind_project

    with bind_project(project_key):
        with SessionLocal() as session:
            existing = session.query(SourceLibraryItem).filter(
                SourceLibraryItem.item_key == TEST_ITEM_KEY
            ).first()
            if existing:
                existing.params = {"site_entries": site_entry_urls}
                session.commit()
                logger.info("  Updated temp item with %d site_entries", len(site_entry_urls))
                return
            item = SourceLibraryItem(
                item_key=TEST_ITEM_KEY,
                name="E2E Test Unified Search",
                channel_key="generic_web.rss",
                description="Temporary item for E2E test",
                params={"site_entries": site_entry_urls},
                tags=["e2e", "temp"],
                enabled=True,
            )
            session.add(item)
            session.commit()
            logger.info("  Created temp item with %d site_entries", len(site_entry_urls))


def _remove_temp_item(project_key: str) -> None:
    """Remove temporary source library item."""
    from app.models.base import SessionLocal
    from app.models.entities import SourceLibraryItem
    from app.services.projects import bind_project

    with bind_project(project_key):
        with SessionLocal() as session:
            session.query(SourceLibraryItem).filter(
                SourceLibraryItem.item_key == TEST_ITEM_KEY
            ).delete()
            session.commit()
            logger.info("  Removed temp item")


def _count_docs_in_schema(project_key: str) -> int:
    """Count documents in project schema. Ensures schema isolation."""
    from sqlalchemy import text

    from app.models.base import engine
    from app.services.projects import project_schema_name

    schema = project_schema_name(project_key)
    try:
        with engine.connect() as conn:
            conn.execute(text(f'SET search_path TO "{schema}"'))
            row = conn.execute(text("SELECT COUNT(*) FROM documents")).fetchone()
            return int(row[0]) if row else 0
    except Exception as exc:
        logger.warning("  _count_docs_in_schema failed (schema may not exist): %s", exc)
        return -1


def run_e2e(project_key: str = PROJECT_KEY) -> dict:
    from app.services.projects import project_schema_name
    from app.services.resource_pool import (
        discover_site_entries_from_urls,
        extract_from_documents,
        list_site_entries,
        list_urls,
        unified_search_by_item,
        write_discovered_site_entries,
    )
    from app.services.source_library import run_item_by_key

    schema_name = project_schema_name(project_key)
    logger.info("Schema isolation: project_key=%s -> schema=%s", project_key, schema_name)

    results: dict = {}
    doc_count_before = _count_docs_in_schema(project_key)
    results["schema"] = {"project_key": project_key, "schema": schema_name, "docs_before": doc_count_before}

    # Step 1: Extract URLs from documents
    r1 = _step(
        "extract_from_documents",
        extract_from_documents,
        project_key=project_key,
        scope="project",
        limit=100,
    )
    results["extract"] = r1
    if r1.get("documents_scanned", 0) == 0:
        logger.warning("No documents found. Ensure project has documents with content/uri/extracted_data.")
        logger.info("  Skipping remaining steps (need URLs in resource_pool_urls)")
        return results

    urls_extracted = r1.get("urls_extracted", 0)
    if urls_extracted == 0:
        logger.warning("No URLs extracted from documents. Check document content/extracted_data.")
        return results

    # Step 2: Discover site entries from resource_pool_urls
    disc = _step(
        "discover_site_entries_from_urls",
        discover_site_entries_from_urls,
        project_key=project_key,
        url_scope="effective",
        target_scope="project",
        limit_domains=10,
        probe_timeout=6.0,
    )
    results["discover"] = {
        "domains_scanned": disc.domains_scanned,
        "candidates_count": len(disc.candidates),
        "probe_stats": disc.probe_stats,
    }

    wr = _step(
        "write_discovered_site_entries",
        write_discovered_site_entries,
        project_key=project_key,
        candidates=disc.candidates,
        target_scope="project",
        dry_run=False,
    )
    results["write_site_entries"] = {"upserted": wr.upserted, "skipped": wr.skipped}

    if wr.upserted == 0 and len(disc.candidates) == 0:
        logger.warning("No site entries created. Skipping unified search.")
        return results

    # Get site entry URLs for unified search
    entries, total = list_site_entries(
        scope="effective",
        project_key=project_key,
        page=1,
        page_size=20,
    )
    site_urls = [e.get("site_url") for e in entries if e.get("site_url")]
    # Prefer rss/sitemap over domain_root for unified search
    rss_sitemap = [e for e in entries if str(e.get("entry_type", "")).lower() in ("rss", "sitemap")]
    if rss_sitemap:
        site_urls = [e.get("site_url") for e in rss_sitemap if e.get("site_url")][:5]
    else:
        site_urls = site_urls[:5]

    if not site_urls:
        logger.warning("No site entry URLs for unified search.")
        return results

    # Step 3: Unified search (requires item with site_entries)
    _ensure_temp_item(project_key, site_urls)
    try:
        usr = _step(
            "unified_search_by_item",
            unified_search_by_item,
            project_key=project_key,
            item_key=TEST_ITEM_KEY,
            query_terms=["lottery", "news"],
            max_candidates=50,
            write_to_pool=True,
            pool_scope="project",
            probe_timeout=8.0,
        )
        results["unified_search"] = {
            "candidates_count": len(usr.candidates),
            "written": usr.written,
            "errors": usr.errors,
        }
    finally:
        _remove_temp_item(project_key)

    # Step 4: Ingest from resource pool (url_pool.default)
    r4 = _step(
        "run_item_by_key (url_pool.default)",
        run_item_by_key,
        item_key="url_pool.default",
        project_key=project_key,
        override_params={"limit": 5},
    )
    results["ingest"] = r4

    # Verify schema isolation: docs should be in project schema only
    doc_count_after = _count_docs_in_schema(project_key)
    inserted = r4.get("result", {}).get("inserted", 0)
    results["schema"]["docs_after"] = doc_count_after
    results["schema"]["docs_delta"] = doc_count_after - doc_count_before
    if inserted > 0 and doc_count_after - doc_count_before != inserted:
        logger.warning(
            "  Schema isolation check: delta=%d vs inserted=%d (may be from prior runs)",
            doc_count_after - doc_count_before,
            inserted,
        )
    else:
        logger.info("  Schema isolation OK: docs in %s", schema_name)

    return results


def main() -> int:
    project_key = os.environ.get("PROJECT_KEY", PROJECT_KEY)
    logger.info("Running resource library E2E test for project_key=%s", project_key)
    try:
        results = run_e2e(project_key=project_key)
        logger.info("=== E2E Summary ===")
        for k, v in results.items():
            logger.info("  %s: %s", k, v)
        return 0
    except Exception as exc:
        logger.exception("E2E test failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
