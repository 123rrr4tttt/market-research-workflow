from __future__ import annotations

import sys
import unittest
from pathlib import Path

from fastapi import HTTPException
from starlette.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.request_identity import (  # noqa: E402
    authenticated_actor_context,
    require_trusted_actor_context,
    resolve_request_actor_context,
    set_request_actor_context,
)


def _request(headers: dict[str, str] | None = None) -> Request:
    raw_headers = [
        (str(key).lower().encode("latin-1"), str(value).encode("latin-1"))
        for key, value in (headers or {}).items()
    ]
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/protected",
            "headers": raw_headers,
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
            "state": {},
        }
    )


class RequestIdentityBoundaryTests(unittest.TestCase):
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
