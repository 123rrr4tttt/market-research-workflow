#!/usr/bin/env python3
# ruff: noqa: TRY003
"""Validate the additive current-file Stage1 binding against an explicit repo root."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from pathlib import Path

from scripts.formal_release import generate_stage1_production_contract_record as stage1
from scripts.formal_release.generate_stage1_current_binding_successor import (
    CHECKER,
    OUTPUT_REL,
    validate_bundle,
)


def check(root: Path, record_path: Path = OUTPUT_REL) -> dict[str, object]:
    root = root.resolve()
    raw = stage1._read(root, record_path)
    try:
        record = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise stage1.Stage1RecordError("current Stage1 binding record is invalid JSON") from exc
    if not isinstance(record, dict):
        raise stage1.Stage1RecordError("current Stage1 binding record JSON root must be an object")
    summary = validate_bundle(root, record)
    return {
        "authoritative": False,
        "checker": CHECKER,
        "current_file_count": summary["file_count"],
        "current_mismatch_count": summary["current_mismatch_count"],
        "historical_receipt_count": summary["historical_receipt_count"],
        "projected_candidate_mismatch_count": summary[
            "projected_candidate_mismatch_count"
        ],
        "removed_count": summary["removed_count"],
        "record": record_path.as_posix(),
        "status": "PASS_NOT_AUTHORITY",
    }


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=stage1.REPOSITORY_ROOT)
    parser.add_argument("--record", type=Path, default=OUTPUT_REL)
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = check(args.repo_root, args.record)
    except (OSError, stage1.Stage1RecordError) as exc:
        result = {
            "authoritative": False,
            "checker": CHECKER,
            "current_mismatch_count": 1,
            "error": str(exc),
            "projected_candidate_mismatch_count": 1,
            "record": args.record.as_posix(),
            "status": "FAIL",
        }
        print(json.dumps(result, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
