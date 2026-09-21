#!/usr/bin/env python3
# ruff: noqa: E501, TRY003
"""Validate the final Stage 2 v6 workflow-equivalent intake package."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
HERE = Path("stage1-successor-evidence/stage2-v6-intake-remediation-v5")
V4 = Path("stage1-successor-evidence/stage2-v6-intake-remediation-v4")
V4_RECORD = V4 / "stage2-v6-intake-remediation-record.v4.json"
V4_MANIFEST = V4 / "artifact-manifest.v4.json"
V4_VALIDATION = V4 / "validation-receipt.v4.json"
V4_HASHES = {
    V4_RECORD: "61e99ae5bbdbb679a1fa670e7ebc99db865e04ee0e693baf313e9bb729100dd2",
    V4_MANIFEST: "a76c62a0912d37ed2782ed8fc35efae81f4affa00e97757fec21610bf2fb95a2",
    V4_VALIDATION: "ac310817d2c29a43f1ede4b398c7b10580b090166dca7b2d652239a23ed52c21",
}
RECORD = HERE / "stage2-v6-intake-remediation-record.v5.json"
MANIFEST = HERE / "artifact-manifest.v5.json"
VALIDATION = HERE / "validation-receipt.v5.json"
CHECKER = HERE / Path(__file__).name
CHANGED = (
    Path("scripts/formal_release/source_closure.py"),
    Path("scripts/formal_release/stage2_candidate_intake.py"),
    Path("tests/formal_release/test_source_closure.py"),
    Path("tests/formal_release/test_stage2_candidate_intake.py"),
)
CEILING = (
    "NO_DEPLOY_NO_LIVE_NO_PRODUCTION_WRITE_NO_EXTERNAL_DELIVERY_NO_CANARY_"
    "NO_CUTOVER_NO_AUTHORITY_TRANSFER_NO_LEGACY_RETIREMENT_NO_PUSH_"
    "NO_REMOTE_MUTATION_NO_REGISTRY_WRITE_NO_SIGNING_WRITE"
)


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON_ROOT:{path}")
    return value


def validate_manifest(manifest: dict[str, Any]) -> None:
    require(manifest.get("schema_version") == "mrw.stage1.stage2_v6_intake_remediation_manifest.v5", "MANIFEST_SCHEMA")
    require(manifest.get("status") == "COMPLETE_NOT_AUTHORITY", "MANIFEST_STATUS")
    require(manifest.get("authoritative") is False and manifest.get("authority_ceiling") == CEILING, "MANIFEST_AUTHORITY")
    members = manifest.get("members")
    require(isinstance(members, list) and len(members) == manifest.get("member_count") == 6, "MANIFEST_COUNT")
    paths = [row.get("path") for row in members]
    require(paths == sorted(paths) and len(paths) == len(set(paths)), "MANIFEST_PATHS")
    for row in members:
        path = ROOT / row["path"]
        require(path.is_file() and path.stat().st_size == row["bytes"] and sha(path) == row["sha256"], f"MANIFEST_MEMBER:{row['path']}")


def validate_record(record: dict[str, Any]) -> None:
    require(record.get("schema_version") == "mrw.stage1.stage2_v6_intake_remediation_record.v5", "RECORD_SCHEMA")
    require(record.get("status") == "PASS_STAGE2_V6_WORKFLOW_EQUIVALENT_INTAKE_NOT_AUTHORITY", "RECORD_STATUS")
    require(record.get("authoritative") is False and record.get("production_release_authorized") is False, "RECORD_AUTHORITY")
    require(record.get("authority_ceiling") == CEILING, "RECORD_CEILING")
    predecessor = record.get("predecessor")
    require(predecessor.get("disposition") == "SUPERSEDED_CURRENT_HASH_DRIFT_PRESERVED_AS_HISTORY", "PREDECESSOR_DISPOSITION")
    for key, path in (("record", V4_RECORD), ("manifest", V4_MANIFEST), ("validation", V4_VALIDATION)):
        require(sha(ROOT / path) == V4_HASHES[path], f"V4_{key.upper()}_HASH")
        require(predecessor[key] == {"path": path.as_posix(), "sha256": V4_HASHES[path]}, f"V4_{key.upper()}_BINDING")
    v4 = load(ROOT / V4_RECORD)
    previous = {row["path"]: row["successor_sha256"] for row in v4["changed_paths"]}
    rows = record.get("changed_paths")
    require(isinstance(rows, list) and [row.get("path") for row in rows] == [path.as_posix() for path in CHANGED], "CHANGED_PATHS")
    for row in rows:
        require(row["predecessor_sha256"] == previous[row["path"]], f"CHANGED_PREDECESSOR:{row['path']}")
        require(row["successor_sha256"] == sha(ROOT / row["path"]), f"CHANGED_CURRENT:{row['path']}")
    verification = record.get("verification")
    require(verification["source_and_intake_tests"] == {"passed": 139, "failed": 0}, "FOCUSED_TESTS")
    selector = verification["source_selector"]
    require((selector["passed"], selector["failed"], selector["errors"], selector["skipped"]) == (1793, 0, 0, 0), "SOURCE_SELECTOR_COUNTS")
    for name in ("log", "junit"):
        ref = selector[name]
        require(sha(ROOT / ref["path"]) == ref["sha256"], f"SOURCE_SELECTOR_{name.upper()}")
    sys.dont_write_bytecode = True
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from scripts.formal_release import source_closure, stage2_candidate_intake as intake

    require(hasattr(source_closure, "check_workflow_selector_manifest_closure"), "CLOSURE_API")
    require(intake.WORKFLOW_EQUIVALENT_STAGE1_REMEDIATION_RECORD == RECORD, "CURRENT_RECORD")
    require(intake.WORKFLOW_EQUIVALENT_STAGE1_REMEDIATION_CHECKER == CHECKER, "CURRENT_CHECKER")


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode()


def receipt_payload() -> dict[str, Any]:
    return {
        "schema_version": "mrw.stage1.stage2_v6_intake_remediation_validation.v5",
        "status": "PASS",
        "authoritative": False,
        "record": {"path": RECORD.as_posix(), "sha256": sha(ROOT / RECORD)},
        "manifest": {"path": MANIFEST.as_posix(), "sha256": sha(ROOT / MANIFEST)},
        "checks": {
            "v4_failed_history_preserved": True,
            "current_four_path_hashes": True,
            "source_and_intake_focused_tests_pass": True,
            "source_selector_pass_evidence_retained": True,
            "v5_constants_bound": True,
        },
        "authority_ceiling": CEILING,
    }


def create(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-receipt", action="store_true")
    parser.add_argument("--check-receipt", action="store_true")
    args = parser.parse_args()
    validate_manifest(load(ROOT / MANIFEST))
    validate_record(load(ROOT / RECORD))
    payload = canonical(receipt_payload())
    if args.write_receipt:
        create(ROOT / VALIDATION, payload)
    if args.check_receipt:
        require((ROOT / VALIDATION).read_bytes() == payload, "VALIDATION_DRIFT")
    print(json.dumps({"status": "PASS", "authoritative": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
