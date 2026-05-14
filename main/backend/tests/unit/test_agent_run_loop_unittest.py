from __future__ import annotations

import unittest
from unittest.mock import patch

import pytest

from app.services.agent_runtime.read_only_tools import ReadOnlyAgentToolRuntime
from app.services.agent_runtime.run_loop import AgentRunLoop, AgentRunLoopBudget, AgentRunLoopContext, JsonModelAgentRunLoopPlanner
from app.services.agent_runtime.tool_contract import ToolCallOptions, ToolExecutionContext
from app.services.agent_runtime.tool_execution import ToolExecutionHooks, ToolExecutionPolicy
from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_sessions.store import InMemoryAgentSessionStore
from app.services.workflow_graph import WorkflowGraphCompilerService
from app.services.workflow_graph.store import InMemoryCompiledGraphStore

pytestmark = pytest.mark.unit


class AgentRunLoopUnitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = self.service.create_session(
            source="user",
            entrypoint_type="interactive_agent",
            goal="当前项目有哪些来源库 item？",
            project_key="demo_proj",
            task_blueprints=[],
        )
        self.session_id = bundle["session"]["session_id"]

    def _tool_runtime(self) -> ReadOnlyAgentToolRuntime:
        def lister(project_key):
            return [
                {
                    "item_key": "demo.news",
                    "name": "Demo News",
                    "channel_key": "generic_web",
                    "enabled": True,
                    "item_type": "user_defined",
                }
            ]

        def structured_searcher(**kwargs):
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

        return ReadOnlyAgentToolRuntime(
            service=self.service,
            source_library_lister=lister,
            structured_data_searcher=structured_searcher,
        )

    def _context(self, *capability_ids: str) -> AgentRunLoopContext:
        return AgentRunLoopContext(
            turn_id="turn-test",
            session_id=self.session_id,
            project_key="demo_proj",
            message="当前项目有哪些来源库 item？",
            selected_capability_ids=tuple(capability_ids),
            agent_mode="read_only",
        )

    def test_run_loop_executes_read_only_tools_and_emits_tool_events(self):
        emitted: list[dict] = []
        loop = AgentRunLoop(tool_runtime=self._tool_runtime(), event_sink=emitted.append)

        out = loop.run(self._context("agent_session.context.read", "source_library.item.list"))

        self.assertEqual(out["contract_version"], "interactive_agent.run_loop.v1")
        self.assertEqual(out["stop_reason"], "final_answer")
        self.assertEqual(out["tool_call_count"], 2)
        self.assertIn("当前项目的来源库", out["model_final_answer"])
        self.assertNotIn("已根据工具结果完成回答准备", out["model_final_answer"])
        call_ids = [item["capability_id"] for item in out["capability_calls"]]
        self.assertEqual(call_ids, ["agent_session.context.read", "source_library.item.list"])
        event_types = [item["event_type"] for item in emitted]
        self.assertIn("interactive_agent.model_delta", event_types)
        self.assertIn("interactive_agent.tool_call_requested", event_types)
        self.assertIn("interactive_agent.tool_call_started", event_types)
        self.assertIn("interactive_agent.tool_call_result", event_types)

    def test_run_loop_stops_when_tool_budget_is_exhausted(self):
        loop = AgentRunLoop(
            tool_runtime=self._tool_runtime(),
            budget=AgentRunLoopBudget(max_tool_calls=1),
        )

        out = loop.run(self._context("agent_session.context.read", "source_library.item.list"))

        self.assertEqual(out["stop_reason"], "max_tool_calls_exceeded")
        self.assertEqual(out["tool_call_count"], 1)
        self.assertEqual(len(out["capability_calls"]), 1)

    def test_json_model_planner_can_drive_tool_selection(self):
        class FakeChatModel:
            def __init__(self):
                self.calls = 0

            def invoke(self, prompt):
                self.calls += 1
                if self.calls > 1:
                    return {"content": '{"tool_calls":[],"final_answer":"来源库已有 1 个 item。","stop":true}'}
                return {
                    "content": (
                        '{"tool_calls":[{"tool_name":"source_library.item.list",'
                        '"input":{"limit":1},"reason":"answer source-library question"}],'
                        '"final_answer":null,"stop":true}'
                    )
                }

        loop = AgentRunLoop(
            tool_runtime=self._tool_runtime(),
            planner=JsonModelAgentRunLoopPlanner(chat_model=FakeChatModel()),
        )

        out = loop.run(self._context("agent_session.context.read"))

        self.assertEqual(out["tool_call_count"], 1)
        self.assertEqual(out["capability_calls"][0]["capability_id"], "source_library.item.list")
        self.assertEqual(out["stop_reason"], "final_answer")
        self.assertEqual(out["model_final_answer"], "来源库已有 1 个 item。")
        planner_events = [
            item["payload"]
            for item in out["events"]
            if item["event_type"] == "interactive_agent.model_delta"
            and item["payload"].get("delta") == "planner decision ready"
        ]
        self.assertEqual(planner_events[-1]["model_path"], "json_model")
        self.assertEqual(out["model_path"], "json_model")
        self.assertIn("elapsed_seconds", out["metrics"])
        self.assertEqual(out["metrics"]["tool_count"], 1)
        self.assertEqual(out["iterations"], 2)

    def test_run_loop_can_search_project_structured_data(self):
        loop = AgentRunLoop(tool_runtime=self._tool_runtime())

        out = loop.run(
            AgentRunLoopContext(
                turn_id="turn-structured",
                session_id=self.session_id,
                project_key="demo_proj",
                message="项目里有什么数据",
                selected_capability_ids=("project.structured_data.search",),
                agent_mode="read_only",
            )
        )

        self.assertEqual(out["tool_call_count"], 1)
        call = out["capability_calls"][0]
        self.assertEqual(call["capability_id"], "project.structured_data.search")
        self.assertEqual(call["status"], "completed")
        self.assertEqual(call["result"]["query_mode"], "inventory")
        self.assertEqual(call["result"]["items"][0]["title"], "Demo document")
        self.assertIn("结构化数据", out["model_final_answer"])

    def test_json_model_planner_final_answer_is_preserved_when_no_tool_is_needed(self):
        class FakeChatModel:
            def invoke(self, prompt):
                return {"content": '{"tool_calls":[],"final_answer":"可以直接回答。","stop":true}'}

        loop = AgentRunLoop(
            tool_runtime=self._tool_runtime(),
            planner=JsonModelAgentRunLoopPlanner(chat_model=FakeChatModel()),
        )

        out = loop.run(self._context("agent_session.context.read"))

        self.assertEqual(out["tool_call_count"], 0)
        self.assertEqual(out["stop_reason"], "final_answer")
        self.assertEqual(out["model_final_answer"], "可以直接回答。")
        self.assertEqual(out["metrics"]["tool_count"], 0)

    def test_tool_execution_context_serializes_options_for_model_planning(self):
        context = ToolExecutionContext(
            session_id=self.session_id,
            task_id="task-1",
            turn_id="turn-1",
            project_key="demo_proj",
            user="unit-test",
            budget={"max_tool_calls": 4},
            permissions=("read:project",),
            feature_flags={"agent_runtime_v2_enabled": True},
            options=ToolCallOptions(
                dry_run=True,
                explain_only=True,
                approval_required=True,
                resume_token="resume-token",
            ),
            abort_signal=object(),
        )

        model_context = context.to_model_context()

        self.assertEqual(model_context["session_id"], self.session_id)
        self.assertEqual(model_context["project_key"], "demo_proj")
        self.assertEqual(model_context["budget"], {"max_tool_calls": 4})
        self.assertEqual(model_context["permissions"], ["read:project"])
        self.assertTrue(model_context["abortable"])
        self.assertEqual(
            model_context["options"],
            {
                "dry_run": True,
                "explain_only": True,
                "approval_required": True,
                "resume_token": "resume-token",
            },
        )

    def test_run_loop_can_list_and_search_dynamic_tool_pool(self):
        loop = AgentRunLoop(tool_runtime=self._tool_runtime())

        out = loop.run(
            AgentRunLoopContext(
                turn_id="turn-tools",
                session_id=self.session_id,
                project_key="demo_proj",
                message="搜索 workflow 工具",
                selected_capability_ids=("agent_runtime.tool_pool.list", "agent_runtime.tool.search"),
                agent_mode="read_only",
            )
        )

        capability_ids = [item["capability_id"] for item in out["capability_calls"]]
        self.assertEqual(capability_ids, ["agent_runtime.tool_pool.list", "agent_runtime.tool.search"])
        pool_call = out["capability_calls"][0]
        self.assertEqual(pool_call["status"], "completed")
        self.assertGreaterEqual(pool_call["result"]["counts"]["core"], 1)
        search_call = out["capability_calls"][1]
        self.assertEqual(search_call["status"], "completed")
        matched_ids = {item["capability_id"] for item in search_call["result"]["items"]}
        self.assertIn("workflow_graph.run", matched_ids)
        self.assertTrue(
            any(item["capability_id"] == "workflow_graph.run" and item["deferred"] for item in search_call["result"]["items"])
        )

    def test_run_loop_emits_tool_hooks_and_parallel_read_only_plan(self):
        hook_events: list[tuple[str, str]] = []
        hooks = ToolExecutionHooks(
            pre_tool=(lambda payload: hook_events.append(("pre", payload["tool_name"])),),
            post_tool=(lambda payload: hook_events.append(("post", payload["tool_name"])),),
        )
        loop = AgentRunLoop(tool_runtime=self._tool_runtime(), hooks=hooks)

        out = loop.run(self._context("agent_session.context.read", "source_library.item.list"))

        self.assertEqual(out["tool_call_count"], 2)
        self.assertIn("agent_session.context.read", out["concurrency_plan"]["read_only_parallelizable"])
        self.assertIn("source_library.item.list", out["concurrency_plan"]["read_only_parallelizable"])
        self.assertEqual({item for kind, item in hook_events if kind == "pre"}, {"agent_session.context.read", "source_library.item.list"})
        self.assertEqual({item for kind, item in hook_events if kind == "post"}, {"agent_session.context.read", "source_library.item.list"})

    def test_run_loop_returns_canceled_tool_result_when_abort_signal_is_set(self):
        hook_events: list[str] = []
        hooks = ToolExecutionHooks(on_cancel=(lambda payload: hook_events.append(payload["call"]["capability_id"]),))
        loop = AgentRunLoop(tool_runtime=self._tool_runtime(), hooks=hooks)

        out = loop.run(
            AgentRunLoopContext(
                turn_id="turn-cancel",
                session_id=self.session_id,
                project_key="demo_proj",
                message="当前项目有哪些来源库 item？",
                selected_capability_ids=("agent_session.context.read",),
                agent_mode="read_only",
                abort_signal=lambda: True,
            )
        )

        self.assertEqual(out["stop_reason"], "user_canceled")
        self.assertEqual(out["tool_call_count"], 1)
        self.assertEqual(out["capability_calls"][0]["status"], "canceled")
        self.assertEqual(out["capability_calls"][0]["result"], {"canceled": True, "recoverable": True})
        self.assertEqual(hook_events, ["agent_session.context.read"])

    def test_tool_execution_policy_requires_approval_for_external_or_high_risk_tools(self):
        policy = ToolExecutionPolicy()

        self.assertTrue(policy.requires_approval({"approval_level": "high", "concurrency_class": "read_only"}))
        self.assertTrue(policy.requires_approval({"approval_level": "none", "concurrency_class": "write_external"}))
        self.assertFalse(policy.requires_approval({"approval_level": "none", "concurrency_class": "read_only"}))

    def test_run_loop_can_read_workflow_graph_inventory_and_inspect_graph(self):
        compiler = WorkflowGraphCompilerService(store=InMemoryCompiledGraphStore())
        compiler.compile(
            {
                "graph_id": "demo_graph_agent_tool",
                "version": "1",
                "nodes": [
                    {"node_id": "n1", "node_type": "llm_call", "config": {"prompt": "hello"}},
                ],
                "edges": [],
            }
        )
        loop = AgentRunLoop(tool_runtime=self._tool_runtime())

        with patch("app.services.workflow_graph.compiler", compiler):
            out = loop.run(
                AgentRunLoopContext(
                    turn_id="turn-workflow",
                    session_id=self.session_id,
                    project_key="demo_proj",
                    message="检查 workflow graph demo_graph_agent_tool 的节点和输入",
                    selected_capability_ids=("workflow_graph.list", "workflow_graph.inspect"),
                    agent_mode="read_only",
                )
            )

        capability_ids = [item["capability_id"] for item in out["capability_calls"]]
        self.assertEqual(capability_ids, ["workflow_graph.list", "workflow_graph.inspect"])
        inspect_call = out["capability_calls"][1]
        self.assertEqual(inspect_call["status"], "completed")
        self.assertEqual(inspect_call["result"]["graph"]["graph_id"], "demo_graph_agent_tool")
        self.assertEqual(inspect_call["result"]["graph"]["node_count"], 1)

    def test_ingest_status_read_summarizes_recent_jobs(self):
        loop = AgentRunLoop(tool_runtime=self._tool_runtime())
        jobs = [
            {"id": 1, "job_type": "source_library_run", "status": "failed", "params": {"item_key": "demo.news"}},
            {"id": 2, "job_type": "other", "status": "completed", "params": {}},
        ]

        with patch("app.services.job_logger.list_jobs", return_value=jobs):
            out = loop.run(self._context("ingest.status.read"))

        self.assertEqual(out["tool_call_count"], 1)
        call = out["capability_calls"][0]
        self.assertEqual(call["capability_id"], "ingest.status.read")
        self.assertEqual(call["status"], "completed")
        self.assertEqual(call["result"]["job_status_counts"], {"failed": 1})


if __name__ == "__main__":
    unittest.main()
