#!/usr/bin/env python3
# ruff: noqa: E501, TRY003
"""Fail-closed checker for corrected Stage 2 v5 intake remediation v2."""

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
HERE_REL = Path("stage1-successor-evidence/stage2-v5-intake-remediation-v2")
RECORD_REL = HERE_REL / "stage2-v5-intake-remediation-record.v2.json"
MANIFEST_REL = HERE_REL / "artifact-manifest.v2.json"
VALIDATION_REL = HERE_REL / "validation-receipt.v2.json"
V1_ROOT = Path("stage1-successor-evidence/stage2-v5-intake-remediation-v1")
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


def validate_v1_predecessor(v1_record: dict[str, Any]) -> None:
    v1_checker = load_module(
        "stage2_v5_intake_remediation_v1_checker",
        ROOT / V1_ROOT / "check_stage2_v5_intake_remediation.py",
    )
    v1_checker.validate_manifest(load_object(ROOT / V1_ROOT / "artifact-manifest.v1.json"))
    source_static = load_object(ROOT / v1_record["predecessor"]["path"])
    require(sha256(ROOT / v1_record["predecessor"]["path"]) == v1_record["predecessor"]["sha256"], "V1_SOURCE_STATIC_HASH")
    v1_checker.validate_predecessor_except_successor_paths(source_static)
    require(v1_record["schema_version"] == "mrw.stage1.stage2_v5_intake_remediation_record.v1", "V1_SCHEMA")
    require(v1_record["authoritative"] is False, "V1_AUTHORITY")
    require(v1_record["authority_ceiling"] == AUTHORITY_CEILING, "V1_CEILING")
    require(len(v1_record["changed_paths"]) == 2, "V1_CHANGED_PATHS")


def validate_manifest(manifest: dict[str, Any]) -> None:
    require(manifest.get("schema_version") == "mrw.stage1.stage2_v5_intake_remediation_manifest.v2", "MANIFEST_SCHEMA")
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
    require(record["schema_version"] == "mrw.stage1.stage2_v5_intake_remediation_record.v2", "RECORD_SCHEMA")
    require(record["status"] == "PASS_STAGE2_V5_INTAKE_REMEDIATION_NOT_AUTHORITY", "RECORD_STATUS")
    require(record["authoritative"] is False and record["production_release_authorized"] is False, "RECORD_AUTHORITY")
    require(record["authority_ceiling"] == AUTHORITY_CEILING, "RECORD_CEILING")
    predecessor = record["predecessor"]
    require(predecessor["relation"] == "ADDITIVE_CORRECTION_NO_REWRITE", "PREDECESSOR_RELATION")
    require(sha256(ROOT / predecessor["path"]) == predecessor["sha256"], "PREDECESSOR_HASH")
    require(sha256(ROOT / predecessor["validation_path"]) == predecessor["validation_sha256"], "PREDECESSOR_VALIDATION_HASH")
    v1_record = load_object(ROOT / predecessor["path"])
    validate_v1_predecessor(v1_record)
    previous = {row["path"]: row["successor_sha256"] for row in v1_record["changed_paths"]}
    rows = record["changed_paths"]
    require([row["path"] for row in rows] == sorted(row["path"] for row in rows), "CHANGED_ORDER")
    require(len(rows) == 2 and len({row["path"] for row in rows}) == 2, "CHANGED_COUNT")
    for row in rows:
        require(row["predecessor_sha256"] == previous[row["path"]], f"CHANGED_PREDECESSOR:{row['path']}")
        require(row["successor_sha256"] == sha256(ROOT / row["path"]), f"CHANGED_SUCCESSOR:{row['path']}")
    contract = record["manifest_contract"]
    require(contract["legacy_schema"] == "mrw.stage2.exact-candidate-manifest.v2", "LEGACY_SCHEMA")
    require(contract["successor_schema"] == "mrw.stage2.exact-candidate-manifest.v3", "SUCCESSOR_SCHEMA")
    require(contract["legacy_behavior_preserved"] is True, "LEGACY_PRESERVATION")
    require(contract["candidate_specific_successor_resolutions"] == 6, "RESOLUTION_COUNT")
    require(contract["remediation_successor_chain_preserved"] is True, "SUCCESSOR_CHAIN")
    current_checker = subprocess.run(
        [sys.executable, str(ROOT / "stage1-successor-evidence/current-byte-remediation-v1/bindings/check_current_byte_binding_successors.py"), "--repo-root", str(ROOT)],
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        check=False,
        capture_output=True,
        text=True,
    )
    require(current_checker.returncode == 0, f"CURRENT_BYTE_CHECKER:{current_checker.stderr.strip()}")
    intake = load_module("stage2_v5_intake_v2", ROOT / "scripts/formal_release/stage2_candidate_intake.py")
    require(intake.DEFAULT_STAGE1_REMEDIATION_RECORD == RECORD_REL, "CURRENT_DEFAULT_REMEDIATION")
    allowed = "stage1-successor-evidence/contract14-local-execution-v1/history/history-verification-receipt.v1.json"
    require(intake.safe_relative(allowed).as_posix() == allowed, "HISTORY_ALLOWLIST_POSITIVE")


def validation_receipt() -> dict[str, Any]:
    return {
        "schema_version": "mrw.stage1.stage2_v5_intake_remediation_validation.v2",
        "status": "PASS",
        "authoritative": False,
        "record": {"path": RECORD_REL.as_posix(), "sha256": sha256(ROOT / RECORD_REL)},
        "artifact_manifest": {"path": MANIFEST_REL.as_posix(), "sha256": sha256(ROOT / MANIFEST_REL)},
        "checks": {
            "v1_predecessor_and_validation_immutable": True,
            "source_static_predecessor_non_successor_paths_current": True,
            "legacy_v2_preserved": True,
            "v3_direct_bindings_and_six_resolutions": True,
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
    validate_manifest(load_object(ROOT / MANIFEST_REL))
    validate_record(load_object(ROOT / RECORD_REL))
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
