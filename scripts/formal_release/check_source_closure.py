#!/usr/bin/env python3
# ruff: noqa: E402
"""CLI for the fail-closed Stage 1 source closure checker."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.formal_release.source_closure import SourceClosureError, check_source_closure


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args(argv)
    try:
        manifest = None
        if args.manifest is not None:
            manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        result = check_source_closure(args.source_root, manifest=manifest)
    except (SourceClosureError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"STAGE_1_SOURCE_CLOSURE_FAILED: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": "PASS",
                "required_modules": result.required_modules,
                "consumers": result.consumers,
                "manifest_paths": result.manifest_paths,
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
