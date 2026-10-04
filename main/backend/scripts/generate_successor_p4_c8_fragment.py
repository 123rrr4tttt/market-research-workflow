#!/usr/bin/env python3
"""Compatibility entrypoint for the P4 C8 family fragment generator."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.successor_runtime.specification import c8_p4
from app.successor_runtime.specification.shared_family_generator import (
    build_fragment as build_family_fragment,
)
from app.successor_runtime.specification.shared_family_generator import (
    canonical_json,
    content_digest,
    run_legacy_cli,
)

CONFIG = c8_p4.CONFIG
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FRAGMENT_PATH = REPOSITORY_ROOT / c8_p4.FRAGMENT_OUTPUT_REL
FRAGMENT_ID = c8_p4.FRAGMENT_ID
FRAGMENT_SCHEMA = c8_p4.FRAGMENT_SCHEMA
FRAGMENT_PHASE = c8_p4.FRAGMENT_PHASE
FRAGMENT_FAMILY = c8_p4.FRAGMENT_FAMILY
FRAGMENT_STATUS = c8_p4.FRAGMENT_STATUS
LIFECYCLE_STATE = c8_p4.LIFECYCLE_STATE

_canonical_json = canonical_json
_self_test = CONFIG.self_check


def build_fragment() -> Annotated[
    dict[str, object],
    "kit:non-authoritative derived_as=generated_evidence "
    "fact_source=C8.1-C8.4_observations+repo_bindings "
    "witness=test:test_w10_cli_generator_derived_metadata_preserves_abi",
]:
    return build_family_fragment(CONFIG, REPOSITORY_ROOT)


def main(argv: list[str] | None = None) -> int:
    return run_legacy_cli(
        CONFIG,
        argv,
        prog="generate_successor_p4_c8_fragment",
        description="Generate or read-only check the P4 C8 evidence fragment",
        repo_root=REPOSITORY_ROOT,
        output_path=FRAGMENT_PATH,
    )


if __name__ == "__main__":
    raise SystemExit(main())
