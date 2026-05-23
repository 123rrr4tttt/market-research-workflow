#!/usr/bin/env python3
"""Check graph/typed/writing/consumer status semantics after migration.

This gate is intentionally about status ownership, not new product evidence.
It verifies that the four Wave27 topics have one canonical current state
(`external_blocked`) while older `partial` / `needs_update` lines remain only
legacy snapshots.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parents[1]
SCRIPTS_ROOT = BACKEND_ROOT / "scripts"
if sys.version_info < (3, 10):
    candidates = (
        os.environ.get("PYTHON311"),
        shutil.which("python3.11"),
        "/Users/wangyiliang/.local/bin/python3.11",
    )
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and Path(candidate) != Path(sys.executable):
            os.execv(candidate, [candidate, *sys.argv])

for path in (BACKEND_ROOT, SCRIPTS_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from check_graph_editing_audit_durability import (  # noqa: E402
    build_gate_snapshot as build_graph_gate_snapshot,
    validate_gate_snapshot as validate_graph_gate_snapshot,
)
from check_typed_writing_live_boundary import build_inventory as build_typed_writing_inventory  # noqa: E402
from check_wave27_structured_consumer_closure import build_check as build_consumer_closure_check  # noqa: E402


CONTRACT_VERSION = "graph_typed_writing_consumer.status_boundary.v1"
CURRENT_DEV_INDEX = Path("development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md")
EXTERNAL_BLOCKED_INDEX = Path("development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/INDEX.md")
TARGET_STATUS = "external_blocked"

TOPICS: tuple[dict[str, str], ...] = (
    {
        "id": "2026-03-07-graph-editing-and-reporting",
        "label": "graph_editing_and_reporting",
        "decision": (
            "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/"
            "2026-03-07-graph-editing-and-reporting/11_wave27-external-blocked-decision-2026-05-23.md"
        ),
        "dir": (
            "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/"
            "2026-03-07-graph-editing-and-reporting"
        ),
    },
    {
        "id": "2026-03-07-typed-knowledge-organization",
        "label": "typed_knowledge_organization",
        "decision": (
            "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/"
            "2026-03-07-typed-knowledge-organization/10_wave27-external-blocked-decision-2026-05-23.md"
        ),
        "dir": (
            "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/"
            "2026-03-07-typed-knowledge-organization"
        ),
    },
    {
        "id": "2026-03-07-writing-workbench-evolution",
        "label": "writing_workbench_evolution",
        "decision": (
            "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/"
            "2026-03-07-writing-workbench-evolution/11_wave27-external-blocked-decision-2026-05-23.md"
        ),
        "dir": (
            "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/"
            "2026-03-07-writing-workbench-evolution"
        ),
    },
    {
        "id": "2026-03-14-consumer-side-modularization",
        "label": "consumer_side_modularization",
        "decision": (
            "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/"
            "2026-03-14-consumer-side-modularization/08_wave27-external-blocked-decision-2026-05-23.md"
        ),
        "dir": (
            "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/"
            "2026-03-14-consumer-side-modularization"
        ),
    },
)

STATUS_COUNT_RE = re.compile(r"^- `(?P<status>[^`]+)`: (?P<count>\d+)\s*$", re.MULTILINE)
LEGACY_STATUS_RE = re.compile(
    r"(?:partial\s*/\s*needs\s+update|needs[_ -]?update|still\s+partial|status:\s*partial\b|"
    r"partial_narrow|retained_partial|external_blocked_candidate)",
    re.IGNORECASE,
)


def _read_text(root: Path, rel_path: Path | str) -> str:
    path = root / rel_path
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _status_counts(index_text: str) -> dict[str, int]:
    return {match.group("status"): int(match.group("count")) for match in STATUS_COUNT_RE.finditer(index_text)}


def _topic_row(index_text: str, topic_id: str) -> dict[str, Any]:
    lines = index_text.splitlines()
    for line_no, line in enumerate(lines, start=1):
        if topic_id not in line:
            continue
        following = ""
        for candidate in lines[line_no:]:
            if candidate.strip():
                following = candidate
                break
        combined = f"{line}\n{following}"
        return {
            "line_no": line_no,
            "text": combined,
            "has_external_blocked": f"`{TARGET_STATUS}`" in combined,
        }
    return {"line_no": None, "text": "", "has_external_blocked": False}


def _decision_status(root: Path, topic: dict[str, str]) -> dict[str, Any]:
    decision_path = Path(topic["decision"])
    text = _read_text(root, decision_path)
    legacy_hits = _legacy_hits_for_text(decision_path, text)
    return {
        "topic_id": topic["id"],
        "decision_file": decision_path.as_posix(),
        "exists": (root / decision_path).is_file(),
        "canonical_status": TARGET_STATUS if f"`{TARGET_STATUS}`" in text else "missing",
        "has_external_blocked": f"`{TARGET_STATUS}`" in text,
        "legacy_status_hits": legacy_hits,
        "current_status_problem_count": len(legacy_hits),
    }


def _legacy_hits_for_text(rel_path: Path, text: str) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if LEGACY_STATUS_RE.search(line):
            hits.append({"path": rel_path.as_posix(), "line": line_no, "text": line.strip()})
    return hits


def _legacy_status_inventory(root: Path, topics: tuple[dict[str, str], ...]) -> dict[str, Any]:
    decision_paths = {Path(topic["decision"]) for topic in topics}
    current_problem_hits: list[dict[str, Any]] = []
    legacy_hits: list[dict[str, Any]] = []

    for topic in topics:
        topic_dir = root / topic["dir"]
        if not topic_dir.is_dir():
            current_problem_hits.append(
                {"path": topic["dir"], "line": None, "text": "topic directory missing"}
            )
            continue
        for path in sorted(topic_dir.glob("*.md")):
            rel_path = path.relative_to(root)
            hits = _legacy_hits_for_text(rel_path, _read_text(root, rel_path))
            if not hits:
                continue
            if rel_path in decision_paths or path.name == "README.md":
                current_problem_hits.extend(hits)
            else:
                legacy_hits.extend(hits)

    by_file: dict[str, int] = {}
    for hit in legacy_hits:
        by_file[hit["path"]] = by_file.get(hit["path"], 0) + 1

    return {
        "current_status_problem_count": len(current_problem_hits),
        "current_status_problem_hits": current_problem_hits,
        "legacy_status_mention_count": len(legacy_hits),
        "legacy_status_mentions_by_file": [
            {"path": path, "count": count} for path, count in sorted(by_file.items())
        ],
        "meaning": (
            "legacy mentions are pre-Wave27 snapshots only; current topic status is owned by "
            "Wave27 decision files plus ARCHIVE_EXTERNAL_BLOCKED/INDEX.md"
        ),
    }


def _build_graph_gate(root: Path) -> dict[str, Any]:
    snapshot = build_graph_gate_snapshot(repo_root=root)
    failures = validate_graph_gate_snapshot(snapshot)
    return {
        "name": "graph_editing_audit_durability",
        "status": snapshot.get("status"),
        "passed": snapshot.get("status") == "passed" and not failures,
        "readiness_state": snapshot.get("readiness_state"),
        "closure_claim": snapshot.get("closure_claim"),
        "repo_local_audit_readback_validated": snapshot.get("repo_local_audit_readback_validated"),
        "graphpage_audit_controls_validated": snapshot.get("graphpage_audit_controls_validated"),
        "live_db_audit_durability_validated": snapshot.get("live_db_audit_durability_validated"),
        "live_tenant_db_audit_open": snapshot.get("live_tenant_db_audit_open"),
        "validation_failures": failures,
    }


def _build_typed_writing_gate(root: Path) -> dict[str, Any]:
    inventory = build_typed_writing_inventory(root)
    return {
        "name": "typed_writing_live_boundary",
        "status": inventory.get("status"),
        "passed": inventory.get("status") == "passed" and not inventory.get("failures"),
        "readiness_state": inventory.get("readiness_state"),
        "closure_claim_allowed": inventory.get("closure_claim_allowed"),
        "deterministic_coverage_count": len(inventory.get("deterministic_coverage") or []),
        "remaining_live_gaps": list(inventory.get("remaining_live_gaps") or []),
        "failures": list(inventory.get("failures") or []),
    }


def _build_consumer_gate(root: Path) -> dict[str, Any]:
    result = build_consumer_closure_check(root)
    consumer_topic = result.get("decision", {}).get("topics", {}).get("2026-03-14-consumer-side-modularization", {})
    return {
        "name": "consumer_side_wave27_closure",
        "status": result.get("status"),
        "passed": result.get("status") == "passed" and not result.get("repo_local_blockers"),
        "gate_count": result.get("validation", {}).get("gate_count"),
        "passed_gate_count": result.get("validation", {}).get("passed_gate_count"),
        "repo_local_blockers": list(result.get("repo_local_blockers") or []),
        "external_blockers": list(result.get("external_blockers") or []),
        "pre_migration_decision_status": consumer_topic.get("status"),
    }


def build_check(repo_root: Path | str = REPO_ROOT) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    current_dev_text = _read_text(root, CURRENT_DEV_INDEX)
    external_index_text = _read_text(root, EXTERNAL_BLOCKED_INDEX)
    counts = _status_counts(current_dev_text)

    topic_statuses = []
    for topic in TOPICS:
        decision = _decision_status(root, topic)
        external_row = _topic_row(external_index_text, topic["id"])
        topic_statuses.append(
            {
                **decision,
                "external_blocked_index_row": external_row,
                "current_dev_active_status": "absent_from_active_partial"
                if counts.get("partial", 0) == 0
                else "current_dev_partial_count_open",
            }
        )

    report = {
        "contract_version": CONTRACT_VERSION,
        "scope": "graph_typed_writing_consumer_external_blocked_status_semantics",
        "status": "passed",
        "topics": topic_statuses,
        "current_dev_status_counts": counts,
        "repo_local_gates": {
            "graph": _build_graph_gate(root),
            "typed_writing": _build_typed_writing_gate(root),
            "consumer": _build_consumer_gate(root),
        },
        "legacy_status_semantics": _legacy_status_inventory(root, TOPICS),
    }
    failures = validate_report(report)
    report["validation"] = {"passed": not failures, "failures": failures}
    report["status"] = "passed" if not failures else "failed"
    return report


def validate_report(report: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if report.get("contract_version") != CONTRACT_VERSION:
        failures.append("contract_version_mismatch")

    if report.get("current_dev_status_counts", {}).get("partial") != 0:
        failures.append("current_dev_partial_count_must_remain_zero")

    for topic in report.get("topics") or []:
        topic_id = topic.get("topic_id")
        if topic.get("exists") is not True:
            failures.append(f"missing_decision_file:{topic_id}")
        if topic.get("canonical_status") != TARGET_STATUS:
            failures.append(f"missing_external_blocked_decision:{topic_id}")
        if topic.get("external_blocked_index_row", {}).get("has_external_blocked") is not True:
            failures.append(f"external_blocked_index_missing_status:{topic_id}")
        if topic.get("current_status_problem_count") != 0:
            failures.append(f"decision_file_contains_legacy_status_terms:{topic_id}")

    gates = report.get("repo_local_gates") or {}
    graph = gates.get("graph") or {}
    if graph.get("passed") is not True:
        failures.append("graph_repo_local_gate_failed")
    if graph.get("closure_claim") is not False or graph.get("live_tenant_db_audit_open") is not True:
        failures.append("graph_gate_must_keep_live_db_external_boundary")

    typed_writing = gates.get("typed_writing") or {}
    if typed_writing.get("passed") is not True:
        failures.append("typed_writing_repo_local_gate_failed")
    if typed_writing.get("closure_claim_allowed") is not False:
        failures.append("typed_writing_gate_must_not_allow_closure_claim")
    if not typed_writing.get("remaining_live_gaps"):
        failures.append("typed_writing_gate_must_preserve_external_live_gaps")

    consumer = gates.get("consumer") or {}
    if consumer.get("passed") is not True:
        failures.append("consumer_repo_local_gate_failed")
    if consumer.get("repo_local_blockers"):
        failures.append("consumer_gate_must_have_no_repo_local_blockers")
    if not consumer.get("external_blockers"):
        failures.append("consumer_gate_must_preserve_live_external_blocker")

    semantics = report.get("legacy_status_semantics") or {}
    if semantics.get("current_status_problem_count") != 0:
        failures.append("legacy_partial_needs_update_terms_leaked_into_current_status_files")

    return failures


def _print_text(report: dict[str, Any]) -> None:
    print(
        "OK graph_typed_writing_consumer_status_boundary=passed"
        if report.get("status") == "passed"
        else "FAIL graph_typed_writing_consumer_status_boundary=failed"
    )
    print(f"contract_version={report['contract_version']}")
    print(f"current_dev_partial={report['current_dev_status_counts'].get('partial')}")
    for topic in report["topics"]:
        print(f"{topic['topic_id']}={topic['canonical_status']}")
    print("repo_local_gates:")
    for key, gate in report["repo_local_gates"].items():
        print(f"- {key}: {'passed' if gate['passed'] else 'failed'}")
    semantics = report["legacy_status_semantics"]
    print(f"legacy_status_mentions={semantics['legacy_status_mention_count']}")
    print(f"current_status_problem_count={semantics['current_status_problem_count']}")
    if report["validation"]["failures"]:
        print("failures:")
        for failure in report["validation"]["failures"]:
            print(f"- {failure}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check graph/typed/writing/consumer status boundary semantics.")
    parser.add_argument("--root", default=str(REPO_ROOT), help="repository root")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    report = build_check(args.root)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_text(report)
    return 0 if report.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
