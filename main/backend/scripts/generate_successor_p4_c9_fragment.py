#!/usr/bin/env python3
"""Compatibility entrypoint for the P4 C9 family fragment generator."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.successor_runtime.specification import c9_p4
from app.successor_runtime.specification.shared_family_generator import (
    build_fragment as build_family_fragment,
)
from app.successor_runtime.specification.shared_family_generator import (
    canonical_json,
    content_digest,
    p1_cell_digest,
    run_legacy_cli,
)

CONFIG = c9_p4.CONFIG
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FRAGMENT_PATH = REPOSITORY_ROOT / c9_p4.FRAGMENT_OUTPUT_REL
FRAGMENT_ID = c9_p4.FRAGMENT_ID
FRAGMENT_SCHEMA = c9_p4.FRAGMENT_SCHEMA
FRAGMENT_PHASE = c9_p4.FRAGMENT_PHASE
FRAGMENT_FAMILY = c9_p4.FRAGMENT_FAMILY
FRAGMENT_STATUS = c9_p4.FRAGMENT_STATUS
FRAGMENT_P4_STATUS = "P4_NOT_STARTED"

_canonical_json = canonical_json
_self_test = CONFIG.self_check


def _p1_cell_digest(cell_id: str) -> str:
    return p1_cell_digest(
        REPOSITORY_ROOT,
        f"{c9_p4._EVIDENCE_ROOT}/P1FunctorizationEligibility.v1.json",
        cell_id,
    )


def build_fragment() -> Annotated[
    dict[str, object],
    "kit:non-authoritative derived_as=generated_evidence "
    "fact_source=C9.1-C9.3_contracts+repo_bindings "
    "witness=test:test_w10_cli_generator_derived_metadata_preserves_abi",
]:
    return build_family_fragment(CONFIG, REPOSITORY_ROOT)


def main(argv: list[str] | None = None) -> int:
    return run_legacy_cli(
        CONFIG,
        argv,
        prog="generate_successor_p4_c9_fragment",
        description="Generate or read-only check the P4 C9 evidence fragment",
        repo_root=REPOSITORY_ROOT,
        output_path=FRAGMENT_PATH,
    )


if __name__ == "__main__":
    raise SystemExit(main())
