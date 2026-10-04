#!/usr/bin/env python3
"""Compatibility entrypoint for the P3 C2 family fragment generator."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.successor_runtime.specification import c2_p3
from app.successor_runtime.specification.shared_family_generator import (
    build_fragment as build_family_fragment,
)
from app.successor_runtime.specification.shared_family_generator import (
    canonical_json,
    content_digest,
    fragment_bytes as family_fragment_bytes,
    run_legacy_cli,
)

CONFIG = c2_p3.CONFIG
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FRAGMENT_PATH = REPOSITORY_ROOT / c2_p3.FRAGMENT_OUTPUT_REL
FRAGMENT_ID = c2_p3.FRAGMENT_ID
FRAGMENT_SCHEMA = c2_p3.FRAGMENT_SCHEMA
FRAGMENT_PHASE = c2_p3.FRAGMENT_PHASE
FRAGMENT_FAMILY = c2_p3.FRAGMENT_FAMILY
FRAGMENT_STATUS = c2_p3.FRAGMENT_STATUS

_canonical_json = canonical_json
_self_test = CONFIG.self_check


def build_fragment() -> Annotated[
    dict[str, object],
    "kit:non-authoritative derived_as=generated_evidence "
    "fact_source=C2.1_resolution+C2.2_program+C2.3_fixture_receipt+C2.4_projection "
    "witness=test:test_w10_cli_generator_derived_metadata_preserves_abi",
]:
    return build_family_fragment(CONFIG, REPOSITORY_ROOT)


def fragment_bytes() -> bytes:
    return family_fragment_bytes(CONFIG, build_fragment())


def main(argv: list[str] | None = None) -> int:
    return run_legacy_cli(
        CONFIG,
        argv,
        prog="generate_successor_p3_c2_fragment",
        description=(
            "Deterministically generate or read-only check the P3 C2 fragment."
        ),
        repo_root=REPOSITORY_ROOT,
        output_path=FRAGMENT_PATH,
        fragment_path_argument=True,
        missing_exit=2,
    )


if __name__ == "__main__":
    raise SystemExit(main())
