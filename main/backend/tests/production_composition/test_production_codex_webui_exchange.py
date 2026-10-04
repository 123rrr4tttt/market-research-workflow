"""Focused production tests for the authenticated Codex WebUI exchange."""

# ruff: noqa: E402

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
from typing import Any

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import SecretStr


BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BACKEND_ROOT.parent.parent
for path in (str(BACKEND_ROOT), str(REPOSITORY_ROOT / "src")):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.api.codex_auth import codex_auth_bootstrap_routes
from app.composition.production import load_production_route_bindings
from app.main import app as backend_app
from app.production_contract import EffectAdmission, EffectClass
from app.services.codex_oauth import CodexSession


pytestmark = pytest.mark.unit


class _Session(CodexSession):
    def __init__(self, session_id: str) -> None:
        super().__init__(
            session_id=session_id,
            access_token=None,
            token_type=None,
            scope=None,
            created_at=100,
            expires_at=700,
            claims={"sub": "codex-webui-exchange-subject"},
        )


@contextmanager
def _real_webui_login_server(
    *, status_code: int = 200, payload: dict[str, Any]
) -> Iterator[tuple[str, list[dict[str, Any]]]]:
    observations: list[dict[str, Any]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - http.server API
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length)
            observations.append(
                {
                    "path": self.path,
                    "accept": self.headers.get("Accept"),
                    "body": body,
                }
            )
            response = b'{"accessToken":"webui-session","expiresIn":86400}'
            if status_code != 200 or payload != {
                "accessToken": "webui-session",
                "expiresIn": 86400,
            }:
                import json

                response = json.dumps(payload, separators=(",", ":")).encode()
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", observations
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _configure(
    monkeypatch: pytest.MonkeyPatch,
    *,
    internal_url: str = "",
    server_key: str = "server-key-for-test",
) -> None:
    from app.settings.config import settings

    monkeypatch.setattr(settings, "codex_webui_internal_url", internal_url, raising=False)
    monkeypatch.setattr(settings, "codex_webui_server_api_key", SecretStr(server_key), raising=False)


def test_webui_exchange_is_not_anonymous_bootstrap_surface() -> None:
    assert ("POST", "/api/v1/codex-auth/webui/bootstrap") not in codex_auth_bootstrap_routes()
    routes = [
        route
        for route in backend_app.routes
        if isinstance(route, APIRoute)
        and route.path == "/api/v1/codex-auth/webui/bootstrap"
        and "POST" in route.methods
    ]
    assert len(routes) == 1
    dependencies = [
        getattr(dependency.call, "__name__", repr(dependency.call)) for dependency in routes[0].dependant.dependencies
    ]
    assert "require_production_policy" in dependencies

    bindings = load_production_route_bindings()
    binding = next(
        item
        for item in bindings
        if item.route_template == "/api/v1/codex-auth/webui/bootstrap" and "POST" in item.methods
    )
    assert binding.operation == "codex-auth.codex_auth_webui_bootstrap"
    assert binding.effect_contract is not None
    assert binding.effect_contract.effect_class is EffectClass.EXTERNAL_AUTH
    assert binding.effect_contract.admission is EffectAdmission.ADMITTED
    assert binding.effect_contract.external_auth_port == "codex_webui.session_exchange.v1"


def test_valid_token_sink_does_not_authorize_missing_exchange_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.api.codex_auth as codex_auth

    _configure(monkeypatch)
    monkeypatch.setattr(codex_auth, "has_valid_token_sink", lambda: True)
    monkeypatch.setattr(codex_auth, "get_session", lambda sid: None)

    response = TestClient(backend_app).post("/api/v1/codex-auth/webui/bootstrap")
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    details = response.json()["error"]["details"]
    assert details["reason_code"] == "missing_oauth_session"


def test_invalid_static_bearer_is_rejected_before_downstream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.api.codex_auth as codex_auth
    from app.settings.config import settings

    _configure(monkeypatch)
    monkeypatch.setattr(settings, "codex_auth_enabled", True)
    monkeypatch.setattr(settings, "codex_auth_tokens", "configured-static-token")
    downstream_called: list[bool] = []
    monkeypatch.setattr(
        codex_auth,
        "_configured_webui_internal_login_url",
        lambda: downstream_called.append(True),
    )

    response = TestClient(backend_app).post(
        "/api/v1/codex-auth/webui/bootstrap",
        headers={"Authorization": "Bearer invalid-static-token"},
    )
    assert response.status_code == 401
    assert downstream_called == []


def test_valid_cookie_requires_same_origin_and_skips_downstream_on_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.api.codex_auth as codex_auth

    _configure(monkeypatch)
    session = _Session("same-origin-session")
    monkeypatch.setattr(codex_auth, "get_session", lambda sid: session if sid == session.session_id else None)
    downstream_called: list[bool] = []
    monkeypatch.setattr(
        codex_auth,
        "_configured_webui_internal_login_url",
        lambda: downstream_called.append(True),
    )

    response = TestClient(backend_app).post(
        "/api/v1/codex-auth/webui/bootstrap",
        headers={
            "Origin": "https://cross-site.example",
            "Sec-Fetch-Site": "same-origin",
        },
        cookies={"codex_session": session.session_id},
    )
    assert response.status_code == 403
    assert downstream_called == []
    details = response.json()["error"]["details"]
    assert details["reason_code"] == "origin_mismatch"


def test_valid_cookie_exchanges_through_real_http_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.api.codex_auth as codex_auth

    session = _Session("browser-session")
    monkeypatch.setattr(codex_auth, "get_session", lambda sid: session if sid == session.session_id else None)
    with _real_webui_login_server(payload={"accessToken": "webui-session", "expiresIn": 86400}) as (
        internal_url,
        observations,
    ):
        _configure(monkeypatch, internal_url=internal_url)
        response = TestClient(backend_app).post(
            "/api/v1/codex-auth/webui/bootstrap",
            headers={
                "Origin": "http://testserver",
                "Sec-Fetch-Site": "same-origin",
            },
            cookies={"codex_session": session.session_id},
        )

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["data"] == {
        "accessToken": "webui-session",
        "expiresIn": 86400,
    }
    assert len(observations) == 1
    assert observations[0]["path"] == "/api/auth/login"
    assert observations[0]["accept"] == "application/json"
    assert json.loads(observations[0]["body"]) == {"apiKey": "server-key-for-test"}
    assert "server-key-for-test" not in response.text


def test_valid_configured_static_bearer_uses_real_http_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.settings.config import settings

    monkeypatch.setattr(settings, "codex_auth_enabled", True)
    monkeypatch.setattr(settings, "codex_auth_tokens", "configured-static-token")
    with _real_webui_login_server(payload={"accessToken": "webui-session", "expiresIn": 86400}) as (
        internal_url,
        observations,
    ):
        _configure(
            monkeypatch,
            internal_url=internal_url,
            server_key="configured-static-token",
        )
        response = TestClient(backend_app).post(
            "/api/v1/codex-auth/webui/bootstrap",
            headers={"Authorization": "Bearer configured-static-token"},
        )

    assert response.status_code == 200
    assert len(observations) == 1
    assert json.loads(observations[0]["body"]) == {"apiKey": "configured-static-token"}
    assert "configured-static-token" not in response.text


def test_missing_internal_configuration_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.settings.config import settings

    _configure(monkeypatch)
    monkeypatch.setattr(settings, "codex_auth_enabled", True)
    monkeypatch.setattr(settings, "codex_auth_tokens", "configured-static-token")

    response = TestClient(backend_app).post(
        "/api/v1/codex-auth/webui/bootstrap",
        headers={"Authorization": "Bearer configured-static-token"},
    )
    assert response.status_code == 503
    details = response.json()["error"]["details"]
    assert details["reason_code"] == "webui_exchange_not_configured"


@pytest.mark.parametrize(
    ("status_code", "payload"),
    [
        (401, {"accessToken": "must-not-be-returned"}),
        (200, {"accessToken": "webui-session"}),
        (200, {"accessToken": "webui-session", "expiresIn": 0}),
    ],
)
def test_downstream_failures_are_sanitized(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    payload: dict[str, Any],
) -> None:
    from app.settings.config import settings

    monkeypatch.setattr(settings, "codex_auth_enabled", True)
    monkeypatch.setattr(settings, "codex_auth_tokens", "configured-static-token")
    with _real_webui_login_server(status_code=status_code, payload=payload) as (
        internal_url,
        _observations,
    ):
        _configure(monkeypatch, internal_url=internal_url)
        response = TestClient(backend_app).post(
            "/api/v1/codex-auth/webui/bootstrap",
            headers={"Authorization": "Bearer configured-static-token"},
        )

    assert response.status_code == 502
    body = response.text
    assert "must-not-be-returned" not in body
    details = response.json()["error"]["details"]
    assert details["reason_code"] == "webui_exchange_failed"
