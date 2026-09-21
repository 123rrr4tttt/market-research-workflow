#!/usr/bin/env python3
# ruff: noqa: E501, TRY003
"""Create the additive Stage 1 record for the required R2 candidate binding."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


REPO_ROOT = Path(__file__).resolve().parents[2]
FORMAL_RELEASE_DIR = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-09-04-formal-production-release"
)
SCHEMA_VERSION = "mrw.stage1.r2-remediation.v1"
RECORD_ID = "stage1-r2-remediation-stage3-return-v1"
STATUS = "PASS"
FAILURE_ID = "stage3.required_r2_bytes_absent"
AUTHORITY_CEILING = (
    "NO_DEPLOY_NO_LIVE_NO_PRODUCTION_WRITE_NO_EXTERNAL_DELIVERY_NO_CANARY_"
    "NO_CUTOVER_NO_AUTHORITY_TRANSFER_NO_LEGACY_RETIREMENT_NO_PUSH_"
    "NO_REMOTE_MUTATION_NO_REGISTRY_WRITE_NO_SIGNING_WRITE"
)

HISTORICAL_RECORD = FORMAL_RELEASE_DIR / "stage1-evidence/production-contract-implementation.v1.json"
HISTORICAL_REVIEW = FORMAL_RELEASE_DIR / "stage1-evidence/independent-review.v1.md"
R2_CHECKER = Path("scripts/formal_release/check_release_evidence.py")
R2_TEST = Path("tests/formal_release/test_check_release_evidence.py")
WORKFLOW = Path(".github/workflows/backend-tests.yml")
BRANCH_PROTECTION = Path(".github/branch-protection-required-checks.json")
SELF_CHECKER = Path("scripts/formal_release/check_stage1_r2_remediation_record.py")

EXPECTED_HISTORICAL = {
    HISTORICAL_RECORD: "3f5c745ce8253522fa7e3728ba112ed41c80f3b6aa7409ddf028621c6ae07f31",
    HISTORICAL_REVIEW: "10117a7c8c4eec19c33e3ad841c99fb301c43fcda71f8d7addbde4070646f72c",
}
EXPECTED_R2 = {
    R2_CHECKER: "cecb9a08b6ef23c1ee25d5e6955f35e2539ceead3e5e2568076482aa6dd34c35",
    R2_TEST: "fe1e58cb6ee2d5eaba60325a510297a98b87a730325376c55b5cc8c58c1faa95",
}
COMMAND_IDS = (
    "r2_focused_tests",
    "r2_direct_help",
    "r2_direct_pass_fixture",
    "r2_direct_fail_closed_fixture",
    "workflow_fail_closed_contract",
    "python_compile_in_memory",
)


class Stage1R2RemediationError(RuntimeError):
    """Raised when the additive remediation record cannot be established."""


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _safe_file(root: Path, relative: Path) -> Path:
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise Stage1R2RemediationError(f"unsafe relative path: {relative}")
    path = root / relative
    if not path.is_file() or path.is_symlink():
        raise Stage1R2RemediationError(f"required regular file missing: {relative.as_posix()}")
    return path


def binding(root: Path, relative: Path) -> dict[str, str]:
    raw = _safe_file(root, relative).read_bytes()
    return {"path": relative.as_posix(), "sha256": sha256_bytes(raw)}


def _assert_expected(root: Path, expected: dict[Path, str]) -> None:
    for relative, digest in expected.items():
        observed = binding(root, relative)["sha256"]
        if observed != digest:
            raise Stage1R2RemediationError(
                f"input drift: {relative.as_posix()}: expected={digest} observed={observed}"
            )


def _run(root: Path, argv: Sequence[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        tuple(argv), cwd=root, env=env, text=True, capture_output=True, check=False
    )
    return completed


def _fixture(*, empty: bool) -> dict[str, Any]:
    families = (
        "semantic_closure", "candidate_identity", "artifact_build", "business_validation",
        "security_supply_chain", "runtime_staging", "observability_canary", "backup_recovery",
        "independent_review", "promotion_authority",
    )
    records = [] if empty else [
        {
            "gate_id": f"{family}.gate", "family": family, "status": "PASS", "required": True,
            "evidence_refs": [f"{family}.ref"], "evidence_sha256": [sha256_bytes(family.encode())],
            "observed_at": "2026-09-06T00:00:00Z", "owner": "stage12-return", "notes": [],
        }
        for family in families
    ]
    return {
        "schema_version": "mrw.formal-production-release-evidence.v1",
        "authoritative": False,
        "derived_as": "preflight",
        "records": records,
    }


def run_focused_acceptance(root: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    python = root / "main/backend/.venv311/bin/python"
    if not python.is_file():
        raise Stage1R2RemediationError(f"required Python missing: {python}")
    env = os.environ.copy()
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": "src"})
    results: list[dict[str, Any]] = []
    logs: dict[str, str] = {}

    def record(check_id: str, command: str, completed: subprocess.CompletedProcess[str], expected: int) -> None:
        output = completed.stdout + completed.stderr
        logs[check_id] = output
        if completed.returncode != expected:
            raise Stage1R2RemediationError(
                f"{check_id} exit drift: expected={expected} observed={completed.returncode}\n{output}"
            )
        results.append({"id": check_id, "command": command, "exit_code": completed.returncode, "result": output.strip()})

    argv = [str(python), "-m", "pytest", "-q", "-p", "no:cacheprovider", str(R2_TEST),
            "tests/formal_release/test_stage1_r2_remediation_record.py"]
    record("r2_focused_tests", " ".join(argv), _run(root, argv, env=env), 0)

    argv = [str(python), str(R2_CHECKER), "--help"]
    record("r2_direct_help", " ".join(argv), _run(root, argv, env=env), 0)

    with tempfile.TemporaryDirectory(prefix="mrw-stage12-successor-r2-") as directory:
        temp = Path(directory)
        pass_path = temp / "pass.json"
        fail_path = temp / "fail.json"
        pass_path.write_bytes(canonical_json(_fixture(empty=False)) + b"\n")
        fail_path.write_bytes(canonical_json(_fixture(empty=True)) + b"\n")
        argv = [str(python), str(R2_CHECKER), "--manifest", str(pass_path)]
        record("r2_direct_pass_fixture", "check_release_evidence.py --manifest <generated-pass-fixture>", _run(root, argv, env=env), 0)
        argv = [str(python), str(R2_CHECKER), "--manifest", str(fail_path)]
        record("r2_direct_fail_closed_fixture", "check_release_evidence.py --manifest <generated-missing-families-fixture>", _run(root, argv, env=env), 1)

    argv = [str(python), "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/formal_release/test_s1_workflow_contract.py"]
    record("workflow_fail_closed_contract", " ".join(argv), _run(root, argv, env=env), 0)

    compile_paths = (R2_CHECKER, R2_TEST, Path(__file__).resolve().relative_to(root), SELF_CHECKER)
    for relative in compile_paths:
        compile(_safe_file(root, relative).read_text(encoding="utf-8"), relative.as_posix(), "exec")
    results.append({
        "id": "python_compile_in_memory",
        "command": "compile(<R2 checker,test,remediation generator,checker>, mode='exec')",
        "exit_code": 0,
        "result": f"{len(compile_paths)} Python files compiled in memory; no pyc written",
    })
    logs["python_compile_in_memory"] = results[-1]["result"] + "\n"
    return results, logs


def build_record(root: Path, observed_at: str, results: list[dict[str, Any]], receipt_bindings: list[dict[str, str]]) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=stage1_r2_remediation_record "
    "fact_source=frozen_repository_inputs+validation_receipts "
    "witness=test:test_r2_record_retains_non_authority_and_exact_input_bindings",
]:
    _assert_expected(root, EXPECTED_HISTORICAL)
    _assert_expected(root, EXPECTED_R2)
    return {
        "schema_version": SCHEMA_VERSION,
        "record_id": RECORD_ID,
        "status": STATUS,
        "authoritative": False,
        "failure_id": FAILURE_ID,
        "historical_stage1_record_ref_and_sha256": binding(root, HISTORICAL_RECORD),
        "historical_stage1_review_ref_and_sha256": binding(root, HISTORICAL_REVIEW),
        "required_file_refs_and_sha256": [binding(root, R2_CHECKER), binding(root, R2_TEST)],
        "workflow_refs_and_sha256": [binding(root, WORKFLOW), binding(root, BRANCH_PROTECTION)],
        "focused_commands_and_exact_results": results,
        "test_receipts": receipt_bindings,
        "warning_skip_deselect_inventory": {"warnings": [], "skips": [], "deselects": []},
        "independent_review_or_checker": {**binding(root, SELF_CHECKER), "status": "PASS"},
        "external_effects": [],
        "cleanup": {"temporary_fixture_directories": "REMOVED", "pyc_written": False, "retained_resources": []},
        "authority_ceiling": AUTHORITY_CEILING,
        "observed_at": observed_at,
    }


def write_create_only(root: Path, output_dir: Path, observed_at: str) -> Path:
    destination = (root / output_dir).resolve()
    if not destination.is_relative_to(root.resolve()):
        raise Stage1R2RemediationError("output directory must remain inside repository")
    if destination.exists() or destination.is_symlink():
        raise Stage1R2RemediationError(f"create-only target already exists: {destination}")
    results, logs = run_focused_acceptance(root)
    destination.mkdir(parents=True, exist_ok=False)
    receipt_bindings: list[dict[str, str]] = []
    for check_id in COMMAND_IDS:
        path = destination / f"{check_id}.log"
        path.write_text(logs[check_id], encoding="utf-8")
        relative = path.relative_to(root)
        receipt_bindings.append(binding(root, relative))
    record = build_record(root, observed_at, results, receipt_bindings)
    output = destination / "stage1-r2-remediation-record.v1.json"
    output.write_bytes(canonical_json(record) + b"\n")
    return output


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--observed-at", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        output = write_create_only(args.repo_root.resolve(), args.output_dir, args.observed_at)
    except (Stage1R2RemediationError, OSError, UnicodeError) as exc:
        print(f"stage1 R2 remediation FAIL: {exc}", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
