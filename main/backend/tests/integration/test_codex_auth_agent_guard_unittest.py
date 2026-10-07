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

    def setUp(self):
        from app.services.codex_oauth import TokenSinkClaimsContext
        claims = patch("app.main.get_token_sink_claims_context", return_value=TokenSinkClaimsContext(
            has_valid_token_sink=False, claims={}, from_token_sink=False,
        ))
        claims.start()
        self.addCleanup(claims.stop)

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

@pytest.mark.parametrize("credential", ["token", "session", "missing", "invalid_token", "revoked", "expired", "provider", "provider_claims"])
@pytest.mark.parametrize("route", ["record-input", "dispatch", "url", "graph", "batch"])
def test_macro_http_ingress_preserves_only_current_mrw_actor(monkeypatch, credential, route):
    if _IMPORT_ERROR is not None:
        pytest.skip(str(_IMPORT_ERROR))
    from types import SimpleNamespace
    from pydantic import SecretStr
    import app.main as main
    import app.api.agent_macro_host as host_api
    import time
    import app.services.codex_oauth as oauth
    from app.services.codex_oauth import CodexSession, TokenSinkClaimsContext

    seen = []
    fake = SimpleNamespace(
        record_input=lambda **kwargs: seen.append(kwargs) or {"recorded": True},
        dispatch=lambda **kwargs: seen.append(kwargs) or {"success": True},
    )
    monkeypatch.setattr(host_api, "get_agent_macro_host_service", lambda: fake)
    monkeypatch.setattr(main.settings, "codex_auth_enabled", True)
    monkeypatch.setattr(main.settings, "codex_auth_tokens", "valid-mrw-token")
    monkeypatch.setattr(main.settings, "codex_oauth_enabled", True)
    monkeypatch.setattr(main.settings, "codex_oauth_cookie_name", "codex_session")
    monkeypatch.setattr(host_api.settings, "codex_webui_server_api_key", SecretStr("webui-service-key"))
    now = int(time.time())
    sessions = {}
    if credential in {"session", "revoked", "expired"}:
        sessions["active-session"] = CodexSession(
            session_id="active-session", access_token=None, token_type=None, scope=None,
            created_at=now - 100, expires_at=now - 1 if credential == "expired" else now + 300,
            claims={"sub": "mrw-user"},
        )
    monkeypatch.setattr(oauth, "_ACTIVE_SESSIONS", sessions)
    if credential == "revoked":
        monkeypatch.setattr(oauth, "revoke_provider_token", lambda **kwargs: {})
        monkeypatch.setattr(oauth, "revoke_token_sink", lambda: {})
        assert oauth.revoke_session("active-session")["session_revoked"]
    provider = credential.startswith("provider")
    monkeypatch.setattr(main, "has_valid_token_sink", lambda: provider)
    monkeypatch.setattr(main, "get_token_sink_claims_context", lambda: TokenSinkClaimsContext(
        has_valid_token_sink=provider, claims={"sub": "provider-only-user"} if credential == "provider_claims" else {}, from_token_sink=provider,
    ))
    headers = {"X-Project-Key": "demo_proj", "X-MRW-Server-API-Key": "webui-service-key", "X-Actor-Id": "forged"}
    if credential == "token":
        headers["X-Codex-Auth"] = "valid-mrw-token"
    elif credential == "invalid_token":
        headers["X-Codex-Auth"] = "revoked-mrw-token"
    elif credential in {"session", "revoked", "expired"}:
        headers["Cookie"] = "codex_session=active-session"
    payload = {"threadId": "thread", "turnId": "turn"}
    payload.update({"content": "read"} if route == "record-input" else {"callId": "call", "tool": "demo.read"})
    if route in {"url", "graph", "batch"}:
        from fastapi import HTTPException
        import app.services.request_identity as identity
        import app.api.workflow_graph as graph_api
        import app.api.agent_batch as batch_api
        original_require = identity.require_trusted_actor_context

        def require_at_effect_boundary(request):
            actor = original_require(request)
            seen.append({"actor_context": actor})
            raise HTTPException(status_code=418, detail="identity verified before effect")

        monkeypatch.setattr(identity, "require_trusted_actor_context", require_at_effect_boundary)
        monkeypatch.setattr(graph_api, "require_trusted_actor_context", require_at_effect_boundary)
        monkeypatch.setattr(batch_api, "require_trusted_actor_context", require_at_effect_boundary)
        client = TestClient(backend_app)
        if route == "url":
            response = client.post("/api/v1/ingest/url/single", json={
                "url": "https://example.com/article", "project_key": "demo_proj", "async_mode": True,
            }, headers=headers)
        else:
            path = "/api/v1/workflow-graph/runs/run-example" if route == "graph" else "/api/v1/agent-batch/jobs/run-example"
            response = client.get(path, headers=headers)
    else:
        response = TestClient(backend_app).post(f"/api/v1/agent-macro-host/{route}", json=payload, headers=headers)
    if credential in {"token", "session"}:
        assert response.status_code == (418 if route in {"url", "graph", "batch"} else 200), response.text
        actor = seen[0]["actor_context"]
        assert actor.actor_trusted
        assert actor.actor_id != "forged"
        assert actor.actor_source == ("authenticated_codex_token" if credential == "token" else "authenticated_oauth_session_claims")
    else:
        expected_status = 403 if route == "url" or (provider and route in {"graph", "batch"}) else 401
        assert response.status_code == expected_status, response.text
        assert seen == []


@pytest.mark.parametrize("route", ["record-input", "dispatch"])
def test_local_single_user_http_ingress_projects_stable_host_actor(monkeypatch, route):
    if _IMPORT_ERROR is not None:
        pytest.skip(str(_IMPORT_ERROR))
    from types import SimpleNamespace

    from pydantic import SecretStr

    import app.api.agent_macro_host as host_api
    import app.main as main
    from app.services.codex_oauth import TokenSinkClaimsContext
    from app.services.request_identity import actor_id_from_secret

    seen = []
    fake = SimpleNamespace(
        record_input=lambda **kwargs: seen.append(kwargs) or {"recorded": True},
        dispatch=lambda **kwargs: seen.append(kwargs) or {"success": True},
    )
    monkeypatch.setattr(host_api, "get_agent_macro_host_service", lambda: fake)
    monkeypatch.setattr(main.settings, "codex_auth_enabled", True)
    monkeypatch.setattr(main.settings, "codex_auth_tokens", "")
    monkeypatch.setattr(main.settings, "codex_oauth_enabled", True)
    monkeypatch.setattr(main.settings, "codex_webui_local_single_user_enabled", True)
    monkeypatch.setattr(
        main.settings,
        "codex_webui_server_api_key",
        SecretStr("webui-service-key"),
    )
    monkeypatch.setattr(main, "has_valid_token_sink", lambda: False)
    monkeypatch.setattr(
        main,
        "get_token_sink_claims_context",
        lambda: TokenSinkClaimsContext(
            has_valid_token_sink=False,
            claims={},
            from_token_sink=False,
        ),
    )
    headers = {
        "X-Project-Key": "demo_proj",
        "X-MRW-Server-API-Key": "webui-service-key",
        "X-Actor-Id": "forged",
    }
    payload = {"threadId": "thread", "turnId": "turn"}
    payload.update(
        {"content": "read"}
        if route == "record-input"
        else {"callId": "call", "tool": "demo.read"}
    )

    response = TestClient(
        backend_app, client=("127.0.0.1", 50000)
    ).post(f"/api/v1/agent-macro-host/{route}", json=payload, headers=headers)

    assert response.status_code == 200, response.text
    actor = seen[0]["actor_context"]
    assert actor.actor_id == actor_id_from_secret("local_host", "webui-service-key")
    assert actor.actor_source == "local_host"
    assert actor.actor_auth_mode == "local_host"
    assert actor.legacy_actor_id == "forged"
    assert actor.actor_trusted is True


@pytest.mark.parametrize(
    ("enabled", "client_host", "extra_headers", "supplied_key"),
    [
        (False, "127.0.0.1", {}, "webui-service-key"),
        (True, "192.0.2.10", {}, "webui-service-key"),
        (True, "127.0.0.1", {"Forwarded": "for=127.0.0.1"}, "webui-service-key"),
        (True, "127.0.0.1", {"X-Forwarded-For": "127.0.0.1"}, "webui-service-key"),
        (True, "127.0.0.1", {"X-Real-IP": "127.0.0.1"}, "webui-service-key"),
        (True, "127.0.0.1", {}, "wrong-key"),
    ],
)
def test_local_single_user_http_ingress_rejects_nonlocal_identity_inputs(
    monkeypatch, enabled, client_host, extra_headers, supplied_key,
):
    if _IMPORT_ERROR is not None:
        pytest.skip(str(_IMPORT_ERROR))
    from types import SimpleNamespace

    from pydantic import SecretStr

    import app.api.agent_macro_host as host_api
    import app.main as main
    from app.services.codex_oauth import TokenSinkClaimsContext

    seen = []
    fake = SimpleNamespace(record_input=lambda **kwargs: seen.append(kwargs) or {})
    monkeypatch.setattr(host_api, "get_agent_macro_host_service", lambda: fake)
    monkeypatch.setattr(main.settings, "codex_auth_enabled", True)
    monkeypatch.setattr(main.settings, "codex_auth_tokens", "")
    monkeypatch.setattr(main.settings, "codex_oauth_enabled", True)
    monkeypatch.setattr(main.settings, "codex_webui_local_single_user_enabled", enabled)
    monkeypatch.setattr(
        main.settings,
        "codex_webui_server_api_key",
        SecretStr("webui-service-key"),
    )
    monkeypatch.setattr(main, "has_valid_token_sink", lambda: False)
    monkeypatch.setattr(
        main,
        "get_token_sink_claims_context",
        lambda: TokenSinkClaimsContext(
            has_valid_token_sink=False,
            claims={},
            from_token_sink=False,
        ),
    )
    headers = {
        "X-Project-Key": "demo_proj",
        "X-MRW-Server-API-Key": supplied_key,
        **extra_headers,
    }

    response = TestClient(backend_app, client=(client_host, 50000)).post(
        "/api/v1/agent-macro-host/record-input",
        json={"threadId": "thread", "turnId": "turn", "content": "read"},
        headers=headers,
    )

    assert response.status_code == 401, response.text
    assert seen == []


def test_wrong_server_key_is_structured_401_after_mrw_actor_auth(monkeypatch):
    if _IMPORT_ERROR is not None:
        pytest.skip(str(_IMPORT_ERROR))
    from types import SimpleNamespace

    from pydantic import SecretStr

    import app.api.agent_macro_host as host_api
    import app.main as main

    seen = []
    fake = SimpleNamespace(record_input=lambda **kwargs: seen.append(kwargs) or {})
    monkeypatch.setattr(host_api, "get_agent_macro_host_service", lambda: fake)
    monkeypatch.setattr(main.settings, "codex_auth_enabled", True)
    monkeypatch.setattr(main.settings, "codex_auth_tokens", "valid-mrw-token")
    monkeypatch.setattr(main.settings, "codex_webui_local_single_user_enabled", True)
    monkeypatch.setattr(
        main.settings,
        "codex_webui_server_api_key",
        SecretStr("webui-service-key"),
    )

    response = TestClient(backend_app, client=("127.0.0.1", 50000)).post(
        "/api/v1/agent-macro-host/record-input",
        json={"threadId": "thread", "turnId": "turn", "content": "read"},
        headers={
            "X-Project-Key": "demo_proj",
            "X-Codex-Auth": "valid-mrw-token",
            "X-MRW-Server-API-Key": "wrong-key",
        },
    )

    assert response.status_code == 401, response.text
    error = response.json()["error"]
    assert error["code"] == "invalid_server_api_key"
    assert error["details"]["reason_code"] == "invalid_server_api_key"
    assert seen == []
