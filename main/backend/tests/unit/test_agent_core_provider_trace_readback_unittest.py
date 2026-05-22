from __future__ import annotations

import unittest

import pytest

from app.services.agent_core.provider_trace import (
    build_agent_core_provider_trace_readback_contract,
    validate_agent_core_provider_trace_readback_contract,
)
from scripts.check_agent_core_provider_trace_readback import build_contract_snapshot, validate_contract_snapshot


pytestmark = pytest.mark.unit


class AgentCoreProviderTraceReadbackUnitTest(unittest.TestCase):
    def test_provider_trace_readback_records_fake_provider_and_open_live_gap(self) -> None:
        contract = build_agent_core_provider_trace_readback_contract()

        self.assertEqual(validate_agent_core_provider_trace_readback_contract(contract), [])
        self.assertEqual(contract["contract_version"], "agent_core.provider_trace_readback.v1")
        self.assertEqual(contract["status"], "passed")
        self.assertTrue(contract["deterministic_provider_trace_ready"])
        self.assertTrue(contract["real_external_provider_call_open"])
        self.assertEqual(contract["external_model_calls"], 0)

        trace = contract["provider_trace"]
        self.assertEqual(trace["provider_key"], "fake_core_provider")
        self.assertEqual(trace["trace_status"], "passed")
        self.assertEqual(trace["call_count"], 2)
        self.assertEqual(trace["calls"][0]["context"]["trace_id"], "trace-agent-core-provider-trace-readback")
        self.assertIn("agent.provider_trace.echo", trace["calls"][0]["tool_names"])
        self.assertTrue(trace["calls"][1]["tool_result_seen"])
        self.assertTrue(trace["calls"][1]["status_data_error_meta_seen_in_transcript"])

        envelope = contract["tool_call_envelope"]
        self.assertEqual(envelope["tool_call_contract"]["contract_version"], "agent_core.tool_call_shape.v1")
        self.assertEqual(envelope["tool_call_contract"]["shape_status"], "valid")
        self.assertEqual(envelope["tool_call_contract"]["tool_name"], "agent.provider_trace.echo")
        self.assertEqual(
            [event["event_type"] for event in envelope["tool_event_sequence"]],
            ["tool_call_requested", "tool_call_started", "tool_result"],
        )
        self.assertEqual(envelope["tool_result_status_counts"]["completed"], 1)

        compat = contract["status_data_error_meta_compatibility"]
        self.assertTrue(compat["compatible"])
        self.assertEqual(compat["present_keys"], ["data", "error", "meta", "status"])
        self.assertEqual(compat["status"], "ok")
        self.assertTrue(compat["error_is_null"])
        self.assertTrue(compat["meta"]["real_external_provider_call_open"])

    def test_provider_trace_readback_links_wave11_wave13_wave14_inputs(self) -> None:
        contract = build_agent_core_provider_trace_readback_contract()
        readbacks = contract["input_contract_readbacks"]

        self.assertEqual(readbacks["wave11_provider_matrix"]["contract_version"], "agent_core.provider_capability_matrix.v1")
        self.assertFalse(readbacks["wave11_provider_matrix"]["live_provider_claims"])
        self.assertEqual(readbacks["wave11_provider_matrix"]["fake_core_provider_status"], "repo_native_supported")
        self.assertEqual(readbacks["wave13_live_provider_readiness"]["contract_version"], "agent_core.provider_live_readiness.v1")
        self.assertEqual(readbacks["wave13_live_provider_readiness"]["readiness_state"], "partial")
        self.assertIn(
            "selected_provider_live_availability_not_closed",
            readbacks["wave13_live_provider_readiness"]["unsupported_claim_codes"],
        )
        self.assertEqual(readbacks["wave14_tool_calling_quality"]["contract_version"], "agent_core.tool_calling_quality.v1")
        self.assertTrue(readbacks["wave14_tool_calling_quality"]["deterministic_tool_calling_ready"])
        self.assertEqual(readbacks["wave14_tool_calling_quality"]["external_provider_live_gap"], "external_provider_live_gap")

    def test_validator_rejects_closed_real_external_provider_gap(self) -> None:
        contract = build_agent_core_provider_trace_readback_contract()
        contract["real_external_provider_call_open"] = False

        errors = validate_agent_core_provider_trace_readback_contract(contract)

        self.assertTrue(any("real external provider call is not marked open" in item for item in errors))

    def test_checker_snapshot_uses_same_contract_validation(self) -> None:
        snapshot = build_contract_snapshot()

        self.assertEqual(validate_contract_snapshot(snapshot), [])
        self.assertTrue(snapshot["real_external_provider_call_open"])
        self.assertTrue(snapshot["status_data_error_meta_compatibility"]["compatible"])

    def test_contract_snapshot_is_deterministic(self) -> None:
        first = build_agent_core_provider_trace_readback_contract()
        second = build_agent_core_provider_trace_readback_contract()

        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
