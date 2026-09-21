#!/usr/bin/env python3
# ruff: noqa: E501, TRY003
"""Build the create-only workflow-equivalent Stage 2 v6 intake package."""

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
HERE_REL = Path("stage1-successor-evidence/stage2-v6-intake-remediation-v3")
V5_ROOT = Path("stage1-successor-evidence/stage2-v5-intake-remediation-v2")
V5_RECORD_REL = V5_ROOT / "stage2-v5-intake-remediation-record.v2.json"
V5_VALIDATION_REL = V5_ROOT / "validation-receipt.v2.json"
V5_CHECKER_REL = V5_ROOT / "check_stage2_v5_intake_remediation_v2.py"
SOURCE_STATIC_ROOT = Path("stage1-successor-evidence/source-static-remediation-v1")
SOURCE_STATIC_RECORD_REL = (
    SOURCE_STATIC_ROOT / "stage1-source-static-remediation-record.v1.json"
)
RECORD_REL = HERE_REL / "stage2-v6-intake-remediation-record.v3.json"
PREDECESSOR_MANIFEST_REL = HERE_REL / "artifact-manifest.corrected.v3.json"
PREDECESSOR_MANIFEST_SHA256 = (
    "9824d90bccda1312ec2f7edf2c0f438114e605697886f31c31819c1ddd014be0"
)
MANIFEST_REL = HERE_REL / "artifact-manifest.corrected2.v3.json"
VALIDATION_REL = HERE_REL / "validation-receipt.corrected2.v3.json"
BUILDER_REL = HERE_REL / Path(__file__).name
CHECKER_REL = HERE_REL / "check_stage2_v6_intake_remediation_v3.py"
TEST_REL = HERE_REL / "test_stage2_v6_intake_remediation_v3.py"
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
REASONS = {
    "scripts/formal_release/source_closure.py": "COMPLETE_WORKFLOW_SELECTOR_CLOSURE_V3",
    "scripts/formal_release/stage2_candidate_intake.py": "WORKFLOW_EQUIVALENT_V3_BINDING",
    "tests/formal_release/test_source_closure.py": "BIND_WORKFLOW_SELECTOR_CLOSURE_TESTS",
    "tests/formal_release/test_stage2_candidate_intake.py": "BIND_WORKFLOW_EQUIVALENT_INTAKE_TESTS",
}


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


def _predecessor_sha_by_path() -> dict[str, str]:
    v5 = load_object(ROOT / V5_RECORD_REL)
    source_static = load_object(ROOT / SOURCE_STATIC_RECORD_REL)
    rows = {row["path"]: row["successor_sha256"] for row in v5["changed_paths"]}
    static_rows = source_static["changed_paths"]["post_residual"]
    rows.update(
        {
            row["path"]: row["current_sha256"]
            for row in static_rows
            if row["path"] in {
                "scripts/formal_release/source_closure.py",
                "tests/formal_release/test_source_closure.py",
            }
        }
    )
    expected = {path.as_posix() for path in CHANGED_PATHS}
    if set(rows) != expected:
        missing = sorted(expected - set(rows))
        raise ValueError(f"predecessor path binding incomplete: {missing}")
    return rows


def build_record() -> dict[str, Any]:
    previous = _predecessor_sha_by_path()
    changed = [
        {
            "path": path.as_posix(),
            "predecessor_sha256": previous[path.as_posix()],
            "successor_sha256": sha256(ROOT / path),
            "reason": REASONS[path.as_posix()],
        }
        for path in CHANGED_PATHS
    ]
    return {
        "schema_version": "mrw.stage1.stage2_v6_intake_remediation_record.v3",
        "status": "PASS_STAGE2_V6_WORKFLOW_SELECTOR_CLOSURE_NOT_AUTHORITY",
        "authoritative": False,
        "authority_ceiling": AUTHORITY_CEILING,
        "predecessor": {
            "v2_record": {
                "path": V5_RECORD_REL.as_posix(),
                "sha256": sha256(ROOT / V5_RECORD_REL),
                "checker": V5_CHECKER_REL.as_posix(),
            },
            "v2_validation": {
                "path": V5_VALIDATION_REL.as_posix(),
                "sha256": sha256(ROOT / V5_VALIDATION_REL),
            },
            "source_static_record": {
                "path": SOURCE_STATIC_RECORD_REL.as_posix(),
                "sha256": sha256(ROOT / SOURCE_STATIC_RECORD_REL),
                "use": "PREDECESSOR_BYTES_FOR_TWO_SOURCE_CLOSURE_PATHS_ONLY",
            },
            "relation": "ADDITIVE_WORKFLOW_EQUIVALENT_EXTENSION_NO_REWRITE",
        },
        "changed_paths": changed,
        "manifest_contract": {
            "legacy_schema": "mrw.stage2.exact-candidate-manifest.v2",
            "workflow_equivalent_schema": "mrw.stage2.exact-candidate-manifest.v3",
            "legacy_behavior_preserved": True,
            "legacy_default_schema_stays_v2": True,
            "workflow_equivalent_requires_explicit_v3_remediation_record": True,
            "historical_v2_and_v3_manifest_compatibility_preserved": True,
            "current_byte_registry_direct_binding": True,
            "candidate_specific_successor_resolutions": 6,
            "remediation_successor_chain_preserved": True,
            "contract14_history_allowlist": (
                "stage1-successor-evidence/contract14-local-execution-v1/history/"
            ),
        },
        "workflow_selector_closure": {
            "selector_roots": [
                "main/backend",
                "main/ops",
                "src/mrw_functorial_kit",
                "ops",
                "scripts",
            ],
            "included_paths": [
                "every regular .py file under a selector root",
                "main/backend/pytest.ini",
                "main/backend/requirements*.in",
                "main/backend/requirements*.txt",
            ],
            "path_contract": {
                "relative_posix_only": True,
                "nfc_normalized": True,
                "rejects_absolute_dot_dot_backslash_nul": True,
                "checkout_regular_files_only": True,
                "traverses_no_symlinks": True,
            },
            "excluded_paths": [
                "cache temporary runtime virtualenv node_modules components except successor_runtime/runtime",
                "credential secret directories and named credential or key files",
            ],
            "delta_contract": {
                "ordering": "path-major lexicographic operation,path rows",
                "checkout_missing_or_byte_mode_changed_base_regular_file": "UPSERT",
                "base_regular_file_missing_from_regular_checkout": "DELETE",
                "unchanged_base_bytes_are_read_from_the_base_tree": True,
                "base_symlinks_are_not_selector_members": True,
            },
            "manifest_contract": {
                "expected_delta_must_occur_exactly_once": True,
                "operation_must_match_expected_delta": True,
                "extra_safe_explicit_paths_are_allowed": True,
                "source_base_oid_when_present_must_match_base_index": True,
                "intake_then_validates_each_entry_against_projected_source": True,
            },
            "semantic": (
                "THE_MANIFEST_PROJECTS_EXACTLY_THE_COMPLETE_WORKFLOW_SELECTOR_DELTA;"
                "_NO_UNCHANGED_SELECTOR_FILE_IS_COPIED_AND_NO_CHANGED_OR_DELETED_"
                "SELECTOR_FILE_MAY_BE_OMITTED"
            ),
        },
        "current_bindings": {
            "old_record_constant": "DEFAULT_STAGE1_REMEDIATION_RECORD",
            "old_record_path": V5_RECORD_REL.as_posix(),
            "old_checker_constant": "DEFAULT_STAGE1_REMEDIATION_CHECKER",
            "old_checker_path": V5_CHECKER_REL.as_posix(),
            "new_record_constant": "WORKFLOW_EQUIVALENT_STAGE1_REMEDIATION_RECORD",
            "new_record_path": RECORD_REL.as_posix(),
            "new_checker_constant": "WORKFLOW_EQUIVALENT_STAGE1_REMEDIATION_CHECKER",
            "new_checker_path": CHECKER_REL.as_posix(),
        },
        "focused_verification": {
            "source_and_intake_tests": {
                "passed": 138,
                "failed": 0,
            },
            "ruff": "PASS",
            "compileall": "PASS",
            "package_tests": "RUN_AFTER_CREATE_ONLY_RECORD_MATERIALIZATION",
            "authority": "NO_AUTHORITY_CLAIM",
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
        for path in sorted(
            (BUILDER_REL, CHECKER_REL, TEST_REL, RECORD_REL),
            key=lambda item: item.as_posix(),
        )
    ]
    return {
        "schema_version": "mrw.stage1.stage2_v6_intake_remediation_manifest.v3",
        "status": "COMPLETE_NOT_AUTHORITY",
        "authoritative": False,
        "authority_ceiling": AUTHORITY_CEILING,
        "member_count": len(members),
        "members": members,
        "supersedes": {
            "path": PREDECESSOR_MANIFEST_REL.as_posix(),
            "sha256": PREDECESSOR_MANIFEST_SHA256,
            "reason": "DRIFTED_RECORD_ARGUMENT_WAS_NOT_CHECKED",
        },
    }


def load_checker():
    checker_path = ROOT / CHECKER_REL
    spec = importlib.util.spec_from_file_location(
        "stage2_v6_intake_remediation_checker_v3", checker_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"checker module spec missing: {checker_path}")
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
        outputs = (ROOT / MANIFEST_REL, ROOT / VALIDATION_REL)
        existing = [path for path in outputs if path.exists() or path.is_symlink()]
        if existing:
            raise FileExistsError(f"create-only outputs already exist: {existing}")
        if (ROOT / RECORD_REL).read_bytes() != canonical_bytes(build_record()):
            raise ValueError("record drift before corrected manifest write")
        if sha256(ROOT / PREDECESSOR_MANIFEST_REL) != PREDECESSOR_MANIFEST_SHA256:
            raise ValueError("predecessor corrected manifest drift")
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
    print(json.dumps({"status": "OK", "authoritative": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        KeyError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        raise SystemExit(1) from exc
