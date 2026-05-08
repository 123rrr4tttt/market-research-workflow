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
    from app.services.codex_oauth import CodexSession

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class CodexOauthBrowserFlowIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"codex oauth integration tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(backend_app)
        cls.headers = {"X-Project-Key": "demo_proj", "X-Request-Id": "codex-oauth-it"}

    def test_protected_path_accepts_oauth_cookie_session(self):
        with (
            patch("app.main.settings.codex_auth_enabled", True),
            patch("app.main.settings.codex_auth_tokens", ""),
            patch("app.main.get_session", return_value=CodexSession(
                session_id="sid-1",
                access_token="at",
                token_type="Bearer",
                scope="openid",
                created_at=100,
                expires_at=999999,
            )),
        ):
            resp = self.client.post(
                "/api/v1/agent-batch/rule-sets/validate",
                json={"rule_set": {"blocked_channels": ["search.market"]}},
                headers=self.headers,
                cookies={"codex_session": "sid-1"},
            )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get("status"), "ok")

    def test_login_redirects_to_oauth_provider(self):
        with (
            patch("app.api.codex_auth.codex_oauth_enabled", return_value=True),
            patch("app.api.codex_auth.build_authorize_url", return_value="https://auth.example/authorize?state=abc"),
        ):
            resp = self.client.get("/api/v1/codex-auth/login", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.headers.get("location"), "https://auth.example/authorize?state=abc")

    def test_login_returns_error_envelope_when_oauth_config_missing(self):
        with (
            patch("app.api.codex_auth.codex_oauth_enabled", return_value=True),
            patch("app.api.codex_auth.build_authorize_url", side_effect=ValueError("missing state secret")),
        ):
            resp = self.client.get("/api/v1/codex-auth/login", follow_redirects=False)

        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["error"]["code"], "INVALID_INPUT")
        self.assertEqual(body["detail"]["error"]["code"], "INVALID_INPUT")
        self.assertEqual(resp.headers.get("x-error-code"), "INVALID_INPUT")

    def test_callback_sets_cookie_after_success_exchange(self):
        with (
            patch("app.api.codex_auth.codex_oauth_enabled", return_value=True),
            patch(
                "app.api.codex_auth.exchange_code_to_session",
                return_value=(
                    CodexSession(
                        session_id="sid-2",
                        access_token="at",
                        token_type="Bearer",
                        scope="openid",
                        created_at=100,
                        expires_at=1000,
                    ),
                    "/workspace",
                ),
            ),
        ):
            resp = self.client.get(
                "/api/v1/codex-auth/callback?code=ok&state=st",
                follow_redirects=False,
            )

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.headers.get("location"), "/workspace")
        self.assertIn("codex_session=sid-2", str(resp.headers.get("set-cookie") or ""))

    def test_status_and_logout_with_cookie(self):
        with patch(
            "app.api.codex_auth.get_session",
            return_value=CodexSession(
                session_id="sid-3",
                access_token="at",
                token_type="Bearer",
                scope="openid",
                created_at=100,
                expires_at=200,
            ),
        ):
            status_resp = self.client.get(
                "/api/v1/codex-auth/status",
                headers=self.headers,
                cookies={"codex_session": "sid-3"},
            )
        self.assertEqual(status_resp.status_code, 200)
        self.assertTrue((status_resp.json().get("data") or {}).get("authenticated"))

        with patch("app.api.codex_auth.revoke_session"):
            logout_resp = self.client.post(
                "/api/v1/codex-auth/logout",
                headers=self.headers,
                cookies={"codex_session": "sid-3"},
            )
        self.assertEqual(logout_resp.status_code, 200)
        self.assertEqual(logout_resp.json().get("status"), "ok")


if __name__ == "__main__":
    unittest.main()
