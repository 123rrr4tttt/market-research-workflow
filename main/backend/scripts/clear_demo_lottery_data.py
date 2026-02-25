#!/usr/bin/env python3
"""
Delete lottery-related data from demo_proj project schema.

Targets:
  - market_stats: all rows (lottery sales, jackpot, game, etc.)
  - documents: doc_type in ('market', 'official_update', 'retailer_update')
    OR title/content/summary/extracted_data contains 'lottery'
  - sources: name contains 'lottery'
  - search_history: topic contains 'lottery'
  - embeddings: for deleted documents

Usage:
  python scripts/clear_demo_lottery_data.py            # dry run (preview only)
  python scripts/clear_demo_lottery_data.py --apply    # actually delete

Run in Docker:
  docker compose exec backend python scripts/clear_demo_lottery_data.py [--apply]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import text
from app.models.base import SessionLocal
from app.services.projects.context import bind_project


LOTTERY_DOC_TYPES = ("market", "official_update", "retailer_update")
LOTTERY_PATTERN = "%lottery%"
PROJECT_KEY = "demo_proj"


def _run_in_demo_schema(operation):
    """Run operation with demo_proj schema bound."""
    with bind_project(PROJECT_KEY):
        with SessionLocal() as session:
            return operation(session)


def _scalar(r):
    row = r.fetchone()
    return (row[0] if row is not None else 0) or 0


def _doc_lottery_condition():
    """SQL condition for documents with lottery in name or content."""
    return f"""
        doc_type IN ({", ".join(f"'{t}'" for t in LOTTERY_DOC_TYPES)})
        OR COALESCE(title, '') ILIKE :lottery
        OR COALESCE(content, '') ILIKE :lottery
        OR COALESCE(summary, '') ILIKE :lottery
        OR COALESCE(extracted_data::text, '') ILIKE :lottery
    """


def preview(session) -> dict:
    """Preview counts of data to be deleted."""
    counts = {}
    params = {"lottery": LOTTERY_PATTERN}

    r = session.execute(text("SELECT COUNT(*) FROM market_stats"))
    counts["market_stats"] = _scalar(r)

    r = session.execute(
        text(f"SELECT COUNT(*) FROM documents WHERE {_doc_lottery_condition()}"),
        params,
    )
    counts["documents"] = _scalar(r)

    r = session.execute(
        text(
            f"""
            SELECT COUNT(*) FROM embeddings e
            WHERE e.object_type = 'document'
            AND e.object_id IN (
                SELECT id FROM documents WHERE {_doc_lottery_condition()}
            )
            """
        ),
        params,
    )
    counts["embeddings"] = _scalar(r)

    r = session.execute(
        text("SELECT COUNT(*) FROM sources WHERE name ILIKE :lottery"),
        params,
    )
    counts["sources"] = _scalar(r)

    r = session.execute(
        text("SELECT COUNT(*) FROM search_history WHERE topic ILIKE :lottery"),
        params,
    )
    counts["search_history"] = _scalar(r)

    return counts


def apply_delete(session) -> dict:
    """Actually delete lottery data."""
    deleted = {}
    params = {"lottery": LOTTERY_PATTERN}

    # 1. Delete embeddings for lottery documents first
    r = session.execute(
        text(
            f"""
            DELETE FROM embeddings
            WHERE object_type = 'document'
            AND object_id IN (
                SELECT id FROM documents WHERE {_doc_lottery_condition()}
            )
            """
        ),
        params,
    )
    deleted["embeddings"] = r.rowcount

    # 2. Delete lottery documents
    r = session.execute(
        text(f"DELETE FROM documents WHERE {_doc_lottery_condition()}"),
        params,
    )
    deleted["documents"] = r.rowcount

    # 3. Delete sources with lottery in name
    r = session.execute(
        text("DELETE FROM sources WHERE name ILIKE :lottery"),
        params,
    )
    deleted["sources"] = r.rowcount

    # 4. Delete all market_stats (lottery-specific)
    r = session.execute(text("DELETE FROM market_stats"))
    deleted["market_stats"] = r.rowcount

    # 5. Delete search_history with lottery in topic
    r = session.execute(
        text("DELETE FROM search_history WHERE topic ILIKE :lottery"),
        params,
    )
    deleted["search_history"] = r.rowcount

    session.commit()
    return deleted


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Delete lottery-related data from demo_proj schema"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute deletion; without this, only preview",
    )
    args = parser.parse_args()

    print("=" * 60)
    print(f"Demo project ({PROJECT_KEY}) lottery data cleanup")
    print("=" * 60)

    def _preview(s):
        c = preview(s)
        print("\n📋 Preview (would be deleted):")
        print(f"  market_stats: {c['market_stats']} rows")
        print(f"  documents (lottery in type/name/content): {c['documents']} rows")
        print(f"  embeddings: {c['embeddings']} rows")
        print(f"  sources (name contains lottery): {c['sources']} rows")
        print(f"  search_history (topic contains lottery): {c['search_history']} rows")
        return c

    if not args.apply:
        _run_in_demo_schema(_preview)
        print("\nℹ️  To actually delete, run: python scripts/clear_demo_lottery_data.py --apply")
        return

    def _apply(s):
        print("\n🗑️  Deleting...")
        d = apply_delete(s)
        print(
            f"\n✅ Deleted: market_stats={d['market_stats']}, documents={d['documents']}, "
            f"embeddings={d['embeddings']}, sources={d['sources']}, search_history={d['search_history']}"
        )

    _run_in_demo_schema(_apply)
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
