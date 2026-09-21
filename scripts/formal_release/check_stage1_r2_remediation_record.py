#!/usr/bin/env python3
# ruff: noqa: E501, TRY003, TRY301
"""Validate the additive Stage 1 R2 remediation record against repository bytes."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.formal_release.generate_stage1_r2_remediation_record import (
    AUTHORITY_CEILING,
    COMMAND_IDS,
    EXPECTED_HISTORICAL,
    EXPECTED_R2,
    FAILURE_ID,
    HISTORICAL_RECORD,
    HISTORICAL_REVIEW,
    RECORD_ID,
    REPO_ROOT,
    R2_CHECKER,
    R2_TEST,
    SCHEMA_VERSION,
    SELF_CHECKER,
    STATUS,
    BRANCH_PROTECTION,
    WORKFLOW,
    Stage1R2RemediationError,
    binding,
)


REQUIRED_KEYS = {
    "schema_version", "record_id", "status", "authoritative", "failure_id",
    "historical_stage1_record_ref_and_sha256", "historical_stage1_review_ref_and_sha256",
    "required_file_refs_and_sha256", "workflow_refs_and_sha256",
    "focused_commands_and_exact_results", "test_receipts", "warning_skip_deselect_inventory",
    "independent_review_or_checker", "external_effects", "cleanup", "authority_ceiling", "observed_at",
}


def _expect_binding(root: Path, value: Any, relative: Path) -> None:
    if value != binding(root, relative):
        raise Stage1R2RemediationError(f"binding drift: {relative.as_posix()}")


def validate_record(root: Path, record: dict[str, Any]) -> None:
    if set(record) != REQUIRED_KEYS:
        raise Stage1R2RemediationError("record key set drift")
    identity = (record["schema_version"], record["record_id"], record["status"], record["authoritative"], record["failure_id"])
    if identity != (SCHEMA_VERSION, RECORD_ID, STATUS, False, FAILURE_ID):
        raise Stage1R2RemediationError("record identity or status drift")
    _expect_binding(root, record["historical_stage1_record_ref_and_sha256"], HISTORICAL_RECORD)
    _expect_binding(root, record["historical_stage1_review_ref_and_sha256"], HISTORICAL_REVIEW)
    if record["required_file_refs_and_sha256"] != [binding(root, R2_CHECKER), binding(root, R2_TEST)]:
        raise Stage1R2RemediationError("required R2 binding drift")
    if record["workflow_refs_and_sha256"] != [binding(root, WORKFLOW), binding(root, BRANCH_PROTECTION)]:
        raise Stage1R2RemediationError("workflow binding drift")
    for relative, digest in {**EXPECTED_HISTORICAL, **EXPECTED_R2}.items():
        if binding(root, relative)["sha256"] != digest:
            raise Stage1R2RemediationError(f"frozen input drift: {relative.as_posix()}")
    commands = record["focused_commands_and_exact_results"]
    if not isinstance(commands, list) or tuple(row.get("id") for row in commands) != COMMAND_IDS:
        raise Stage1R2RemediationError("focused command set drift")
    if any(row.get("exit_code") not in {0, 1} or not isinstance(row.get("result"), str) for row in commands):
        raise Stage1R2RemediationError("focused command result drift")
    fail_row = next(row for row in commands if row["id"] == "r2_direct_fail_closed_fixture")
    if fail_row["exit_code"] != 1 or '"status": "FAIL"' not in fail_row["result"]:
        raise Stage1R2RemediationError("R2 fail-closed witness drift")
    if any(row["exit_code"] != 0 for row in commands if row["id"] != "r2_direct_fail_closed_fixture"):
        raise Stage1R2RemediationError("focused acceptance contains failure")
    receipts = record["test_receipts"]
    if not isinstance(receipts, list) or len(receipts) != len(COMMAND_IDS):
        raise Stage1R2RemediationError("test receipt set drift")
    for receipt, check_id in zip(receipts, COMMAND_IDS, strict=True):
        relative = Path(receipt.get("path", ""))
        if relative.name != f"{check_id}.log":
            raise Stage1R2RemediationError("test receipt identity drift")
        _expect_binding(root, receipt, relative)
    checker = record["independent_review_or_checker"]
    if checker != {**binding(root, SELF_CHECKER), "status": "PASS"}:
        raise Stage1R2RemediationError("independent checker binding drift")
    if record["warning_skip_deselect_inventory"] != {"warnings": [], "skips": [], "deselects": []}:
        raise Stage1R2RemediationError("warning/skip/deselect inventory drift")
    if record["external_effects"] != [] or record["authority_ceiling"] != AUTHORITY_CEILING:
        raise Stage1R2RemediationError("external effect or authority ceiling drift")
    cleanup = record["cleanup"]
    if cleanup != {"temporary_fixture_directories": "REMOVED", "pyc_written": False, "retained_resources": []}:
        raise Stage1R2RemediationError("cleanup declaration drift")
    if not isinstance(record["observed_at"], str) or not record["observed_at"].endswith("Z"):
        raise Stage1R2RemediationError("observed_at must be an explicit UTC value")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        value = json.loads(args.record.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise Stage1R2RemediationError("record JSON root must be an object")
        validate_record(args.repo_root.resolve(), value)
    except (Stage1R2RemediationError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"stage1 R2 remediation record FAIL: {exc}", file=sys.stderr)
        return 1
    print("stage1 R2 remediation record PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
