#!/usr/bin/env python3
"""Fetch content for documents with empty content.

For each doc where content is None or empty, fetches the URL and updates the document.
Uses the same _fetch_content logic (with fallback selectors) as discovery store.

Run in Docker:
  docker compose exec backend python scripts/fetch_empty_content.py --project demo_proj
  docker compose exec backend python scripts/fetch_empty_content.py --project demo_proj --limit 5 --dry-run
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select, or_
from sqlalchemy.orm.attributes import flag_modified

from app.models.base import SessionLocal
from app.models.entities import Document
from app.services.projects import bind_project
from app.services.discovery.store import fetch_content_from_url

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fetch_empty_content(
    project_key: str = "demo_proj",
    limit: int | None = None,
    doc_ids: list[int] | None = None,
    dry_run: bool = False,
) -> dict:
    """Fetch and update content for docs with empty content."""
    stats = {"total": 0, "updated": 0, "failed": 0, "skipped": 0}

    with bind_project(project_key):
        with SessionLocal() as session:
            conditions = [
                or_(Document.content.is_(None), Document.content == ""),
                Document.uri.isnot(None),
                Document.uri != "",
            ]
            if doc_ids:
                conditions.append(Document.id.in_(doc_ids))
            query = select(Document).where(*conditions)
            if limit:
                query = query.limit(limit)
            docs = list(session.execute(query).scalars().all())
            stats["total"] = len(docs)

            for doc in docs:
                uri = (doc.uri or "").strip()
                if not uri:
                    stats["skipped"] += 1
                    continue

                try:
                    content = fetch_content_from_url(uri)
                    if content and len(content.strip()) >= 50:
                        doc.content = content[:50000]
                        flag_modified(doc, "content")
                        if not dry_run:
                            session.add(doc)
                        stats["updated"] += 1
                        logger.info("Doc %s: fetched %d chars from %s", doc.id, len(content), uri[:60])
                    else:
                        stats["failed"] += 1
                        logger.debug("Doc %s: no content from %s", doc.id, uri[:60])
                except Exception as e:
                    stats["failed"] += 1
                    logger.warning("Doc %s fetch failed: %s", doc.id, e)

            if not dry_run and stats["updated"] > 0:
                session.commit()

    return stats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch content for docs with empty content")
    parser.add_argument("--project", default="demo_proj", help="Project key")
    parser.add_argument("--limit", type=int, default=None, help="Max docs to process")
    parser.add_argument("--doc-ids", type=int, nargs="+", default=None, help="Specific doc IDs (e.g. --doc-ids 96)")
    parser.add_argument("--dry-run", action="store_true", help="Do not persist")

    args = parser.parse_args()

    print("Fetch empty content")
    print("  project=%s limit=%s doc_ids=%s dry_run=%s" % (
        args.project, args.limit or "all", args.doc_ids or "all", args.dry_run))
    print("-" * 60)

    result = fetch_empty_content(
        project_key=args.project,
        limit=args.limit,
        doc_ids=args.doc_ids,
        dry_run=args.dry_run,
    )

    print("-" * 60)
    print("  total=%d updated=%d failed=%d skipped=%d" % (
        result["total"], result["updated"], result["failed"], result["skipped"]))
    if args.dry_run:
        print("\n(dry-run: no changes persisted)")
