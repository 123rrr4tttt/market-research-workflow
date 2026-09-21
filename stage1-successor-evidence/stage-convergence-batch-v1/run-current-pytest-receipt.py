#!/usr/bin/env python3
"""Run the current source-closure/intake/package suite and create a receipt."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "stage1-successor-evidence/stage3-v6-artifact-remediation-v1/raw"
STEM = "current-byte-selector-intake-package-development-takeover-20260908"
TESTS = (
    "tests/formal_release/test_source_closure.py",
    "tests/formal_release/test_stage2_candidate_intake.py",
    "stage1-successor-evidence/stage3-v6-artifact-remediation-v1/"
    "test_stage3_v6_artifact_remediation_v1.py",
)


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def create(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)


def main() -> int:
    log_path = RAW / f"{STEM}.log"
    junit_path = RAW / f"{STEM}.xml"
    receipt_path = RAW / f"{STEM}.json"
    outputs = (log_path, junit_path, receipt_path)
    if any(path.exists() or path.is_symlink() for path in outputs):
        raise FileExistsError(f"create-only pytest receipt exists: {STEM}")

    pythonpath = os.pathsep.join(
        (
            ROOT.as_posix(),
            (ROOT / "src").as_posix(),
            (ROOT / "main/backend").as_posix(),
        )
    )
    environment = {
        "LLM_CACHE_ENABLED": "false",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTHONPATH": pythonpath,
    }
    command = (
        sys.executable,
        "-m",
        "pytest",
        "-p",
        "no:cacheprovider",
        "-q",
        *TESTS,
        f"--junitxml={junit_path.as_posix()}",
    )
    started = time.monotonic()
    result = subprocess.run(
        command,
        cwd=ROOT,
        env={**os.environ, **environment},
        check=False,
        capture_output=True,
    )
    elapsed = time.monotonic() - started
    log = result.stdout + result.stderr
    create(log_path, log)
    if not junit_path.is_file() or junit_path.is_symlink():
        raise RuntimeError("pytest did not create a regular JUnit artifact")
    junit = junit_path.read_bytes()
    receipt = {
        "artifacts": [
            {"path": log_path.as_posix(), "sha256": sha256(log)},
            {"path": junit_path.as_posix(), "sha256": sha256(junit)},
        ],
        "authoritative": False,
        "command": list(command),
        "cwd": ROOT.as_posix(),
        "elapsed_seconds": elapsed,
        "environment": environment,
        "exit_code": result.returncode,
        "isolation": "none added",
    }
    create(
        receipt_path,
        (json.dumps(receipt, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode(),
    )
    print(log.decode(errors="replace"), end="")
    print(json.dumps({"receipt": receipt_path.as_posix(), "exit_code": result.returncode}))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
