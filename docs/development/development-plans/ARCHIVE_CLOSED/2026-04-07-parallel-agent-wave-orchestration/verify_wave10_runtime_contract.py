#!/usr/bin/env python3
"""Verify the Wave10 parallel-agent runtime contract refresh."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


TOPIC = Path(
    "development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/"
    "2026-04-07-parallel-agent-wave-orchestration"
)
README = TOPIC / "README.md"
WAVE7 = TOPIC / "05_wave7-runtime-closure-evidence-2026-05-22.md"
WAVE10 = TOPIC / "06_wave10-runtime-contract-refresh-2026-05-22.md"
CONTRACT = TOPIC / "runtime_contract_refresh_2026-05-22.json"
AGENTS = Path("codex_settings/AGENTS.md")
BOOTSTRAP = Path("codex_settings/scripts/swarm_file_bootstrap.sh")
SWARM = Path("codex_settings/scripts/swarm.sh")


def fail(message: str) -> None:
    print(f"[FAIL] {message}", file=sys.stderr)
    raise SystemExit(1)


def require_file(path: Path) -> None:
    if not path.is_file():
        fail(f"missing file: {path}")


def require_contains(path: Path, text: str, label: str) -> None:
    content = path.read_text(encoding="utf-8")
    if text not in content:
        fail(f"{label} not found in {path}")


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def load_contract() -> dict:
    try:
        return json.loads(CONTRACT.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON in {CONTRACT}: {exc}")


def check_contract(data: dict) -> None:
    require(data.get("schema") == "parallel_agent_runtime_contract_refresh.v1", "unexpected contract schema")
    require(data.get("status") == "partial", "contract status must remain partial")
    tags = set(data.get("status_tags", []))
    require({"external_blocked", "wave10_checked"} <= tags, "contract tags must include external_blocked and wave10_checked")

    parent = data.get("parent_runtime", {})
    require(parent.get("tool") == "multi_agent_v1.spawn_agent", "parent runtime tool must name multi_agent_v1.spawn_agent")
    require(parent.get("available") is True, "parent runtime must be marked available")
    require(parent.get("claim_scope") == "parent_runtime_only", "parent runtime claim must be scope-limited")

    worker = data.get("worker_boundary", {})
    require(worker.get("worker_runtime_must_verify_tool_exposure") is True, "worker runtime must require actual tool exposure")
    require(worker.get("subagent_capability_claimed_by_this_worker") is False, "this worker must not claim subagent capability")
    claim_requires = " ".join(worker.get("claim_requires", []))
    for required in ("callable", "result", "changed files", "validation status", "risk", "fallback"):
        require(required in claim_requires, f"worker claim requirements must mention {required!r}")

    fallback = data.get("fallback_contract", {})
    require(fallback.get("tool_search_required_when_missing") is True, "fallback must require tool_search")
    require(fallback.get("no_fabricated_subagent_capability") is True, "fallback must forbid fabricated subagent capability")
    search_phrases = " ".join(fallback.get("search_phrases", []))
    require("spawn_agent" in search_phrases, "fallback search phrases must mention spawn_agent")
    fallback_steps = " ".join(fallback.get("if_still_missing", []))
    for required in ("record runtime tool unavailable", "single-agent", "parallel shell/tool reads"):
        require(required in fallback_steps, f"fallback steps must mention {required!r}")
    not_spawn = set(fallback.get("not_runtime_spawn_evidence", []))
    require(str(BOOTSTRAP) in not_spawn, "bootstrap script must be marked non-spawn evidence")
    require(str(SWARM) in not_spawn, "swarm script must be marked non-spawn evidence")

    verification = data.get("verification", {})
    require(verification.get("checker") == "verify_wave10_runtime_contract.py", "checker name mismatch")
    require(verification.get("expected_marker") == "WAVE10_RUNTIME_CONTRACT_OK", "expected marker mismatch")


def check_docs() -> None:
    for path in (README, WAVE7, WAVE10, CONTRACT, AGENTS, BOOTSTRAP, SWARM):
        require_file(path)

    for text, label in (
        ("06_wave10-runtime-contract-refresh-2026-05-22.md", "Wave10 evidence link"),
        ("runtime_contract_refresh_2026-05-22.json", "Wave10 JSON link"),
        ("verify_wave10_runtime_contract.py", "Wave10 checker link"),
    ):
        require_contains(README, text, label)

    for text, label in (
        ("runtime_contract_refresh_2026-05-22.json", "Wave10 JSON link"),
        ("verify_wave10_runtime_contract.py", "Wave10 checker link"),
    ):
        require_contains(WAVE10, text, label)

    for text, label in (
        ("parent_runtime.available=true", "parent runtime availability boundary"),
        ("worker_runtime_must_verify_tool_exposure=true", "worker verification boundary"),
        ("subagent_capability_claimed_by_this_worker=false", "no worker subagent claim"),
        ("not as runtime-spawn evidence", "fallback non-spawn boundary"),
        ("tool_search", "tool discovery rule"),
    ):
        require_contains(WAVE10, text, label)

    for text, label in (
        ("multi_agent_v1.spawn_agent", "multi-agent runtime name"),
        ("tool_search", "tool discovery fallback"),
        ("不要伪造子 Agent 能力", "no-fabrication fallback"),
        ("常规单 Agent 流程", "single-agent fallback"),
        ("并行 shell/tool 调用", "parallel shell/tool fallback"),
    ):
        require_contains(AGENTS, text, label)

    require_contains(BOOTSTRAP, "SWARM FILE BOOTSTRAP", "bootstrap marker")
    require_contains(SWARM, "swarm_file_bootstrap.sh", "batch bootstrap delegation")


def check_bootstrap_output() -> None:
    proc = subprocess.run(
        ["bash", str(BOOTSTRAP), str(WAVE10)],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        fail(f"bootstrap fallback failed: {detail}")
    require("=== SWARM FILE BOOTSTRAP ===" in proc.stdout, "bootstrap output missing header")
    require(f"target: {WAVE10}" in proc.stdout, "bootstrap output missing Wave10 target")


def main() -> int:
    root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        text=True,
        capture_output=True,
        check=False,
    )
    if root.returncode != 0:
        fail("not inside a git repository")
    repo_root = Path(root.stdout.strip())
    os.chdir(repo_root)

    check_docs()
    check_contract(load_contract())
    check_bootstrap_output()
    print("WAVE10_RUNTIME_CONTRACT_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
