from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts import flake_report

pytestmark = pytest.mark.unit


class FlakeReportUnitTestCase(unittest.TestCase):
    def test_main_writes_failure_summary_from_junit(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            junit = root / "junit.xml"
            output = root / "flake-report.md"
            junit.write_text(
                """<testsuite tests="1" failures="1" errors="0" skipped="0">
  <testcase classname="tests.test_alpha" name="test_fails">
    <failure message="boom" />
  </testcase>
</testsuite>
""",
                encoding="utf-8",
            )

            with patch.object(
                sys,
                "argv",
                ["flake_report.py", "--junit", str(junit), "--output", str(output)],
            ):
                self.assertEqual(flake_report.main(), 0)

            text = output.read_text(encoding="utf-8")
            self.assertIn("- failures: `1`", text)
            self.assertIn("tests.test_alpha::test_fails", text)


if __name__ == "__main__":
    unittest.main()
