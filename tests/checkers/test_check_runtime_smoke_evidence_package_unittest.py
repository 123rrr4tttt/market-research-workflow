#!/usr/bin/env python3
"""Tests for the runtime smoke evidence package aggregator."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_runtime_smoke_evidence_package.py"
SPEC = importlib.util.spec_from_file_location("check_runtime_smoke_evidence_package", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


class RuntimeSmokeEvidencePackageTestCase(unittest.TestCase):
    def make_repo(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name)

    def write_json(self, root: Path, name: str, payload: object) -> Path:
        path = root / name
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def args(self, **overrides: object) -> Namespace:
        values = {
            "docker_preflight": None,
            "local_preflight": None,
            "backend_smoke": None,
            "frontend_browser": None,
            "runtime_health": None,
            "output": None,
            "allow_blocked": False,
            "json": False,
        }
        values.update(overrides)
        return Namespace(**values)

    def test_all_provided_passed_evidence_passes(self) -> None:
        root = self.make_repo()
        docker = self.write_json(root, "docker.json", {"schema_version": "ops", "status": "passed"})
        backend = self.write_json(root, "backend.json", {"schema_version": "backend", "status": "passed"})
        browser = self.write_json(root, "browser.json", {"schema_version": "browser", "status": "passed"})

        package = checker.build_package(
            self.args(docker_preflight=docker, backend_smoke=backend, frontend_browser=browser)
        )

        self.assertEqual("passed", package["status"])
        self.assertEqual(
            ["docker_preflight", "backend_live_smoke", "frontend_real_backend_browser"],
            package["summary"]["provided_components"],
        )
        self.assertIn("local_preflight", package["summary"]["missing_components"])
        self.assertIn("runtime_health_matrix", package["summary"]["missing_components"])

    def test_docker_daemon_blocker_is_classified_without_pass_claim(self) -> None:
        root = self.make_repo()
        docker = self.write_json(
            root,
            "docker.json",
            {
                "schema_version": "ops_preflight_evidence_contract.v1",
                "status": "failed",
                "fail_fast_decision": {
                    "reasons": ["service:docker-daemon"],
                    "recommended_command": "./scripts/docker-deploy.sh preflight",
                },
            },
        )
        backend = self.write_json(root, "backend.json", {"status": "blocked_by_environment"})

        package = checker.build_package(self.args(docker_preflight=docker, backend_smoke=backend))

        self.assertEqual("blocked_by_environment", package["status"])
        self.assertIn("docker_preflight", package["summary"]["blocked_components"])
        self.assertEqual("service:docker-daemon", package["summary"]["first_blocker"]["reason"])

    def test_invalid_or_missing_provided_file_fails(self) -> None:
        root = self.make_repo()
        missing = root / "missing.json"

        package = checker.build_package(self.args(docker_preflight=missing))

        self.assertEqual("failed", package["status"])
        self.assertEqual(["docker_preflight"], package["summary"]["failed_components"])
        self.assertEqual("file_not_found", package["components"][0]["load_error"])

    def test_runtime_health_passed_with_blocked_modes_is_blocked_not_failed(self) -> None:
        root = self.make_repo()
        runtime = self.write_json(
            root,
            "runtime.json",
            {
                "schema_version": "mrw.runtime_health_matrix.v1",
                "status": "passed_with_blocked_modes",
                "runtime_modes": [
                    {"mode": "local", "status": "passed", "blocked_by_environment": []},
                    {
                        "mode": "docker",
                        "status": "blocked_by_environment",
                        "blocked_by_environment": [
                            {
                                "reason": "endpoint_unreachable",
                                "recommended_command": "./scripts/docker-deploy.sh start --profile modern-ui",
                            }
                        ],
                    },
                ],
            },
        )

        package = checker.build_package(self.args(runtime_health=runtime))

        self.assertEqual("blocked_by_environment", package["status"])
        self.assertEqual(["runtime_health_matrix"], package["summary"]["blocked_components"])
        self.assertEqual("endpoint_unreachable", package["summary"]["first_blocker"]["reason"])


if __name__ == "__main__":
    unittest.main()
