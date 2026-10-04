from __future__ import annotations

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
            raise unittest.SkipTest(
                f"agent chat integration tests require backend dependencies: {_IMPORT_ERROR}"
            )
        cls.client = TestClient(backend_app)

    def test_retired_runtime_variants_return_410_before_project_fallback(self):
        for runtime_variant in ("agent_runtime_v2", "legacy_batch", "agent_core_v3"):
            with self.subTest(runtime_variant=runtime_variant), patch(
                "app.main._get_active_project_key_fallback"
            ) as active_project_fallback:
                response = self.client.post(
                    "/api/v1/agent-chat/turn",
                    json={
                        "message": "collect market updates",
                        "project_key": "demo_proj",
                        "runtime_variant": runtime_variant,
                    },
                )

            self.assertEqual(response.status_code, 410)
            self.assertEqual(
                response.json()["detail"]["error"]["code"], "agent_runtime_retired"
            )
            self.assertEqual(
                response.json()["detail"]["error"]["details"]["runtime_variant"],
                runtime_variant,
            )
            active_project_fallback.assert_not_called()

    def test_retired_stream_variant_returns_410(self):
        response = self.client.post(
            "/api/v1/agent-chat/turn/stream",
            json={
                "message": "what tools are available",
                "project_key": "demo_proj",
                "runtime_variant": "agent_core_v3",
            },
        )

        self.assertEqual(response.status_code, 410)
        self.assertEqual(
            response.json()["detail"]["error"]["code"], "agent_runtime_retired"
        )

    def test_runtime_variant_is_required(self):
        response = self.client.post(
            "/api/v1/agent-chat/turn",
            json={"message": "hello", "project_key": "demo_proj"},
        )

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["error"]["code"], "INVALID_INPUT")
        self.assertIn("runtime_variant is required", body["error"]["message"])

    def test_reserved_project_key_is_rejected_for_new_native_turn(self):
        with patch(
            "app.api.agent_chat._lookup_active_agent_project_key",
            return_value="demo_proj",
        ) as active_project:
            response = self.client.post(
                "/api/v1/agent-chat/turn",
                json={
                    "message": "read project context",
                    "project_key": "default",
                    "runtime_variant": "agent_macro_native",
                },
            )

        self.assertEqual(response.status_code, 400)
        error = response.json()["detail"]["error"]
        self.assertEqual(error["code"], "INVALID_INPUT")
        self.assertIn("project_key is required", error["message"])
        active_project.assert_not_called()

    def test_native_turn_rejects_retired_control_options_even_when_false(self):
        retired_options = (
            "dry_run",
            "enable_bounded_retry",
            "enable_limited_branching",
            "enable_model_tool_loop",
            "require_high_risk_approval",
        )

        for option in retired_options:
            with self.subTest(option=option), patch(
                "app.api.agent_chat._run_agent_macro_native_turn",
                return_value={"contract_version": "agent_macro.native_turn.v1"},
            ) as run_turn:
                response = self.client.post(
                    "/api/v1/agent-chat/turn",
                    json={
                        "message": "read project context",
                        "project_key": "demo_proj",
                        "runtime_variant": "agent_macro_native",
                        option: False,
                    },
                )

            self.assertEqual(response.status_code, 400)
            error = response.json()["detail"]["error"]
            self.assertEqual(error["code"], "unsupported_agent_chat_option")
            self.assertIn(option, error["message"])
            self.assertEqual(error["details"]["options"], [option])
            run_turn.assert_not_called()

    def test_native_stream_rejects_retired_control_options_before_sse(self):
        with patch("app.api.agent_chat._run_agent_macro_native_turn") as run_turn:
            response = self.client.post(
                "/api/v1/agent-chat/turn/stream",
                json={
                    "message": "read project context",
                    "project_key": "demo_proj",
                    "runtime_variant": "agent_macro_native",
                    "require_high_risk_approval": False,
                },
            )

        self.assertEqual(response.status_code, 400)
        error = response.json()["detail"]["error"]
        self.assertEqual(error["code"], "unsupported_agent_chat_option")
        self.assertEqual(error["details"]["options"], ["require_high_risk_approval"])
        run_turn.assert_not_called()

    def test_native_turn_rejects_cross_project_session_reuse(self):
        service = Mock()
        service.get_session.return_value = {
            "session_id": "session-a",
            "project_key": "project_a",
        }

        with (
            patch("app.api.agent_chat.get_agent_session_service", return_value=service),
            patch(
                "app.services.llm.codex_app_server.get_persistent_codex_core"
            ) as core_factory,
        ):
            response = self.client.post(
                "/api/v1/agent-chat/turn",
                json={
                    "message": "continue",
                    "project_key": "project_b",
                    "session_id": "session-a",
                    "runtime_variant": "agent_macro_native",
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("different project", str(response.json()))
        core_factory.assert_not_called()

    def test_native_stream_wraps_the_native_turn_result(self):
        result = {
            "runtime_variant": "agent_macro_native",
            "session": {"session_id": "session-native"},
            "events": [],
            "final_answer": "native answer",
        }

        with patch(
            "app.api.agent_chat._run_agent_chat_turn_payload",
            return_value=result,
        ) as run_turn:
            response = self.client.post(
                "/api/v1/agent-chat/turn/stream",
                json={
                    "message": "read a retrieval run",
                    "project_key": "demo_proj",
                    "runtime_variant": "agent_macro_native",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("event: interactive_agent.stream_started", response.text)
        self.assertIn("event: interactive_agent.final_answer", response.text)
        self.assertIn("native answer", response.text)
        run_turn.assert_called_once()

    def test_native_stream_contract_documents_events_after_turn_completion(self):
        operation = backend_app.openapi()["paths"]["/api/v1/agent-chat/turn/stream"]["post"]
        description = operation["responses"]["200"]["description"]

        self.assertIn("start event is sent first", description)
        self.assertIn("after the native turn completes", description)

    def test_agent_chat_capabilities_route_includes_platform_metadata(self):
        response = self.client.get("/api/v1/agent-chat/capabilities")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("items", body["data"])
        self.assertIn("tool_pool", body["data"])
        self.assertGreaterEqual(body["data"]["tool_pool"]["counts"]["core"], 1)
        self.assertEqual(
            set(body["data"]["feature_flags"]),
            {"agent_stream_enabled", "agent_batch_as_tool_enabled"},
        )
        self.assertNotIn(
            "agent_batch.nl_command.submit",
            [item["capability_id"] for item in body["data"]["items"]],
        )

    def test_agent_chat_capabilities_route_marks_read_and_governed_tools(self):
        response = self.client.get(
            "/api/v1/agent-chat/capabilities?project_key=demo_proj"
        )

        self.assertEqual(response.status_code, 200)
        tools = {
            item["capability_id"]: item
            for item in response.json()["data"]["tool_pool"]["tools"]
        }
        project_summary = tools["project.summary.read"]
        self.assertEqual(project_summary["tool_group"], "core")
        self.assertTrue(project_summary["implemented"])
        self.assertEqual(project_summary["permission_state"], "available")

        source_run = tools["ingest.source_library.run"]
        self.assertEqual(source_run["tool_group"], "deferred")
        self.assertTrue(source_run["deferred"])
        self.assertEqual(source_run["approval_level"], "high")
        self.assertEqual(source_run["permission_state"], "available")

    def test_agent_chat_turn_invalid_message_returns_structured_error(self):
        response = self.client.post(
            "/api/v1/agent-chat/turn",
            json={"message": "", "project_key": "demo_proj"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["status"], "error")

    def test_agent_chat_approval_continue_route_remains_retired(self):
        response = self.client.post(
            "/api/v1/agent-chat/approvals/approval-1/continue",
            json={"approved_by": "unit-test"},
        )

        self.assertEqual(response.status_code, 410)
        self.assertEqual(
            response.json()["detail"]["error"]["code"], "agent_runtime_retired"
        )


if __name__ == "__main__":
    unittest.main()
