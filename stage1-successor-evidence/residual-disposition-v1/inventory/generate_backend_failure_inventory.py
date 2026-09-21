#!/usr/bin/env python3
"""Repository-root entry point for the Contract 12 inventory generator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[3]
NESTED_DIR = (
    REPO_ROOT
    / "development/latest-dev-docs/development-plans/CURRENT_DEV"
    / "2026-09-04-formal-production-release/stage1-successor-evidence"
    / "residual-disposition-v1/inventory"
)
if str(NESTED_DIR) not in sys.path:
    sys.path.insert(0, str(NESTED_DIR))
from generate_backend_failure_inventory import build_inventory  # type: ignore  # noqa: E402


RAW_GATE_DIR = Path(__file__).resolve().parents[1] / "raw-gate"
DEFAULT_JUNIT = RAW_GATE_DIR / "backend-unit-final.xml"
DEFAULT_LOG = RAW_GATE_DIR / "backend-unit-final.log"
DEFAULT_OUTPUT = Path(__file__).with_name("backend_failure_inventory.v1.json")


def _write_create_only(path: Path, body: bytes) -> None:
    if path.exists():
        if path.read_bytes() != body:
            raise FileExistsError(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(body)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", type=Path, default=DEFAULT_JUNIT)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    payload = build_inventory(args.junit, args.log)
    body = (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    _write_create_only(args.output, body)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "failure_count": payload["failure_count"],
                "inventory_sha256": payload["inventory_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
