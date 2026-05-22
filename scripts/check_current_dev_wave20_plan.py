#!/usr/bin/env python3
"""Validate the Wave20 CURRENT_DEV worktree plan."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PLAN_PATH = Path(
    "development/latest-dev-docs/automation-runs/dev-docs-folder-audit-2026-05-22/"
    "wave20-worktree-plan-2026-05-22.md"
)
INTEGRATION_BRANCH = "codex/devdocs-wave20-integration-2026-05-22"
SUPERVISOR_BRANCH = "codex/devdocs-supervisor-seed"

EXPECTED_BRANCHES = [
    "codex/devdocs-wave20-time-semantics-readback",
    "codex/devdocs-wave20-openclaw-mirror-readback",
    "codex/devdocs-wave20-graph-editing-audit-conflict",
    "codex/devdocs-wave20-long-cycle-scheduler-queue",
    "codex/devdocs-wave20-agent-batch-quality-promotion",
    "codex/devdocs-wave20-document-query-endpoint-slice",
    "codex/devdocs-wave20-consumer-facade-slice",
    "codex/devdocs-wave20-source-library-review-batch4",
    "codex/devdocs-wave20-frontend-i18n-next-slice",
    "codex/devdocs-wave20-docs-root-content-move-batch5",
]

FORBIDDEN_SHARED_INDEXES = {
    "development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md",
    "development/latest-dev-docs/development-plans/CURRENT_DEV/STATUS_AUDIT_2026-04-07.md",
    "development/latest-dev-docs/development-plans/INDEX.md",
    "development/latest-dev-docs/README.md",
    "development/latest-dev-docs/MERGED_OVERVIEW.md",
}
FORBIDDEN_DIRTY_FILES = {
    "main/backend/scripts/workflow_graph_smoke_local.py",
    "development/latest-dev-docs/automation-runs/branch-hygiene-2026-05-15.md",
}

REQUIRED_AUDIT_TEXT = [
    "`partial` | 33",
    "`not_closed` | 0",
    "`no_closure_claim` | 0",
    "production data",
    "external OpenClaw runtime",
    "live tenant DB",
    "live scheduler",
    "live provider quality",
    "live DB/API smoke",
    "human review",
    "unsafe moves",
]


def run_git(args: list[str]) -> str:
    proc = subprocess.run(["git", *args], text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return proc.stdout.strip()


def branch_exists(branch: str) -> bool:
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", branch],
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.returncode == 0


def changed_files_against_integration() -> list[str]:
    if branch_exists(INTEGRATION_BRANCH):
        try:
            merge_base = run_git(["merge-base", "HEAD", INTEGRATION_BRANCH])
        except RuntimeError:
            merge_base = "HEAD~1"
    else:
        merge_base = "HEAD~1"
    output = run_git(["diff", "--name-only", f"{merge_base}..HEAD"])
    return [line for line in output.splitlines() if line]


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


def unique_ordered(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            result.append(path)
    return result


def main() -> int:
    problems: list[str] = []
    current_branch = run_git(["branch", "--show-current"])
    allowed_branches = {INTEGRATION_BRANCH, SUPERVISOR_BRANCH, *EXPECTED_BRANCHES}
    if current_branch not in allowed_branches:
        problems.append(f"current branch is {current_branch!r}, expected a Wave20 branch")

    if not PLAN_PATH.is_file():
        problems.append(f"missing plan file: {PLAN_PATH}")
        text = ""
    else:
        text = PLAN_PATH.read_text(encoding="utf-8")

    for branch in EXPECTED_BRANCHES:
        if branch not in text:
            problems.append(f"plan text does not mention {branch}")

    for required in REQUIRED_AUDIT_TEXT:
        if required not in text:
            problems.append(f"plan text does not mention required audit marker {required}")

    for forbidden in sorted(FORBIDDEN_SHARED_INDEXES | FORBIDDEN_DIRTY_FILES):
        if forbidden not in text:
            problems.append(f"plan text does not list forbidden path {forbidden}")

    changed = unique_ordered(changed_files_against_integration() + changed_files_in_worktree())
    enforce_worker_boundary = current_branch in EXPECTED_BRANCHES
    if enforce_worker_boundary:
        forbidden_changed = sorted(set(changed) & (FORBIDDEN_SHARED_INDEXES | FORBIDDEN_DIRTY_FILES))
        if forbidden_changed:
            problems.append(f"worker branch changed forbidden paths: {forbidden_changed}")

    if problems:
        for problem in problems:
            print(f"FAIL wave20_current_dev_plan: {problem}", file=sys.stderr)
        return 1

    print(
        "OK wave20_current_dev_plan=passed "
        f"mode={current_branch} branches={len(EXPECTED_BRANCHES)} "
        f"changed_files={len(changed)} worker_boundary_enforced={str(enforce_worker_boundary).lower()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
