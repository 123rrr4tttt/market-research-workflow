#!/usr/bin/env python3
# ruff: noqa: TRY003
"""Create an additive current-byte binding over the historical Stage1 record."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Annotated, Any

from scripts.formal_release import generate_stage1_production_contract_record as stage1


OUTPUT_REL = Path(
    "stage1-successor-evidence/stage1-production-contract-binding-successor-v1-r12/"
    "stage1-production-contract-binding-successor.v1.json"
)
ARTIFACT_MANIFEST_REL = OUTPUT_REL.parent / "artifact-manifest.v1.json"
SCHEMA = "mrw.stage1.production-contract-binding-successor.v1"
STATUS = "CURRENT_STAGE1_PRODUCTION_CONTRACT_BYTES_BOUND_NOT_AUTHORITY"
CHECKER = "stage1-production-contract-binding-successor"
OBSERVED_AT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
HISTORICAL_RECORD_SHA256 = (
    "3f5c745ce8253522fa7e3728ba112ed41c80f3b6aa7409ddf028621c6ae07f31"
)
HISTORICAL_RECORD_BYTES = 35_946
HISTORICAL_NON_RECEIPT_COUNT = 149
HISTORICAL_RECEIPT_COUNT = 11
HISTORICAL_TOTAL_BINDING_COUNT = 160
EXECUTION_CONTRACT_RELS = (
    stage1.PLAN_REL,
    stage1.FORMAL_RELEASE_DIR
    / "10_stage1-stage2-source-and-static-closure-return-contract.v1.md",
    stage1.FORMAL_RELEASE_DIR / "16_stage-convergence-execution-amendment.v1.md",
)
IMPLEMENTATION_RELS = (
    Path("scripts/formal_release/generate_stage1_production_contract_record.py"),
    Path("scripts/formal_release/check_stage1_production_contract_record.py"),
    Path("scripts/formal_release/generate_stage1_current_binding_successor.py"),
    Path("scripts/formal_release/check_stage1_current_binding_successor.py"),
    Path("scripts/formal_release/stage2_candidate_intake.py"),
    Path("scripts/formal_release/source_closure.py"),
    Path("tests/formal_release/test_generate_stage1_production_contract_record.py"),
    Path("tests/formal_release/test_stage1_current_binding_successor.py"),
    Path("tests/formal_release/test_stage2_candidate_intake.py"),
    Path("tests/formal_release/test_source_closure.py"),
)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_digest(value: Any) -> str:
    return sha256_bytes(
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        )
    )


def _load_historical_record(root: Path) -> tuple[dict[str, Any], bytes]:
    raw = stage1._read(root, stage1.OUTPUT_REL)
    try:
        historical = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise stage1.Stage1RecordError("historical Stage1 record is invalid JSON") from exc
    if not isinstance(historical, dict):
        raise stage1.Stage1RecordError("historical Stage1 record JSON root must be an object")
    if (
        len(raw) != HISTORICAL_RECORD_BYTES
        or sha256_bytes(raw) != HISTORICAL_RECORD_SHA256
        or
        historical.get("schema") != stage1.SCHEMA
        or historical.get("schema_version") != stage1.SCHEMA_VERSION
        or historical.get("record_id") != stage1.RECORD_ID
        or historical.get("status") != stage1.STATUS
        or historical.get("authoritative") is not False
    ):
        raise stage1.Stage1RecordError("historical Stage1 record identity or authority drift")
    authority = historical.get("authority")
    if not isinstance(authority, dict) or set(authority) != set(stage1.AUTHORITY_KEYS):
        raise stage1.Stage1RecordError("historical Stage1 authority key set drift")
    if any(authority.get(key) is not False for key in stage1.AUTHORITY_KEYS):
        raise stage1.Stage1RecordError("historical Stage1 authority ceiling expanded")
    return historical, raw


def _historical_receipts(root: Path, historical: dict[str, Any]) -> list[dict[str, str]]:
    commands = historical.get("commands")
    if not isinstance(commands, dict) or len(commands) != HISTORICAL_RECEIPT_COUNT:
        raise stage1.Stage1RecordError("historical Stage1 receipt count must be exactly 11")
    receipts: list[dict[str, str]] = []
    for command_id, command in sorted(commands.items()):
        if not isinstance(command_id, str) or not isinstance(command, dict):
            raise stage1.Stage1RecordError("historical Stage1 command shape drift")
        receipt = command.get("receipt")
        if not isinstance(receipt, dict) or set(receipt) != {"path", "sha256"}:
            raise stage1.Stage1RecordError(
                f"historical Stage1 receipt binding drift: {command_id}"
            )
        path = receipt.get("path")
        sha256 = receipt.get("sha256")
        if not isinstance(path, str) or not isinstance(sha256, str):
            raise stage1.Stage1RecordError(
                f"historical Stage1 receipt identity drift: {command_id}"
            )
        raw = stage1._read(root, path)
        if sha256_bytes(raw) != sha256:
            raise stage1.Stage1RecordError(
                f"historical Stage1 receipt byte drift: {command_id}"
            )
        receipts.append(
            {
                "command_id": command_id,
                "path": path,
                "sha256": sha256,
                "role": "HISTORICAL_ONLY_NOT_FRESH",
            }
        )
    return receipts


def _current_file_count(required_files: dict[str, list[dict[str, str]]]) -> int:
    return sum(len(rows) for rows in required_files.values())


def _binding_paths(required_files: dict[str, list[dict[str, str]]]) -> set[str]:
    paths: list[str] = []
    for group in ("source", "configuration", "workflow", "migration"):
        rows = required_files.get(group)
        if not isinstance(rows, list):
            raise stage1.Stage1RecordError(f"required-file group is invalid: {group}")
        for row in rows:
            if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
                raise stage1.Stage1RecordError("required-file binding shape drift")
            path = row.get("path")
            if not isinstance(path, str) or not path:
                raise stage1.Stage1RecordError("required-file binding path drift")
            paths.append(path)
    if len(paths) != len(set(paths)):
        raise stage1.Stage1RecordError("required-file paths are duplicated")
    return set(paths)


def _historical_binding_coverage(
    historical: dict[str, Any],
    current_required_files: dict[str, list[dict[str, str]]],
) -> dict[str, Any]:
    historical_required = historical.get("bindings", {}).get("required_files")
    if not isinstance(historical_required, dict):
        raise stage1.Stage1RecordError("historical Stage1 required-file inventory drift")
    historical_paths = _binding_paths(historical_required)
    current_paths = _binding_paths(current_required_files)
    removed = sorted(historical_paths - current_paths)
    additive = sorted(current_paths - historical_paths)
    non_receipt_count = len(historical_paths) + 3
    total_count = non_receipt_count + HISTORICAL_RECEIPT_COUNT
    if non_receipt_count != HISTORICAL_NON_RECEIPT_COUNT or total_count != HISTORICAL_TOTAL_BINDING_COUNT:
        raise stage1.Stage1RecordError("historical Stage1 binding count drift")
    if removed:
        raise stage1.Stage1RecordError(
            f"historical Stage1 required-file path removed: {removed}"
        )
    return {
        "historical_non_receipt_binding_count": non_receipt_count,
        "historical_receipt_binding_count": HISTORICAL_RECEIPT_COUNT,
        "historical_total_binding_count": total_count,
        "removed_paths": removed,
        "removed_count": len(removed),
        "additive_current_paths": additive,
        "additive_current_count": len(additive),
    }


def _current_bindings(
    root: Path,
    required_files: dict[str, list[dict[str, str]]],
    historical: dict[str, Any],
) -> list[dict[str, Any]]:
    roles: dict[str, set[str]] = {}
    digests: dict[str, str] = {}

    def add(path: str, digest: str, role: str) -> None:
        previous = digests.setdefault(path, digest)
        if previous != digest:
            raise stage1.Stage1RecordError(f"current binding digest conflict: {path}")
        roles.setdefault(path, set()).add(role)

    for group in ("source", "configuration", "workflow", "migration"):
        for binding in required_files[group]:
            add(binding["path"], binding["sha256"], f"REQUIRED_FILE_{group.upper()}")
    for relative, role in (
        (stage1.PLAN_REL, "STAGE_PLAN"),
        (stage1.PLAN_FREEZE_REL, "STAGE_PLAN_FREEZE"),
        (stage1.STAGE0_COMPLETION_REL, "STAGE0_COMPLETION"),
    ):
        binding = stage1._ref(root, relative)
        add(binding["path"], binding["sha256"], role)
    for relative in EXECUTION_CONTRACT_RELS:
        binding = stage1._ref(root, relative)
        add(binding["path"], binding["sha256"], "EXECUTION_CONTRACT")

    predecessor_by_path: dict[str, tuple[str, str]] = {}
    historical_bindings = historical["bindings"]
    for key in ("stage_plan", "stage_plan_freeze", "stage0_completion"):
        binding = historical_bindings[key]
        predecessor_by_path[binding["path"]] = (
            binding["sha256"],
            f"bindings.{key}",
        )
    for group in ("source", "configuration", "workflow", "migration"):
        for index, binding in enumerate(historical_bindings["required_files"][group]):
            predecessor_by_path[binding["path"]] = (
                binding["sha256"],
                f"bindings.required_files.{group}[{index}]",
            )

    def row(path: str) -> dict[str, Any]:
        predecessor = predecessor_by_path.get(path)
        predecessor_sha256 = predecessor[0] if predecessor is not None else None
        relation = (
            "ADDITIVE_CURRENT_REQUIREMENT"
            if predecessor is None
            else (
                "IDENTITY"
                if predecessor_sha256 == digests[path]
                else "CURRENT_BYTE_SUCCESSOR"
            )
        )
        return {
            "path": path,
            "successor_sha256": digests[path],
            "predecessor_sha256": predecessor_sha256,
            "historical_pointer": predecessor[1] if predecessor is not None else None,
            "role": "+".join(sorted(roles[path])),
            "relation": relation,
        }
    return [
        row(path)
        for path in sorted(digests)
    ]


def build_successor_record(root: Path, observed_at: str) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=evidence "
    "fact_source=historical_stage1_record+current_required_files "
    "witness=test:test_build_validates_all_historical_and_current_bindings",
]:
    root = root.resolve()
    if OBSERVED_AT.fullmatch(observed_at) is None:
        raise stage1.Stage1RecordError("--observed-at must be an explicit UTC second ending in Z")
    historical, historical_raw = _load_historical_record(root)
    receipts = _historical_receipts(root, historical)
    required_files = stage1._manifest(root)
    if required_files != stage1._manifest(root):
        raise stage1.Stage1RecordError("current Stage1 inventory changed during construction")
    coverage = _historical_binding_coverage(historical, required_files)
    current_bindings = _current_bindings(root, required_files, historical)
    projected_stage1 = json.loads(json.dumps(historical))
    projected_stage1["bindings"]["required_files"] = required_files
    stage1.validate_stage1_record(root, projected_stage1)
    record: dict[str, Any] = {
        "schema": SCHEMA,
        "schema_version": SCHEMA,
        "record_id": "stage1-production-contract-binding-successor-v1",
        "stage": "STAGE_1",
        "status": STATUS,
        "authoritative": False,
        "derived_as": "evidence",
        "authority": {key: False for key in stage1.AUTHORITY_KEYS},
        "observed_at": observed_at,
        "predecessor": {
            "path": stage1.OUTPUT_REL.as_posix(),
            "sha256": sha256_bytes(historical_raw),
            "schema_version": stage1.SCHEMA_VERSION,
            "status": stage1.STATUS,
            "role": "HISTORICAL_PREDECESSOR_NOT_CURRENT_BYTES",
        },
        "historical_receipts": receipts,
        "historical_binding_coverage": coverage,
        "execution_contracts": [stage1._ref(root, path) for path in EXECUTION_CONTRACT_RELS],
        "current_bindings": current_bindings,
        "current_required_files": required_files,
        "current_required_files_summary": {
            "current_binding_count": len(current_bindings),
            "file_count": _current_file_count(required_files),
            "content_digest": canonical_digest(required_files),
            "mismatch_count_at_generation": 0,
        },
        "qualification": {
            "historical_commands_reexecuted": False,
            "historical_receipts_are_fresh_evidence": False,
            "current_stage1_required_file_bytes_bound": True,
            "fresh_stage1_behavioral_gates_bound": False,
            "candidate_or_release_authority": False,
        },
    }
    validate_successor_record(root, record)
    return record


def validate_successor_record(root: Path, record: dict[str, Any]) -> dict[str, int]:
    root = root.resolve()
    expected_fields = {
        "schema",
        "schema_version",
        "record_id",
        "stage",
        "status",
        "authoritative",
        "derived_as",
        "authority",
        "observed_at",
        "predecessor",
        "historical_receipts",
        "historical_binding_coverage",
        "execution_contracts",
        "current_bindings",
        "current_required_files",
        "current_required_files_summary",
        "qualification",
    }
    if not isinstance(record, dict) or set(record) != expected_fields:
        raise stage1.Stage1RecordError("unexpected current Stage1 binding root shape")
    if (
        record.get("schema") != SCHEMA
        or record.get("schema_version") != SCHEMA
        or record.get("record_id") != "stage1-production-contract-binding-successor-v1"
        or record.get("stage") != "STAGE_1"
        or record.get("status") != STATUS
        or record.get("authoritative") is not False
        or record.get("derived_as") != "evidence"
        or not isinstance(record.get("observed_at"), str)
        or OBSERVED_AT.fullmatch(record["observed_at"]) is None
    ):
        raise stage1.Stage1RecordError("current Stage1 binding identity or status drift")
    authority = record.get("authority")
    if not isinstance(authority, dict) or set(authority) != set(stage1.AUTHORITY_KEYS):
        raise stage1.Stage1RecordError("current Stage1 binding authority key set drift")
    if any(authority.get(key) is not False for key in stage1.AUTHORITY_KEYS):
        raise stage1.Stage1RecordError("current Stage1 binding authority ceiling expanded")

    historical, historical_raw = _load_historical_record(root)
    expected_predecessor = {
        "path": stage1.OUTPUT_REL.as_posix(),
        "sha256": sha256_bytes(historical_raw),
        "schema_version": stage1.SCHEMA_VERSION,
        "status": stage1.STATUS,
        "role": "HISTORICAL_PREDECESSOR_NOT_CURRENT_BYTES",
    }
    if record.get("predecessor") != expected_predecessor:
        raise stage1.Stage1RecordError("historical Stage1 predecessor binding drift")
    expected_receipts = _historical_receipts(root, historical)
    if record.get("historical_receipts") != expected_receipts:
        raise stage1.Stage1RecordError("historical-only Stage1 receipt binding drift")

    expected_required_files = stage1._manifest(root)
    if expected_required_files != stage1._manifest(root):
        raise stage1.Stage1RecordError("current Stage1 inventory changed during validation")
    if record.get("current_required_files") != expected_required_files:
        raise stage1.Stage1RecordError("current Stage1 required-file mismatch count is nonzero")
    expected_coverage = _historical_binding_coverage(historical, expected_required_files)
    if record.get("historical_binding_coverage") != expected_coverage:
        raise stage1.Stage1RecordError("historical Stage1 binding coverage drift")
    expected_execution_contracts = [stage1._ref(root, path) for path in EXECUTION_CONTRACT_RELS]
    if record.get("execution_contracts") != expected_execution_contracts:
        raise stage1.Stage1RecordError("Stage1 execution contract binding drift")
    expected_current_bindings = _current_bindings(
        root,
        expected_required_files,
        historical,
    )
    if record.get("current_bindings") != expected_current_bindings:
        raise stage1.Stage1RecordError("Stage1 current binding closure drift")
    file_count = _current_file_count(expected_required_files)
    expected_summary = {
        "current_binding_count": len(expected_current_bindings),
        "file_count": file_count,
        "content_digest": canonical_digest(expected_required_files),
        "mismatch_count_at_generation": 0,
    }
    if record.get("current_required_files_summary") != expected_summary:
        raise stage1.Stage1RecordError("current Stage1 required-file summary drift")
    projected_stage1 = json.loads(json.dumps(historical))
    projected_stage1["bindings"]["required_files"] = expected_required_files
    stage1.validate_stage1_record(root, projected_stage1)
    expected_qualification = {
        "historical_commands_reexecuted": False,
        "historical_receipts_are_fresh_evidence": False,
        "current_stage1_required_file_bytes_bound": True,
        "fresh_stage1_behavioral_gates_bound": False,
        "candidate_or_release_authority": False,
    }
    if record.get("qualification") != expected_qualification:
        raise stage1.Stage1RecordError("current Stage1 binding qualification drift")
    return {
        "current_mismatch_count": 0,
        "file_count": file_count,
        "historical_receipt_count": len(expected_receipts),
        "projected_candidate_mismatch_count": 0,
        "removed_count": expected_coverage["removed_count"],
    }


def _serialized_record(record: dict[str, Any]) -> bytes:
    return (json.dumps(record, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def build_artifact_manifest(root: Path, record: dict[str, Any]) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=evidence "
    "fact_source=successor_record+implementation_files "
    "witness=test:test_successor_authority_and_create_only_are_fail_closed",
]:
    validate_successor_record(root, record)
    manifest = {
        "schema": "mrw.stage1.production-contract-binding-successor.artifact-manifest.v1",
        "status": "COMPLETE_NOT_AUTHORITY",
        "authoritative": False,
        "record": {
            "path": OUTPUT_REL.as_posix(),
            "sha256": sha256_bytes(_serialized_record(record)),
        },
        "implementation": [stage1._ref(root, path) for path in IMPLEMENTATION_RELS],
    }
    validate_artifact_manifest(root, record, manifest)
    return manifest


def validate_artifact_manifest(
    root: Path,
    record: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    expected = {
        "schema": "mrw.stage1.production-contract-binding-successor.artifact-manifest.v1",
        "status": "COMPLETE_NOT_AUTHORITY",
        "authoritative": False,
        "record": {
            "path": OUTPUT_REL.as_posix(),
            "sha256": sha256_bytes(_serialized_record(record)),
        },
        "implementation": [stage1._ref(root, path) for path in IMPLEMENTATION_RELS],
    }
    if manifest != expected:
        raise stage1.Stage1RecordError("Stage1 successor artifact manifest drift")


def validate_bundle(root: Path, record: dict[str, Any]) -> dict[str, int]:
    summary = validate_successor_record(root, record)
    if stage1._read(root, OUTPUT_REL) != _serialized_record(record):
        raise stage1.Stage1RecordError("Stage1 successor record bytes differ from artifact binding")
    raw = stage1._read(root, ARTIFACT_MANIFEST_REL)
    try:
        artifact_manifest = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise stage1.Stage1RecordError("Stage1 successor artifact manifest is invalid JSON") from exc
    if not isinstance(artifact_manifest, dict):
        raise stage1.Stage1RecordError("Stage1 successor artifact manifest root must be an object")
    validate_artifact_manifest(root, record, artifact_manifest)
    return summary


def write_successor_create_only(root: Path, record: dict[str, Any]) -> Path:
    root = root.resolve()
    manifest = build_artifact_manifest(root, record)
    for relative in (OUTPUT_REL, ARTIFACT_MANIFEST_REL):
        if (root / relative).exists():
            raise stage1.Stage1RecordError(
                f"create-only target already exists: {relative.as_posix()}"
            )
    destination = stage1.write_create_only(root, record, root / OUTPUT_REL)
    stage1.write_create_only(root, manifest, root / ARTIFACT_MANIFEST_REL)
    validate_bundle(root, record)
    return destination


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=stage1.REPOSITORY_ROOT)
    parser.add_argument("--observed-at", required=True)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.repo_root.resolve()
    try:
        record = build_successor_record(root, args.observed_at)
        if args.write:
            destination = write_successor_create_only(root, record)
            result = {
                "authoritative": False,
                "current_mismatch_count": 0,
                "file_count": record["current_required_files_summary"]["file_count"],
                "output": destination.relative_to(root).as_posix(),
                "projected_candidate_mismatch_count": 0,
                "removed_count": 0,
                "status": STATUS,
            }
            print(json.dumps(result, sort_keys=True))
        else:
            print(json.dumps(record, indent=2, sort_keys=True))
    except (OSError, stage1.Stage1RecordError) as exc:
        print(
            json.dumps(
                {
                    "authoritative": False,
                    "checker": CHECKER,
                    "current_mismatch_count": 1,
                    "error": str(exc),
                    "projected_candidate_mismatch_count": 1,
                    "status": "FAIL",
                },
                sort_keys=True,
            )
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
