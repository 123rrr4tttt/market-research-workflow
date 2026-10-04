from __future__ import annotations

import socket
import unittest
from unittest.mock import patch

import pytest

from app.services.agent_core import AgentCoreRequest, CoreToolCall
from app.services.agent_core.project_tools import build_project_core_tool_registry
from app.services.agent_core.query_tools import register_query_project_tools
from app.services.agent_core.registry import CoreToolRegistry
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

        with patch(
            "app.services.source_library.external_project.socket.getaddrinfo",
            return_value=public_dns,
        ):
            plan = build_source_candidate_plan(
                project_key="demo_proj",
                query="robot funding",
                urls=urls,
                domains=["example.com"],
                source_library_items=items,
                max_candidates=10,
            )

        assert plan["counts"]["candidate_urls"] == 1
        assert plan["counts"]["duplicate_urls"] == 1
        assert plan["candidate_urls"][0]["normalized_url"] == "https://example.com/robot?id=1"
        assert plan["candidate_urls"][0]["source_policy_action"] == "allow"
        assert (
            plan["candidate_source_items"][0]["item_key"]
            == "handler.cluster.search_template"
        )
        assert plan["trust_policy"]["network_fetch_performed"] is False
        assert plan["rejected_urls"][0]["source_policy_action"] == "block"

    def test_plan_marks_medium_trust_candidates_as_downgraded_review_path(self):
        public_dns = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
        with patch(
            "app.services.source_library.external_project.socket.getaddrinfo",
            return_value=public_dns,
        ):
            plan = build_source_candidate_plan(
                project_key="demo_proj",
                query="robot funding",
                urls=["https://example.org/general"],
                domains=[],
                source_library_items=[],
                max_candidates=10,
            )

        candidate = plan["candidate_urls"][0]
        assert candidate["status"] == "accepted"
        assert candidate["trust_level"] == "medium"
        assert candidate["source_policy_action"] == "downgrade"

    def test_query_catalog_preserves_source_discovery_no_effect_gate(self):
        public_dns = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="source discovery",
            project_key="demo_proj",
            task_blueprints=[],
        )
        registry = CoreToolRegistry()
        assert (
            register_query_project_tools(
                registry=registry,
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
            is None
        )
        spec = registry.get("source.discovery.plan")
        request = AgentCoreRequest(
            message="plan source candidates",
            session_id=bundle["session"]["session_id"],
            project_key="demo_proj",
        )
        call = CoreToolCall(
            tool_name="source.discovery.plan",
            call_id="call-query-catalog-plan",
            arguments={
                "topic": "robot funding",
                "candidate_urls": ["https://example.com/robot?id=1"],
                "domains": ["example.com"],
            },
        )
        with patch(
            "app.services.source_library.external_project.socket.getaddrinfo",
            return_value=public_dns,
        ):
            result = registry.execute_tool(
                tool_call=call,
                tool_spec=spec,
                request=request,
                emit=lambda _event: None,
            )
        content = result.structured_content
        assert spec.risk == "read_only"
        assert content["candidate_urls"][0]["normalized_url"] == "https://example.com/robot?id=1"
        assert content["candidate_source_items"][0]["item_key"] == "handler.cluster.search_template"
        assert content["quality_gates"]["network_fetch_performed"] is False
        assert content["quality_gates"]["external_write_performed"] is False

    def test_project_registry_exposes_source_discovery_plan_as_read_only_gate(self):
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
        assert specs["source.discovery.plan"].risk == "read_only"
        assert specs["source.discovery.plan"].permission == "allow"
        request = AgentCoreRequest(
            message="plan source candidates",
            session_id=bundle["session"]["session_id"],
            project_key="demo_proj",
        )
        call = CoreToolCall(
            tool_name="source.discovery.plan",
            call_id="call-plan",
            arguments={
                "topic": "robot funding",
                "candidate_urls": ["https://example.com/robot?id=1"],
                "domains": ["example.com"],
            },
        )
        with patch(
            "app.services.source_library.external_project.socket.getaddrinfo",
            return_value=public_dns,
        ):
            result = registry.execute_tool(
                tool_call=call,
                tool_spec=specs["source.discovery.plan"],
                request=request,
                emit=lambda _event: None,
            )
        content = result.structured_content
        assert content["candidate_urls"][0]["normalized_url"] == "https://example.com/robot?id=1"
        assert content["quality_gates"]["network_fetch_performed"] is False
        assert content["candidate_source_items"][0]["item_key"] == "handler.cluster.search_template"
