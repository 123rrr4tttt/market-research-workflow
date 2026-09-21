#!/usr/bin/env python3
"""Focused tests for performance capacity service probe fail-fast evidence."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_SCRIPT = REPO_ROOT / "scripts" / "performance_capacity_baseline.py"
CHECKER_SCRIPT = REPO_ROOT / "scripts" / "check_performance_capacity_baseline_artifact.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


baseline = load_module("performance_capacity_baseline", BASELINE_SCRIPT)
checker = load_module("check_performance_capacity_baseline_artifact", CHECKER_SCRIPT)


def make_args(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "output": None,
        "previous": None,
        "api_base": None,
        "runtime_mode": "repo_local_deterministic_fixture_smoke",
        "service_required": False,
        "allow_service_failure": False,
        "probe_timeout": 0.05,
        "trend_regression_ratio": 1.5,
        "trend_budget_ratio": 0.95,
        "fail_on_degradation": False,
        "self_test": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class PerformanceCapacityServiceProbeTestCase(unittest.TestCase):
    def assert_checker_accepts(self, artifact: dict[str, object]) -> None:
        self.assertEqual([], baseline.validate_artifact_shape(artifact))
        self.assertEqual([], checker.validate(artifact))

    def test_default_deterministic_fixture_smoke_still_passes(self) -> None:
        artifact = baseline.build_artifact(make_args())

        self.assertEqual("passed", artifact["status"])
        self.assertFalse(artifact["degradation"]["flag"])
        self.assert_checker_accepts(artifact)

    def test_required_unavailable_service_records_fail_fast_evidence(self) -> None:
        artifact = baseline.build_artifact(
            make_args(api_base="http://127.0.0.1:1", service_required=True)
        )
        service_probe = artifact["service_probe"]

        self.assertEqual("degraded", artifact["status"])
        self.assertEqual("unavailable", service_probe["status"])
        self.assertEqual("failed", service_probe["service_ready"]["status"])
        self.assertEqual("measured", service_probe["latency"]["status"])
        self.assertGreaterEqual(service_probe["latency"]["total_elapsed_ms"], 0)
        self.assertIsInstance(service_probe["latency_ms"], (int, float))
        self.assertTrue(service_probe["degradation"]["flag"])
        self.assertTrue(service_probe["fail_fast_decision"]["should_fail"])
        self.assertEqual(1, service_probe["fail_fast_decision"]["exit_code"])
        self.assertIn("--service-required", service_probe["recommended_command"])
        self.assert_checker_accepts(artifact)

    def test_cli_required_unavailable_service_writes_artifact_and_exits_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "performance.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(BASELINE_SCRIPT),
                    "--output",
                    str(output),
                    "--api-base",
                    "http://127.0.0.1:1",
                    "--service-required",
                    "--probe-timeout",
                    "0.05",
                ],
                cwd=REPO_ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(1, result.returncode, result.stdout + result.stderr)
            artifact = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(artifact["service_probe"]["fail_fast_decision"]["should_fail"])
            self.assert_checker_accepts(artifact)

    def test_cli_allow_service_failure_keeps_fail_fast_evidence_but_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "performance.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(BASELINE_SCRIPT),
                    "--output",
                    str(output),
                    "--api-base",
                    "http://127.0.0.1:1",
                    "--service-required",
                    "--allow-service-failure",
                    "--probe-timeout",
                    "0.05",
                ],
                cwd=REPO_ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            artifact = json.loads(output.read_text(encoding="utf-8"))
            fail_fast = artifact["service_probe"]["fail_fast_decision"]
            self.assertTrue(fail_fast["should_fail"])
            self.assertTrue(fail_fast["allow_service_failure"])
            self.assertEqual(0, fail_fast["effective_exit_code"])
            self.assert_checker_accepts(artifact)


if __name__ == "__main__":
    unittest.main()
