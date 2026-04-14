#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.base import SessionLocal
from app.services.graph.backfill_graph_nodes import run_graph_node_backfill


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill graph_nodes from documents.extracted_data")
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--resume-token", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with SessionLocal() as session:
        result = run_graph_node_backfill(
            session,
            batch_size=args.batch_size,
            limit=args.limit,
            resume_token=args.resume_token,
            dry_run=args.dry_run,
        )
    print(json.dumps(result.__dict__, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
