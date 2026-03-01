#!/usr/bin/env python3
"""Check split coverage thresholds for core vs other modules.

Default policy:
- core modules: 100%
- other modules: 20%
"""

from __future__ import annotations

import argparse
import os
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Bucket:
    covered: int = 0
    total: int = 0

    @property
    def pct(self) -> float:
        if self.total == 0:
            return 100.0
        return (self.covered / self.total) * 100.0


def parse_args() -> argparse.Namespace:
    default_core_paths = os.getenv(
        "CORE_COVERAGE_PATHS",
        "app/api/search.py,app/contracts/api.py,app/contracts/responses.py,app/contracts/tasks.py,app/contracts/errors.py",
    )
    parser = argparse.ArgumentParser(description="Check split coverage thresholds.")
    parser.add_argument(
        "--coverage-file",
        default="coverage.xml",
        help="Path to coverage xml report (Cobertura format).",
    )
    parser.add_argument(
        "--core-paths",
        default=default_core_paths,
        help="Comma-separated core module path prefixes (or exact file path).",
    )
    parser.add_argument(
        "--core-threshold",
        type=float,
        default=100.0,
        help="Minimum core coverage percentage.",
    )
    parser.add_argument(
        "--other-threshold",
        type=float,
        default=20.0,
        help="Minimum other coverage percentage.",
    )
    return parser.parse_args()


def is_core(path: str, core_paths: list[str]) -> bool:
    for p in core_paths:
        if path == p or path.startswith(f"{p}/"):
            return True
    return False


def accumulate(coverage_file: Path, core_paths: list[str]) -> tuple[Bucket, Bucket]:
    root = ET.parse(coverage_file).getroot()
    core = Bucket()
    other = Bucket()

    for cls in root.findall(".//class"):
        filename = cls.get("filename")
        if not filename:
            continue
        # coverage.py xml may emit paths relative to app source root (e.g. "api/admin.py")
        # or rooted paths (e.g. "app/api/admin.py"). Normalize to "app/..." first.
        normalized = filename if filename.startswith("app/") else f"app/{filename}"
        # Ignore clearly non-backend-app paths after normalization.
        if not normalized.startswith("app/"):
            continue

        bucket = core if is_core(normalized, core_paths) else other
        for line in cls.findall("./lines/line"):
            hits = int(line.get("hits", "0"))
            bucket.total += 1
            if hits > 0:
                bucket.covered += 1

    return core, other


def main() -> int:
    args = parse_args()
    coverage_file = Path(args.coverage_file)
    if not coverage_file.exists():
        print(f"[coverage-thresholds] coverage file not found: {coverage_file}", file=sys.stderr)
        return 2

    core_paths = [p.strip() for p in args.core_paths.split(",") if p.strip()]
    core, other = accumulate(coverage_file, core_paths)

    print("[coverage-thresholds] policy")
    print(f"  core paths      : {', '.join(core_paths)}")
    print(f"  core threshold  : {args.core_threshold:.2f}%")
    print(f"  other threshold : {args.other_threshold:.2f}%")
    print("[coverage-thresholds] results")
    print(f"  core  : {core.covered}/{core.total} ({core.pct:.2f}%)")
    print(f"  other : {other.covered}/{other.total} ({other.pct:.2f}%)")

    failed = False
    if core.pct < args.core_threshold:
        print(
            f"[coverage-thresholds] FAIL core coverage {core.pct:.2f}% < {args.core_threshold:.2f}%",
            file=sys.stderr,
        )
        failed = True
    if other.pct < args.other_threshold:
        print(
            f"[coverage-thresholds] FAIL other coverage {other.pct:.2f}% < {args.other_threshold:.2f}%",
            file=sys.stderr,
        )
        failed = True

    if failed:
        return 1

    print("[coverage-thresholds] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
