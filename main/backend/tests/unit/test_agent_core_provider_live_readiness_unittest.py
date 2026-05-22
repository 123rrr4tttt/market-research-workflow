from __future__ import annotations

import unittest

import pytest

from app.services.agent_core.provider_readiness import (
    build_agent_core_provider_live_readiness_contract,
    validate_agent_core_provider_live_readiness_contract,
)
from scripts.check_agent_core_provider_live_readiness import build_contract_snapshot, validate_contract_snapshot


pytestmark = pytest.mark.unit


class AgentCoreProviderLiveReadinessUnitTest(unittest.TestCase):
    def test_readiness_contract_records_configured_provider_fixtures_and_live_gaps(self) -> None:
        contract = build_agent_core_provider_live_readiness_contract(
            settings_source={"llm_provider": "openai", "openai_api_key": None},
            codex_cli_status={
                "available": False,
                "binary_available": False,
                "auth_available": False,
                "fallback_enabled": True,
                "model": "gpt-fixture",
            },
        )

        self.assertEqual(validate_agent_core_provider_live_readiness_contract(contract), [])
        self.assertEqual(contract["contract_version"], "agent_core.provider_live_readiness.v1")
        self.assertEqual(contract["status"], "passed")
        self.assertEqual(contract["readiness_state"], "partial")
        self.assertEqual(contract["configured_provider"]["llm_provider"], "openai")

        provider_rows = {row["provider"]: row for row in contract["configured_providers"]}
        self.assertEqual(provider_rows["openai"]["config_state"], "missing_config")
        self.assertIn("OPENAI_API_KEY", provider_rows["openai"]["missing_config_keys"])
        self.assertEqual(provider_rows["openai"]["live_probe_status"], "blocked")

        fixture_rows = {row["provider_key"]: row for row in contract["local_fixture_readiness"]}
        self.assertEqual(set(fixture_rows), {"fake_core_provider", "json_core_provider", "native_tool_calling_provider"})
        for row in fixture_rows.values():
            self.assertEqual(row["fixture_status"], "ready")
            self.assertEqual(row["stop_reason"], "final_answer")
            self.assertGreaterEqual(row["tool_result_status_counts"]["completed"], 1)

        live_rows = {row["provider"]: row for row in contract["live_availability"]["providers"]}
        self.assertEqual(live_rows["openai"]["live_probe_status"], "blocked")
        self.assertEqual(live_rows["openai"]["availability_state"], "gap_recorded")

        claim_codes = {row["code"] for row in contract["unsupported_closure_claims"]}
        self.assertIn("all_agentcore_providers_live_not_closed", claim_codes)
        self.assertIn("selected_provider_live_availability_not_closed", claim_codes)
        self.assertIn("native_tool_calling_quality_not_closed", claim_codes)

    def test_openai_config_can_be_recorded_via_codex_cli_fallback_without_live_claim(self) -> None:
        contract = build_agent_core_provider_live_readiness_contract(
            settings_source={"llm_provider": "openai", "openai_api_key": None},
            codex_cli_status={
                "available": True,
                "binary_available": True,
                "auth_available": True,
                "fallback_enabled": True,
                "model": "gpt-fixture",
            },
        )

        provider_rows = {row["provider"]: row for row in contract["configured_providers"]}
        self.assertEqual(provider_rows["openai"]["config_state"], "configured_via_codex_cli_fallback")
        live_rows = {row["provider"]: row for row in contract["live_availability"]["providers"]}
        self.assertEqual(live_rows["openai"]["live_probe_status"], "not_run")
        self.assertEqual(live_rows["openai"]["gap_reason"], "live_probe_disabled")
        self.assertEqual(contract["readiness_state"], "partial")

    def test_local_llm_provider_is_explicitly_unsupported_until_adapter_exists(self) -> None:
        contract = build_agent_core_provider_live_readiness_contract(
            settings_source={"llm_provider": "local", "local_llm_enabled": True},
            codex_cli_status={"available": False, "binary_available": False, "auth_available": False},
        )

        selected = next(row for row in contract["configured_providers"] if row["selected"])
        self.assertEqual(selected["provider"], "local")
        self.assertEqual(selected["config_state"], "unsupported_provider")
        self.assertEqual(selected["live_gap_reason"], "local_llm_provider_not_implemented")
        claim_codes = {row["code"] for row in contract["unsupported_closure_claims"]}
        self.assertIn("local_provider_adapter_not_implemented", claim_codes)
        self.assertEqual(validate_agent_core_provider_live_readiness_contract(contract), [])

    def test_contract_validator_rejects_fixture_drift(self) -> None:
        contract = build_agent_core_provider_live_readiness_contract(
            settings_source={"llm_provider": "openai", "openai_api_key": "sk-test"},
            codex_cli_status={"available": False, "binary_available": False, "auth_available": False},
        )
        contract["local_fixture_readiness"][0]["fixture_status"] = "failed"

        errors = validate_agent_core_provider_live_readiness_contract(contract)

        self.assertTrue(any("local fixture not ready" in item for item in errors))

    def test_checker_snapshot_uses_same_contract_validation(self) -> None:
        snapshot = build_contract_snapshot()

        self.assertEqual(validate_contract_snapshot(snapshot), [])
        self.assertEqual(snapshot["contract_version"], "agent_core.provider_live_readiness.v1")


if __name__ == "__main__":
    unittest.main()
