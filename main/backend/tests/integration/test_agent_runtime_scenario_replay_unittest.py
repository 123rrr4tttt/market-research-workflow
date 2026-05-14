from __future__ import annotations

import unittest
from unittest.mock import patch

import pytest

from app.services.agent_runtime.interactive_agent import InteractiveAgentRuntime
from app.services.agent_runtime.tool_contract import build_capability_call
from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_sessions.store import InMemoryAgentSessionStore
from app.services.workflow_graph import WorkflowGraphCompilerService
from app.services.workflow_graph.store import InMemoryCompiledGraphStore

pytestmark = pytest.mark.integration


def _reject_batch_runner(**kwargs):
    raise AssertionError("scenario replay should not dispatch agent_batch for this user path")


class AgentRuntimeScenarioReplayTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = AgentSessionService(store=InMemoryAgentSessionStore())
        self.runtime = InteractiveAgentRuntime(service=self.service)

    def _run_turn(self, **overrides):
        return self.runtime.run_turn(
            message=overrides.pop("message"),
            project_key=overrides.pop("project_key", "demo_proj"),
            batch_loop_runner=overrides.pop("batch_loop_runner", _reject_batch_runner),
            parser_fallback=lambda command: {"command": command},
            submitter=lambda tasks, project_key, idem: {"job_id": "unused"},
            executor_snapshot=lambda: {"status": "ok"},
            **overrides,
        )

    def test_s01_capability_question_stays_fast_and_read_only(self):
        out = self._run_turn(message="你能做什么工具？")

        self.assertEqual(out["agent_mode"], "conversation")
        capability_ids = [item["capability_id"] for item in out["capability_calls"]]
        self.assertIn("agent_runtime.capability.catalog", capability_ids)
        self.assertIn("agent_session.context.read", capability_ids)
        self.assertNotIn("agent_batch.nl_command.submit", capability_ids)
        self.assertIn("没有提交项目执行 job", out["final_answer"])
        self.assertIn("当前 agent 暴露", out["final_answer"])

    def test_s01b_greeting_returns_general_answer_without_batch_or_approval(self):
        out = self._run_turn(message="你好", require_high_risk_approval=True)

        self.assertEqual(out["agent_mode"], "conversation")
        capability_ids = [item["capability_id"] for item in out["capability_calls"]]
        self.assertNotIn("agent_batch.nl_command.submit", capability_ids)
        self.assertEqual(out["approval_requests"], [])
        self.assertEqual(out["suggested_next_actions"], [])
        self.assertIn("普通对话回答问题", out["final_answer"])
        self.assertNotIn("审批请求", out["final_answer"])

    def test_s01c_general_questions_do_not_enter_batch_or_approval(self):
        messages = [
            "你是谁",
            "这个系统现在能干什么",
            "这个项目有什么数据",
            "请总结当前项目进展",
            "搜索来源库里新能源相关条目",
        ]
        for message in messages:
            with self.subTest(message=message):
                out = self._run_turn(message=message, require_high_risk_approval=True)
                capability_ids = [item["capability_id"] for item in out["capability_calls"]]
                self.assertIn(out["agent_mode"], {"conversation", "read_only"})
                self.assertEqual(out["approval_requests"], [])
                self.assertNotIn("agent_batch.nl_command.submit", capability_ids)
                self.assertNotIn("ingest.source_library.run", capability_ids)
                self.assertIn(out["plan"]["turn_decision"]["action"], {"answer_direct", "call_tools"})

    def test_s02_project_source_library_fact_question_uses_read_only_tools(self):
        def lister(project_key):
            self.assertEqual(project_key, "demo_proj")
            return [
                {
                    "item_key": "demo.news",
                    "name": "Demo News",
                    "channel_key": "generic_web",
                    "enabled": True,
                    "item_type": "user_defined",
                    "scope": "project",
                }
            ]

        out = self._run_turn(message="当前项目有哪些来源库 item？", source_library_lister=lister)

        self.assertEqual(out["agent_mode"], "read_only")
        capability_ids = [item["capability_id"] for item in out["capability_calls"]]
        self.assertIn("project.summary.read", capability_ids)
        self.assertIn("source_library.item.list", capability_ids)
        self.assertNotIn("agent_batch.nl_command.submit", capability_ids)
        source_call = next(item for item in out["capability_calls"] if item["capability_id"] == "source_library.item.list")
        self.assertEqual(source_call["status"], "completed")
        self.assertEqual(source_call["result"]["total"], 1)
        self.assertIn("来源库匹配 total=1", out["final_answer"])

    def test_s03_source_library_collection_lists_candidates_waits_for_confirmation_and_continues(self):
        def lister(project_key):
            self.assertEqual(project_key, "demo_proj")
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
                    "item_key": "demo.filings",
                    "name": "Demo Filings",
                    "channel_key": "handler_cluster",
                    "enabled": True,
                    "item_type": "user_defined",
                    "scope": "project",
                },
            ]

        out = self._run_turn(
            message="用来源库 demo.news 补一轮证据",
            source_library_lister=lister,
            require_high_risk_approval=True,
        )

        self.assertEqual(out["agent_mode"], "execute")
        capability_ids = [item["capability_id"] for item in out["capability_calls"]]
        self.assertIn("source_library.item.list", capability_ids)
        self.assertIn("ingest.status.read", capability_ids)
        self.assertIn("ingest.source_library.run", capability_ids)
        self.assertNotIn("agent_batch.nl_command.submit", capability_ids)
        collection_call = next(item for item in out["capability_calls"] if item["capability_id"] == "ingest.source_library.run")
        self.assertEqual(collection_call["status"], "needs_approval")
        approval = out["approval_requests"][0]
        binding = approval["binding_payload"]
        preview = binding["preview_payload"]
        self.assertTrue(preview["requires_confirmation"])
        self.assertEqual(preview["scope_summary"]["candidate_count"], 2)
        self.assertEqual(preview["scope_summary"]["selected_item_key"], "demo.news")
        self.assertEqual(binding["execution_payload"]["item_key"], "demo.news")
        event_types = [item["event_type"] for item in out["events"]]
        self.assertLess(event_types.index("interactive_agent.approval_preview"), event_types.index("approval.requested"))
        self.assertIn("interactive_agent.execution_payload_snapshotted", event_types)

        approval_id = approval["approval_id"]

        def fake_executor(**kwargs):
            self.assertEqual(kwargs["binding_payload"]["item_key"], "demo.news")
            self.assertEqual(kwargs["binding_payload"]["execution_payload"]["item_key"], "demo.news")
            return build_capability_call(
                turn_id=kwargs["turn_id"],
                capability_id=kwargs["capability_id"],
                protocol="approval_gated",
                status="completed",
                summary="scenario source-library evidence collected",
                result={"item_key": "demo.news", "run_identifier": "sl-run-s03", "status": "completed"},
                extra={"approval_id": approval_id, "run_identifier": "sl-run-s03"},
            )

        continued = self.runtime.continue_approved_capability(
            approval_id=approval_id,
            approved_by="scenario-test",
            high_risk_executor=fake_executor,
        )

        self.assertTrue(continued["continued"])
        self.assertEqual(continued["capability_call"]["status"], "completed")
        self.assertEqual(continued["capability_call"]["run_identifier"], "sl-run-s03")
        self.assertIn("审批已处理", continued["final_answer"])

    def test_s04_ingest_chain_uses_scoped_execution_payload_and_resume_context(self):
        def lister(project_key):
            self.assertEqual(project_key, "demo_proj")
            return [
                {
                    "item_key": "demo.ingest",
                    "name": "Demo Ingest",
                    "channel_key": "generic_web",
                    "enabled": True,
                    "item_type": "user_defined",
                    "scope": "project",
                }
            ]

        out = self._run_turn(
            message="ingest demo.ingest time_window=2026-05-01..2026-05-10 max_items=5",
            source_library_lister=lister,
            require_high_risk_approval=True,
        )

        approval = out["approval_requests"][0]
        binding = approval["binding_payload"]
        execution_payload = binding["execution_payload"]
        self.assertEqual(execution_payload["item_key"], "demo.ingest")
        self.assertEqual(execution_payload["time_window"], "2026-05-01..2026-05-10")
        self.assertEqual(execution_payload["max_items"], 5)
        self.assertEqual(execution_payload["budget"]["max_items"], 5)
        self.assertEqual(binding["resume_context"]["replay_capability_id"], "ingest.source_library.run")
        self.assertIn("ingest.status.read", [item["capability_id"] for item in out["capability_calls"]])
        snapshot_event = next(
            item for item in out["events"] if item["event_type"] == "interactive_agent.execution_payload_snapshotted"
        )
        self.assertEqual(snapshot_event["payload"]["execution_payload"]["item_key"], "demo.ingest")

        approval_id = approval["approval_id"]

        def fake_executor(**kwargs):
            payload = kwargs["binding_payload"]["execution_payload"]
            self.assertEqual(payload["override_params"], {"time_window": "2026-05-01..2026-05-10", "max_items": 5})
            return build_capability_call(
                turn_id=kwargs["turn_id"],
                capability_id=kwargs["capability_id"],
                protocol="approval_gated",
                status="completed",
                summary="scenario ingest chain completed",
                result={"run_identifier": "ingest-run-s04", "status": "completed"},
                extra={
                    "approval_id": approval_id,
                    "run_identifier": "ingest-run-s04",
                    "resume_context": kwargs["binding_payload"]["resume_context"],
                },
            )

        continued = self.runtime.continue_approved_capability(
            approval_id=approval_id,
            approved_by="scenario-test",
            high_risk_executor=fake_executor,
        )

        self.assertEqual(continued["session"]["status"], "completed")
        self.assertEqual(continued["capability_call"]["run_identifier"], "ingest-run-s04")
        self.assertEqual(continued["capability_call"]["resume_context"]["replay_capability_id"], "ingest.source_library.run")

    def test_s05_workflow_execution_inspects_then_waits_for_editable_approval_and_continues(self):
        compiler = WorkflowGraphCompilerService(store=InMemoryCompiledGraphStore())
        compiler.compile(
            {
                "graph_id": "demo_graph_agent_scenario",
                "version": "1",
                "nodes": [{"node_id": "n1", "node_type": "llm_call", "config": {"prompt": "ok"}}],
                "edges": [],
            }
        )

        with patch("app.services.workflow_graph.compiler", compiler):
            out = self._run_turn(
                message="运行 workflow graph demo_graph_agent_scenario",
                require_high_risk_approval=True,
            )

        capability_ids = [item["capability_id"] for item in out["capability_calls"]]
        self.assertIn("workflow_graph.inspect", capability_ids)
        inspect_call = next(item for item in out["capability_calls"] if item["capability_id"] == "workflow_graph.inspect")
        self.assertEqual(inspect_call["status"], "completed")
        workflow_call = next(item for item in out["capability_calls"] if item["capability_id"] == "workflow_graph.run")
        self.assertEqual(workflow_call["status"], "needs_approval")
        self.assertEqual(out["session"]["status"], "blocked")
        approval_id = out["approval_requests"][0]["approval_id"]

        def fake_executor(**kwargs):
            self.assertEqual(kwargs["binding_payload"]["inputs"], {"smoke": True})
            return build_capability_call(
                turn_id=kwargs["turn_id"],
                capability_id=kwargs["capability_id"],
                protocol="approval_gated",
                status="completed",
                summary="scenario workflow graph executed",
                result={"run_id": "wgr-scenario", "status": "completed"},
                extra={"approval_id": approval_id, "run_id": "wgr-scenario"},
            )

        continued = self.runtime.continue_approved_capability(
            approval_id=approval_id,
            approved_by="scenario-test",
            binding_payload_overrides={"inputs": {"smoke": True}},
            high_risk_executor=fake_executor,
        )

        self.assertTrue(continued["continued"])
        self.assertEqual(continued["session"]["status"], "completed")
        self.assertEqual(continued["capability_call"]["status"], "completed")
        self.assertIn("审批已处理", continued["final_answer"])
        event_types = [item["event_type"] for item in continued["events"]]
        self.assertIn("approval.binding_overridden", event_types)
        self.assertIn("interactive_agent.approval_continued", event_types)

    def test_s07_cancel_then_continue_preserves_recoverable_session_state(self):
        def lister(project_key):
            self.assertEqual(project_key, "demo_proj")
            return [
                {
                    "item_key": "demo.news",
                    "name": "Demo News",
                    "channel_key": "generic_web",
                    "enabled": True,
                    "item_type": "user_defined",
                    "scope": "project",
                }
            ]

        out = self._run_turn(
            message="用来源库 demo.news 补一轮证据",
            source_library_lister=lister,
            require_high_risk_approval=True,
        )
        session_id = out["session"]["session_id"]
        self.assertEqual(out["session"]["status"], "blocked")

        canceled = self._run_turn(message="取消当前会话", session_id=session_id)
        self.assertEqual(canceled["session"]["status"], "canceled")
        cancel_call = next(item for item in canceled["capability_calls"] if item["capability_id"] == "task.cancel")
        self.assertEqual(cancel_call["status"], "completed")

        continued = self._run_turn(message="继续", session_id=session_id)
        continue_call = next(item for item in continued["capability_calls"] if item["capability_id"] == "task.continue")
        self.assertEqual(continue_call["status"], "completed")
        self.assertIn(continued["session"]["status"], {"blocked", "pending", "active", "completed"})
        self.assertNotEqual(continued["session"]["status"], "canceled")
        event_types = [item["event_type"] for item in continued["events"]]
        self.assertIn("task.continue_resumed_canceled", event_types)
        self.assertTrue(
            any(
                item.get("action") == "wait_for_approval"
                for item in list(continue_call["result"]["coordinator"].get("decisions") or [])
            )
        )

    def test_s06_missing_workflow_graph_failure_is_returned_as_tool_result(self):
        compiler = WorkflowGraphCompilerService(store=InMemoryCompiledGraphStore())

        with patch("app.services.workflow_graph.compiler", compiler):
            out = self._run_turn(message="检查 workflow graph missing_graph_404 的节点和输入")

        self.assertEqual(out["agent_mode"], "read_only")
        inspect_call = next(item for item in out["capability_calls"] if item["capability_id"] == "workflow_graph.inspect")
        self.assertEqual(inspect_call["status"], "failed")
        self.assertEqual(inspect_call["result"]["graph_id"], "missing_graph_404")
        self.assertIn("Workflow graph missing_graph_404 inspect failed", out["final_answer"])
        event_types = [item["event_type"] for item in out["events"]]
        self.assertIn("interactive_agent.tool_call_result", event_types)

        follow_up = self._run_turn(
            message="刚才那个结果里第二项为什么失败？",
            session_id=out["session"]["session_id"],
        )
        self.assertIn(follow_up["agent_mode"], {"conversation", "read_only"})
        context_call = next(
            item for item in follow_up["capability_calls"] if item["capability_id"] == "agent_session.context.read"
        )
        recent_tool_results = list(context_call["result"].get("recent_tool_results") or [])
        self.assertTrue(any(item.get("capability_id") == "workflow_graph.inspect" for item in recent_tool_results))
        self.assertIn("missing_graph_404", follow_up["final_answer"])


if __name__ == "__main__":
    unittest.main()
