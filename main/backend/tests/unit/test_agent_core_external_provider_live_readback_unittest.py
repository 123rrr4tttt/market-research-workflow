from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.agent_core.external_provider_live_readback import (
    build_agent_core_external_provider_live_readback_evidence,
    validate_agent_core_external_provider_live_readback_evidence,
)
from scripts.check_agent_core_external_provider_live_readback import validate_contract_snapshot


pytestmark = pytest.mark.unit


class AgentCoreExternalProviderLiveReadbackUnitTest(unittest.TestCase):
    def test_external_provider_live_readback_closes_with_recorded_native_tool_call(self) -> None:
        evidence = build_agent_core_external_provider_live_readback_evidence(
            settings_source={
                "llm_provider": "openai",
                "openai_api_key": "sk-fixture",
                "openai_api_base": "https://api.example.test/v1",
            },
            chat_model_factory=_FakeExternalToolCallingChat,
            allow_external_network=True,
            timeout_ms=5000,
            model="gpt-fixture-live",
        )

        self.assertEqual(validate_agent_core_external_provider_live_readback_evidence(evidence), [])
        self.assertEqual(validate_contract_snapshot(evidence), [])
        self.assertEqual(evidence["contract_version"], "agent_core.external_provider_live_readback.v1")
        self.assertEqual(evidence["status"], "passed")
        self.assertTrue(evidence["closed"])
        self.assertTrue(evidence["external_provider_live_verified"])
        self.assertEqual(evidence["external_model_calls"], 2)
        self.assertEqual(evidence["provider_invocation"]["network_scope"], "external_provider_network")
        self.assertEqual(evidence["provider_invocation"]["account_state"], "selected_provider_credentials_configured")
        self.assertEqual(evidence["tool_call_readback"]["shape_status"], "valid")
        self.assertTrue(evidence["tool_call_readback"]["arguments_redacted"])
        self.assertTrue(evidence["status_data_error_meta_trace"]["compatible"])
        self.assertEqual(evidence["reviewer_readback"]["status"], "accepted")
        self.assertTrue(evidence["redaction"]["raw_sensitive_values_absent"])
        self.assertEqual(evidence["remaining_blockers"], [])

    def test_missing_selected_provider_config_records_exact_blocker_without_false_closure(self) -> None:
        evidence = build_agent_core_external_provider_live_readback_evidence(
            settings_source={"llm_provider": "openai", "openai_api_key": None},
            allow_external_network=True,
        )

        self.assertEqual(validate_agent_core_external_provider_live_readback_evidence(evidence), [])
        self.assertFalse(evidence["closed"])
        self.assertEqual(evidence["status"], "blocked")
        self.assertFalse(evidence["external_provider_live_verified"])
        self.assertEqual(evidence["external_model_calls"], 0)
        self.assertEqual(evidence["remaining_blockers"][0]["code"], "missing_openai_provider_config")
        self.assertIn("OPENAI_API_KEY", evidence["remaining_blockers"][0]["detail"])

    def test_external_network_must_be_explicitly_allowed(self) -> None:
        evidence = build_agent_core_external_provider_live_readback_evidence(
            settings_source={"llm_provider": "openai", "openai_api_key": "sk-fixture"},
            allow_external_network=False,
        )

        self.assertEqual(validate_agent_core_external_provider_live_readback_evidence(evidence), [])
        self.assertFalse(evidence["closed"])
        self.assertEqual(evidence["remaining_blockers"][0]["code"], "external_network_not_allowed")


class _FakeExternalToolCallingChat:
    def __init__(self) -> None:
        self.calls = 0
        self.bound_tools: list[dict[str, Any]] = []

    def bind_tools(self, tools: Any) -> "_FakeExternalToolCallingChat":
        self.bound_tools = list(tools or [])
        return self

    def invoke(self, messages: Any) -> SimpleNamespace:
        self.calls += 1
        if self.calls == 1:
            tool = self.bound_tools[0]["function"]
            return SimpleNamespace(
                content="",
                additional_kwargs={
                    "tool_calls": [
                        {
                            "id": "call-agent-core-external-provider-live",
                            "type": "function",
                            "function": {
                                "name": tool["name"],
                                "arguments": json.dumps(
                                    {
                                        "query": "external-provider-live-readback",
                                        "trace_id": "trace-agent-core-external-provider-live-readback",
                                        "request_body": "wave55-agentcore-external-provider-live-readback-sentinel::not-a-secret;redaction-required",
                                    },
                                    sort_keys=True,
                                ),
                            },
                        }
                    ]
                },
                response_metadata={"model_name": "gpt-fixture-live", "finish_reason": "tool_calls"},
            )
        return SimpleNamespace(
            content="external provider live readback confirmed",
            tool_calls=[],
            response_metadata={"model_name": "gpt-fixture-live", "finish_reason": "stop"},
        )


if __name__ == "__main__":
    unittest.main()
