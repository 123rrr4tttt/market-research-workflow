from __future__ import annotations

import socket
import unittest
from unittest.mock import patch

import pytest

from app.services.agent_core import (
    AgentCore,
    AgentCoreRequest,
    CoreModelStep,
    CoreToolCall,
    FakeCoreProvider,
    build_project_core_tool_registry,
    select_core_tool_window,
)
from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_sessions.store import InMemoryAgentSessionStore
from app.services.source_library.source_candidate_trust import build_source_candidate_plan

pytestmark = pytest.mark.unit


class SourceCandidateTrustUnitTest(unittest.TestCase):
    def test_plan_normalizes_scores_dedupes_and_blocks_private_urls(self):
        public_dns = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
        urls = [
            "https://www.google.com/url?url=https%3A%2F%2Fexample.com%2Frobot%3Futm_source%3Dfeed%26id%3D1%23frag",
            "https://example.com/robot?id=1",
            "http://127.0.0.1/admin",
        ]
        items = [
            {
                "item_key": "generic_web.rss",
                "name": "Generic RSS",
                "channel_key": "generic_web",
                "description": "robot funding news",
                "enabled": True,
            },
            {
                "item_key": "handler.cluster.search_template",
                "name": "Search Template Cluster",
                "channel_key": "handler.cluster",
                "description": "robot commercialization funding news",
                "enabled": True,
            },
        ]

        with patch("app.services.source_library.external_project.socket.getaddrinfo", return_value=public_dns):
            plan = build_source_candidate_plan(
                project_key="demo_proj",
                query="robot funding",
                urls=urls,
                domains=["example.com"],
                source_library_items=items,
                max_candidates=10,
            )

        self.assertEqual(plan["counts"]["candidate_urls"], 1)
        self.assertEqual(plan["counts"]["duplicate_urls"], 1)
        self.assertEqual(plan["candidate_urls"][0]["normalized_url"], "https://example.com/robot?id=1")
        self.assertIn("query_wrapped_url", plan["candidate_urls"][0]["normalization_steps"])
        self.assertEqual(plan["duplicate_urls"][0]["blocked_reason"], "duplicate_candidate_url")
        self.assertEqual(plan["rejected_urls"][0]["domain"], "127.0.0.1")
        self.assertIn("localhost", plan["rejected_urls"][0]["blocked_reason"])
        self.assertEqual(plan["candidate_source_items"][0]["item_key"], "handler.cluster.search_template")
        self.assertFalse(plan["trust_policy"]["network_fetch_performed"])
        self.assertIn("redirect_chain_validation", plan["trust_policy"]["pre_ingest_required_checks"])

    def test_agent_core_exposes_source_discovery_plan_as_read_only_p1_gate(self):
        public_dns = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="source discovery",
            project_key="demo_proj",
            task_blueprints=[],
        )
        registry = build_project_core_tool_registry(
            service=service,
            source_library_lister=lambda _project_key: [
                {
                    "item_key": "handler.cluster.search_template",
                    "name": "Search Template Cluster",
                    "channel_key": "handler.cluster",
                    "description": "robot commercialization funding news",
                    "enabled": True,
                }
            ],
        )
        specs = {spec.name: spec for spec in registry.list_specs()}
        self.assertEqual(specs["source.discovery.plan"].risk, "read_only")
        self.assertEqual(specs["source.discovery.plan"].permission, "allow")

        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="source.discovery.plan",
                        call_id="call-plan",
                        arguments={
                            "topic": "robot funding",
                            "candidate_urls": ["https://example.com/robot?id=1"],
                            "domains": ["example.com"],
                        },
                    )
                ),
                CoreModelStep.final("source discovery planned"),
            ]
        )
        core = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs())

        with patch("app.services.source_library.external_project.socket.getaddrinfo", return_value=public_dns):
            out = core.run(
                AgentCoreRequest(
                    message="规划来源库候选和 URL trust gate",
                    session_id=bundle["session"]["session_id"],
                    project_key="demo_proj",
                )
            )

        self.assertEqual(out.stop_reason, "final_answer")
        result = out.tool_results[0].structured_content
        self.assertEqual(result["candidate_urls"][0]["normalized_url"], "https://example.com/robot?id=1")
        self.assertFalse(result["quality_gates"]["network_fetch_performed"])
        self.assertEqual(result["candidate_source_items"][0]["item_key"], "handler.cluster.search_template")
        self.assertNotIn("permission_requested", [event.event_type for event in out.events])

        window = select_core_tool_window(message="规划来源库候选 URL trust", tool_specs=registry.list_specs())
        self.assertEqual(window.profile, "source-discovery-plan")
        self.assertIn("source.discovery.plan", [spec.name for spec in window.specs])


if __name__ == "__main__":
    unittest.main()
