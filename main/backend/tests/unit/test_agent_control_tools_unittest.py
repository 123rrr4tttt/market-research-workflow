from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.agent_runtime.capability_registry import classify_goal, select_capabilities_for_goal
from app.services.agent_runtime.control_tools import AgentControlToolRuntime
from app.services.agent_core.host_authorization import (
    TrustedHostContext,
    VerifiedHostAuthorization,
    verified_host_authorization_channel,
)
from app.services.agent_core.tool_support import session_abort_requested
from app.services.request_identity import RequestActorContext
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
        self.service.store.update_task(self.session_id, "task-plan", {"status": "completed"})
        self.service.store.update_task(
            self.session_id,
            "task-failed",
            {"status": "failed", "result_summary": "boom"},
        )
        self.runtime = AgentControlToolRuntime(service=self.service)

    def _authorization(self, session_id: str) -> VerifiedHostAuthorization:
        actor = RequestActorContext(
            actor_id="authenticated-user-7",
            actor_source="test_auth",
            actor_trusted=True,
            actor_auth_mode="test_auth",
        )
        return VerifiedHostAuthorization(
            context=TrustedHostContext(
                project_key="demo_proj",
                session_id=session_id,
                host_thread_id="thread-7",
                turn_id="turn-control",
                user_message_id="message-7",
                actor_context=actor,
            ),
            tool_name="task.cancel",
            arguments_sha256="a" * 64,
            package_digest=None,
            permission="explicit_user_request",
            approval_id="approval-7",
            origin_call_id="call-7",
            origin_turn_id="turn-control",
            origin_user_message_id="message-7",
            execution_call_id="call-7",
        )

    def test_control_capability_selection(self):
        self.assertEqual(classify_goal("继续上一步"), "control")
        self.assertEqual(classify_goal("重试失败任务"), "control")
        self.assertEqual(classify_goal("取消当前会话"), "control")
        self.assertIn("task.summary", [item["capability_id"] for item in select_capabilities_for_goal("继续上一步")])
        self.assertNotIn("task.retry", [item["capability_id"] for item in select_capabilities_for_goal("重试失败任务")])
        self.assertIn("task.cancel", [item["capability_id"] for item in select_capabilities_for_goal("取消当前会话")])

    def test_greeting_does_not_select_agent_batch(self):
        self.assertEqual(classify_goal("你好"), "conversation")
        self.assertNotIn("agent_batch.nl_command.submit", [item["capability_id"] for item in select_capabilities_for_goal("你好")])

    def test_task_cancel_requires_verified_host_authorization(self):
        call = self.runtime.execute("task.cancel", session_id=self.session_id, turn_id="turn-control")

        self.assertEqual(call["status"], "failed")
        self.assertEqual(call["error"]["type"], "Failure")
        self.assertEqual(call["error"]["code"], "host_authorization_missing")
        self.assertEqual(call["result"], {"session_id": self.session_id})

    def test_task_cancel_passes_authenticated_request_actor_to_canonical_runtime(self):
        bundle = self.service.create_session(
            source="runtime",
            entrypoint_type="runtime_projection",
            goal="cancel canonical run",
            project_key="demo_proj",
            compat_job_id="run-7",
        )
        session_id = bundle["session"]["session_id"]
        runtime = AgentControlToolRuntime(service=self.service, engine=SimpleNamespace())
        with (
            verified_host_authorization_channel(self._authorization(session_id)),
            patch.object(self.service, "cancel_run", return_value={"state": "CANCELLING"}) as cancel_run,
        ):
            call = runtime.task_cancel(turn_id="turn-control", session_id=session_id)

        self.assertEqual(call["status"], "completed")
        cancel_run.assert_called_once_with(
            "run-7",
            actor_id="authenticated-user-7",
            project_key="demo_proj",
            engine=runtime._engine,
        )

    def test_abort_readback_passes_authenticated_request_actor_to_runtime_projection(self):
        bundle = self.service.create_session(
            source="runtime",
            entrypoint_type="runtime_projection",
            goal="read canonical cancellation",
            project_key="demo_proj",
            compat_job_id="run-8",
        )
        session_id = bundle["session"]["session_id"]
        with (
            verified_host_authorization_channel(self._authorization(session_id)),
            patch.object(self.service, "read_run_cancellation", return_value=True) as read_cancel,
        ):
            requested = session_abort_requested(service=self.service, session_id=session_id)

        self.assertTrue(requested)
        read_cancel.assert_called_once_with(
            "run-8",
            project_key="demo_proj",
            actor_id="authenticated-user-7",
        )

    def test_legacy_continue_is_rejected_without_mutating_session(self):
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
        summary_call = self.runtime.execute("task.summary", session_id="missing-session", turn_id="turn-control")

        self.assertEqual(summary_call["status"], "failed")
        self.assertEqual(summary_call["error"]["code"], "session_not_found")
        self.assertEqual(summary_call["error"]["context"], {"session_id": "missing-session"})

    def test_task_cancel_preserves_missing_host_authorization_failure(self):
        call = self.runtime.execute("task.cancel", session_id="missing-session", turn_id="turn-control")

        self.assertEqual(call["status"], "failed")
        self.assertEqual(call["error"]["type"], "Failure")
        self.assertEqual(call["error"]["code"], "host_authorization_missing")
        self.assertEqual(call["result"], {"session_id": "missing-session"})

    def test_control_tool_exports_preserve_host_authorization_contract(self):
        definitions = {item["name"]: item for item in self.runtime.list_tool_definitions()}

        self.assertEqual(set(definitions), {"task.cancel", "task.summary"})
        self.assertEqual(definitions["task.cancel"]["approval_level"], "explicit_user_request")
        self.assertEqual(definitions["task.summary"]["approval_level"], "none")
        self.assertEqual(definitions["task.summary"]["concurrency_class"], "read_only")

    def test_functorial_projection_does_not_export_legacy_continue(self):
        with patch("app.services.agent_core.project_tools.list_registered_skills", return_value=[]):
            operator_ids = {item.operator_id for item in project_process_operators()}

        self.assertNotIn("task.continue", operator_ids)
        self.assertIn("task.summary", operator_ids)
if __name__ == "__main__":
    unittest.main()
