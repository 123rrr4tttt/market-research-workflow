#!/usr/bin/env python3
"""Check the correction2 successor package and its recursive member closure."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import sys
import xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[2]
HERE = Path("stage1-successor-evidence/stage3-v6-artifact-remediation-correction2")
OUTPUT_DIR = HERE / "package"
RECORD = OUTPUT_DIR / "stage3-v6-artifact-remediation-record.v1.correction2.json"
MANIFEST = OUTPUT_DIR / "artifact-manifest.v1.correction2.json"
VALIDATION = OUTPUT_DIR / "validation-receipt.v1.correction2.json"
BUILDER = HERE / "build_stage3_v6_artifact_remediation_correction2.py"
CHECKER = HERE / Path(__file__).name
PACKAGE_TEST = HERE / "test_stage3_v6_artifact_remediation_correction2.py"
ISOLATED_PYTEST_RUNNER = (
    Path("stage1-successor-evidence/stage-convergence-batch-v1")
    / "run-current-pytest-receipt-v2.py"
)
ISOLATED_RECEIPT_SCHEMA = "mrw.current-pytest-receipt.v2"
ISOLATED_BUNDLE_PARENT = (
    Path("stage1-successor-evidence/stage3-v6-artifact-remediation-v1") / "raw"
)
ISOLATED_BUNDLE_PREFIX = "current-byte-selector-intake-package-isolated-v2"
ISOLATED_TEST_TARGETS = (
    "tests/formal_release/test_source_closure.py",
    "tests/formal_release/test_stage2_candidate_intake.py",
    "stage1-successor-evidence/stage3-v6-artifact-remediation-v1/"
    "test_stage3_v6_artifact_remediation_v1.py",
)
PYTEST_CONTROL_VARIABLES = (
    "PYTEST_ADDOPTS",
    "PYTEST_PLUGINS",
    "PYTHONSTARTUP",
    "PYTHONHOME",
    "PYTHONINSPECT",
)
ISOLATED_ENVIRONMENT_KEYS = {
    "GIT_CONFIG_COUNT",
    "GIT_CONFIG_GLOBAL",
    "GIT_CONFIG_NOSYSTEM",
    "HOME",
    "LANG",
    "LC_ALL",
    "LLM_CACHE_ENABLED",
    "MRW_PYTEST_NODEIDS_PATH",
    "PATH",
    "PYTHONDONTWRITEBYTECODE",
    "PYTHONHASHSEED",
    "PYTHONNOUSERSITE",
    "PYTHONPATH",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
    "TMPDIR",
    "TZ",
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
}
REJECTED_ISOLATED_RUN_IDS = {"v2-20260908"}

CORRECTION1_DIR = Path(
    "stage1-successor-evidence/stage3-v6-artifact-remediation-v1"
)
CORRECTION1_RECORD = (
    CORRECTION1_DIR / "stage3-v6-artifact-remediation-record.v1.correction1.json"
)
CORRECTION1_MANIFEST = CORRECTION1_DIR / "artifact-manifest.v1.correction1.json"
CORRECTION1_VALIDATION = CORRECTION1_DIR / "validation-receipt.v1.correction1.json"
CORRECTION1_HASHES = {
    CORRECTION1_RECORD: "1f2eb55570ade210db34078f449215df235afcb99ffcf00e2e8238f5688567fc",
    CORRECTION1_MANIFEST: "6cb08c46f6579a553c4a26cd458eab49817896504375d3e009921dbd1cd492b6",
    CORRECTION1_VALIDATION: "1e77a1211ce73f5dc8f0291477489a1cdbb9cf29c6aefdb37e0856cf13f52bcd",
}
CEILING = (
    "NO_DEPLOY_NO_LIVE_NO_PRODUCTION_WRITE_NO_EXTERNAL_DELIVERY_NO_CANARY_"
    "NO_CUTOVER_NO_AUTHORITY_TRANSFER_NO_LEGACY_RETIREMENT_NO_PUSH_"
    "NO_REMOTE_MUTATION_NO_REGISTRY_WRITE_NO_SIGNING_WRITE"
)
RECORD_SCHEMA = "mrw.stage1.stage3_v6_artifact_remediation_correction2_record.v1"
MANIFEST_SCHEMA = "mrw.stage1.stage3_v6_artifact_remediation_correction2_manifest.v1"
VALIDATION_SCHEMA = "mrw.stage1.stage3_v6_artifact_remediation_correction2_validation.v1"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def canonical(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative(value: object, *, label: str) -> Path:
    require(isinstance(value, str) and bool(value), f"{label}_TYPE")
    path = Path(value)
    require(not path.is_absolute(), f"{label}_ABSOLUTE:{value}")
    require(path.as_posix() == value, f"{label}_NOT_CANONICAL:{value}")
    require(".." not in path.parts and "." not in path.parts, f"{label}_TRAVERSAL:{value}")
    return path


def regular_file(path: Path, *, label: str) -> None:
    metadata = path.lstat()
    require(stat.S_ISREG(metadata.st_mode), f"{label}_TYPE:{path}")


def load(path: Path) -> dict[str, Any]:
    regular_file(path, label="JSON")
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON_ROOT:{path}")
    return value


def member(path: Path, *, root: Path = ROOT) -> dict[str, str | int]:
    current = root / path
    regular_file(current, label="MEMBER")
    return {
        "path": path.as_posix(),
        "bytes": current.stat().st_size,
        "sha256": sha(current),
    }


def validate_declared_member(
    row: object,
    *,
    root: Path,
    label: str,
) -> tuple[Path, dict[str, str | int]]:
    require(
        isinstance(row, dict) and set(row) == {"path", "bytes", "sha256"},
        f"{label}_FIELDS",
    )
    relative = safe_relative(row.get("path"), label=f"{label}_PATH")
    expected_bytes = row.get("bytes")
    expected_hash = row.get("sha256")
    require(isinstance(expected_bytes, int) and expected_bytes >= 0, f"{label}_BYTES")
    require(
        isinstance(expected_hash, str) and len(expected_hash) == 64,
        f"{label}_SHA256",
    )
    actual = member(relative, root=root)
    require(actual["bytes"] == expected_bytes, f"{label}_BYTE_DRIFT:{relative}")
    require(actual["sha256"] == expected_hash, f"{label}_HASH_DRIFT:{relative}")
    return relative, actual


def validate_correction1_inputs(
    *,
    root: Path = ROOT,
    record: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
    validation: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    for relative, expected_hash in CORRECTION1_HASHES.items():
        regular_file(root / relative, label="CORRECTION1")
        require(sha(root / relative) == expected_hash, f"CORRECTION1_HASH_DRIFT:{relative}")
    record = record if record is not None else load(root / CORRECTION1_RECORD)
    manifest = manifest if manifest is not None else load(root / CORRECTION1_MANIFEST)
    validation = validation if validation is not None else load(root / CORRECTION1_VALIDATION)
    require(record.get("authoritative") is False, "CORRECTION1_RECORD_AUTHORITY")
    require(
        record.get("production_release_authorized") is False,
        "CORRECTION1_RECORD_RELEASE",
    )
    require(record.get("authority_ceiling") == CEILING, "CORRECTION1_RECORD_CEILING")
    require(manifest.get("authoritative") is False, "CORRECTION1_MANIFEST_AUTHORITY")
    require(manifest.get("authority_ceiling") == CEILING, "CORRECTION1_MANIFEST_CEILING")
    require(validation.get("authoritative") is False, "CORRECTION1_VALIDATION_AUTHORITY")
    require(validation.get("authority_ceiling") == CEILING, "CORRECTION1_VALIDATION_CEILING")
    return record, manifest, validation


def _merge(
    closure: dict[str, dict[str, str | int]],
    row: dict[str, str | int],
    *,
    label: str,
) -> bool:
    key = str(row["path"])
    prior = closure.get(key)
    require(prior is None or prior == row, f"MEMBER_DECLARATION_CONFLICT:{label}:{key}")
    if prior is not None:
        return False
    closure[key] = row
    return True


def _is_artifact_manifest(path: Path, payload: dict[str, Any]) -> bool:
    return (
        path.suffix == ".json"
        and path.name.startswith("artifact-manifest")
        and "members" in payload
        and "member_count" in payload
    )


def _receipt_artifact_relative(
    value: object,
    *,
    receipt_source_root: Path,
    label: str,
) -> Path:
    require(isinstance(value, str) and bool(value), f"{label}_PATH_TYPE")
    path = Path(value)
    require(path.is_absolute(), f"{label}_PATH_NOT_ABSOLUTE")
    try:
        relative = path.relative_to(receipt_source_root)
    except ValueError as exc:
        raise ValueError(f"{label}_PATH_OUTSIDE_SOURCE_ROOT:{path}") from exc
    return safe_relative(relative.as_posix(), label=f"{label}_PROJECTED_PATH")


def normalize_repo_input_path(value: Path, *, root: Path, label: str) -> Path:
    if value.is_absolute():
        try:
            value = value.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"{label}_OUTSIDE_ROOT:{value}") from exc
    return safe_relative(value.as_posix(), label=label)


def _junit_counts(path: Path) -> dict[str, int]:
    document = ET.parse(path).getroot()
    if document.tag == "testsuite":
        suites = [document]
    elif document.tag == "testsuites":
        suites = list(document.findall("testsuite"))
    else:
        raise ValueError("ISOLATED_JUNIT_ROOT")
    require(bool(suites), "ISOLATED_JUNIT_EMPTY")
    suite = {
        field: sum(int(item.attrib.get(field, "0")) for item in suites)
        for field in ("tests", "failures", "errors", "skipped")
    }
    testcases = list(document.iter("testcase"))
    derived = {
        "tests": len(testcases),
        "failures": sum(bool(item.findall("failure")) for item in testcases),
        "errors": sum(bool(item.findall("error")) for item in testcases),
        "skipped": sum(bool(item.findall("skipped")) for item in testcases),
    }
    require(suite == derived, "ISOLATED_JUNIT_INCONSISTENT")
    return {
        **derived,
        "passed": derived["tests"]
        - derived["failures"]
        - derived["errors"]
        - derived["skipped"],
    }


def validate_isolated_pytest_receipt(
    receipt_path: Path,
    *,
    expected_count: int,
    root: Path = ROOT,
    bundle_parent: Path = ISOLATED_BUNDLE_PARENT,
) -> tuple[dict[str, Any], list[dict[str, str | int]]]:
    require(isinstance(expected_count, int) and expected_count > 0, "ISOLATED_EXPECTED_COUNT")
    relative = normalize_repo_input_path(receipt_path, root=root, label="ISOLATED_RECEIPT_PATH")
    require(relative.name == "receipt.json", "ISOLATED_RECEIPT_NAME")
    receipt = load(root / relative)
    require(receipt.get("schema") == ISOLATED_RECEIPT_SCHEMA, "ISOLATED_RECEIPT_SCHEMA")
    require(receipt.get("status") == f"PASS_COMPLETE_EXACT_{expected_count}", "ISOLATED_RECEIPT_STATUS")
    require(receipt.get("authoritative") is False, "ISOLATED_RECEIPT_AUTHORITY")
    require(
        receipt.get("authority")
        == {
            "candidate_promotion": False,
            "production_release": False,
            "deployment": False,
            "live_write": False,
        },
        "ISOLATED_RECEIPT_AUTHORITY_MAP",
    )
    require(receipt.get("expected_count") == expected_count, "ISOLATED_RECEIPT_EXPECTED_COUNT")
    run_id = receipt.get("run_id")
    require(isinstance(run_id, str) and bool(run_id), "ISOLATED_RECEIPT_RUN_ID")
    require(run_id not in REJECTED_ISOLATED_RUN_IDS, "ISOLATED_RECEIPT_HISTORICAL_RUN_REJECTED")
    require(relative.parent.parent == bundle_parent, "ISOLATED_RECEIPT_PARENT")
    require(
        relative.parent.name == f"{ISOLATED_BUNDLE_PREFIX}-{run_id}",
        "ISOLATED_RECEIPT_BUNDLE_NAME",
    )
    bundle = receipt.get("bundle")
    require(isinstance(bundle, str) and Path(bundle).is_absolute(), "ISOLATED_RECEIPT_BUNDLE")
    require(Path(bundle).resolve() == (root / relative.parent).resolve(), "ISOLATED_RECEIPT_BUNDLE_PATH")

    execution = receipt.get("execution")
    require(isinstance(execution, dict), "ISOLATED_EXECUTION")
    require(execution.get("cwd") == root.as_posix(), "ISOLATED_EXECUTION_CWD")
    require(execution.get("process_exit_code") == 0, "ISOLATED_EXECUTION_EXIT")
    require(execution.get("execution_error") is None, "ISOLATED_EXECUTION_ERROR")
    argv = execution.get("argv")
    require(isinstance(argv, list) and all(isinstance(item, str) for item in argv), "ISOLATED_ARGV")
    require(len(argv) == 12, "ISOLATED_ARGV_COUNT")
    require(Path(argv[0]).is_absolute(), "ISOLATED_PYTHON_PATH")
    require(
        argv[1:8]
        == [
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-p",
            "mrw_pytest_receipt_plugin_v2",
            "-q",
        ],
        "ISOLATED_ARGV_PREFIX",
    )
    require(tuple(argv[8:11]) == ISOLATED_TEST_TARGETS, "ISOLATED_TEST_TARGETS")
    require(argv[11].startswith("--junitxml=") and Path(argv[11].split("=", 1)[1]).is_absolute(), "ISOLATED_JUNIT_ARG")

    environment = receipt.get("environment")
    require(isinstance(environment, dict), "ISOLATED_ENVIRONMENT")
    require(environment.get("inherit_ambient") is False, "ISOLATED_AMBIENT_ENV")
    allowlisted = environment.get("allowlisted")
    require(isinstance(allowlisted, dict), "ISOLATED_ALLOWLIST")
    require(not (set(PYTEST_CONTROL_VARIABLES) & set(allowlisted)), "ISOLATED_FORBIDDEN_ENV_PRESENT")
    require(set(allowlisted) == ISOLATED_ENVIRONMENT_KEYS, "ISOLATED_ALLOWLIST_KEYS")
    require(all(isinstance(key, str) and isinstance(value, str) for key, value in allowlisted.items()), "ISOLATED_ALLOWLIST_VALUES")
    require(environment.get("explicitly_not_inherited") == list(PYTEST_CONTROL_VARIABLES), "ISOLATED_FORBIDDEN_ENV_LIST")
    require(allowlisted.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD") == "1", "ISOLATED_PLUGIN_AUTOLOAD")
    require(allowlisted.get("PYTHONNOUSERSITE") == "1", "ISOLATED_USER_SITE")
    require(allowlisted.get("PYTHONDONTWRITEBYTECODE") == "1", "ISOLATED_BYTECODE")
    require(allowlisted.get("PATH") == "/usr/bin:/bin:/usr/sbin:/sbin", "ISOLATED_PATH")
    require(allowlisted.get("GIT_CONFIG_COUNT") == "0", "ISOLATED_GIT_CONFIG_COUNT")
    require(allowlisted.get("GIT_CONFIG_GLOBAL") == "/dev/null", "ISOLATED_GIT_CONFIG_GLOBAL")
    require(allowlisted.get("GIT_CONFIG_NOSYSTEM") == "1", "ISOLATED_GIT_CONFIG_SYSTEM")

    inputs = receipt.get("inputs")
    require(isinstance(inputs, dict), "ISOLATED_INPUTS")
    before = inputs.get("before")
    after = inputs.get("after")
    require(before == after, "ISOLATED_INPUT_HASH_DRIFT")
    require(inputs.get("unchanged_during_run") is True, "ISOLATED_INPUT_UNCHANGED")
    require(inputs.get("after_error") is None, "ISOLATED_INPUT_AFTER_ERROR")
    require(isinstance(before, list) and len(before) == len(ISOLATED_TEST_TARGETS), "ISOLATED_INPUT_COUNT")
    require([row.get("path") for row in before] == list(ISOLATED_TEST_TARGETS), "ISOLATED_INPUT_PATHS")
    for row in before:
        require(isinstance(row, dict) and set(row) == {"path", "sha256", "size_bytes"}, "ISOLATED_INPUT_FIELDS")
        input_path = safe_relative(row["path"], label="ISOLATED_INPUT_PATH")
        actual = member(input_path, root=root)
        require(actual["sha256"] == row["sha256"], f"ISOLATED_INPUT_HASH:{input_path}")
        require(actual["bytes"] == row["size_bytes"], f"ISOLATED_INPUT_BYTES:{input_path}")

    expected = {
        "collected": expected_count,
        "passed": expected_count,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
    }
    results = receipt.get("results")
    require(isinstance(results, dict), "ISOLATED_RESULTS")
    require(results.get("expected") == expected, "ISOLATED_RESULTS_EXPECTED")
    require(results.get("observed") == expected, "ISOLATED_RESULTS_OBSERVED")
    require(
        results.get("junit_suite_attributes")
        == {
            "tests": expected_count,
            "failures": 0,
            "errors": 0,
            "skipped": 0,
        },
        "ISOLATED_JUNIT_SUITE_COUNTS",
    )
    require(
        results.get("junit_testcase_derived")
        == {
            "tests": expected_count,
            "failures": 0,
            "errors": 0,
            "skipped": 0,
            "passed": expected_count,
        },
        "ISOLATED_JUNIT_TESTCASE_COUNTS",
    )
    require(results.get("junit_counts_consistent") is True, "ISOLATED_JUNIT_RECEIPT_CONSISTENCY")
    require(results.get("junit_error") is None, "ISOLATED_JUNIT_RECEIPT_ERROR")
    require(results.get("nodeids_error") is None, "ISOLATED_NODEIDS_ERROR")
    nodeids = results.get("nodeids")
    require(isinstance(nodeids, list) and all(isinstance(item, str) and item for item in nodeids), "ISOLATED_NODEIDS")
    require(len(nodeids) == expected_count, "ISOLATED_NODEID_COUNT")
    require(nodeids == sorted(nodeids), "ISOLATED_NODEID_ORDER")
    require(len(nodeids) == len(set(nodeids)), "ISOLATED_NODEID_UNIQUE")
    require(results.get("nodeids_unique") is True, "ISOLATED_NODEID_UNIQUE_FLAG")
    require(
        results.get("nodeids_normalization") == "sorted UTF-8 RFC8259 JSON with no whitespace",
        "ISOLATED_NODEID_NORMALIZATION",
    )
    require(results.get("nodeids_sha256") == sha_bytes(json.dumps(nodeids, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")), "ISOLATED_NODEID_HASH")

    artifact_rows = receipt.get("artifacts")
    require(isinstance(artifact_rows, list) and len(artifact_rows) == 4, "ISOLATED_ARTIFACTS")
    expected_names = ["pytest.log", "pytest.junit.xml", "nodeids.json", "mrw_pytest_receipt_plugin_v2.py"]
    require([Path(row.get("path", "")).name for row in artifact_rows] == expected_names, "ISOLATED_ARTIFACT_NAMES")
    members = [member(ISOLATED_PYTEST_RUNNER, root=root), member(relative, root=root)]
    artifacts_by_name: dict[str, Path] = {}
    for row in artifact_rows:
        require(isinstance(row, dict) and set(row) == {"path", "present", "sha256", "size_bytes"}, "ISOLATED_ARTIFACT_FIELDS")
        require(row.get("present") is True, "ISOLATED_ARTIFACT_PRESENT")
        absolute = Path(row["path"])
        require(absolute.is_absolute() and absolute.parent.resolve() == Path(bundle).resolve(), "ISOLATED_ARTIFACT_PATH")
        projected = normalize_repo_input_path(absolute, root=root, label="ISOLATED_ARTIFACT_PROJECTED")
        actual = member(projected, root=root)
        require(actual["sha256"] == row["sha256"], f"ISOLATED_ARTIFACT_HASH:{projected}")
        require(actual["bytes"] == row["size_bytes"], f"ISOLATED_ARTIFACT_BYTES:{projected}")
        members.append(actual)
        artifacts_by_name[absolute.name] = root / projected
    nodeids_payload = json.loads(artifacts_by_name["nodeids.json"].read_text(encoding="utf-8"))
    require(
        isinstance(nodeids_payload, list)
        and all(isinstance(item, str) for item in nodeids_payload)
        and sorted(nodeids_payload) == nodeids,
        "ISOLATED_NODEID_ARTIFACT_CONTENT",
    )
    junit_counts = _junit_counts(artifacts_by_name["pytest.junit.xml"])
    require(junit_counts == {"tests": expected_count, "failures": 0, "errors": 0, "skipped": 0, "passed": expected_count}, "ISOLATED_JUNIT_COUNTS")
    cleanup = receipt.get("cleanup")
    require(cleanup == {"runtime_directory_removed_before_publish": True, "error": None}, "ISOLATED_CLEANUP")
    binding = {
        "path": relative.as_posix(),
        "sha256": sha(root / relative),
        "run_id": run_id,
        "expected_count": expected_count,
        "status": receipt["status"],
        "runner": {
            "path": ISOLATED_PYTEST_RUNNER.as_posix(),
            "sha256": sha(root / ISOLATED_PYTEST_RUNNER),
        },
    }
    return binding, members


def collect_member_closure(
    correction1_record: dict[str, Any],
    correction1_manifest: dict[str, Any],
    *,
    isolated_receipt_path: Path,
    isolated_expected_count: int,
    isolated_bundle_parent: Path = ISOLATED_BUNDLE_PARENT,
    root: Path = ROOT,
) -> tuple[
    list[dict[str, str | int]],
    tuple[Path, ...],
    list[dict[str, Any]],
    dict[str, Any],
]:
    """Return the verified union and recursively expand every artifact manifest."""
    closure: dict[str, dict[str, str | int]] = {}
    queue: deque[Path] = deque()
    expanded: list[Path] = []
    predecessor_declarations: dict[str, dict[str, Any]] = {}

    def add_actual(
        relative: Path,
        expected_hash: str | None = None,
        *,
        label: str,
        enqueue: bool = True,
    ) -> None:
        actual = member(relative, root=root)
        if expected_hash is not None:
            require(actual["sha256"] == expected_hash, f"{label}_HASH_DRIFT:{relative}")
        if _merge(closure, actual, label=label) and enqueue:
            queue.append(relative)

    for relative, expected_hash in CORRECTION1_HASHES.items():
        add_actual(
            relative,
            expected_hash,
            label="CORRECTION1_TRIO",
            enqueue=relative != CORRECTION1_MANIFEST,
        )

    artifact_rows = correction1_record.get("artifact_paths")
    require(isinstance(artifact_rows, list) and bool(artifact_rows), "ARTIFACT_PATHS")
    artifact_seen: set[str] = set()
    for row in artifact_rows:
        require(isinstance(row, dict), "ARTIFACT_PATH_ROW")
        relative = safe_relative(row.get("path"), label="ARTIFACT_PATH")
        key = relative.as_posix()
        require(key not in artifact_seen, f"ARTIFACT_PATH_DUPLICATE:{key}")
        artifact_seen.add(key)
        expected_hash = row.get("current_sha256")
        require(isinstance(expected_hash, str) and len(expected_hash) == 64, "ARTIFACT_PATH_HASH")
        predecessor_declarations.setdefault(key, {})["artifact_path_sha256"] = expected_hash
        add_actual(relative, label="ARTIFACT_PATH")

    manifest_rows = correction1_manifest.get("members")
    require(isinstance(manifest_rows, list) and bool(manifest_rows), "CORRECTION1_MEMBERS")
    require(
        correction1_manifest.get("member_count") == len(manifest_rows),
        "CORRECTION1_MEMBER_COUNT",
    )
    for row in manifest_rows:
        require(
            isinstance(row, dict) and set(row) == {"path", "bytes", "sha256"},
            "CORRECTION1_MEMBER_FIELDS",
        )
        relative = safe_relative(row.get("path"), label="CORRECTION1_MEMBER_PATH")
        expected_bytes = row.get("bytes")
        expected_hash = row.get("sha256")
        require(isinstance(expected_bytes, int) and expected_bytes >= 0, "CORRECTION1_MEMBER_BYTES")
        require(isinstance(expected_hash, str) and len(expected_hash) == 64, "CORRECTION1_MEMBER_SHA256")
        declaration = predecessor_declarations.setdefault(relative.as_posix(), {})
        declaration["manifest_bytes"] = expected_bytes
        declaration["manifest_sha256"] = expected_hash
        add_actual(relative, label="CORRECTION1_MEMBER")

    source_value = correction1_record.get("predecessor", {}).get("receipt_source_root")
    require(isinstance(source_value, str), "RECEIPT_SOURCE_ROOT_TYPE")
    receipt_source_root = Path(source_value)
    require(receipt_source_root.is_absolute(), "RECEIPT_SOURCE_ROOT_ABSOLUTE")
    for field in ("test_receipts", "command_receipts"):
        receipt_refs = correction1_record.get(field)
        require(isinstance(receipt_refs, list) and bool(receipt_refs), f"{field.upper()}_TYPE")
        for receipt_ref in receipt_refs:
            require(isinstance(receipt_ref, dict), f"{field.upper()}_ROW")
            relative = safe_relative(receipt_ref.get("path"), label=f"{field.upper()}_PATH")
            expected_hash = receipt_ref.get("sha256")
            require(isinstance(expected_hash, str) and len(expected_hash) == 64, f"{field.upper()}_HASH")
            add_actual(relative, expected_hash, label=field.upper())
            receipt = load(root / relative)
            artifacts = receipt.get("artifacts")
            require(isinstance(artifacts, list) and bool(artifacts), f"{field.upper()}_ARTIFACTS")
            for artifact in artifacts:
                require(isinstance(artifact, dict), f"{field.upper()}_ARTIFACT_ROW")
                projected = _receipt_artifact_relative(
                    artifact.get("path"),
                    receipt_source_root=receipt_source_root,
                    label=field.upper(),
                )
                expected_artifact_hash = artifact.get("sha256")
                require(
                    isinstance(expected_artifact_hash, str)
                    and len(expected_artifact_hash) == 64,
                    f"{field.upper()}_ARTIFACT_HASH",
                )
                add_actual(projected, expected_artifact_hash, label=f"{field.upper()}_ARTIFACT")

    isolated_binding, isolated_members = validate_isolated_pytest_receipt(
        isolated_receipt_path,
        expected_count=isolated_expected_count,
        root=root,
        bundle_parent=isolated_bundle_parent,
    )
    for isolated_member in isolated_members:
        relative = safe_relative(
            isolated_member["path"],
            label="ISOLATED_CLOSURE_MEMBER",
        )
        if _merge(closure, isolated_member, label="ISOLATED_CLOSURE_MEMBER"):
            queue.append(relative)

    visited: set[Path] = set()
    while queue:
        relative = queue.popleft()
        if relative in visited:
            continue
        visited.add(relative)
        if relative.suffix != ".json" or not relative.name.startswith("artifact-manifest"):
            continue
        payload = load(root / relative)
        if not _is_artifact_manifest(relative, payload):
            continue
        declaration = predecessor_declarations.get(relative.as_posix(), {})
        expected_hashes = {
            value
            for key, value in declaration.items()
            if key.endswith("sha256")
        }
        require(bool(expected_hashes), f"NESTED_MANIFEST_UNDECLARED:{relative}")
        require(len(expected_hashes) == 1, f"NESTED_MANIFEST_DECLARATION_CONFLICT:{relative}")
        require(
            sha(root / relative) == next(iter(expected_hashes)),
            f"NESTED_MANIFEST_SELF_HASH_DRIFT:{relative}",
        )
        members = payload.get("members")
        require(isinstance(members, list) and bool(members), f"NESTED_MANIFEST_MEMBERS:{relative}")
        require(payload.get("member_count") == len(members), f"NESTED_MANIFEST_COUNT:{relative}")
        expanded.append(relative)
        for row in members:
            child, actual = validate_declared_member(
                row,
                root=root,
                label=f"NESTED_MANIFEST:{relative}",
            )
            if _merge(closure, actual, label=f"NESTED_MANIFEST:{relative}"):
                queue.append(child)

    drifts: list[dict[str, Any]] = []
    for key in sorted(predecessor_declarations):
        current = closure[key]
        declaration = predecessor_declarations[key]
        artifact_sha = declaration.get("artifact_path_sha256")
        manifest_sha = declaration.get("manifest_sha256")
        manifest_bytes = declaration.get("manifest_bytes")
        changed = (
            (artifact_sha is not None and artifact_sha != current["sha256"])
            or (manifest_sha is not None and manifest_sha != current["sha256"])
            or (manifest_bytes is not None and manifest_bytes != current["bytes"])
        )
        if changed:
            drifts.append(
                {
                    "path": key,
                    "correction1_artifact_path_sha256": artifact_sha,
                    "correction1_manifest_bytes": manifest_bytes,
                    "correction1_manifest_sha256": manifest_sha,
                    "current_bytes": current["bytes"],
                    "current_sha256": current["sha256"],
                    "changed": True,
                }
            )
    rows = [closure[key] for key in sorted(closure)]
    return (
        rows,
        tuple(sorted(expanded, key=lambda item: item.as_posix())),
        drifts,
        isolated_binding,
    )


def predecessor_refs() -> list[dict[str, str]]:
    return [
        {"path": relative.as_posix(), "sha256": expected_hash}
        for relative, expected_hash in CORRECTION1_HASHES.items()
    ]


def expected_record(
    correction1_record: dict[str, Any],
    correction1_manifest: dict[str, Any],
    closure: list[dict[str, str | int]],
    expanded: Iterable[Path],
    predecessor_drifts: list[dict[str, Any]],
    isolated_binding: dict[str, Any],
) -> dict[str, Any]:
    artifact_paths = correction1_record["artifact_paths"]
    manifest_members = correction1_manifest["members"]
    return {
        "schema_version": RECORD_SCHEMA,
        "status": "PASS_COMPLETE_MEMBER_CLOSURE_NOT_AUTHORITY",
        "authoritative": False,
        "production_release_authorized": False,
        "production_release_status": "PRODUCTION_RELEASE_NOT_AUTHORIZED",
        "authority_ceiling": CEILING,
        "predecessor_correction1": predecessor_refs(),
        "isolated_pytest_receipt": isolated_binding,
        "correction": {
            "attempt": 2,
            "reason": "CORRECTION1_MANIFEST_INCOMPLETE_STRUCTURAL_CLOSURE",
            "historical_predecessor_status": (
                "CORRECTION1_PASS_RETAINED_AS_HISTORICAL_ONLY_AND_LIMITED_BY_THIS_SUCCESSOR"
            ),
            "policy": (
                "CORRECTION1_ARTIFACT_PATHS_PLUS_MANIFEST_MEMBERS_PLUS_RECEIPT_ARTIFACTS_"
                "PLUS_RECURSIVE_ARTIFACT_MANIFEST_MEMBERS"
            ),
        },
        "closure": {
            "correction1_artifact_path_count": len(artifact_paths),
            "correction1_manifest_member_count": len(manifest_members),
            "test_receipt_count": len(correction1_record["test_receipts"]),
            "command_receipt_count": len(correction1_record["command_receipts"]),
            "member_count": len(closure),
            "recursive_artifact_manifests": [path.as_posix() for path in expanded],
            "predecessor_declaration_drift_count": len(predecessor_drifts),
            "predecessor_declaration_drifts": predecessor_drifts,
            "nested_declared_hashes_and_bytes_verified": True,
            "direct_predecessor_paths_rebound_to_current_bytes": True,
        },
        "current_bindings": {
            "record": RECORD.as_posix(),
            "manifest": MANIFEST.as_posix(),
            "validation": VALIDATION.as_posix(),
            "builder": BUILDER.as_posix(),
            "checker": CHECKER.as_posix(),
            "test": PACKAGE_TEST.as_posix(),
        },
        "external_effects": "NONE_LOCAL_DETERMINISTIC_VALIDATION_ONLY",
    }


def expected_manifest(
    record: dict[str, Any],
    closure: list[dict[str, str | int]],
    *,
    root: Path = ROOT,
) -> dict[str, Any]:
    rows = {str(row["path"]): dict(row) for row in closure}
    for relative in (BUILDER, CHECKER, PACKAGE_TEST):
        _merge(rows, member(relative, root=root), label="CORRECTION2_CODE")
    record_bytes = canonical(record)
    _merge(
        rows,
        {
            "path": RECORD.as_posix(),
            "bytes": len(record_bytes),
            "sha256": sha_bytes(record_bytes),
        },
        label="CORRECTION2_RECORD",
    )
    members = [rows[key] for key in sorted(rows)]
    return {
        "schema_version": MANIFEST_SCHEMA,
        "status": "COMPLETE_NOT_AUTHORITY",
        "authoritative": False,
        "production_release_authorized": False,
        "production_release_status": "PRODUCTION_RELEASE_NOT_AUTHORIZED",
        "authority_ceiling": CEILING,
        "member_count": len(members),
        "members": members,
    }


def expected_validation(record: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": VALIDATION_SCHEMA,
        "status": "PASS_NOT_AUTHORITY",
        "authoritative": False,
        "production_release_authorized": False,
        "production_release_status": "PRODUCTION_RELEASE_NOT_AUTHORIZED",
        "authority_ceiling": CEILING,
        "record": {"path": RECORD.as_posix(), "sha256": sha_bytes(canonical(record))},
        "manifest": {"path": MANIFEST.as_posix(), "sha256": sha_bytes(canonical(manifest))},
        "predecessor_correction1": predecessor_refs(),
        "checks": {
            "correction1_trio_fixed_hashes": True,
            "artifact_paths_complete": True,
            "correction1_manifest_members_complete": True,
            "receipt_artifacts_complete": True,
            "recursive_artifact_manifest_members_complete": True,
            "nested_declared_bytes_and_hashes_verified": True,
            "authority_false": True,
            "production_release_not_authorized": True,
            "create_only_atomic_bundle": True,
        },
    }


def validate_record(record: dict[str, Any], expected: dict[str, Any]) -> None:
    require(record.get("schema_version") == RECORD_SCHEMA, "RECORD_SCHEMA")
    require(record.get("status") == "PASS_COMPLETE_MEMBER_CLOSURE_NOT_AUTHORITY", "RECORD_STATUS")
    require(record.get("authoritative") is False, "RECORD_AUTHORITY")
    require(record.get("production_release_authorized") is False, "RECORD_RELEASE")
    require(
        record.get("production_release_status") == "PRODUCTION_RELEASE_NOT_AUTHORIZED",
        "RECORD_RELEASE_STATUS",
    )
    require(record.get("authority_ceiling") == CEILING, "RECORD_CEILING")
    require(record == expected, "RECORD_DRIFT")


def validate_manifest(
    manifest: dict[str, Any],
    expected: dict[str, Any],
    *,
    root: Path = ROOT,
    virtual_files: Mapping[Path, bytes] | None = None,
) -> None:
    require(manifest.get("schema_version") == MANIFEST_SCHEMA, "MANIFEST_SCHEMA")
    require(manifest.get("status") == "COMPLETE_NOT_AUTHORITY", "MANIFEST_STATUS")
    require(manifest.get("authoritative") is False, "MANIFEST_AUTHORITY")
    require(manifest.get("production_release_authorized") is False, "MANIFEST_RELEASE")
    require(
        manifest.get("production_release_status") == "PRODUCTION_RELEASE_NOT_AUTHORIZED",
        "MANIFEST_RELEASE_STATUS",
    )
    require(manifest.get("authority_ceiling") == CEILING, "MANIFEST_CEILING")
    require(manifest == expected, "MANIFEST_DRIFT")
    members = manifest.get("members")
    require(isinstance(members, list), "MANIFEST_MEMBERS")
    require(manifest.get("member_count") == len(members), "MANIFEST_MEMBER_COUNT")
    require([row["path"] for row in members] == sorted(row["path"] for row in members), "MANIFEST_ORDER")
    virtual_files = virtual_files or {}
    for row in members:
        relative = safe_relative(row.get("path"), label="MANIFEST_MEMBER_PATH")
        if relative in virtual_files:
            content = virtual_files[relative]
            require(len(content) == row.get("bytes"), f"MANIFEST_MEMBER_BYTE_DRIFT:{relative}")
            require(sha_bytes(content) == row.get("sha256"), f"MANIFEST_MEMBER_HASH_DRIFT:{relative}")
        else:
            validate_declared_member(row, root=root, label="MANIFEST_MEMBER")


def validate_validation(
    validation: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    require(validation.get("schema_version") == VALIDATION_SCHEMA, "VALIDATION_SCHEMA")
    require(validation.get("status") == "PASS_NOT_AUTHORITY", "VALIDATION_STATUS")
    require(validation.get("authoritative") is False, "VALIDATION_AUTHORITY")
    require(validation.get("production_release_authorized") is False, "VALIDATION_RELEASE")
    require(
        validation.get("production_release_status") == "PRODUCTION_RELEASE_NOT_AUTHORIZED",
        "VALIDATION_RELEASE_STATUS",
    )
    require(validation.get("authority_ceiling") == CEILING, "VALIDATION_CEILING")
    require(validation == expected, "VALIDATION_DRIFT")


def build_expected_payloads(
    *,
    isolated_receipt_path: Path,
    isolated_expected_count: int,
    isolated_bundle_parent: Path = ISOLATED_BUNDLE_PARENT,
    root: Path = ROOT,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    correction1_record, correction1_manifest, _validation = validate_correction1_inputs(root=root)
    closure, expanded, predecessor_drifts, isolated_binding = collect_member_closure(
        correction1_record,
        correction1_manifest,
        isolated_receipt_path=isolated_receipt_path,
        isolated_expected_count=isolated_expected_count,
        isolated_bundle_parent=isolated_bundle_parent,
        root=root,
    )
    record = expected_record(
        correction1_record,
        correction1_manifest,
        closure,
        expanded,
        predecessor_drifts,
        isolated_binding,
    )
    manifest = expected_manifest(record, closure, root=root)
    validation = expected_validation(record, manifest)
    validate_record(record, record)
    validate_manifest(
        manifest,
        manifest,
        root=root,
        virtual_files={RECORD: canonical(record)},
    )
    validate_validation(validation, validation)
    return record, manifest, validation


def check_package(
    *,
    isolated_receipt_path: Path,
    isolated_expected_count: int,
    root: Path = ROOT,
) -> dict[str, int | str | bool]:
    expected_record_payload, expected_manifest_payload, expected_validation_payload = (
        build_expected_payloads(
            isolated_receipt_path=isolated_receipt_path,
            isolated_expected_count=isolated_expected_count,
            root=root,
        )
    )
    record = load(root / RECORD)
    manifest = load(root / MANIFEST)
    validation = load(root / VALIDATION)
    validate_record(record, expected_record_payload)
    validate_manifest(manifest, expected_manifest_payload, root=root)
    validate_validation(validation, expected_validation_payload)
    return {
        "status": "PASS_NOT_AUTHORITY",
        "authoritative": False,
        "production_release_authorized": False,
        "member_count": manifest["member_count"],
        "recursive_artifact_manifest_count": len(
            record["closure"]["recursive_artifact_manifests"]
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--isolated-pytest-receipt", required=True, type=Path)
    parser.add_argument("--expected-count", required=True, type=int)
    args = parser.parse_args(argv)
    if not args.check:
        parser.error("select --check")
    print(
        json.dumps(
            check_package(
                isolated_receipt_path=args.isolated_pytest_receipt,
                isolated_expected_count=args.expected_count,
            ),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        raise SystemExit(1) from exc
