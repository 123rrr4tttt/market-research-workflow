#!/usr/bin/env python3
# ruff: noqa: E501, TRY003
"""Fail-closed checker for the final Stage 2 v6 intake remediation package."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
HERE_REL = Path("stage1-successor-evidence/stage2-v6-intake-remediation-v4")
RECORD_REL = HERE_REL / "stage2-v6-intake-remediation-record.v4.json"
MANIFEST_REL = HERE_REL / "artifact-manifest.v4.json"
VALIDATION_REL = HERE_REL / "validation-receipt.v4.json"
V3_ROOT = Path("stage1-successor-evidence/stage2-v6-intake-remediation-v3")
V3_RECORD_REL = V3_ROOT / "stage2-v6-intake-remediation-record.v3.json"
V3_MANIFEST_REL = V3_ROOT / "artifact-manifest.corrected2.v3.json"
V3_VALIDATION_REL = V3_ROOT / "validation-receipt.corrected2.v3.json"
V3_HASHES = {
    V3_RECORD_REL: "69ed505d428771104dc906b42ebd8f16b5f7b1458edaa785236ae9231d8c6a14",
    V3_MANIFEST_REL: "c57d7fc64c1493a99aa6791fcaafa73ac2e6e7d110a46bf3a601b8ca3d319353",
    V3_VALIDATION_REL: "1f6daaa1bf92228b26c543d1cb85a56520881a4e9210fd0b65633060ad652a33",
}
CHANGED_PATHS = (
    Path("scripts/formal_release/source_closure.py"),
    Path("scripts/formal_release/stage2_candidate_intake.py"),
    Path("tests/formal_release/test_source_closure.py"),
    Path("tests/formal_release/test_stage2_candidate_intake.py"),
)
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


def validate_manifest(manifest: dict[str, Any]) -> None:
    require(manifest.get("schema_version") == "mrw.stage1.stage2_v6_intake_remediation_manifest.v4", "MANIFEST_SCHEMA")
    require(manifest.get("status") == "COMPLETE_NOT_AUTHORITY", "MANIFEST_STATUS")
    require(manifest.get("authoritative") is False, "MANIFEST_AUTHORITY")
    require(manifest.get("authority_ceiling") == AUTHORITY_CEILING, "MANIFEST_CEILING")
    members = manifest.get("members")
    require(isinstance(members, list) and len(members) == manifest.get("member_count") == 6, "MANIFEST_COUNT")
    paths = [row.get("path") for row in members]
    require(paths == sorted(paths) and len(paths) == len(set(paths)), "MANIFEST_PATHS")
    for row in members:
        path = ROOT / row["path"]
        require(path.is_file(), f"MANIFEST_MISSING:{row['path']}")
        require(path.stat().st_size == row["bytes"], f"MANIFEST_SIZE:{row['path']}")
        require(sha256(path) == row["sha256"], f"MANIFEST_HASH:{row['path']}")


def validate_record(record: dict[str, Any]) -> None:
    require(record.get("schema_version") == "mrw.stage1.stage2_v6_intake_remediation_record.v4", "RECORD_SCHEMA")
    require(record.get("status") == "PASS_STAGE2_V6_WORKFLOW_EQUIVALENT_INTAKE_NOT_AUTHORITY", "RECORD_STATUS")
    require(record.get("authoritative") is False and record.get("production_release_authorized") is False, "RECORD_AUTHORITY")
    require(record.get("authority_ceiling") == AUTHORITY_CEILING, "RECORD_CEILING")
    predecessor = record.get("predecessor")
    require(isinstance(predecessor, dict) and predecessor.get("relation") == "ADDITIVE_SUCCESSOR_NO_REWRITE", "PREDECESSOR_RELATION")
    for key, path in (("record", V3_RECORD_REL), ("manifest", V3_MANIFEST_REL), ("validation", V3_VALIDATION_REL)):
        require(sha256(ROOT / path) == V3_HASHES[path], f"V3_{key.upper()}_FROZEN_HASH")
        require(predecessor[key] == {"path": path.as_posix(), "sha256": V3_HASHES[path]}, f"V3_{key.upper()}_BINDING")
    v3 = load_object(ROOT / V3_RECORD_REL)
    previous = {row["path"]: row["successor_sha256"] for row in v3["changed_paths"]}
    rows = record.get("changed_paths")
    require(isinstance(rows, list) and [row.get("path") for row in rows] == [path.as_posix() for path in CHANGED_PATHS], "CHANGED_PATHS")
    for row in rows:
        require(row["predecessor_sha256"] == previous[row["path"]], f"CHANGED_PREDECESSOR:{row['path']}")
        require(row["successor_sha256"] == sha256(ROOT / row["path"]), f"CHANGED_CURRENT:{row['path']}")
    focused = record.get("focused_verification")
    require(focused["source_and_intake_tests"] == {"passed": 139, "failed": 0}, "FOCUSED_TESTS")
    require(focused["source_selector"]["passed"] == 1793 and focused["source_selector"]["skipped"] == 0, "SOURCE_SELECTOR_COUNTS")
    for key in ("log", "junit"):
        ref = focused["source_selector"][key]
        require(sha256(ROOT / ref["path"]) == ref["sha256"], f"SOURCE_SELECTOR_{key.upper()}_HASH")
    sys.dont_write_bytecode = True
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from scripts.formal_release import source_closure, stage2_candidate_intake as intake

    require(hasattr(source_closure, "compute_workflow_selector_delta"), "SOURCE_DELTA_API")
    require(hasattr(source_closure, "check_workflow_selector_manifest_closure"), "SOURCE_CHECK_API")
    require(intake.WORKFLOW_EQUIVALENT_STAGE1_REMEDIATION_RECORD == RECORD_REL, "CURRENT_RECORD_CONSTANT")
    require(intake.WORKFLOW_EQUIVALENT_STAGE1_REMEDIATION_CHECKER == HERE_REL / Path(__file__).name, "CURRENT_CHECKER_CONSTANT")


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode()


def validation_receipt() -> dict[str, Any]:
    return {
        "schema_version": "mrw.stage1.stage2_v6_intake_remediation_validation.v4",
        "status": "PASS",
        "authoritative": False,
        "record": {"path": RECORD_REL.as_posix(), "sha256": sha256(ROOT / RECORD_REL)},
        "artifact_manifest": {"path": MANIFEST_REL.as_posix(), "sha256": sha256(ROOT / MANIFEST_REL)},
        "checks": {
            "v3_history_immutable": True,
            "current_four_path_hashes": True,
            "workflow_delta_stage0_overlap_closed": True,
            "source_selector_pass_evidence_retained": True,
            "v4_intake_constants_bound": True,
        },
        "authority_ceiling": AUTHORITY_CEILING,
    }


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
    raise SystemExit(main())
