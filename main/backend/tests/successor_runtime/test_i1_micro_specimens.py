"""I1 micro-specimen evidence rows: 30 capability cell specs + manifests.

Each row is the non-PostgreSQL equivalent of
``generate_capability_spec_pilots.py --check MATCH``: the on-disk manifest
must equal the canonical compile output for the on-disk spec/ABI, every exact
binding must match its recorded sha256, and the manifest must keep candidate
creation and authority adoption false.  No production code is touched.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from app.successor_runtime.specification import (
    CapabilityCellSpec,
    RuntimeKernelABI,
    build_manifest_bytes,
    compile_capability_spec,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BACKEND_ROOT.parents[1]
TOPIC = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration"
)
SPECS_DIR = REPOSITORY_ROOT / TOPIC / "evidence/capability-specs"
BUILDS_DIR = REPOSITORY_ROOT / TOPIC / "evidence/capability-spec-builds"
ABI_PATH = SPECS_DIR / "RuntimeKernelABI.v1.json"

CELL_IDS = tuple(
    f"C{family}.{cell}"
    for family in range(1, 10)
    for cell in {
        1: (1, 2, 3),
        2: (1, 2, 3, 4),
        3: (1, 2),
        4: (1, 2, 3),
        5: (1, 2, 3, 4),
        6: (1, 2, 3),
        7: (1, 2, 3, 4),
        8: (1, 2, 3, 4),
        9: (1, 2, 3),
    }[family]
)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def _verify_exact_bindings(spec: CapabilityCellSpec) -> None:
    for binding in spec.exact_bindings():
        path = Path(binding.path)
        if not path.is_absolute():
            path = REPOSITORY_ROOT / path
        resolved = path.resolve()
        try:
            resolved.relative_to(REPOSITORY_ROOT.resolve())
        except ValueError as exc:
            raise AssertionError(
                f"exact binding escapes repository root: {binding.path}"
            ) from exc
        if not resolved.is_file():
            raise AssertionError(f"exact binding missing: {binding.path}")
        actual = hashlib.sha256(resolved.read_bytes()).hexdigest()
        assert actual == binding.file_sha256, (
            f"exact binding drift: {binding.path}: {actual} != {binding.file_sha256}"
        )


def _micro_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cell_id in CELL_IDS:
        spec_path = SPECS_DIR / f"{cell_id}.v1.json"
        build_path = BUILDS_DIR / f"{cell_id}.BuildManifest.v1.json"
        assert spec_path.is_file(), spec_path
        assert build_path.is_file(), build_path
        spec_value = _load(spec_path)
        spec = CapabilityCellSpec.from_dict(spec_value)
        abi = RuntimeKernelABI.from_dict(_load(ABI_PATH))
        _verify_exact_bindings(spec)
        compiled = compile_capability_spec(spec, abi)
        expected_bytes = build_manifest_bytes(compiled)
        assert build_path.read_bytes() == expected_bytes, (
            f"manifest --check DRIFT: {cell_id}"
        )
        manifest = _load(build_path)
        assert manifest["cell_id"] == cell_id
        assert manifest["candidate_created"] is False
        assert manifest["authority_ceiling"] == {
            "authority_transfer": False,
            "canonical_write": False,
            "cutover": False,
            "external_delivery": False,
            "live_provider": False,
        }
        rows.append(
            {
                "cell_id": cell_id,
                "family_id": spec.family_id,
                "entrypoint_kind": spec.entrypoint_kind,
                "from_dict": "PASS",
                "manifest_check": "MATCH",
                "exact_bindings": len(spec.exact_bindings()),
                "candidate_created": False,
                "program_atom_generated": (
                    compiled["generated"].get("program_skeleton") is not None
                ),
            }
        )
    assert len(rows) == 30
    return rows


@pytest.mark.unit
def test_i1_micro_specimen_matrix_is_30_of_30_and_manifest_exact() -> None:
    rows = _micro_rows()
    assert {row["cell_id"] for row in rows} == set(CELL_IDS)
    assert all(row["from_dict"] == "PASS" for row in rows)
    assert all(row["manifest_check"] == "MATCH" for row in rows)
    assert all(row["candidate_created"] is False for row in rows)


@pytest.mark.unit
def test_i1_micro_rows_record_declared_no_atom_shapes() -> None:
    rows = _micro_rows()
    by_id = {row["cell_id"]: row for row in rows}
    no_atom_cells = {
        "C1.3",
        "C2.4",
        "C5.1",
        "C5.2",
        "C5.3",
        "C5.4",
        "C9.1",
        "C9.2",
        "C9.3",
    }
    for cell_id, row in by_id.items():
        if cell_id in no_atom_cells:
            assert row["program_atom_generated"] is False
        else:
            assert row["program_atom_generated"] is True, cell_id


@pytest.mark.unit
def test_i1_micro_specimen_evidence_rows_are_reproducible() -> None:
    assert _micro_rows() == _micro_rows()
