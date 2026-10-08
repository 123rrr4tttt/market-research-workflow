from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import Mock, patch

import pytest

from app.services.agent_runtime.capability_registry import classify_goal, select_capabilities_for_goal
from sqlalchemy.engine import Engine

from app.services.agent_runtime.control_tools import control_project_tool_sources, task_cancel
from app.services.agent_core.contracts import AgentCoreRequest, CoreToolCall
from app.services.agent_core.registry import CoreToolRegistry
from app.services.agent_core.tool_contribution import register_project_tool_contributions
from app.services.agent_core.host_authorization import (
    TrustedHostContext,
    VerifiedHostAuthorization,
    verified_host_authorization_channel,
    canonical_arguments_sha256,
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
        self.registry = CoreToolRegistry()
        self.assertIsNone(register_project_tool_contributions(
            self.registry, control_project_tool_sources(service=self.service),
        ))

    def _invoke(self, name: str, *, session_id: str, turn_id: str):
        call = CoreToolCall(tool_name=name, call_id="call-control")
        request = AgentCoreRequest(message="control", session_id=session_id, turn_id=turn_id)
        if name == "task.cancel":
            spec = self.registry.get(name)
            assert spec is not None
            return task_cancel(call, request, service=self.service)
        return self.registry.execute_tool(tool_call=call, request=request, emit=lambda _event: None)

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
        call = self._invoke("task.cancel", session_id=self.session_id, turn_id="turn-control")

        self.assertEqual(call.status, "failed")
        self.assertEqual(call.error["type"], "Failure")
        self.assertEqual(call.error["code"], "host_authorization_missing")
        self.assertEqual(call.structured_content["result"], {"session_id": self.session_id})

    def test_task_cancel_passes_authenticated_request_actor_to_canonical_runtime(self):
        bundle = self.service.create_session(
            source="runtime",
            entrypoint_type="runtime_projection",
            goal="cancel canonical run",
            project_key="demo_proj",
            compat_job_id="run-7",
        )
        session_id = bundle["session"]["session_id"]
        runtime_engine = Mock(spec=Engine)
        with (
            verified_host_authorization_channel(self._authorization(session_id)),
            patch.object(self.service, "cancel_run", return_value={"state": "CANCELLING"}) as cancel_run,
        ):
            spec = self.registry.get("task.cancel")
            assert spec is not None
            call = task_cancel(
                CoreToolCall(tool_name="task.cancel", call_id="call-control"),
                AgentCoreRequest(message="cancel", session_id=session_id, turn_id="turn-control"),
                service=self.service, engine=runtime_engine,
            )

        self.assertEqual(call.status, "completed")
        cancel_run.assert_called_once_with(
            "run-7",
            actor_id="authenticated-user-7",
            project_key="demo_proj",
            engine=runtime_engine,
        )

    def test_task_cancel_real_registry_keeps_verified_target_and_actor(self):
        bundle = self.service.create_session(
            source="runtime", entrypoint_type="runtime_projection", goal="cancel canonical run",
            project_key="demo_proj", compat_job_id="run-registry",
        )
        session_id = bundle["session"]["session_id"]
        call = CoreToolCall(tool_name="task.cancel", call_id="call-7")
        request = AgentCoreRequest(message="cancel", session_id=session_id, project_key="demo_proj", turn_id="turn-control")
        authorization = replace(self._authorization(session_id), arguments_sha256=canonical_arguments_sha256({}))
        runtime_engine = Mock(spec=Engine)
        with (
            patch("app.services.agent_runtime.control_tools._runtime_engine", return_value=runtime_engine),
            patch.object(self.service, "cancel_run", return_value={"state": "CANCELLING"}) as cancel_run,
        ):
            result = self.registry.execute_tool(
                tool_call=call, request=request, emit=lambda _event: None,
                trusted_context=authorization.context, host_authorization=authorization,
            )
        self.assertEqual(result.status, "completed")
        cancel_run.assert_called_once_with(
            "run-registry", actor_id="authenticated-user-7", project_key="demo_proj", engine=runtime_engine,
        )

    def test_task_cancel_rejects_other_target_without_canonical_write(self):
        with (
            verified_host_authorization_channel(self._authorization("other-session")),
            patch.object(self.service, "cancel_run") as cancel_run,
        ):
            result = self._invoke("task.cancel", session_id=self.session_id, turn_id="turn-control")
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error["code"], "host_context_session_mismatch")
        cancel_run.assert_not_called()

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

        call = self._invoke("task.continue", session_id=self.session_id, turn_id="turn-control")

        self.assertEqual(call.status, "failed")
        self.assertEqual(call.error["code"], "tool_not_registered")
        self.assertEqual(self.service.get_session(self.session_id), before)

    def test_task_summary_reads_session_owner_projection(self):
        call = self._invoke("task.summary", session_id=self.session_id, turn_id="turn-control")

        self.assertEqual(call.status, "completed")
        summary = call.structured_content["result"]["summary"]
        self.assertEqual(summary["session_id"], self.session_id)
        self.assertEqual(summary["status"], self.service.get_session(self.session_id)["status"])
        self.assertEqual(summary["task_counts"], {"completed": 1, "failed": 1})

    def test_failure_results_are_preserved(self):
        summary_call = self._invoke("task.summary", session_id="missing-session", turn_id="turn-control")

        self.assertEqual(summary_call.status, "failed")
        self.assertEqual(summary_call.error["code"], "session_not_found")
        self.assertEqual(summary_call.error["context"], {"session_id": "missing-session"})

    def test_summary_exception_is_preserved_by_registry(self):
        with patch.object(self.service, "get_session_summary", side_effect=OSError("summary unavailable")):
            result = self._invoke("task.summary", session_id=self.session_id, turn_id="turn-control")
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error, {"type": "OSError", "message": "summary unavailable"})
        self.assertEqual(result.structured_content["result"], {"session_id": self.session_id})

    def test_task_cancel_preserves_missing_host_authorization_failure(self):
        call = self._invoke("task.cancel", session_id="missing-session", turn_id="turn-control")

        self.assertEqual(call.status, "failed")
        self.assertEqual(call.error["type"], "Failure")
        self.assertEqual(call.error["code"], "host_authorization_missing")
        self.assertEqual(call.structured_content["result"], {"session_id": "missing-session"})

    def test_control_tool_exports_preserve_host_authorization_contract(self):
        definitions = {
            spec.name: spec.metadata["legacy_tool_definition"] for spec in self.registry.list_specs()
        }

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
