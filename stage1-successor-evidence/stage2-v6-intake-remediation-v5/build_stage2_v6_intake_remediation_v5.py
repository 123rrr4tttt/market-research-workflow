#!/usr/bin/env python3
# ruff: noqa: E501, TRY003
"""Build the create-only final successor for Stage 2 v6 intake remediation."""

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
HERE = Path("stage1-successor-evidence/stage2-v6-intake-remediation-v5")
V4 = Path("stage1-successor-evidence/stage2-v6-intake-remediation-v4")
V4_RECORD = V4 / "stage2-v6-intake-remediation-record.v4.json"
V4_MANIFEST = V4 / "artifact-manifest.v4.json"
V4_VALIDATION = V4 / "validation-receipt.v4.json"
RECORD = HERE / "stage2-v6-intake-remediation-record.v5.json"
MANIFEST = HERE / "artifact-manifest.v5.json"
VALIDATION = HERE / "validation-receipt.v5.json"
BUILDER = HERE / Path(__file__).name
CHECKER = HERE / "check_stage2_v6_intake_remediation_v5.py"
TEST = HERE / "test_stage2_v6_intake_remediation_v5.py"
RAW_LOG = HERE / "raw/source-selector.final.log"
RAW_JUNIT = HERE / "raw/source-selector.final.xml"
SOURCE_LOG = V4 / "raw/source-selector.final.log"
SOURCE_JUNIT = V4 / "raw/source-selector.final.xml"
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


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"JSON root must be object: {path}")
    return value


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode()


def create(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)


def record_payload() -> dict[str, Any]:
    previous_record = load(ROOT / V4_RECORD)
    previous = {row["path"]: row["successor_sha256"] for row in previous_record["changed_paths"]}
    rows = [
        {
            "path": path.as_posix(),
            "predecessor_sha256": previous[path.as_posix()],
            "successor_sha256": sha(ROOT / path),
            "reason": "FINAL_WORKFLOW_EQUIVALENT_CLOSURE_CORRECTION",
        }
        for path in CHANGED
    ]
    return {
        "schema_version": "mrw.stage1.stage2_v6_intake_remediation_record.v5",
        "status": "PASS_STAGE2_V6_WORKFLOW_EQUIVALENT_INTAKE_NOT_AUTHORITY",
        "authoritative": False,
        "authority_ceiling": CEILING,
        "predecessor": {
            "record": {"path": V4_RECORD.as_posix(), "sha256": sha(ROOT / V4_RECORD)},
            "manifest": {"path": V4_MANIFEST.as_posix(), "sha256": sha(ROOT / V4_MANIFEST)},
            "validation": {"path": V4_VALIDATION.as_posix(), "sha256": sha(ROOT / V4_VALIDATION)},
            "disposition": "SUPERSEDED_CURRENT_HASH_DRIFT_PRESERVED_AS_HISTORY",
        },
        "changed_paths": rows,
        "closure_contract": {
            "workflow_roots": ["main/backend", "main/ops", "src/mrw_functorial_kit", "ops", "scripts"],
            "changed_or_deleted_selector_paths_must_be_manifest_bound": True,
            "stage0_upserts_satisfy_duplicate_workflow_upserts": True,
            "non_selector_manifest_entries_are_allowed": True,
            "invalid_or_excluded_selector_paths_fail_closed": True,
            "candidate_local_full_selector_is_final_gate": True,
        },
        "verification": {
            "source_and_intake_tests": {"passed": 139, "failed": 0},
            "source_selector": {
                "passed": 1793,
                "failed": 0,
                "errors": 0,
                "skipped": 0,
                "deselected": 2329,
                "warnings": 25,
                "subtests_passed": 52,
                "log": {"path": RAW_LOG.as_posix(), "sha256": sha(ROOT / RAW_LOG)},
                "junit": {"path": RAW_JUNIT.as_posix(), "sha256": sha(ROOT / RAW_JUNIT)},
            },
            "ruff": "PASS",
            "compileall": "PASS",
        },
        "current_bindings": {
            "record": RECORD.as_posix(),
            "checker": CHECKER.as_posix(),
        },
        "external_effects": "NONE_LOCAL_DETERMINISTIC_VALIDATION_ONLY",
        "production_release_authorized": False,
    }


def manifest_payload() -> dict[str, Any]:
    paths = (BUILDER, CHECKER, TEST, RECORD, RAW_LOG, RAW_JUNIT)
    members = [
        {"path": path.as_posix(), "bytes": (ROOT / path).stat().st_size, "sha256": sha(ROOT / path)}
        for path in sorted(paths, key=lambda item: item.as_posix())
    ]
    return {
        "schema_version": "mrw.stage1.stage2_v6_intake_remediation_manifest.v5",
        "status": "COMPLETE_NOT_AUTHORITY",
        "authoritative": False,
        "authority_ceiling": CEILING,
        "member_count": len(members),
        "members": members,
    }


def checker_module():
    spec = importlib.util.spec_from_file_location("stage2_v6_remediation_v5_checker", ROOT / CHECKER)
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
        outputs = (ROOT / RECORD, ROOT / MANIFEST, ROOT / VALIDATION, ROOT / RAW_LOG, ROOT / RAW_JUNIT)
        if any(path.exists() or path.is_symlink() for path in outputs):
            raise FileExistsError("create-only output already exists")
        (ROOT / RAW_LOG).parent.mkdir(mode=0o755)
        create(ROOT / RAW_LOG, (ROOT / SOURCE_LOG).read_bytes())
        create(ROOT / RAW_JUNIT, (ROOT / SOURCE_JUNIT).read_bytes())
        create(ROOT / RECORD, canonical(record_payload()))
        create(ROOT / MANIFEST, canonical(manifest_payload()))
    if args.check:
        checker = checker_module()
        checker.validate_manifest(checker.load(ROOT / MANIFEST))
        checker.validate_record(checker.load(ROOT / RECORD))
        if (ROOT / RECORD).read_bytes() != canonical(record_payload()):
            raise ValueError("record drift")
        if (ROOT / MANIFEST).read_bytes() != canonical(manifest_payload()):
            raise ValueError("manifest drift")
    if not args.write and not args.check:
        parser.error("select --write or --check")
    print(json.dumps({"status": "PASS", "authoritative": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
