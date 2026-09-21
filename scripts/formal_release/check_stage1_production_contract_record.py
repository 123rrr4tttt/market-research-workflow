#!/usr/bin/env python3
# ruff: noqa: TRY003, TRY301
"""Read-only fail-closed validator for the Stage1 production-contract record."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from pathlib import Path

from scripts.formal_release.generate_stage1_production_contract_record import (
    CHECKER,
    REPOSITORY_ROOT,
    Stage1RecordError,
    validate_stage1_record,
)
from scripts.formal_release.model import Finding, PreflightReport


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path)
    parser.add_argument("--repo-root", type=Path, default=REPOSITORY_ROOT)
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        value = json.loads(args.record.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise Stage1RecordError("record JSON root must be an object")
        validate_stage1_record(args.repo_root.resolve(), value)
    except (Stage1RecordError, OSError, json.JSONDecodeError) as exc:
        report = PreflightReport(
            CHECKER,
            (Finding("stage1_production_contract_record", "FAIL", str(exc)),),
        )
        print(report.to_json(), end="")
        return 1
    report = PreflightReport(
        CHECKER,
        (
            Finding(
                "stage1_production_contract_record",
                "PASS",
                "record identity, exact-byte bindings, one-time receipts, and create-only ceiling hold",
            ),
        ),
    )
    print(report.to_json(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
