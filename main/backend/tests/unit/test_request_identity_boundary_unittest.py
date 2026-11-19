from __future__ import annotations

import sys
import unittest
from pathlib import Path

from fastapi import HTTPException
from starlette.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.request_identity import (  # noqa: E402
    actor_id_from_secret,
    authenticated_actor_context,
    require_trusted_actor_context,
    resolve_local_single_user_actor_context,
    resolve_request_actor_context,
    set_request_actor_context,
)


def _request(
    headers: dict[str, str] | None = None,
    *,
    path: str = "/api/v1/protected",
    client_host: str = "testclient",
) -> Request:
    raw_headers = [
        (str(key).lower().encode("latin-1"), str(value).encode("latin-1"))
        for key, value in (headers or {}).items()
    ]
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": raw_headers,
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": (client_host, 50000),
            "state": {},
        }
    )


class RequestIdentityBoundaryTests(unittest.TestCase):
    def test_local_single_user_actor_has_stable_explicit_identity(self):
        key = "webui-service-key"
        for route in ("prepare-turn", "record-input", "dispatch"):
            with self.subTest(route=route):
                request = _request(
                    {"X-MRW-Server-API-Key": key, "X-Actor-Id": "forged"},
                    path=f"/api/v1/agent-macro-host/{route}",
                    client_host="127.0.0.1",
                )

                context = resolve_local_single_user_actor_context(
                    request, enabled=True, server_api_key=key,
                )

                self.assertIsNotNone(context)
                assert context is not None
                self.assertEqual(context.actor_id, actor_id_from_secret("local_host", key))
                self.assertEqual(context.actor_source, "local_host")
                self.assertEqual(context.actor_auth_mode, "local_host")
                self.assertEqual(context.legacy_actor_id, "forged")
                self.assertTrue(context.actor_trusted)

    def test_local_single_user_actor_rejects_nonlocal_or_spoofable_inputs(self):
        key = "webui-service-key"
        cases = (
            (False, "127.0.0.1", {}, key, "/api/v1/agent-macro-host/record-input"),
            (True, "192.0.2.10", {}, key, "/api/v1/agent-macro-host/record-input"),
            (True, "127.0.0.1", {"Forwarded": "for=127.0.0.1"}, key, "/api/v1/agent-macro-host/record-input"),
            (True, "127.0.0.1", {"X-Forwarded-For": "127.0.0.1"}, key, "/api/v1/agent-macro-host/record-input"),
            (True, "127.0.0.1", {"X-Real-IP": "127.0.0.1"}, key, "/api/v1/agent-macro-host/record-input"),
            (True, "127.0.0.1", {}, "wrong-key", "/api/v1/agent-macro-host/record-input"),
            (True, "127.0.0.1", {}, key, "/api/v1/agent-macro-host/confirm"),
        )
        for enabled, client_host, extra_headers, configured_key, path in cases:
            with self.subTest(enabled=enabled, client_host=client_host, headers=extra_headers, path=path):
                request = _request(
                    {"X-MRW-Server-API-Key": key, **extra_headers},
                    path=path,
                    client_host=client_host,
                )
                self.assertIsNone(resolve_local_single_user_actor_context(
                    request, enabled=enabled, server_api_key=configured_key,
                ))

    def test_authenticated_state_actor_overrides_legacy_spoof_header_and_aliases(self):
        request = _request({"X-Actor-Id": "spoofed-header-actor"})
        request.state.authenticated_actor = {
            "actor_id": "authenticated-actor",
            "identity_source": "oauth_session",
            "auth_mode": "oidc_claims",
        }

        context = resolve_request_actor_context(request)

        self.assertEqual(context.actor_id, "authenticated-actor")
        self.assertTrue(context.actor_trusted)
        self.assertEqual(context.identity_source, "oauth_session")
        self.assertEqual(context.actor_source, "oauth_session")
        self.assertEqual(context.auth_mode, "oidc_claims")
        self.assertEqual(context.actor_auth_mode, "oidc_claims")
        self.assertEqual(context.legacy_actor_id, "spoofed-header-actor")

        observability = context.to_observability()
        self.assertEqual(observability["identity_source"], "oauth_session")
        self.assertEqual(observability["actor_source"], "oauth_session")
        self.assertEqual(observability["auth_mode"], "oidc_claims")
        self.assertEqual(observability["actor_auth_mode"], "oidc_claims")
        self.assertEqual(observability["legacy_actor_id"], "spoofed-header-actor")

    def test_legacy_header_is_untrusted_and_explicitly_labelled(self):
        context = resolve_request_actor_context(_request({"X-Actor-Id": "spoofed-header-actor"}))

        self.assertEqual(context.actor_id, "spoofed-header-actor")
        self.assertFalse(context.actor_trusted)
        self.assertEqual(context.identity_source, "legacy_header")
        self.assertEqual(context.auth_mode, "legacy_header")
        self.assertEqual(context.legacy_actor_id, "spoofed-header-actor")

        observability = context.to_observability()
        self.assertFalse(observability["actor_trusted"])
        self.assertEqual(observability["identity_source"], "legacy_header")
        self.assertEqual(observability["auth_mode"], "legacy_header")
        self.assertEqual(observability["legacy_actor_id"], "spoofed-header-actor")

    def test_set_request_actor_context_exposes_canonical_state_aliases(self):
        request = _request({"X-Actor-Id": "spoofed-header-actor"})
        context = authenticated_actor_context(
            actor_id="authenticated-actor",
            source="oauth_session",
            auth_mode="oidc_claims",
            legacy_actor_id="spoofed-header-actor",
        )

        set_request_actor_context(request, context)

        self.assertEqual(request.state.actor_source, "oauth_session")
        self.assertEqual(request.state.identity_source, "oauth_session")
        self.assertEqual(request.state.actor_auth_mode, "oidc_claims")
        self.assertEqual(request.state.auth_mode, "oidc_claims")
        self.assertEqual(request.state.legacy_actor_id, "spoofed-header-actor")

    def test_require_trusted_actor_rejects_legacy_header_with_recoverable_403(self):
        with self.assertRaises(HTTPException) as exc_ctx:
            require_trusted_actor_context(_request({"X-Actor-Id": "spoofed-header-actor"}))

        exc = exc_ctx.exception
        self.assertEqual(exc.status_code, 403)
        self.assertEqual(exc.detail["reason_code"], "trusted_actor_required")
        self.assertEqual(exc.detail["next_action"], "authenticate_request")
        self.assertEqual(exc.detail["actor_context"]["identity_source"], "legacy_header")
        self.assertEqual(exc.detail["actor_context"]["auth_mode"], "legacy_header")
        self.assertEqual(exc.detail["actor_context"]["legacy_actor_id"], "spoofed-header-actor")
        self.assertFalse(exc.detail["actor_context"]["actor_trusted"])

    def test_provider_token_sink_cannot_supply_mrw_user_identity(self):
        for source in ("authenticated_oauth_token_sink", "authenticated_oauth_token_sink_claims"):
            with self.subTest(source=source):
                request = _request()
                set_request_actor_context(request, authenticated_actor_context(
                    actor_id="provider-user", source=source, auth_mode="provider_oauth",
                ))
                with self.assertRaises(HTTPException) as rejected:
                    require_trusted_actor_context(request)
                self.assertEqual(rejected.exception.status_code, 403)
                self.assertEqual(rejected.exception.detail["reason_code"], "trusted_actor_required")

    def test_require_trusted_actor_returns_authenticated_actor(self):
        request = _request({"X-Actor-Id": "spoofed-header-actor"})
        request.state.authenticated_actor = {
            "actor_id": "authenticated-actor",
            "identity_source": "oauth_session",
            "auth_mode": "oidc_claims",
        }

        context = require_trusted_actor_context(request)

        self.assertEqual(context.actor_id, "authenticated-actor")
        self.assertTrue(context.actor_trusted)
        self.assertEqual(context.legacy_actor_id, "spoofed-header-actor")


if __name__ == "__main__":
    unittest.main()
