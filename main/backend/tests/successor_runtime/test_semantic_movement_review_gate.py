"""P1-P3 semantic movement gate and validator CLI tests."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
_DEFAULT_REPO = _BACKEND.parents[1]
REPO = Path(
    os.environ.get("P1P3_SEMANTIC_MOVEMENT_REPO_ROOT", str(_DEFAULT_REPO))
).resolve()
OUTPUT = Path(os.environ.get("P1P3_SEMANTIC_MOVEMENT_OUTPUT_ROOT", str(REPO))).resolve()
EVIDENCE = (
    OUTPUT / "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence/semantic-movement"
)
VALIDATOR = _BACKEND / "scripts/validate_successor_semantic_movement.py"


def _load(name: str) -> dict:
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))


def _copy_artifacts(destination: Path) -> None:
    for relative in (
        *[
            EVIDENCE / f"fragments/{family}.v1.json"
            for family in ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9")
        ],
        EVIDENCE / "P1P3LegacyDonorSemanticMovementInventory.v1.json",
        EVIDENCE / "P1P3SuccessorMovementMatrix.v1.json",
        EVIDENCE / "P1P3SemanticMovementGate.v1.json",
    ):
        target = destination / relative.relative_to(OUTPUT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(OUTPUT / relative, target)


def test_gate_is_block_dependent_scope_with_exact_blocker_count() -> None:
    gate = _load("P1P3SemanticMovementGate.v1.json")
    matrix = _load("P1P3SuccessorMovementMatrix.v1.json")
    blocker_ids = [
        row["movement_id"]
        for row in matrix["movements"]
        if row["disposition"] == "UNASSIGNED_BLOCKER"
    ]
    assert gate["status"] == "BLOCK_DEPENDENT_SCOPE"
    assert gate["verdict"] == "BLOCK"
    assert gate["counts"]["inline_movements"] == 40
    assert gate["counts"]["external_c7_movements"] == 20
    assert gate["counts"]["total_movements"] == 60
    assert gate["counts"]["unique_movements"] == 60
    assert gate["counts"]["inline_unassigned_blockers"] == len(blocker_ids)
    assert gate["counts"]["external_c7_unassigned_blockers"] == 0
    assert gate["counts"]["exact_blockers_for_this_spec"] == len(blocker_ids)
    assert gate["unassigned_blocker_ids"] == blocker_ids
    assert len(gate["unassigned_blocker_ids"]) == len(set(blocker_ids))


def test_scoped_blocker_gate_never_rolls_back_p0_p3() -> None:
    gate = _load("P1P3SemanticMovementGate.v1.json")
    matrix = _load("P1P3SuccessorMovementMatrix.v1.json")
    scoped = gate["scoped_blocker_gate"]
    assert scoped["does_not_revoke_or_reprove_p0_p3_local_only_state"] is True
    assert "no P0-P3 local-only record is rolled back" in scoped["effect"]
    assert gate["promotion_decision"] is None
    assert gate["promotion_allowed"] is False
    assert gate["aggregate"]["status"] == "BLOCK_DEPENDENT_SCOPE"
    assert gate["aggregate"]["promotion_allowed"] is False
    blocked = set(scoped["blocked_dependency_scopes"])
    if matrix["unassigned_blocker_count"] > 0:
        assert "P4:C7 family" in blocked
        assert "P4:C8 family" in blocked
        assert "P4:C9 family" in blocked
        assert "candidate" in blocked
        assert "authority claim" in blocked
        assert "C7 pilot" not in blocked
    else:
        assert blocked == set()


def test_gate_reports_declared_scope_and_predecessor_gate() -> None:
    gate = _load("P1P3SemanticMovementGate.v1.json")
    matrix = _load("P1P3SuccessorMovementMatrix.v1.json")
    declared = gate["declared_scope_correctness_gate"]
    predecessor = gate["predecessor_to_successor_completeness_gate"]
    assert predecessor["status"] == "PASS"
    assert declared["status"] == "PASS"
    failing = [check for check in declared["checks"] if check["status"] != "PASS"]
    assert failing == []
    declared_by_id = {check["id"]: check for check in declared["checks"]}
    predecessor_by_id = {check["id"]: check for check in predecessor["checks"]}
    assert (
        "zero UNASSIGNED_BLOCKER"
        in declared_by_id["c7_external_exact_binding"]["description"]
    )
    assert (
        f"exact blocker count {matrix['unassigned_blocker_count']}"
        in predecessor_by_id["exact_blocker_count_and_scopes"]["description"]
    )


def test_validator_preserves_all_semantics_for_current_canonical_rebuild() -> None:
    paths = sorted(path for path in EVIDENCE.rglob("*") if path.is_file())
    fragment_paths = list((EVIDENCE / "fragments").glob("*.v1.json"))
    aggregate_names = (
        "P1P3LegacyDonorSemanticMovementInventory.v1.json",
        "P1P3SuccessorMovementMatrix.v1.json",
        "P1P3SemanticMovementGate.v1.json",
    )
    assert len(fragment_paths) == 9
    assert sum((EVIDENCE / name).is_file() for name in aggregate_names) == 3
    snapshot = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths}
    gate = _load("P1P3SemanticMovementGate.v1.json")
    matrix = _load("P1P3SuccessorMovementMatrix.v1.json")
    result = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--repo-root",
            str(REPO),
            "--output-root",
            str(OUTPUT),
        ],
        cwd=_BACKEND,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    checks = {check["id"]: check for check in payload["checks"]}
    assert checks["canonical_rebuild_matches"]["status"] == "PASS"
    assert checks["canonical_rebuild_matches"]["detail"]["drift"] == []
    assert checks["gate_consistency"]["detail"] == gate["counts"]
    assert gate["counts"] == {
        "exact_blockers_for_this_spec": 0,
        "external_c7_movements": 20,
        "external_c7_unassigned_blockers": 0,
        "inline_movements": 40,
        "inline_unassigned_blockers": 0,
        "total_movements": 60,
        "unique_movements": 60,
    }
    assert gate["unassigned_blocker_ids"] == []
    assert matrix["unassigned_blocker_count"] == 0
    assert matrix["unassigned_blocker_ids"] == []
    assert gate["predecessor_to_successor_completeness_gate"]["status"] == "PASS"
    assert all(check["status"] == "PASS" for check in payload["checks"])
    after = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths}
    assert after == snapshot


def test_validator_detects_canonical_rebuild_drift_without_mutating_source(
    tmp_path: Path,
) -> None:
    drifted_root = tmp_path / "drifted-output"
    _copy_artifacts(drifted_root)
    source = EVIDENCE / "P1P3SuccessorMovementMatrix.v1.json"
    source_snapshot = (source.read_bytes(), source.stat().st_mtime_ns)
    drifted = drifted_root / source.relative_to(OUTPUT)
    drifted.write_text(
        json.dumps(json.loads(source.read_text(encoding="utf-8")), indent=2) + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--repo-root",
            str(REPO),
            "--output-root",
            str(drifted_root),
        ],
        cwd=_BACKEND,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "FAIL"
    checks = {check["id"]: check for check in payload["checks"]}
    assert checks["canonical_rebuild_matches"]["status"] == "FAIL"
    assert checks["canonical_rebuild_matches"]["detail"]["drift"] == [
        source.relative_to(OUTPUT).as_posix()
    ]
    assert {
        check_id: check["status"]
        for check_id, check in checks.items()
        if check_id != "canonical_rebuild_matches"
    } == {
        check_id: "PASS"
        for check_id in checks
        if check_id != "canonical_rebuild_matches"
    }
    assert (source.read_bytes(), source.stat().st_mtime_ns) == source_snapshot


def test_validator_cli_fails_on_tampered_gate(tmp_path: Path) -> None:
    tampered_root = tmp_path / "tampered-output"
    _copy_artifacts(tampered_root)
    gate = tampered_root / (
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-08-30-functorial-successor-migration/evidence/semantic-movement/"
        "P1P3SemanticMovementGate.v1.json"
    )
    gate.write_text(
        gate.read_text(encoding="utf-8").replace(
            '"BLOCK_DEPENDENT_SCOPE"', '"PASS"', 1
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--repo-root",
            str(REPO),
            "--output-root",
            str(tampered_root),
        ],
        cwd=_BACKEND,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "FAIL"


def test_validator_fails_when_c7_design_sha_binding_is_stale(tmp_path: Path) -> None:
    tampered_root = tmp_path / "stale-design-sha"
    _copy_artifacts(tampered_root)
    matrix = tampered_root / (
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-08-30-functorial-successor-migration/evidence/semantic-movement/"
        "P1P3SuccessorMovementMatrix.v1.json"
    )
    data = json.loads(matrix.read_text(encoding="utf-8"))
    data["c7_external_binding"]["design_sha256"] = (
        "6416b6d0febdbb4f0e91c9b19654a46d738a889acd99118b436c570bc9325c7d"
    )
    matrix.write_text(
        json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--repo-root",
            str(REPO),
            "--output-root",
            str(tampered_root),
        ],
        cwd=_BACKEND,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    c7_check = next(
        check
        for check in payload["checks"]
        if check["id"] == "c7_external_exact_binding"
    )
    assert c7_check["status"] == "FAIL"
