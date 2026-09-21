from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.integration

try:
    from fastapi.testclient import TestClient

    from app.contracts.errors import ErrorCode
    from app.main import app as backend_app
    from app.services.agent_sessions.service import AgentSessionService
    from app.services.agent_sessions.store import InMemoryAgentSessionStore

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class AgentSessionsApiIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"agent sessions integration tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(backend_app)

    def test_agent_approvals_list_route(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        service.create_session(source="user", entrypoint_type="chat", goal="Approval list", project_key="demo_proj")
        service.create_or_update_approval(
            approval_id="approval-1",
            binding_payload={"argv": ["cmd"], "cwd": "/workspace", "env": {}},
            requester_session_id=service.list_sessions(limit=1)[0]["session_id"],
            requester_task_id="task-1",
            requester_actor="user_facing_assistant",
            expires_at=None,
            status="pending",
            audit_log=[{"action": "requested"}],
        )
        session_id = service.list_sessions(limit=1)[0]["session_id"]
        with patch("app.api.agent_sessions.get_agent_session_service", return_value=service):
            response = self.client.get(f"/api/v1/agent-approvals?session_id={session_id}")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["data"]["items"][0]["approval_id"], "approval-1")

    def test_agent_session_stream_route(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="chat",
            goal="Stream test",
        )
        session_id = bundle["session"]["session_id"]
        with patch("app.api.agent_sessions.get_agent_session_service", return_value=service):
            response = self.client.get(
                f"/api/v1/agent-sessions/{session_id}/stream?since_seq=0&poll_seconds=0.2&max_seconds=1"
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers.get("content-type", ""))
        self.assertIn("event: session.created", response.text)

    def test_agent_session_messages_and_coordinator_routes(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(source="user", entrypoint_type="chat", goal="Coordinator API")
        session_id = bundle["session"]["session_id"]
        research_task = bundle["tasks"][0]["task_id"]
        service.release_task(session_id, research_task, status="completed", result_summary="Research done")

        with patch("app.api.agent_sessions.get_agent_session_service", return_value=service):
            message_response = self.client.post(
                f"/api/v1/agent-sessions/{session_id}/messages",
                json={"role": "assistant", "actor": "tester", "content": "hello"},
            )
            coordinator_response = self.client.post(f"/api/v1/agent-sessions/{session_id}/actions/coordinator-pass")

        self.assertEqual(message_response.status_code, 200)
        self.assertEqual(coordinator_response.status_code, 200)
        coordinator_body = coordinator_response.json()
        self.assertEqual(coordinator_body["status"], "ok")
        self.assertTrue(coordinator_body["data"]["messages"])

    def test_agent_session_request_approval_route(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(source="user", entrypoint_type="chat", goal="Approval API")
        session_id = bundle["session"]["session_id"]
        task_id = bundle["tasks"][2]["task_id"]

        with patch("app.api.agent_sessions.get_agent_session_service", return_value=service):
            response = self.client.post(
                f"/api/v1/agent-sessions/{session_id}/actions/request-approval",
                json={
                    "task_id": task_id,
                    "requester_actor": "ops_panel",
                    "binding_payload": {"argv": ["deploy"]},
                    "metadata": {"force_approval": True},
                },
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["data"]["requester_task_id"], task_id)

    def test_create_agent_session_invalid_input_returns_structured_error(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        with patch("app.api.agent_sessions.get_agent_session_service", return_value=service):
            with patch.object(service, "create_session", side_effect=ValueError("invalid session payload")):
                response = self.client.post(
                    "/api/v1/agent-sessions",
                    json={"source": "user", "entrypoint_type": "chat", "goal": "Create session"},
                )

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertIn("invalid session payload", body["detail"]["error"]["message"])

    def test_retry_agent_session_task_invalid_input_returns_structured_error(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(source="user", entrypoint_type="chat", goal="Retry API")
        session_id = bundle["session"]["session_id"]
        task_id = bundle["tasks"][0]["task_id"]

        with patch("app.api.agent_sessions.get_agent_session_service", return_value=service):
            with patch.object(service, "retry_task", side_effect=ValueError("task cannot be retried")):
                response = self.client.post(
                    f"/api/v1/agent-sessions/{session_id}/actions/retry-task",
                    json={"task_id": task_id},
                )

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertIn("task cannot be retried", body["detail"]["error"]["message"])

    def test_retry_agent_session_task_repeated_call_returns_already_pending(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(source="user", entrypoint_type="chat", goal="Retry API idempotency")
        session_id = bundle["session"]["session_id"]
        task_id = bundle["tasks"][0]["task_id"]
        service.release_task(session_id, task_id, status="completed", result_summary="ok")

        with patch("app.api.agent_sessions.get_agent_session_service", return_value=service):
            first_response = self.client.post(
                f"/api/v1/agent-sessions/{session_id}/actions/retry-task",
                json={"task_id": task_id},
            )
            event_count = len(service.list_events(session_id))
            second_response = self.client.post(
                f"/api/v1/agent-sessions/{session_id}/actions/retry-task",
                json={"task_id": task_id},
            )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(first_response.json()["data"]["action_status"], "retried")
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(second_response.json()["data"]["action_status"], "already_pending")
        self.assertEqual(len(service.list_events(session_id)), event_count)

    def test_export_agent_session_failure_package_route_by_run_id(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="chat",
            goal="Failure package API",
            project_key="proj-api",
            task_blueprints=[
                {
                    "task_id": "task-api-failed",
                    "subject": "Dispatch",
                    "task_type": "implementation",
                    "phase": "implementation",
                    "metadata": {"workflow_run_id": "run-api-1", "trace_id": "trace-api-1"},
                }
            ],
        )
        session_id = bundle["session"]["session_id"]
        service.release_task(
            session_id,
            "task-api-failed",
            status="failed",
            result_summary="worker crashed",
            result_payload={"error": "worker crashed"},
        )

        with patch("app.api.agent_sessions.get_agent_session_service", return_value=service):
            response = self.client.get(f"/api/v1/agent-sessions/{session_id}/failure-package?run_id=run-api-1")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        package = body["data"]["failure_package"]
        self.assertEqual(package["session_id"], session_id)
        self.assertEqual(package["run_id"], "run-api-1")
        self.assertEqual(package["task_id"], "task-api-failed")
        self.assertEqual(package["project_key"], "proj-api")
        self.assertEqual(package["trace_id"], "trace-api-1")
        self.assertEqual(package["export_schema_version"], "agent_failure_package.v1")
        self.assertEqual(body["data"]["export_status"], "ok")

    def test_export_agent_session_failure_package_non_failed_returns_empty_package(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(source="user", entrypoint_type="chat", goal="Failure package empty")
        session_id = bundle["session"]["session_id"]
        task_id = bundle["tasks"][0]["task_id"]

        with patch("app.api.agent_sessions.get_agent_session_service", return_value=service):
            response = self.client.get(f"/api/v1/agent-sessions/{session_id}/failure-package?task_id={task_id}")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["data"]["export_status"], "not_failed")
        self.assertEqual(body["data"]["reason_code"], "task_not_failed")
        self.assertIsNone(body["data"]["failure_package"])
        self.assertEqual(body["data"]["empty_package"]["task_id"], task_id)

    def test_export_agent_session_failure_package_missing_task_returns_structured_error(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(source="user", entrypoint_type="chat", goal="Failure package missing")
        session_id = bundle["session"]["session_id"]

        with patch("app.api.agent_sessions.get_agent_session_service", return_value=service):
            response = self.client.get(f"/api/v1/agent-sessions/{session_id}/failure-package?task_id=missing-task")

        self.assertEqual(response.status_code, 404)
        body = response.json()
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.NOT_FOUND.value)
        self.assertEqual(body["detail"]["error"]["message"], "task not found")

    def test_create_agent_session_runtime_error_returns_internal_error(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        with patch("app.api.agent_sessions.get_agent_session_service", return_value=service):
            with patch.object(service, "create_session", side_effect=RuntimeError("database timeout")):
                response = self.client.post(
                    "/api/v1/agent-sessions",
                    json={"source": "user", "entrypoint_type": "chat", "goal": "Create session"},
                )

        self.assertEqual(response.status_code, 502)
        body = response.json()
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.UPSTREAM_ERROR.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.UPSTREAM_ERROR.value)

    def test_retry_agent_session_task_runtime_error_returns_internal_error(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(source="user", entrypoint_type="chat", goal="Retry API")
        session_id = bundle["session"]["session_id"]
        task_id = bundle["tasks"][0]["task_id"]

        with patch("app.api.agent_sessions.get_agent_session_service", return_value=service):
            with patch.object(service, "retry_task", side_effect=RuntimeError("database timeout")):
                response = self.client.post(
                    f"/api/v1/agent-sessions/{session_id}/actions/retry-task",
                    json={"task_id": task_id},
                )

        self.assertEqual(response.status_code, 502)
        body = response.json()
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.UPSTREAM_ERROR.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.UPSTREAM_ERROR.value)

    def test_get_agent_session_not_found_returns_structured_error(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        with patch("app.api.agent_sessions.get_agent_session_service", return_value=service):
            response = self.client.get("/api/v1/agent-sessions/missing-session")

        self.assertEqual(response.status_code, 404)
        body = response.json()
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.NOT_FOUND.value)
        self.assertEqual(body["detail"]["error"]["message"], "session not found")

    def test_resolve_approval_not_found_returns_structured_error(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        with patch("app.api.agent_sessions.get_agent_session_service", return_value=service):
            response = self.client.post(
                "/api/v1/agent-approvals/missing-approval/resolve",
                json={"approved": True, "approved_by": "user"},
            )

        self.assertEqual(response.status_code, 404)
        body = response.json()
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.NOT_FOUND.value)
        self.assertEqual(body["detail"]["error"]["message"], "approval not found")

    def test_resolve_approval_repeated_approve_returns_already_final(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(source="user", entrypoint_type="chat", goal="Approval API idempotency")
        session_id = bundle["session"]["session_id"]
        task_id = bundle["tasks"][0]["task_id"]
        service.create_or_update_approval(
            approval_id="approval-api-idem",
            binding_payload={"argv": ["cmd"], "cwd": "/workspace", "env": {}},
            requester_session_id=session_id,
            requester_task_id=task_id,
            requester_actor="user_facing_assistant",
            expires_at=None,
            status="pending",
            audit_log=[{"action": "requested"}],
        )

        with patch("app.api.agent_sessions.get_agent_session_service", return_value=service):
            first_response = self.client.post(
                "/api/v1/agent-approvals/approval-api-idem/resolve",
                json={"approved": True, "approved_by": "user"},
            )
            event_count = len(service.list_events(session_id))
            second_response = self.client.post(
                "/api/v1/agent-approvals/approval-api-idem/resolve",
                json={"approved": True, "approved_by": "user-2"},
            )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(first_response.json()["data"]["action_status"], "resolved")
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(second_response.json()["data"]["status"], "approved")
        self.assertEqual(second_response.json()["data"]["action_status"], "already_final")
        self.assertEqual(len(service.list_events(session_id)), event_count)

    def test_resolve_approval_conflicting_final_decision_returns_conflict(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(source="user", entrypoint_type="chat", goal="Approval API conflict")
        session_id = bundle["session"]["session_id"]
        task_id = bundle["tasks"][0]["task_id"]
        service.create_or_update_approval(
            approval_id="approval-api-conflict",
            binding_payload={"argv": ["cmd"], "cwd": "/workspace", "env": {}},
            requester_session_id=session_id,
            requester_task_id=task_id,
            requester_actor="user_facing_assistant",
            expires_at=None,
            status="pending",
            audit_log=[{"action": "requested"}],
        )
        service.resolve_approval("approval-api-conflict", approved_by="user", approved=True)

        with patch("app.api.agent_sessions.get_agent_session_service", return_value=service):
            response = self.client.post(
                "/api/v1/agent-approvals/approval-api-conflict/resolve",
                json={"approved": False, "approved_by": "user"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["data"]["status"], "approved")
        self.assertEqual(body["data"]["action_status"], "conflict")
        self.assertEqual(body["data"]["requested_status"], "failed")


if __name__ == "__main__":
    unittest.main()
