from __future__ import annotations

import unittest

import pytest

from app.services.llm.platformization import (
    evaluate_agent_permission_boundary,
    normalize_capability,
    normalize_agent_role,
    resolve_consumer_adapter_boundary,
    resolve_request_identity,
    resolve_routing_decision,
)

pytestmark = pytest.mark.unit


class LlmPlatformizationUnitTest(unittest.TestCase):
    def test_normalize_capability_falls_back_to_general_chat(self):
        self.assertEqual(normalize_capability("workflow_llm_call"), "workflow_llm_call")
        self.assertEqual(normalize_capability("unknown_capability"), "general_chat")

    def test_resolve_request_identity_uses_request_id_when_trace_missing(self):
        identity = resolve_request_identity(
            consumer="writing.llm_action",
            trace_id=None,
            request_id="req-1",
            project_key="demo_proj",
        )
        self.assertEqual(identity.trace_id, "req-1")
        self.assertEqual(identity.request_id, "req-1")
        self.assertEqual(identity.project_key, "demo_proj")

    def test_resolve_routing_decision_prefers_request_overrides(self):
        routing = resolve_routing_decision(
            service_name="policy_summary",
            capability="workflow_llm_call",
            request_overrides={
                "provider": "openai",
                "model": "gpt-4o-mini",
                "temperature": "0.1",
                "max_tokens": "320",
                "top_p": "0.9",
            },
            service_config={
                "provider": "azure",
                "model": "gpt-4.1",
                "temperature": 0.2,
            },
            default_provider="litellm",
            default_model="gpt-default",
        )
        self.assertEqual(routing.route_kind, "request_override")
        self.assertEqual(routing.model, "gpt-4o-mini")
        self.assertEqual(routing.provider, "openai")
        self.assertEqual(routing.field_sources["model"], "request")
        self.assertEqual(routing.field_sources["provider"], "request")

    def test_resolve_consumer_adapter_boundary_for_known_consumer(self):
        boundary = resolve_consumer_adapter_boundary("workflow_graph.llm_call")
        self.assertEqual(boundary.capability, "workflow_llm_call")
        self.assertEqual(boundary.routing_owner, "llm.platformization_routing")
        self.assertIn("provider.route_override", boundary.allowed_permissions)

    def test_evaluate_agent_permission_boundary_denies_cross_consumer_permission(self):
        decision = evaluate_agent_permission_boundary(
            consumer="writing.llm_action",
            agent_role=normalize_agent_role("business_capability_wrapper", consumer="writing.llm_action"),
            requested_permissions=["llm.invoke", "cross_consumer.invoke"],
        )
        self.assertFalse(decision.allowed)
        self.assertIn("permission_not_allowed_for_consumer", decision.denied_reasons)
        self.assertIn("cross_consumer.invoke", decision.denied_permissions)

    def test_evaluate_agent_permission_boundary_denies_invalid_role_for_consumer(self):
        decision = evaluate_agent_permission_boundary(
            consumer="llm_report.generate",
            agent_role="orchestration_runtime",
            requested_permissions=["llm.invoke"],
        )
        self.assertFalse(decision.allowed)
        self.assertIn("agent_role_not_allowed_for_consumer", decision.denied_reasons)

    def test_evaluate_agent_permission_boundary_denies_unknown_permission_explicitly(self):
        decision = evaluate_agent_permission_boundary(
            consumer="llm_report.generate",
            agent_role=normalize_agent_role("business_capability_wrapper", consumer="llm_report.generate"),
            requested_permissions=["llm.invoke", "made.up.permission"],
        )
        self.assertFalse(decision.allowed)
        self.assertIn("unknown_permission_requested", decision.denied_reasons)
        self.assertIn("made.up.permission", decision.unknown_permissions)


if __name__ == "__main__":
    unittest.main()
