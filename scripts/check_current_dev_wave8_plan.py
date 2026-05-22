#!/usr/bin/env python3
"""Validate the Wave8 CURRENT_DEV support-lane plan.

This is a read-only guardrail for supervisor integration. It checks that the
Wave8 plan lists every expected worker/support branch, exposes machine-readable
metadata, and that this support lane has not modified shared navigation indexes.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


PLAN_PATH = Path(
    "development/latest-dev-docs/automation-runs/dev-docs-folder-audit-2026-05-22/"
    "wave8-worktree-plan-2026-05-22.md"
)
BASE_BRANCH = "codex/devdocs-wave8-integration-2026-05-22"
SUPPORT_BRANCH = "codex/devdocs-wave8-current-dev-audit"

EXPECTED_BRANCHES = [
    "codex/devdocs-wave8-crawler-external-closure",
    "codex/devdocs-wave8-fetch-router-cluster",
    "codex/devdocs-wave8-frontend-topology-i18n",
    "codex/devdocs-wave8-graph-rollout",
    "codex/devdocs-wave8-search-vectorization",
    "codex/devdocs-wave8-source-library-adapter",
    "codex/devdocs-wave8-time-semantics-density",
    "codex/devdocs-wave8-writing-typed-knowledge",
    "codex/devdocs-wave8-current-dev-audit",
]

FORBIDDEN_SHARED_INDEXES = {
    "development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md",
    "development/latest-dev-docs/development-plans/INDEX.md",
    "development/latest-dev-docs/README.md",
    "development/latest-dev-docs/MERGED_OVERVIEW.md",
}

ALLOWED_CHANGED_PREFIXES = (
    "development/latest-dev-docs/automation-runs/dev-docs-folder-audit-2026-05-22/",
    "scripts/check_current_dev_wave8_plan.py",
)


def run_git(args: list[str]) -> str:
    proc = subprocess.run(["git", *args], text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return proc.stdout.strip()


def extract_manifest(text: str) -> dict[str, object]:
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not match:
        raise ValueError("missing fenced JSON manifest")
    manifest = json.loads(match.group(1))
    if not isinstance(manifest, dict):
        raise ValueError("manifest is not a JSON object")
    return manifest


def changed_files_against_base() -> list[str]:
    try:
        merge_base = run_git(["merge-base", "HEAD", BASE_BRANCH])
    except RuntimeError:
        # Fall back to the parent commit so the gate remains useful in isolated
        # worktrees that do not have the integration branch ref.
        merge_base = "HEAD~1"
    output = run_git(["diff", "--name-only", f"{merge_base}..HEAD"])
    return [line for line in output.splitlines() if line]


def changed_files_in_worktree() -> list[str]:
    output = run_git(["status", "--porcelain"])
    paths: list[str] = []
    for line in output.splitlines():
        if not line:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.append(path)
    return paths


def unique_ordered(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        result.append(path)
    return result


def main() -> int:
    problems: list[str] = []

    current_branch = run_git(["branch", "--show-current"])
    if current_branch != SUPPORT_BRANCH:
        problems.append(f"current branch is {current_branch!r}, expected {SUPPORT_BRANCH!r}")

    if not PLAN_PATH.is_file():
        problems.append(f"missing plan file: {PLAN_PATH}")
        manifest: dict[str, object] = {}
        text = ""
    else:
        text = PLAN_PATH.read_text(encoding="utf-8")
        try:
            manifest = extract_manifest(text)
        except (ValueError, json.JSONDecodeError) as exc:
            problems.append(str(exc))
            manifest = {}

    manifest_branches = []
    for item in manifest.get("branches", []):
        if isinstance(item, dict) and isinstance(item.get("branch"), str):
            manifest_branches.append(item["branch"])

    missing_branches = sorted(set(EXPECTED_BRANCHES) - set(manifest_branches))
    extra_branches = sorted(set(manifest_branches) - set(EXPECTED_BRANCHES))
    if missing_branches:
        problems.append(f"manifest missing branches: {missing_branches}")
    if extra_branches:
        problems.append(f"manifest has unexpected branches: {extra_branches}")
    if len(manifest_branches) != len(EXPECTED_BRANCHES):
        problems.append(f"manifest branch count is {len(manifest_branches)}, expected {len(EXPECTED_BRANCHES)}")

    if manifest.get("integration_branch") != BASE_BRANCH:
        problems.append("manifest integration_branch mismatch")
    if manifest.get("support_branch") != SUPPORT_BRANCH:
        problems.append("manifest support_branch mismatch")

    forbidden = set(manifest.get("forbidden_shared_indexes", []))
    if forbidden != FORBIDDEN_SHARED_INDEXES:
        problems.append("manifest forbidden_shared_indexes mismatch")

    for branch in EXPECTED_BRANCHES:
        if branch not in text:
            problems.append(f"plan text does not mention {branch}")

    changed = unique_ordered(changed_files_against_base() + changed_files_in_worktree())
    forbidden_changed = sorted(set(changed) & FORBIDDEN_SHARED_INDEXES)
    if forbidden_changed:
        problems.append(f"forbidden shared indexes changed: {forbidden_changed}")

    outside_allowed = [
        path
        for path in changed
        if not any(path == prefix or path.startswith(prefix) for prefix in ALLOWED_CHANGED_PREFIXES)
    ]
    if outside_allowed:
        problems.append(f"changed files outside support-lane allowlist: {outside_allowed}")

    if problems:
        for problem in problems:
            print(f"FAIL wave8_current_dev_plan: {problem}", file=sys.stderr)
        return 1

    print(
        "OK wave8_current_dev_plan=passed "
        f"branches={len(EXPECTED_BRANCHES)} changed_files={len(changed)} forbidden_shared_indexes=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
