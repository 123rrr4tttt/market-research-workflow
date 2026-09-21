"""Shared Git helpers for CURRENT_DEV plan gates."""

from __future__ import annotations

import subprocess


def run_git(args: list[str]) -> str:
    proc = subprocess.run(["git", *args], text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return proc.stdout.strip()


def changed_files_in_worktree() -> list[str]:
    output = run_git(["status", "--porcelain"])
    paths: list[str] = []
    for line in output.splitlines():
        if not line:
            continue
        path = line[2:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.append(path)
    return paths
