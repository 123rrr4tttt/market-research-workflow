#!/usr/bin/env python3
"""Focused tests for the runtime health matrix artifact."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "runtime_health_matrix.py"
SPEC = importlib.util.spec_from_file_location("runtime_health_matrix", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def blocked_endpoint(spec: checker.EndpointSpec, timeout: float) -> dict[str, object]:
    return {
        "check_id": spec.check_id,
        "label": spec.label,
        "url": spec.url,
        "required": spec.required,
        "expected_statuses": list(spec.expected_statuses),
        "status": "blocked_by_environment",
        "blocked": True,
        "reason": "endpoint_unreachable",
        "detail": "fixture endpoint is not running",
    }


def blocked_port(spec: checker.PortSpec, timeout: float) -> dict[str, object]:
    return {
        "check_id": spec.check_id,
        "label": spec.label,
        "host": spec.host,
        "port": spec.port,
        "required": spec.required,
        "status": "blocked_by_environment",
        "blocked": True,
        "reason": "port_not_listening",
        "detail": "fixture port is not listening",
    }


def passed_endpoint(spec: checker.EndpointSpec, timeout: float) -> dict[str, object]:
    return {
        "check_id": spec.check_id,
        "label": spec.label,
        "url": spec.url,
        "required": spec.required,
        "expected_statuses": list(spec.expected_statuses),
        "actual_status": spec.expected_statuses[0],
        "status": "passed",
        "blocked": False,
    }


def passed_port(spec: checker.PortSpec, timeout: float) -> dict[str, object]:
    return {
        "check_id": spec.check_id,
        "label": spec.label,
        "host": spec.host,
        "port": spec.port,
        "required": spec.required,
        "status": "passed",
        "blocked": False,
    }


def blocked_worker_readiness(spec: checker.WorkerReadinessSpec, timeout: float) -> dict[str, object]:
    return {
        "check_id": spec.check_id,
        "label": spec.label,
        "url": spec.url,
        "required": spec.required,
        "expected_statuses": list(spec.expected_statuses),
        "actual_status": 200,
        "status": "blocked_by_environment",
        "blocked": True,
        "reason": "celery_worker_unavailable",
        "detail": "backend process stats reported 0 Celery workers; async task lane is not ready",
        "recommended_command": spec.recommended_command,
        "worker_online": False,
        "worker_count": 0,
        "worker_names": [],
    }


def passed_worker_readiness(spec: checker.WorkerReadinessSpec, timeout: float) -> dict[str, object]:
    return {
        "check_id": spec.check_id,
        "label": spec.label,
        "url": spec.url,
        "required": spec.required,
        "expected_statuses": list(spec.expected_statuses),
        "actual_status": 200,
        "status": "passed",
        "blocked": False,
        "detail": "backend process stats report at least one Celery worker",
        "worker_online": True,
        "worker_count": 1,
        "worker_names": ["celery@test"],
    }


class RuntimeHealthMatrixTestCase(unittest.TestCase):
    def specs(self) -> list[checker.RuntimeModeSpec]:
        return checker.build_mode_specs(
            backend_base_url="http://127.0.0.1:8000",
            local_frontend_url="http://127.0.0.1:5173",
            docker_frontend_url="http://127.0.0.1:5174",
        )

    def test_default_timeout_covers_process_stats_readiness_probe(self) -> None:
        args = checker.parse_args([])

        self.assertGreaterEqual(args.timeout, 5.0)
        self.assertEqual(checker.DEFAULT_TIMEOUT_SECONDS, args.timeout)

    def test_default_output_is_repo_local_persistent_artifact(self) -> None:
        args = checker.parse_args([])

        self.assertFalse(str(args.output).startswith("/tmp/"))
        self.assertIn("development/latest-dev-docs/automation-runs/runtime-health-matrix", args.output)
        self.assertFalse(Path(args.output).is_absolute())

    def test_schema_records_blocked_modes_without_passed_claim(self) -> None:
        matrix = checker.build_matrix(
            self.specs(),
            timeout=0.01,
            endpoint_probe=blocked_endpoint,
            port_probe=blocked_port,
            worker_readiness_probe=blocked_worker_readiness,
        )

        self.assertEqual("mrw.runtime_health_matrix.v1", matrix["schema_version"])
        self.assertEqual("blocked_by_environment", matrix["status"])
        self.assertEqual(["docker", "local", "mixed"], sorted(mode["mode"] for mode in matrix["runtime_modes"]))

        for mode in matrix["runtime_modes"]:
            self.assertEqual("blocked_by_environment", mode["status"], mode["mode"])
            self.assertNotEqual("passed", mode["status"])
            self.assertGreater(len(mode["blocked_by_environment"]), 0, mode["mode"])
            self.assertGreater(len(mode["checked_endpoints"]), 0, mode["mode"])
            self.assertGreater(len(mode["checked_ports"]), 0, mode["mode"])
            self.assertGreater(len(mode["checked_async_readiness"]), 0, mode["mode"])
            self.assertGreater(len(mode["recommended_commands"]), 0, mode["mode"])

    def test_exit_code_allows_structured_environment_blocks(self) -> None:
        matrix = checker.build_matrix(
            self.specs(),
            timeout=0.01,
            endpoint_probe=blocked_endpoint,
            port_probe=blocked_port,
            worker_readiness_probe=blocked_worker_readiness,
        )

        self.assertEqual(3, checker.determine_exit_code(matrix, allow_blocked=False))
        self.assertEqual(0, checker.determine_exit_code(matrix, allow_blocked=True))

    def test_passed_probe_matrix_has_required_artifact_fields(self) -> None:
        matrix = checker.build_matrix(
            self.specs(),
            timeout=0.01,
            endpoint_probe=passed_endpoint,
            port_probe=passed_port,
            worker_readiness_probe=passed_worker_readiness,
        )

        self.assertEqual("passed", matrix["status"])
        for mode in matrix["runtime_modes"]:
            self.assertEqual("passed", mode["status"], mode["mode"])
            self.assertEqual([], mode["blocked_by_environment"])
            self.assertIn("checked_endpoints", mode)
            self.assertIn("checked_ports", mode)
            self.assertIn("checked_async_readiness", mode)
            self.assertEqual("passed", mode["checked_async_readiness"][0]["status"])

    def test_worker_missing_blocks_async_lane_without_pure_pass(self) -> None:
        matrix = checker.build_matrix(
            self.specs(),
            timeout=0.01,
            endpoint_probe=passed_endpoint,
            port_probe=passed_port,
            worker_readiness_probe=blocked_worker_readiness,
        )

        self.assertEqual("worker_blocked", matrix["status"])
        self.assertNotEqual("passed", matrix["status"])
        self.assertEqual(3, checker.determine_exit_code(matrix, allow_blocked=False))
        self.assertEqual(0, checker.determine_exit_code(matrix, allow_blocked=True))

        for mode in matrix["runtime_modes"]:
            self.assertEqual("worker_blocked", mode["status"], mode["mode"])
            self.assertNotEqual("passed", mode["status"])
            self.assertEqual("blocked_by_environment", mode["checked_async_readiness"][0]["status"])
            blocked = mode["blocked_by_environment"]
            self.assertEqual(1, len(blocked), mode["mode"])
            self.assertEqual("celery_worker_unavailable", blocked[0]["reason"])
            self.assertIn("Celery workers", blocked[0]["detail"])
            self.assertIn("start", blocked[0]["recommended_command"])
            self.assertNotIn("warnings", mode)


if __name__ == "__main__":
    unittest.main()
