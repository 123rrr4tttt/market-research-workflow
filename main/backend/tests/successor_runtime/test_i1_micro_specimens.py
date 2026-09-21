"""I1 micro-specimen evidence rows: 30 capability cell specs + manifests.

Each row is the non-PostgreSQL equivalent of
``generate_capability_spec_pilots.py --check MATCH``: the on-disk manifest
must equal the canonical compile output for the on-disk spec/ABI, every exact
binding must match its recorded sha256, and the manifest must keep candidate
creation and authority adoption false.  No production code is touched.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from app.successor_runtime.specification import (
    CapabilityCellSpec,
    RuntimeKernelABI,
    build_manifest_bytes,
    compile_capability_spec,
)
from tests.successor_runtime.i1_binding_candidate_support import (
    B10_CANDIDATE_PATH,
    B16_CANDIDATE_PATH,
    B19_HISTORY_CANDIDATE_PATH,
    B20_HISTORY_CANDIDATE_PATH,
    B21_HISTORY_CANDIDATE_PATH,
    B22_HISTORY_CANDIDATE_PATH,
    CANDIDATE_PATH,
    CHECKER_PATH,
    REPOSITORY_ROOT,
    _expand_current_binding_successors,
    candidate_binding_keys,
    check_current_successor_live,
    candidate_context,
    current_successor_binding_keys,
    direct_successor_binding_keys,
    verify_spec_bindings,
)

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
        raise TypeError(f"expected JSON object: {path}")  # noqa: TRY003
    return value


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
        binding_dispositions = verify_spec_bindings(spec)
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
                "additive_successor_bindings": sum(
                    disposition.startswith("ADDITIVE_")
                    for disposition in binding_dispositions
                ),
                "current_byte_successor_bindings": binding_dispositions.count(
                    "ADDITIVE_CURRENT_BYTE_SUCCESSOR_NOT_AUTHORITY"
                ),
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
    assert sum(row["additive_successor_bindings"] for row in rows) == len(
        candidate_binding_keys() | direct_successor_binding_keys()
    )
    assert sum(row["current_byte_successor_bindings"] for row in rows) == len(
        current_successor_binding_keys() | direct_successor_binding_keys()
    )
    assert current_successor_binding_keys() <= candidate_binding_keys()
    assert {key[0] for key in direct_successor_binding_keys()} == {"C5.2", "C6.1", "C6.3"}
    assert not (direct_successor_binding_keys() & candidate_binding_keys())


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


@pytest.mark.unit
def test_i1_current_successor_is_live_and_frozen_candidates_are_history_only() -> None:
    candidate, fragment = candidate_context()
    stage_roots = {
        path.parents[2]
        for path in (
            CANDIDATE_PATH,
            B10_CANDIDATE_PATH,
            B16_CANDIDATE_PATH,
            B22_HISTORY_CANDIDATE_PATH,
            B19_HISTORY_CANDIDATE_PATH,
            B20_HISTORY_CANDIDATE_PATH,
            B21_HISTORY_CANDIDATE_PATH,
        )
    }
    paths = [
        path for root in stage_roots for path in root.rglob("*") if path.is_file()
    ]
    snapshot = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths}

    live_outcome, registry = check_current_successor_live()
    assert live_outcome["status"] == "PASS"
    assert registry["status"] == (
        "CURRENT_BYTES_BOUND_BY_ADDITIVE_SUCCESSORS_NOT_AUTHORITY"
    )

    checks = (
        (
            CANDIDATE_PATH,
            ("--history-only",),
            "HISTORY_SNAPSHOT_VALID_NOT_AUTHORITY",
        ),
        (
            B22_HISTORY_CANDIDATE_PATH,
            ("--history-only",),
            "HISTORY_SNAPSHOT_VALID_NOT_AUTHORITY",
        ),
        (
            B19_HISTORY_CANDIDATE_PATH,
            ("--history-only",),
            "HISTORY_SNAPSHOT_VALID_NOT_AUTHORITY",
        ),
        (
            B20_HISTORY_CANDIDATE_PATH,
            ("--history-only",),
            "HISTORY_SNAPSHOT_VALID_NOT_AUTHORITY",
        ),
        (
            B21_HISTORY_CANDIDATE_PATH,
            ("--history-only",),
            "HISTORY_SNAPSHOT_VALID_NOT_AUTHORITY",
        ),
        (
            B10_CANDIDATE_PATH,
            ("--history-only",),
            "HISTORY_SNAPSHOT_VALID_NOT_AUTHORITY",
        ),
        (
            B16_CANDIDATE_PATH,
            ("--history-only",),
            "HISTORY_SNAPSHOT_VALID_NOT_AUTHORITY",
        ),
    )
    for candidate_path, extra, expected_status in checks:
        result = subprocess.run(
            [
                sys.executable,
                str(CHECKER_PATH),
                "check-candidate",
                "--repo-root",
                str(REPOSITORY_ROOT),
                "--candidate",
                str(candidate_path),
                *extra,
            ],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        expected_id = (
            candidate["candidate_id"]
            if candidate_path == CANDIDATE_PATH
            else _load(candidate_path)["candidate_id"]
        )
        assert payload["candidate_id"] == expected_id
        assert payload["status"] == expected_status

    assert fragment["authority"] and not any(fragment["authority"].values())
    after = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths}
    assert after == snapshot


@pytest.mark.unit
def test_i1_v2_shared_successor_expands_to_two_exact_keys() -> None:
    _outcome, registry = check_current_successor_live()
    assert len(registry["successors"]) == 11
    expanded = _expand_current_binding_successors(registry)
    shared = [
        row
        for row in expanded.values()
        if row["successor_id"] == "i1-c6-native-provider-current-bytes-v2"
    ]
    assert {row["cell_id"] for row in shared} == {"C6.1", "C6.2"}
    assert len(shared) == 2
    assert {row["successor_sha256"] for row in shared} == {
        "1daddedc2fe8a435c062fa66019e00db2b47aeb2e88d8fce97e7dfe3e8bd4cf5"
    }


@pytest.mark.unit
def test_i1_v2_shared_successor_rejects_invalid_expansion_keys() -> None:
    _outcome, registry = check_current_successor_live()
    shared_index = next(
        index
        for index, row in enumerate(registry["successors"])
        if row["successor_id"] == "i1-c6-native-provider-current-bytes-v2"
    )

    duplicate_cells = copy.deepcopy(registry)
    duplicate_cells["successors"][shared_index]["cell_ids"] = ["C6.1", "C6.1"]
    with pytest.raises(AssertionError):
        _expand_current_binding_successors(duplicate_cells)

    missing_cells = copy.deepcopy(registry)
    del missing_cells["successors"][shared_index]["cell_ids"]
    with pytest.raises(AssertionError):
        _expand_current_binding_successors(missing_cells)

    duplicate_key = copy.deepcopy(registry)
    duplicate_key["successors"].append(
        copy.deepcopy(duplicate_key["successors"][shared_index])
    )
    with pytest.raises(AssertionError, match="duplicate expanded I1 successor key"):
        _expand_current_binding_successors(duplicate_key)
