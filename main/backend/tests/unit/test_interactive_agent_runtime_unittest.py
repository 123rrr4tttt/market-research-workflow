from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

import pytest

from app.services.agent_runtime.interactive_agent import InteractiveAgentRuntime
from app.services.agent_runtime.tool_contract import build_capability_call
from app.services.agent_runtime.turn_decision import GuardedModelTurnDecisionPlanner
from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_sessions.store import InMemoryAgentSessionStore
from app.services.workflow_graph import WorkflowGraphCompilerService
from app.services.workflow_graph.store import InMemoryCompiledGraphStore

pytestmark = pytest.mark.unit


def _fake_loop_runner(**kwargs):
    return {
        "loop_id": "abl-test",
        "parsed": {"channel": "search.market", "command": kwargs["command"]},
        "plan": {
            "intent": "market_research",
            "tasks": [{"channel": "search.market", "query_terms": [kwargs["command"]], "max_items": 3}],
            "search_brief": {"retrieval_mode": "hybrid"},
        },
        "submit": {"job_id": "abj-test", "accepted_count": 1, "rejected_count": 0, "status": "accepted"},
    }


class InteractiveAgentRuntimeUnitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = AgentSessionService(store=InMemoryAgentSessionStore())
        self.runtime = InteractiveAgentRuntime(service=self.service)

    def _run_turn(self, **overrides):
        def structured_data_searcher(**kwargs):
            return {
                "contract_version": "project.structured_data.search.v1",
                "project_key": kwargs.get("project_key"),
                "query": "",
                "query_mode": "inventory",
                "inventory": [{"dataset": "documents", "label": "Documents", "sample_count": 1, "total_rows": 2}],
                "dataset_counts": {"documents": 1},
                "total_matches": 1,
                "items": [{"dataset": "documents", "record_id": 1, "title": "Demo document", "summary": "stored row"}],
                "dataset_results": [],
                "errors": [],
            }

        return self.runtime.run_turn(
            message=overrides.pop("message", "采集最近 7 天 AI 终端融资动态"),
            project_key=overrides.pop("project_key", "demo_proj"),
            batch_loop_runner=overrides.pop("batch_loop_runner", _fake_loop_runner),
            parser_fallback=lambda command: {"command": command},
            submitter=lambda tasks, project_key, idem: {"job_id": "unused"},
            executor_snapshot=lambda: {"status": "ok"},
            structured_data_searcher=overrides.pop("structured_data_searcher", structured_data_searcher),
            **overrides,
        )

    def test_run_turn_creates_session_tasks_events_and_final_answer(self):
        out = self._run_turn()

        self.assertEqual(out["contract_version"], "interactive_agent.turn.v1")
        self.assertEqual(out["session"]["entrypoint_type"], "interactive_agent")
        self.assertEqual(out["session"]["status"], "completed")
        self.assertIn("job_id=abj-test", out["final_answer"])
        self.assertIn("agent_batch.nl_command.submit", [item["capability_id"] for item in out["capability_calls"]])
        self.assertIn("source_library.item.list", [item["capability_id"] for item in out["capability_calls"]])

        event_types = [item["event_type"] for item in out["events"]]
        self.assertIn("interactive_agent.turn_started", event_types)
        self.assertIn("interactive_agent.capability_planned", event_types)
        self.assertIn("interactive_agent.capability_executed", event_types)
        self.assertIn("interactive_agent.tool_call_result", event_types)
        self.assertIn("interactive_agent.final_answer", event_types)

        artifact_names = [item["name"] for item in out["artifacts"]]
        self.assertTrue(any(name.startswith("interactive_agent.plan.") for name in artifact_names))
        self.assertTrue(any(name.startswith("interactive_agent.capability_call.") for name in artifact_names))
        self.assertTrue(any(name.startswith("interactive_agent.loop_result.") for name in artifact_names))
        self.assertTrue(any(name.startswith("interactive_agent.final_answer.") for name in artifact_names))

    def test_run_turn_appends_to_existing_session(self):
        first = self._run_turn(message="分析 California gas price")
        session_id = first["session"]["session_id"]

        second = self._run_turn(message="继续补充来源库证据", session_id=session_id)

        self.assertEqual(second["session"]["session_id"], session_id)
        self.assertGreaterEqual(len(second["messages"]), 4)
        self.assertGreaterEqual(len(second["tasks"]), 6)
        self.assertTrue(any("ingest.source_library.run" == item.get("capability_id") for item in second["plan"]["selected_capabilities"]))

    def test_run_turn_project_mismatch_is_rejected(self):
        first = self._run_turn(project_key="demo_proj")
        with self.assertRaises(ValueError):
            self._run_turn(session_id=first["session"]["session_id"], project_key="other_proj")

    def test_run_turn_failure_is_projected_to_session(self):
        def fail_runner(**kwargs):
            raise RuntimeError("planner unavailable")

        out = self._run_turn(batch_loop_runner=fail_runner)

        self.assertEqual(out["session"]["status"], "failed")
        self.assertIn("planner unavailable", out["final_answer"])
        self.assertIn("interactive_agent.failed", [item["event_type"] for item in out["events"]])

    def test_capability_question_does_not_submit_agent_batch(self):
        def should_not_run(**kwargs):
            raise AssertionError("agent_batch should not run for capability catalogue questions")

        out = self._run_turn(message="你能做什么工具？", batch_loop_runner=should_not_run)

        self.assertEqual(out["agent_mode"], "conversation")
        self.assertEqual(out["loop_result"], {})
        capability_ids = [item["capability_id"] for item in out["capability_calls"]]
        self.assertIn("agent_runtime.capability.catalog", capability_ids)
        self.assertIn("agent_runtime.tool_pool.list", capability_ids)
        self.assertIn("agent_session.context.read", capability_ids)
        self.assertNotIn("agent_batch.nl_command.submit", capability_ids)
        self.assertTrue(
            all(item.get("protocol") == "read_only" for item in out["capability_calls"]),
            out["capability_calls"],
        )
        self.assertEqual(out["plan"]["strategy"], "read-only-fast-path")
        self.assertEqual(out["run_loop"]["contract_version"], "interactive_agent.run_loop.v1")
        self.assertIn("工具池", out["final_answer"])

    def test_model_planner_final_answer_is_used_for_read_only_turn(self):
        def should_not_run(**kwargs):
            raise AssertionError("agent_batch should not run for model-planned read-only answer")

        class FinalAnswerPlanner:
            def plan_next(self, *, context, available_tools, transcript, remaining_budget):
                return {
                    "model_path": "unit-model",
                    "tool_calls": [],
                    "final_answer": "这是模型基于当前上下文生成的自然回答。",
                    "stop": True,
                }

        out = self._run_turn(
            message="当前状态怎么样？",
            batch_loop_runner=should_not_run,
            run_loop_planner=FinalAnswerPlanner(),
        )

        self.assertEqual(out["agent_mode"], "conversation")
        self.assertTrue(out["final_answer"].startswith("这是模型基于当前上下文生成的自然回答。"))
        self.assertEqual(out["run_loop"]["model_path"], "unit-model")
        self.assertEqual(out["run_loop"]["model_final_answer"], "这是模型基于当前上下文生成的自然回答。")

    def test_source_library_discovery_uses_injected_lister_before_batch(self):
        seen: list[str | None] = []

        def lister(project_key):
            seen.append(project_key)
            return [
                {
                    "item_key": "demo.news",
                    "name": "Demo News",
                    "channel_key": "generic_web",
                    "enabled": True,
                    "item_type": "user_defined",
                }
            ]

        out = self._run_turn(message="继续补充来源库证据", source_library_lister=lister)

        self.assertEqual(seen, ["demo_proj"])
        source_call = next(item for item in out["capability_calls"] if item["capability_id"] == "source_library.item.list")
        self.assertEqual(source_call["status"], "completed")
        self.assertEqual(source_call["result"]["total"], 1)

    def test_source_library_fact_question_uses_read_only_fast_path(self):
        def should_not_run(**kwargs):
            raise AssertionError("agent_batch should not run for source-library fact questions")

        def lister(project_key):
            return [
                {
                    "item_key": "demo.news",
                    "name": "Demo News",
                    "channel_key": "generic_web",
                    "enabled": True,
                    "item_type": "user_defined",
                    "scope": "project",
                },
                {
                    "item_key": "shared.policy",
                    "name": "Shared Policy",
                    "channel_key": "policy_api",
                    "enabled": False,
                    "item_type": "managed",
                    "scope": "shared",
                },
            ]

        out = self._run_turn(
            message="当前项目有哪些来源库 item？",
            batch_loop_runner=should_not_run,
            source_library_lister=lister,
        )

        self.assertEqual(out["agent_mode"], "read_only")
        self.assertEqual(out["loop_result"], {})
        selected_ids = [item["capability_id"] for item in out["plan"]["selected_capabilities"]]
        self.assertIn("project.summary.read", selected_ids)
        self.assertIn("source_library.item.list", selected_ids)
        self.assertNotIn("agent_batch.nl_command.submit", selected_ids)
        source_call = next(item for item in out["capability_calls"] if item["capability_id"] == "source_library.item.list")
        self.assertEqual(source_call["protocol"], "read_only")
        self.assertEqual(source_call["result"]["total"], 2)
        self.assertIn("来源库", out["final_answer"])
        event_types = [item["event_type"] for item in out["events"]]
        self.assertIn("interactive_agent.model_delta", event_types)
        self.assertIn("interactive_agent.tool_call_requested", event_types)
        self.assertIn("interactive_agent.tool_call_started", event_types)
        self.assertIn("interactive_agent.tool_call_result", event_types)

    def test_project_summary_question_demotes_execute_hint_to_read_only_decision(self):
        def should_not_run(**kwargs):
            raise AssertionError("agent_batch should not run for project summary questions")

        out = self._run_turn(
            message="请总结当前项目进展",
            batch_loop_runner=should_not_run,
            require_high_risk_approval=True,
        )

        self.assertEqual(out["agent_mode"], "read_only")
        self.assertEqual(out["approval_requests"], [])
        selected_ids = [item["capability_id"] for item in out["plan"]["selected_capabilities"]]
        self.assertIn("project.summary.read", selected_ids)
        self.assertIn("project.structured_data.search", selected_ids)
        self.assertIn("agent_artifact.search", selected_ids)
        self.assertNotIn("source_library.item.list", selected_ids)
        self.assertNotIn("agent_batch.nl_command.submit", selected_ids)
        decision = out["plan"]["turn_decision"]
        self.assertEqual(decision["action"], "call_tools")
        self.assertEqual(decision["routing_hints"]["goal_class"], "execute")
        self.assertEqual(decision["routing_hints"]["role"], "hint_only_guardrails_not_primary_router")

    def test_existing_project_materials_do_not_route_to_source_library(self):
        def should_not_run(**kwargs):
            raise AssertionError("agent_batch should not run for existing material questions")

        out = self._run_turn(
            message="项目库里已有资料有哪些，帮我看一下",
            batch_loop_runner=should_not_run,
            require_high_risk_approval=True,
        )

        self.assertEqual(out["agent_mode"], "read_only")
        self.assertEqual(out["approval_requests"], [])
        selected_ids = [item["capability_id"] for item in out["plan"]["selected_capabilities"]]
        self.assertIn("project.context.bundle", selected_ids)
        self.assertIn("project.summary.read", selected_ids)
        self.assertIn("project.structured_data.search", selected_ids)
        self.assertIn("agent_artifact.search", selected_ids)
        self.assertNotIn("source_library.item.list", selected_ids)
        self.assertNotIn("ingest.source_library.run", selected_ids)
        bundle_call = next(item for item in out["capability_calls"] if item["capability_id"] == "project.context.bundle")
        self.assertEqual(bundle_call["result"]["material_intent"]["category"], "internal_existing")
        self.assertIn("internal_existing", bundle_call["result"]["material_categories"])
        self.assertEqual(bundle_call["material_category"]["category"], "internal_existing")

    def test_generic_material_supplement_routes_to_governed_collection(self):
        out = self._run_turn(
            message="帮我补充资料",
            require_high_risk_approval=True,
        )

        self.assertEqual(out["agent_mode"], "execute")
        self.assertTrue(out["approval_requests"])
        selected_ids = [item["capability_id"] for item in out["plan"]["selected_capabilities"]]
        self.assertIn("project.context.bundle", selected_ids)
        self.assertIn("project.summary.read", selected_ids)
        self.assertIn("project.structured_data.search", selected_ids)
        self.assertIn("agent_artifact.search", selected_ids)
        self.assertIn("source_library.item.list", selected_ids)
        self.assertIn("agent_batch.nl_command.submit", selected_ids)

    def test_writing_material_supplement_prefers_internal_context(self):
        def should_not_run(**kwargs):
            raise AssertionError("agent_batch should not run for writing material context preview")

        out = self._run_turn(
            message="写作时帮我补充资料",
            batch_loop_runner=should_not_run,
            require_high_risk_approval=True,
        )

        self.assertEqual(out["agent_mode"], "read_only")
        self.assertEqual(out["approval_requests"], [])
        selected_ids = [item["capability_id"] for item in out["plan"]["selected_capabilities"]]
        self.assertIn("project.context.bundle", selected_ids)
        self.assertIn("project.summary.read", selected_ids)
        self.assertIn("project.structured_data.search", selected_ids)
        self.assertIn("agent_artifact.search", selected_ids)
        self.assertNotIn("source_library.item.list", selected_ids)
        self.assertNotIn("agent_batch.nl_command.submit", selected_ids)

    def test_text_writing_existing_data_prefers_internal_context(self):
        def should_not_run(**kwargs):
            raise AssertionError("agent_batch should not run for existing writing data context")

        out = self._run_turn(
            message="这段正文需要补一些已有数据",
            batch_loop_runner=should_not_run,
            require_high_risk_approval=True,
        )

        self.assertEqual(out["agent_mode"], "read_only")
        self.assertEqual(out["approval_requests"], [])
        selected_ids = [item["capability_id"] for item in out["plan"]["selected_capabilities"]]
        self.assertIn("project.context.bundle", selected_ids)
        self.assertIn("project.structured_data.search", selected_ids)
        self.assertNotIn("source_library.item.list", selected_ids)
        self.assertNotIn("agent_batch.nl_command.submit", selected_ids)

    def test_text_writing_ingested_data_prefers_internal_context(self):
        def should_not_run(**kwargs):
            raise AssertionError("agent_batch should not run for already ingested writing material")

        out = self._run_turn(
            message="这段文字用已入库资料补一些事实",
            batch_loop_runner=should_not_run,
            require_high_risk_approval=True,
        )

        self.assertEqual(out["agent_mode"], "read_only")
        self.assertEqual(out["approval_requests"], [])
        selected_ids = [item["capability_id"] for item in out["plan"]["selected_capabilities"]]
        self.assertIn("project.context.bundle", selected_ids)
        self.assertIn("project.structured_data.search", selected_ids)
        self.assertNotIn("source_library.item.list", selected_ids)
        self.assertNotIn("agent_batch.nl_command.submit", selected_ids)

    def test_writing_external_material_supplement_can_expand_outward(self):
        out = self._run_turn(
            message="写作时帮我补充外部资料",
            require_high_risk_approval=True,
        )

        self.assertEqual(out["agent_mode"], "execute")
        self.assertTrue(out["approval_requests"])
        selected_ids = [item["capability_id"] for item in out["plan"]["selected_capabilities"]]
        self.assertIn("project.context.bundle", selected_ids)
        self.assertIn("project.summary.read", selected_ids)
        self.assertIn("project.structured_data.search", selected_ids)
        self.assertIn("source_library.item.list", selected_ids)
        self.assertIn("agent_batch.nl_command.submit", selected_ids)
        self.assertNotIn("ingest.source_library.run", selected_ids)

    def test_source_library_search_is_read_only_not_ingest_execution(self):
        def should_not_run(**kwargs):
            raise AssertionError("agent_batch should not run for source-library search")

        out = self._run_turn(
            message="搜索来源库里新能源相关条目",
            batch_loop_runner=should_not_run,
            require_high_risk_approval=True,
        )

        self.assertEqual(out["agent_mode"], "read_only")
        self.assertEqual(out["approval_requests"], [])
        capability_ids = [item["capability_id"] for item in out["capability_calls"]]
        self.assertIn("source_library.item.search", capability_ids)
        self.assertNotIn("ingest.source_library.run", capability_ids)
        self.assertNotIn("agent_batch.nl_command.submit", capability_ids)

    def test_turn_decision_planner_can_override_classifier_execute_path(self):
        def should_not_run(**kwargs):
            raise AssertionError("agent_batch should not run when model turn decision answers directly")

        case = self

        class DirectAnswerTurnPlanner:
            def decide(self, *, message, project_key, routing_hints, tool_pool):
                case.assertEqual(routing_hints["goal_class"], "execute")
                return {
                    "model_path": "unit-turn-model",
                    "action": "answer_direct",
                    "agent_mode": "conversation",
                    "confidence": 0.99,
                    "reason": "model chose to answer without tools",
                    "selected_capability_ids": [],
                    "direct_answer": "模型判断这只是一个可直接解释的问题。",
                }

        out = self._run_turn(
            message="分析 California gas price 的最新市场变化",
            batch_loop_runner=should_not_run,
            turn_decision_planner=DirectAnswerTurnPlanner(),
            require_high_risk_approval=True,
        )

        self.assertEqual(out["agent_mode"], "conversation")
        self.assertEqual(out["capability_calls"], [])
        self.assertEqual(out["approval_requests"], [])
        self.assertEqual(out["final_answer"], "模型判断这只是一个可直接解释的问题。")
        self.assertEqual(out["plan"]["turn_decision"]["model_path"], "unit-turn-model")

    def test_generic_free_chat_uses_model_answer_without_tools_or_batch(self):
        def should_not_run(**kwargs):
            raise AssertionError("agent_batch should not run for ordinary free conversation")

        class FakeConversationAnswerer:
            def answer(self, *, message, project_key, context_summary, turn_decision):
                return {
                    "answer": "CAPM 的核心是假设投资者按风险和收益权衡资产，系统性风险用 beta 表示。",
                    "source": "model",
                    "model_path": "unit-conversation-model",
                }

        out = self._run_turn(
            message="解释一下 CAPM 的核心假设",
            batch_loop_runner=should_not_run,
            conversation_answerer=FakeConversationAnswerer(),
        )

        self.assertEqual(out["agent_mode"], "conversation")
        self.assertEqual(out["capability_calls"], [])
        self.assertEqual(out["loop_result"], {})
        self.assertEqual(out["approval_requests"], [])
        self.assertIn("CAPM", out["final_answer"])
        self.assertIn("beta", out["final_answer"])
        decision = out["plan"]["turn_decision"]
        self.assertEqual(decision["action"], "answer_direct")
        self.assertEqual(decision["answer_source"], "model")
        self.assertTrue(decision["requires_model_answer"])
        self.assertEqual(decision["routing_hints"]["role"], "hint_only_guardrails_not_primary_router")

    def test_model_turn_decision_can_select_project_database_read_tools(self):
        def should_not_run(**kwargs):
            raise AssertionError("agent_batch should not run for model-selected project read tools")

        class ProjectDataModelPlanner:
            def decide(self, *, message, project_key, routing_hints, tool_pool):
                return {
                    "model_path": "unit-model-tool-router",
                    "action": "call_tools",
                    "agent_mode": "read_only",
                    "confidence": 0.94,
                    "reason": "project data question should query read-only project database tools",
                    "selected_capability_ids": [
                        "agent_session.context.read",
                        "project.summary.read",
                        "project.structured_data.search",
                        "agent_artifact.search",
                    ],
                }

        out = self._run_turn(
            message="项目里有什么数据",
            batch_loop_runner=should_not_run,
            turn_decision_planner=GuardedModelTurnDecisionPlanner(model_planner=ProjectDataModelPlanner()),
            require_high_risk_approval=True,
        )

        self.assertEqual(out["agent_mode"], "read_only")
        self.assertEqual(out["approval_requests"], [])
        capability_ids = [item["capability_id"] for item in out["capability_calls"]]
        self.assertIn("agent_session.context.read", capability_ids)
        self.assertIn("project.summary.read", capability_ids)
        self.assertIn("project.structured_data.search", capability_ids)
        self.assertIn("agent_artifact.search", capability_ids)
        self.assertNotIn("source_library.item.list", capability_ids)
        self.assertNotIn("agent_batch.nl_command.submit", capability_ids)
        self.assertEqual(out["plan"]["turn_decision"]["model_path"], "unit-model-tool-router")
        self.assertEqual(out["plan"]["turn_decision"]["action"], "call_tools")

    def test_project_data_question_falls_back_to_read_only_tools_when_model_router_fails(self):
        def should_not_run(**kwargs):
            raise AssertionError("agent_batch should not run for project read fallback")

        class FailingModelPlanner:
            def decide(self, *, message, project_key, routing_hints, tool_pool):
                raise subprocess.TimeoutExpired(cmd=["/Applications/Codex.app/Contents/Resources/codex", "exec"], timeout=8)

        out = self._run_turn(
            message="现在有哪些数据可以用",
            batch_loop_runner=should_not_run,
            turn_decision_planner=GuardedModelTurnDecisionPlanner(model_planner=FailingModelPlanner()),
            require_high_risk_approval=True,
        )

        self.assertEqual(out["agent_mode"], "read_only")
        capability_ids = [item["capability_id"] for item in out["capability_calls"]]
        self.assertIn("project.summary.read", capability_ids)
        self.assertIn("project.structured_data.search", capability_ids)
        self.assertIn("agent_artifact.search", capability_ids)
        self.assertNotIn("source_library.item.list", capability_ids)
        self.assertNotIn("agent_batch.nl_command.submit", capability_ids)
        decision = out["plan"]["turn_decision"]
        self.assertEqual(decision["model_path"], "guarded_fast_after_model_error")
        self.assertIn("model routing failed", decision["reason"])
        self.assertNotIn("/Applications/Codex.app", str(decision.get("model_error")))

    def test_workflow_graph_fact_question_uses_read_only_tools_before_execution(self):
        def should_not_run(**kwargs):
            raise AssertionError("agent_batch should not run for workflow graph fact questions")

        compiler = WorkflowGraphCompilerService(store=InMemoryCompiledGraphStore())
        compiler.compile(
            {
                "graph_id": "demo_graph_agent_tool",
                "version": "1",
                "nodes": [{"node_id": "n1", "node_type": "llm_call", "config": {"prompt": "hello"}}],
                "edges": [],
            }
        )

        with patch("app.services.workflow_graph.compiler", compiler):
            out = self._run_turn(
                message="检查 workflow graph demo_graph_agent_tool 的节点和输入",
                batch_loop_runner=should_not_run,
            )

        self.assertEqual(out["agent_mode"], "read_only")
        capability_ids = [item["capability_id"] for item in out["capability_calls"]]
        self.assertIn("workflow_graph.list", capability_ids)
        self.assertIn("workflow_graph.inspect", capability_ids)
        self.assertNotIn("agent_batch.nl_command.submit", capability_ids)
        inspect_call = next(item for item in out["capability_calls"] if item["capability_id"] == "workflow_graph.inspect")
        self.assertEqual(inspect_call["status"], "completed")
        self.assertEqual(inspect_call["result"]["graph"]["graph_id"], "demo_graph_agent_tool")

    def test_high_risk_capability_can_request_approval_without_batch_dispatch(self):
        def should_not_run(**kwargs):
            raise AssertionError("agent_batch should not run while high-risk approval is required")

        out = self._run_turn(
            message="运行 workflow graph demo_graph",
            batch_loop_runner=should_not_run,
            require_high_risk_approval=True,
        )

        self.assertEqual(out["loop_result"], {})
        workflow_call = next(item for item in out["capability_calls"] if item["capability_id"] == "workflow_graph.run")
        self.assertEqual(workflow_call["status"], "needs_approval")
        self.assertTrue(workflow_call["approval_id"])
        self.assertEqual(len(out["approval_requests"]), 1)
        self.assertEqual(out["approval_requests"][0]["status"], "pending")
        self.assertEqual(out["session"]["status"], "blocked")
        event_types = [item["event_type"] for item in out["events"]]
        self.assertIn("approval.requested", event_types)
        self.assertIn("approval.waiting", event_types)

    def test_agent_batch_fallback_is_approval_gated_when_no_specific_executor_matches(self):
        def should_not_run(**kwargs):
            raise AssertionError("agent_batch fallback must wait for approval")

        out = self._run_turn(
            message="分析 California gas price 的最新市场变化",
            batch_loop_runner=should_not_run,
            require_high_risk_approval=True,
        )

        self.assertEqual(out["loop_result"], {})
        fallback_call = next(item for item in out["capability_calls"] if item["capability_id"] == "agent_batch.nl_command.submit")
        self.assertEqual(fallback_call["status"], "needs_approval")
        self.assertEqual(len(out["approval_requests"]), 1)
        approval = out["approval_requests"][0]
        self.assertEqual(approval["binding_payload"]["capability_id"], "agent_batch.nl_command.submit")
        execution_payload = approval["binding_payload"]["execution_payload"]
        self.assertEqual(execution_payload["command"], "分析 California gas price 的最新市场变化")
        self.assertEqual(execution_payload["approval_level"], "medium")
        self.assertEqual(out["session"]["status"], "blocked")

        approval_id = approval["approval_id"]

        def fake_executor(**kwargs):
            self.assertEqual(kwargs["capability_id"], "agent_batch.nl_command.submit")
            self.assertEqual(kwargs["binding_payload"]["execution_payload"]["command"], "分析 California gas price 的最新市场变化")
            return build_capability_call(
                turn_id=kwargs["turn_id"],
                capability_id=kwargs["capability_id"],
                protocol="approval_gated",
                status="completed",
                summary="fake agent_batch fallback executed",
                result={"loop_id": "loop-approved", "submit": {"job_id": "abj-approved"}},
                extra={"approval_id": approval_id, "job_id": "abj-approved"},
            )

        continued = self.runtime.continue_approved_capability(
            approval_id=approval_id,
            approved_by="unit-test",
            high_risk_executor=fake_executor,
        )

        self.assertTrue(continued["continued"])
        self.assertEqual(continued["capability_call"]["status"], "completed")
        self.assertEqual(continued["capability_call"]["job_id"], "abj-approved")

    def test_approved_high_risk_capability_can_continue_same_session(self):
        def should_not_run(**kwargs):
            raise AssertionError("agent_batch should not run while high-risk approval is required")

        out = self._run_turn(
            message="运行 workflow graph demo_graph",
            batch_loop_runner=should_not_run,
            require_high_risk_approval=True,
        )
        approval_id = out["approval_requests"][0]["approval_id"]

        def fake_executor(**kwargs):
            self.assertEqual(kwargs["binding_payload"]["graph_id"], "demo_graph_override")
            self.assertEqual(kwargs["binding_payload"]["inputs"], {"x": 1})
            return build_capability_call(
                turn_id=kwargs["turn_id"],
                capability_id=kwargs["capability_id"],
                protocol="approval_gated",
                status="completed",
                summary="fake workflow graph executed",
                result={"run_id": "wgr-test", "status": "completed"},
                extra={"approval_id": approval_id, "run_id": "wgr-test"},
            )

        continued = self.runtime.continue_approved_capability(
            approval_id=approval_id,
            approved_by="unit-test",
            binding_payload_overrides={"graph_id": "demo_graph_override", "inputs": {"x": 1}},
            high_risk_executor=fake_executor,
        )

        self.assertTrue(continued["continued"])
        self.assertEqual(continued["approval"]["status"], "approved")
        self.assertEqual(continued["session"]["session_id"], out["session"]["session_id"])
        self.assertEqual(continued["session"]["status"], "completed")
        self.assertEqual(continued["capability_call"]["status"], "completed")
        self.assertEqual(continued["capability_call"]["run_id"], "wgr-test")
        event_types = [item["event_type"] for item in continued["events"]]
        self.assertIn("approval.binding_overridden", event_types)
        self.assertIn("approval.approved", event_types)
        self.assertIn("interactive_agent.tool_call_started", event_types)
        self.assertIn("interactive_agent.tool_call_result", event_types)
        self.assertIn("interactive_agent.approval_continued", event_types)
        self.assertIn("interactive_agent.final_answer", event_types)

    def test_report_generate_requests_approval_and_continues_to_markdown_artifact(self):
        def should_not_run(**kwargs):
            raise AssertionError("agent_batch should not run while report.generate approval is required")

        out = self._run_turn(
            message="基于已有产物生成报告草稿 output_path=reports/demo.md",
            batch_loop_runner=should_not_run,
            require_high_risk_approval=True,
        )

        capability_ids = [item["capability_id"] for item in out["capability_calls"]]
        self.assertIn("agent_artifact.search", capability_ids)
        self.assertIn("report.generate", capability_ids)
        report_call = next(item for item in out["capability_calls"] if item["capability_id"] == "report.generate")
        self.assertEqual(report_call["status"], "needs_approval")
        approval_id = out["approval_requests"][0]["approval_id"]

        continued = self.runtime.continue_approved_capability(
            approval_id=approval_id,
            approved_by="unit-test",
            binding_payload_overrides={
                "sources": [
                    {
                        "id": "S1",
                        "title": "Demo source",
                        "url": "https://example.com/demo",
                        "publisher": "example",
                        "evidence": "demo evidence",
                    }
                ]
            },
        )

        self.assertTrue(continued["continued"])
        self.assertEqual(continued["capability_call"]["status"], "completed")
        self.assertEqual(continued["capability_call"]["capability_id"], "report.generate")
        artifacts = [item for item in continued["artifacts"] if item.get("name") == "reports/demo.md"]
        self.assertEqual(len(artifacts), 1)
        self.assertEqual(artifacts[0]["artifact_type"], "report.generate.markdown")
        self.assertIn("# 研究报告", artifacts[0]["content_text"])


if __name__ == "__main__":
    unittest.main()
