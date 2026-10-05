"""Byte and structure checks for retired C2/C7/C8 evidence history."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.successor_runtime.capabilities.checksum import content_digest

_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_EVIDENCE_REL = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence"
)

_FROZEN_FRAGMENTS = (
    (
        "p3-fragments/C2.json",
        "31d32ce3d29eb2ed82063ba8c67d881ed3589cfdf23a616be520acabab1c9922",
        "C2",
        "P3",
        3,
    ),
    (
        "p4-fragments/C7.json",
        "d3a7aaf1916d2a01c1ed6e7004a06d6cd6ed24840a7403fd10e2ffdc53559a83",
        "C7",
        "P4",
        4,
    ),
    (
        "p4-fragments/C8.json",
        "206e69ad34ab60948c8310c6012f15fc66a03386eb3d2b60ae9e88328c8316a6",
        "C8",
        "P4",
        4,
    ),
)


@pytest.mark.parametrize(
    ("relative_path", "sha256", "family", "phase", "cell_count"),
    _FROZEN_FRAGMENTS,
)
def test_frozen_fragment_bytes_and_structure_are_history_only(
    relative_path: str,
    sha256: str,
    family: str,
    phase: str,
    cell_count: int,
) -> None:
    path = _REPOSITORY_ROOT / _EVIDENCE_REL / relative_path
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == sha256

    fragment = json.loads(raw)
    assert fragment["family"] == family
    assert fragment["phase"] == phase
    assert len(fragment["cells"]) == cell_count
    assert all(value is False for value in fragment["authority"].values())
    assert fragment["content_digest"] == content_digest(
        {key: value for key, value in fragment.items() if key != "content_digest"}
    )
