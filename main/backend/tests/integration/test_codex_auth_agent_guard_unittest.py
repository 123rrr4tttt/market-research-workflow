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


class CodexAuthAgentGuardIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"codex auth integration tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(backend_app)
        cls.headers = {"X-Project-Key": "demo_proj", "X-Request-Id": "codex-auth-it"}

    def test_protected_path_allows_request_when_auth_disabled(self):
        with patch("app.main.settings.codex_auth_enabled", False):
            response = self.client.post(
                "/api/v1/agent-batch/rule-sets/validate",
                json={"rule_set": {"blocked_channels": ["search.market"]}},
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("status"), "ok")

    def test_protected_path_rejects_missing_token_when_enabled(self):
        with (
            patch("app.main.settings.codex_auth_enabled", True),
            patch("app.main.settings.codex_auth_tokens", "token-1"),
            patch("app.main.has_valid_token_sink", return_value=False),
        ):
            response = self.client.post(
                "/api/v1/agent-batch/rule-sets/validate",
                json={"rule_set": {"blocked_channels": ["search.market"]}},
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 401)
        body = response.json()
        self.assertEqual(body.get("status"), "error")
        self.assertEqual(((body.get("error") or {}).get("details") or {}).get("reason_code"), "missing_token")

    def test_protected_path_rejects_missing_oauth_session_when_only_oauth_enabled(self):
        with (
            patch("app.main.settings.codex_auth_enabled", True),
            patch("app.main.settings.codex_auth_tokens", ""),
            patch("app.main.settings.codex_oauth_enabled", True),
            patch("app.main.has_valid_token_sink", return_value=False),
        ):
            response = self.client.post(
                "/api/v1/agent-batch/rule-sets/validate",
                json={"rule_set": {"blocked_channels": ["search.market"]}},
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 401)
        body = response.json()
        self.assertEqual(((body.get("error") or {}).get("details") or {}).get("reason_code"), "missing_oauth_session")

    def test_protected_path_accepts_valid_token_sink(self):
        with (
            patch("app.main.settings.codex_auth_enabled", True),
            patch("app.main.settings.codex_auth_tokens", ""),
            patch("app.main.settings.codex_oauth_enabled", True),
            patch("app.main.has_valid_token_sink", return_value=True),
        ):
            response = self.client.post(
                "/api/v1/agent-batch/rule-sets/validate",
                json={"rule_set": {"blocked_channels": ["search.market"]}},
                headers=self.headers,
            )
        self.assertEqual(response.status_code, 200)

    def test_protected_path_accepts_bearer_and_x_codex_auth(self):
        with (
            patch("app.main.settings.codex_auth_enabled", True),
            patch("app.main.settings.codex_auth_tokens", "token-1,token-2"),
        ):
            bearer_resp = self.client.post(
                "/api/v1/agent-batch/rule-sets/validate",
                json={"rule_set": {"blocked_channels": ["search.market"]}},
                headers={**self.headers, "Authorization": "Bearer token-1"},
            )
            header_resp = self.client.post(
                "/api/v1/agent-batch/rule-sets/validate",
                json={"rule_set": {"blocked_channels": ["search.market"]}},
                headers={**self.headers, "X-Codex-Auth": "token-2"},
            )

        self.assertEqual(bearer_resp.status_code, 200)
        self.assertEqual(header_resp.status_code, 200)

    def test_unprotected_path_health_not_blocked(self):
        with (
            patch("app.main.settings.codex_auth_enabled", True),
            patch("app.main.settings.codex_auth_tokens", "token-1"),
        ):
            response = self.client.get("/api/v1/health", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("status"), "ok")


if __name__ == "__main__":
    unittest.main()
