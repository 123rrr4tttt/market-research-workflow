#!/usr/bin/env python3
"""ST05: Historical backfill + quality report for source time-window density."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class Counters:
    scanned: int = 0
    valid: int = 0
    missing_time: int = 0
    invalid_time: int = 0
    duplicate: int = 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill source/noun density aggregates and emit quality report",
    )
    parser.add_argument("--input", help="JSONL file path (one document per line)")
    parser.add_argument(
        "--output-report",
        default="main/backend/scripts/artifacts/st05_density_quality_report.json",
        help="Path to write quality report JSON",
    )
    parser.add_argument(
        "--state-path",
        default="main/backend/scripts/artifacts/st05_density_backfill_state.json",
        help="Path to write backfill state JSON",
    )
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--window-days", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true", help="Compute only; no state/report write")
    parser.add_argument(
        "--sample-size",
        type=int,
        default=30,
        help="When --input is absent, generate deterministic sample rows for dry-run",
    )
    return parser.parse_args()


def _read_jsonl(path: Path, limit: int | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            text = line.strip()
            if not text:
                continue
            item = json.loads(text)
            if isinstance(item, dict):
                rows.append(item)
            if limit is not None and len(rows) >= limit:
                break
    return rows


def _sample_rows(size: int) -> list[dict[str, Any]]:
    base = datetime(2026, 3, 1, tzinfo=timezone.utc)
    rows: list[dict[str, Any]] = []
    for idx in range(max(1, size)):
        day_offset = idx % 10
        source = "example.com" if idx % 2 == 0 else "marketwatch.com"
        noun = "EV" if idx % 3 else "AI"
        row: dict[str, Any] = {
            "doc_id": f"sample-{idx}",
            "source_domain": source,
            "noun_group_id": noun,
            "effective_time": (base.replace(day=max(1, base.day - day_offset))).isoformat(),
            "is_duplicate": idx % 7 == 0,
        }
        if idx % 13 == 0:
            row["effective_time"] = None
        rows.append(row)
    return rows


def _to_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None
    return None


def _process(rows: list[dict[str, Any]], window_days: int) -> tuple[dict[str, Any], dict[str, Any]]:
    counters = Counters()
    grouped: dict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: {
        "source_domain": "unknown",
        "noun_group_id": "unknown",
        "docs": 0,
        "duplicates": 0,
        "valid_docs": 0,
        "density": 0.0,
    })

    for row in rows:
        counters.scanned += 1
        source = str(row.get("source_domain") or "unknown")
        noun = str(row.get("noun_group_id") or "unknown")
        key = (source, noun)
        bucket = grouped[key]
        bucket["source_domain"] = source
        bucket["noun_group_id"] = noun
        bucket["docs"] += 1

        is_dup = bool(row.get("is_duplicate"))
        if is_dup:
            counters.duplicate += 1
            bucket["duplicates"] += 1

        dt = _to_dt(row.get("effective_time"))
        if dt is None:
            if row.get("effective_time") in (None, ""):
                counters.missing_time += 1
            else:
                counters.invalid_time += 1
            continue

        counters.valid += 1
        bucket["valid_docs"] += 1

    for _, bucket in grouped.items():
        bucket["density"] = round(float(bucket["valid_docs"]) / float(max(1, window_days)), 6)

    scan_total = max(1, counters.scanned)
    quality = {
        "scanned": counters.scanned,
        "valid_time_docs": counters.valid,
        "missing_time_docs": counters.missing_time,
        "invalid_time_docs": counters.invalid_time,
        "duplicate_docs": counters.duplicate,
        "valid_time_ratio": round(counters.valid / scan_total, 6),
        "missing_time_ratio": round(counters.missing_time / scan_total, 6),
        "invalid_time_ratio": round(counters.invalid_time / scan_total, 6),
        "duplicate_ratio": round(counters.duplicate / scan_total, 6),
    }
    aggregates = sorted(grouped.values(), key=lambda x: (x["source_domain"], x["noun_group_id"]))

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_days": window_days,
        "quality": quality,
        "density_aggregates": aggregates,
    }
    state = {
        "updated_at": report["generated_at"],
        "cursor": counters.scanned,
        "batch_size": None,
        "status": "dry_run" if counters.scanned >= 0 else "unknown",
    }
    return report, state


def main() -> int:
    args = _parse_args()
    if args.batch_size <= 0:
        raise SystemExit("--batch-size must be > 0")
    if args.window_days <= 0:
        raise SystemExit("--window-days must be > 0")

    if args.input:
        input_path = Path(args.input).resolve()
        if not input_path.exists():
            raise SystemExit(f"Input not found: {input_path}")
        rows = _read_jsonl(input_path, args.limit)
        input_mode = "jsonl"
    else:
        rows = _sample_rows(args.sample_size if args.limit is None else min(args.sample_size, args.limit))
        input_mode = "sample"

    report, state = _process(rows, args.window_days)
    state["batch_size"] = args.batch_size
    state["status"] = "dry_run" if args.dry_run else "applied"
    state["input_mode"] = input_mode

    if not args.dry_run:
        report_path = Path(args.output_report).resolve()
        state_path = Path(args.state_path).resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "mode": "dry_run" if args.dry_run else "apply",
                "input_mode": input_mode,
                "rows": len(rows),
                "quality": report["quality"],
                "top_aggregate": report["density_aggregates"][0] if report["density_aggregates"] else None,
                "report_path": None if args.dry_run else str(Path(args.output_report).resolve()),
                "state_path": None if args.dry_run else str(Path(args.state_path).resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
