#!/usr/bin/env python3
"""Focused tests for development-plans target topic matrix checker."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "checkers"
    / "check_development_plans_status_matrix.py"
)
SPEC = importlib.util.spec_from_file_location("check_development_plans_status_matrix", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


class DevelopmentPlansTargetTopicMatrixTestCase(unittest.TestCase):
    def make_repo(self, *, partial: int = 0, dev_plans_extra: str = "") -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)

        dev_plans = root / checker.DEV_PLANS_ROOT
        current_dev = root / checker.CURRENT_DEV
        current_dev.mkdir(parents=True)
        (current_dev / "main").mkdir()

        (dev_plans / "INDEX.md").write_text(
            "\n".join(
                [
                    "# Development Plans Index",
                    "",
                    "- [CURRENT_DEV/INDEX.md](./CURRENT_DEV/INDEX.md)",
                    dev_plans_extra,
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (current_dev / "INDEX.md").write_text(
            "\n".join(
                [
                    "# CURRENT_DEV Index",
                    "",
                    "## 剩余状态分布",
                    "",
                    f"- `partial`: {partial}",
                    "- `not_closed`: 0",
                    "- `no_closure_claim`: 0",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        closed = root / "docs/development/development-plans/ARCHIVE_CLOSED"
        external = root / checker.DEV_PLANS_ROOT / "ARCHIVE_EXTERNAL_BLOCKED"
        retired = root / checker.DEV_PLANS_ROOT / "ARCHIVE_RETIRED"
        for archive_root in (closed, external, retired):
            archive_root.mkdir(parents=True)
            (archive_root / "INDEX.md").write_text("# Archive\n", encoding="utf-8")

        for navigation in (
            "A_ARCHITECTURE",
            "B_API",
            "C_INGEST",
            "D_TEST",
            "E_OPS",
            "F_PLAN",
            "G_REVIEW",
            "main",
            "ARCHIVE_CLOSED",
        ):
            (dev_plans / navigation).mkdir(parents=True, exist_ok=True)
        (root / "docs/development/development-plans/main").mkdir(parents=True)
        (root / "development/latest-dev-docs/automation-runs").mkdir(parents=True)
        (root / "docs/development/development-plans/archive-closed-file-classification-2026-05-23.json").write_text(
            "{}\n", encoding="utf-8"
        )

        allowlist = {
            "schema": "development-plans-target-topic-allowlist/v1",
            "target_roots": [
                {
                    "path": checker.CURRENT_DEV.as_posix(),
                    "status": "active_current",
                    "entrypoint": checker.CURRENT_DEV_INDEX.as_posix(),
                    "allowed_non_topic_dirs": ["main"],
                },
                {
                    "path": "docs/development/development-plans/ARCHIVE_CLOSED",
                    "status": "closed",
                    "entrypoint": "docs/development/development-plans/ARCHIVE_CLOSED/INDEX.md",
                    "excluded_topic_dirs": ["process-topic"],
                },
                {
                    "path": (checker.DEV_PLANS_ROOT / "ARCHIVE_EXTERNAL_BLOCKED").as_posix(),
                    "status": "external_blocked",
                    "entrypoint": (checker.DEV_PLANS_ROOT / "ARCHIVE_EXTERNAL_BLOCKED/INDEX.md").as_posix(),
                },
                {
                    "path": (checker.DEV_PLANS_ROOT / "ARCHIVE_RETIRED").as_posix(),
                    "status": "retired",
                    "entrypoint": (checker.DEV_PLANS_ROOT / "ARCHIVE_RETIRED/INDEX.md").as_posix(),
                },
            ],
            "non_target_roots": [
                {"path": (checker.DEV_PLANS_ROOT / "A_ARCHITECTURE").as_posix()},
                {"path": (checker.DEV_PLANS_ROOT / "B_API").as_posix()},
                {"path": (checker.DEV_PLANS_ROOT / "C_INGEST").as_posix()},
                {"path": (checker.DEV_PLANS_ROOT / "D_TEST").as_posix()},
                {"path": (checker.DEV_PLANS_ROOT / "E_OPS").as_posix()},
                {"path": (checker.DEV_PLANS_ROOT / "F_PLAN").as_posix()},
                {"path": (checker.DEV_PLANS_ROOT / "G_REVIEW").as_posix()},
                {"path": (checker.DEV_PLANS_ROOT / "main").as_posix()},
                {"path": (checker.DEV_PLANS_ROOT / "ARCHIVE_CLOSED").as_posix()},
                {"path": "docs/development/development-plans/main"},
            ],
            "evidence_roots": [
                "development/latest-dev-docs/automation-runs",
                "docs/development/development-plans/archive-closed-file-classification-2026-05-23.json",
            ],
        }
        (dev_plans / "TARGET_TOPIC_ALLOWLIST.json").write_text(
            json.dumps(allowlist, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return root

    def test_checker_accepts_clean_zero_current_dev_fixture(self) -> None:
        result = checker.check(self.make_repo())

        self.assertTrue(result.ok, result.problems)
        self.assertEqual({"partial": 0, "not_closed": 0, "no_closure_claim": 0}, result.status_counts)
        self.assertEqual((), tuple(target for target in result.targets if target.status == "active_current"))
        self.assertEqual({}, result.target_profiles)

    def test_checker_expands_target_roots_without_requiring_navigation_dirs_to_close(self) -> None:
        root = self.make_repo()
        topic = root / "docs/development/development-plans/ARCHIVE_CLOSED/closed-topic"
        topic.mkdir()
        (topic / "evidence.md").write_text("# Closed evidence\n\nGate: pytest tests/unit/test_closed.py passed.\n", encoding="utf-8")
        with (root / "docs/development/development-plans/ARCHIVE_CLOSED/INDEX.md").open("a", encoding="utf-8") as handle:
            handle.write("- [Closed Topic](./closed-topic/evidence.md)\n")

        result = checker.check(root)

        self.assertTrue(result.ok, result.problems)
        self.assertIn(
            checker.TargetTopic(
                path=Path("docs/development/development-plans/ARCHIVE_CLOSED/closed-topic"),
                status="closed",
                entrypoint=Path("docs/development/development-plans/ARCHIVE_CLOSED/INDEX.md"),
            ),
            result.targets,
        )
        profile = result.target_profiles[Path("docs/development/development-plans/ARCHIVE_CLOSED/closed-topic")]
        self.assertEqual(1, profile.file_count)

    def test_checker_rejects_current_dev_count_mismatch(self) -> None:
        root = self.make_repo(partial=0)
        topic = root / checker.CURRENT_DEV / "topic-a"
        topic.mkdir()
        (topic / "INDEX.md").write_text("# Topic A\n", encoding="utf-8")

        result = checker.check(root)

        self.assertFalse(result.ok)
        self.assertTrue(any("partial count 0 does not match active_current target count 1" in p.message for p in result.problems))

    def test_checker_rejects_stale_active_partial_count(self) -> None:
        root = self.make_repo(dev_plans_extra="- CURRENT_DEV still reports `partial:33`")

        result = checker.check(root)

        self.assertFalse(result.ok)
        self.assertTrue(any("stale partial count 33" in problem.message for problem in result.problems), result.problems)

    def test_checker_allows_historical_stale_partial_count(self) -> None:
        root = self.make_repo(dev_plans_extra="- historical snapshot: CURRENT_DEV was `partial:33`")

        result = checker.check(root)

        self.assertTrue(result.ok, result.problems)

    def test_checker_rejects_external_blocked_topic_without_evidence(self) -> None:
        root = self.make_repo()
        topic = root / checker.DEV_PLANS_ROOT / "ARCHIVE_EXTERNAL_BLOCKED/external-topic"
        topic.mkdir()
        (topic / "note.md").write_text("# Missing explicit blocker\n", encoding="utf-8")
        with (root / checker.DEV_PLANS_ROOT / "ARCHIVE_EXTERNAL_BLOCKED/INDEX.md").open("a", encoding="utf-8") as handle:
            handle.write("- [External Topic](./external-topic/note.md)\n")

        result = checker.check(root)

        self.assertFalse(result.ok)
        self.assertTrue(any("external blocker evidence" in problem.message for problem in result.problems), result.problems)

    def test_checker_excludes_configured_non_target_roots(self) -> None:
        root = self.make_repo(dev_plans_extra="- historical snapshot: CURRENT_DEV was `partial:33`")

        result = checker.check(root)

        self.assertTrue(result.ok, result.problems)
        self.assertIn(checker.DEV_PLANS_ROOT / "A_ARCHITECTURE", result.non_target_roots)
        self.assertFalse(any(target.path.name == "A_ARCHITECTURE" for target in result.targets))

    def test_checker_rejects_closed_topic_without_code_script_test_or_gate_signal(self) -> None:
        root = self.make_repo()
        topic = root / "docs/development/development-plans/ARCHIVE_CLOSED/weak-closed-topic"
        topic.mkdir()
        (topic / "note.md").write_text("# Weak closed topic\n\nOnly narrative.\n", encoding="utf-8")
        with (root / "docs/development/development-plans/ARCHIVE_CLOSED/INDEX.md").open("a", encoding="utf-8") as handle:
            handle.write("- [Weak Closed Topic](./weak-closed-topic/note.md)\n")

        result = checker.check(root)

        self.assertFalse(result.ok)
        self.assertTrue(any("lacks code/script/test/gate evidence" in problem.message for problem in result.problems), result.problems)

    def test_checker_excludes_configured_process_topic_from_target_expansion(self) -> None:
        root = self.make_repo()
        process_topic = root / "docs/development/development-plans/ARCHIVE_CLOSED/process-topic"
        process_topic.mkdir()
        (process_topic / "note.md").write_text("# Process record\n", encoding="utf-8")

        result = checker.check(root)

        self.assertTrue(result.ok, result.problems)
        self.assertFalse(any(target.path.name == "process-topic" for target in result.targets))

    def test_evidence_profile_detects_code_script_test_gate_and_external_signals(self) -> None:
        root = self.make_repo()
        topic = root / checker.DEV_PLANS_ROOT / "ARCHIVE_EXTERNAL_BLOCKED/external-profile-topic"
        topic.mkdir()
        (topic / "INDEX.md").write_text(
            "\n".join(
                [
                    "# External Profile Topic",
                    "Status: external_blocked",
                    "Code: main/backend/app/services/example.py",
                    "Script: scripts/check_example.py",
                    "Test: pytest tests/unit/test_example.py passed",
                    "Gate: validation gate readback",
                    "External blocker: live provider not_verified",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        with (root / checker.DEV_PLANS_ROOT / "ARCHIVE_EXTERNAL_BLOCKED/INDEX.md").open("a", encoding="utf-8") as handle:
            handle.write("- [External Profile Topic](./external-profile-topic/INDEX.md)\n")

        result = checker.check(root)

        self.assertTrue(result.ok, result.problems)
        profile = result.target_profiles[checker.DEV_PLANS_ROOT / "ARCHIVE_EXTERNAL_BLOCKED/external-profile-topic"]
        self.assertTrue(profile.has_code_reference)
        self.assertTrue(profile.has_script_reference)
        self.assertTrue(profile.has_test_reference)
        self.assertTrue(profile.has_gate_reference)
        self.assertTrue(profile.has_external_blocker)

    def test_reference_excludes_from_allowlist_are_used_by_profile_scan(self) -> None:
        root = self.make_repo()
        topic = root / "docs/development/development-plans/ARCHIVE_CLOSED/reference-excluded-topic"
        topic.mkdir()
        (topic / "evidence.md").write_text("# Evidence\n\nGate: pytest tests/unit/test_ref.py passed.\n", encoding="utf-8")
        excluded = topic / "references/repos/example"
        excluded.mkdir(parents=True)
        (excluded / "README.md").write_text("External fixture with `.py` and external_blocked noise.\n", encoding="utf-8")
        with (root / "docs/development/development-plans/ARCHIVE_CLOSED/INDEX.md").open("a", encoding="utf-8") as handle:
            handle.write("- [Reference Excluded Topic](./reference-excluded-topic/evidence.md)\n")

        result = checker.check(root)

        self.assertTrue(result.ok, result.problems)
        profile = result.target_profiles[Path("docs/development/development-plans/ARCHIVE_CLOSED/reference-excluded-topic")]
        self.assertEqual(1, profile.file_count)

    def test_json_includes_status_summary_and_mapping_rules(self) -> None:
        root = self.make_repo()
        topic = root / "docs/development/development-plans/ARCHIVE_CLOSED/closed-topic"
        topic.mkdir()
        (topic / "evidence.md").write_text(
            "# Closed evidence\n\nGate: pytest tests/unit/test_closed.py passed.\n",
            encoding="utf-8",
        )
        with (root / "docs/development/development-plans/ARCHIVE_CLOSED/INDEX.md").open("a", encoding="utf-8") as handle:
            handle.write("- [Closed Topic](./closed-topic/evidence.md)\n")

        payload = checker.result_json(checker.check(root))

        self.assertEqual(2, payload["state_schema_version"])
        self.assertIn("generated_at", payload)
        self.assertEqual(
            {
                "unsealed_count": 0,
                "sealed_count": 1,
                "outdated_count": 0,
                "needs_update_count": 0,
                "external_blocked_count": 0,
            },
            payload["status_summary"],
        )
        self.assertIn("sealed_count", payload["status_mapping_rules"])
        self.assertIn("target_review_status_counts", payload)

    def test_target_topic_override_marks_needs_update_without_changing_archive_status(self) -> None:
        root = self.make_repo()
        topic = root / "docs/development/development-plans/ARCHIVE_CLOSED/closed-but-stale-topic"
        topic.mkdir()
        (topic / "evidence.md").write_text(
            "# Closed but stale\n\nGate: pytest tests/unit/test_closed.py passed.\n",
            encoding="utf-8",
        )
        with (root / "docs/development/development-plans/ARCHIVE_CLOSED/INDEX.md").open("a", encoding="utf-8") as handle:
            handle.write("- [Closed But Stale](./closed-but-stale-topic/evidence.md)\n")

        allowlist_path = root / checker.ALLOWLIST
        allowlist = json.loads(allowlist_path.read_text(encoding="utf-8"))
        allowlist["target_topic_overrides"] = [
            {
                "path": "docs/development/development-plans/ARCHIVE_CLOSED/closed-but-stale-topic",
                "review_status": "needs_update",
                "reason": "fixture forces a stale review state",
            }
        ]
        allowlist_path.write_text(json.dumps(allowlist, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        payload = checker.result_json(checker.check(root))
        profile = next(
            item
            for item in payload["target_profiles"]
            if item["path"] == "docs/development/development-plans/ARCHIVE_CLOSED/closed-but-stale-topic"
        )

        self.assertEqual({"closed": 1}, payload["target_status_counts"])
        self.assertEqual({"needs_update": 1}, payload["target_review_status_counts"])
        self.assertEqual("closed", profile["status"])
        self.assertEqual("needs_update", profile["target_review_status"])
        self.assertEqual("fixture forces a stale review state", profile["review_reason"])

    def test_reference_excludes_merge_defaults_with_custom_patterns(self) -> None:
        patterns = checker.reference_excludes({"reference_excludes": ["**/vendor/reference/**"]})

        self.assertIn("**/references/repos/**", patterns)
        self.assertIn("references/repos/**", patterns)
        self.assertIn("**/vendor/reference/**", patterns)

    def test_reference_repo_paths_are_excluded(self) -> None:
        self.assertTrue(checker.is_reference_repo_path(Path("topic/references/repos/example/README.md")))
        self.assertFalse(checker.is_reference_repo_path(Path("topic/references/papers/example.pdf")))


if __name__ == "__main__":
    unittest.main()
