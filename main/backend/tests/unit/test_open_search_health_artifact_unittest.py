from __future__ import annotations

import json
import unittest
from typing import Annotated, get_args, get_origin, get_type_hints

import pytest

from scripts.check_open_search_health_artifact import (
    build_compose_expectations,
    build_health_artifact,
    validate_health_artifact,
)
from tests.unit._evidence_source_assertions import assert_typed_evidence_unavailable


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


class OpenSearchHealthArtifactTest(unittest.TestCase):
    def test_stopped_services_record_connect_error_without_live_closure(self) -> None:
        artifact = build_health_artifact(
            runtime_boundary=_runtime_boundary(classification="service_not_started_connect_error"),
            command_runner=_stopped_runner,
        )

        self.assertIn("Wave12 provider readiness input must be passed", validate_health_artifact(artifact))
        assert_typed_evidence_unavailable(
            self,
            artifact,
            expected_missing_paths=(
                "development/latest-dev-docs/automation-runs/wave12-provider-readiness/"
                "2026-05-22/provider_readiness_summary.json",
            ),
        )
        self.assertFalse(artifact["closure_claim_allowed"])
        self.assertTrue(artifact["live_probe"]["open"])
        for provider, row in artifact["provider_health"].items():
            self.assertFalse(row["facts"]["current_service_running"], provider)
            self.assertTrue(row["facts"]["service_not_started_connect_error"], provider)
            self.assertTrue(row["facts"]["live_probe_open"], provider)
            self.assertTrue(row["facts"]["no_live_closure_claim"], provider)
            self.assertFalse(row["wave15_runtime_boundary"]["live_closure_claim_allowed"], provider)

    def test_running_live_probe_remains_unsealed_and_explicit_only(self) -> None:
        artifact = build_health_artifact(
            runtime_boundary=_runtime_boundary(classification="live_query_unsealed", running=True),
            command_runner=_running_runner,
        )

        self.assertIn("Wave12 provider readiness input must be passed", validate_health_artifact(artifact))
        assert_typed_evidence_unavailable(self, artifact)
        for provider, row in artifact["provider_health"].items():
            self.assertTrue(row["facts"]["current_service_running"], provider)
            self.assertTrue(row["facts"]["live_query_unsealed"], provider)
            self.assertFalse(row["facts"]["service_not_started_connect_error"], provider)
            self.assertEqual(row["provider_route"], f"explicit:{provider}", provider)
            self.assertFalse(row["provider_auto_included"], provider)
            self.assertTrue(row["facts"]["no_provider_auto_promotion"], provider)
            self.assertTrue(row["facts"]["no_live_closure_claim"], provider)

    def test_validator_rejects_stopped_service_live_closure_claim(self) -> None:
        artifact = build_health_artifact(
            runtime_boundary=_runtime_boundary(classification="service_not_started_connect_error"),
            command_runner=_stopped_runner,
        )
        artifact["provider_health"]["searxng"]["wave15_runtime_boundary"]["live_closure_claim_allowed"] = True

        failures = validate_health_artifact(artifact)

        self.assertTrue(any("stopped service must not have live closure claim" in item for item in failures))

    def test_open_search_compose_expectations_authority_metadata(self) -> None:
        return_hint = get_type_hints(build_compose_expectations, include_extras=True)["return"]
        self.assertIs(get_origin(return_hint), Annotated)
        _, metadata = get_args(return_hint)
        self.assertEqual(
            metadata,
            "kit:non-authoritative derived_as=view fact_source=repository.search_lab_and_main_ops_compose "
            "witness=test:test_open_search_compose_expectations_authority_metadata",
        )

    def test_open_search_health_artifact_authority_metadata(self) -> None:
        return_hint = get_type_hints(build_health_artifact, include_extras=True)["return"]
        self.assertIs(get_origin(return_hint), Annotated)
        _, metadata = get_args(return_hint)
        self.assertEqual(
            metadata,
            "kit:non-authoritative derived_as=preflight fact_source=repository.wave12_boundary_and_runtime_probe_results "
            "witness=test:test_open_search_health_artifact_authority_metadata",
        )


if __name__ == "__main__":
    unittest.main()
