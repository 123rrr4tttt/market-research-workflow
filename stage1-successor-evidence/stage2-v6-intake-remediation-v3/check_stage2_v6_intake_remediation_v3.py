#!/usr/bin/env python3
# ruff: noqa: E501, TRY003
"""Fail-closed checker for the Stage 2 v6 workflow-equivalent package."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
HERE_REL = Path("stage1-successor-evidence/stage2-v6-intake-remediation-v3")
RECORD_REL = HERE_REL / "stage2-v6-intake-remediation-record.v3.json"
PREDECESSOR_MANIFEST_REL = HERE_REL / "artifact-manifest.corrected.v3.json"
PREDECESSOR_MANIFEST_SHA256 = (
    "9824d90bccda1312ec2f7edf2c0f438114e605697886f31c31819c1ddd014be0"
)
MANIFEST_REL = HERE_REL / "artifact-manifest.corrected2.v3.json"
VALIDATION_REL = HERE_REL / "validation-receipt.corrected2.v3.json"
V5_RECORD_REL = Path(
    "stage1-successor-evidence/stage2-v5-intake-remediation-v2/"
    "stage2-v5-intake-remediation-record.v2.json"
)
V5_VALIDATION_REL = Path(
    "stage1-successor-evidence/stage2-v5-intake-remediation-v2/"
    "validation-receipt.v2.json"
)
V5_CHECKER_REL = Path(
    "stage1-successor-evidence/stage2-v5-intake-remediation-v2/"
    "check_stage2_v5_intake_remediation_v2.py"
)
SOURCE_STATIC_RECORD_REL = Path(
    "stage1-successor-evidence/source-static-remediation-v1/"
    "stage1-source-static-remediation-record.v1.json"
)
AUTHORITY_CEILING = (
    "NO_DEPLOY_NO_LIVE_NO_PRODUCTION_WRITE_NO_EXTERNAL_DELIVERY_NO_CANARY_"
    "NO_CUTOVER_NO_AUTHORITY_TRANSFER_NO_LEGACY_RETIREMENT_NO_PUSH_"
    "NO_REMOTE_MUTATION_NO_REGISTRY_WRITE_NO_SIGNING_WRITE"
)
OLD_RECORD_REL = Path(
    "stage1-successor-evidence/stage2-v5-intake-remediation-v2/"
    "stage2-v5-intake-remediation-record.v2.json"
)
OLD_CHECKER_REL = Path(
    "stage1-successor-evidence/stage2-v5-intake-remediation-v2/"
    "check_stage2_v5_intake_remediation_v2.py"
)
NEW_RECORD_REL = RECORD_REL
NEW_CHECKER_REL = HERE_REL / Path(__file__).name
EXPECTED_V5_RECORD_SHA256 = (
    "840dae5a8f24d70cb2b84ccc8f6e5a5b5a13556403004e8f21072ee41cf70e01"
)
EXPECTED_V5_VALIDATION_SHA256 = (
    "c859672c66c01747c3dfe228ec0da7bc88eda0bdaa4a795937e711a7c6d1d09f"
)
CHANGED_PATHS = (
    Path("scripts/formal_release/source_closure.py"),
    Path("scripts/formal_release/stage2_candidate_intake.py"),
    Path("tests/formal_release/test_source_closure.py"),
    Path("tests/formal_release/test_stage2_candidate_intake.py"),
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
    require(
        manifest.get("schema_version")
        == "mrw.stage1.stage2_v6_intake_remediation_manifest.v3",
        "MANIFEST_SCHEMA",
    )
    require(manifest.get("status") == "COMPLETE_NOT_AUTHORITY", "MANIFEST_STATUS")
    require(manifest.get("authoritative") is False, "MANIFEST_AUTHORITY")
    require(manifest.get("authority_ceiling") == AUTHORITY_CEILING, "MANIFEST_CEILING")
    require(manifest.get("supersedes") == {
        "path": PREDECESSOR_MANIFEST_REL.as_posix(),
        "sha256": PREDECESSOR_MANIFEST_SHA256,
        "reason": "DRIFTED_RECORD_ARGUMENT_WAS_NOT_CHECKED",
    }, "MANIFEST_SUPERSEDES")
    require(sha256(ROOT / PREDECESSOR_MANIFEST_REL) == PREDECESSOR_MANIFEST_SHA256, "PREDECESSOR_MANIFEST_HASH")
    members = manifest.get("members")
    require(
        isinstance(members, list)
        and manifest.get("member_count") == len(members) == 4,
        "MANIFEST_COUNT",
    )
    paths = [row.get("path") for row in members]
    require(paths == sorted(paths) and len(paths) == len(set(paths)), "MANIFEST_PATHS")
    expected = {
        (HERE_REL / Path(__file__).name).as_posix(),
        (HERE_REL / "build_stage2_v6_intake_remediation_v3.py").as_posix(),
        (HERE_REL / "test_stage2_v6_intake_remediation_v3.py").as_posix(),
        RECORD_REL.as_posix(),
    }
    require(set(paths) == expected, "MANIFEST_MEMBERS")
    for row in members:
        path = ROOT / row["path"]
        require(path.is_file(), f"MANIFEST_MISSING:{row['path']}")
        require(path.stat().st_size == row["bytes"], f"MANIFEST_SIZE:{row['path']}")
        require(sha256(path) == row["sha256"], f"MANIFEST_HASH:{row['path']}")


def _validate_v2_predecessor(record: dict[str, Any]) -> None:
    v2_record = load_object(ROOT / V5_RECORD_REL)
    require(sha256(ROOT / V5_RECORD_REL) == EXPECTED_V5_RECORD_SHA256, "V2_RECORD_FROZEN_HASH")
    require(sha256(ROOT / V5_VALIDATION_REL) == EXPECTED_V5_VALIDATION_SHA256, "V2_VALIDATION_FROZEN_HASH")
    require(sha256(ROOT / V5_RECORD_REL) == record["predecessor"]["v2_record"]["sha256"], "V2_RECORD_HASH")
    require(sha256(ROOT / V5_VALIDATION_REL) == record["predecessor"]["v2_validation"]["sha256"], "V2_VALIDATION_HASH")
    require(v2_record.get("schema_version") == "mrw.stage1.stage2_v5_intake_remediation_record.v2", "V2_SCHEMA")
    require(v2_record.get("authoritative") is False, "V2_AUTHORITY")
    require(v2_record.get("production_release_authorized") is False, "V2_RELEASE_AUTHORITY")
    require(v2_record.get("authority_ceiling") == AUTHORITY_CEILING, "V2_CEILING")
    require(v2_record["changed_paths"][0]["path"] == "scripts/formal_release/stage2_candidate_intake.py", "V2_PATH_BINDING")


def _validate_source_static_predecessor(record: dict[str, Any]) -> None:
    source_static = load_object(ROOT / SOURCE_STATIC_RECORD_REL)
    binding = record["predecessor"]["source_static_record"]
    require(sha256(ROOT / SOURCE_STATIC_RECORD_REL) == binding["sha256"], "SOURCE_STATIC_HASH")
    require(source_static.get("authoritative") is False, "SOURCE_STATIC_AUTHORITY")
    require(source_static.get("authority_ceiling") == AUTHORITY_CEILING, "SOURCE_STATIC_CEILING")
    rows = {
        row["path"]: row["current_sha256"]
        for row in source_static["changed_paths"]["post_residual"]
    }
    selected = {
        "scripts/formal_release/source_closure.py",
        "tests/formal_release/test_source_closure.py",
    }
    require(selected <= set(rows), "SOURCE_STATIC_PATH_SET")
    for row in record["changed_paths"]:
        if row["path"] in selected:
            require(row["predecessor_sha256"] == rows[row["path"]], f"SOURCE_STATIC_PREDECESSOR:{row['path']}")


def _expected_workflow_contract() -> dict[str, Any]:
    return {
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
    }


def validate_record(record: dict[str, Any]) -> None:
    require(
        record.get("schema_version")
        == "mrw.stage1.stage2_v6_intake_remediation_record.v3",
        "RECORD_SCHEMA",
    )
    require(
        record.get("status")
        == "PASS_STAGE2_V6_WORKFLOW_SELECTOR_CLOSURE_NOT_AUTHORITY",
        "RECORD_STATUS",
    )
    require(
        record.get("authoritative") is False
        and record.get("production_release_authorized") is False,
        "RECORD_AUTHORITY",
    )
    require(record.get("authority_ceiling") == AUTHORITY_CEILING, "RECORD_CEILING")
    _validate_v2_predecessor(record)
    _validate_source_static_predecessor(record)
    require(record["predecessor"]["relation"] == "ADDITIVE_WORKFLOW_EQUIVALENT_EXTENSION_NO_REWRITE", "PREDECESSOR_RELATION")
    rows = record.get("changed_paths")
    require(isinstance(rows, list) and [row.get("path") for row in rows] == [path.as_posix() for path in CHANGED_PATHS], "CHANGED_PATHS")
    for row in rows:
        path = ROOT / row["path"]
        require(path.is_file(), f"CURRENT_MISSING:{row['path']}")
        require(sha256(path) == row["successor_sha256"], f"CURRENT_HASH:{row['path']}")
        require(isinstance(row.get("predecessor_sha256"), str) and len(row["predecessor_sha256"]) == 64, f"PREDECESSOR_HASH_FORMAT:{row['path']}")
    require(record.get("manifest_contract") == {
        "legacy_schema": "mrw.stage2.exact-candidate-manifest.v2",
        "workflow_equivalent_schema": "mrw.stage2.exact-candidate-manifest.v3",
        "legacy_behavior_preserved": True,
        "legacy_default_schema_stays_v2": True,
        "workflow_equivalent_requires_explicit_v3_remediation_record": True,
        "historical_v2_and_v3_manifest_compatibility_preserved": True,
        "current_byte_registry_direct_binding": True,
        "candidate_specific_successor_resolutions": 6,
        "remediation_successor_chain_preserved": True,
        "contract14_history_allowlist": "stage1-successor-evidence/contract14-local-execution-v1/history/",
    }, "MANIFEST_CONTRACT")
    require(record.get("workflow_selector_closure") == _expected_workflow_contract(), "WORKFLOW_SELECTOR_CONTRACT")
    require(record.get("current_bindings") == {
        "old_record_constant": "DEFAULT_STAGE1_REMEDIATION_RECORD",
        "old_record_path": OLD_RECORD_REL.as_posix(),
        "old_checker_constant": "DEFAULT_STAGE1_REMEDIATION_CHECKER",
        "old_checker_path": OLD_CHECKER_REL.as_posix(),
        "new_record_constant": "WORKFLOW_EQUIVALENT_STAGE1_REMEDIATION_RECORD",
        "new_record_path": NEW_RECORD_REL.as_posix(),
        "new_checker_constant": "WORKFLOW_EQUIVALENT_STAGE1_REMEDIATION_CHECKER",
        "new_checker_path": NEW_CHECKER_REL.as_posix(),
    }, "CURRENT_BINDINGS")
    require(record.get("focused_verification") == {
        "source_and_intake_tests": {"passed": 138, "failed": 0},
        "ruff": "PASS",
        "compileall": "PASS",
        "package_tests": "RUN_AFTER_CREATE_ONLY_RECORD_MATERIALIZATION",
        "authority": "NO_AUTHORITY_CLAIM",
    }, "FOCUSED_VERIFICATION")
    require(record.get("external_effects") == "NONE_LOCAL_DETERMINISTIC_VALIDATION_ONLY", "EXTERNAL_EFFECTS")

    sys.dont_write_bytecode = True
    repo = str(ROOT)
    if repo not in sys.path:
        sys.path.insert(0, repo)
    from scripts.formal_release import source_closure as source_closure_module
    from scripts.formal_release import stage2_candidate_intake as intake

    require(list(source_closure_module.WORKFLOW_SELECTOR_ROOTS) == _expected_workflow_contract()["selector_roots"], "SOURCE_SELECTOR_ROOTS")
    exported = set(source_closure_module.__all__)
    require({"compute_workflow_selector_delta", "check_workflow_selector_manifest_closure"} <= exported, "SOURCE_CLOSURE_EXPORTS")
    require(intake.SCHEMA_VERSION_V2 == "mrw.stage2.exact-candidate-manifest.v2", "INTAKE_LEGACY_SCHEMA")
    require(intake.SCHEMA_VERSION_V3 == "mrw.stage2.exact-candidate-manifest.v3", "INTAKE_WORKFLOW_SCHEMA")
    require(intake.SCHEMA_VERSION == intake.SCHEMA_VERSION_V2, "INTAKE_DEFAULT_LEGACY_SCHEMA")
    require(intake.DEFAULT_STAGE1_REMEDIATION_RECORD == OLD_RECORD_REL, "OLD_RECORD_CONSTANT")
    require(intake.DEFAULT_STAGE1_REMEDIATION_CHECKER == OLD_CHECKER_REL, "OLD_CHECKER_CONSTANT")
    require(intake.WORKFLOW_EQUIVALENT_STAGE1_REMEDIATION_RECORD == NEW_RECORD_REL, "NEW_RECORD_CONSTANT")
    require(intake.WORKFLOW_EQUIVALENT_STAGE1_REMEDIATION_CHECKER == NEW_CHECKER_REL, "NEW_CHECKER_CONSTANT")
    allowed = "stage1-successor-evidence/contract14-local-execution-v1/history/history-verification-receipt.v1.json"
    require(intake.safe_relative(allowed).as_posix() == allowed, "HISTORY_ALLOWLIST_POSITIVE")


def validation_receipt() -> dict[str, Any]:
    return {
        "schema_version": "mrw.stage1.stage2_v6_intake_remediation_validation.v3",
        "status": "PASS",
        "authoritative": False,
        "record": {"path": RECORD_REL.as_posix(), "sha256": sha256(ROOT / RECORD_REL)},
        "artifact_manifest": {"path": MANIFEST_REL.as_posix(), "sha256": sha256(ROOT / MANIFEST_REL)},
        "checks": {
            "current_four_path_hashes": True,
            "historical_v2_and_v3_manifest_compatibility": True,
            "source_static_predecessor_bytes_for_two_closure_paths": True,
            "v2_predecessor_and_validation_immutable": True,
            "v2_predecessor_hashes_match_v5_manifest": True,
            "workflow_selector_closure_semantics_exact": True,
            "workflow_equivalent_constants_bound": True,
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
