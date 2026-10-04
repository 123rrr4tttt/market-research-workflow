from __future__ import annotations

import unittest

import pytest

from app.services.agent_core import AgentCoreRequest, CoreToolCall
from app.services.agent_core.project_tools import build_project_core_tool_registry
from app.services.agent_core.query_tools import (
    query_project_tool_sources,
    register_query_project_tools,
)
from app.services.agent_core.registry import CoreToolRegistry
from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_sessions.store import InMemoryAgentSessionStore


pytestmark = pytest.mark.unit


class AgentCoreClueChainToolUnitTest(unittest.TestCase):
    def _service_and_session(self) -> tuple[AgentSessionService, str]:
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="agent_core",
            goal="Clue chain investigation",
            project_key="demo_proj",
            task_blueprints=[],
        )
        return service, str(bundle["session"]["session_id"])

    def test_query_catalog_registers_chain_expand_with_original_review_artifact(self):
        service, session_id = self._service_and_session()
        registry = CoreToolRegistry()
        sources = query_project_tool_sources(service=service)
        assert [source.tool_spec.name for source in sources] == [
            "project.graph.search",
            "project.structured_graph.query",
            "project.structured_data.quality_audit",
            "chain.expand",
            "source.web.search",
            "source.candidate.review",
            "skill.search",
            "source.discovery.plan",
            "skill.load",
        ]
        assert register_query_project_tools(registry=registry, service=service) is None

        result = self._execute(
            registry,
            session_id,
            "chain.expand",
            {
                "project_key": "demo_proj",
                "chain_id": "chain-catalog",
                "query": "robotics evidence",
                "mode": "source_library_search",
                "limit": 1,
            },
        )

        assert result.status == "completed"
        assert result.structured_content["requires_review"] is True
        assert result.structured_content["promoted_to_graph"] is False
        artifact = next(
            item
            for item in service.list_artifacts(session_id)
            if item["name"] == "clue_chain_expansions.json"
        )
        assert artifact["content_json"]["guardrails"]["silent_promote_allowed"] is False

    def _execute(self, registry, session_id: str, tool_name: str, arguments: dict):
        spec = registry.get(tool_name)
        request = AgentCoreRequest(
            message="expand clue chain",
            session_id=session_id,
            project_key="demo_proj",
        )
        call = CoreToolCall(
            tool_name=tool_name,
            arguments=arguments,
            call_id=f"call-{tool_name}",
        )
        return registry.execute_tool(
            tool_call=call,
            tool_spec=spec,
            request=request,
            emit=lambda _event: None,
        )

    def test_chain_expand_is_callable_and_requires_review_without_graph_promotion(self):
        service, session_id = self._service_and_session()
        registry = build_project_core_tool_registry(
            service=service, source_library_lister=lambda _: []
        )
        specs = {spec.name: spec for spec in registry.list_specs()}
        assert "chain.expand" in specs
        assert specs["chain.expand"].permission == "allow"
        assert specs["chain.expand"].risk == "write_shared"

        result = self._execute(
            registry,
            session_id,
            "chain.expand",
            {
                "project_key": "demo_proj",
                "chain_id": "chain-robotics",
                "query": "warehouse robotics commercialization evidence",
                "frontier_node_ids": ["robot_company", "warehouse_pilot"],
                "mode": "source_library_search",
                "limit": 2,
            },
        )

        assert result.tool_name == "chain.expand"
        assert result.status == "completed"
        content = result.structured_content
        assert content["contract_version"] == "chain.expand.v1"
        assert content["chain_id"] == "chain-robotics"
        assert content["mode"] == "source_library_search"
        assert content["requires_review"] is True
        assert content["no_silent_promote"] is True
        assert content["promoted_to_graph"] is False
        assert content["graph_mutation_performed"] is False
        assert content["external_network_io"] is False
        assert content["candidate_count"] == 2
        assert {candidate["review_status"] for candidate in content["candidates"]} == {
            "pending_review"
        }
        artifact = next(
            item
            for item in service.list_artifacts(session_id)
            if item["name"] == "clue_chain_expansions.json"
        )
        assert artifact["content_json"]["counts"]["promoted"] == 0
        assert artifact["content_json"]["guardrails"]["silent_promote_allowed"] is False

    def test_chain_expand_requires_chain_id(self):
        service, session_id = self._service_and_session()
        registry = build_project_core_tool_registry(
            service=service, source_library_lister=lambda _: []
        )
        result = self._execute(
            registry,
            session_id,
            "chain.expand",
            {"project_key": "demo_proj", "query": "robotics", "mode": "source_library_search"},
        )
        assert result.status == "failed"
        assert result.error["code"] == "missing_chain_id"

    def test_external_fixture_mode_is_offline_and_review_only(self):
        service, session_id = self._service_and_session()
        registry = build_project_core_tool_registry(
            service=service, source_library_lister=lambda _: []
        )
        result = self._execute(
            registry,
            session_id,
            "chain.expand",
            {
                "project_key": "demo_proj",
                "chain_id": "chain-fixture",
                "query": "robotics policy filing",
                "provider": "external_search_fixture",
                "limit": 1,
            },
        )
        content = result.structured_content
        assert content["mode"] == "external_search_fixture"
        assert content["fixture_gated"] is True
        assert content["external_network_io"] is False
        assert content["graph_mutation_performed"] is False
        assert content["candidates"][0]["candidate_type"] == "external_search_fixture_lead"
        assert content["candidates"][0]["proposed_graph_nodes"] == []
        assert content["candidates"][0]["proposed_graph_edges"] == []
