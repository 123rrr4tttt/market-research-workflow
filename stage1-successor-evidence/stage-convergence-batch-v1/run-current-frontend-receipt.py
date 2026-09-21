#!/usr/bin/env python3
"""Run one bounded frontend gate and create a hash-bound local receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "main/frontend-modern"
RAW = ROOT / "stage1-successor-evidence/stage3-v6-artifact-remediation-v1/raw"
STORYBOOK_OUTPUT = Path("/private/tmp/mrw-frontend-storybook-development-takeover-20260908")
GATES = {
    "frozen-install": ("pnpm", "install", "--frozen-lockfile", "--offline"),
    "lint": ("pnpm", "lint"),
    "typecheck": ("pnpm", "exec", "tsc", "-b", "--pretty", "false"),
    "build": ("pnpm", "build"),
    "storybook": (
        "pnpm", "storybook:build", "--output-dir", STORYBOOK_OUTPUT.as_posix()
    ),
}


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def create(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)


def version(command: tuple[str, ...]) -> str:
    result = subprocess.run(command, cwd=FRONTEND, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gate", choices=tuple(GATES))
    args = parser.parse_args()
    command = GATES[args.gate]
    stem = f"frontend-{args.gate}-development-takeover-20260908"
    log_path = RAW / f"{stem}.log"
    receipt_path = RAW / f"{stem}.json"
    if log_path.exists() or receipt_path.exists():
        raise FileExistsError(f"create-only frontend receipt exists: {stem}")
    started = time.monotonic()
    result = subprocess.run(command, cwd=FRONTEND, check=False, capture_output=True)
    elapsed = time.monotonic() - started
    log = result.stdout + result.stderr
    create(log_path, log)
    receipt = {
        "artifacts": [{"path": log_path.as_posix(), "sha256": sha256(log)}],
        "authoritative": False,
        "command": list(command),
        "cwd": FRONTEND.as_posix(),
        "elapsed_seconds": elapsed,
        "environment": {
            "NODE_VERSION": version(("node", "--version")),
            "PNPM_VERSION": version(("pnpm", "--version")),
            "scope": "CURRENT_SOURCE_LOCAL_DIAGNOSTIC_NOT_FINAL_PREVIEW",
        },
        "exit_code": result.returncode,
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
