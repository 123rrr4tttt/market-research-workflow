#!/usr/bin/env python3
"""
Test: unified search -> write to pool -> auto_ingest -> Documents.

Verifies the search chain can automatically obtain documents in one call.

Usage:
  cd main/ops && docker compose exec backend python -m scripts.test_search_to_document_chain
  PROJECT_KEY=online_lottery docker compose exec backend python -m scripts.test_search_to_document_chain
"""

from __future__ import annotations

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PROJECT_KEY = os.environ.get("PROJECT_KEY", "online_lottery")
TEST_ITEM_KEY = "test.unified_search.e2e"


def main() -> int:
    from app.models.base import SessionLocal
    from app.models.entities import SourceLibraryItem
    from app.services.projects import bind_project
    from app.services.resource_pool import (
        list_site_entries,
        unified_search_by_item,
    )

    project_key = os.environ.get("PROJECT_KEY", PROJECT_KEY)
    logger.info("Testing search->document chain (auto_ingest) for project_key=%s", project_key)

    # Ensure we have site entries and a temp item
    entries, _ = list_site_entries(scope="effective", project_key=project_key, page=1, page_size=20)
    rss_sitemap = [e for e in entries if str(e.get("entry_type", "")).lower() in ("rss", "sitemap")]
    site_urls = [e.get("site_url") for e in (rss_sitemap or entries)[:5] if e.get("site_url")]

    if not site_urls:
        logger.error("No site entries (rss/sitemap) found. Run E2E test first: extract->discover->write.")
        return 1

    with bind_project(project_key):
        with SessionLocal() as session:
            existing = session.query(SourceLibraryItem).filter(
                SourceLibraryItem.item_key == TEST_ITEM_KEY
            ).first()
            if existing:
                existing.params = {"site_entries": site_urls}
            else:
                session.add(
                    SourceLibraryItem(
                        item_key=TEST_ITEM_KEY,
                        name="E2E Test Unified Search",
                        channel_key="generic_web.rss",
                        description="Temporary item for search->document test",
                        params={"site_entries": site_urls},
                        tags=["e2e", "temp"],
                        enabled=True,
                    )
                )
            session.commit()

    try:
        result = unified_search_by_item(
            project_key=project_key,
            item_key=TEST_ITEM_KEY,
            query_terms=["lottery", "california", "news"],
            max_candidates=30,
            write_to_pool=True,
            pool_scope="project",
            auto_ingest=True,
            ingest_limit=5,
            probe_timeout=8.0,
        )

        logger.info("=== Search chain result ===")
        logger.info("  candidates: %d", len(result.candidates))
        logger.info("  written: %s", result.written)
        logger.info("  ingest_result: %s", result.ingest_result)
        logger.info("  errors: %s", result.errors)

        if result.ingest_result:
            inserted = result.ingest_result.get("inserted", 0)
            skipped = result.ingest_result.get("skipped", 0)
            urls = result.ingest_result.get("urls", 0)
            logger.info("  -> Documents: inserted=%d, skipped=%d, urls_fetched=%d", inserted, skipped, urls)
            if inserted > 0:
                logger.info("  SUCCESS: auto_ingest produced %d new document(s)", inserted)
            else:
                logger.info("  NOTE: inserted=0 (URLs may already exist as documents)")
        else:
            logger.warning("  No ingest_result (auto_ingest may have failed)")

        return 0 if not result.errors else 1
    finally:
        with bind_project(project_key):
            with SessionLocal() as session:
                session.query(SourceLibraryItem).filter(
                    SourceLibraryItem.item_key == TEST_ITEM_KEY
                ).delete()
                session.commit()
        logger.info("  Cleaned up temp item")


if __name__ == "__main__":
    sys.exit(main())
