#!/usr/bin/env python3
"""Focused tests for search/vector external-blocked status readback."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "checkers"
    / "check_search_vector_external_blocked_status.py"
)
SPEC = importlib.util.spec_from_file_location("check_search_vector_external_blocked_status", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def build_topic_index(topic: checker.TopicContract) -> str:
    return "\n".join(
        [
            f"# {topic.title} Index",
            "",
            "状态：`" + "` / `".join(topic.status_tokens) + "`。",
            "",
            "Remaining conditions:",
            *[f"- {token}" for token in topic.remaining_condition_tokens],
            "",
            "## 文件",
            "",
            f"- [{topic.latest_decision.name}](./{topic.latest_decision.name})",
            "",
        ]
    )


def build_topic_decision(topic: checker.TopicContract) -> str:
    return "\n".join(
        [
            f"# {topic.title} Decision",
            "",
            "状态：`" + "` / `".join(topic.status_tokens) + "`。",
            "",
            "Remaining conditions:",
            *[f"- {token}" for token in topic.remaining_condition_tokens],
            "",
        ]
    )


class SearchVectorExternalBlockedStatusTestCase(unittest.TestCase):
    def make_repo(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)

        (root / checker.ARCHIVE_ROOT).mkdir(parents=True)
        (root / checker.CURRENT_DEV_INDEX.parent).mkdir(parents=True)
        archive_lines = ["# Archive External Blocked", ""]
        current_lines = ["# Current Dev", ""]

        for topic in checker.TOPICS:
            topic_dir = root / topic.directory
            topic_dir.mkdir(parents=True)
            (topic_dir / topic.entrypoint).write_text(build_topic_index(topic), encoding="utf-8")
            (topic_dir / topic.latest_decision).write_text(build_topic_decision(topic), encoding="utf-8")
            archive_lines.append(f"- [{topic.title}](./{topic.directory.name}/{topic.entrypoint.as_posix()})")
            current_lines.append(
                f"- `external_blocked` [{topic.title}](../ARCHIVE_EXTERNAL_BLOCKED/{topic.directory.name}/{topic.entrypoint.as_posix()})"
            )

        (root / checker.ARCHIVE_INDEX).write_text("\n".join(archive_lines) + "\n", encoding="utf-8")
        (root / checker.CURRENT_DEV_INDEX).write_text("\n".join(current_lines) + "\n", encoding="utf-8")
        return root

    def test_readback_passes_complete_fixture(self) -> None:
        root = self.make_repo()
        problems: list[checker.Problem] = []

        topic_results = [checker.topic_readback(root, topic, problems) for topic in checker.TOPICS]
        checker.check_navigation(root, checker.TOPICS, problems)

        self.assertEqual([], problems)
        self.assertEqual(["external_blocked"] * 3, [item["status"] for item in topic_results])

    def test_readback_rejects_missing_entrypoint(self) -> None:
        root = self.make_repo()
        open_source = checker.TOPICS[-1]
        (root / open_source.directory / open_source.entrypoint).unlink()
        problems: list[checker.Problem] = []

        checker.topic_readback(root, open_source, problems)

        self.assertTrue(any("file is missing" in problem.message for problem in problems), problems)

    def test_navigation_rejects_current_dev_non_external_reference(self) -> None:
        root = self.make_repo()
        open_search = checker.TOPICS[0]
        with (root / checker.CURRENT_DEV_INDEX).open("a", encoding="utf-8") as handle:
            handle.write(f"- `partial` [bad](../ARCHIVE_EXTERNAL_BLOCKED/{open_search.directory.name}/INDEX.md)\n")
        problems: list[checker.Problem] = []

        checker.check_navigation(root, checker.TOPICS, problems)

        self.assertTrue(any("non-external_blocked" in problem.message for problem in problems), problems)


if __name__ == "__main__":
    unittest.main()
