#!/usr/bin/env python3
"""Compatibility entrypoint for the P3 C5 family fragment generator."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.successor_runtime.specification import c5_p3
from app.successor_runtime.specification.shared_family_generator import (
    build_fragment as build_family_fragment,
)
from app.successor_runtime.specification.shared_family_generator import (
    canonical_json,
    content_digest,
    load_p1_cells,
    run_legacy_cli,
)

CONFIG = c5_p3.CONFIG
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FRAGMENT_PATH = REPOSITORY_ROOT / c5_p3.FRAGMENT_OUTPUT_REL
FRAGMENT_ID = c5_p3.FRAGMENT_ID
FRAGMENT_SCHEMA = c5_p3.FRAGMENT_SCHEMA
ADJUDICATION_PATH = c5_p3.EVIDENCE_ROOT / "C5_4LocatorAdjudication.v1.json"
ADJUDICATION_CONTENT_DIGEST = c5_p3.ADJUDICATION_CONTENT_DIGEST
NORMATIVE_DONOR_LOCATORS = c5_p3.NORMATIVE_DONOR_LOCATORS
SUPPLEMENTARY_READ_ONLY_EVIDENCE = c5_p3.SUPPLEMENTARY_READ_ONLY_EVIDENCE
PROHIBITED_DIRTY_SOURCE = c5_p3.PROHIBITED_DIRTY_SOURCE

_canonical_json = canonical_json
_self_test = CONFIG.self_check


def _p1_cells() -> dict[str, object]:
    return dict(
        load_p1_cells(
            REPOSITORY_ROOT,
            f"{c5_p3._EVIDENCE_ROOT}/P1FunctorizationEligibility.v1.json",
        )
    )


def build_fragment() -> Annotated[
    dict[str, object],
    "kit:non-authoritative derived_as=generated_evidence "
    "fact_source=C5.1-C5.4_observations+repo_bindings "
    "witness=test:test_w10_cli_generator_derived_metadata_preserves_abi",
]:
    return build_family_fragment(CONFIG, REPOSITORY_ROOT)


def main(argv: list[str] | None = None) -> int:
    return run_legacy_cli(
        CONFIG,
        argv,
        prog="generate_successor_p3_c5_fragment",
        description="generate or read-only check the P3 C5 evidence fragment",
        repo_root=REPOSITORY_ROOT,
        output_path=FRAGMENT_PATH,
    )


if __name__ == "__main__":
    raise SystemExit(main())
