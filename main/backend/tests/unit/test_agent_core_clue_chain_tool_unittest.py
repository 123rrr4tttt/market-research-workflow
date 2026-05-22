from __future__ import annotations

import unittest

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

    def test_chain_expand_is_callable_and_requires_review_without_graph_promotion(self):
        service, session_id = self._service_and_session()
        registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
        specs = {spec.name: spec for spec in registry.list_specs()}
        self.assertIn("chain.expand", specs)
        self.assertEqual(specs["chain.expand"].permission, "allow")
        self.assertEqual(specs["chain.expand"].risk, "write_shared")

        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="chain.expand",
                        call_id="call-chain-expand",
                        arguments={
                            "project_key": "demo_proj",
                            "chain_id": "chain-robotics",
                            "query": "warehouse robotics commercialization evidence",
                            "frontier_node_ids": ["robot_company", "warehouse_pilot"],
                            "mode": "source_library_search",
                            "limit": 2,
                        },
                    )
                ),
                CoreModelStep.final("已创建线索链扩展候选，等待审核。"),
            ]
        )
        out = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs()).run(
            AgentCoreRequest(
                message="扩展这条线索链，从 frontier 节点继续找证据",
                session_id=session_id,
                project_key="demo_proj",
            )
        )

        self.assertEqual(out.stop_reason, "final_answer")
        result = out.tool_results[0]
        self.assertEqual(result.tool_name, "chain.expand")
        self.assertEqual(result.status, "completed")
        content = result.structured_content
        self.assertEqual(content["contract_version"], "chain.expand.v1")
        self.assertEqual(content["chain_id"], "chain-robotics")
        self.assertEqual(content["mode"], "source_library_search")
        self.assertTrue(content["requires_review"])
        self.assertTrue(content["no_silent_promote"])
        self.assertFalse(content["promoted_to_graph"])
        self.assertFalse(content["graph_mutation_performed"])
        self.assertFalse(content["external_network_io"])
        self.assertEqual(content["candidate_count"], 2)
        self.assertEqual(
            {candidate["review_status"] for candidate in content["candidates"]},
            {"pending_review"},
        )
        self.assertTrue(all(candidate["requires_review"] for candidate in content["candidates"]))
        self.assertTrue(all(not candidate["promoted_to_graph"] for candidate in content["candidates"]))
        self.assertEqual(content["decision_gate"]["decision_contract"], "ChainDecision")
        self.assertIn("/api/v1/clue-chains/chain-robotics/candidates/{candidate_id}/decision", content["decision_gate"]["decision_api"])

        artifacts = service.list_artifacts(session_id)
        artifact = next(item for item in artifacts if item["name"] == "clue_chain_expansions.json")
        artifact_content = artifact["content_json"]
        self.assertEqual(artifact_content["counts"]["promoted"], 0)
        self.assertFalse(artifact_content["guardrails"]["silent_promote_allowed"])
        self.assertFalse(artifact_content["guardrails"]["graph_mutation_performed"])

    def test_chain_expand_requires_chain_id(self):
        service, session_id = self._service_and_session()
        registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="chain.expand",
                        call_id="call-missing-chain",
                        arguments={"project_key": "demo_proj", "query": "robotics", "mode": "source_library_search"},
                    )
                ),
                CoreModelStep.final("缺少 chain_id。"),
            ]
        )
        out = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs()).run(
            AgentCoreRequest(
                message="扩展线索链",
                session_id=session_id,
                project_key="demo_proj",
            )
        )

        result = out.tool_results[0]
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error["code"], "missing_chain_id")

    def test_external_fixture_mode_is_offline_and_review_only(self):
        service, session_id = self._service_and_session()
        registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="chain.expand",
                        call_id="call-external-fixture",
                        arguments={
                            "project_key": "demo_proj",
                            "chain_id": "chain-fixture",
                            "query": "robotics policy filing",
                            "provider": "external_search_fixture",
                            "limit": 1,
                        },
                    )
                ),
                CoreModelStep.final("已创建 fixture 候选。"),
            ]
        )
        out = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs()).run(
            AgentCoreRequest(
                message="用外部搜索 fixture 扩展这条线索链",
                session_id=session_id,
                project_key="demo_proj",
            )
        )

        content = out.tool_results[0].structured_content
        self.assertEqual(content["mode"], "external_search_fixture")
        self.assertTrue(content["fixture_gated"])
        self.assertFalse(content["external_network_io"])
        self.assertFalse(content["graph_mutation_performed"])
        self.assertEqual(content["candidates"][0]["candidate_type"], "external_search_fixture_lead")
        self.assertEqual(content["candidates"][0]["proposed_graph_nodes"], [])
        self.assertEqual(content["candidates"][0]["proposed_graph_edges"], [])

    def test_tool_window_exposes_chain_expand_only_for_clue_chain_context(self):
        service, _session_id = self._service_and_session()
        registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
        specs = registry.list_specs()

        general = select_core_tool_window(message="你好", tool_specs=specs)
        self.assertEqual(general.profile, "conversation")
        self.assertNotIn("chain.expand", [spec.name for spec in general.specs])

        project_data = select_core_tool_window(message="项目里有什么数据", tool_specs=specs)
        self.assertEqual(project_data.profile, "project-context")
        self.assertNotIn("chain.expand", [spec.name for spec in project_data.specs])

        source_library = select_core_tool_window(message="当前项目有哪些来源库 item？", tool_specs=specs)
        self.assertEqual(source_library.profile, "source-library-read")
        self.assertNotIn("chain.expand", [spec.name for spec in source_library.specs])

        clue_chain = select_core_tool_window(
            message="扩展这条线索链，从 workflow graph frontier 节点继续找证据",
            tool_specs=specs,
        )
        self.assertEqual(clue_chain.profile, "clue-chain-investigation")
        clue_chain_tools = [spec.name for spec in clue_chain.specs]
        self.assertIn("chain.expand", clue_chain_tools)
        self.assertIn("project.structured_graph.query", clue_chain_tools)
        self.assertIn("source_library.item.search", clue_chain_tools)


if __name__ == "__main__":
    unittest.main()
