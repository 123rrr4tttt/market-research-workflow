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


if __name__ == "__main__":
    unittest.main()
