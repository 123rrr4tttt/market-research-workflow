from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts import flake_trend

pytestmark = pytest.mark.unit


class FlakeTrendUnitTestCase(unittest.TestCase):
    def test_build_summary_outputs_machine_readable_schema(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "junit.xml").write_text(
                """<testsuite tests="2" failures="1" errors="0">
  <testcase classname="tests.test_alpha" name="test_pass" />
  <testcase classname="tests.test_alpha" name="test_flaky">
    <failure message="boom" />
  </testcase>
</testsuite>
""",
                encoding="utf-8",
            )

            summary = flake_trend.build_summary(
                junit_glob=str(root / "*.xml"),
                threshold=0.30,
                top_n=1,
            )

        self.assertEqual(summary["history_files"], 1)
        self.assertEqual(summary["threshold"], 0.30)
        self.assertEqual(summary["top_n"], 1)
        self.assertEqual(summary["totals"], {"tests": 2, "runs": 2, "failures": 1})
        self.assertEqual(len(summary["items"]), 1)
        self.assertEqual(summary["items"][0]["nodeid"], "tests.test_alpha::test_flaky")
        self.assertTrue(summary["items"][0]["above_threshold"])
        self.assertEqual(len(summary["tests"]), 2)

    def test_main_writes_optional_json_output(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            history = root / "history"
            history.mkdir()
            (history / "junit.xml").write_text(
                """<testsuite tests="1" failures="0" errors="0">
  <testcase classname="tests.test_alpha" name="test_pass" />
</testsuite>
""",
                encoding="utf-8",
            )
            report = root / "flaky-trend-report.md"
            summary_json = root / "flaky-trend-summary.json"

            with patch.object(
                sys,
                "argv",
                [
                    "flake_trend.py",
                    "--junit-glob",
                    str(history / "*.xml"),
                    "--output",
                    str(report),
                    "--output-json",
                    str(summary_json),
                    "--top-n",
                    "15",
                    "--threshold",
                    "0.30",
                ],
            ):
                self.assertEqual(flake_trend.main(), 0)

            self.assertIn("Flaky Trend Report", report.read_text(encoding="utf-8"))
            payload = json.loads(summary_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["totals"]["tests"], 1)
            self.assertEqual(payload["tests"][0]["nodeid"], "tests.test_alpha::test_pass")

    def test_main_allows_markdown_only_output(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "flaky-trend-report.md"

            with patch.object(
                sys,
                "argv",
                [
                    "flake_trend.py",
                    "--junit-glob",
                    str(root / "missing" / "*.xml"),
                    "--output",
                    str(report),
                ],
            ):
                self.assertEqual(flake_trend.main(), 0)

            self.assertIn("status: no-history", report.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
