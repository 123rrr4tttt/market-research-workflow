#!/usr/bin/env python3
"""Run the focused current-byte pytest suite in an allowlisted environment."""

# ruff: noqa: TRY003

from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import errno
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "stage1-successor-evidence/stage3-v6-artifact-remediation-v1/raw"
STEM_PREFIX = "current-byte-selector-intake-package-isolated-v2"
TESTS = (
    "tests/formal_release/test_source_closure.py",
    "tests/formal_release/test_stage2_candidate_intake.py",
    "stage1-successor-evidence/stage3-v6-artifact-remediation-v1/"
    "test_stage3_v6_artifact_remediation_v1.py",
)
RUN_ID_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
CONTROL_ENVIRONMENT_VARIABLES = (
    "PYTEST_ADDOPTS",
    "PYTEST_PLUGINS",
    "PYTHONSTARTUP",
    "PYTHONHOME",
    "PYTHONINSPECT",
)
PLUGIN_NAME = "mrw_pytest_receipt_plugin_v2"
PLUGIN_SOURCE = '''"""Capture the exact nodeids collected by the receipt run."""
import json
import os
from pathlib import Path


def pytest_collection_finish(session):
    output = Path(os.environ["MRW_PYTEST_NODEIDS_PATH"])
    output.write_text(
        json.dumps([item.nodeid for item in session.items], ensure_ascii=True) + "\\n",
        encoding="utf-8",
    )
'''


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def run_id(value: str) -> str:
    if len(value) > 64 or RUN_ID_PATTERN.fullmatch(value) is None:
        raise argparse.ArgumentTypeError(
            "run-id must be a lowercase alphanumeric slug with single hyphen separators (max 64 chars)"
        )
    return value


def expected_count(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected-count must be a positive integer") from error
    if parsed <= 0:
        raise argparse.ArgumentTypeError("expected-count must be a positive integer")
    return parsed


def bundle_for_run(value: str) -> Path:
    return RAW / f"{STEM_PREFIX}-{value}"


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def write_exclusive(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)


def lexists(path: Path) -> bool:
    return os.path.lexists(path)


def publish_directory_exclusive(source: Path, destination: Path) -> None:
    """Atomically rename a directory while refusing any existing destination."""
    libc = ctypes.CDLL(None, use_errno=True)
    source_bytes = os.fsencode(source)
    destination_bytes = os.fsencode(destination)

    if sys.platform == "darwin":
        function = libc.renameatx_np
        function.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        )
        function.restype = ctypes.c_int
        result = function(-2, source_bytes, -2, destination_bytes, 0x00000004)
    elif sys.platform.startswith("linux"):
        function = libc.renameat2
        function.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        )
        function.restype = ctypes.c_int
        result = function(-100, source_bytes, -100, destination_bytes, 0x00000001)
    else:
        raise OSError(errno.ENOTSUP, "exclusive directory rename is unsupported")

    if result != 0:
        error_number = ctypes.get_errno()
        raise OSError(
            error_number,
            os.strerror(error_number),
            destination.as_posix(),
        )


def input_snapshot() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for relative in TESTS:
        path = ROOT / relative
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError(f"test target is not a regular file: {relative}")
        result.append(
            {
                "path": relative,
                "sha256": sha256_path(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return result


def parse_junit(path: Path) -> tuple[dict[str, int], dict[str, int]]:
    document = ET.parse(path).getroot()
    if document.tag == "testsuite":
        suites = [document]
    elif document.tag == "testsuites":
        suites = list(document.findall("testsuite"))
    else:
        raise ValueError(f"unsupported JUnit root element: {document.tag}")
    if not suites:
        raise ValueError("JUnit contains no test suites")

    suite_counts = {
        field: sum(int(suite.attrib.get(field, "0")) for suite in suites)
        for field in ("tests", "failures", "errors", "skipped")
    }
    testcases = list(document.iter("testcase"))
    testcase_counts = {
        "tests": len(testcases),
        "failures": sum(bool(case.findall("failure")) for case in testcases),
        "errors": sum(bool(case.findall("error")) for case in testcases),
        "skipped": sum(bool(case.findall("skipped")) for case in testcases),
    }
    testcase_counts["passed"] = (
        testcase_counts["tests"]
        - testcase_counts["failures"]
        - testcase_counts["errors"]
        - testcase_counts["skipped"]
    )
    return suite_counts, testcase_counts


def parse_regular_junit(path: Path) -> tuple[dict[str, int], dict[str, int]]:
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError("pytest did not create a regular JUnit artifact")
    return parse_junit(path)


def load_nodeids(path: Path) -> list[str]:
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError("pytest plugin did not create a regular nodeid artifact")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, list) or not all(isinstance(item, str) for item in loaded):
        raise ValueError("nodeid artifact must be an array of strings")
    return sorted(loaded)


def artifact(path: Path, final_name: str, bundle: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        return {"path": (bundle / final_name).as_posix(), "present": False}
    return {
        "path": (bundle / final_name).as_posix(),
        "present": True,
        "sha256": sha256_path(path),
        "size_bytes": path.stat().st_size,
    }


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an isolated, create-only receipt for the focused current-byte pytest suite."
    )
    parser.add_argument(
        "--run-id",
        required=True,
        type=run_id,
        help="unique lowercase slug used to derive the output bundle name",
    )
    parser.add_argument(
        "--expected-count",
        required=True,
        type=expected_count,
        help="exact number of tests that must be collected and pass",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    stem = f"{STEM_PREFIX}-{args.run_id}"
    bundle = bundle_for_run(args.run_id)
    expected = {
        "collected": args.expected_count,
        "passed": args.expected_count,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
    }
    if not RAW.is_dir() or RAW.is_symlink():
        raise NotADirectoryError(f"raw output root is not a regular directory: {RAW}")
    if lexists(bundle):
        raise FileExistsError(f"create-only pytest receipt bundle exists: {bundle}")

    temporary = Path(tempfile.mkdtemp(prefix=f".{stem}.tmp-", dir=RAW))
    log_path = temporary / "pytest.log"
    junit_path = temporary / "pytest.junit.xml"
    receipt_path = temporary / "receipt.json"
    nodeids_path = temporary / "nodeids.json"
    plugin_path = temporary / f"{PLUGIN_NAME}.py"
    runtime = temporary / "runtime"
    published = False

    try:
        for relative in ("home", "tmp", "xdg-cache", "xdg-config", "xdg-data"):
            (runtime / relative).mkdir(parents=True)
        write_exclusive(plugin_path, PLUGIN_SOURCE.encode("utf-8"))

        before = input_snapshot()
        pythonpath = os.pathsep.join(
            (
                temporary.as_posix(),
                ROOT.as_posix(),
                (ROOT / "src").as_posix(),
                (ROOT / "main/backend").as_posix(),
            )
        )
        environment = {
            "GIT_CONFIG_COUNT": "0",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "HOME": (runtime / "home").as_posix(),
            "LANG": "C",
            "LC_ALL": "C",
            "LLM_CACHE_ENABLED": "false",
            "MRW_PYTEST_NODEIDS_PATH": nodeids_path.as_posix(),
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "PYTHONNOUSERSITE": "1",
            "PYTHONPATH": pythonpath,
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "TMPDIR": (runtime / "tmp").as_posix(),
            "TZ": "UTC",
            "XDG_CACHE_HOME": (runtime / "xdg-cache").as_posix(),
            "XDG_CONFIG_HOME": (runtime / "xdg-config").as_posix(),
            "XDG_DATA_HOME": (runtime / "xdg-data").as_posix(),
        }
        argv = (
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-p",
            PLUGIN_NAME,
            "-q",
            *TESTS,
            f"--junitxml={junit_path.as_posix()}",
        )

        started_at = utc_now()
        started = time.monotonic()
        execution_error: str | None = None
        try:
            completed = subprocess.run(
                argv,
                cwd=ROOT,
                env=environment,
                check=False,
                capture_output=True,
            )
            process_exit_code: int | None = completed.returncode
            log = completed.stdout + completed.stderr
        except Exception as error:  # Ensure launch failures produce a receipt.
            process_exit_code = None
            execution_error = f"{type(error).__name__}: {error}"
            log = (execution_error + "\n").encode("utf-8", errors="replace")
        elapsed = time.monotonic() - started
        finished_at = utc_now()
        write_exclusive(log_path, log)

        after_error: str | None = None
        try:
            after = input_snapshot()
        except Exception as error:
            after = []
            after_error = f"{type(error).__name__}: {error}"
        inputs_unchanged = before == after

        junit_error: str | None = None
        suite_counts: dict[str, int] = {}
        testcase_counts: dict[str, int] = {}
        try:
            suite_counts, testcase_counts = parse_regular_junit(junit_path)
        except Exception as error:
            junit_error = f"{type(error).__name__}: {error}"

        nodeids_error: str | None = None
        nodeids: list[str] = []
        try:
            nodeids = load_nodeids(nodeids_path)
        except Exception as error:
            nodeids_error = f"{type(error).__name__}: {error}"

        observed = {
            "collected": len(nodeids),
            "passed": testcase_counts.get("passed"),
            "failures": testcase_counts.get("failures"),
            "errors": testcase_counts.get("errors"),
            "skipped": testcase_counts.get("skipped"),
        }
        junit_consistent = bool(suite_counts) and all(
            suite_counts.get(field) == testcase_counts.get(field)
            for field in ("tests", "failures", "errors", "skipped")
        )
        exact_counts = observed == expected
        unique_nodeids = len(nodeids) == len(set(nodeids))
        passed = (
            process_exit_code == 0
            and execution_error is None
            and after_error is None
            and inputs_unchanged
            and junit_error is None
            and nodeids_error is None
            and junit_consistent
            and unique_nodeids
            and exact_counts
            and suite_counts.get("tests") == expected["collected"]
        )

        runtime_cleanup_error: str | None = None
        try:
            shutil.rmtree(runtime)
        except Exception as error:
            runtime_cleanup_error = f"{type(error).__name__}: {error}"
            passed = False

        receipt = {
            "schema": "mrw.current-pytest-receipt.v2",
            "status": f"PASS_COMPLETE_EXACT_{args.expected_count}" if passed else "FAIL",
            "authoritative": False,
            "authority": {
                "candidate_promotion": False,
                "production_release": False,
                "deployment": False,
                "live_write": False,
            },
            "run_id": args.run_id,
            "expected_count": args.expected_count,
            "bundle": bundle.as_posix(),
            "execution": {
                "argv": list(argv),
                "cwd": ROOT.as_posix(),
                "started_at_utc": started_at,
                "finished_at_utc": finished_at,
                "elapsed_seconds": elapsed,
                "process_exit_code": process_exit_code,
                "execution_error": execution_error,
            },
            "environment": {
                "inherit_ambient": False,
                "allowlisted": environment,
                "explicitly_not_inherited": list(CONTROL_ENVIRONMENT_VARIABLES),
            },
            "runtime": {
                "python_executable": sys.executable,
                "python_implementation": platform.python_implementation(),
                "python_version": platform.python_version(),
                "python_version_detail": sys.version,
                "pytest_version": importlib.metadata.version("pytest"),
                "platform": platform.platform(),
                "system": platform.system(),
                "release": platform.release(),
                "machine": platform.machine(),
            },
            "inputs": {
                "before": before,
                "after": after,
                "after_error": after_error,
                "unchanged_during_run": inputs_unchanged,
            },
            "results": {
                "expected": expected,
                "observed": observed,
                "junit_suite_attributes": suite_counts,
                "junit_testcase_derived": testcase_counts,
                "junit_counts_consistent": junit_consistent,
                "junit_error": junit_error,
                "nodeids_error": nodeids_error,
                "nodeids_unique": unique_nodeids,
                "nodeids_normalization": "sorted UTF-8 RFC8259 JSON with no whitespace",
                "nodeids_sha256": sha256_bytes(canonical_json(nodeids)),
                "nodeids": nodeids,
            },
            "artifacts": [
                artifact(log_path, log_path.name, bundle),
                artifact(junit_path, junit_path.name, bundle),
                artifact(nodeids_path, nodeids_path.name, bundle),
                artifact(plugin_path, plugin_path.name, bundle),
            ],
            "cleanup": {
                "runtime_directory_removed_before_publish": runtime_cleanup_error is None,
                "error": runtime_cleanup_error,
            },
            "limits": [
                "This receipt is local development evidence and grants no release authority.",
                "The receipt binds only the named current source files and this exact execution.",
            ],
        }
        write_exclusive(
            receipt_path,
            (json.dumps(receipt, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )
        publish_directory_exclusive(temporary, bundle)
        published = True

        sys.stdout.buffer.write(log)
        print(
            json.dumps(
                {
                    "bundle": bundle.as_posix(),
                    "receipt": (bundle / receipt_path.name).as_posix(),
                    "receipt_sha256": sha256_path(bundle / receipt_path.name),
                    "status": receipt["status"],
                },
                sort_keys=True,
            )
        )
        return 0 if passed else 1
    finally:
        if not published and temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
