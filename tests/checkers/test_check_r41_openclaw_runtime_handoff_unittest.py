#!/usr/bin/env python3
"""Focused tests for the R41 OpenClaw runtime handoff checker."""

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
    / "check_r41_openclaw_runtime_handoff.py"
)
SPEC = importlib.util.spec_from_file_location("check_r41_openclaw_runtime_handoff", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def build_contract_text() -> str:
    mirror_script = checker.load_autodispatch_gate(checker.REPO_ROOT)
    rows = []
    for line_key, fields in mirror_script.EXPECTED_REQUIRED_FIELDS.items():
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


def build_autodispatch_text() -> str:
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
            "- ready_dispatch_count: 0",
            "- parallel_lanes: research(next batch) + development(current batch) + interface-unify(current batch)",
            "- contract_lock_required: yes (development merge depends on interface-unify output)",
            "",
            "| line | task_id | goal | acceptance | minimal_gate | failure_isolation | bundle_doc | research_doc | interface_doc | development_doc |",
            "|---|---|---|---|---|---|---|---|---|---|",
            *rows,
        ]
    )


def build_handoff_text() -> str:
    lines = ["# Codex Handoff — 2026-03-04-scout-r41", ""]
    for line_key in checker.EXPECTED_LINES:
        lines.extend(
            [
                f"line: {line_key}",
                "lane_focus: fixture lane",
                "must_to_atomic:",
                f"- task_id: {line_key}-R41-M1",
                "  goal: first handoff task",
                "  acceptance: deterministic replay proof coverage = 100%",
                "  minimal_gate: replay proof checker green",
                "  failure_isolation: proof missing disables auto-pass",
                f"- task_id: {line_key}-R41-M2",
                "  goal: second handoff task",
                "  acceptance: timeout remediation binding = 100%",
                "  minimal_gate: timeout remediation lint pass",
                "  failure_isolation: binding failure escalates review",
                "",
            ]
        )
    lines.append("runtime_fingerprint is preserved for line D.")
    lines.append("next-batch-trigger: build lane can use the R41 handoff.")
    return "\n".join(lines)


def build_implementation_text(label: str, envelope: str) -> str:
    return "\n".join(
        [
            f"# {label} R41 execution record",
            "",
            "- entry: `/Users/wangyiliang/Desktop/openclaw/artifacts/orchestration/line-autodispatch-2026-03-04-scout-r41.md`",
            "- scope: fixture",
            "- mode: `development(current) + interface-unify(current)`; `research => R42 envelope only`",
            "",
            "## Runtime entry",
            "",
            "- command: `bash scripts/line_unfinished_autodispatch_refresh.sh`",
            "- output: `LINE_AUTODISPATCH_skipped`",
            "- run_state: `state/runs/line-autodispatch-2026-03-04-scout-r41.json`",
            "- reason: `no_unfinished_line_task`",
            "- ready_dispatch_count=0",
            "- no runtime slice: no task is actionable, 未新增 development/interface-unify 切片。",
            "",
            "## Research boundary",
            "",
            f"- R42 research envelope only: `{envelope}`",
        ]
    )


def build_reference_index_text() -> str:
    return "\n".join(
        [
            "# Reference Pool Index — 2026-03-04-scout-r41",
            "",
            "- batch: `2026-03-04-scout-r41`",
            "",
            "## Included",
            *(f"- `{name}`" for name in checker.EXPECTED_REFERENCE_FILES),
        ]
    )


def build_dedup_text() -> str:
    return "\n".join(
        [
            "# Dedup Diff — 2026-03-04-scout-r41",
            "",
            "baseline_batch: 2026-03-04-scout-r41",
            "",
            "## acceptance for handoff",
            "- boundaries: advisory and hard-block boundaries are marked.",
            "- ready_for_r41_buildlane: yes",
        ]
    )


def build_alignment_text() -> str:
    lines = [
        "# Interface Envelope Alignment",
        "",
        "- batch: `2026-03-04-scout-r41`",
        "- total_line_added_keys: 0",
        "",
        "| line | line_added_keys_count | line_added_keys | alignment_action |",
        "|---|---|---|---|",
    ]
    lines.extend(f"| {line_key} | 0 | none | no_new_key |" for line_key in checker.EXPECTED_LINES)
    return "\n".join(lines)


def build_evidence_text(*, live_verified: bool = False) -> str:
    live_value = "true" if live_verified else "false"
    return "\n".join(
        [
            "# Wave15 R41 OpenClaw Runtime Handoff Evidence",
            "",
            "- evidence_id: `wave15_openclaw_runtime_handoff`",
            "- consistency_claim: `repo_local_handoff_mirror_consistent`",
            f"- external_openclaw_runtime_live_verified: `{live_value}`",
            "- external_runtime_checked: `false`",
            "- runtime_handoff_status: `repo_local_handoff_mirror_only`",
            "",
            "## Gates",
            "",
            "- `scripts/checkers/check_r41_openclaw_runtime_handoff.py`",
            "- `scripts/checkers/check_r41_openclaw_autodispatch_gate.py`",
            "",
            "## Mirror",
            "",
            "- `LINE_AUTODISPATCH_skipped`",
            "- `no_unfinished_line_task`",
            "- `ready_dispatch_count=0`",
        ]
    )


class R41OpenClawRuntimeHandoffGateTestCase(unittest.TestCase):
    def make_topic(self, *, implementation_text: str | None = None, evidence_text: str | None = None) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        topic = Path(temp_dir.name)

        (topic / checker.AUTODISPATCH_REL.parent).mkdir(parents=True)
        (topic / checker.AUTODISPATCH_REL).write_text(build_autodispatch_text(), encoding="utf-8")
        (topic / "R41_INTERFACE_CONTRACT.md").write_text(build_contract_text(), encoding="utf-8")

        (topic / checker.CODEX_HANDOFF_REL.parent).mkdir(parents=True)
        (topic / checker.CODEX_HANDOFF_REL).write_text(build_handoff_text(), encoding="utf-8")
        (topic / checker.REFERENCE_INDEX_REL).write_text(build_reference_index_text(), encoding="utf-8")
        (topic / checker.DEDUP_DIFF_REL).write_text(build_dedup_text(), encoding="utf-8")
        (topic / checker.INTERFACE_ALIGNMENT_REL).write_text(build_alignment_text(), encoding="utf-8")
        for name in checker.EXPECTED_REFERENCE_FILES:
            path = topic / checker.REFERENCE_POOL_REL / name
            if not path.exists():
                path.write_text(f"# {name}\n", encoding="utf-8")

        (topic / checker.EVIDENCE_REL.parent).mkdir(parents=True, exist_ok=True)
        for doc in checker.IMPLEMENTATION_DOCS:
            text = implementation_text if implementation_text is not None else build_implementation_text(doc.label, doc.r42_envelope)
            (topic / doc.path).write_text(text, encoding="utf-8")
        (topic / checker.EVIDENCE_REL).write_text(
            evidence_text if evidence_text is not None else build_evidence_text(),
            encoding="utf-8",
        )
        return topic

    def test_checker_accepts_repo_local_handoff_fixture(self) -> None:
        result = checker.check_topic(self.make_topic(), checker.REPO_ROOT)

        self.assertTrue(result.ok, result.problems)
        self.assertEqual(result.mirror_line_rows, 6)
        self.assertEqual(result.handoff_task_count, 12)
        self.assertEqual(result.implementation_doc_count, 3)
        self.assertEqual(result.reference_file_count, 11)

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

    def test_checker_rejects_implementation_without_skipped_runtime_marker(self) -> None:
        implementation_text = build_implementation_text("broken", "AB-envelope.md").replace(
            "LINE_AUTODISPATCH_skipped",
            "LINE_AUTODISPATCH_live_run",
        )

        result = checker.check_topic(self.make_topic(implementation_text=implementation_text), checker.REPO_ROOT)

        self.assertFalse(result.ok)
        self.assertTrue(any("LINE_AUTODISPATCH_skipped" in problem.message for problem in result.problems), result.problems)

    def test_checker_rejects_external_live_runtime_claim(self) -> None:
        result = checker.check_topic(
            self.make_topic(evidence_text=build_evidence_text(live_verified=True)),
            checker.REPO_ROOT,
        )

        self.assertFalse(result.ok)
        self.assertTrue(any("external OpenClaw runtime live verification" in problem.message for problem in result.problems), result.problems)

    def test_checker_rejects_empty_required_reference_documents(self) -> None:
        topic = self.make_topic()
        (topic / checker.CODEX_HANDOFF_REL).write_text("", encoding="utf-8")
        (topic / checker.REFERENCE_INDEX_REL).write_text("", encoding="utf-8")
        (topic / checker.DEDUP_DIFF_REL).write_text("", encoding="utf-8")
        (topic / checker.INTERFACE_ALIGNMENT_REL).write_text("", encoding="utf-8")
        (topic / checker.EVIDENCE_REL).write_text("", encoding="utf-8")

        result = checker.check_topic(topic, checker.REPO_ROOT)

        self.assertFalse(result.ok)
        empty_paths = {problem.path.resolve() for problem in result.problems if problem.message == "required document is empty"}
        self.assertIn((topic / checker.CODEX_HANDOFF_REL).resolve(), empty_paths)
        self.assertIn((topic / checker.REFERENCE_INDEX_REL).resolve(), empty_paths)
        self.assertIn((topic / checker.DEDUP_DIFF_REL).resolve(), empty_paths)
        self.assertIn((topic / checker.INTERFACE_ALIGNMENT_REL).resolve(), empty_paths)
        self.assertIn((topic / checker.EVIDENCE_REL).resolve(), empty_paths)


if __name__ == "__main__":
    unittest.main()
