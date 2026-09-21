from __future__ import annotations

import json
import subprocess
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts._automation_runtime import repo_root, utc_now, write_json


class AutomationRuntimeHelpersTest(unittest.TestCase):
    def test_repo_root_is_project_root(self) -> None:
        self.assertEqual(repo_root(), Path(__file__).resolve().parents[2])

    def test_utc_now_is_second_precision_utc_z(self) -> None:
        value = utc_now()

        self.assertRegex(value, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        self.assertEqual(parsed.microsecond, 0)
        self.assertEqual(parsed.utcoffset(), timedelta(0))

    def test_write_json_uses_exact_bytes_and_creates_parents(self) -> None:
        payload = {"z": 1, "a": "中文", "nested": {"b": True, "a": None}}
        expected = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "artifact.json"
            write_json(path, payload)

            self.assertEqual(path.read_bytes(), expected.encode("utf-8"))

    def test_script_import_works_directly_and_as_package(self) -> None:
        script = repo_root() / "scripts" / "check_llm_report_token_state_retention_automation_spec.py"

        with TemporaryDirectory() as outside_repo:
            for cwd in (repo_root(), Path(outside_repo)):
                completed = subprocess.run(
                    [sys.executable, str(script), "--help"],
                    cwd=cwd,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
