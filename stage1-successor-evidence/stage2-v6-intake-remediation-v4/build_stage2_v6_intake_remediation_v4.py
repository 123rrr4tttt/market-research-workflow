#!/usr/bin/env python3
# ruff: noqa: E501, TRY003
"""Build the create-only final workflow-equivalent Stage 2 v6 intake package."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
HERE_REL = Path("stage1-successor-evidence/stage2-v6-intake-remediation-v4")
V3_ROOT = Path("stage1-successor-evidence/stage2-v6-intake-remediation-v3")
V3_RECORD_REL = V3_ROOT / "stage2-v6-intake-remediation-record.v3.json"
V3_MANIFEST_REL = V3_ROOT / "artifact-manifest.corrected2.v3.json"
V3_VALIDATION_REL = V3_ROOT / "validation-receipt.corrected2.v3.json"
RECORD_REL = HERE_REL / "stage2-v6-intake-remediation-record.v4.json"
MANIFEST_REL = HERE_REL / "artifact-manifest.v4.json"
VALIDATION_REL = HERE_REL / "validation-receipt.v4.json"
BUILDER_REL = HERE_REL / Path(__file__).name
CHECKER_REL = HERE_REL / "check_stage2_v6_intake_remediation_v4.py"
TEST_REL = HERE_REL / "test_stage2_v6_intake_remediation_v4.py"
RAW_LOG_REL = HERE_REL / "raw/source-selector.final.log"
RAW_JUNIT_REL = HERE_REL / "raw/source-selector.final.xml"
SOURCE_LOG = Path("/private/tmp/mrw-stage12-v6-source-selector.final.log")
SOURCE_JUNIT = Path("/private/tmp/mrw-stage12-v6-source-selector.final.xml")
SOURCE_LOG_SHA256 = "97b26df9e9e70b071e9b2308fea906aecf1cef85bd512d346d671f0ea62aad1c"
SOURCE_JUNIT_SHA256 = "2ee9878a74628727b1442190e7212530a3c12014558e837768df38d918d0cfe4"
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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"JSON root must be an object: {path}")
    return value


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode()


def write_create_only(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)


def build_record() -> dict[str, Any]:
    predecessor = load_object(ROOT / V3_RECORD_REL)
    previous = {row["path"]: row["successor_sha256"] for row in predecessor["changed_paths"]}
    expected = {path.as_posix() for path in CHANGED_PATHS}
    if set(previous) != expected:
        raise ValueError("v3 predecessor path set drift")
    changed = [
        {
            "path": path.as_posix(),
            "predecessor_sha256": previous[path.as_posix()],
            "successor_sha256": sha256(ROOT / path),
            "reason": (
                "WORKFLOW_DELTA_STAGE0_CLOSURE_DEDUPLICATION"
                if "stage2_candidate_intake" in path.name
                else "UNCHANGED_FROM_V3" if previous[path.as_posix()] == sha256(ROOT / path)
                else "BIND_FOCUSED_REGRESSION_FOR_STAGE0_CLOSURE_DEDUPLICATION"
            ),
        }
        for path in CHANGED_PATHS
    ]
    return {
        "schema_version": "mrw.stage1.stage2_v6_intake_remediation_record.v4",
        "status": "PASS_STAGE2_V6_WORKFLOW_EQUIVALENT_INTAKE_NOT_AUTHORITY",
        "authoritative": False,
        "authority_ceiling": AUTHORITY_CEILING,
        "predecessor": {
            "record": {"path": V3_RECORD_REL.as_posix(), "sha256": sha256(ROOT / V3_RECORD_REL)},
            "manifest": {"path": V3_MANIFEST_REL.as_posix(), "sha256": sha256(ROOT / V3_MANIFEST_REL)},
            "validation": {"path": V3_VALIDATION_REL.as_posix(), "sha256": sha256(ROOT / V3_VALIDATION_REL)},
            "relation": "ADDITIVE_SUCCESSOR_NO_REWRITE",
        },
        "changed_paths": changed,
        "workflow_selector_closure": {
            "roots": ["main/backend", "main/ops", "src/mrw_functorial_kit", "ops", "scripts"],
            "delta_operations": ["UPSERT", "DELETE"],
            "stage0_closure_upserts_satisfy_matching_workflow_upserts": True,
            "stage0_delete_conflicts_fail_closed": True,
            "candidate_local_full_selector_remains_final_gate": True,
        },
        "focused_verification": {
            "source_and_intake_tests": {"passed": 139, "failed": 0},
            "source_selector": {
                "passed": 1793,
                "failed": 0,
                "errors": 0,
                "skipped": 0,
                "deselected": 2329,
                "warnings": 25,
                "subtests_passed": 52,
                "log": {"path": RAW_LOG_REL.as_posix(), "sha256": sha256(ROOT / RAW_LOG_REL)},
                "junit": {"path": RAW_JUNIT_REL.as_posix(), "sha256": sha256(ROOT / RAW_JUNIT_REL)},
            },
            "ruff": "PASS",
            "compileall": "PASS",
        },
        "current_bindings": {
            "record_path": RECORD_REL.as_posix(),
            "checker_path": CHECKER_REL.as_posix(),
            "record_schema": "mrw.stage1.stage2_v6_intake_remediation_record.v4",
        },
        "external_effects": "NONE_LOCAL_DETERMINISTIC_VALIDATION_ONLY",
        "production_release_authorized": False,
    }


def build_manifest() -> dict[str, Any]:
    members = [
        {"path": path.as_posix(), "bytes": (ROOT / path).stat().st_size, "sha256": sha256(ROOT / path)}
        for path in sorted((BUILDER_REL, CHECKER_REL, TEST_REL, RECORD_REL, RAW_LOG_REL, RAW_JUNIT_REL), key=lambda item: item.as_posix())
    ]
    return {
        "schema_version": "mrw.stage1.stage2_v6_intake_remediation_manifest.v4",
        "status": "COMPLETE_NOT_AUTHORITY",
        "authoritative": False,
        "authority_ceiling": AUTHORITY_CEILING,
        "member_count": len(members),
        "members": members,
    }


def load_checker():
    spec = importlib.util.spec_from_file_location("stage2_v6_intake_remediation_checker_v4", ROOT / CHECKER_REL)
    if spec is None or spec.loader is None:
        raise RuntimeError("checker module spec missing")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.write:
        outputs = (ROOT / RECORD_REL, ROOT / MANIFEST_REL, ROOT / VALIDATION_REL, ROOT / RAW_LOG_REL, ROOT / RAW_JUNIT_REL)
        existing = [path for path in outputs if path.exists() or path.is_symlink()]
        if existing:
            raise FileExistsError(f"create-only outputs already exist: {existing}")
        if sha256(SOURCE_LOG) != SOURCE_LOG_SHA256 or sha256(SOURCE_JUNIT) != SOURCE_JUNIT_SHA256:
            raise ValueError("source selector evidence drift")
        (ROOT / RAW_LOG_REL).parent.mkdir(mode=0o755)
        write_create_only(ROOT / RAW_LOG_REL, SOURCE_LOG.read_bytes())
        write_create_only(ROOT / RAW_JUNIT_REL, SOURCE_JUNIT.read_bytes())
        write_create_only(ROOT / RECORD_REL, canonical_bytes(build_record()))
        write_create_only(ROOT / MANIFEST_REL, canonical_bytes(build_manifest()))
    if args.check:
        checker = load_checker()
        checker.validate_manifest(checker.load_object(ROOT / MANIFEST_REL))
        checker.validate_record(checker.load_object(ROOT / RECORD_REL))
        if (ROOT / RECORD_REL).read_bytes() != canonical_bytes(build_record()):
            raise ValueError("record drift")
        if (ROOT / MANIFEST_REL).read_bytes() != canonical_bytes(build_manifest()):
            raise ValueError("manifest drift")
    if not args.write and not args.check:
        parser.error("select --write or --check")
    print(json.dumps({"status": "PASS", "authoritative": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
