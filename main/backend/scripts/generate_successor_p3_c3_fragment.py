#!/usr/bin/env python3
"""Compatibility entrypoint for the P3 C3 family fragment generator."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.successor_runtime.specification import acquisition_batch_p3
from app.successor_runtime.specification.shared_family_generator import (
    build_fragment as build_family_fragment,
)
from app.successor_runtime.specification.shared_family_generator import (
    canonical_json,
    content_digest,
    fragment_bytes as family_fragment_bytes,
    run_legacy_cli,
    write_atomic_if_changed,
)

CONFIG = acquisition_batch_p3.CONFIG
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FRAGMENT_PATH = REPOSITORY_ROOT / acquisition_batch_p3.FRAGMENT_OUTPUT_REL
FRAGMENT_ID = acquisition_batch_p3.FRAGMENT_ID
FRAGMENT_SCHEMA = acquisition_batch_p3.FRAGMENT_SCHEMA
FRAGMENT_STATUS = acquisition_batch_p3.FRAGMENT_STATUS

_canonical_json = canonical_json
_canonical_digest = content_digest
_self_test = CONFIG.self_check


def build_fragment() -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=generated_evidence "
    "fact_source=C3.1_C3.2_fixtures+current_repo_bindings "
    "witness=test:test_w10_cli_generator_derived_metadata_preserves_abi",
]:
    return build_family_fragment(CONFIG, REPOSITORY_ROOT)


def fragment_bytes(fragment: dict[str, Any]) -> bytes:
    return family_fragment_bytes(CONFIG, fragment)


def write_fragment() -> Path:
    write_atomic_if_changed(FRAGMENT_PATH, fragment_bytes(build_fragment()))
    return FRAGMENT_PATH


def main(argv: list[str] | None = None) -> int:
    return run_legacy_cli(
        CONFIG,
        argv,
        prog="generate_successor_p3_c3_fragment",
        description="Generate the deterministic P3 C3 evidence fragment.",
        repo_root=REPOSITORY_ROOT,
        output_path=FRAGMENT_PATH,
    )


if __name__ == "__main__":
    raise SystemExit(main())
