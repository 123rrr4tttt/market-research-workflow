#!/usr/bin/env python3
"""Generate one family evidence fragment through the shared family generator.

Each family submits a thin config under
``app/successor_runtime/specification/``; the shared module owns canonical
JSON/digest, path confinement, authority, determinism and atomic writes.
``--check`` is strictly read-only: exact bytes exit 0, drift or a missing
output exits 1, and no output is written.  Run from ``main/backend``:

    python3.11 scripts/generate_family_fragment_shared.py [--family C7] [--check]
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.successor_runtime.specification.shared_family_generator import run_generate

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

_FAMILY_MODULES = {
    "C2": "app.successor_runtime.specification.c2_p3",
    "C3": "app.successor_runtime.specification.c3_p3",
    "C4": "app.successor_runtime.specification.c4_p3",
    "C5": "app.successor_runtime.specification.c5_p3",
    "C6": "app.successor_runtime.specification.c6_p3",
    "C7": "app.successor_runtime.specification.c7_p4",
    "C8": "app.successor_runtime.specification.c8_p4",
    "C9": "app.successor_runtime.specification.c9_p4",
}


def config_for(family: str):
    """Load the thin family config module, failing closed on missing families."""

    try:
        module_name = _FAMILY_MODULES[family]
    except KeyError as exc:
        raise ValueError(f"unknown family: {family}") from exc
    return importlib.import_module(module_name).CONFIG


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--family",
        choices=sorted(_FAMILY_MODULES),
        default="C7",
        help="family fragment to generate (default: C7)",
    )
    parser.add_argument(
        "--repo-root",
        default=str(REPOSITORY_ROOT),
        help="repository root for relative paths",
    )
    parser.add_argument("--check", action="store_true", help="read-only byte gate")
    args = parser.parse_args(argv)
    return run_generate(config_for(args.family), Path(args.repo_root), check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
