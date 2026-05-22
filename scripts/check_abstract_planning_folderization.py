#!/usr/bin/env python3
"""Check the abstract-planning folderization package.

The check is intentionally read-only. It treats missing topic directories or
missing starter documents as hard failures, and reports section-contract drift
as a gap list unless --strict-content is used.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable


EXPECTED_TOPICS = [
    "writing-workbench-evolution",
    "typed-knowledge-organization",
    "graph-editing-and-reporting",
    "ingest-digestion-and-long-cycle-automation",
    "crawler-source-expansion",
    "frontend-i18n-theme-modularization",
    "llm-service-and-agent-platformization",
    "dual-frontend-workbench-topology",
]

COORDINATION_FILES = [
    "01_abstract-planning-folderization-plan-2026-03-07.md",
    "02_atomic-tasklist-abstract-planning-folderization-2026-03-07.md",
    "03_feature-implementation-orchestration-2026-03-08.md",
    "抽象规划.md",
]

PLAN_SECTION_RULES = {
    "goal_or_objective": [r"^##\s+\d+\.\s+(Goal|Goals|Objective|Objectives)\b"],
    "current_baseline": [r"^##\s+\d+\.\s+(Verified\s+)?Current Baseline\b"],
    "requirement_clarification": [r"^##\s+\d+\.\s+Requirement Clarification(s)?\b"],
    "scope_non_goals": [r"^##\s+\d+\.\s+Scope and Non-Goals\b"],
    "recommended_solution": [
        r"^##\s+\d+\.\s+Recommended (Layering|Architecture|Topology|.*Plan Shape)\b"
    ],
    "implementation_order": [r"^##\s+\d+\.\s+(Recommended )?Implementation Order\b"],
    "serial_parallel": [r"^##\s+\d+\.\s+(Serial and Parallel|Parallel and Serial|Parallel vs Serial)"],
    "minimum_validation": [r"^##\s+\d+\.\s+Minim(al|um) Validation\b"],
}

TASK_SECTION_RULES = {
    "execution_status_snapshot": [r"^##\s+Execution Status Snapshot\b"],
    "serial_parallel_rules": [r"^##\s+Global Serial-Parallel Rules\b"],
    "module_boundary": [r"^##\s+Global Module Boundary( Rules)?\b"],
    "atomic_tasks": [r"^##\s+Task\s+"],
}


def has_any_pattern(text: str, patterns: Iterable[str]) -> bool:
    return any(re.search(pattern, text, flags=re.MULTILINE) for pattern in patterns)


def missing_sections(text: str, rules: dict[str, list[str]]) -> list[str]:
    return [name for name, patterns in rules.items() if not has_any_pattern(text, patterns)]


def one_file(files: list[Path], label: str) -> tuple[str | None, str | None]:
    if len(files) == 1:
        return files[0].as_posix(), None
    if not files:
        return None, f"missing {label}"
    return None, f"ambiguous {label}: {', '.join(path.name for path in files)}"


def resolve_coordination_dir(root: Path) -> tuple[Path, str]:
    current_dev = root / "development/latest-dev-docs/development-plans/CURRENT_DEV"
    current_coordination_dir = current_dev / "2026-03-07-后续安排"
    if current_coordination_dir.is_dir():
        return current_coordination_dir, "current_dev"
    archive_coordination_dir = (
        root / "development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-03-07-后续安排"
    )
    if archive_coordination_dir.is_dir():
        return archive_coordination_dir, "archive_closed"
    return current_coordination_dir, "missing"


def build_report(root: Path) -> dict:
    current_dev = root / "development/latest-dev-docs/development-plans/CURRENT_DEV"
    coordination_dir, coordination_location = resolve_coordination_dir(root)

    hard_failures: list[str] = []
    content_gaps: list[str] = []

    if not coordination_dir.is_dir():
        hard_failures.append(f"missing coordination directory: {coordination_dir.as_posix()}")
        return {
            "coordination_dir": coordination_dir.as_posix(),
            "coordination_location": coordination_location,
            "hard_failures": hard_failures,
            "content_gaps": content_gaps,
            "topics": [],
        }

    coordination_missing = [
        name for name in COORDINATION_FILES if not (coordination_dir / name).is_file()
    ]
    for name in coordination_missing:
        hard_failures.append(f"missing coordination file: {coordination_dir / name}")

    topics = []
    for topic in EXPECTED_TOPICS:
        topic_dir = current_dev / f"2026-03-07-{topic}"
        item = {
            "topic": topic,
            "directory": topic_dir.as_posix(),
            "directory_exists": topic_dir.is_dir(),
            "plan_file": None,
            "task_file": None,
            "missing_plan_sections": [],
            "missing_task_sections": [],
        }

        if not topic_dir.is_dir():
            hard_failures.append(f"missing topic directory: {topic_dir.as_posix()}")
            topics.append(item)
            continue

        plan_path, plan_error = one_file(sorted(topic_dir.glob("01_*.md")), "01 plan")
        task_path, task_error = one_file(sorted(topic_dir.glob("02_*.md")), "02 tasklist")
        if plan_error:
            hard_failures.append(f"{topic}: {plan_error}")
        if task_error:
            hard_failures.append(f"{topic}: {task_error}")
        item["plan_file"] = plan_path
        item["task_file"] = task_path

        if plan_path:
            text = Path(plan_path).read_text(encoding="utf-8")
            item["missing_plan_sections"] = missing_sections(text, PLAN_SECTION_RULES)
            for section in item["missing_plan_sections"]:
                content_gaps.append(f"{topic}: 01 plan missing {section}")

        if task_path:
            text = Path(task_path).read_text(encoding="utf-8")
            item["missing_task_sections"] = missing_sections(text, TASK_SECTION_RULES)
            for section in item["missing_task_sections"]:
                content_gaps.append(f"{topic}: 02 tasklist missing {section}")

        topics.append(item)

    return {
        "coordination_dir": coordination_dir.as_posix(),
        "coordination_location": coordination_location,
        "coordination_files": [
            (coordination_dir / name).as_posix() for name in COORDINATION_FILES
        ],
        "hard_failures": hard_failures,
        "content_gaps": content_gaps,
        "topics": topics,
    }


def print_markdown(report: dict) -> None:
    print("# Abstract Planning Folderization Check")
    print()
    print(f"- coordination_dir: `{report['coordination_dir']}`")
    print(f"- coordination_location: `{report['coordination_location']}`")
    print(f"- hard_failures: {len(report['hard_failures'])}")
    print(f"- content_gaps: {len(report['content_gaps'])}")
    print()

    if report["hard_failures"]:
        print("## Hard Failures")
        print()
        for item in report["hard_failures"]:
            print(f"- {item}")
        print()

    if report["content_gaps"]:
        print("## Content Gaps")
        print()
        for item in report["content_gaps"]:
            print(f"- {item}")
        print()

    print("## Topic Matrix")
    print()
    print("| Topic | Directory | 01 | 02 | Plan gaps | Task gaps |")
    print("|---|---|---|---|---|---|")
    for item in report["topics"]:
        plan_gaps = ", ".join(item["missing_plan_sections"]) or "-"
        task_gaps = ", ".join(item["missing_task_sections"]) or "-"
        directory_status = "ok" if item["directory_exists"] else "missing"
        plan_status = "ok" if item["plan_file"] else "missing"
        task_status = "ok" if item["task_file"] else "missing"
        print(
            f"| `{item['topic']}` | {directory_status} | {plan_status} | "
            f"{task_status} | {plan_gaps} | {task_gaps} |"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root. Defaults to the current working directory.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON instead of the default Markdown report.",
    )
    parser.add_argument(
        "--strict-content",
        action="store_true",
        help="Return a non-zero status when section-contract content gaps exist.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    report = build_report(root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_markdown(report)

    if report["hard_failures"]:
        return 1
    if args.strict_content and report["content_gaps"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
