#!/usr/bin/env python3
# ruff: noqa: E501, TRY003
"""Validate the create-only Stage 3 v6 artifact remediation package."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import xml.etree.ElementTree as ET
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
WORKFLOW_SELECTOR_PYTHON_ROOTS = (
    "main/backend",
    "main/ops",
    "src/mrw_functorial_kit",
    "ops",
    "scripts",
    "tests",
)
WORKFLOW_SELECTOR_SHELL_ROOTS = ("main/ops", "ops", "scripts")
WORKFLOW_SELECTOR_JSON_ROOTS = (
    "docs/governance",
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-09-04-formal-production-release/stage0-evidence",
)
WORKFLOW_SELECTOR_JSON_SUBTREE_ROOTS = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind",
)
BUILDER = HERE / "build_stage3_v6_artifact_remediation_v1.py"
CHECKER = HERE / Path(__file__).name
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
CONTRACT_SHA256 = "f7d3637c5cc48eaf7396331c3657cc6cff42269dbf4ffab17af4f7a7a3170d5a"
V6_COMMIT = "909eb608e538b6427bcbacca974f1efb05fef611"
V6_TREE = "a60b795e509aa5dc479904a321fba32ed0ab9ab2"
HISTORICAL_V6_REMEDIATION_SHA256 = (
    "b25c4fbccef8358a62a8f8ca8a46c86c593be9a8f42e2ffe370607a7a8f93002"
)
EVIDENCE_ROOT = Path("/Users/wangyiliang/.codex/release-evidence/mrw-stage2-20260906-v6")
EVIDENCE_HASHES = {
    "candidate-manifest.v6.json": "020ea3fe312fe5a21f5c064455fc7e2fb1d53440ca0a2dfa9bf115777c80ece1",
    "closure.final.v6.json": "d2f0607fbf29422f78887c5c72ac17af2d867e719044fa03a545ba19a1e30e73",
    "stage2-record.final.v6.json": "0a6555aca056084f3e7645d03b7adf04b3e4f2be49d52294e48f2b2a239f9a90",
    "r1.final.v6.json": "c0ed90b8d1253b0d8191cef46506d5ed436b74f34c6a4f8a0758de0b76ef8f2d",
    "r2.pass.v6.json": "0edca14b4177a63cb2046fb74ab01e1099d66277d5a778df91b6c7faedef9c76",
    "r3.pass.v6.json": "9f7bc679db5e6e481090e43c1c4ee9d59cfe29b9efa3d8e9fa470689cda61e03",
}
OBSERVED_ARTIFACT_PATHS = (
    ".github/branch-protection-required-checks.json",
    ".github/workflows/backend-tests.yml",
    "main/backend/Dockerfile",
    "main/frontend-modern/Dockerfile",
    "main/frontend-modern/package-lock.json",
    "main/frontend-modern/pnpm-lock.yaml",
    "scripts/formal_release/check_static_production_contract.py",
    "scripts/formal_release/stage2_candidate_intake.py",
    "tests/formal_release/test_stage2_candidate_intake.py",
)
REQUIRED_ARTIFACT_PATHS = (
    *OBSERVED_ARTIFACT_PATHS,
    "main/backend/app/services/agent_core/native_provider.py",
    "main/frontend-modern/package.json",
)
CEILING = (
    "NO_DEPLOY_NO_LIVE_NO_PRODUCTION_WRITE_NO_EXTERNAL_DELIVERY_NO_CANARY_"
    "NO_CUTOVER_NO_AUTHORITY_TRANSFER_NO_LEGACY_RETIREMENT_NO_PUSH_"
    "NO_REMOTE_MUTATION_NO_REGISTRY_WRITE_NO_SIGNING_WRITE"
)
RECORD_FIELDS = {
    "schema_version",
    "status",
    "authoritative",
    "authority_ceiling",
    "contract",
    "predecessor",
    "artifact_paths",
    "additional_binding_paths",
    "test_receipts",
    "command_receipts",
    "fresh_test_summary",
    "current_bindings",
    "external_effects",
    "production_release_authorized",
}
PYTEST_RECEIPT_FIELDS = {
    "artifacts",
    "authoritative",
    "command",
    "cwd",
    "elapsed_seconds",
    "environment",
    "exit_code",
    "isolation",
}
COMMAND_RECEIPT_FIELDS = {
    "artifacts",
    "authoritative",
    "command",
    "cwd",
    "elapsed_seconds",
    "environment",
    "exit_code",
}
FRONTEND_COMMAND_RECEIPTS = {
    "frontend-build.json": ("pnpm", "build"),
    "frontend-frozen-install.json": ("pnpm", "install", "--frozen-lockfile"),
    "frontend-lint.json": ("pnpm", "lint"),
    "frontend-storybook.json": ("pnpm", "storybook:build"),
    "frontend-typecheck.json": ("pnpm", "exec", "tsc"),
    "frontend-build-development-takeover-20260908.json": ("pnpm", "build"),
    "frontend-frozen-install-development-takeover-20260908.json": (
        "pnpm", "install", "--frozen-lockfile"
    ),
    "frontend-lint-development-takeover-20260908.json": ("pnpm", "lint"),
    "frontend-storybook-development-takeover-20260908.json": (
        "pnpm", "storybook:build"
    ),
    "frontend-typecheck-development-takeover-20260908.json": (
        "pnpm", "exec", "tsc"
    ),
}


def require(condition: bool, message: str) -> None:
    if not condition:
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


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode()


def safe_relative(value: object, *, label: str = "path") -> Path:
    require(isinstance(value, str) and bool(value), f"{label}_NOT_STRING")
    path = Path(value)  # type: ignore[arg-type]
    require(not path.is_absolute(), f"{label}_ABSOLUTE")
    require(path.as_posix() == value and "\\" not in value, f"{label}_NOT_CANONICAL")  # type: ignore[arg-type]
    require(all(part not in {"", ".", ".."} for part in path.parts), f"{label}_TRAVERSAL")
    return path


def binding_ref(path: Path) -> dict[str, str]:
    return {"path": path.as_posix(), "sha256": sha(ROOT / path)}


def workflow_selector_policy_binding(*, root: Path = ROOT) -> dict[str, Any]:
    """Bind the exact additive selector policy without claiming release authority."""
    return {
        "implementation": {
            "path": SOURCE_CLOSURE_PATH.as_posix(),
            "sha256": sha(root / SOURCE_CLOSURE_PATH),
        },
        "test": {
            "path": SOURCE_CLOSURE_TEST_PATH.as_posix(),
            "sha256": sha(root / SOURCE_CLOSURE_TEST_PATH),
        },
        "python_roots": list(WORKFLOW_SELECTOR_PYTHON_ROOTS),
        "shell_roots": list(WORKFLOW_SELECTOR_SHELL_ROOTS),
        "json_roots": list(WORKFLOW_SELECTOR_JSON_ROOTS),
        "json_subtree_roots": list(WORKFLOW_SELECTOR_JSON_SUBTREE_ROOTS),
        "json_subtree_required_parent_component": "sidecar-inputs",
    }


def validate_file_hash(reference: object, root: Path = ROOT, label: str = "REF") -> Path:
    require(isinstance(reference, dict), f"{label}_REF_TYPE")
    ref: dict[str, Any] = reference  # type: ignore[assignment]
    require(set(ref) == {"path", "sha256"}, f"{label}_REF_FIELDS")
    relative = safe_relative(ref.get("path"), label=label)
    require(isinstance(ref.get("sha256"), str) and len(ref["sha256"]) == 64, f"{label}_DIGEST")
    require(sha(root / relative) == ref["sha256"], f"{label}_HASH:{relative.as_posix()}")
    return relative


def validate_evidence_hash(reference: object) -> Path:
    require(isinstance(reference, dict) and set(reference) == {"path", "sha256"}, "EVIDENCE_REF_FIELDS")
    raw_path = reference.get("path")
    require(isinstance(raw_path, str) and bool(raw_path), "EVIDENCE_PATH_TYPE")
    path = Path(raw_path)
    require(path.is_absolute() and path == EVIDENCE_ROOT / path.name, "EVIDENCE_PATH_CANONICAL")
    require(sha(path) == reference.get("sha256"), f"EVIDENCE_HASH:{path.name}")
    return path


def validate_junit(path: Path) -> dict[str, int]:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise ValueError(f"JUNIT_PARSE:{path}") from exc
    suites = list(root.iter("testsuite"))
    require(bool(suites), "JUNIT_NO_SUITE")
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for key in totals:
            try:
                totals[key] += int(suite.attrib[key])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"JUNIT_COUNT:{key}:{path}") from exc
    require(totals["tests"] > 0, "JUNIT_EMPTY")
    require(totals["failures"] == 0 and totals["errors"] == 0 and totals["skipped"] == 0, "JUNIT_NOT_CLEAN")
    return totals


def project_receipt_artifact(
    raw_path: Path,
    *,
    root: Path,
    source_root: Path,
) -> tuple[Path, Path]:
    """Project a historical absolute source locator onto this relocated root."""
    require(isinstance(source_root, Path) and source_root.is_absolute(), "RECEIPT_SOURCE_ANCHOR")
    require(isinstance(raw_path, Path) and raw_path.is_absolute(), "RECEIPT_ARTIFACT_LOCATOR")
    source_raw = source_root / HERE / "raw"
    require(raw_path.parent == source_raw, f"RECEIPT_OUTSIDE_SOURCE_RAW:{raw_path}")
    relative = HERE / "raw" / raw_path.name
    current = root / relative
    try:
        metadata = current.lstat()
    except OSError as exc:
        raise ValueError(f"RELOCATED_ARTIFACT_MISSING:{relative.as_posix()}") from exc
    require(
        stat.S_ISREG(metadata.st_mode) and not current.is_symlink(),
        f"RELOCATED_ARTIFACT_TYPE:{relative.as_posix()}",
    )
    return current, relative


def validate_receipt_path(
    path: Path,
    *,
    root: Path,
    source_root: Path | None = None,
) -> Path:
    current, _relative = project_receipt_artifact(
        path,
        root=root,
        source_root=source_root or root,
    )
    return current


def validate_command_receipt(
    payload: dict[str, Any],
    *,
    root: Path,
    source_root: Path | None = None,
) -> dict[str, Any]:
    receipt_source_root = source_root or root
    require(set(payload) == COMMAND_RECEIPT_FIELDS, "COMMAND_RECEIPT_FIELDS")
    require(payload.get("authoritative") is False, "COMMAND_RECEIPT_AUTHORITY")
    require(payload.get("exit_code") == 0, "COMMAND_RECEIPT_EXIT_CODE")
    command = payload.get("command")
    require(
        isinstance(command, list)
        and bool(command)
        and all(isinstance(item, str) and bool(item) for item in command),
        "COMMAND_RECEIPT_COMMAND",
    )
    cwd = payload.get("cwd")
    require(isinstance(cwd, str) and Path(cwd).is_absolute(), "COMMAND_RECEIPT_CWD")
    require(Path(cwd).is_relative_to(receipt_source_root), "COMMAND_RECEIPT_CWD_ANCHOR")
    environment = payload.get("environment")
    require(
        isinstance(environment, dict)
        and all(isinstance(key, str) and isinstance(value, str) for key, value in environment.items()),
        "COMMAND_RECEIPT_ENVIRONMENT",
    )
    elapsed = payload.get("elapsed_seconds")
    require(
        isinstance(elapsed, (int, float))
        and not isinstance(elapsed, bool)
        and elapsed >= 0,
        "COMMAND_RECEIPT_ELAPSED",
    )
    artifacts = payload.get("artifacts")
    require(isinstance(artifacts, list) and len(artifacts) == 1, "COMMAND_RECEIPT_ARTIFACT_COUNT")
    item = artifacts[0]
    require(isinstance(item, dict) and set(item) == {"path", "sha256"}, "COMMAND_RECEIPT_ARTIFACT_FIELDS")
    raw_path = item.get("path")
    require(isinstance(raw_path, str) and bool(raw_path), "COMMAND_RECEIPT_ARTIFACT_PATH")
    path, _relative = project_receipt_artifact(
        Path(raw_path),
        root=root,
        source_root=receipt_source_root,
    )
    require(path.suffix.lower() == ".log", "COMMAND_RECEIPT_ARTIFACT_KIND")
    require(isinstance(item.get("sha256"), str), "COMMAND_RECEIPT_ARTIFACT_DIGEST")
    require(sha(path) == item["sha256"], f"COMMAND_RECEIPT_ARTIFACT_HASH:{path}")
    expected = FRONTEND_COMMAND_RECEIPTS.get(path.with_suffix(".json").name)
    require(expected is not None, "COMMAND_RECEIPT_UNKNOWN")
    observed = tuple(command)
    require(observed[: len(expected)] == expected, "COMMAND_RECEIPT_COMMAND_KIND")
    return {"log": {"path": path.as_posix(), "sha256": item["sha256"]}}


def validate_receipt(
    payload: dict[str, Any],
    *,
    root: Path,
    source_root: Path | None = None,
) -> dict[str, Any]:
    receipt_source_root = source_root or root
    require(set(payload) == PYTEST_RECEIPT_FIELDS, "RECEIPT_FIELDS")
    require(payload.get("authoritative") is False, "RECEIPT_AUTHORITY")
    require(payload.get("exit_code") == 0, "RECEIPT_EXIT_CODE")
    command = payload.get("command")
    require(
        isinstance(command, list)
        and bool(command)
        and all(isinstance(item, str) and bool(item) for item in command),
        "RECEIPT_COMMAND",
    )
    require(any("pytest" in item for item in command), "RECEIPT_NOT_PYTEST")
    cwd = payload.get("cwd")
    require(isinstance(cwd, str) and Path(cwd).is_absolute(), "RECEIPT_CWD")
    require(Path(cwd).is_relative_to(receipt_source_root), "RECEIPT_CWD_ANCHOR")
    environment = payload.get("environment")
    require(
        isinstance(environment, dict)
        and all(isinstance(key, str) and isinstance(value, str) for key, value in environment.items()),
        "RECEIPT_ENVIRONMENT",
    )
    require(
        payload.get("isolation") in {"getaddrinfo fail-fast injection only", "none added"},
        "RECEIPT_ISOLATION",
    )
    elapsed = payload.get("elapsed_seconds")
    require(
        isinstance(elapsed, (int, float))
        and not isinstance(elapsed, bool)
        and elapsed >= 0,
        "RECEIPT_ELAPSED",
    )
    artifacts = payload.get("artifacts")
    require(isinstance(artifacts, list) and len(artifacts) == 2, "RECEIPT_ARTIFACT_COUNT")
    observed: dict[str, dict[str, str]] = {}
    suffixes: list[str] = []
    for item in artifacts:
        require(isinstance(item, dict) and set(item) == {"path", "sha256"}, "RECEIPT_ARTIFACT_FIELDS")
        raw_path = item.get("path")
        require(isinstance(raw_path, str) and bool(raw_path), "RECEIPT_ARTIFACT_PATH")
        path, _relative = project_receipt_artifact(
            Path(raw_path),
            root=root,
            source_root=receipt_source_root,
        )
        require(isinstance(item.get("sha256"), str), "RECEIPT_ARTIFACT_DIGEST")
        require(sha(path) == item["sha256"], f"RECEIPT_ARTIFACT_HASH:{path}")
        suffix = path.suffix.lower()
        suffixes.append(suffix)
        observed[suffix] = {"path": path.as_posix(), "sha256": item["sha256"]}
    require(sorted(suffixes) == [".log", ".xml"], "RECEIPT_ARTIFACT_KINDS")
    totals = validate_junit(Path(observed[".xml"]["path"]))
    return {
        "log": observed[".log"],
        "junit": {**observed[".xml"], **totals},
    }


def validate_observation(payload: dict[str, Any]) -> dict[str, Any]:
    require(
        set(payload)
        == {
            "authoritative",
            "contract",
            "paths",
            "predecessor",
            "production_release_authorized",
            "schema_version",
            "status",
            "successor_created",
        },
        "OBSERVATION_FIELDS",
    )
    require(payload.get("schema_version") == "mrw.stage3_v6_artifact_repair.input_observation.v1", "OBSERVATION_SCHEMA")
    require(payload.get("status") == "INPUTS_VERIFIED_REPAIR_IN_PROGRESS", "OBSERVATION_STATUS")
    require(payload.get("authoritative") is False, "OBSERVATION_AUTHORITY")
    require(payload.get("production_release_authorized") is False, "OBSERVATION_RELEASE")
    require(payload.get("successor_created") is False, "OBSERVATION_SUCCESSOR_FLAG")
    contract = payload.get("contract")
    require(
        contract
        == {
            "path": CONTRACT.as_posix(),
            "sha256": CONTRACT_SHA256,
        },
        "OBSERVATION_CONTRACT",
    )
    predecessor = payload.get("predecessor")
    require(isinstance(predecessor, dict), "OBSERVATION_PREDECESSOR_TYPE")
    require(predecessor.get("commit") == V6_COMMIT and predecessor.get("tree") == V6_TREE, "OBSERVATION_V6_IDENTITY")
    evidence = predecessor.get("evidence")
    require(isinstance(evidence, list) and len(evidence) == len(EVIDENCE_HASHES), "OBSERVATION_EVIDENCE_COUNT")
    seen_evidence: set[str] = set()
    for item in evidence:
        require(isinstance(item, dict) and set(item) == {"path", "sha256"}, "OBSERVATION_EVIDENCE_REF")
        name = Path(item.get("path", "")).name
        require(EVIDENCE_HASHES.get(name) == item.get("sha256"), f"OBSERVATION_EVIDENCE:{name}")
        require(name not in seen_evidence, "OBSERVATION_EVIDENCE_DUPLICATE")
        seen_evidence.add(name)
    require(seen_evidence == set(EVIDENCE_HASHES), "OBSERVATION_EVIDENCE_SET")
    rows = payload.get("paths")
    require(isinstance(rows, list) and bool(rows), "OBSERVATION_PATHS")
    observed: dict[str, dict[str, str]] = {}
    for row in rows:
        require(
            isinstance(row, dict)
            and set(row)
            == {
                "observation_scope",
                "observed_source_sha256",
                "path",
                "v6_sha256",
            },
            "OBSERVATION_PATH_FIELDS",
        )
        relative = safe_relative(row.get("path"), label="OBSERVATION_PATH")
        require(row.get("observation_scope") == "RESUMED_REPAIR_OBSERVATION_NOT_TASK_START", "OBSERVATION_SCOPE")
        observed[relative.as_posix()] = {
            "v6_sha256": row.get("v6_sha256", ""),
            "observed_source_sha256": row.get("observed_source_sha256", ""),
        }
    require(set(OBSERVED_ARTIFACT_PATHS) <= set(observed), "OBSERVATION_PATH_SET")
    return {"predecessor": predecessor, "paths": observed}


def validate_manifest(manifest: dict[str, Any], *, root: Path = ROOT, expected_paths: tuple[Path, ...] | None = None) -> None:
    require(manifest.get("schema_version") == "mrw.stage1.stage3_v6_artifact_remediation_manifest.v1", "MANIFEST_SCHEMA")
    require(manifest.get("status") == "COMPLETE_NOT_AUTHORITY", "MANIFEST_STATUS")
    require(manifest.get("authoritative") is False, "MANIFEST_AUTHORITY")
    require(manifest.get("authority_ceiling") == CEILING, "MANIFEST_CEILING")
    members = manifest.get("members")
    require(isinstance(members, list) and bool(members), "MANIFEST_MEMBERS")
    require(manifest.get("member_count") == len(members), "MANIFEST_COUNT")
    paths: list[str] = []
    seen: set[str] = set()
    for row in members:
        require(isinstance(row, dict) and set(row) == {"path", "bytes", "sha256"}, "MANIFEST_MEMBER_FIELDS")
        relative = safe_relative(row.get("path"), label="MANIFEST_MEMBER")
        key = relative.as_posix()
        require(key not in seen, f"MANIFEST_DUPLICATE:{key}")
        seen.add(key)
        paths.append(key)
        path = root / relative
        metadata = path.lstat()
        require(stat.S_ISREG(metadata.st_mode), f"MANIFEST_MEMBER_TYPE:{key}")
        require(metadata.st_size == row.get("bytes"), f"MANIFEST_MEMBER_SIZE:{key}")
        require(sha(path) == row.get("sha256"), f"MANIFEST_MEMBER_HASH:{key}")
    require(paths == sorted(paths), "MANIFEST_PATH_ORDER")
    if expected_paths is not None:
        require(tuple(Path(path) for path in paths) == expected_paths, "MANIFEST_MEMBERSHIP")


def validate_record(
    record: dict[str, Any],
    *,
    root: Path = ROOT,
    receipt_paths: tuple[Path, ...] | None = None,
    record_path: Path = RECORD,
) -> tuple[Path, ...]:
    require(record_path in {RECORD, CORRECTION_RECORD}, "RECORD_PATH_UNSUPPORTED")
    correction = record_path == CORRECTION_RECORD
    require(record.get("schema_version") == "mrw.stage1.stage3_v6_artifact_remediation_record.v1", "RECORD_SCHEMA")
    require(record.get("status") == "PASS_STAGE3_V6_ARTIFACT_REMEDIATION_NOT_AUTHORITY", "RECORD_STATUS")
    require(record.get("authoritative") is False, "RECORD_AUTHORITY")
    require(record.get("production_release_authorized") is False, "RECORD_RELEASE")
    require(record.get("authority_ceiling") == CEILING, "RECORD_CEILING")
    require(set(record) == (RECORD_FIELDS | {"correction"} if correction else RECORD_FIELDS), "RECORD_FIELDS")
    if correction:
        correction_binding = record.get("correction")
        require(
            correction_binding
            == {
                "attempt": 1,
                "reason": "INTAKE_C6_AND_WORKFLOW_SELECTOR_POLICY_BYTE_DRIFT",
                "predecessor_record": {
                    "path": PRIOR_ATTEMPT_RECORD.as_posix(),
                    "sha256": PRIOR_ATTEMPT_RECORD_SHA256,
                },
                "final_bindings": [
                    {"path": path.as_posix(), "sha256": sha(root / path)}
                    for path in CORRECTION_FINAL_BINDING_PATHS
                ],
                "workflow_selector_policy": workflow_selector_policy_binding(
                    root=root
                ),
            },
            "CORRECTION_BINDING",
        )
        require(sha(root / PRIOR_ATTEMPT_RECORD) == PRIOR_ATTEMPT_RECORD_SHA256, "PRIOR_ATTEMPT_HASH")
    contract_ref = record.get("contract")
    require(contract_ref == {"path": CONTRACT.as_posix(), "sha256": CONTRACT_SHA256}, "RECORD_CONTRACT")
    require(sha(root / CONTRACT) == CONTRACT_SHA256, "CONTRACT_HASH")

    predecessor = record.get("predecessor")
    require(isinstance(predecessor, dict), "PREDECESSOR_TYPE")
    require(
        set(predecessor)
        == {
            "candidate_root",
            "commit",
            "tree",
    "evidence",
    "input_observation",
    "receipt_source_root",
    "v6_intake_remediation_record",
        },
        "PREDECESSOR_FIELDS",
    )
    require(predecessor.get("commit") == V6_COMMIT and predecessor.get("tree") == V6_TREE, "PREDECESSOR_IDENTITY")
    raw_source_anchor = predecessor.get("receipt_source_root")
    require(isinstance(raw_source_anchor, str), "RECEIPT_SOURCE_ANCHOR_TYPE")
    receipt_source_root = Path(raw_source_anchor)
    require(receipt_source_root.is_absolute(), "RECEIPT_SOURCE_ANCHOR_ABSOLUTE")
    require(receipt_source_root != Path("/") and len(receipt_source_root.parts) > 1, "RECEIPT_SOURCE_ANCHOR_ROOT")
    observation_ref = predecessor.get("input_observation")
    observation_path = validate_file_hash(observation_ref, root=root, label="OBSERVATION")
    require(observation_path == INPUT_OBSERVATION, "OBSERVATION_PATH")
    historical_ref = predecessor.get("v6_intake_remediation_record")
    require(
        historical_ref
        == {
            "path": HISTORICAL_V6_REMEDIATION_RECORD.as_posix(),
            "sha256": HISTORICAL_V6_REMEDIATION_SHA256,
        },
        "HISTORICAL_V6_BINDING",
    )
    require(sha(root / HISTORICAL_V6_REMEDIATION_RECORD) == HISTORICAL_V6_REMEDIATION_SHA256, "HISTORICAL_V6_HASH")
    historical = load(root / HISTORICAL_V6_REMEDIATION_RECORD)
    require(historical.get("schema_version") == "mrw.stage1.stage2_v6_intake_remediation_record.v5", "HISTORICAL_V6_SCHEMA")
    require(historical.get("authoritative") is False, "HISTORICAL_V6_AUTHORITY")
    evidence_refs = predecessor.get("evidence")
    require(isinstance(evidence_refs, list), "EVIDENCE_TYPE")
    for reference in evidence_refs:
        validate_evidence_hash(reference)

    observation = validate_observation(load(root / observation_path))
    require(predecessor.get("candidate_root") == observation["predecessor"].get("root"), "CANDIDATE_ROOT")
    require(predecessor.get("evidence") == observation["predecessor"].get("evidence"), "EVIDENCE_PROJECTION")

    rows = record.get("artifact_paths")
    require(isinstance(rows, list) and bool(rows), "ARTIFACT_PATHS_TYPE")
    row_map: dict[str, dict[str, Any]] = {}
    for row in rows:
        require(
            isinstance(row, dict)
            and set(row)
            == {
                "path",
                "v6_sha256",
                "v6_present",
                "current_sha256",
                "changed",
            },
            "ARTIFACT_PATH_FIELDS",
        )
        relative = safe_relative(row.get("path"), label="ARTIFACT_PATH")
        key = relative.as_posix()
        require(key not in row_map, f"ARTIFACT_PATH_DUPLICATE:{key}")
        require(isinstance(row.get("v6_present"), bool), "ARTIFACT_V6_PRESENT")
        require(isinstance(row.get("changed"), bool), "ARTIFACT_CHANGED")
        for field in ("v6_sha256", "current_sha256"):
            digest = row.get(field)
            require(isinstance(digest, str) and len(digest) == 64, f"ARTIFACT_{field}:{key}")
        require(row["current_sha256"] == sha(root / relative), f"ARTIFACT_CURRENT_HASH:{key}")
        if key in observation["paths"]:
            require(row["v6_sha256"] == observation["paths"][key]["v6_sha256"], f"ARTIFACT_V6_HASH:{key}")
        require(row["changed"] == (row["v6_sha256"] != row["current_sha256"]), f"ARTIFACT_CHANGED_FLAG:{key}")
        row_map[key] = row
    require(set(REQUIRED_ARTIFACT_PATHS) <= set(row_map), "REQUIRED_ARTIFACT_PATHS")

    additional = record.get("additional_binding_paths")
    require(isinstance(additional, list), "ADDITIONAL_BINDINGS_TYPE")
    safe_additional: list[Path] = []
    for item in additional:
        relative = safe_relative(item, label="ADDITIONAL_BINDING")
        require(relative.as_posix() in row_map, f"ADDITIONAL_BINDING_UNBOUND:{relative}")
        require(row_map[relative.as_posix()]["changed"] is True, f"ADDITIONAL_BINDING_UNCHANGED:{relative}")
        require(relative.as_posix() not in OBSERVED_ARTIFACT_PATHS, f"ADDITIONAL_BINDING_NOT_EXTENSION:{relative}")
        safe_additional.append(relative)
    require(len(safe_additional) == len(set(safe_additional)), "ADDITIONAL_BINDINGS_DUPLICATE")
    require(all((root / relative).is_file() for relative in safe_additional), "ADDITIONAL_BINDING_MISSING")
    if correction:
        require(
            {SOURCE_CLOSURE_PATH, SOURCE_CLOSURE_TEST_PATH}
            <= set(safe_additional),
            "CORRECTION_SELECTOR_BINDINGS_MISSING",
        )

    receipts = record.get("test_receipts")
    require(isinstance(receipts, list) and bool(receipts), "TEST_RECEIPTS_TYPE")
    receipt_refs: dict[str, dict[str, str]] = {}
    final_count = 0
    roles: list[str] = []
    for item in receipts:
        require(
            isinstance(item, dict) and set(item) == {"path", "sha256", "role", "kind"},
            "TEST_RECEIPT_FIELDS",
        )
        relative = safe_relative(item.get("path"), label="TEST_RECEIPT")
        key = relative.as_posix()
        require(key not in receipt_refs, f"TEST_RECEIPT_DUPLICATE:{key}")
        require(item.get("role") in {"prior", "final"}, f"TEST_RECEIPT_ROLE:{key}")
        require(item.get("kind") == "pytest", f"TEST_RECEIPT_KIND:{key}")
        require(sha(root / relative) == item.get("sha256"), f"TEST_RECEIPT_HASH:{key}")
        receipt_refs[key] = {"path": relative.as_posix(), "sha256": item.get("sha256", "")}
        roles.append(item.get("role", ""))
        final_count += item.get("role") == "final"
    require(final_count == 1 and "final" in roles, "FINAL_TEST_RECEIPT")
    if receipt_paths is not None:
        require({path.resolve().relative_to(root).as_posix() for path in receipt_paths} == set(receipt_refs), "TEST_RECEIPT_SET")

    summary = record.get("fresh_test_summary")
    require(isinstance(summary, dict), "FRESH_TEST_SUMMARY_TYPE")
    aggregate = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for relative in (root / item["path"] for item in receipts):
        parsed = validate_receipt(
            load(relative),
            root=root,
            source_root=receipt_source_root,
        )
        aggregate["tests"] += parsed["junit"]["tests"]
        aggregate["failures"] += parsed["junit"]["failures"]
        aggregate["errors"] += parsed["junit"]["errors"]
        aggregate["skipped"] += parsed["junit"]["skipped"]
    require(
        aggregate["failures"] == aggregate["errors"] == aggregate["skipped"] == 0,
        "FRESH_TEST_RESULTS",
    )

    command_receipts = record.get("command_receipts")
    require(isinstance(command_receipts, list) and bool(command_receipts), "COMMAND_RECEIPTS_TYPE")
    command_keys: set[str] = set()
    for item in command_receipts:
        require(
            isinstance(item, dict) and set(item) == {"path", "sha256", "kind"},
            "COMMAND_RECEIPT_BINDING_FIELDS",
        )
        relative = safe_relative(item.get("path"), label="COMMAND_RECEIPT")
        key = relative.as_posix()
        require(key not in command_keys and key not in receipt_refs, f"RECEIPT_DUPLICATE:{key}")
        require(item.get("kind") == "frontend-tool", f"COMMAND_RECEIPT_KIND:{key}")
        require(sha(root / relative) == item.get("sha256"), f"COMMAND_RECEIPT_HASH:{key}")
        validate_command_receipt(
            load(root / relative),
            root=root,
            source_root=receipt_source_root,
        )
        command_keys.add(key)
    summary["command_receipt_count"] = len(command_receipts)
    require(
        summary
        == {
            "receipt_count": len(receipts),
            "final_receipt_count": 1,
            "command_receipt_count": len(command_receipts),
            "all_exit_codes_zero": True,
            "junit_failures": 0,
            "junit_errors": 0,
            "junit_skipped": 0,
        },
        "FRESH_TEST_SUMMARY",
    )

    bindings = record.get("current_bindings")
    require(
        bindings
        == {
            "record": record_path.as_posix(),
            "builder": BUILDER.as_posix(),
            "checker": CHECKER.as_posix(),
            "test": PACKAGE_TEST.as_posix(),
        },
        "CURRENT_BINDINGS",
    )
    require(record.get("external_effects") == "NONE_LOCAL_DETERMINISTIC_VALIDATION_ONLY", "EXTERNAL_EFFECTS")
    member_paths = [
        Path(row["path"])
        for row in manifest_members(record, root=root, record_path=record_path)
    ]
    return tuple(member_paths)


def manifest_members(
    record: dict[str, Any],
    *,
    root: Path = ROOT,
    record_path: Path = RECORD,
) -> list[dict[str, str | int]]:
    require(record_path in {RECORD, CORRECTION_RECORD}, "RECORD_PATH_UNSUPPORTED")
    required = {BUILDER, CHECKER, PACKAGE_TEST, INPUT_OBSERVATION, record_path}
    if record_path == CORRECTION_RECORD:
        required.add(PRIOR_ATTEMPT_RECORD)
        required.update(CORRECTION_FINAL_BINDING_PATHS)
    raw_source_root = record.get("predecessor", {}).get("receipt_source_root")
    require(isinstance(raw_source_root, str) and Path(raw_source_root).is_absolute(), "RECEIPT_SOURCE_ANCHOR")
    receipt_source_root = Path(raw_source_root)
    for item in record.get("test_receipts", []):
        required.add(Path(item["path"]))
        receipt = load(root / Path(item["path"]))
        for artifact in receipt.get("artifacts", []):
            _current, relative = project_receipt_artifact(
                Path(artifact["path"]),
                root=root,
                source_root=receipt_source_root,
            )
            required.add(relative)
    for item in record.get("command_receipts", []):
        required.add(Path(item["path"]))
        receipt = load(root / Path(item["path"]))
        for artifact in receipt.get("artifacts", []):
            _current, relative = project_receipt_artifact(
                Path(artifact["path"]),
                root=root,
                source_root=receipt_source_root,
            )
            required.add(relative)
    return [
        {
            "path": relative.as_posix(),
            "bytes": len(canonical(record)) if relative == record_path else (root / relative).stat().st_size,
            "sha256": hashlib.sha256(canonical(record)).hexdigest() if relative == record_path else sha(root / relative),
        }
        for relative in sorted(required, key=lambda item: item.as_posix())
    ]


def receipt_payload(
    record: dict[str, Any],
    manifest: dict[str, Any],
    *,
    record_path: Path = RECORD,
    manifest_path: Path = MANIFEST,
    root: Path = ROOT,
) -> dict[str, Any]:
    return {
        "schema_version": "mrw.stage1.stage3_v6_artifact_remediation_validation.v1",
        "status": "PASS",
        "authoritative": False,
        "record": {"path": record_path.as_posix(), "sha256": sha(root / record_path)},
        "manifest": {"path": manifest_path.as_posix(), "sha256": sha(root / manifest_path)},
        "checks": {
            "contract_and_v6_identity_bound": True,
            "input_observation_bound": True,
            "historical_v6_record_bound": True,
            "current_artifact_hashes_bound": True,
            "fresh_test_receipts_clean": True,
            "authority_false": True,
            "production_release_false": True,
        },
        "authority_ceiling": CEILING,
    }


def create(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)


def _selected_record_paths(value: Path | None) -> tuple[Path, Path, Path, bool]:
    if value is None:
        return RECORD, MANIFEST, VALIDATION, False
    require(not value.is_absolute(), "RECORD_PATH_ABSOLUTE")
    require(value.as_posix() == str(value), "RECORD_PATH_NOT_CANONICAL")
    if value == RECORD:
        return RECORD, MANIFEST, VALIDATION, False
    if value == CORRECTION_RECORD:
        return CORRECTION_RECORD, CORRECTION_MANIFEST, CORRECTION_VALIDATION, True
    raise ValueError("RECORD_PATH_UNSUPPORTED")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-receipt", action="store_true")
    parser.add_argument("--check-receipt", action="store_true")
    parser.add_argument("--record", type=Path)
    args = parser.parse_args()
    record_path, manifest_path, validation_path, _correction = _selected_record_paths(args.record)
    record = load(ROOT / record_path)
    manifest = load(ROOT / manifest_path)
    expected_paths = validate_record(record, record_path=record_path)
    validate_manifest(manifest, expected_paths=expected_paths)
    payload = canonical(
        receipt_payload(
            record,
            manifest,
            record_path=record_path,
            manifest_path=manifest_path,
        )
    )
    if args.write_receipt:
        create(ROOT / validation_path, payload)
    if args.check_receipt:
        require((ROOT / validation_path).read_bytes() == payload, "VALIDATION_DRIFT")
    if not args.write_receipt and not args.check_receipt:
        parser.error("select --write-receipt or --check-receipt")
    print(json.dumps({"status": "PASS", "authoritative": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, sort_keys=True), file=__import__("sys").stderr)
        raise SystemExit(1) from exc
