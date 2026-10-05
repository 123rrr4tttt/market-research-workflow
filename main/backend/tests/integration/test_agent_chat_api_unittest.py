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

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class RetiredAgentChatApiIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(
                f"agent chat integration tests require backend dependencies: {_IMPORT_ERROR}"
            )
        cls.client = TestClient(backend_app)

    def test_all_retired_agent_chat_routes_are_absent(self):
        retired_routes = [
            ("GET", "/api/v1/agent-chat/capabilities"),
            ("GET", "/api/v1/agent-chat/cell"),
            ("POST", "/api/v1/agent-chat/turn"),
            ("POST", "/api/v1/agent-chat/turn/stream"),
            ("POST", "/api/v1/agent-chat/approvals/approval-1/continue"),
        ]

        with (
            patch(
                "app.main._get_active_project_key_fallback",
                return_value=None,
            ),
            patch(
                "app.services.agent_runtime.tool_pool.AgentToolPoolAssembler"
            ) as tool_pool_assembler,
            patch(
                "app.services.llm.codex_app_server.get_persistent_codex_core"
            ) as codex_core_factory,
            patch(
                "app.api.agent_sessions.get_agent_session_service"
            ) as session_service_factory,
            patch(
                "app.api.agent_cell.get_agent_session_service"
            ) as cell_session_factory,
            patch("app.api.agent_cell.select_active_macro_identity") as select_identity,
            patch("app.api.agent_cell.resolve_macro_environment") as resolve_environment,
            patch(
                "app.api.agent_cell.build_project_core_tool_registry"
            ) as build_registry,
        ):
            for method, path in retired_routes:
                with self.subTest(method=method, path=path):
                    response = self.client.request(
                        method,
                        path,
                        json={} if method == "POST" else None,
                    )

                    self.assertEqual(response.status_code, 404)

            tool_pool_assembler.assert_not_called()
            codex_core_factory.assert_not_called()
            session_service_factory.assert_not_called()
            cell_session_factory.assert_not_called()
            select_identity.assert_not_called()
            resolve_environment.assert_not_called()
            build_registry.assert_not_called()

        paths = backend_app.openapi()["paths"]
        self.assertFalse(any("/agent-chat/" in path for path in paths))
        self.assertIn("/api/v1/agent-cell", paths)
        self.assertIn("get", paths["/api/v1/agent-cell"])


if __name__ == "__main__":
    unittest.main()
