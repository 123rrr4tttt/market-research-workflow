from __future__ import annotations

from contextlib import contextmanager
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.integration

try:
    from fastapi.testclient import TestClient

    from app.main import app as backend_app

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class AgentChatApiIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"agent chat integration tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(backend_app)

    def test_agent_chat_turn_route_returns_interactive_bundle(self):
        runtime = Mock()
        runtime.run_turn.return_value = {
            "contract_version": "interactive_agent.turn.v1",
            "session": {"session_id": "as-1", "entrypoint_type": "interactive_agent"},
            "tasks": [],
            "messages": [],
            "events": [],
            "artifacts": [],
            "approvals": [],
            "plan": {"selected_capabilities": []},
            "capability_calls": [{"capability_id": "agent_batch.nl_command.submit"}],
            "loop_result": {"submit": {"job_id": "abj-1"}},
            "final_answer": "done",
        }

        with patch("app.api.agent_chat.InteractiveAgentRuntime", return_value=runtime):
            response = self.client.post(
                "/api/v1/agent-chat/turn",
                json={"message": "采集市场动态", "project_key": "demo_proj", "runtime_variant": "agent_runtime_v2"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["data"]["contract_version"], "interactive_agent.turn.v1")
        self.assertTrue(body["data"]["feature_flags"]["agent_runtime_v2_enabled"])
        self.assertEqual(body["data"]["runtime_variant"], "agent_runtime_v2")
        runtime.run_turn.assert_called_once()
        self.assertFalse(runtime.run_turn.call_args.kwargs["require_high_risk_approval"])

    def test_agent_chat_turn_can_use_legacy_batch_runtime_variant(self):
        loop_result = {
            "loop_id": "legacy-loop",
            "submit": {"job_id": "abj-legacy", "accepted_count": 1, "rejected_count": 0},
        }

        with patch("app.api.agent_chat.run_agent_batch_nl_command_loop", return_value=loop_result) as mocked_loop:
            response = self.client.post(
                "/api/v1/agent-chat/turn",
                json={"message": "采集市场动态", "project_key": "demo_proj", "runtime_variant": "legacy_batch"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["data"]["runtime_variant"], "legacy_batch")
        self.assertEqual(body["data"]["contract_version"], "agent_chat.legacy_batch_turn.v1")
        self.assertIn("abj-legacy", body["data"]["final_answer"])
        mocked_loop.assert_called_once()

    def test_agent_chat_turn_stream_route_emits_sse_events(self):
        runtime = Mock()
        runtime.run_turn.return_value = {
            "contract_version": "interactive_agent.turn.v1",
            "session": {"session_id": "as-stream", "entrypoint_type": "interactive_agent"},
            "tasks": [],
            "messages": [],
            "events": [{"event_type": "interactive_agent.final_answer", "payload": {"summary": "done"}}],
            "artifacts": [],
            "approvals": [],
            "plan": {"selected_capabilities": []},
            "capability_calls": [],
            "loop_result": {},
            "stream": {"url": "/api/v1/agent-sessions/as-stream/stream"},
            "final_answer": "done",
        }

        with patch("app.api.agent_chat.InteractiveAgentRuntime", return_value=runtime):
            response = self.client.post(
                "/api/v1/agent-chat/turn/stream",
                json={"message": "你能做什么工具？", "project_key": "demo_proj", "runtime_variant": "agent_runtime_v2"},
            )

        self.assertEqual(response.status_code, 200)
        text = response.text
        self.assertIn("event: interactive_agent.stream_started", text)
        self.assertIn("event: interactive_agent.final_answer", text)
        self.assertIn('"result":', text)
        self.assertIn('"contract_version": "interactive_agent.turn.v1"', text)
        self.assertIn("done", text)

    def test_agent_core_stream_emits_live_core_events(self):
        from app.services.agent_core import CoreModelStep, FakeCoreProvider

        with patch("app.api.agent_chat._build_agent_core_provider", return_value=FakeCoreProvider([CoreModelStep.final("streamed core answer")])):
            response = self.client.post(
                "/api/v1/agent-chat/turn/stream",
                json={"message": "你好", "project_key": "demo_proj"},
            )

        self.assertEqual(response.status_code, 200)
        text = response.text
        self.assertIn("event: agent_core.stream_opened", text)
        self.assertIn("event: agent_core.stream_started", text)
        self.assertIn("event: agent_core.session_started", text)
        self.assertIn("event: agent_core.user_message", text)
        self.assertIn("event: agent_core.assistant_delta", text)
        self.assertIn("event: agent_core.final_answer", text)
        self.assertLess(text.index("event: agent_core.stream_opened"), text.index("event: agent_core.stream_started"))
        self.assertLess(text.index("event: agent_core.assistant_delta"), text.index("event: agent_core.final_answer"))
        self.assertIn("streamed core answer", text)

    def test_agent_core_stream_preserves_tool_metadata_for_project_answers(self):
        from app.services.agent_core import CoreModelStep, CoreToolCall, FakeCoreProvider

        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(CoreToolCall(tool_name="project.summary.read", call_id="call-summary")),
                CoreModelStep.final("项目摘要已读取。"),
            ]
        )
        with patch("app.api.agent_chat._build_agent_core_provider", return_value=provider):
            response = self.client.post(
                "/api/v1/agent-chat/turn/stream",
                json={"message": "项目里有什么数据", "project_key": "demo_proj"},
            )

        self.assertEqual(response.status_code, 200)
        text = response.text
        self.assertIn("event: agent_core.tool_call_requested", text)
        self.assertIn("event: agent_core.tool_result", text)
        self.assertIn("project.summary.read", text)
        self.assertIn('"capability_id": "project.summary.read"', text)
        self.assertIn("来源库/采集入口", text)
        self.assertIn("insubstantial_model_final_answer_after_tools", text)
        self.assertEqual(len(provider.calls), 2)
        self.assertFalse(provider.calls[0]["context"]["agent_core_auto_answer_after_project_tools"])

    def test_agent_core_writing_intent_uses_tool_without_approval_pause(self):
        from app.services.agent_core import CoreModelStep, CoreToolCall, FakeCoreProvider

        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="writing.document.insert_paragraph",
                        call_id="call-write",
                        arguments={"doc_id": 7, "content_md": "新增研究背景。", "operation": "append", "allow_latest": True},
                    )
                )
            ]
        )
        with patch("app.api.agent_chat._build_agent_core_provider", return_value=provider):
            response = self.client.post(
                "/api/v1/agent-chat/turn",
                json={"message": "帮我在写作工作台插入一段研究背景", "project_key": "demo_proj"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()["data"]
        self.assertEqual(body["runtime_variant"], "agent_core_v3")
        self.assertEqual(body["run_loop"]["stop_reason"], "final_answer")
        self.assertEqual(body["session"]["status"], "completed")
        self.assertEqual(body["tasks"][0]["status"], "completed")
        self.assertEqual(body["approval_requests"], [])
        self.assertEqual(body["capability_calls"][0]["tool_name"], "writing.document.insert_paragraph")
        self.assertNotIn("agent_batch.nl_command.submit", str(body))

    def test_agent_core_writing_tool_update_is_visible_to_writing_workbench_readback(self):
        from app.services.agent_core import CoreModelStep, CoreToolCall, FakeCoreProvider

        document = {
            "id": 7,
            "project_key": "demo_proj",
            "title": "Workbench Draft",
            "body_md": "# 背景\n\n已有段落。",
            "status": "draft",
            "version": 2,
            "etag": "etag-2",
            "metadata_json": {},
        }

        @contextmanager
        def noop_project_context(_project_key):
            yield

        def get_document(*, doc_id: int, project_key: str):
            self.assertEqual(doc_id, 7)
            self.assertEqual(project_key, "demo_proj")
            return dict(document)

        def save_document_with_conflict(**kwargs):
            self.assertEqual(kwargs["doc_id"], 7)
            self.assertEqual(kwargs["project_key"], "demo_proj")
            self.assertEqual(kwargs["base_version"], 2)
            self.assertEqual(kwargs["if_match"], "etag-2")
            document.update(
                {
                    "body_md": kwargs["body_md"],
                    "version": 3,
                    "etag": "etag-3",
                    "metadata_json": dict(kwargs["metadata_json"] or {}),
                }
            )
            return dict(document)

        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="writing.document.read",
                        call_id="call-read-before",
                        arguments={"doc_id": 7},
                    )
                ),
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="writing.document.insert_paragraph",
                        call_id="call-write",
                        arguments={
                            "doc_id": 7,
                            "content_md": "AgentCore 写回段落。",
                            "operation": "append",
                            "base_version": 2,
                            "if_match": "etag-2",
                        },
                    )
                ),
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="writing.document.read",
                        call_id="call-read-after",
                        arguments={"doc_id": 7},
                    )
                ),
                CoreModelStep.final("已写入并复核工作台文稿。"),
            ]
        )

        with (
            patch("app.api.agent_chat._build_agent_core_provider", return_value=provider),
            patch("app.services.agent_core.project_tools.bind_project", side_effect=noop_project_context),
            patch("app.services.agent_core.project_tools.get_document", side_effect=get_document),
            patch("app.services.agent_core.project_tools.save_document_with_conflict", side_effect=save_document_with_conflict),
            patch("app.api.writing.bind_project", side_effect=noop_project_context),
            patch("app.api.writing.get_document", side_effect=get_document),
        ):
            turn_response = self.client.post(
                "/api/v1/agent-chat/turn",
                json={"message": "把一段 AgentCore 写回内容追加到写作工作台文稿 7", "project_key": "demo_proj"},
            )
            readback_response = self.client.get(
                "/api/v1/writing/documents/7?project_key=demo_proj",
                headers={"X-Project-Key": "demo_proj"},
            )

        self.assertEqual(turn_response.status_code, 200)
        turn_body = turn_response.json()["data"]
        self.assertEqual(turn_body["runtime_variant"], "agent_core_v3")
        self.assertIn("写作工作台", turn_body["final_answer"])
        self.assertIn("Workbench Draft", turn_body["final_answer"])
        self.assertEqual(
            [call["tool_name"] for call in turn_body["capability_calls"]],
            ["writing.document.read", "writing.document.insert_paragraph", "writing.document.read"],
        )
        write_call = turn_body["capability_calls"][1]
        self.assertEqual(write_call["status"], "completed")
        self.assertEqual(write_call["result"]["doc_id"], 7)
        self.assertEqual(write_call["result"]["document"]["version"], 3)
        self.assertEqual(write_call["result"]["agent_update"]["call_id"], "call-write")

        self.assertEqual(readback_response.status_code, 200)
        readback_body = readback_response.json()
        self.assertEqual(readback_body["status"], "ok")
        self.assertEqual(readback_body["data"]["version"], 3)
        self.assertIn("AgentCore 写回段落。", readback_body["data"]["body_md"])
        self.assertEqual(readback_body["data"]["metadata_json"]["last_agent_update"]["call_id"], "call-write")

    def test_agent_core_compare_replay_creates_writing_document_instead_of_project_search(self):
        from app.services.agent_core import CoreModelStep, FakeCoreProvider, JsonCoreProvider

        class ProjectSearchFirstChat:
            def invoke(self, prompt):
                return {
                    "content": json.dumps(
                        {
                            "type": "tool_calls",
                            "tool_calls": [
                                {
                                    "tool_name": "project.structured_data.search",
                                    "arguments": {"query": "新建稿件并把内容贴进去"},
                                    "reason": "incorrect project search first",
                                }
                            ],
                        },
                        ensure_ascii=False,
                    )
                }

        @contextmanager
        def noop_project_context(_project_key):
            yield

        saved_document = {
            "id": 147,
            "project_key": "demo_proj_compare_0303_121137",
            "title": "机器人：从自动执行工具到具身智能载体的演进",
            "body_md": "# 机器人：从自动执行工具到具身智能载体的演进\n\n记录 94 提到人形机器人市场加速。",
            "status": "draft",
            "version": 1,
            "etag": "etag-147",
            "metadata_json": {},
        }
        first_provider = FakeCoreProvider(
            [
                CoreModelStep.final(
                    "# 机器人：从自动执行工具到具身智能载体的演进\n\n记录 94 提到人形机器人市场加速。\n\n## 引用框\n- 记录 94：证券时报 IDC 报告"
                )
            ]
        )
        second_provider = JsonCoreProvider(chat_model=ProjectSearchFirstChat())

        with patch("app.api.agent_chat._build_agent_core_provider", side_effect=[first_provider, second_provider]):
            first = self.client.post(
                "/api/v1/agent-chat/turn",
                json={"message": "输出完整稿件", "project_key": "demo_proj_compare_0303_121137"},
            )
            self.assertEqual(first.status_code, 200)
            session_id = first.json()["data"]["session"]["session_id"]
            with patch("app.services.agent_core.project_tools.bind_project", side_effect=noop_project_context):
                with patch("app.services.agent_core.project_tools.create_document", return_value=saved_document) as mocked_create:
                    second = self.client.post(
                        "/api/v1/agent-chat/turn",
                        json={
                            "message": "新建稿件并把内容贴进去",
                            "project_key": "demo_proj_compare_0303_121137",
                            "session_id": session_id,
                        },
                    )

        self.assertEqual(second.status_code, 200)
        body = second.json()["data"]
        self.assertEqual([item["tool_name"] for item in body["capability_calls"]], ["writing.document.create"])
        self.assertIn("已在写作工作台新建文档", body["final_answer"])
        self.assertIn("ID: 147", body["final_answer"])
        mocked_create.assert_called_once()
        self.assertEqual(mocked_create.call_args.kwargs["project_key"], "demo_proj_compare_0303_121137")
        self.assertIn("记录 94", mocked_create.call_args.kwargs["body_md"])

    def test_agent_chat_turn_injects_guarded_turn_planner_when_enabled(self):
        runtime = Mock()
        runtime.run_turn.return_value = {
            "contract_version": "interactive_agent.turn.v1",
            "session": {"session_id": "as-model", "entrypoint_type": "interactive_agent"},
            "tasks": [],
            "messages": [],
            "events": [],
            "artifacts": [],
            "approvals": [],
            "plan": {"selected_capabilities": [], "turn_decision": {"action": "answer_direct"}},
            "capability_calls": [],
            "loop_result": {},
            "final_answer": "model answer",
        }

        with patch("app.api.agent_chat.InteractiveAgentRuntime", return_value=runtime):
            response = self.client.post(
                "/api/v1/agent-chat/turn",
                json={"message": "解释一下 CAPM", "project_key": "demo_proj", "enable_model_tool_loop": True, "runtime_variant": "agent_runtime_v2"},
            )

        self.assertEqual(response.status_code, 200)
        kwargs = runtime.run_turn.call_args.kwargs
        self.assertIsNone(kwargs["run_loop_planner"])
        self.assertIsNotNone(kwargs["turn_decision_planner"])

    def test_agent_chat_turn_defaults_to_agent_core_v3(self):
        from app.services.agent_core import CoreModelStep, FakeCoreProvider

        with patch("app.api.agent_chat._build_agent_core_provider", return_value=FakeCoreProvider([CoreModelStep.final("core answer")])):
            response = self.client.post(
                "/api/v1/agent-chat/turn",
                json={"message": "你好", "project_key": "demo_proj"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["data"]["runtime_variant"], "agent_core_v3")
        self.assertEqual(body["data"]["contract_version"], "agent_core.turn.v1")
        self.assertEqual(body["data"]["final_answer"], "core answer")
        self.assertEqual(body["data"]["plan"]["classifier"], "not_used")
        self.assertEqual(body["data"]["plan"]["tool_count"], 0)
        self.assertEqual(body["data"]["plan"]["tool_window_profile"], "conversation")
        self.assertEqual(body["data"]["feature_flags"]["agent_runtime_v2_enabled"], True)
        self.assertEqual([task["phase"] for task in body["data"]["tasks"]], ["conversation"])
        self.assertEqual([task["subject"] for task in body["data"]["tasks"]], ["Agent Core Turn"])
        self.assertEqual([task["status"] for task in body["data"]["tasks"]], ["completed"])

    def test_agent_core_e2e_scripted_provider_uses_isolated_session_source(self):
        with patch("app.api.agent_chat.settings.agent_core_e2e_scripted_provider_enabled", True):
            response = self.client.post(
                "/api/v1/agent-chat/turn",
                json={"message": "CAPM 核心假设是什么", "project_key": "demo_proj"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()["data"]
        self.assertEqual(body["session"]["source"], "e2e-scripted")
        self.assertIn("CAPM", body["final_answer"])

    def test_agent_chat_default_project_key_is_rejected_for_new_session(self):
        from app.services.agent_core import CoreModelStep, FakeCoreProvider

        with patch("app.api.agent_chat._lookup_active_agent_project_key", return_value="demo_proj"):
            with patch("app.api.agent_chat._build_agent_core_provider", return_value=FakeCoreProvider([CoreModelStep.final("core answer")])):
                response = self.client.post(
                    "/api/v1/agent-chat/turn",
                    json={"message": "项目里有什么数据", "project_key": "default"},
                )

        self.assertEqual(response.status_code, 400)
        body = response.json()["detail"]["error"]
        self.assertEqual(body["code"], "INVALID_INPUT")
        self.assertIn("project_key is required", body["message"])

    def test_agent_core_rejects_cross_project_session_reuse(self):
        from app.services.agent_core import CoreModelStep, FakeCoreProvider
        from app.services.agent_sessions.service import get_agent_session_service

        service = get_agent_session_service()
        bundle = service.create_session(
            source="unit-test",
            entrypoint_type="agent_core",
            goal="项目 A 上下文",
            project_key="project_a",
            metadata={"test": "cross_project_session_guard"},
        )

        with patch("app.api.agent_chat._build_agent_core_provider", return_value=FakeCoreProvider([CoreModelStep.final("should not run")])):
            response = self.client.post(
                "/api/v1/agent-chat/turn",
                json={"message": "继续", "project_key": "project_b", "session_id": bundle["session"]["session_id"]},
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("different project", str(response.json()))

    def test_agent_core_turn_uses_prior_session_transcript_for_followup(self):
        from app.services.agent_core import AgentCoreRequest, CoreModelStep, CoreToolSpec
        from app.services.agent_sessions.service import get_agent_session_service

        class ContextAwareProvider:
            def __init__(self) -> None:
                self.calls = []

            def next_step(
                self,
                *,
                request: AgentCoreRequest,
                tools: list[CoreToolSpec],
                transcript: list[dict],
                remaining_budget: dict,
            ) -> CoreModelStep:
                self.calls.append(
                    {
                        "transcript": list(transcript),
                        "context": dict(request.context or {}),
                        "tool_names": [tool.name for tool in tools],
                    }
                )
                has_prior_answer = any(
                    item.get("role") == "assistant" and "documents 和 graph_nodes" in str(item.get("content") or "")
                    for item in transcript
                )
                return CoreModelStep.final("基于上文总结：项目里有 documents 和 graph_nodes。" if has_prior_answer else "缺少上文。")

        service = get_agent_session_service()
        bundle = service.create_session(
            source="unit-test",
            entrypoint_type="agent_core",
            goal="项目里有什么数据",
            project_key="demo_proj",
            metadata={"test": "followup_context"},
        )
        session_id = bundle["session"]["session_id"]
        service.create_message(
            session_id,
            role="assistant",
            actor="agent_core",
            content="项目里已有 documents 和 graph_nodes 数据。",
            metadata={"runtime_variant": "agent_core_v3"},
        )
        provider = ContextAwareProvider()

        with patch("app.api.agent_chat._build_agent_core_provider", return_value=provider):
            response = self.client.post(
                "/api/v1/agent-chat/turn",
                json={"message": "帮我总结一些", "project_key": "demo_proj", "session_id": session_id},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()["data"]
        self.assertEqual(body["final_answer"], "基于上文总结：项目里有 documents 和 graph_nodes。")
        self.assertTrue(provider.calls[0]["context"]["contextual_followup"])
        self.assertGreaterEqual(len(provider.calls[0]["context"]["prior_transcript"]), 2)
        self.assertIn("session_context_summary", provider.calls[0]["context"])
        self.assertTrue(body["plan"]["tool_window_context_used"])
        self.assertIn("project.structured_data.search", provider.calls[0]["tool_names"])
        self.assertEqual(body["context_summary"]["contract_version"], "agent_core.context_summary.v1")
        self.assertGreaterEqual(body["context_summary"]["prior_transcript_count"], 2)

    def test_agent_core_turn_can_query_project_structured_data_tool(self):
        from app.services.agent_core import CoreModelStep, CoreToolCall, FakeCoreProvider

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

        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(CoreToolCall(tool_name="project.structured_data.search", arguments={"query": "", "limit": 8})),
                CoreModelStep.final("项目里已有 documents 数据，例如 Demo document。"),
            ]
        )
        with patch("app.api.agent_chat._build_agent_core_provider", return_value=provider):
            with patch("app.services.agent_runtime.read_only_tools.query_project_structured_data", side_effect=structured_searcher):
                response = self.client.post(
                    "/api/v1/agent-chat/turn",
                    json={"message": "项目里有什么数据", "project_key": "demo_proj"},
                )

        self.assertEqual(response.status_code, 200)
        body = response.json()["data"]
        self.assertEqual(body["runtime_variant"], "agent_core_v3")
        self.assertEqual(body["capability_calls"][0]["capability_id"], "project.structured_data.search")
        result = body["capability_calls"][0]["result"]["result"]
        self.assertEqual(result["query_mode"], "inventory")
        self.assertEqual(result["items"][0]["title"], "Demo document")
        self.assertEqual(result["model_evidence_manifest"][0]["read_tool"], "project.structured_data.item.read")
        self.assertFalse(provider.calls[0]["context"]["agent_core_auto_answer_after_project_tools"])
        self.assertEqual(len(provider.calls), 2)
        self.assertIn("Demo document", body["final_answer"])

    def test_agent_core_robot_material_summary_can_demand_read_local_record(self):
        from app.services.agent_core import CoreModelStep, CoreToolCall, FakeCoreProvider

        def structured_searcher(**kwargs):
            return {
                "contract_version": "project.structured_data.search.v1",
                "project_key": kwargs.get("project_key"),
                "query": kwargs.get("query") or "机器人",
                "query_mode": "search",
                "inventory": [{"dataset": "documents", "label": "Documents", "sample_count": 1, "total_rows": 1}],
                "dataset_counts": {"documents": 1},
                "total_matches": 1,
                "items": [
                    {
                        "dataset": "documents",
                        "record_id": "doc-robot",
                        "title": "机器人商业化本地资料",
                        "summary": "本地项目资料显示仓储机器人试点加速，成本压力集中在传感器和系统集成。",
                    }
                ],
                "dataset_results": [],
                "errors": [],
            }

        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(CoreToolCall(tool_name="project.structured_data.search", arguments={"query": "机器人", "limit": 5}, call_id="call-search")),
                CoreModelStep.tools(CoreToolCall(tool_name="project.structured_data.item.read", arguments={"dataset": "documents", "record_id": "doc-robot"}, call_id="call-read")),
                CoreModelStep.final("本地资料的实质结论是：仓储机器人试点在加速，但商业化瓶颈集中在传感器和系统集成成本。"),
            ]
        )
        with patch("app.api.agent_chat._build_agent_core_provider", return_value=provider):
            with patch("app.services.agent_runtime.read_only_tools.query_project_structured_data", side_effect=structured_searcher):
                response = self.client.post(
                    "/api/v1/agent-chat/turn",
                    json={"message": "帮我总结一些机器人资料", "project_key": "demo_proj"},
                )

        self.assertEqual(response.status_code, 200)
        body = response.json()["data"]
        tool_names = [item["tool_name"] for item in body["capability_calls"]]
        self.assertEqual(tool_names[:2], ["project.structured_data.search", "project.structured_data.item.read"])
        read_result = body["capability_calls"][1]["result"]["result"]
        self.assertEqual(read_result["item"]["title"], "机器人商业化本地资料")
        self.assertIn("系统集成成本", body["final_answer"])
        self.assertEqual(len(provider.calls), 3)

    def test_agent_core_execution_tool_runs_without_default_approval_pause(self):
        from app.services.agent_core import CoreModelStep, CoreToolCall, FakeCoreProvider

        tool_call = CoreToolCall(
            tool_name="ingest.source_library.run",
            arguments={"items": ["demo.news"]},
            call_id="call-ingest",
        )

        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(tool_call),
                CoreModelStep.final("已直接提交来源库补证据任务。"),
            ]
        )
        with patch("app.api.agent_chat._build_agent_core_provider", return_value=provider):
            with patch(
                "app.services.agent_core.project_tools.invoke_skill",
                return_value={"result": {"task_id": "task-demo-news"}},
            ):
                turn_response = self.client.post(
                    "/api/v1/agent-chat/turn",
                    json={"message": "用来源库补一轮证据", "project_key": "demo_proj"},
                )
        self.assertEqual(turn_response.status_code, 200)
        turn_body = turn_response.json()["data"]
        self.assertEqual(turn_body["runtime_variant"], "agent_core_v3")
        self.assertEqual(turn_body["run_loop"]["stop_reason"], "final_answer")
        self.assertEqual(turn_body["tasks"][0]["status"], "completed")
        self.assertEqual(turn_body["approval_requests"], [])
        self.assertEqual(turn_body["capability_calls"][0]["tool_name"], "ingest.source_library.run")
        self.assertEqual(turn_body["capability_calls"][0]["status"], "completed")
        self.assertIn("来源库采集", turn_body["final_answer"])
        self.assertIn("后续应读取 ingest 状态", turn_body["final_answer"])

    def test_agent_core_long_task_chat_api_has_enough_iterations_for_multi_tool_loop(self):
        from app.services.agent_core import CoreModelStep, CoreToolCall, FakeCoreProvider

        calls = [
            CoreToolCall(tool_name="project.summary.read", call_id=f"call-summary-{index}")
            for index in range(1, 8)
        ]
        provider = FakeCoreProvider(
            [CoreModelStep.tools(call) for call in calls]
            + [CoreModelStep.final("长任务多轮工具循环已完成。")]
        )
        with patch("app.api.agent_chat._build_agent_core_provider", return_value=provider):
            response = self.client.post(
                "/api/v1/agent-chat/turn",
                json={"message": "执行一个长任务：持续调查机器人商业化线索", "project_key": "demo_proj"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()["data"]
        self.assertEqual(body["plan"]["tool_window_profile"], "long-task-investigation")
        self.assertEqual(body["run_loop"]["stop_reason"], "final_answer")
        self.assertIn("来源库/采集入口", body["final_answer"])
        self.assertIn("当前会话数据", body["final_answer"])
        self.assertEqual(len(body["capability_calls"]), 7)
        self.assertEqual(provider.calls[-1]["remaining_budget"]["max_iterations"], 14)

    def test_agent_core_turn_runs_investigation_trace_to_writing_chain_through_chat_api(self):
        from app.services.agent_core import CoreModelStep, CoreToolCall, FakeCoreProvider

        saved_document = {
            "id": 88,
            "project_key": "demo_proj",
            "title": "Robot Investigation",
            "body_md": "# Robot Investigation\n\n候选来源显示配送机器人商业化正在加速。",
            "status": "draft",
            "version": 1,
            "etag": "etag-88",
            "metadata_json": {},
        }
        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="source.discovery.plan",
                        call_id="call-discovery",
                        arguments={
                            "project_key": "demo_proj",
                            "topic": "配送机器人商业化",
                            "query_terms": ["配送机器人", "商业化"],
                            "candidate_urls": ["https://example.com/robot-market"],
                        },
                    )
                ),
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="agent_investigation.leads.append",
                        call_id="call-leads",
                        arguments={
                            "project_key": "demo_proj",
                            "artifact_name": "robot-api.leads.json",
                            "goal": "配送机器人商业化调查",
                            "clue_nodes": [
                                {"id": "robot_market", "label": "配送机器人市场"},
                                {"id": "source_candidate", "label": "候选来源"},
                                {"id": "writing_claim", "label": "写作论点"},
                            ],
                            "clue_edges": [
                                {"source": "robot_market", "target": "source_candidate", "relation": "evidenced_by"},
                                {"source": "source_candidate", "target": "writing_claim", "relation": "supports"},
                            ],
                            "followed_leads": [{"url": "https://example.com/robot-market"}],
                            "pending_questions": ["是否有官方披露可验证"],
                            "citations": [{"source_id": "candidate:example.com", "quote": "robot-market"}],
                        },
                    )
                ),
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="agent_investigation.trace.read",
                        call_id="call-trace",
                        arguments={"artifact_name": "robot-api.leads.json", "focus_node_id": "robot_market", "max_hops": 2},
                    )
                ),
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="writing.document.insert_paragraph",
                        call_id="call-writing",
                        arguments={
                            "project_key": "demo_proj",
                            "title": "Robot Investigation",
                            "operation": "append",
                            "content_md": "配送机器人商业化线索已从候选来源推进到写作论点，仍需补充官方披露验证。",
                            "source_refs": ["https://example.com/robot-market"],
                            "provenance": {"from_tool_call": "call-trace"},
                        },
                    )
                ),
                CoreModelStep.tools(CoreToolCall(tool_name="agent_session.resume_bundle", arguments={"limit": 10}, call_id="call-resume")),
                CoreModelStep.final("已完成调查、追踪、写作和恢复上下文闭环。"),
            ]
        )

        @contextmanager
        def noop_project_context(_project_key):
            yield

        with patch("app.api.agent_chat._build_agent_core_provider", return_value=provider):
            with patch("app.api.agent_chat._list_source_library_items_for_agent", return_value=[{"item_key": "robot.baseline", "name": "Robot Baseline"}]):
                with patch("app.services.agent_core.project_tools.bind_project", side_effect=noop_project_context):
                    with patch("app.services.agent_core.project_tools.create_document", return_value=saved_document) as mocked_create:
                        response = self.client.post(
                            "/api/v1/agent-chat/turn",
                            json={"message": "执行一个多轮调查：追查配送机器人商业化并写入工作台", "project_key": "demo_proj"},
                        )

        self.assertEqual(response.status_code, 200)
        body = response.json()["data"]
        self.assertEqual(body["runtime_variant"], "agent_core_v3")
        self.assertEqual(
            [item["tool_name"] for item in body["capability_calls"]],
            [
                "source.discovery.plan",
                "agent_investigation.leads.append",
                "agent_investigation.trace.read",
                "writing.document.insert_paragraph",
                "agent_session.resume_bundle",
            ],
        )
        trace_result = next(item for item in body["capability_calls"] if item["tool_name"] == "agent_investigation.trace.read")["result"]
        self.assertEqual(trace_result["focus_node_id"], "robot_market")
        self.assertEqual({item["id"] for item in trace_result["nodes"]}, {"robot_market", "source_candidate", "writing_claim"})
        self.assertEqual({item["relation"] for item in trace_result["edges"]}, {"evidenced_by", "supports"})
        self.assertIn("robot-api.leads.json", {item["name"] for item in body["artifacts"]})
        mocked_create.assert_called_once()
        self.assertIn("当前线索图", body["final_answer"])
        self.assertIn("Robot Investigation", body["final_answer"])

    def test_agent_core_can_attach_material_card_citations_to_writing_document(self):
        from app.services.agent_core import CoreModelStep, CoreToolCall, FakeCoreProvider

        provider = FakeCoreProvider(
            [
                CoreModelStep.tools(
                    CoreToolCall(
                        tool_name="writing.document.citations.upsert",
                        call_id="call-citations",
                        arguments={
                            "project_key": "demo_proj",
                            "doc_id": 88,
                            "material_cards": [
                                {
                                    "id": "card-robot-market",
                                    "title": "机器人市场资料卡",
                                    "url": "https://example.com/robot-market",
                                    "snippet": "机器人市场加速。",
                                }
                            ],
                            "position_anchor": "selection:robot-market",
                            "provenance": {"from_selection": "机器人商业化"},
                        },
                    )
                ),
                CoreModelStep.final("已把资料卡加入引用框。"),
            ]
        )
        saved = [
            {
                "id": 12,
                "doc_id": 88,
                "project_key": "demo_proj",
                "card_id": "card-robot-market",
                "source_uri": "https://example.com/robot-market",
                "source_title": "机器人市场资料卡",
                "quote_text": "机器人市场加速。",
                "position_anchor": "selection:robot-market",
            }
        ]

        @contextmanager
        def noop_project_context(_project_key):
            yield

        with patch("app.api.agent_chat._build_agent_core_provider", return_value=provider):
            with patch("app.services.agent_core.project_tools.bind_project", side_effect=noop_project_context):
                with patch("app.services.agent_core.project_tools.list_citations", return_value=[]) as mocked_list:
                    with patch("app.services.agent_core.project_tools.upsert_citations", return_value=saved) as mocked_upsert:
                        response = self.client.post(
                            "/api/v1/agent-chat/turn",
                            json={"message": "把这张资料卡加入写作工作台引用框", "project_key": "demo_proj"},
                        )

        self.assertEqual(response.status_code, 200)
        body = response.json()["data"]
        self.assertEqual([item["tool_name"] for item in body["capability_calls"]], ["writing.document.citations.upsert"])
        call_result = body["capability_calls"][0]["result"]
        self.assertEqual(call_result["contract_version"], "writing.document.citations.upsert.v1")
        self.assertEqual(call_result["doc_id"], 88)
        self.assertEqual(call_result["total_count"], 1)
        mocked_list.assert_called_once_with(doc_id=88, project_key="demo_proj")
        mocked_upsert.assert_called_once()
        self.assertEqual(mocked_upsert.call_args.kwargs["citations"][0]["card_id"], "card-robot-market")
        self.assertEqual(mocked_upsert.call_args.kwargs["citations"][0]["source_uri"], "https://example.com/robot-market")

    def test_agent_source_library_lister_reuses_short_ttl_cache(self):
        from app.api import agent_chat

        agent_chat._source_library_agent_cache.clear()
        with patch(
            "app.api.agent_chat.list_effective_items",
            return_value=[{"item_key": "demo.news", "name": "Demo News"}],
        ) as mocked_list:
            first = agent_chat._list_source_library_items_for_agent("demo_proj")
            second = agent_chat._list_source_library_items_for_agent("demo_proj")

        self.assertEqual(first, second)
        mocked_list.assert_called_once_with(scope="effective", project_key="demo_proj", include_execution_plan=False)
        agent_chat._source_library_agent_cache.clear()

    def test_agent_chat_capabilities_route_includes_runtime_feature_flags(self):
        response = self.client.get("/api/v1/agent-chat/capabilities")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("items", body["data"])
        self.assertIn("tool_pool", body["data"])
        self.assertGreaterEqual(body["data"]["tool_pool"]["counts"]["core"], 1)
        self.assertEqual(
            set(body["data"]["feature_flags"].keys()),
            {"agent_runtime_v2_enabled", "agent_stream_enabled", "agent_batch_as_tool_enabled"},
        )

    def test_agent_chat_capabilities_route_marks_core_and_deferred_tool_metadata(self):
        response = self.client.get("/api/v1/agent-chat/capabilities?project_key=demo_proj")

        self.assertEqual(response.status_code, 200)
        body = response.json()["data"]
        tools = {item["capability_id"]: item for item in body["tool_pool"]["tools"]}

        project_summary = tools["project.summary.read"]
        self.assertEqual(project_summary["tool_group"], "core")
        self.assertFalse(project_summary["deferred"])
        self.assertTrue(project_summary["implemented"])
        self.assertEqual(project_summary["implementation_state"], "implemented")
        self.assertEqual(project_summary["permission_state"], "available")
        self.assertEqual(project_summary["loading_hint"], "core")

        source_run = tools["ingest.source_library.run"]
        self.assertEqual(source_run["tool_group"], "deferred")
        self.assertTrue(source_run["deferred"])
        self.assertTrue(source_run["implemented"])
        self.assertEqual(source_run["implementation_state"], "implemented")
        self.assertEqual(source_run["approval_level"], "high")
        self.assertEqual(source_run["permission_state"], "available")
        self.assertEqual(source_run["loading_hint"], "implemented but governed by explicit model selection or approval")
        self.assertIn(source_run, body["tool_pool"]["groups"]["deferred"])
        self.assertEqual(tools["skill.search"]["tool_group"], "core")
        self.assertEqual(tools["mcp.tools.list"]["implementation_state"], "implemented")
        browser_service = tools["mcp.service.browser-playwright"]
        self.assertFalse(browser_service["implemented"])
        self.assertFalse(browser_service["enabled"])
        self.assertEqual(browser_service["implementation_state"], "not_configured")
        self.assertFalse(browser_service["configured"])
        self.assertFalse(browser_service["reachable"])
        self.assertIn(browser_service, body["tool_pool"]["groups"]["disabled"])
        external_search = tools["mcp.service.external-search"]
        self.assertEqual(external_search["service_status"], "not_configured")
        source_web_search = tools["source.web.search"]
        self.assertEqual(source_web_search["tool_group"], "core")
        self.assertTrue(source_web_search["implemented"])
        self.assertEqual(source_web_search["implementation_state"], "implemented")
        self.assertEqual(source_web_search["permission_state"], "available")
        source_candidate_review = tools["source.candidate.review"]
        self.assertEqual(source_candidate_review["tool_group"], "core")
        self.assertTrue(source_candidate_review["implemented"])
        self.assertEqual(source_candidate_review["implementation_state"], "implemented")
        self.assertEqual(source_candidate_review["permission_state"], "available")
        url_pool_submit = tools["ingest.url_pool.submit"]
        self.assertEqual(url_pool_submit["tool_group"], "core")
        self.assertTrue(url_pool_submit["implemented"])
        self.assertEqual(url_pool_submit["implementation_state"], "implemented")
        self.assertEqual(url_pool_submit["permission_state"], "available")
        url_pool_status = tools["ingest.url_pool.status"]
        self.assertEqual(url_pool_status["tool_group"], "core")
        self.assertTrue(url_pool_status["implemented"])
        self.assertEqual(url_pool_status["implementation_state"], "implemented")
        self.assertEqual(url_pool_status["permission_state"], "available")
        source_history = tools["source.history.read"]
        self.assertEqual(source_history["tool_group"], "core")
        self.assertTrue(source_history["implemented"])
        self.assertEqual(source_history["implementation_state"], "implemented")
        self.assertEqual(source_history["permission_state"], "available")

    def test_agent_core_control_tools_cancel_continue_retry_in_one_session(self):
        from app.services.agent_core import CoreModelStep, CoreToolCall, FakeCoreProvider
        from app.services.agent_sessions.service import AgentSessionService, get_agent_session_service, reset_agent_session_service_for_tests
        from app.services.agent_sessions.store import InMemoryAgentSessionStore

        reset_agent_session_service_for_tests(AgentSessionService(store=InMemoryAgentSessionStore()))
        service = get_agent_session_service()
        providers = [
            FakeCoreProvider([CoreModelStep.final("控制场景已准备。")]),
            FakeCoreProvider(
                [
                    CoreModelStep.tools(CoreToolCall(tool_name="task.cancel", call_id="call-cancel", arguments={"reason": "user requested cancel"})),
                    CoreModelStep.final("已取消当前会话。"),
                ]
            ),
            FakeCoreProvider(
                [
                    CoreModelStep.tools(CoreToolCall(tool_name="task.continue", call_id="call-continue", arguments={"reason": "user requested continue"})),
                    CoreModelStep.final("已继续当前会话。"),
                ]
            ),
            FakeCoreProvider(
                [
                    CoreModelStep.tools(CoreToolCall(tool_name="task.retry", call_id="call-retry", arguments={"reason": "user requested retry"})),
                    CoreModelStep.final("已重试失败任务。"),
                ]
            ),
        ]

        try:
            with patch("app.api.agent_chat._build_agent_core_provider", side_effect=providers):
                first = self.client.post(
                    "/api/v1/agent-chat/turn",
                    json={"message": "准备一个可取消和重试的长任务", "project_key": "demo_proj"},
                )
                self.assertEqual(first.status_code, 200)
                session_id = first.json()["data"]["session"]["session_id"]
                service.append_task_blueprints(
                    session_id,
                    goal="control replay task",
                    task_blueprints=[
                        {
                            "task_id": "task-control-worker",
                            "subject": "control worker",
                            "task_type": "execute",
                            "phase": "implementation",
                        }
                    ],
                )

                canceled = self.client.post(
                    "/api/v1/agent-chat/turn",
                    json={"message": "取消当前会话", "project_key": "demo_proj", "session_id": session_id},
                )
                self.assertEqual(canceled.status_code, 200)
                canceled_body = canceled.json()["data"]
                self.assertEqual(canceled_body["capability_calls"][0]["tool_name"], "task.cancel")
                self.assertEqual(canceled_body["capability_calls"][0]["status"], "completed")
                self.assertEqual(canceled_body["session"]["status"], "canceled")
                self.assertEqual(service.get_session(session_id)["status"], "canceled")

                continued = self.client.post(
                    "/api/v1/agent-chat/turn",
                    json={"message": "继续", "project_key": "demo_proj", "session_id": session_id},
                )
                self.assertEqual(continued.status_code, 200)
                continued_body = continued.json()["data"]
                self.assertEqual(continued_body["capability_calls"][0]["tool_name"], "task.continue")
                self.assertEqual(continued_body["capability_calls"][0]["status"], "completed")
                resumed = next(task for task in service.list_tasks(session_id) if task["task_id"] == "task-control-worker")
                self.assertIn(resumed["status"], {"pending", "blocked"})

                service.append_task_blueprints(
                    session_id,
                    goal="retry replay task",
                    task_blueprints=[
                        {
                            "task_id": "task-retry-worker",
                            "subject": "retry worker",
                            "task_type": "execute",
                            "phase": "implementation",
                        }
                    ],
                )
                service.release_task(session_id, "task-retry-worker", status="failed", result_summary="simulated failure")

                retried = self.client.post(
                    "/api/v1/agent-chat/turn",
                    json={"message": "重试失败任务", "project_key": "demo_proj", "session_id": session_id},
                )
                self.assertEqual(retried.status_code, 200)
                retried_body = retried.json()["data"]
                self.assertEqual(retried_body["capability_calls"][0]["tool_name"], "task.retry")
                self.assertEqual(retried_body["capability_calls"][0]["status"], "completed")
                self.assertEqual(service.store.get_task(session_id, "task-retry-worker")["status"], "pending")
        finally:
            reset_agent_session_service_for_tests(None)

    def test_agent_chat_turn_invalid_message_returns_structured_error(self):
        response = self.client.post(
            "/api/v1/agent-chat/turn",
            json={"message": "", "project_key": "demo_proj"},
        )

        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["status"], "error")

    def test_agent_chat_approval_continue_route_returns_runtime_bundle(self):
        runtime = Mock()
        runtime.continue_approved_capability.return_value = {
            "contract_version": "interactive_agent.turn.v1",
            "approval": {"approval_id": "approval-1", "status": "approved"},
            "session": {"session_id": "as-1", "status": "completed"},
            "tasks": [],
            "messages": [],
            "events": [],
            "artifacts": [],
            "approvals": [],
            "capability_call": {"capability_id": "workflow_graph.run", "status": "completed"},
            "continued": True,
            "final_answer": "continued",
        }

        with patch("app.api.agent_chat.InteractiveAgentRuntime", return_value=runtime):
            response = self.client.post(
                "/api/v1/agent-chat/approvals/approval-1/continue",
                json={"approved_by": "unit-test", "binding_payload_overrides": {"graph_id": "g-override"}},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertTrue(body["data"]["continued"])
        runtime.continue_approved_capability.assert_called_once_with(
            approval_id="approval-1",
            approved_by="unit-test",
            binding_payload_overrides={"graph_id": "g-override"},
        )


if __name__ == "__main__":
    unittest.main()
