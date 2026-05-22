from __future__ import annotations

import json
import unittest

import pytest

from scripts.check_open_search_health_artifact import build_health_artifact
from scripts.check_open_search_health_artifact_schema_readback import build_schema_readback


pytestmark = pytest.mark.unit


def _runtime_row(provider: str, *, classification: str, running: bool = False) -> dict:
    return {
        "provider": provider,
        "provider_route": f"explicit:{provider}",
        "provider_family": "local_open_search",
        "provider_auto_included": False,
        "runtime_state": "live_query_returned" if running else "service_not_started",
        "boundary_classification": classification,
        "live_probe_status": "ready" if running else "unavailable",
        "live_result_count": 1 if running else 0,
        "fallback_reason": None if running else "ConnectError",
        "error_type": None if running else "ConnectError",
        "live_closure_claim_allowed": False,
        "provider_auto_promotion_allowed": False,
    }


def _runtime_boundary(*, classification: str, running: bool = False) -> dict:
    return {
        "status": "passed",
        "generated_by": "test",
        "boundary_state": "partial",
        "external_runtime_gap": "retained",
        "closure_claim_allowed": False,
        "provider_runtime_boundaries": {
            "searxng": _runtime_row("searxng", classification=classification, running=running),
            "yacy": _runtime_row("yacy", classification=classification, running=running),
        },
    }


def _command(stdout: str, *, ok: bool = True) -> dict:
    return {
        "cmd": ["docker", "compose", "ps"],
        "returncode": 0 if ok else 1,
        "ok": ok,
        "stdout": stdout,
        "stderr": "" if ok else "docker unavailable",
        "latency_ms": 0,
    }


def _stopped_runner(cmd: list[str], cwd, timeout: int) -> dict:
    return _command("")


def _running_runner(cmd: list[str], cwd, timeout: int) -> dict:
    rows = [
        {"Service": "searxng", "Name": "mrw-search-lab-searxng", "State": "running", "Status": "Up 1 second"},
        {"Service": "yacy", "Name": "mrw-search-lab-yacy", "State": "running", "Status": "Up 1 second"},
    ]
    return _command("\n".join(json.dumps(row) for row in rows))


class OpenSearchHealthArtifactSchemaReadbackTest(unittest.TestCase):
    def test_schema_readback_distinguishes_compose_config_from_stopped_connect_error(self) -> None:
        artifact = build_health_artifact(
            runtime_boundary=_runtime_boundary(classification="service_not_started_connect_error"),
            command_runner=_stopped_runner,
        )

        readback = build_schema_readback(artifact)

        self.assertEqual(readback["status"], "passed")
        self.assertEqual(readback["contract_version"], "wave19-open-search-health-artifact-schema-readback.v1")
        self.assertEqual(readback["classification_counts"]["compose_config_evidence"], 2)
        self.assertEqual(readback["classification_counts"]["service_not_started_connect_error"], 2)
        self.assertEqual(readback["classification_counts"]["real_live_probe_response"], 0)
        self.assertFalse(readback["external_provider_closure_claimed"])
        for provider, row in readback["provider_readbacks"].items():
            self.assertEqual(row["compose_config_evidence"]["state"], "present", provider)
            self.assertEqual(row["runtime_evidence"]["readback_kind"], "service_not_started_connect_error", provider)
            self.assertTrue(row["runtime_evidence"]["service_not_started_connect_error"], provider)
            self.assertFalse(row["runtime_evidence"]["real_live_probe_response"], provider)
            self.assertTrue(row["no_external_provider_closure"], provider)

    def test_schema_readback_records_real_live_probe_response_without_closure(self) -> None:
        artifact = build_health_artifact(
            runtime_boundary=_runtime_boundary(classification="live_query_unsealed", running=True),
            command_runner=_running_runner,
        )

        readback = build_schema_readback(artifact)

        self.assertEqual(readback["status"], "passed")
        self.assertEqual(readback["classification_counts"]["compose_config_evidence"], 2)
        self.assertEqual(readback["classification_counts"]["service_not_started_connect_error"], 0)
        self.assertEqual(readback["classification_counts"]["real_live_probe_response"], 2)
        for provider, row in readback["provider_readbacks"].items():
            runtime = row["runtime_evidence"]
            self.assertEqual(runtime["readback_kind"], "real_live_probe_response", provider)
            self.assertEqual(runtime["boundary_classification"], "live_query_unsealed", provider)
            self.assertEqual(runtime["live_probe_status"], "ready", provider)
            self.assertEqual(runtime["live_result_count"], 1, provider)
            self.assertFalse(runtime["external_provider_closure_claimed"], provider)
            self.assertTrue(row["no_external_provider_closure"], provider)

    def test_schema_readback_rejects_runtime_live_closure_claim(self) -> None:
        artifact = build_health_artifact(
            runtime_boundary=_runtime_boundary(classification="service_not_started_connect_error"),
            command_runner=_stopped_runner,
        )
        artifact["provider_health"]["searxng"]["wave15_runtime_boundary"]["live_closure_claim_allowed"] = True

        readback = build_schema_readback(artifact)

        self.assertEqual(readback["status"], "failed")
        self.assertTrue(readback["external_provider_closure_claimed"])
        self.assertTrue(
            any("external provider closure claim must remain false" in failure for failure in readback["failures"])
        )

    def test_schema_readback_is_deterministic_for_same_artifact(self) -> None:
        artifact = build_health_artifact(
            runtime_boundary=_runtime_boundary(classification="service_not_started_connect_error"),
            command_runner=_stopped_runner,
        )

        self.assertEqual(build_schema_readback(artifact), build_schema_readback(artifact))


if __name__ == "__main__":
    unittest.main()
