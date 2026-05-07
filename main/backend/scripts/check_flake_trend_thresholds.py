#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary-json", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--max-above-threshold", type=int, default=0)
    parser.add_argument("--min-tests", type=int, default=1)
    args = parser.parse_args()

    summary_path = Path(args.summary_json)
    output_path = Path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not summary_path.exists():
        payload = {
            "status": "missing-summary",
            "above_threshold_count": 0,
            "eligible_tests": 0,
            "max_above_threshold": args.max_above_threshold,
        }
        output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return 1

    data = json.loads(summary_path.read_text(encoding="utf-8"))
    tests = data.get("tests", [])
    eligible = [item for item in tests if int(item.get("runs", 0)) >= args.min_tests]
    above = [item for item in eligible if item.get("above_threshold")]
    payload = {
        "status": "pass" if len(above) <= args.max_above_threshold else "fail",
        "above_threshold_count": len(above),
        "eligible_tests": len(eligible),
        "max_above_threshold": args.max_above_threshold,
        "failing_tests": above[:20],
    }
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
