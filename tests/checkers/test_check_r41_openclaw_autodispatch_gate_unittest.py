#!/usr/bin/env python3
"""Focused tests for the R41 OpenClaw autodispatch checker."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "checkers"
    / "check_r41_openclaw_autodispatch_gate.py"
)
SPEC = importlib.util.spec_from_file_location("check_r41_openclaw_autodispatch_gate", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def build_contract_text() -> str:
    rows = []
    for line_key, fields in checker.EXPECTED_REQUIRED_FIELDS.items():
        rows.append(f"- {line_key}: " + ", ".join(f"`{field}`" for field in fields))
    return "\n".join(
        [
            "# R41 Interface Contract",
            "",
            "Version: `R41`",
            "Source batch: `2026-03-04-scout-r41`",
            "",
            "## R41 Required Fields (by line)",
            "",
            *rows,
            "",
            "## Compatibility",
            "",
            "- All contracts are R41-compatible.",
        ]
    )


def build_autodispatch_text(ready_dispatch_count: str = "0") -> str:
    rows = []
    for line_key in checker.EXPECTED_LINES:
        rows.append(f"| {line_key} | none | none | none | none | none | no_unfinished_task |  |  |  |")
    return "\n".join(
        [
            "# Line Auto Dispatch",
            "",
            "- batch: `2026-03-04-scout-r41`",
            "- status: `skipped`",
            "- reason: no_unfinished_line_task",
            f"- ready_dispatch_count: {ready_dispatch_count}",
            "- parallel_lanes: research(next batch) + development(current batch) + interface-unify(current batch)",
            "- contract_lock_required: yes (development merge depends on interface-unify output)",
            "",
            "| line | task_id | goal | acceptance | minimal_gate | failure_isolation | bundle_doc | research_doc | interface_doc | development_doc |",
            "|---|---|---|---|---|---|---|---|---|---|",
            *rows,
        ]
    )


class R41OpenClawAutodispatchGateTestCase(unittest.TestCase):
    def make_topic(self, *, ready_dispatch_count: str = "0", contract_text: str | None = None) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        topic = Path(temp_dir.name)
        (topic / checker.AUTODISPATCH_REL.parent).mkdir(parents=True)
        (topic / checker.AUTODISPATCH_REL).write_text(
            build_autodispatch_text(ready_dispatch_count=ready_dispatch_count),
            encoding="utf-8",
        )
        (topic / checker.INTERFACE_CONTRACT_REL).write_text(
            contract_text if contract_text is not None else build_contract_text(),
            encoding="utf-8",
        )
        return topic

    def test_checker_accepts_skipped_no_unfinished_fixture(self) -> None:
        result = checker.check_topic(self.make_topic())

        self.assertTrue(result.ok, result.problems)
        self.assertEqual(result.line_count, 6)
        self.assertEqual(result.required_field_count, 26)

    def test_parse_args_accepts_repo_root_alias(self) -> None:
        with patch.object(sys, "argv", ["checker", "--repo-root", "/tmp/repo"]):
            args = checker.parse_args()

        self.assertEqual(args.root, "/tmp/repo")

    def test_resolve_topic_path_prefers_existing_archive_topic(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            topic = root / checker.ARCHIVE_EXTERNAL_BLOCKED_TOPIC_REL
            topic.mkdir(parents=True)

            self.assertEqual(checker.resolve_topic_path(root), topic)

    def test_checker_rejects_nonzero_ready_dispatch_count(self) -> None:
        result = checker.check_topic(self.make_topic(ready_dispatch_count="1"))

        self.assertFalse(result.ok)
        self.assertTrue(
            any("ready_dispatch_count" in problem.message for problem in result.problems),
            result.problems,
        )

    def test_checker_rejects_missing_required_interface_field(self) -> None:
        contract_text = build_contract_text().replace("`expiry_guard`", "`expiry_missing`")

        result = checker.check_topic(self.make_topic(contract_text=contract_text))

        self.assertFalse(result.ok)
        self.assertTrue(
            any("expiry_guard" in problem.message for problem in result.problems),
            result.problems,
        )


if __name__ == "__main__":
    unittest.main()
