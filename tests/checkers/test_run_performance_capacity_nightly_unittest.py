#!/usr/bin/env python3
"""Unit tests for the performance/capacity nightly wrapper."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WRAPPER_PATH = REPO_ROOT / "scripts" / "run_performance_capacity_nightly.sh"


class PerformanceCapacityNightlyWrapperTestCase(unittest.TestCase):
    def run_wrapper(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            ["bash", str(WRAPPER_PATH), *args],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode != 0:
            self.fail(
                f"wrapper exited {completed.returncode}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
            )
        return completed

    def dry_run_markers(self, output: str) -> dict[str, str]:
        markers: dict[str, str] = {}
        for line in output.splitlines():
            if not line.startswith("DRY-RUN "):
                continue
            key, value = line[len("DRY-RUN ") :].split("=", 1)
            markers[key] = value
        return markers

    def test_dry_run_passes_service_required_to_baseline_command(self) -> None:
        completed = self.run_wrapper(
            "--date",
            "2026-05-25",
            "--api-base",
            "http://127.0.0.1:8000",
            "--service-required",
            "--fail-on-degradation",
            "--dry-run",
        )

        markers = self.dry_run_markers(completed.stdout)
        self.assertEqual("http://127.0.0.1:8000", markers["api_base"])
        self.assertEqual("1", markers["service_required"])
        self.assertEqual("0", markers["allow_service_failure"])

        baseline_cmd = shlex.split(markers["baseline_cmd"])
        self.assertIn("--api-base", baseline_cmd)
        self.assertEqual("http://127.0.0.1:8000", baseline_cmd[baseline_cmd.index("--api-base") + 1])
        self.assertIn("--service-required", baseline_cmd)
        self.assertNotIn("--allow-service-failure", baseline_cmd)

    def test_dry_run_can_record_service_failure_without_failing_wrapper(self) -> None:
        completed = self.run_wrapper(
            "--date",
            "2026-05-25",
            "--api-base",
            "http://127.0.0.1:1",
            "--service-required",
            "--allow-service-failure",
            "--dry-run",
        )

        markers = self.dry_run_markers(completed.stdout)
        self.assertEqual("1", markers["service_required"])
        self.assertEqual("1", markers["allow_service_failure"])
        baseline_cmd = shlex.split(markers["baseline_cmd"])
        self.assertIn("--service-required", baseline_cmd)
        self.assertIn("--allow-service-failure", baseline_cmd)

    def test_dry_run_prefers_path_python311_over_user_local_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_python = Path(temp_dir) / "python3.11"
            fake_python.write_text(
                f"#!/usr/bin/env bash\nexec {shlex.quote(sys.executable)} \"$@\"\n",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)
            env = os.environ.copy()
            env.pop("PYTHON", None)
            env["PATH"] = f"{temp_dir}{os.pathsep}{env.get('PATH', '')}"

            completed = self.run_wrapper("--date", "2026-05-25", "--dry-run", env=env)

        markers = self.dry_run_markers(completed.stdout)
        baseline_cmd = shlex.split(markers["baseline_cmd"])
        checker_cmd = shlex.split(markers["checker_cmd"])
        self.assertEqual(str(fake_python), baseline_cmd[0])
        self.assertEqual(str(fake_python), checker_cmd[0])


if __name__ == "__main__":
    unittest.main()
