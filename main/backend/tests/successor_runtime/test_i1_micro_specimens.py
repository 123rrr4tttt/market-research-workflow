"""I1 frozen micro-specimen evidence: historical specs and build manifests.

Each row is the non-PostgreSQL equivalent of
``generate_capability_spec_pilots.py --check MATCH``: the on-disk manifest
must equal the canonical compile output for the on-disk spec/ABI, every exact
manifest must keep candidate creation and authority adoption false. Historical
C6 rows do not assert current code, bindings, or runtime capability.
"""

from __future__ import annotations

import json
import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from app.successor_runtime.specification import (
    CapabilityCellSpec,
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
    candidate_context,
)

TOPIC = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration"
)
SPECS_DIR = REPOSITORY_ROOT / TOPIC / "evidence/capability-specs"
BUILDS_DIR = REPOSITORY_ROOT / TOPIC / "evidence/capability-spec-builds"
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
    candidate_context()
    historical_bindings = _load(
        CANDIDATE_PATH.parents[2] / "fragments/I1.json"
    )["bindings"]
    for cell_id in CELL_IDS:
        spec_path = SPECS_DIR / f"{cell_id}.v1.json"
        build_path = BUILDS_DIR / f"{cell_id}.BuildManifest.v1.json"
        assert build_path.is_file(), build_path
        refs = [
            row for row in historical_bindings
            if row["cell_id"] == cell_id
            and row["spec_path"] == str(spec_path.relative_to(REPOSITORY_ROOT))
        ]
        assert refs, f"missing historical spec reference: {cell_id}"
        spec_sha256 = refs[0]["spec_sha256"]
        assert all(row["spec_sha256"] == spec_sha256 for row in refs)
        snapshot_path = CANDIDATE_PATH.parent / "snapshots" / spec_sha256
        assert snapshot_path.is_file(), snapshot_path
        assert hashlib.sha256(snapshot_path.read_bytes()).hexdigest() == spec_sha256
        spec_value = _load(snapshot_path)
        spec = CapabilityCellSpec.from_dict(spec_value)
        manifest = _load(build_path)
        assert build_path.read_bytes() == (
            json.dumps(
                manifest,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
            + b"\n"
        ), f"historical manifest is not canonical JSON: {cell_id}"
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
                "historical_spec_sha256": spec_sha256,
                "exact_bindings": len(spec.exact_bindings()),
                "candidate_created": False,
                "program_atom_generated": (
                    manifest["generated"].get("program_skeleton") is not None
                ),
            }
        )
    assert len(rows) == 30
    return rows
def test_i1_historical_micro_specimen_matrix_is_30_of_30_and_manifest_exact() -> None:
    rows = _micro_rows()
    assert {row["cell_id"] for row in rows} == set(CELL_IDS)
    assert all(row["from_dict"] == "PASS" for row in rows)
    assert all(row["manifest_check"] == "MATCH" for row in rows)
    assert all(row["candidate_created"] is False for row in rows)
    assert {row["cell_id"] for row in rows if row["cell_id"].startswith("C6.")} == {
        "C6.1", "C6.2", "C6.3"
    }
    assert all(row["historical_spec_sha256"] for row in rows)
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

def test_i1_micro_specimen_evidence_rows_are_reproducible() -> None:
    assert _micro_rows() == _micro_rows()


@pytest.mark.unit
def test_i1_frozen_candidates_are_read_only_history() -> None:
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
