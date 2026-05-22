from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.agent_core import AgentCoreRequest, CoreToolSpec, NativeToolCallingCoreProvider
from app.services.agent_core.native_provider import _native_tool_name
from app.services.agent_core.tool_calling_quality import (
    build_agent_core_tool_calling_quality_contract,
    validate_agent_core_tool_calling_quality_contract,
)
from scripts.check_agent_core_tool_calling_quality import build_contract_snapshot, validate_contract_snapshot


pytestmark = pytest.mark.unit


class AgentCoreToolCallingQualityUnitTest(unittest.TestCase):
    def test_tool_calling_quality_contract_records_provider_shape_and_live_gap(self) -> None:
        contract = build_agent_core_tool_calling_quality_contract()

        self.assertEqual(validate_agent_core_tool_calling_quality_contract(contract), [])
        self.assertEqual(contract["contract_version"], "agent_core.tool_calling_quality.v1")
        self.assertEqual(contract["status"], "passed")
        self.assertTrue(contract["deterministic_tool_calling_ready"])
        self.assertEqual(contract["quality_gate"]["live_model_calls"], 0)
        self.assertFalse(contract["quality_gate"]["quality_claim_allowed"])

        rows = {row["provider_key"]: row for row in contract["provider_tool_call_contracts"]}
        self.assertEqual(set(rows), {"fake_core_provider", "json_core_provider", "native_tool_calling_provider"})
        for provider_key, row in rows.items():
            self.assertEqual(row["fixture_status"], "ready")
            self.assertEqual(row["step_type"], "tool_calls")
            self.assertEqual(row["tool_call_contract"]["contract_version"], "agent_core.tool_call_shape.v1")
            self.assertEqual(row["tool_call_contract"]["shape_status"], "valid")
            self.assertEqual(row["tool_call_contract"]["tool_name"], "agent.tool_calling_quality.echo")
            self.assertEqual(row["schema_validation"]["status"], "passed")
            self.assertEqual(row["runtime_dispatch"]["stop_reason"], "final_answer")
            self.assertEqual(
                [event["event_type"] for event in row["runtime_dispatch"]["tool_event_sequence"]],
                ["tool_call_requested", "tool_call_started", "tool_result"],
            )

        native_wire = rows["native_tool_calling_provider"]["provider_wire_contract"]
        self.assertEqual(native_wire["wire_protocol"], "native_bind_tools_function_call")
        self.assertEqual(native_wire["canonical_tool_name"], "agent.tool_calling_quality.echo")
        self.assertTrue(native_wire["safe_name_changed"])

        gap = contract["external_provider_live_gap"]
        self.assertEqual(gap["state"], "external_provider_live_gap")
        self.assertEqual(gap["live_model_calls"], 0)
        self.assertFalse(gap["quality_claim_allowed"])
        claim_codes = {row["code"] for row in contract["unsupported_closure_claims"]}
        self.assertIn("deterministic_fixture_proves_external_provider_quality", claim_codes)

    def test_validator_rejects_tool_call_shape_drift(self) -> None:
        contract = build_agent_core_tool_calling_quality_contract()
        contract["provider_tool_call_contracts"][0]["tool_call_contract"]["shape_status"] = "invalid"

        errors = validate_agent_core_tool_calling_quality_contract(contract)

        self.assertTrue(any("tool-call shape invalid" in item for item in errors))

    def test_checker_snapshot_uses_same_contract_validation(self) -> None:
        snapshot = build_contract_snapshot()

        self.assertEqual(validate_contract_snapshot(snapshot), [])
        self.assertTrue(snapshot["deterministic_tool_calling_ready"])
        self.assertEqual(snapshot["external_provider_live_gap"]["state"], "external_provider_live_gap")

    def test_contract_snapshot_is_deterministic(self) -> None:
        first = build_agent_core_tool_calling_quality_contract()
        second = build_agent_core_tool_calling_quality_contract()

        self.assertEqual(first, second)

    def test_native_provider_maps_openai_function_tool_calls_to_core_shape(self) -> None:
        spec = CoreToolSpec(
            name="agent.tool_calling_quality.echo",
            description_for_model="Echo for native function-call shape.",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
        )
        provider = NativeToolCallingCoreProvider(chat_model=_OpenAiFunctionToolCallChat())

        step = provider.next_step(
            request=AgentCoreRequest(
                message="Call the quality echo tool.",
                session_id="native-openai-function-shape-test",
                turn_id="turn-native-openai-function-shape-test",
                project_key="demo_proj",
            ),
            tools=[spec],
            transcript=[],
            remaining_budget={"max_iterations": 2, "iteration": 1, "max_tool_calls": 1, "remaining_tool_calls": 1},
        )

        self.assertEqual(step.step_type, "tool_calls")
        self.assertEqual(step.metadata["model_path"], "native_tool_calling_provider")
        self.assertEqual(len(step.tool_calls), 1)
        call = step.tool_calls[0]
        self.assertEqual(call.call_id, "call-native-openai-function-shape")
        self.assertEqual(call.tool_name, "agent.tool_calling_quality.echo")
        self.assertEqual(call.arguments, {"query": "native-openai-shape"})


class _OpenAiFunctionToolCallChat:
    def bind_tools(self, tools: Any) -> "_OpenAiFunctionToolCallChat":
        self.bound_tools = list(tools or [])
        return self

    def invoke(self, messages: Any) -> SimpleNamespace:
        return SimpleNamespace(
            content="",
            additional_kwargs={
                "tool_calls": [
                    {
                        "id": "call-native-openai-function-shape",
                        "type": "function",
                        "function": {
                            "name": _native_tool_name("agent.tool_calling_quality.echo"),
                            "arguments": json.dumps({"query": "native-openai-shape"}),
                        },
                    }
                ]
            },
        )


if __name__ == "__main__":
    unittest.main()
