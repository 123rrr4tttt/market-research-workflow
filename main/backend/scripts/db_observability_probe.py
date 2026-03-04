#!/usr/bin/env python3
"""Lightweight DB observability probe for E-db line.

Usage:
  python scripts/db_observability_probe.py --database-url "$DATABASE_URL"
"""

from __future__ import annotations

import argparse
import json
import time
from typing import Any

from sqlalchemy import create_engine, text


def run_probe(database_url: str) -> dict[str, Any]:
    start = time.perf_counter()
    engine = create_engine(database_url, future=True, pool_pre_ping=True)
    details: dict[str, Any] = {"database_url_masked": database_url.split("@")[-1]}
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        db_ms = (time.perf_counter() - start) * 1000
        details["db_ping_ms"] = round(db_ms, 2)

        # These views are Postgres-specific; keep failure isolated.
        try:
            top_tables = conn.execute(
                text(
                    """
                    SELECT relname AS table_name, seq_scan, idx_scan
                    FROM pg_stat_user_tables
                    ORDER BY seq_scan DESC NULLS LAST
                    LIMIT 5
                    """
                )
            ).mappings().all()
            details["top_seq_scan_tables"] = [dict(row) for row in top_tables]
        except Exception as exc:  # noqa: BLE001
            details["top_seq_scan_tables_error"] = type(exc).__name__
    return details


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()

    payload = run_probe(args.database_url)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
