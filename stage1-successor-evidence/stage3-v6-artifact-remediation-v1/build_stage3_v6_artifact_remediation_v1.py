#!/usr/bin/env python3
# ruff: noqa: E501, TRY003
"""Build the create-only Stage 3 v6 artifact remediation package."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
HERE = Path("stage1-successor-evidence/stage3-v6-artifact-remediation-v1")
RECORD = HERE / "stage3-v6-artifact-remediation-record.v1.json"
MANIFEST = HERE / "artifact-manifest.v1.json"
VALIDATION = HERE / "validation-receipt.v1.json"
CORRECTION_RECORD = HERE / "stage3-v6-artifact-remediation-record.v1.correction1.json"
CORRECTION_MANIFEST = HERE / "artifact-manifest.v1.correction1.json"
CORRECTION_VALIDATION = HERE / "validation-receipt.v1.correction1.json"
PRIOR_ATTEMPT_RECORD = RECORD
PRIOR_ATTEMPT_RECORD_SHA256 = (
    "bda307646e629af1f0488184dfc3dac6eabfa3e04754e858fb4696c6e54907cc"
)
INTAKE_PATH = Path("scripts/formal_release/stage2_candidate_intake.py")
INTAKE_TEST_PATH = Path("tests/formal_release/test_stage2_candidate_intake.py")
SOURCE_CLOSURE_PATH = Path("scripts/formal_release/source_closure.py")
SOURCE_CLOSURE_TEST_PATH = Path("tests/formal_release/test_source_closure.py")
CORRECTION_FINAL_BINDING_PATHS = (
    INTAKE_PATH,
    INTAKE_TEST_PATH,
    SOURCE_CLOSURE_PATH,
    SOURCE_CLOSURE_TEST_PATH,
)
BUILDER = HERE / Path(__file__).name
CHECKER = HERE / "check_stage3_v6_artifact_remediation_v1.py"
PACKAGE_TEST = HERE / "test_stage3_v6_artifact_remediation_v1.py"
INPUT_OBSERVATION = HERE / "input-observation.v1.json"
CONTRACT = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-09-04-formal-production-release/"
    "15_production-deployment-stage3-v6-contract.v1.md"
)
HISTORICAL_V6_REMEDIATION_RECORD = Path(
    "stage1-successor-evidence/stage2-v6-intake-remediation-v5/"
    "stage2-v6-intake-remediation-record.v5.json"
)
V6_REMEDIATION_SHA256 = (
    "b25c4fbccef8358a62a8f8ca8a46c86c593be9a8f42e2ffe370607a7a8f93002"
)
CEILING = (
    "NO_DEPLOY_NO_LIVE_NO_PRODUCTION_WRITE_NO_EXTERNAL_DELIVERY_NO_CANARY_"
    "NO_CUTOVER_NO_AUTHORITY_TRANSFER_NO_LEGACY_RETIREMENT_NO_PUSH_"
    "NO_REMOTE_MUTATION_NO_REGISTRY_WRITE_NO_SIGNING_WRITE"
)
ABSENT_SHA256 = "0" * 64


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


def checker_module():
    spec = importlib.util.spec_from_file_location("stage3_v6_artifact_remediation_checker", ROOT / CHECKER)
    if spec is None or spec.loader is None:
        raise RuntimeError("checker module spec missing")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def safe_relative(path: Path) -> Path:
    relative = path.relative_to(ROOT) if path.is_absolute() else path
    if relative.as_posix() != str(relative) or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError(f"non-canonical repository path: {relative}")
    return relative


def unique_paths(values: Iterable[Path]) -> tuple[Path, ...]:
    unique = tuple(dict.fromkeys(safe_relative(path) for path in values))
    if len(unique) != len({path.as_posix() for path in unique}):
        raise ValueError("duplicate source path")
    return tuple(sorted(unique, key=lambda item: item.as_posix()))


def verify_receipts(
    receipt_paths: Sequence[Path],
    command_receipt_paths: Sequence[Path],
    final_receipt: Path,
    receipt_source_root: Path,
) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, Any]]:
    checker = checker_module()
    normalized = unique_paths(receipt_paths)
    final_relative = safe_relative(final_receipt)
    if final_relative.as_posix() not in {path.as_posix() for path in normalized}:
        raise ValueError("final receipt must also be supplied through --test-receipt")
    refs: list[dict[str, str]] = []
    aggregate = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for relative in normalized:
        path = ROOT / relative
        payload = load(path)
        parsed = checker.validate_receipt(
            payload,
            root=ROOT,
            source_root=receipt_source_root,
        )
        aggregate["tests"] += parsed["junit"]["tests"]
        aggregate["failures"] += parsed["junit"]["failures"]
        aggregate["errors"] += parsed["junit"]["errors"]
        aggregate["skipped"] += parsed["junit"]["skipped"]
        refs.append(
            {
                "path": relative.as_posix(),
                "sha256": sha(path),
                "role": "final" if relative == final_relative else "prior",
                "kind": "pytest",
            }
        )
    if aggregate["failures"] or aggregate["errors"] or aggregate["skipped"]:
        raise ValueError("fresh test receipt is not clean")
    command_refs: list[dict[str, str]] = []
    for relative in unique_paths(command_receipt_paths):
        path = ROOT / relative
        checker.validate_command_receipt(
            load(path),
            root=ROOT,
            source_root=receipt_source_root,
        )
        command_refs.append(
            {
                "path": relative.as_posix(),
                "sha256": sha(path),
                "kind": "frontend-tool",
            }
        )
    summary = {
        "receipt_count": len(refs),
        "final_receipt_count": 1,
        "command_receipt_count": len(command_refs),
        "all_exit_codes_zero": True,
        "junit_failures": aggregate["failures"],
        "junit_errors": aggregate["errors"],
        "junit_skipped": aggregate["skipped"],
    }
    return (
        sorted(refs, key=lambda item: item["path"]),
        sorted(command_refs, key=lambda item: item["path"]),
        summary,
    )


def artifact_rows(changed_paths: Sequence[Path]) -> tuple[list[dict[str, Any]], list[Path]]:
    checker = checker_module()
    observation = load(ROOT / INPUT_OBSERVATION)
    if observation.get("schema_version") != "mrw.stage3_v6_artifact_repair.input_observation.v1":
        raise ValueError("input observation schema drift")
    candidate_root = Path(observation["predecessor"]["root"])
    observed_hashes = {Path(row["path"]).as_posix(): row["v6_sha256"] for row in observation["paths"]}
    extensions = unique_paths(changed_paths)
    if not extensions:
        raise ValueError("at least one --changed-path is required")
    for relative in extensions:
        if relative.as_posix() in checker.OBSERVED_ARTIFACT_PATHS:
            raise ValueError(f"changed path is not an extension: {relative.as_posix()}")
    selected = {
        *checker.OBSERVED_ARTIFACT_PATHS,
        *checker.REQUIRED_ARTIFACT_PATHS,
        *(path.as_posix() for path in extensions),
    }
    rows: list[dict[str, Any]] = []
    for item in sorted(selected):
        relative = Path(item)
        path = ROOT / relative
        if not path.is_file():
            raise FileNotFoundError(path)
        candidate_path = candidate_root / relative
        v6_present = candidate_path.is_file() and not candidate_path.is_symlink()
        v6_hash = sha(candidate_path) if v6_present else observed_hashes.get(item, ABSENT_SHA256)
        current_hash = sha(path)
        rows.append(
            {
                "path": item,
                "v6_sha256": v6_hash,
                "v6_present": v6_present,
                "current_sha256": current_hash,
                "changed": v6_hash != current_hash,
            }
        )
    return rows, extensions


def record_payload(
    *,
    receipt_paths: Sequence[Path],
    command_receipt_paths: Sequence[Path],
    final_receipt: Path,
    receipt_source_root: Path,
    changed_paths: Sequence[Path],
    correction1: bool = False,
) -> dict[str, Any]:
    observation = load(ROOT / INPUT_OBSERVATION)
    correction_paths = (
        (*changed_paths, SOURCE_CLOSURE_PATH, SOURCE_CLOSURE_TEST_PATH, PRIOR_ATTEMPT_RECORD)
        if correction1
        else changed_paths
    )
    rows, extensions = artifact_rows(correction_paths)
    receipts, command_receipts, summary = verify_receipts(
        receipt_paths,
        command_receipt_paths,
        final_receipt,
        receipt_source_root,
    )
    payload = {
        "schema_version": "mrw.stage1.stage3_v6_artifact_remediation_record.v1",
        "status": "PASS_STAGE3_V6_ARTIFACT_REMEDIATION_NOT_AUTHORITY",
        "authoritative": False,
        "authority_ceiling": CEILING,
        "contract": {"path": CONTRACT.as_posix(), "sha256": sha(ROOT / CONTRACT)},
        "predecessor": {
            "candidate_root": observation["predecessor"]["root"],
            "commit": observation["predecessor"]["commit"],
            "tree": observation["predecessor"]["tree"],
            "evidence": observation["predecessor"]["evidence"],
            "input_observation": {
                "path": INPUT_OBSERVATION.as_posix(),
                "sha256": sha(ROOT / INPUT_OBSERVATION),
            },
            "receipt_source_root": receipt_source_root.as_posix(),
            "v6_intake_remediation_record": {
                "path": HISTORICAL_V6_REMEDIATION_RECORD.as_posix(),
                "sha256": V6_REMEDIATION_SHA256,
            },
        },
        "artifact_paths": rows,
        "additional_binding_paths": [path.as_posix() for path in extensions],
        "test_receipts": receipts,
        "command_receipts": command_receipts,
        "fresh_test_summary": summary,
        "current_bindings": {
            "record": (CORRECTION_RECORD if correction1 else RECORD).as_posix(),
            "builder": BUILDER.as_posix(),
            "checker": CHECKER.as_posix(),
            "test": PACKAGE_TEST.as_posix(),
        },
        "external_effects": "NONE_LOCAL_DETERMINISTIC_VALIDATION_ONLY",
        "production_release_authorized": False,
    }
    if correction1:
        checker = checker_module()
        payload["correction"] = {
            "attempt": 1,
            "reason": "INTAKE_C6_AND_WORKFLOW_SELECTOR_POLICY_BYTE_DRIFT",
            "predecessor_record": {
                "path": PRIOR_ATTEMPT_RECORD.as_posix(),
                "sha256": PRIOR_ATTEMPT_RECORD_SHA256,
            },
            "final_bindings": [
                {
                    "path": path.as_posix(),
                    "sha256": sha(ROOT / path),
                }
                for path in CORRECTION_FINAL_BINDING_PATHS
            ],
            "workflow_selector_policy": checker.workflow_selector_policy_binding(
                root=ROOT
            ),
        }
    return payload


def manifest_payload(
    record: dict[str, Any],
    *,
    record_path: Path = RECORD,
) -> dict[str, Any]:
    checker = checker_module()
    members = checker.manifest_members(record, root=ROOT, record_path=record_path)
    return {
        "schema_version": "mrw.stage1.stage3_v6_artifact_remediation_manifest.v1",
        "status": "COMPLETE_NOT_AUTHORITY",
        "authoritative": False,
        "authority_ceiling": CEILING,
        "member_count": len(members),
        "members": members,
    }


def validation_payload(
    record: dict[str, Any],
    manifest: dict[str, Any],
    *,
    record_path: Path = RECORD,
    manifest_path: Path = MANIFEST,
) -> dict[str, Any]:
    checker = checker_module()
    return checker.receipt_payload(
        record,
        manifest,
        record_path=record_path,
        manifest_path=manifest_path,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write-correction1", action="store_true")
    parser.add_argument("--check-correction1", action="store_true")
    parser.add_argument("--test-receipt", action="append", type=Path, default=[])
    parser.add_argument("--command-receipt", action="append", type=Path, default=[])
    parser.add_argument("--receipt-source-root", type=Path, default=ROOT.absolute())
    parser.add_argument("--final-test-receipt", type=Path)
    parser.add_argument(
        "--changed-path",
        action="append",
        type=Path,
        default=[],
        help="repository-relative source path outside the original observation boundary",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    if isinstance(argv, argparse.Namespace):
        args = argv
    else:
        args = parse_args(argv)
    correction = args.write_correction1 or args.check_correction1
    if not any((args.write, args.check, args.write_correction1, args.check_correction1)):
        raise ValueError("select --write, --check, --write-correction1, or --check-correction1")
    if correction and (args.write or args.check):
        raise ValueError("original and correction modes are mutually exclusive")
    record_path = CORRECTION_RECORD if correction else RECORD
    manifest_path = CORRECTION_MANIFEST if correction else MANIFEST
    validation_path = CORRECTION_VALIDATION if correction else VALIDATION
    if args.final_test_receipt is None:
        raise ValueError("--final-test-receipt is required")
    if not args.command_receipt:
        raise ValueError("at least one --command-receipt is required")
    record = record_payload(
        receipt_paths=args.test_receipt,
        command_receipt_paths=args.command_receipt,
        final_receipt=args.final_test_receipt,
        receipt_source_root=args.receipt_source_root.absolute(),
        changed_paths=args.changed_path,
        correction1=correction,
    )
    checker = checker_module()
    checker.validate_record(
        record,
        receipt_paths=tuple(unique_paths(args.test_receipt)),
        record_path=record_path,
    )
    if args.check or args.check_correction1:
        stored_record = load(ROOT / record_path)
        stored_manifest = load(ROOT / manifest_path)
        if stored_record != record:
            raise ValueError("record drift")
        expected_members = checker.manifest_members(record, root=ROOT, record_path=record_path)
        checker.validate_manifest(
            stored_manifest,
            expected_paths=tuple(Path(row["path"]) for row in expected_members),
        )
        validation = checker.receipt_payload(
            stored_record,
            stored_manifest,
            record_path=record_path,
            manifest_path=manifest_path,
        )
        if (ROOT / validation_path).read_bytes() != canonical(validation):
            raise ValueError("validation drift")
    if args.write or args.write_correction1:
        outputs = (ROOT / record_path, ROOT / manifest_path, ROOT / validation_path)
        if any(path.exists() or path.is_symlink() for path in outputs):
            raise FileExistsError("create-only output already exists")
        create(ROOT / record_path, canonical(record))
        manifest = manifest_payload(record, record_path=record_path)
        checker.validate_manifest(
            manifest,
            expected_paths=tuple(Path(row["path"]) for row in manifest["members"]),
        )
        create(ROOT / manifest_path, canonical(manifest))
        create(
            ROOT / validation_path,
            canonical(
                validation_payload(
                    record,
                    manifest,
                    record_path=record_path,
                    manifest_path=manifest_path,
                )
            ),
        )
    print(json.dumps({"status": "PASS", "authoritative": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        raise SystemExit(1) from exc
