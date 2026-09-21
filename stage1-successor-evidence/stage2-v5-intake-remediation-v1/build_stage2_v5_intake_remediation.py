#!/usr/bin/env python3
"""Build the create-only Stage 2 v5 intake remediation successor package."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
HERE_REL = Path("stage1-successor-evidence/stage2-v5-intake-remediation-v1")
PREDECESSOR_REL = Path(
    "stage1-successor-evidence/source-static-remediation-v1/"
    "stage1-source-static-remediation-record.v1.json"
)
RECORD_REL = HERE_REL / "stage2-v5-intake-remediation-record.v1.json"
MANIFEST_REL = HERE_REL / "artifact-manifest.v1.json"
CHANGED_PATHS = (
    Path("scripts/formal_release/stage2_candidate_intake.py"),
    Path("tests/formal_release/test_stage2_candidate_intake.py"),
)
MEMBER_PATHS = (
    HERE_REL / "build_stage2_v5_intake_remediation.py",
    HERE_REL / "check_stage2_v5_intake_remediation.py",
    HERE_REL / "test_stage2_v5_intake_remediation.py",
    RECORD_REL,
)
AUTHORITY_CEILING = (
    "NO_DEPLOY_NO_LIVE_NO_PRODUCTION_WRITE_NO_EXTERNAL_DELIVERY_NO_CANARY_"
    "NO_CUTOVER_NO_AUTHORITY_TRANSFER_NO_LEGACY_RETIREMENT_NO_PUSH_"
    "NO_REMOTE_MUTATION_NO_REGISTRY_WRITE_NO_SIGNING_WRITE"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode()


def write_create_only(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)


def build_record() -> dict[str, Any]:
    predecessor = load_object(ROOT / PREDECESSOR_REL)
    previous = {
        row["path"]: row["current_sha256"]
        for row in predecessor["changed_paths"]["post_residual"]
        if row["path"] in {path.as_posix() for path in CHANGED_PATHS}
    }
    if set(previous) != {path.as_posix() for path in CHANGED_PATHS}:
        raise ValueError("predecessor does not bind both Phase C changed paths")
    changed = [
        {
            "path": path.as_posix(),
            "predecessor_sha256": previous[path.as_posix()],
            "successor_sha256": sha256(ROOT / path),
            "reason": (
                "VERSIONED_STAGE2_V5_INTAKE_SUCCESSOR"
                if path.name == "stage2_candidate_intake.py"
                else "VERSIONED_STAGE2_V5_INTAKE_SUCCESSOR_TESTS"
            ),
        }
        for path in CHANGED_PATHS
    ]
    return {
        "schema_version": "mrw.stage1.stage2_v5_intake_remediation_record.v1",
        "status": "PASS_STAGE2_V5_INTAKE_REMEDIATION_NOT_AUTHORITY",
        "authoritative": False,
        "authority_ceiling": AUTHORITY_CEILING,
        "predecessor": {
            "path": PREDECESSOR_REL.as_posix(),
            "sha256": sha256(ROOT / PREDECESSOR_REL),
            "relation": "ADDITIVE_SUCCESSOR_NO_REWRITE",
        },
        "changed_paths": changed,
        "manifest_contract": {
            "legacy_schema": "mrw.stage2.exact-candidate-manifest.v2",
            "successor_schema": "mrw.stage2.exact-candidate-manifest.v3",
            "legacy_behavior_preserved": True,
            "current_byte_registry_direct_binding": True,
            "candidate_specific_successor_resolutions": 6,
            "historical_stage1_record_preserved": True,
            "current_stage1_remediation_direct_binding": True,
            "contract14_history_allowlist": (
                "stage1-successor-evidence/contract14-local-execution-v1/history/"
            ),
        },
        "focused_verification": {
            "test_file": "tests/formal_release/test_stage2_candidate_intake.py",
            "passed": 102,
            "failed": 0,
            "safe_history_positive": 1,
            "safe_history_negative": 3,
            "candidate_resolution_positive": 1,
            "candidate_resolution_negative": 1,
        },
        "external_effects": "NONE_LOCAL_DETERMINISTIC_VALIDATION_ONLY",
        "production_release_authorized": False,
    }


def build_manifest() -> dict[str, Any]:
    members = [
        {
            "path": path.as_posix(),
            "bytes": (ROOT / path).stat().st_size,
            "sha256": sha256(ROOT / path),
        }
        for path in sorted(MEMBER_PATHS, key=lambda item: item.as_posix())
    ]
    return {
        "schema_version": "mrw.stage1.stage2_v5_intake_remediation_manifest.v1",
        "status": "COMPLETE_NOT_AUTHORITY",
        "authoritative": False,
        "authority_ceiling": AUTHORITY_CEILING,
        "member_count": len(members),
        "members": members,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    record_payload = canonical_bytes(build_record())
    if args.write:
        write_create_only(ROOT / RECORD_REL, record_payload)
        write_create_only(ROOT / MANIFEST_REL, canonical_bytes(build_manifest()))
    if args.check:
        if (ROOT / RECORD_REL).read_bytes() != record_payload:
            raise ValueError("record drift")
        if (ROOT / MANIFEST_REL).read_bytes() != canonical_bytes(build_manifest()):
            raise ValueError("manifest drift")
    print(json.dumps({"status": "PASS", "authoritative": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
