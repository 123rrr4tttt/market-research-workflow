from __future__ import annotations

import unittest
from unittest.mock import patch

import pytest

from app.services.agent_runtime.capability_registry import classify_goal, select_capabilities_for_goal
from app.services.agent_runtime.control_tools import AgentControlToolRuntime
from app.services.agent_core.functorial.operator import project_process_operators
from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_sessions.store import InMemoryAgentSessionStore

pytestmark = pytest.mark.unit


class AgentControlToolsUnitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = AgentSessionService(store=InMemoryAgentSessionStore())
        self.bundle = self.service.create_session(
            source="user",
            entrypoint_type="interactive_agent",
            goal="control tool test",
            project_key="demo_proj",
            task_blueprints=[
                {
                    "task_id": "task-plan",
                    "subject": "plan",
                    "task_type": "plan",
                    "phase": "research",
                },
                {
                    "task_id": "task-failed",
                    "subject": "failed task",
                    "task_type": "execute",
                    "phase": "implementation",
                    "blocked_by": ["task-plan"],
                },
            ],
        )
        self.session_id = self.bundle["session"]["session_id"]
        self.service.release_task(self.session_id, "task-plan", status="completed")
        self.service.release_task(self.session_id, "task-failed", status="failed", result_summary="boom")
        self.runtime = AgentControlToolRuntime(service=self.service)

    def test_control_capability_selection(self):
        self.assertEqual(classify_goal("继续上一步"), "control")
        self.assertEqual(classify_goal("重试失败任务"), "control")
        self.assertEqual(classify_goal("取消当前会话"), "control")
        self.assertIn("task.summary", [item["capability_id"] for item in select_capabilities_for_goal("继续上一步")])
        self.assertIn("task.retry", [item["capability_id"] for item in select_capabilities_for_goal("重试失败任务")])
        self.assertIn("task.cancel", [item["capability_id"] for item in select_capabilities_for_goal("取消当前会话")])

    def test_greeting_does_not_select_agent_batch(self):
        self.assertEqual(classify_goal("你好"), "conversation")
        self.assertNotIn("agent_batch.nl_command.submit", [item["capability_id"] for item in select_capabilities_for_goal("你好")])

    def test_task_retry_uses_latest_failed_task_when_task_id_omitted(self):
        call = self.runtime.execute("task.retry", session_id=self.session_id, turn_id="turn-control")

        self.assertEqual(call["status"], "completed")
        self.assertEqual(call["result"]["task_id"], "task-failed")
        retried = self.service.store.get_task(self.session_id, "task-failed")
        self.assertEqual(retried["status"], "pending")

    def test_task_cancel_cancels_session(self):
        call = self.runtime.execute("task.cancel", session_id=self.session_id, turn_id="turn-control")

        self.assertEqual(call["status"], "completed")
        self.assertEqual(self.service.get_session(self.session_id)["status"], "canceled")

    def test_legacy_continue_is_rejected_without_mutating_canceled_session(self):
        self.service.cancel_session(self.session_id)
        before = self.service.get_session(self.session_id)

        call = self.runtime.execute("task.continue", session_id=self.session_id, turn_id="turn-control")

        self.assertEqual(call["status"], "failed")
        self.assertEqual(call["error"]["type"], "UnsupportedTool")
        self.assertEqual(self.service.get_session(self.session_id), before)

    def test_task_summary_reads_session_owner_projection(self):
        call = self.runtime.execute("task.summary", session_id=self.session_id, turn_id="turn-control")

        self.assertEqual(call["status"], "completed")
        summary = call["result"]["summary"]
        self.assertEqual(summary["session_id"], self.session_id)
        self.assertEqual(summary["status"], self.service.get_session(self.session_id)["status"])
        self.assertEqual(summary["task_counts"], {"completed": 1, "failed": 1})

    def test_failure_results_are_preserved(self):
        retry_call = self.runtime.execute(
            "task.retry",
            session_id="missing-session",
            turn_id="turn-control",
            input_payload={"task_id": "missing-task"},
        )
        summary_call = self.runtime.execute("task.summary", session_id="missing-session", turn_id="turn-control")

        self.assertEqual(retry_call["status"], "failed")
        self.assertEqual(retry_call["error"]["code"], "session_not_found")
        self.assertEqual(retry_call["result"], {"session_id": "missing-session", "task_id": "missing-task"})
        self.assertEqual(summary_call["status"], "failed")
        self.assertEqual(summary_call["error"]["code"], "session_not_found")
        self.assertEqual(summary_call["error"]["context"], {"session_id": "missing-session"})

    def test_control_tool_exports_preserve_host_authorization_contract(self):
        definitions = {item["name"]: item for item in self.runtime.list_tool_definitions()}

        self.assertEqual(set(definitions), {"task.cancel", "task.retry", "task.summary"})
        self.assertEqual(definitions["task.cancel"]["approval_level"], "explicit_user_request")
        self.assertEqual(definitions["task.retry"]["approval_level"], "explicit_user_request")
        self.assertEqual(definitions["task.summary"]["approval_level"], "none")
        self.assertEqual(definitions["task.summary"]["concurrency_class"], "read_only")

    def test_functorial_projection_does_not_export_legacy_continue(self):
        with patch("app.services.agent_core.project_tools.list_registered_skills", return_value=[]):
            operator_ids = {item.operator_id for item in project_process_operators()}

        self.assertNotIn("task.continue", operator_ids)
        self.assertIn("task.summary", operator_ids)
if __name__ == "__main__":
    unittest.main()
