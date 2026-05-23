#!/usr/bin/env python3
"""Verify the Wave16 parallel-agent runtime boundary closure."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


TOPIC = Path(
    "docs/development/development-plans/ARCHIVE_CLOSED/"
    "2026-04-07-parallel-agent-wave-orchestration"
)
RUNS = Path("development/latest-dev-docs/automation-runs/dev-docs-folder-audit-2026-05-22")
README = TOPIC / "README.md"
WAVE16 = TOPIC / "07_wave16-runtime-boundary-closure-2026-05-22.md"
CONTRACT = TOPIC / "wave16_runtime_boundary_closure_2026-05-22.json"
WAVE10_CONTRACT = TOPIC / "runtime_contract_refresh_2026-05-22.json"
WAVE16_PLAN = RUNS / "wave16-worktree-plan-2026-05-22.md"
AGENTS = Path("codex_settings/AGENTS.md")
BOOTSTRAP = Path("codex_settings/scripts/swarm_file_bootstrap.sh")
SWARM = Path("codex_settings/scripts/swarm.sh")

EXPECTED_BRANCHES = [
    "codex/devdocs-wave16-parallel-runtime-closure",
    "codex/devdocs-wave16-clue-chain-closure-split",
    "codex/devdocs-wave16-graph-editing-ui-audit-controls",
    "codex/devdocs-wave16-typed-knowledge-api-route",
    "codex/devdocs-wave16-writing-workbench-typed-fetch",
    "codex/devdocs-wave16-long-cycle-live-repository-readback",
    "codex/devdocs-wave16-docs-root-content-move-batch",
    "codex/devdocs-wave16-frontend-business-string-migration",
    "codex/devdocs-wave16-source-library-review-closure-batch",
]

FORBIDDEN_PATHS = [
    "development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md",
    "development/latest-dev-docs/development-plans/CURRENT_DEV/STATUS_AUDIT_2026-04-07.md",
    "development/latest-dev-docs/development-plans/INDEX.md",
    "development/latest-dev-docs/README.md",
    "development/latest-dev-docs/MERGED_OVERVIEW.md",
    "main/backend/scripts/workflow_graph_smoke_local.py",
]


def fail(message: str) -> None:
    print(f"[FAIL] {message}", file=sys.stderr)
    raise SystemExit(1)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def require_file(path: Path) -> None:
    require(path.is_file(), f"missing file: {path}")


def read_text(path: Path) -> str:
    require_file(path)
    return path.read_text(encoding="utf-8")


def require_contains(path: Path, text: str, label: str) -> None:
    content = read_text(path)
    require(text in content, f"{label} not found in {path}")


def load_json(path: Path) -> dict:
    try:
        return json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON in {path}: {exc}")


def check_contract(data: dict) -> None:
    require(data.get("schema") == "parallel_agent_runtime_boundary_closure_wave16.v1", "unexpected Wave16 schema")
    require(data.get("status") == "archive_candidate", "Wave16 status must be archive_candidate")
    tags = set(data.get("status_tags", []))
    require(
        {"wave16_checked", "archive_candidate", "successor_split", "worker_runtime_external"} <= tags,
        "Wave16 status tags are incomplete",
    )

    parent = data.get("parent_runtime", {})
    require(parent.get("tool") == "multi_agent_v1.spawn_agent", "parent runtime tool mismatch")
    require(parent.get("available") is True, "parent runtime must be available")
    require(parent.get("claim_scope") == "parent_runtime_only", "parent runtime claim must be scope-limited")
    require(parent.get("closed_for_repo_boundary") is True, "parent runtime boundary must be closed for repo scope")

    repo = data.get("repo_runtime_entry", {})
    require(repo.get("agents_contract") == str(AGENTS), "repo AGENTS contract path mismatch")
    require(repo.get("tool_search_required_when_missing") is True, "repo contract must require tool_search")
    require(repo.get("spawn_tool_name") == "multi_agent_v1.spawn_agent", "repo spawn tool name mismatch")
    require(repo.get("no_fabricated_subagent_capability") is True, "repo contract must forbid fabricated subagent capability")
    require(repo.get("fallback_context_tools_are_spawn_evidence") is False, "fallback tools must not count as spawn evidence")
    fallback_text = " ".join(repo.get("fallback_when_missing", []))
    for required in ("record runtime tool unavailable", "single-agent", "read-only exploration"):
        require(required in fallback_text, f"repo fallback must mention {required!r}")
    require(str(BOOTSTRAP) in repo.get("fallback_context_tools", []), "bootstrap fallback path missing")
    require(str(SWARM) in repo.get("fallback_context_tools", []), "swarm fallback path missing")

    successor = data.get("worker_runtime_successor", {})
    require(successor.get("successor_required") is True, "worker successor must be required")
    require(successor.get("closed_by_this_topic") is False, "worker runtime must not be closed by this topic")
    require(successor.get("must_not_be_reported_as_closed") is True, "worker runtime non-closure must be explicit")
    require(successor.get("must_not_block_archive_candidate") is True, "worker successor must not block archive candidate")
    claim_requires = " ".join(successor.get("claim_requires", []))
    for required in ("callable", "result", "changed files", "validation status", "risk"):
        require(required in claim_requires, f"worker successor claim must mention {required!r}")

    archive = data.get("archive_candidate", {})
    require(archive.get("candidate") is True, "archive candidate flag must be true")
    require(archive.get("supervisor_owns_shared_index_update") is True, "shared index update must be supervisor-owned")

    verification = data.get("verification", {})
    require(verification.get("checker") == "verify_wave16_runtime_contract.py", "Wave16 checker name mismatch")
    require(verification.get("expected_marker") == "WAVE16_RUNTIME_BOUNDARY_OK", "Wave16 expected marker mismatch")


def check_docs() -> None:
    for path in (README, WAVE16, CONTRACT, WAVE10_CONTRACT, WAVE16_PLAN, AGENTS, BOOTSTRAP, SWARM):
        require_file(path)

    for text, label in (
        ("07_wave16-runtime-boundary-closure-2026-05-22.md", "Wave16 evidence link"),
        ("wave16_runtime_boundary_closure_2026-05-22.json", "Wave16 JSON link"),
        ("verify_wave16_runtime_contract.py", "Wave16 checker link"),
    ):
        require_contains(README, text, label)

    for text, label in (
        ("wave16_runtime_boundary_closure_2026-05-22.json", "Wave16 JSON link"),
        ("verify_wave16_runtime_contract.py", "Wave16 checker link"),
    ):
        require_contains(WAVE16, text, label)

    for text, label in (
        ("archive candidate", "archive candidate marker"),
        ("successor_split", "successor split marker"),
        ("parent runtime", "parent runtime boundary"),
        ("worker runtime proof", "worker runtime successor"),
        ("not runtime-spawn evidence", "fallback non-spawn boundary"),
        ("supervisor", "supervisor shared-index owner"),
    ):
        require_contains(WAVE16, text, label)

    for text, label in (
        ("multi_agent_v1.spawn_agent", "multi-agent runtime name"),
        ("tool_search", "tool discovery fallback"),
        ("不要伪造子 Agent 能力", "no-fabrication fallback"),
        ("常规单 Agent 流程", "single-agent fallback"),
        ("并行 shell/tool 调用", "parallel shell/tool fallback"),
    ):
        require_contains(AGENTS, text, label)

    require_contains(BOOTSTRAP, "SWARM FILE BOOTSTRAP", "bootstrap marker")
    require_contains(SWARM, "swarm_file_bootstrap.sh", "swarm batch delegates to bootstrap")


def check_wave16_plan() -> None:
    text = read_text(WAVE16_PLAN)
    for branch in EXPECTED_BRANCHES:
        require(branch in text, f"Wave16 plan missing branch {branch}")
    for path in FORBIDDEN_PATHS:
        require(path in text, f"Wave16 plan missing forbidden path {path}")
    require("9 个并行工作树任务" in text, "Wave16 plan must record nine worker tasks")
    require("parent runtime" in read_text(WAVE16).lower(), "Wave16 evidence must mention parent runtime")


def check_legacy_contract_alignment() -> None:
    wave10 = load_json(WAVE10_CONTRACT)
    require(wave10.get("parent_runtime", {}).get("available") is True, "Wave10 parent runtime must remain available")
    require(
        wave10.get("worker_boundary", {}).get("worker_runtime_must_verify_tool_exposure") is True,
        "Wave10 worker verification boundary must remain explicit",
    )
    require(
        wave10.get("worker_boundary", {}).get("subagent_capability_claimed_by_this_worker") is False,
        "Wave10 must not claim worker subagent capability",
    )


def check_changed_paths() -> None:
    branch = subprocess.run(["git", "branch", "--show-current"], text=True, capture_output=True, check=False)
    if branch.returncode == 0 and branch.stdout.strip() != "codex/devdocs-wave16-parallel-runtime-closure":
        return
    proc = subprocess.run(["git", "status", "--porcelain"], text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        fail(proc.stderr.strip() or "git status failed")
    changed: list[str] = []
    for line in proc.stdout.splitlines():
        if not line:
            continue
        path = line[2:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        changed.append(path)
    forbidden = sorted(set(changed) & set(FORBIDDEN_PATHS))
    require(not forbidden, f"forbidden worker paths changed: {forbidden}")


def main() -> int:
    root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        text=True,
        capture_output=True,
        check=False,
    )
    if root.returncode != 0:
        fail("not inside a git repository")
    os.chdir(Path(root.stdout.strip()))

    check_docs()
    check_contract(load_json(CONTRACT))
    check_wave16_plan()
    check_legacy_contract_alignment()
    check_changed_paths()
    print("WAVE16_RUNTIME_BOUNDARY_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
