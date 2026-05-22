from __future__ import annotations

import unittest

import pytest

from scripts.check_open_search_runtime_boundary import (
    build_contract,
    endpoint_config,
    validate_contract,
)


pytestmark = pytest.mark.unit


def _sample_result(provider: str) -> dict:
    route = f"explicit:{provider}"
    backend_trace = {
        "provider": provider,
        "provider_route": route,
        "provider_family": "local_open_search",
        "auto_included": False,
    }
    if provider == "searxng":
        backend_trace["pageno"] = 1
    else:
        backend_trace["resource"] = "local"
    return {
        "title": f"{provider} result",
        "link": f"https://example.test/{provider}",
        "source": provider,
        "provider_route": route,
        "provider_family": "local_open_search",
        "provider_auto_included": False,
        "backend_trace": backend_trace,
    }


class OpenSearchRuntimeBoundaryTest(unittest.TestCase):
    def test_skip_live_probe_keeps_configured_endpoints_distinct_from_runtime_closure(self) -> None:
        contract = build_contract(enable_live_probe=False, env={})

        self.assertEqual(validate_contract(contract), [])
        self.assertEqual(contract["status"], "passed")
        self.assertEqual(contract["external_runtime_gap"], "retained")
        self.assertFalse(contract["closure_claim_allowed"])
        self.assertEqual(contract["configured_endpoints"]["searxng"]["endpoint_state"], "configured_endpoint")
        self.assertEqual(contract["configured_endpoints"]["yacy"]["endpoint_state"], "configured_endpoint")
        self.assertEqual(
            {
                row["boundary_classification"]
                for row in contract["provider_runtime_boundaries"].values()
            },
            {"configured_endpoint_only"},
        )
        self.assertEqual(
            {
                row["live_probe_status"]
                for row in contract["provider_runtime_boundaries"].values()
            },
            {"not_run"},
        )

    def test_connect_error_is_reported_as_service_not_started_without_failing_boundary_gate(self) -> None:
        class ConnectError(Exception):
            pass

        def runner(provider: str, base_url: str, limit: int) -> list[dict]:
            raise ConnectError(f"connection refused at {base_url}")

        contract = build_contract(enable_live_probe=True, env={}, search_runner=runner)

        self.assertEqual(contract["status"], "passed")
        for provider, row in contract["provider_runtime_boundaries"].items():
            self.assertEqual(row["runtime_state"], "service_not_started", provider)
            self.assertEqual(row["boundary_classification"], "service_not_started_connect_error", provider)
            self.assertEqual(row["live_probe_status"], "unavailable", provider)
            self.assertEqual(row["fallback_reason"], "ConnectError", provider)
            self.assertFalse(row["live_closure_claim_allowed"])

    def test_live_query_success_remains_unsealed_and_explicit_only(self) -> None:
        def runner(provider: str, base_url: str, limit: int) -> list[dict]:
            return [_sample_result(provider)]

        contract = build_contract(enable_live_probe=True, env={}, search_runner=runner)

        self.assertEqual(contract["status"], "passed")
        for provider, row in contract["provider_runtime_boundaries"].items():
            self.assertEqual(row["runtime_state"], "live_query_returned", provider)
            self.assertEqual(row["boundary_classification"], "live_query_unsealed", provider)
            self.assertEqual(row["live_probe_status"], "ready", provider)
            self.assertEqual(row["live_result_count"], 1, provider)
            self.assertEqual(row["provider_route"], f"explicit:{provider}", provider)
            self.assertFalse(row["provider_auto_included"])
            self.assertFalse(row["provider_auto_promotion_allowed"])
            self.assertFalse(row["live_closure_claim_allowed"])

        claim_codes = {item["code"] for item in contract["unsupported_claims"]}
        self.assertIn("live_query_quality_not_closed", claim_codes)
        self.assertIn("provider_auto_promotion_not_allowed", claim_codes)

    def test_endpoint_config_rejects_invalid_endpoint_values(self) -> None:
        config = endpoint_config("searxng", env={"SEARXNG_BASE_URL": "not-a-url"})

        self.assertFalse(config["configured"])
        self.assertEqual(config["endpoint_state"], "invalid_endpoint")


if __name__ == "__main__":
    unittest.main()
