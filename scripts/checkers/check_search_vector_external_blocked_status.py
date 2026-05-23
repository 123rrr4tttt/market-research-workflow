#!/usr/bin/env python3
"""Read back external-blocked status for search/vector adjacent topics.

This checker is intentionally read-only. It exists to keep follow-up agents from
re-opening these migrated topics as ordinary CURRENT_DEV partial work when the
repo-local gates are already closed and only external runtime/provider evidence
remains.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ARCHIVE_ROOT = Path("development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED")
CURRENT_DEV_INDEX = Path("development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md")
ARCHIVE_INDEX = ARCHIVE_ROOT / "INDEX.md"


@dataclass(frozen=True)
class TopicContract:
    key: str
    title: str
    directory: Path
    entrypoint: Path
    latest_decision: Path
    status_tokens: tuple[str, ...]
    remaining_condition_tokens: tuple[str, ...]


@dataclass(frozen=True)
class Problem:
    path: Path
    message: str


TOPICS: tuple[TopicContract, ...] = (
    TopicContract(
        key="open_search",
        title="Local Open Search Provider Isolation",
        directory=ARCHIVE_ROOT / "2026-05-14-local-open-search-provider-isolation",
        entrypoint=Path("INDEX.md"),
        latest_decision=Path("16_wave22-external-blocked-decision-2026-05-22.md"),
        status_tokens=("external_blocked", "wave22_checked"),
        remaining_condition_tokens=(
            "SearXNG / YaCy live availability",
            "live result quality",
            "operator approval gate",
            "`provider=auto` promotion",
        ),
    ),
    TopicContract(
        key="vector",
        title="Global Vectorization General Foundation",
        directory=ARCHIVE_ROOT / "2026-05-14-global-vectorization-general-foundation",
        entrypoint=Path("INDEX.md"),
        latest_decision=Path("11_wave30-vector-closure-external-blocked-decision-2026-05-23.md"),
        status_tokens=("external_blocked", "wave30_checked"),
        remaining_condition_tokens=(
            "live embedding provider",
            "semantic_embedding_quality_not_proven",
            "production vector quality",
        ),
    ),
    TopicContract(
        key="open_source",
        title="Open Source Platform Integration",
        directory=ARCHIVE_ROOT / "2026-03-01-open-source-platform-integration",
        entrypoint=Path("INDEX.md"),
        latest_decision=Path("09_wave30-open-source-external-blocked-decision-2026-05-23.md"),
        status_tokens=("external_blocked", "wave30_checked"),
        remaining_condition_tokens=(
            "live provider",
            "local_open_search_live_quality_not_sealed",
            "semantic_embedding_quality_not_proven",
            "oss_node_platform_io_sla_not_closed",
        ),
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read back external-blocked status for open-search/vector/open-source topics."
    )
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument("--out", help="Optional JSON output path.")
    return parser.parse_args()


def read_text(path: Path, problems: list[Problem]) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        problems.append(Problem(path, "file is missing"))
    except UnicodeDecodeError as exc:
        problems.append(Problem(path, f"file is not valid UTF-8: {exc}"))
    return ""


def check_contains(path: Path, text: str, tokens: tuple[str, ...], problems: list[Problem]) -> None:
    for token in tokens:
        if token not in text:
            problems.append(Problem(path, f"missing token: {token}"))


def first_section(text: str) -> str:
    marker = "\n## 文件"
    if marker in text:
        return text.split(marker, 1)[0]
    return "\n".join(text.splitlines()[:40])


def topic_readback(repo_root: Path, topic: TopicContract, problems: list[Problem]) -> dict[str, Any]:
    directory = repo_root / topic.directory
    entrypoint = directory / topic.entrypoint
    latest_decision = directory / topic.latest_decision
    current_dev_shadow = repo_root / "development/latest-dev-docs/development-plans/CURRENT_DEV" / topic.directory.name

    topic_status: dict[str, Any] = {
        "key": topic.key,
        "title": topic.title,
        "directory": topic.directory.as_posix(),
        "entrypoint": (topic.directory / topic.entrypoint).as_posix(),
        "latest_decision": (topic.directory / topic.latest_decision).as_posix(),
        "status": "unknown",
    }

    if not directory.is_dir():
        problems.append(Problem(topic.directory, "topic directory is missing from ARCHIVE_EXTERNAL_BLOCKED"))
        return topic_status
    if current_dev_shadow.exists():
        problems.append(Problem(current_dev_shadow.relative_to(repo_root), "topic also exists under CURRENT_DEV"))

    entrypoint_text = read_text(entrypoint, problems)
    decision_text = read_text(latest_decision, problems)
    if entrypoint_text:
        entrypoint_rel = topic.directory / topic.entrypoint
        check_contains(entrypoint_rel, first_section(entrypoint_text), topic.status_tokens, problems)
        check_contains(entrypoint_rel, entrypoint_text, (topic.latest_decision.as_posix(),), problems)
        check_contains(entrypoint_rel, entrypoint_text, topic.remaining_condition_tokens, problems)
    if decision_text:
        check_contains(topic.directory / topic.latest_decision, decision_text, topic.status_tokens, problems)
        check_contains(topic.directory / topic.latest_decision, decision_text, topic.remaining_condition_tokens, problems)

    topic_status["status"] = "external_blocked"
    topic_status["status_tokens"] = list(topic.status_tokens)
    topic_status["remaining_condition_tokens"] = list(topic.remaining_condition_tokens)
    return topic_status


def check_navigation(repo_root: Path, topics: tuple[TopicContract, ...], problems: list[Problem]) -> dict[str, Any]:
    archive_index_text = read_text(repo_root / ARCHIVE_INDEX, problems)
    current_index_text = read_text(repo_root / CURRENT_DEV_INDEX, problems)
    surfaces: dict[str, Any] = {
        "archive_index": ARCHIVE_INDEX.as_posix(),
        "current_dev_index": CURRENT_DEV_INDEX.as_posix(),
    }

    for topic in topics:
        entry_link_from_archive = f"./{topic.directory.name}/{topic.entrypoint.as_posix()}"
        entry_link_from_current = f"../ARCHIVE_EXTERNAL_BLOCKED/{topic.directory.name}/{topic.entrypoint.as_posix()}"
        if archive_index_text and entry_link_from_archive not in archive_index_text:
            problems.append(Problem(ARCHIVE_INDEX, f"missing archive entrypoint link for {topic.key}"))
        if current_index_text:
            if entry_link_from_current not in current_index_text:
                problems.append(Problem(CURRENT_DEV_INDEX, f"missing CURRENT_DEV external-blocked link for {topic.key}"))
            current_lines = [
                line for line in current_index_text.splitlines() if topic.directory.name in line and "external_blocked" not in line
            ]
            if current_lines:
                problems.append(
                    Problem(
                        CURRENT_DEV_INDEX,
                        f"{topic.key} has non-external_blocked CURRENT_DEV references: {current_lines[:3]}",
                    )
                )
    return surfaces


def main() -> int:
    args = parse_args()
    repo_root = Path(args.root).resolve()
    problems: list[Problem] = []

    topics = [topic_readback(repo_root, topic, problems) for topic in TOPICS]
    surfaces = check_navigation(repo_root, TOPICS, problems)

    result: dict[str, Any] = {
        "status": "passed" if not problems else "failed",
        "contract_version": "search-vector-external-blocked-status.v1",
        "scope": "open-search/vector/open-source external-blocked status readback",
        "topics": topics,
        "navigation_surfaces": surfaces,
        "problems": [{"path": problem.path.as_posix(), "message": problem.message} for problem in problems],
    }

    if args.out:
        out_path = repo_root / args.out
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
