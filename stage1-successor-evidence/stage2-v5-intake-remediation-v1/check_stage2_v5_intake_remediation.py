#!/usr/bin/env python3
"""Fail-closed checker for the Stage 2 v5 intake remediation successor."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
HERE_REL = Path("stage1-successor-evidence/stage2-v5-intake-remediation-v1")
RECORD_REL = HERE_REL / "stage2-v5-intake-remediation-record.v1.json"
MANIFEST_REL = HERE_REL / "artifact-manifest.v1.json"
VALIDATION_REL = HERE_REL / "validation-receipt.v1.json"
PREDECESSOR_CHECKER = ROOT / (
    "stage1-successor-evidence/source-static-remediation-v1/"
    "check_source_static_remediation_record.py"
)
INTAKE_PATH = ROOT / "scripts/formal_release/stage2_candidate_intake.py"
AUTHORITY_CEILING = (
    "NO_DEPLOY_NO_LIVE_NO_PRODUCTION_WRITE_NO_EXTERNAL_DELIVERY_NO_CANARY_"
    "NO_CUTOVER_NO_AUTHORITY_TRANSFER_NO_LEGACY_RETIREMENT_NO_PUSH_"
    "NO_REMOTE_MUTATION_NO_REGISTRY_WRITE_NO_SIGNING_WRITE"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON_ROOT:{path}")
    return value


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"MODULE_SPEC:{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def validate_predecessor_except_successor_paths(predecessor: dict[str, Any]) -> None:
    checker = load_module("source_static_predecessor_checker", PREDECESSOR_CHECKER)
    checker.validate_manifest(load_object(ROOT / checker.MANIFEST_REL))
    checker.validate_phase_a(predecessor)
    checker.validate_phase_b(predecessor)
    checker.validate_history(predecessor)
    allowed = {
        "scripts/formal_release/stage2_candidate_intake.py",
        "tests/formal_release/test_stage2_candidate_intake.py",
    }
    rows = predecessor["changed_paths"]["post_residual"]
    for row in rows:
        if row["path"] in allowed:
            continue
        require(sha256(ROOT / row["path"]) == row["current_sha256"], f"PREDECESSOR_PATH:{row['path']}")


def validate_manifest(manifest: dict[str, Any]) -> None:
    require(manifest.get("schema_version") == "mrw.stage1.stage2_v5_intake_remediation_manifest.v1", "MANIFEST_SCHEMA")
    require(manifest.get("status") == "COMPLETE_NOT_AUTHORITY", "MANIFEST_STATUS")
    require(manifest.get("authoritative") is False, "MANIFEST_AUTHORITY")
    require(manifest.get("authority_ceiling") == AUTHORITY_CEILING, "MANIFEST_CEILING")
    members = manifest.get("members")
    require(isinstance(members, list) and len(members) == manifest.get("member_count") == 4, "MANIFEST_COUNT")
    paths = [row.get("path") for row in members]
    require(paths == sorted(paths) and len(paths) == len(set(paths)), "MANIFEST_PATHS")
    for row in members:
        path = ROOT / row["path"]
        require(path.is_file(), f"MANIFEST_MISSING:{row['path']}")
        require(path.stat().st_size == row["bytes"], f"MANIFEST_SIZE:{row['path']}")
        require(sha256(path) == row["sha256"], f"MANIFEST_HASH:{row['path']}")


def validate_record(record: dict[str, Any]) -> None:
    require(set(record) == {
        "schema_version", "status", "authoritative", "authority_ceiling",
        "predecessor", "changed_paths", "manifest_contract", "focused_verification",
        "external_effects", "production_release_authorized",
    }, "RECORD_FIELDS")
    require(record["schema_version"] == "mrw.stage1.stage2_v5_intake_remediation_record.v1", "RECORD_SCHEMA")
    require(record["status"] == "PASS_STAGE2_V5_INTAKE_REMEDIATION_NOT_AUTHORITY", "RECORD_STATUS")
    require(record["authoritative"] is False and record["production_release_authorized"] is False, "RECORD_AUTHORITY")
    require(record["authority_ceiling"] == AUTHORITY_CEILING, "RECORD_CEILING")
    predecessor_ref = record["predecessor"]
    predecessor_path = ROOT / predecessor_ref["path"]
    require(predecessor_ref["relation"] == "ADDITIVE_SUCCESSOR_NO_REWRITE", "PREDECESSOR_RELATION")
    require(sha256(predecessor_path) == predecessor_ref["sha256"], "PREDECESSOR_HASH")
    predecessor = load_object(predecessor_path)
    validate_predecessor_except_successor_paths(predecessor)
    rows = record["changed_paths"]
    require(isinstance(rows, list) and len(rows) == 2, "CHANGED_COUNT")
    expected_previous = {
        row["path"]: row["current_sha256"]
        for row in predecessor["changed_paths"]["post_residual"]
    }
    require([row["path"] for row in rows] == sorted(row["path"] for row in rows), "CHANGED_ORDER")
    for row in rows:
        require(row["predecessor_sha256"] == expected_previous[row["path"]], f"CHANGED_PREDECESSOR:{row['path']}")
        require(row["successor_sha256"] == sha256(ROOT / row["path"]), f"CHANGED_SUCCESSOR:{row['path']}")
    contract = record["manifest_contract"]
    require(contract["legacy_schema"] == "mrw.stage2.exact-candidate-manifest.v2", "LEGACY_SCHEMA")
    require(contract["successor_schema"] == "mrw.stage2.exact-candidate-manifest.v3", "SUCCESSOR_SCHEMA")
    require(contract["legacy_behavior_preserved"] is True, "LEGACY_PRESERVATION")
    require(contract["candidate_specific_successor_resolutions"] == 6, "RESOLUTION_COUNT")
    require(contract["current_byte_registry_direct_binding"] is True, "REGISTRY_BINDING")
    require(contract["historical_stage1_record_preserved"] is True, "HISTORICAL_STAGE1")
    require(contract["current_stage1_remediation_direct_binding"] is True, "REMEDIATION_BINDING")
    require(record["focused_verification"] == {
        "test_file": "tests/formal_release/test_stage2_candidate_intake.py",
        "passed": 102,
        "failed": 0,
        "safe_history_positive": 1,
        "safe_history_negative": 3,
        "candidate_resolution_positive": 1,
        "candidate_resolution_negative": 1,
    }, "FOCUSED_VERIFICATION")
    current_checker = subprocess.run(
        [
            sys.executable,
            str(ROOT / "stage1-successor-evidence/current-byte-remediation-v1/bindings/check_current_byte_binding_successors.py"),
            "--repo-root",
            str(ROOT),
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        check=False,
        capture_output=True,
        text=True,
    )
    require(current_checker.returncode == 0, f"CURRENT_BYTE_CHECKER:{current_checker.stderr.strip()}")
    intake = load_module("stage2_v5_intake", INTAKE_PATH)
    allowed = (
        "stage1-successor-evidence/contract14-local-execution-v1/history/"
        "history-verification-receipt.v1.json"
    )
    require(intake.safe_relative(allowed).as_posix() == allowed, "HISTORY_ALLOWLIST_POSITIVE")
    for rejected in (
        "stage1-successor-evidence/other/history/receipt.json",
        "stage1-successor-evidence/contract14-local-execution-v1/history",
        "stage1-successor-evidence/contract14-local-execution-v1/history/cache/data.json",
    ):
        try:
            intake.safe_relative(rejected)
        except intake.Stage2IntakeError:
            pass
        else:
            raise ValueError(f"HISTORY_ALLOWLIST_NEGATIVE:{rejected}")


def validation_receipt() -> dict[str, Any]:
    return {
        "schema_version": "mrw.stage1.stage2_v5_intake_remediation_validation.v1",
        "status": "PASS",
        "authoritative": False,
        "record": {"path": RECORD_REL.as_posix(), "sha256": sha256(ROOT / RECORD_REL)},
        "artifact_manifest": {"path": MANIFEST_REL.as_posix(), "sha256": sha256(ROOT / MANIFEST_REL)},
        "checks": {
            "predecessor_non_successor_paths_current": True,
            "phase_a_phase_b_history_preserved": True,
            "legacy_v2_preserved": True,
            "v3_direct_bindings_and_candidate_resolutions": True,
            "contract14_history_allowlist_exact": True,
            "current_byte_registry_checker_pass": True,
        },
        "authority_ceiling": AUTHORITY_CEILING,
    }


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode()


def write_create_only(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-receipt", action="store_true")
    parser.add_argument("--check-receipt", action="store_true")
    args = parser.parse_args()
    manifest = load_object(ROOT / MANIFEST_REL)
    record = load_object(ROOT / RECORD_REL)
    validate_manifest(manifest)
    validate_record(record)
    receipt = canonical_bytes(validation_receipt())
    if args.write_receipt:
        write_create_only(ROOT / VALIDATION_REL, receipt)
    if args.check_receipt:
        require((ROOT / VALIDATION_REL).read_bytes() == receipt, "VALIDATION_RECEIPT_DRIFT")
    print(json.dumps({"status": "PASS", "authoritative": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        raise SystemExit(1) from exc
