from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.contract

_TARGET_MODULE_COUNTS = {
    "agent_chat.py": 4,
    "agent_sessions.py": 16,
    "codex_auth.py": 5,
    "app.web_ui_routes": 1,
}

_JSON_ENVELOPE_PATHS = {
    ("GET", "/api/v1/agent-chat/capabilities"),
    ("POST", "/api/v1/agent-chat/turn"),
    ("POST", "/api/v1/agent-chat/approvals/{approval_id}/continue"),
    ("GET", "/api/v1/agent-sessions"),
    ("POST", "/api/v1/agent-sessions"),
    ("GET", "/api/v1/agent-sessions/{session_id}"),
    ("GET", "/api/v1/agent-sessions/{session_id}/tasks"),
    ("GET", "/api/v1/agent-sessions/{session_id}/events"),
    ("GET", "/api/v1/agent-sessions/{session_id}/artifacts"),
    ("GET", "/api/v1/agent-sessions/{session_id}/messages"),
    ("POST", "/api/v1/agent-sessions/{session_id}/messages"),
    ("GET", "/api/v1/agent-approvals"),
    ("POST", "/api/v1/agent-sessions/{session_id}/actions/retry-task"),
    ("POST", "/api/v1/agent-sessions/{session_id}/actions/cancel"),
    ("POST", "/api/v1/agent-sessions/{session_id}/actions/reclaim-expired"),
    ("POST", "/api/v1/agent-sessions/{session_id}/actions/coordinator-pass"),
    ("POST", "/api/v1/agent-sessions/{session_id}/actions/request-approval"),
    ("POST", "/api/v1/agent-approvals/{approval_id}/resolve"),
    ("GET", "/api/v1/codex-auth/status"),
    ("POST", "/api/v1/codex-auth/logout"),
    ("POST", "/api/v1/codex-auth/cli/bootstrap"),
}

_NON_JSON_OR_REDIRECT_PATHS = {
    ("POST", "/api/v1/agent-chat/turn/stream"),
    ("GET", "/api/v1/agent-sessions/{session_id}/stream"),
    ("GET", "/api/v1/codex-auth/login"),
    ("GET", "/api/v1/codex-auth/callback"),
}

try:
    from app.main import app as backend_app
    from scripts.generate_api_schema_inventory import build_inventory

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class ApiSchemaAuthAgentWebContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"auth/agent/web schema tests require backend dependencies: {_IMPORT_ERROR}")

    def _operations(self) -> list[dict]:
        return build_inventory(backend_app)["operations"]

    def test_target_modules_keep_expected_route_coverage(self):
        counts = {module: 0 for module in _TARGET_MODULE_COUNTS}
        for operation in self._operations():
            module = operation["source_module"]
            if module in counts:
                counts[module] += 1

        self.assertEqual(counts, _TARGET_MODULE_COUNTS)

    def test_target_routes_have_no_untyped_openapi_200_schema(self):
        target_modules = set(_TARGET_MODULE_COUNTS)
        untyped = [
            f"{operation['method']} {operation['path']} ({operation['source_module']})"
            for operation in self._operations()
            if operation["source_module"] in target_modules and operation["response_200_schema"] == "untyped"
        ]

        self.assertEqual(untyped, [])

    def test_json_agent_and_codex_auth_routes_advertise_envelope_schema(self):
        operations = {(operation["method"], operation["path"]): operation for operation in self._operations()}
        for key in _JSON_ENVELOPE_PATHS:
            operation = operations[key]
            self.assertIn("ApiEnvelope", operation["response_model"], msg=operation)
            self.assertNotEqual(operation["response_200_schema"], "untyped", msg=operation)

    def test_stream_redirect_and_map_routes_are_explicitly_typed(self):
        operations = {(operation["method"], operation["path"]): operation for operation in self._operations()}
        for key in _NON_JSON_OR_REDIRECT_PATHS:
            operation = operations[key]
            self.assertNotEqual(operation["response_200_schema"], "untyped", msg=operation)

        usa_map = operations[("GET", "/api/v1/maps/usa")]
        self.assertEqual(usa_map["source_module"], "app.web_ui_routes")
        self.assertEqual(usa_map["response_200_schema"], "object")


if __name__ == "__main__":
    unittest.main()
