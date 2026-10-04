from __future__ import annotations

import asyncio
import base64
import hmac
import hashlib
import json
import sys
import tempfile
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.integration

try:
    from fastapi.testclient import TestClient
    from fastapi.responses import JSONResponse
    from starlette.requests import Request

    from app import main as backend_main
    from app.main import app as backend_app
    from app.services import codex_oauth as codex_oauth_service
    from app.services.codex_oauth import CodexSession

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


_TEST_ID_TOKEN_SHARED_KEY = "codex-oauth-id-token-test-shared-key"


def _fake_unsigned_jwt(payload: dict[str, object]) -> str:
    def _segment(data: dict[str, object]) -> str:
        raw = json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    now = int(time.time())
    default_payload: dict[str, object] = {
        "aud": getattr(codex_oauth_service.settings, "codex_oauth_client_id", "app_EMoamEEZ73f0CkXaXp7hrann"),
        "iss": "https://auth.openai.com",
        "exp": now + 3600,
        "source": "codex_cli_rs",
    }
    default_payload.update(payload)
    return f"{_segment({'alg': 'none', 'typ': 'JWT'})}.{_segment(default_payload)}."


def _fake_signed_jwt(payload: dict[str, object]) -> str:
    def _segment(data: dict[str, object]) -> str:
        raw = json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    now = int(time.time())
    default_payload: dict[str, object] = {
        "aud": getattr(codex_oauth_service.settings, "codex_oauth_client_id", "app_EMoamEEZ73f0CkXaXp7hrann"),
        "iss": "https://auth.openai.com",
        "exp": now + 3600,
        "source": "codex_cli_rs",
    }
    default_payload.update(payload)
    signing_input = (
        f"{_segment({'alg': 'HS256', 'typ': 'JWT', 'kid': 'codex-oauth-test-key'})}."
        f"{_segment(default_payload)}"
    )
    signature = hmac.new(
        _TEST_ID_TOKEN_SHARED_KEY.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    signature_segment = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return f"{signing_input}.{signature_segment}"


class _FakeTokenResponse:
    status_code = 200
    content = b"{}"

    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def json(self) -> dict[str, object]:
        return self._payload


class _FakeAsyncClient:
    def __init__(self, *args, token_payload: dict[str, object], **kwargs) -> None:
        self._token_payload = token_payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def post(self, *args, **kwargs) -> _FakeTokenResponse:
        return _FakeTokenResponse(self._token_payload)


class _FakeProviderRevokeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _FakeProviderRevokeClient:
    def __init__(
        self,
        calls: list[dict[str, object]],
        *,
        status_code: int = 200,
        exception: Exception | None = None,
    ) -> None:
        self._calls = calls
        self._status_code = status_code
        self._exception = exception

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def post(self, url: str, **kwargs) -> _FakeProviderRevokeResponse:
        self._calls.append({"url": url, **kwargs})
        if self._exception is not None:
            raise self._exception
        return _FakeProviderRevokeResponse(self._status_code)


def _request_with_headers_and_cookie(
    *,
    path: str,
    headers: dict[str, str],
    cookie_name: str,
    cookie_value: str,
) -> Request:
    raw_headers = [
        (str(key).lower().encode("latin-1"), str(value).encode("latin-1"))
        for key, value in headers.items()
    ]
    raw_headers.append((b"cookie", f"{cookie_name}={cookie_value}".encode("latin-1")))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": raw_headers,
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )


_TOKEN_SINK_PROFILE_NAME_KEYS = (
    "profile_name",
    "profile",
    "token_sink_profile",
    "token_sink_profile_name",
    "codex_oauth_token_sink_profile",
    "codex_oauth_token_sink_profile_name",
)
_TOKEN_SINK_PROFILE_NAME_HASH_KEYS = (
    "profile_name_hash",
    "profile_hash",
    "token_sink_profile_hash",
    "token_sink_profile_name_hash",
    "codex_oauth_token_sink_profile_hash",
    "codex_oauth_token_sink_profile_name_hash",
)
_TOKEN_SINK_EXPIRES_AT_KEYS = (
    "expires_at",
    "profile_expires_at",
    "token_sink_expires_at",
    "token_sink_profile_expires_at",
    "codex_oauth_token_sink_expires_at",
    "codex_oauth_token_sink_profile_expires_at",
)
_TOKEN_SINK_FALLBACK_KEYS = (
    "fallback_used",
    "used_fallback",
    "profile_fallback_used",
    "token_sink_fallback_used",
    "token_sink_profile_fallback_used",
    "codex_oauth_token_sink_fallback_used",
    "codex_oauth_token_sink_profile_fallback_used",
)
_TOKEN_SINK_METADATA_KEYS = (
    "metadata",
    "actor_metadata",
    "profile_metadata",
    "token_sink_metadata",
    "token_sink_profile_metadata",
    "codex_oauth_token_sink_metadata",
    "codex_oauth_token_sink_profile_metadata",
)
_TOKEN_SINK_SECRET_KEYS = ("access_token", "refresh_token", "id_token")


def _first_present(mapping: dict[str, object], keys: tuple[str, ...]) -> object:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _observable_token_sink_profile_name(profile_name: str | None) -> str | None:
    if profile_name is None:
        return None
    formatter = getattr(codex_oauth_service, "_observable_token_sink_profile_name", None)
    if callable(formatter):
        return formatter(profile_name)
    return "redacted" if str(profile_name or "").strip() else "unknown"


def _token_sink_profile_name_hash(profile_name: str | None) -> str | None:
    if profile_name is None:
        return None
    hasher = getattr(codex_oauth_service, "_token_sink_profile_name_hash", None)
    if callable(hasher):
        return hasher(profile_name)
    digest = hashlib.sha256(str(profile_name or "").encode("utf-8")).hexdigest()[:16]
    return f"profile:{digest}"


def _object_mapping(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    fields = getattr(value, "__dataclass_fields__", None)
    if isinstance(fields, dict):
        return {name: getattr(value, name) for name in fields if hasattr(value, name)}
    return dict(getattr(value, "__dict__", {}) or {})


def _token_sink_profile_metadata(value: object) -> dict[str, object] | None:
    mapping = _object_mapping(value)
    candidates = [mapping]
    for key in _TOKEN_SINK_METADATA_KEYS:
        nested = mapping.get(key)
        if isinstance(nested, dict):
            candidates.append(nested)

    for candidate in candidates:
        profile_name = _first_present(candidate, _TOKEN_SINK_PROFILE_NAME_KEYS)
        profile_name_hash = _first_present(candidate, _TOKEN_SINK_PROFILE_NAME_HASH_KEYS)
        expires_at = _first_present(candidate, _TOKEN_SINK_EXPIRES_AT_KEYS)
        fallback_used = _first_present(candidate, _TOKEN_SINK_FALLBACK_KEYS)
        if (
            profile_name is not None
            or profile_name_hash is not None
            or expires_at is not None
            or fallback_used is not None
        ):
            return {
                "profile_name": profile_name,
                "profile_name_hash": profile_name_hash,
                "expires_at": expires_at,
                "fallback_used": fallback_used,
            }
    return None


def _token_sink_context_kwargs(
    *,
    profile_name: str | None = None,
    expires_at: int | None = None,
    fallback_used: bool | None = None,
) -> dict[str, object]:
    fields = getattr(codex_oauth_service.TokenSinkClaimsContext, "__dataclass_fields__", {}) or {}
    field_names = set(fields.keys())
    kwargs: dict[str, object] = {}
    observable_profile_name = _observable_token_sink_profile_name(profile_name)
    profile_name_hash = _token_sink_profile_name_hash(profile_name)
    metadata = {
        "profile_name": observable_profile_name,
        "profile_name_hash": profile_name_hash,
        "expires_at": expires_at,
        "fallback_used": fallback_used,
    }
    for key in _TOKEN_SINK_PROFILE_NAME_KEYS:
        if key in field_names:
            kwargs[key] = observable_profile_name
            break
    for key in _TOKEN_SINK_PROFILE_NAME_HASH_KEYS:
        if key in field_names:
            kwargs[key] = profile_name_hash
            break
    for key in _TOKEN_SINK_EXPIRES_AT_KEYS:
        if key in field_names:
            kwargs[key] = expires_at
            break
    for key in _TOKEN_SINK_FALLBACK_KEYS:
        if key in field_names:
            kwargs[key] = fallback_used
            break
    for key in _TOKEN_SINK_METADATA_KEYS:
        if key in field_names:
            kwargs[key] = metadata
            break
    return kwargs


def _token_sink_claims_context_from_id_token(
    id_token: str | None,
    *,
    has_valid_token_sink: bool = True,
    from_token_sink: bool = True,
    profile_name: str | None = None,
    expires_at: int | None = None,
    fallback_used: bool | None = None,
):
    return codex_oauth_service.TokenSinkClaimsContext(
        has_valid_token_sink=has_valid_token_sink,
        claims=codex_oauth_service.decode_id_token_claims(id_token),
        from_token_sink=from_token_sink,
        **_token_sink_context_kwargs(
            profile_name=profile_name,
            expires_at=expires_at,
            fallback_used=fallback_used,
        ),
    )


def _recording_token_sink_file_lock(calls: list[bool]):
    @contextmanager
    def _lock(exclusive: bool):
        calls.append(exclusive)
        yield

    return _lock


class CodexOauthBrowserFlowIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"codex oauth integration tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(backend_app)
        cls.headers = {"X-Project-Key": "demo_proj", "X-Request-Id": "codex-oauth-it"}

    def setUp(self):
        super().setUp()
        self._id_token_shared_key_patcher = patch(
            "app.services.codex_oauth.settings.codex_oauth_id_token_shared_key",
            _TEST_ID_TOKEN_SHARED_KEY,
        )
        self._id_token_shared_key_patcher.start()

    def tearDown(self):
        self._id_token_shared_key_patcher.stop()
        super().tearDown()

    def assertTokenSinkProfileMetadata(
        self,
        value: object,
        *,
        profile_name: str,
        expires_at: int,
        fallback_used: bool,
    ) -> dict[str, object]:
        metadata = _token_sink_profile_metadata(value)
        self.assertIsNotNone(metadata, "token sink profile metadata must be observable")
        assert metadata is not None
        observable_profile_name = metadata.get("profile_name")
        profile_name_hash = metadata.get("profile_name_hash")
        serialized = json.dumps(metadata, default=str, sort_keys=True)
        self.assertIsInstance(observable_profile_name, str)
        self.assertIsInstance(profile_name_hash, str)
        self.assertNotEqual(observable_profile_name, profile_name)
        self.assertNotIn(profile_name, str(observable_profile_name))
        self.assertNotIn(profile_name, str(profile_name_hash))
        self.assertNotIn(profile_name, serialized)
        self.assertEqual(metadata.get("expires_at"), expires_at)
        self.assertIs(metadata.get("fallback_used"), fallback_used)
        return metadata

    def assertNoSensitiveTokenSinkMetadata(
        self,
        metadata: dict[str, object],
        *,
        forbidden_values: tuple[str, ...] = (),
    ) -> None:
        serialized = json.dumps(metadata, default=str, sort_keys=True)
        for key in _TOKEN_SINK_SECRET_KEYS:
            self.assertNotIn(key, serialized)
        for value in forbidden_values:
            if value:
                self.assertNotIn(value, serialized)

    def assertNoTokenSinkProfileMetadata(self, value: object) -> None:
        self.assertIsNone(_token_sink_profile_metadata(value))

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

    def test_protected_static_token_sets_trusted_hashed_request_actor(self):
        request = _request_with_headers_and_cookie(
            path="/api/v1/agent-batch/rule-sets/validate",
            headers={
                **self.headers,
                "Authorization": "Bearer static-token-for-state-witness",
                "X-Actor-Id": "spoofed-header-actor",
            },
            cookie_name="codex_session",
            cookie_value="",
        )
        observed: dict[str, object] = {}

        async def call_next(next_request: Request) -> JSONResponse:
            observed["actor_context"] = getattr(next_request.state, "actor_context", None)
            return JSONResponse({"status": "ok"})

        with (
            patch("app.main.settings.codex_auth_enabled", True),
            patch("app.main.settings.codex_auth_protected_prefixes", "/api/v1/agent-batch"),
            patch("app.main.settings.codex_auth_tokens", "static-token-for-state-witness"),
            patch("app.main._resolve_request_project_context", return_value=("demo_proj", "header", False)),
            patch("app.main.get_effective_project_key_enforcement_mode", return_value="require"),
        ):
            response = asyncio.run(backend_main.metrics_middleware(request, call_next))

        self.assertEqual(response.status_code, 200)
        actor_context = observed.get("actor_context")
        self.assertIsInstance(actor_context, dict)
        assert isinstance(actor_context, dict)
        self.assertTrue(actor_context["actor_trusted"])
        self.assertEqual(actor_context["actor_source"], "authenticated_codex_token")
        self.assertEqual(actor_context["actor_auth_mode"], "codex_static_token")
        self.assertTrue(str(actor_context["actor_id"]).startswith("actor:codex-token:"))
        self.assertNotEqual(actor_context["actor_id"], "static-token-for-state-witness")
        self.assertNotIn("static-token-for-state-witness", str(actor_context["actor_id"]))
        self.assertEqual(actor_context["legacy_actor_id"], "spoofed-header-actor")

    def test_oauth_middleware_does_not_read_cli_fallback_after_valid_token_sink(self):
        request = _request_with_headers_and_cookie(
            path="/api/v1/agent-batch/rule-sets/validate",
            headers=self.headers,
            cookie_name="codex_session",
            cookie_value="",
        )
        claims_context = _token_sink_claims_context_from_id_token(
            _fake_signed_jwt(
                {
                    "sub": "single-read-token-sink-sub",
                    "email": "single-read-token-sink@example.test",
                    "email_verified": True,
                }
            ),
            profile_name="work",
            expires_at=int(time.time()) + 3600,
            fallback_used=False,
        )
        observed: dict[str, object] = {}

        async def call_next(next_request: Request) -> JSONResponse:
            observed["actor_context"] = getattr(next_request.state, "actor_context", None)
            return JSONResponse({"status": "ok"})

        with (
            patch("app.main.settings.codex_auth_enabled", True),
            patch("app.main.settings.codex_auth_protected_prefixes", "/api/v1/agent-batch"),
            patch("app.main.settings.codex_auth_tokens", ""),
            patch("app.main.get_token_sink_claims_context", return_value=claims_context),
            patch("app.main.has_valid_token_sink", side_effect=AssertionError("CLI fallback must not be read")),
            patch("app.main._resolve_request_project_context", return_value=("demo_proj", "header", False)),
            patch("app.main.get_effective_project_key_enforcement_mode", return_value="require"),
        ):
            response = asyncio.run(backend_main.metrics_middleware(request, call_next))

        self.assertEqual(response.status_code, 200)
        actor_context = observed.get("actor_context")
        self.assertIsInstance(actor_context, dict)
        assert isinstance(actor_context, dict)
        self.assertEqual(actor_context["actor_id"], "single-read-token-sink-sub")
        self.assertEqual(actor_context["actor_source"], "authenticated_oauth_token_sink_claims")
        self.assertTrue(actor_context["actor_trusted"])

    def test_codex_session_old_constructor_without_claims_stays_compatible(self):
        session = CodexSession(
            session_id="sid-legacy",
            access_token="at",
            token_type="Bearer",
            scope="openid",
            created_at=100,
            expires_at=999999,
        )

        self.assertEqual(session.session_id, "sid-legacy")
        self.assertEqual(getattr(session, "claims", {}), {})

    def test_decode_id_token_claims_preserves_subject_and_email_claims(self):
        token = _fake_unsigned_jwt(
            {
                "sub": "user-sub-123",
                "email": "user@example.test",
                "email_verified": True,
                "name": "Example User",
            }
        )

        decode_claims = getattr(codex_oauth_service, "decode_id_token_claims", None)
        self.assertTrue(callable(decode_claims), "codex_oauth.decode_id_token_claims must exist")

        claims = decode_claims(token)

        self.assertEqual(claims.get("sub"), "user-sub-123")
        self.assertEqual(claims.get("email"), "user@example.test")
        self.assertIs(claims.get("email_verified"), True)
        self.assertEqual(claims.get("name"), "Example User")

    def test_validate_id_token_claims_rejects_unsigned_token_and_accepts_signed_token(self):
        unsigned_token = _fake_unsigned_jwt(
            {
                "sub": "unsigned-sub-123",
                "email": "unsigned@example.test",
                "email_verified": True,
            }
        )
        signed_token = _fake_signed_jwt(
            {
                "sub": "signed-sub-123",
                "email": "signed@example.test",
                "email_verified": True,
            }
        )

        self.assertEqual(codex_oauth_service.validate_id_token_claims(unsigned_token), {})

        claims = codex_oauth_service.validate_id_token_claims(signed_token)
        self.assertEqual(claims.get("sub"), "signed-sub-123")
        self.assertEqual(claims.get("email"), "signed@example.test")
        self.assertIs(claims.get("email_verified"), True)

    def test_validate_id_token_claims_returns_empty_without_verification_material(self):
        token = _fake_signed_jwt(
            {
                "sub": "signed-without-key-sub",
                "email": "signed-without-key@example.test",
                "email_verified": True,
            }
        )

        with patch("app.services.codex_oauth.settings.codex_oauth_id_token_shared_key", ""):
            self.assertEqual(codex_oauth_service.validate_id_token_claims(token), {})

    def test_exchange_code_to_session_persists_id_token_claims(self):
        id_token = _fake_signed_jwt(
            {
                "aud": "client-id",
                "iss": "https://auth.example",
                "sub": "exchange-sub-123",
                "email": "exchange@example.test",
                "email_verified": True,
            }
        )
        now = int(time.time())
        with codex_oauth_service._STATE_LOCK:
            codex_oauth_service._PENDING_STATES["state-with-id-token"] = {
                "created_at": now,
                "expires_at": now + 600,
                "code_verifier": "verifier",
                "redirect_uri": "https://app.example/callback",
                "next_url": "/workspace",
            }

        token_payload = {
            "access_token": "access-token",
            "token_type": "Bearer",
            "scope": "openid email profile",
            "expires_in": 3600,
            "id_token": id_token,
        }

        with (
            patch("app.services.codex_oauth.settings.codex_oauth_enabled", True),
            patch("app.services.codex_oauth.settings.codex_oauth_provider", "custom"),
            patch("app.services.codex_oauth.settings.codex_oauth_authorize_url", "https://auth.example/authorize"),
            patch("app.services.codex_oauth.settings.codex_oauth_token_url", "https://auth.example/token"),
            patch("app.services.codex_oauth.settings.codex_oauth_client_id", "client-id"),
            patch("app.services.codex_oauth.settings.codex_oauth_client_secret", ""),
            patch("app.services.codex_oauth.settings.codex_oauth_redirect_uri", "https://app.example/callback"),
            patch("app.services.codex_oauth.settings.codex_oauth_token_sink_enabled", False),
            patch(
                "app.services.codex_oauth.httpx.AsyncClient",
                lambda *args, **kwargs: _FakeAsyncClient(*args, token_payload=token_payload, **kwargs),
            ),
        ):
            session, next_url = asyncio.run(
                codex_oauth_service.exchange_code_to_session(code="code-ok", state="state-with-id-token")
            )

        self.assertEqual(next_url, "/workspace")
        self.assertEqual(session.claims.get("sub"), "exchange-sub-123")
        self.assertEqual(session.claims.get("email"), "exchange@example.test")
        self.assertIs(session.claims.get("email_verified"), True)

    def test_exchange_code_to_session_rejects_invalid_id_token_trust_claims(self):
        now = int(time.time())
        cases = [
            ("aud", {"aud": "wrong-client", "iss": "https://auth.example", "exp": now + 3600, "source": "codex_cli_rs"}),
            ("iss", {"aud": "client-id", "iss": "https://evil.example", "exp": now + 3600, "source": "codex_cli_rs"}),
            ("exp", {"aud": "client-id", "iss": "https://auth.example", "exp": now - 1, "source": "codex_cli_rs"}),
            ("source", {"aud": "client-id", "iss": "https://auth.example", "exp": now + 3600, "source": "browser"}),
        ]

        for label, invalid_claims in cases:
            with self.subTest(label=label):
                state = f"state-invalid-{label}"
                with codex_oauth_service._STATE_LOCK:
                    codex_oauth_service._PENDING_STATES[state] = {
                        "created_at": now,
                        "expires_at": now + 600,
                        "code_verifier": "verifier",
                        "redirect_uri": "https://app.example/callback",
                        "next_url": "/workspace",
                    }

                token_payload = {
                    "access_token": f"access-token-{label}",
                    "token_type": "Bearer",
                    "scope": "openid email profile",
                    "expires_in": 3600,
                    "id_token": _fake_signed_jwt(
                        {
                            **invalid_claims,
                            "sub": f"invalid-{label}-sub",
                            "email": f"invalid-{label}@example.test",
                            "email_verified": True,
                        }
                    ),
                }

                with (
                    patch("app.services.codex_oauth.settings.codex_oauth_enabled", True),
                    patch("app.services.codex_oauth.settings.codex_oauth_provider", "custom"),
                    patch("app.services.codex_oauth.settings.codex_oauth_authorize_url", "https://auth.example/authorize"),
                    patch("app.services.codex_oauth.settings.codex_oauth_token_url", "https://auth.example/token"),
                    patch("app.services.codex_oauth.settings.codex_oauth_client_id", "client-id"),
                    patch("app.services.codex_oauth.settings.codex_oauth_client_secret", ""),
                    patch("app.services.codex_oauth.settings.codex_oauth_redirect_uri", "https://app.example/callback"),
                    patch("app.services.codex_oauth.settings.codex_oauth_token_sink_enabled", False),
                    patch(
                        "app.services.codex_oauth.httpx.AsyncClient",
                        lambda *args, **kwargs: _FakeAsyncClient(*args, token_payload=token_payload, **kwargs),
                    ),
                ):
                    session, _next_url = asyncio.run(
                        codex_oauth_service.exchange_code_to_session(code="code-ok", state=state)
                    )

                self.assertEqual(session.claims, {})
                request = _request_with_headers_and_cookie(
                    path="/api/v1/agent-batch/rule-sets/validate",
                    headers={**self.headers, "X-Actor-Id": "spoofed-header-actor"},
                    cookie_name="codex_session",
                    cookie_value=session.session_id,
                )
                with (
                    patch("app.main.get_session", return_value=session),
                    patch("app.main.has_valid_token_sink", return_value=False),
                ):
                    actor_context = backend_main._resolve_codex_oauth_actor_context(request)

                self.assertIsNotNone(actor_context)
                self.assertNotEqual(actor_context.actor_id, f"invalid-{label}-sub")
                self.assertEqual(actor_context.actor_source, "authenticated_oauth_session")
                self.assertEqual(actor_context.actor_auth_mode, "codex_oauth_session")

    def test_oauth_session_claims_actor_context_overrides_spoofed_header(self):
        request = _request_with_headers_and_cookie(
            path="/api/v1/agent-batch/rule-sets/validate",
            headers={**self.headers, "X-Actor-Id": "spoofed-header-actor"},
            cookie_name="codex_session",
            cookie_value="sid-claims",
        )
        session = CodexSession(
            session_id="sid-claims",
            access_token="at",
            token_type="Bearer",
            scope="openid email",
            created_at=100,
            expires_at=999999,
            claims={
                "sub": "oauth-sub-123",
                "email": "oauth-user@example.test",
                "email_verified": True,
            },
        )

        with (
            patch("app.main.get_session", return_value=session),
            patch("app.main.has_valid_token_sink", return_value=False),
        ):
            actor_context = backend_main._resolve_codex_oauth_actor_context(request)

        self.assertIsNotNone(actor_context)
        self.assertEqual(actor_context.actor_id, "oauth-sub-123")
        self.assertEqual(actor_context.actor_source, "authenticated_oauth_session_claims")
        self.assertTrue(actor_context.actor_trusted)
        self.assertEqual(actor_context.actor_auth_mode, "codex_oauth_session_oidc_claims")
        self.assertEqual(actor_context.legacy_actor_id, "spoofed-header-actor")

    def test_oauth_session_claims_actor_context_uses_verified_email_when_subject_missing(self):
        verified_email = "verified-user@example.test"

        def _resolve_for_session(session_id: str):
            request = _request_with_headers_and_cookie(
                path="/api/v1/agent-batch/rule-sets/validate",
                headers={**self.headers, "X-Actor-Id": "spoofed-header-actor"},
                cookie_name="codex_session",
                cookie_value=session_id,
            )
            session = CodexSession(
                session_id=session_id,
                access_token="at",
                token_type="Bearer",
                scope="openid email",
                created_at=100,
                expires_at=999999,
                claims={
                    "email": verified_email,
                    "email_verified": True,
                },
            )

            with (
                patch("app.main.get_session", return_value=session),
                patch("app.main.has_valid_token_sink", return_value=False),
            ):
                return backend_main._resolve_codex_oauth_actor_context(request)

        actor_context = _resolve_for_session("sid-email-claims-a")
        repeated_actor_context = _resolve_for_session("sid-email-claims-b")

        self.assertIsNotNone(actor_context)
        self.assertIsNotNone(repeated_actor_context)
        self.assertNotEqual(actor_context.actor_id, verified_email)
        self.assertTrue(actor_context.actor_id.startswith("codex_oauth_email:"))
        self.assertNotIn(verified_email, actor_context.actor_id)
        self.assertNotIn("@", actor_context.actor_id)
        self.assertEqual(actor_context.actor_id, repeated_actor_context.actor_id)
        self.assertEqual(actor_context.actor_source, "authenticated_oauth_session_claims")
        self.assertEqual(actor_context.actor_auth_mode, "codex_oauth_session_oidc_claims")
        self.assertEqual(actor_context.legacy_actor_id, "spoofed-header-actor")

    def test_oauth_session_unverified_email_falls_back_to_session_actor(self):
        request = _request_with_headers_and_cookie(
            path="/api/v1/agent-batch/rule-sets/validate",
            headers=self.headers,
            cookie_name="codex_session",
            cookie_value="sid-unverified-email",
        )
        session = CodexSession(
            session_id="sid-unverified-email",
            access_token="at",
            token_type="Bearer",
            scope="openid email",
            created_at=100,
            expires_at=999999,
            claims={
                "email": "unverified-user@example.test",
                "email_verified": False,
            },
        )

        with (
            patch("app.main.get_session", return_value=session),
            patch("app.main.has_valid_token_sink", return_value=False),
        ):
            actor_context = backend_main._resolve_codex_oauth_actor_context(request)

        self.assertIsNotNone(actor_context)
        self.assertTrue(actor_context.actor_id.startswith("codex_oauth_session:"))
        self.assertEqual(actor_context.actor_source, "authenticated_oauth_session")
        self.assertEqual(actor_context.actor_auth_mode, "codex_oauth_session")

    def test_token_sink_claims_context_decodes_only_valid_token_sink_payload(self):
        now = int(time.time())
        id_token = _fake_signed_jwt(
            {
                "sub": "token-sink-service-sub",
                "email": "token-sink-service@example.test",
                "email_verified": True,
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            sink_path = Path(tmpdir) / "auth.json"
            sink_path.write_text(
                json.dumps(
                    {
                        "schema_version": "codex_oauth_sink.v1",
                        "active_profile": "default",
                        "profiles": {
                            "default": {
                                "access_token": "access-token",
                                "expires_at": now + 3600,
                                "id_token": id_token,
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch("app.services.codex_oauth.settings.codex_oauth_token_sink_enabled", True),
                patch("app.services.codex_oauth.settings.codex_oauth_token_sink_fallback_profiles", "default"),
                patch("app.services.codex_oauth._resolve_token_sink_path", return_value=sink_path),
            ):
                claims_context = codex_oauth_service.get_token_sink_claims_context()

        self.assertTrue(claims_context.has_valid_token_sink)
        self.assertTrue(claims_context.from_token_sink)
        self.assertEqual(claims_context.claims.get("sub"), "token-sink-service-sub")
        self.assertEqual(claims_context.claims.get("email"), "token-sink-service@example.test")

        with tempfile.TemporaryDirectory() as tmpdir:
            sink_path = Path(tmpdir) / "auth.json"
            sink_path.write_text(
                json.dumps(
                    {
                        "schema_version": "codex_oauth_sink.v1",
                        "active_profile": "default",
                        "profiles": {
                            "default": {
                                "access_token": "access-token",
                                "expires_at": now - 60,
                                "id_token": id_token,
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch("app.services.codex_oauth.settings.codex_oauth_token_sink_enabled", True),
                patch("app.services.codex_oauth._resolve_token_sink_path", return_value=sink_path),
            ):
                expired_context = codex_oauth_service.get_token_sink_claims_context()

        self.assertFalse(expired_context.has_valid_token_sink)
        self.assertFalse(expired_context.from_token_sink)
        self.assertEqual(expired_context.claims, {})

    def test_token_sink_claims_context_uses_valid_active_profile(self):
        now = int(time.time())
        active_expires_at = now + 3600
        fallback_expires_at = now + 7200
        active_id_token = _fake_signed_jwt(
            {
                "sub": "active-profile-sub",
                "email": "active-profile@example.test",
                "email_verified": True,
            }
        )
        fallback_id_token = _fake_signed_jwt(
            {
                "sub": "fallback-profile-sub",
                "email": "fallback-profile@example.test",
                "email_verified": True,
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            sink_path = Path(tmpdir) / "auth.json"
            sink_path.write_text(
                json.dumps(
                    {
                        "schema_version": "codex_oauth_sink.v1",
                        "active_profile": "work",
                        "profiles": {
                            "work": {
                                "access_token": "active-access-token",
                                "expires_at": active_expires_at,
                                "id_token": active_id_token,
                            },
                            "default": {
                                "access_token": "fallback-access-token",
                                "expires_at": fallback_expires_at,
                                "id_token": fallback_id_token,
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch("app.services.codex_oauth.settings.codex_oauth_token_sink_enabled", True),
                patch("app.services.codex_oauth._resolve_token_sink_path", return_value=sink_path),
            ):
                claims_context = codex_oauth_service.get_token_sink_claims_context()

        self.assertTrue(claims_context.has_valid_token_sink)
        self.assertTrue(claims_context.from_token_sink)
        self.assertEqual(claims_context.claims.get("sub"), "active-profile-sub")
        self.assertEqual(claims_context.claims.get("email"), "active-profile@example.test")
        metadata = self.assertTokenSinkProfileMetadata(
            claims_context,
            profile_name="work",
            expires_at=active_expires_at,
            fallback_used=False,
        )
        self.assertNoSensitiveTokenSinkMetadata(
            metadata,
            forbidden_values=(
                "active-access-token",
                "fallback-access-token",
                active_id_token,
                fallback_id_token,
                "active-profile@example.test",
                "fallback-profile@example.test",
            ),
        )

    def test_token_sink_profile_metadata_hashes_profile_name_without_leaking_raw_name(self):
        now = int(time.time())
        alice_expires_at = now + 3600
        jane_expires_at = now + 7200
        alice_profile_name = "alice-work"
        jane_profile_name = "jane_prod"
        alice_id_token = _fake_signed_jwt(
            {
                "sub": "alice-work-profile-sub",
                "email": "alice-work-profile@example.test",
                "email_verified": True,
            }
        )
        jane_id_token = _fake_signed_jwt(
            {
                "sub": "jane-prod-profile-sub",
                "email": "jane-prod-profile@example.test",
                "email_verified": True,
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            sink_path = Path(tmpdir) / "auth.json"

            def write_sink(active_profile: str) -> None:
                sink_path.write_text(
                    json.dumps(
                        {
                            "schema_version": "codex_oauth_sink.v1",
                            "active_profile": active_profile,
                            "profiles": {
                                alice_profile_name: {
                                    "access_token": "alice-work-access-token",
                                    "expires_at": alice_expires_at,
                                    "id_token": alice_id_token,
                                },
                                jane_profile_name: {
                                    "access_token": "jane-prod-access-token",
                                    "expires_at": jane_expires_at,
                                    "id_token": jane_id_token,
                                },
                            },
                        }
                    ),
                    encoding="utf-8",
                )

            with (
                patch("app.services.codex_oauth.settings.codex_oauth_token_sink_enabled", True),
                patch("app.services.codex_oauth._resolve_token_sink_path", return_value=sink_path),
            ):
                write_sink(alice_profile_name)
                alice_context = codex_oauth_service.get_token_sink_claims_context()
                repeated_alice_context = codex_oauth_service.get_token_sink_claims_context()

                write_sink(jane_profile_name)
                jane_context = codex_oauth_service.get_token_sink_claims_context()

        alice_metadata = self.assertTokenSinkProfileMetadata(
            alice_context,
            profile_name=alice_profile_name,
            expires_at=alice_expires_at,
            fallback_used=False,
        )
        repeated_alice_metadata = self.assertTokenSinkProfileMetadata(
            repeated_alice_context,
            profile_name=alice_profile_name,
            expires_at=alice_expires_at,
            fallback_used=False,
        )
        jane_metadata = self.assertTokenSinkProfileMetadata(
            jane_context,
            profile_name=jane_profile_name,
            expires_at=jane_expires_at,
            fallback_used=False,
        )
        self.assertEqual(alice_metadata.get("profile_name_hash"), repeated_alice_metadata.get("profile_name_hash"))
        self.assertNotEqual(alice_metadata.get("profile_name_hash"), jane_metadata.get("profile_name_hash"))
        self.assertNoSensitiveTokenSinkMetadata(
            alice_metadata,
            forbidden_values=(
                alice_profile_name,
                jane_profile_name,
                "alice-work-access-token",
                "jane-prod-access-token",
                alice_id_token,
                jane_id_token,
                "alice-work-profile@example.test",
                "jane-prod-profile@example.test",
            ),
        )

    def test_token_sink_claims_context_falls_back_when_active_profile_expired(self):
        now = int(time.time())
        active_expires_at = now - 60
        fallback_expires_at = now + 3600
        active_id_token = _fake_signed_jwt(
            {
                "sub": "expired-active-profile-sub",
                "email": "expired-active-profile@example.test",
                "email_verified": True,
            }
        )
        fallback_id_token = _fake_signed_jwt(
            {
                "sub": "valid-fallback-profile-sub",
                "email": "valid-fallback-profile@example.test",
                "email_verified": True,
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            sink_path = Path(tmpdir) / "auth.json"
            sink_path.write_text(
                json.dumps(
                    {
                        "schema_version": "codex_oauth_sink.v1",
                        "active_profile": "work",
                        "profiles": {
                            "work": {
                                "access_token": "expired-active-access-token",
                                "expires_at": active_expires_at,
                                "id_token": active_id_token,
                            },
                            "backup": {
                                "access_token": "valid-fallback-access-token",
                                "expires_at": fallback_expires_at,
                                "id_token": fallback_id_token,
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch("app.services.codex_oauth.settings.codex_oauth_token_sink_enabled", True),
                patch("app.services.codex_oauth.settings.codex_oauth_token_sink_fallback_profiles", ""),
                patch("app.services.codex_oauth._resolve_token_sink_path", return_value=sink_path),
                patch("app.services.codex_oauth._has_valid_codex_cli_auth", return_value=False),
            ):
                claims_context = codex_oauth_service.get_token_sink_claims_context()
                has_valid_sink = codex_oauth_service.has_valid_token_sink()

        self.assertTrue(claims_context.has_valid_token_sink)
        self.assertTrue(claims_context.from_token_sink)
        self.assertEqual(claims_context.claims.get("sub"), "valid-fallback-profile-sub")
        self.assertEqual(claims_context.claims.get("email"), "valid-fallback-profile@example.test")
        metadata = self.assertTokenSinkProfileMetadata(
            claims_context,
            profile_name="backup",
            expires_at=fallback_expires_at,
            fallback_used=True,
        )
        self.assertNoSensitiveTokenSinkMetadata(
            metadata,
            forbidden_values=(
                "expired-active-access-token",
                "valid-fallback-access-token",
                active_id_token,
                fallback_id_token,
                "expired-active-profile@example.test",
                "valid-fallback-profile@example.test",
            ),
        )
        self.assertTrue(has_valid_sink)

    def test_token_sink_claims_context_skips_revoked_active_profile_and_falls_back(self):
        now = int(time.time())
        active_expires_at = now + 3600
        fallback_expires_at = now + 7200
        active_id_token = _fake_signed_jwt(
            {
                "sub": "revoked-active-profile-sub",
                "email": "revoked-active-profile@example.test",
                "email_verified": True,
            }
        )
        fallback_id_token = _fake_signed_jwt(
            {
                "sub": "valid-backup-after-revoked-active-sub",
                "email": "valid-backup-after-revoked-active@example.test",
                "email_verified": True,
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            sink_path = Path(tmpdir) / "auth.json"
            sink_path.write_text(
                json.dumps(
                    {
                        "schema_version": "codex_oauth_sink.v1",
                        "active_profile": "work",
                        "profiles": {
                            "work": {
                                "access_token": "revoked-active-access-token",
                                "expires_at": active_expires_at,
                                "id_token": active_id_token,
                                "revoked": True,
                            },
                            "backup": {
                                "access_token": "valid-backup-access-token",
                                "expires_at": fallback_expires_at,
                                "id_token": fallback_id_token,
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch("app.services.codex_oauth.settings.codex_oauth_token_sink_enabled", True),
                patch("app.services.codex_oauth.settings.codex_oauth_token_sink_fallback_profiles", "backup"),
                patch("app.services.codex_oauth._resolve_token_sink_path", return_value=sink_path),
                patch("app.services.codex_oauth._has_valid_codex_cli_auth", return_value=False),
            ):
                claims_context = codex_oauth_service.get_token_sink_claims_context()
                has_valid_sink = codex_oauth_service.has_valid_token_sink()

        self.assertTrue(claims_context.has_valid_token_sink)
        self.assertTrue(claims_context.from_token_sink)
        self.assertEqual(claims_context.claims.get("sub"), "valid-backup-after-revoked-active-sub")
        self.assertNotEqual(claims_context.claims.get("sub"), "revoked-active-profile-sub")
        metadata = self.assertTokenSinkProfileMetadata(
            claims_context,
            profile_name="backup",
            expires_at=fallback_expires_at,
            fallback_used=True,
        )
        self.assertNoSensitiveTokenSinkMetadata(
            metadata,
            forbidden_values=(
                "revoked-active-access-token",
                "valid-backup-access-token",
                active_id_token,
                fallback_id_token,
                "revoked-active-profile@example.test",
                "valid-backup-after-revoked-active@example.test",
            ),
        )
        self.assertTrue(has_valid_sink)

    def test_token_sink_claims_context_rejects_revoked_fallback_profile(self):
        now = int(time.time())
        active_expires_at = now - 60
        fallback_expires_at = now + 3600
        active_id_token = _fake_signed_jwt(
            {
                "sub": "expired-active-before-revoked-fallback-sub",
                "email": "expired-active-before-revoked-fallback@example.test",
                "email_verified": True,
            }
        )
        fallback_id_token = _fake_signed_jwt(
            {
                "sub": "revoked-fallback-profile-sub",
                "email": "revoked-fallback-profile@example.test",
                "email_verified": True,
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            sink_path = Path(tmpdir) / "auth.json"
            sink_path.write_text(
                json.dumps(
                    {
                        "schema_version": "codex_oauth_sink.v1",
                        "active_profile": "work",
                        "profiles": {
                            "work": {
                                "access_token": "expired-active-access-token",
                                "expires_at": active_expires_at,
                                "id_token": active_id_token,
                            },
                            "backup": {
                                "access_token": "revoked-fallback-access-token",
                                "expires_at": fallback_expires_at,
                                "id_token": fallback_id_token,
                                "revoked": True,
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch("app.services.codex_oauth.settings.codex_oauth_token_sink_enabled", True),
                patch("app.services.codex_oauth.settings.codex_oauth_token_sink_fallback_profiles", "backup"),
                patch("app.services.codex_oauth._resolve_token_sink_path", return_value=sink_path),
                patch("app.services.codex_oauth._has_valid_codex_cli_auth", return_value=False),
            ):
                claims_context = codex_oauth_service.get_token_sink_claims_context()
                has_valid_sink = codex_oauth_service.has_valid_token_sink()

        self.assertFalse(claims_context.has_valid_token_sink)
        self.assertFalse(claims_context.from_token_sink)
        self.assertEqual(claims_context.claims, {})
        self.assertNoTokenSinkProfileMetadata(claims_context)
        self.assertFalse(has_valid_sink)

    def test_token_sink_fallback_allowlist_skips_revoked_profiles(self):
        now = int(time.time())
        active_expires_at = now - 60
        revoked_expires_at = now + 1800
        valid_expires_at = now + 3600
        active_id_token = _fake_signed_jwt(
            {
                "sub": "expired-active-before-allowlist-revoked-sub",
                "email": "expired-active-before-allowlist-revoked@example.test",
                "email_verified": True,
            }
        )
        revoked_id_token = _fake_signed_jwt(
            {
                "sub": "revoked-allowlisted-profile-sub",
                "email": "revoked-allowlisted-profile@example.test",
                "email_verified": True,
            }
        )
        valid_id_token = _fake_signed_jwt(
            {
                "sub": "valid-allowlisted-after-revoked-sub",
                "email": "valid-allowlisted-after-revoked@example.test",
                "email_verified": True,
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            sink_path = Path(tmpdir) / "auth.json"

            def write_sink(*, include_valid_profile: bool) -> None:
                profiles = {
                    "work": {
                        "access_token": "expired-active-access-token",
                        "expires_at": active_expires_at,
                        "id_token": active_id_token,
                    },
                    "revoked-backup": {
                        "access_token": "revoked-allowlisted-access-token",
                        "expires_at": revoked_expires_at,
                        "id_token": revoked_id_token,
                        "revoked_at": "2026-05-24T00:00:00Z",
                    },
                }
                if include_valid_profile:
                    profiles["valid-backup"] = {
                        "access_token": "valid-allowlisted-access-token",
                        "expires_at": valid_expires_at,
                        "id_token": valid_id_token,
                    }
                sink_path.write_text(
                    json.dumps(
                        {
                            "schema_version": "codex_oauth_sink.v1",
                            "active_profile": "work",
                            "profiles": profiles,
                        }
                    ),
                    encoding="utf-8",
                )

            with (
                patch("app.services.codex_oauth.settings.codex_oauth_token_sink_enabled", True),
                patch(
                    "app.services.codex_oauth.settings.codex_oauth_token_sink_fallback_profiles",
                    "revoked-backup,valid-backup",
                ),
                patch("app.services.codex_oauth._resolve_token_sink_path", return_value=sink_path),
                patch("app.services.codex_oauth._has_valid_codex_cli_auth", return_value=False),
            ):
                write_sink(include_valid_profile=False)
                revoked_only_context = codex_oauth_service.get_token_sink_claims_context()
                revoked_only_has_valid_sink = codex_oauth_service.has_valid_token_sink()

                write_sink(include_valid_profile=True)
                valid_context = codex_oauth_service.get_token_sink_claims_context()
                valid_has_valid_sink = codex_oauth_service.has_valid_token_sink()

        self.assertFalse(revoked_only_context.has_valid_token_sink)
        self.assertFalse(revoked_only_context.from_token_sink)
        self.assertEqual(revoked_only_context.claims, {})
        self.assertNoTokenSinkProfileMetadata(revoked_only_context)
        self.assertFalse(revoked_only_has_valid_sink)

        self.assertTrue(valid_context.has_valid_token_sink)
        self.assertTrue(valid_context.from_token_sink)
        self.assertEqual(valid_context.claims.get("sub"), "valid-allowlisted-after-revoked-sub")
        self.assertNotEqual(valid_context.claims.get("sub"), "revoked-allowlisted-profile-sub")
        metadata = self.assertTokenSinkProfileMetadata(
            valid_context,
            profile_name="valid-backup",
            expires_at=valid_expires_at,
            fallback_used=True,
        )
        self.assertNoSensitiveTokenSinkMetadata(
            metadata,
            forbidden_values=(
                "expired-active-access-token",
                "revoked-allowlisted-access-token",
                "valid-allowlisted-access-token",
                active_id_token,
                revoked_id_token,
                valid_id_token,
                "expired-active-before-allowlist-revoked@example.test",
                "revoked-allowlisted-profile@example.test",
                "valid-allowlisted-after-revoked@example.test",
            ),
        )
        self.assertTrue(valid_has_valid_sink)

    def test_token_sink_claims_context_does_not_treat_false_revoked_markers_as_revoked(self):
        now = int(time.time())
        active_expires_at = now + 3600
        active_id_token = _fake_signed_jwt(
            {
                "sub": "not-revoked-active-profile-sub",
                "email": "not-revoked-active-profile@example.test",
                "email_verified": True,
            }
        )

        false_marker_cases = [
            {"revoked": False},
            {"revoked_at": 0},
            {"revoked_at": "0"},
            {"revoked_at": ""},
            {"revoked_at": "false"},
        ]

        for marker in false_marker_cases:
            with self.subTest(marker=marker):
                with tempfile.TemporaryDirectory() as tmpdir:
                    sink_path = Path(tmpdir) / "auth.json"
                    sink_path.write_text(
                        json.dumps(
                            {
                                "schema_version": "codex_oauth_sink.v1",
                                "active_profile": "work",
                                "profiles": {
                                    "work": {
                                        "access_token": "not-revoked-active-access-token",
                                        "expires_at": active_expires_at,
                                        "id_token": active_id_token,
                                        **marker,
                                    },
                                },
                            }
                        ),
                        encoding="utf-8",
                    )

                    with (
                        patch("app.services.codex_oauth.settings.codex_oauth_token_sink_enabled", True),
                        patch("app.services.codex_oauth._resolve_token_sink_path", return_value=sink_path),
                        patch("app.services.codex_oauth._has_valid_codex_cli_auth", return_value=False),
                    ):
                        claims_context = codex_oauth_service.get_token_sink_claims_context()
                        has_valid_sink = codex_oauth_service.has_valid_token_sink()

                self.assertTrue(claims_context.has_valid_token_sink)
                self.assertTrue(claims_context.from_token_sink)
                self.assertEqual(claims_context.claims.get("sub"), "not-revoked-active-profile-sub")
                self.assertTokenSinkProfileMetadata(
                    claims_context,
                    profile_name="work",
                    expires_at=active_expires_at,
                    fallback_used=False,
                )
                self.assertTrue(has_valid_sink)

    def test_revoke_token_sink_profile_marks_active_profile_and_preserves_fallback(self):
        now = int(time.time())
        active_expires_at = now + 3600
        fallback_expires_at = now + 7200
        active_id_token = _fake_signed_jwt(
            {
                "sub": "profile-revoke-active-sub",
                "email": "profile-revoke-active@example.test",
                "email_verified": True,
            }
        )
        fallback_id_token = _fake_signed_jwt(
            {
                "sub": "profile-revoke-fallback-sub",
                "email": "profile-revoke-fallback@example.test",
                "email_verified": True,
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            sink_path = Path(tmpdir) / "auth.json"
            sink_path.write_text(
                json.dumps(
                    {
                        "schema_version": "codex_oauth_sink.v1",
                        "active_profile": "work",
                        "profiles": {
                            "work": {
                                "access_token": "active-profile-revoke-access-token",
                                "refresh_token": "active-profile-revoke-refresh-token",
                                "expires_at": active_expires_at,
                                "id_token": active_id_token,
                            },
                            "backup": {
                                "access_token": "backup-profile-preserved-access-token",
                                "refresh_token": "backup-profile-preserved-refresh-token",
                                "expires_at": fallback_expires_at,
                                "id_token": fallback_id_token,
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch("app.services.codex_oauth.settings.codex_oauth_token_sink_enabled", True),
                patch("app.services.codex_oauth.settings.codex_oauth_token_sink_fallback_profiles", "backup"),
                patch("app.services.codex_oauth._resolve_token_sink_path", return_value=sink_path),
                patch("app.services.codex_oauth._has_valid_codex_cli_auth", return_value=False),
            ):
                result = codex_oauth_service.revoke_token_sink_profile()
                claims_context = codex_oauth_service.get_token_sink_claims_context()
                has_valid_sink = codex_oauth_service.has_valid_token_sink()

            updated_sink = json.loads(sink_path.read_text(encoding="utf-8"))

        serialized_result = json.dumps(result, default=str, sort_keys=True)
        self.assertTrue(result["revoked"])
        self.assertEqual(result["reason"], "revoked")
        self.assertEqual(result["profile_name"], "redacted")
        self.assertNotIn("work", serialized_result)
        self.assertNotIn("active-profile-revoke-access-token", serialized_result)
        self.assertNotIn(active_id_token, serialized_result)
        active_profile = updated_sink["profiles"]["work"]
        backup_profile = updated_sink["profiles"]["backup"]
        self.assertTrue(active_profile["revoked"])
        self.assertIsInstance(active_profile["revoked_at"], int)
        self.assertNotIn("access_token", active_profile)
        self.assertNotIn("refresh_token", active_profile)
        self.assertNotIn("id_token", active_profile)
        self.assertEqual(backup_profile["access_token"], "backup-profile-preserved-access-token")
        self.assertEqual(backup_profile["id_token"], fallback_id_token)
        self.assertTrue(claims_context.has_valid_token_sink)
        self.assertTrue(claims_context.from_token_sink)
        self.assertEqual(claims_context.claims.get("sub"), "profile-revoke-fallback-sub")
        self.assertTokenSinkProfileMetadata(
            claims_context,
            profile_name="backup",
            expires_at=fallback_expires_at,
            fallback_used=True,
        )
        self.assertTrue(has_valid_sink)

    def test_persist_token_sink_atomic_write_preserves_existing_profiles_and_full_json(self):
        now = int(time.time())
        existing_id_token = _fake_signed_jwt(
            {
                "sub": "persist-existing-sub",
                "email": "persist-existing@example.test",
                "email_verified": True,
            }
        )
        active_id_token = _fake_signed_jwt(
            {
                "sub": "persist-active-sub",
                "email": "persist-active@example.test",
                "email_verified": True,
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            sink_path = Path(tmpdir) / "nested" / "auth.json"
            sink_path.parent.mkdir(parents=True)
            lock_calls: list[bool] = []
            existing_payload = {
                "schema_version": "codex_oauth_sink.v1",
                "active_profile": "backup",
                "profiles": {
                    "backup": {
                        "provider": "openai",
                        "access_token": "existing-access-token",
                        "refresh_token": "existing-refresh-token",
                        "token_type": "Bearer",
                        "scope": "openid email",
                        "expires_at": now + 7200,
                        "created_at": now - 120,
                        "id_token": existing_id_token,
                    },
                },
                "updated_at": now - 120,
            }
            sink_path.write_text(json.dumps(existing_payload), encoding="utf-8")

            with (
                patch("app.services.codex_oauth.settings.codex_oauth_token_sink_profile", "work"),
                patch("app.services.codex_oauth._resolve_token_sink_path", return_value=sink_path),
                patch(
                    "app.services.codex_oauth._token_sink_file_lock",
                    _recording_token_sink_file_lock(lock_calls),
                    create=True,
                ),
            ):
                codex_oauth_service.persist_token_sink(
                    {
                        "provider": "openai",
                        "access_token": "active-access-token",
                        "refresh_token": "active-refresh-token",
                        "token_type": "Bearer",
                        "scope": "openid email profile",
                        "expires_at": now + 3600,
                        "created_at": now,
                        "id_token": active_id_token,
                    }
                )

            persisted_payload = json.loads(sink_path.read_text(encoding="utf-8"))
            sink_mode = sink_path.stat().st_mode & 0o777
            leftover_temp_files = list(sink_path.parent.glob(f".{sink_path.name}.*.tmp"))

        self.assertEqual(persisted_payload["schema_version"], "codex_oauth_sink.v1")
        self.assertIn(True, lock_calls)
        self.assertNotIn(False, lock_calls)
        self.assertEqual(persisted_payload["active_profile"], "work")
        self.assertIsInstance(persisted_payload["updated_at"], int)
        self.assertEqual(sink_mode, 0o600)
        self.assertEqual(leftover_temp_files, [])
        self.assertEqual(set(persisted_payload["profiles"]), {"backup", "work"})
        self.assertEqual(persisted_payload["profiles"]["backup"], existing_payload["profiles"]["backup"])
        self.assertEqual(
            persisted_payload["profiles"]["work"],
            {
                "provider": "openai",
                "access_token": "active-access-token",
                "refresh_token": "active-refresh-token",
                "token_type": "Bearer",
                "scope": "openid email profile",
                "expires_at": now + 3600,
                "created_at": now,
                "id_token": active_id_token,
            },
        )

    def test_persist_token_sink_path_safety_rejects_symlink_sink_without_touching_target(self):
        now = int(time.time())
        target_payload = {
            "schema_version": "codex_oauth_sink.v1",
            "active_profile": "target",
            "profiles": {
                "target": {
                    "provider": "openai",
                    "access_token": "target-access-token",
                    "expires_at": now + 3600,
                    "created_at": now,
                },
            },
            "updated_at": now,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target_path = root / "target-auth.json"
            sink_path = root / "auth.json"
            target_path.write_text(json.dumps(target_payload), encoding="utf-8")
            sink_path.symlink_to(target_path)

            with (
                patch("app.services.codex_oauth.settings.codex_oauth_token_sink_profile", "work"),
                patch("app.services.codex_oauth._resolve_token_sink_path", return_value=sink_path),
            ):
                try:
                    codex_oauth_service.persist_token_sink(
                        {
                            "provider": "openai",
                            "access_token": "unsafe-symlink-access-token",
                            "refresh_token": "unsafe-symlink-refresh-token",
                            "token_type": "Bearer",
                            "scope": "openid email",
                            "expires_at": now + 7200,
                            "created_at": now,
                        }
                    )
                except (OSError, ValueError, PermissionError):
                    pass

            persisted_target = json.loads(target_path.read_text(encoding="utf-8"))
            sink_is_symlink = sink_path.is_symlink()

        self.assertTrue(sink_is_symlink)
        self.assertEqual(persisted_target, target_payload)
        self.assertNotIn("work", persisted_target.get("profiles", {}))

    def test_read_token_sink_path_safety_returns_none_for_symlink_sink(self):
        now = int(time.time())
        target_payload = {
            "schema_version": "codex_oauth_sink.v1",
            "active_profile": "work",
            "profiles": {
                "work": {
                    "provider": "openai",
                    "access_token": "symlink-target-access-token",
                    "refresh_token": "symlink-target-refresh-token",
                    "token_type": "Bearer",
                    "scope": "openid email",
                    "expires_at": now + 3600,
                    "created_at": now,
                },
            },
            "updated_at": now,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target_path = root / "target-auth.json"
            sink_path = root / "auth.json"
            target_path.write_text(json.dumps(target_payload), encoding="utf-8")
            sink_path.symlink_to(target_path)

            with patch("app.services.codex_oauth._resolve_token_sink_path", return_value=sink_path):
                raw_payload = codex_oauth_service._read_token_sink_file()
                profile_payload = codex_oauth_service.read_token_sink()

        self.assertIsNone(raw_payload)
        self.assertIsNone(profile_payload)

    def test_persist_token_sink_path_safety_rejects_group_world_writable_parent(self):
        now = int(time.time())

        with tempfile.TemporaryDirectory() as tmpdir:
            parent = Path(tmpdir) / "unsafe-parent"
            parent.mkdir()
            sink_path = parent / "auth.json"
            original_mode = parent.stat().st_mode & 0o777
            parent.chmod(0o777)
            try:
                with (
                    patch("app.services.codex_oauth.settings.codex_oauth_token_sink_profile", "work"),
                    patch("app.services.codex_oauth._resolve_token_sink_path", return_value=sink_path),
                ):
                    try:
                        codex_oauth_service.persist_token_sink(
                            {
                                "provider": "openai",
                                "access_token": "unsafe-parent-access-token",
                                "refresh_token": "unsafe-parent-refresh-token",
                                "token_type": "Bearer",
                                "scope": "openid email",
                                "expires_at": now + 3600,
                                "created_at": now,
                            }
                        )
                    except (OSError, ValueError, PermissionError):
                        pass
                sink_exists = sink_path.exists() or sink_path.is_symlink()
                leftover_temp_files = list(parent.glob(f".{sink_path.name}.*.tmp"))
            finally:
                parent.chmod(original_mode)

        self.assertFalse(sink_exists)
        self.assertEqual(leftover_temp_files, [])

    def test_token_sink_advisory_file_lock_read_and_select_paths_use_shared_lock(self):
        now = int(time.time())
        active_id_token = _fake_signed_jwt(
            {
                "sub": "shared-lock-active-sub",
                "email": "shared-lock-active@example.test",
                "email_verified": True,
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            sink_path = Path(tmpdir) / "auth.json"
            sink_path.write_text(
                json.dumps(
                    {
                        "schema_version": "codex_oauth_sink.v1",
                        "active_profile": "work",
                        "profiles": {
                            "work": {
                                "provider": "openai",
                                "access_token": "shared-lock-access-token",
                                "refresh_token": "shared-lock-refresh-token",
                                "token_type": "Bearer",
                                "scope": "openid email",
                                "expires_at": now + 3600,
                                "created_at": now,
                                "id_token": active_id_token,
                            },
                        },
                        "updated_at": now,
                    }
                ),
                encoding="utf-8",
            )
            lock_calls: list[bool] = []

            with (
                patch("app.services.codex_oauth.settings.codex_oauth_token_sink_enabled", True),
                patch("app.services.codex_oauth._resolve_token_sink_path", return_value=sink_path),
                patch(
                    "app.services.codex_oauth._token_sink_file_lock",
                    _recording_token_sink_file_lock(lock_calls),
                    create=True,
                ),
            ):
                profile_payload = codex_oauth_service.read_token_sink()
                claims_context = codex_oauth_service.get_token_sink_claims_context()

        self.assertEqual(profile_payload["access_token"], "shared-lock-access-token")
        self.assertTrue(claims_context.has_valid_token_sink)
        self.assertEqual(claims_context.claims.get("sub"), "shared-lock-active-sub")
        self.assertGreaterEqual(lock_calls.count(False), 2)
        self.assertNotIn(True, lock_calls)

    def test_revoke_token_sink_profile_atomic_write_failed_is_safe_and_non_leaking(self):
        now = int(time.time())
        active_id_token = _fake_signed_jwt(
            {
                "sub": "profile-revoke-write-failed-sub",
                "email": "profile-revoke-write-failed@example.test",
                "email_verified": True,
            }
        )
        original_payload = {
            "schema_version": "codex_oauth_sink.v1",
            "active_profile": "alice-work",
            "profiles": {
                "alice-work": {
                    "access_token": "write-failed-access-token",
                    "refresh_token": "write-failed-refresh-token",
                    "expires_at": now + 3600,
                    "id_token": active_id_token,
                },
                "backup": {
                    "access_token": "write-failed-backup-access-token",
                    "expires_at": now + 7200,
                },
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            sink_path = Path(tmpdir) / "auth.json"
            sink_path.write_text(json.dumps(original_payload), encoding="utf-8")
            lock_calls: list[bool] = []

            with (
                patch("app.services.codex_oauth._resolve_token_sink_path", return_value=sink_path),
                patch(
                    "app.services.codex_oauth._token_sink_file_lock",
                    _recording_token_sink_file_lock(lock_calls),
                    create=True,
                ),
                patch(
                    "app.services.codex_oauth._write_token_sink_file",
                    side_effect=OSError("simulated atomic replace failure"),
                    create=True,
                ),
            ):
                result = codex_oauth_service.revoke_token_sink_profile()

            persisted_payload = json.loads(sink_path.read_text(encoding="utf-8"))

        serialized_result = json.dumps(result, default=str, sort_keys=True)
        self.assertFalse(result["revoked"])
        self.assertEqual(result["reason"], "write_failed")
        self.assertEqual(result["profile_name"], "redacted")
        self.assertIn(True, lock_calls)
        self.assertNotIn(False, lock_calls)
        self.assertNotIn("alice-work", serialized_result)
        self.assertNotIn("write-failed-access-token", serialized_result)
        self.assertNotIn("write-failed-refresh-token", serialized_result)
        self.assertNotIn(active_id_token, serialized_result)
        self.assertEqual(persisted_payload, original_payload)

    def test_revoke_token_sink_profile_explicit_missing_profile_is_safe_and_non_leaking(self):
        now = int(time.time())
        active_id_token = _fake_signed_jwt(
            {
                "sub": "profile-revoke-explicit-active-sub",
                "email": "profile-revoke-explicit-active@example.test",
                "email_verified": True,
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            sink_path = Path(tmpdir) / "auth.json"
            original_payload = {
                "schema_version": "codex_oauth_sink.v1",
                "active_profile": "work",
                "profiles": {
                    "work": {
                        "access_token": "explicit-active-access-token",
                        "expires_at": now + 3600,
                        "id_token": active_id_token,
                    },
                },
            }
            sink_path.write_text(json.dumps(original_payload), encoding="utf-8")

            with patch("app.services.codex_oauth._resolve_token_sink_path", return_value=sink_path):
                result = codex_oauth_service.revoke_token_sink_profile(profile_name="alice-work")

            updated_payload = json.loads(sink_path.read_text(encoding="utf-8"))

        serialized_result = json.dumps(result, default=str, sort_keys=True)
        self.assertFalse(result["revoked"])
        self.assertEqual(result["reason"], "profile_missing")
        self.assertEqual(result["profile_name"], "redacted")
        self.assertNotIn("alice-work", serialized_result)
        self.assertEqual(updated_payload, original_payload)

    def test_revoke_session_reports_missing_token_sink_without_leaking_inputs(self):
        session_id = "local-revoke-session-id"
        with tempfile.TemporaryDirectory() as tmpdir:
            sink_path = Path(tmpdir) / "missing-auth.json"
            with codex_oauth_service._STATE_LOCK:
                codex_oauth_service._ACTIVE_SESSIONS[session_id] = CodexSession(
                    session_id=session_id,
                    access_token="local-revoke-session-access-token",
                    token_type="Bearer",
                    scope="openid",
                    created_at=100,
                    expires_at=200,
                )

            with patch("app.services.codex_oauth._resolve_token_sink_path", return_value=sink_path):
                result = codex_oauth_service.revoke_session(session_id)

            remaining_session = codex_oauth_service.get_session(session_id)

        serialized_result = json.dumps(result, default=str, sort_keys=True)
        self.assertTrue(result["session_present"])
        self.assertTrue(result["session_revoked"])
        self.assertTrue(result["token_sink_attempted"])
        self.assertFalse(result["token_sink_revoked"])
        self.assertEqual(result["token_sink_reason"], "missing")
        self.assertEqual(
            result["provider_revoke"],
            {"attempted": False, "revoked": False, "reason": "not_configured"},
        )
        self.assertIsNone(remaining_session)
        self.assertNotIn(session_id, serialized_result)
        self.assertNotIn("local-revoke-session-access-token", serialized_result)
        self.assertNotIn(str(sink_path), serialized_result)
        self.assertNotIn(tmpdir, serialized_result)

    def test_revoke_session_provider_revoke_success_uses_live_session_token_without_leaking_it(self):
        session_id = "provider-live-session-id"
        live_access_token = "provider-live-access-token-secret"
        sink_access_token = "provider-sink-access-token-secret"
        calls: list[dict[str, object]] = []
        with tempfile.TemporaryDirectory() as tmpdir:
            sink_path = Path(tmpdir) / "auth.json"
            sink_path.write_text(
                json.dumps(
                    {
                        "schema_version": "codex_oauth_sink.v1",
                        "active_profile": "work",
                        "profiles": {
                            "work": {
                                "access_token": sink_access_token,
                                "expires_at": int(time.time()) + 3600,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            with codex_oauth_service._STATE_LOCK:
                codex_oauth_service._ACTIVE_SESSIONS[session_id] = CodexSession(
                    session_id=session_id,
                    access_token=live_access_token,
                    token_type="Bearer",
                    scope="openid",
                    created_at=100,
                    expires_at=200,
                )

            with (
                patch("app.services.codex_oauth.settings.codex_oauth_provider_revoke_url", "https://provider.example/revoke"),
                patch("app.services.codex_oauth._resolve_token_sink_path", return_value=sink_path),
                patch(
                    "app.services.codex_oauth.httpx.Client",
                    lambda *args, **kwargs: _FakeProviderRevokeClient(calls, status_code=200),
                ),
            ):
                result = codex_oauth_service.revoke_session(session_id)

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["url"], "https://provider.example/revoke")
        self.assertEqual((calls[0]["data"] or {}).get("token"), live_access_token)
        self.assertNotEqual((calls[0]["data"] or {}).get("token"), sink_access_token)
        self.assertEqual(
            result["provider_revoke"],
            {"attempted": True, "revoked": True, "reason": "revoked", "status_code": 200},
        )
        serialized_result = json.dumps(result, default=str, sort_keys=True)
        self.assertNotIn(live_access_token, serialized_result)
        self.assertNotIn(sink_access_token, serialized_result)
        self.assertNotIn(session_id, serialized_result)
        self.assertNotIn("https://provider.example/revoke", serialized_result)
        self.assertTrue(result["token_sink_revoked"])

    def test_revoke_session_provider_revoke_uses_token_sink_when_live_session_missing(self):
        sink_access_token = "provider-fallback-sink-access-token-secret"
        calls: list[dict[str, object]] = []
        with tempfile.TemporaryDirectory() as tmpdir:
            sink_path = Path(tmpdir) / "auth.json"
            sink_path.write_text(
                json.dumps(
                    {
                        "schema_version": "codex_oauth_sink.v1",
                        "active_profile": "work",
                        "profiles": {
                            "work": {
                                "access_token": sink_access_token,
                                "expires_at": int(time.time()) + 3600,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch("app.services.codex_oauth.settings.codex_oauth_provider_revoke_url", "https://provider.example/revoke"),
                patch("app.services.codex_oauth._resolve_token_sink_path", return_value=sink_path),
                patch(
                    "app.services.codex_oauth.httpx.Client",
                    lambda *args, **kwargs: _FakeProviderRevokeClient(calls, status_code=204),
                ),
            ):
                result = codex_oauth_service.revoke_session("missing-live-session")

        self.assertEqual(len(calls), 1)
        self.assertEqual((calls[0]["data"] or {}).get("token"), sink_access_token)
        self.assertEqual(
            result["provider_revoke"],
            {"attempted": True, "revoked": True, "reason": "revoked", "status_code": 204},
        )
        serialized_result = json.dumps(result, default=str, sort_keys=True)
        self.assertNotIn(sink_access_token, serialized_result)
        self.assertNotIn("missing-live-session", serialized_result)
        self.assertTrue(result["token_sink_revoked"])

    def test_revoke_session_provider_revoke_http_failure_does_not_block_local_revoke_or_leak_token(self):
        session_id = "provider-http-fail-session-id"
        live_access_token = "provider-http-fail-access-token-secret"
        calls: list[dict[str, object]] = []
        with tempfile.TemporaryDirectory() as tmpdir:
            sink_path = Path(tmpdir) / "auth.json"
            sink_path.write_text(json.dumps({"profiles": {"work": {"access_token": "local-token"}}}), encoding="utf-8")
            with codex_oauth_service._STATE_LOCK:
                codex_oauth_service._ACTIVE_SESSIONS[session_id] = CodexSession(
                    session_id=session_id,
                    access_token=live_access_token,
                    token_type="Bearer",
                    scope="openid",
                    created_at=100,
                    expires_at=200,
                )

            with (
                patch("app.services.codex_oauth.settings.codex_oauth_provider_revoke_url", "https://provider.example/revoke"),
                patch("app.services.codex_oauth._resolve_token_sink_path", return_value=sink_path),
                patch(
                    "app.services.codex_oauth.httpx.Client",
                    lambda *args, **kwargs: _FakeProviderRevokeClient(calls, status_code=503),
                ),
            ):
                result = codex_oauth_service.revoke_session(session_id)

        self.assertEqual(len(calls), 1)
        self.assertEqual(
            result["provider_revoke"],
            {"attempted": True, "revoked": False, "reason": "http_failed", "status_code": 503},
        )
        self.assertTrue(result["token_sink_revoked"])
        serialized_result = json.dumps(result, default=str, sort_keys=True)
        self.assertNotIn(live_access_token, serialized_result)
        self.assertNotIn(session_id, serialized_result)

    def test_revoke_session_provider_revoke_exception_does_not_block_logout_or_leak_exception_text(self):
        session_id = "provider-request-fail-session-id"
        live_access_token = "provider-request-fail-access-token-secret"
        raw_exception_message = "boom provider-request-fail-access-token-secret /tmp/provider-revoke/path"
        calls: list[dict[str, object]] = []
        with tempfile.TemporaryDirectory() as tmpdir:
            sink_path = Path(tmpdir) / "auth.json"
            sink_path.write_text(json.dumps({"profiles": {"work": {"access_token": "local-token"}}}), encoding="utf-8")
            with codex_oauth_service._STATE_LOCK:
                codex_oauth_service._ACTIVE_SESSIONS[session_id] = CodexSession(
                    session_id=session_id,
                    access_token=live_access_token,
                    token_type="Bearer",
                    scope="openid",
                    created_at=100,
                    expires_at=200,
                )

            with (
                patch("app.services.codex_oauth.settings.codex_oauth_provider_revoke_url", "https://provider.example/revoke"),
                patch("app.services.codex_oauth._resolve_token_sink_path", return_value=sink_path),
                patch(
                    "app.services.codex_oauth.httpx.Client",
                    lambda *args, **kwargs: _FakeProviderRevokeClient(
                        calls,
                        exception=RuntimeError(raw_exception_message),
                    ),
                ),
            ):
                result = codex_oauth_service.revoke_session(session_id)

        self.assertEqual(len(calls), 1)
        self.assertEqual(
            result["provider_revoke"],
            {"attempted": True, "revoked": False, "reason": "request_failed"},
        )
        self.assertTrue(result["token_sink_revoked"])
        serialized_result = json.dumps(result, default=str, sort_keys=True)
        self.assertNotIn(live_access_token, serialized_result)
        self.assertNotIn(session_id, serialized_result)
        self.assertNotIn(raw_exception_message, serialized_result)
        self.assertNotIn("/tmp/provider-revoke/path", serialized_result)

    def test_logout_provider_revoke_exception_returns_200_with_safe_evidence(self):
        session_id = "provider-logout-request-fail-session-id"
        live_access_token = "provider-logout-request-fail-access-token-secret"
        raw_exception_message = "boom provider-logout-request-fail-access-token-secret /tmp/logout-provider-revoke/path"
        calls: list[dict[str, object]] = []
        with tempfile.TemporaryDirectory() as tmpdir:
            sink_path = Path(tmpdir) / "auth.json"
            sink_path.write_text(json.dumps({"profiles": {"work": {"access_token": "local-token"}}}), encoding="utf-8")
            with codex_oauth_service._STATE_LOCK:
                codex_oauth_service._ACTIVE_SESSIONS[session_id] = CodexSession(
                    session_id=session_id,
                    access_token=live_access_token,
                    token_type="Bearer",
                    scope="openid",
                    created_at=100,
                    expires_at=200,
                )

            with (
                patch("app.services.codex_oauth.settings.codex_oauth_provider_revoke_url", "https://provider.example/revoke"),
                patch("app.services.codex_oauth._resolve_token_sink_path", return_value=sink_path),
                patch(
                    "app.services.codex_oauth.httpx.Client",
                    lambda *args, **kwargs: _FakeProviderRevokeClient(
                        calls,
                        exception=RuntimeError(raw_exception_message),
                    ),
                ),
            ):
                logout_resp = self.client.post(
                    "/api/v1/codex-auth/logout",
                    headers=self.headers,
                    cookies={"codex_session": session_id},
                )

        self.assertEqual(logout_resp.status_code, 200)
        body = logout_resp.json()
        revoke_result = (body.get("data") or {}).get("revoke") or {}
        self.assertEqual(
            revoke_result.get("provider_revoke"),
            {"attempted": True, "revoked": False, "reason": "request_failed"},
        )
        self.assertTrue(revoke_result.get("token_sink_revoked"))
        serialized_body = json.dumps(body, default=str, sort_keys=True)
        self.assertIn("provider_revoke", serialized_body)
        self.assertIn("request_failed", serialized_body)
        self.assertNotIn(live_access_token, serialized_body)
        self.assertNotIn(session_id, serialized_body)
        self.assertNotIn(raw_exception_message, serialized_body)
        self.assertNotIn("/tmp/logout-provider-revoke/path", serialized_body)
        self.assertNotIn("https://provider.example/revoke", serialized_body)

    def test_revoke_session_reports_successful_token_sink_unlink_without_leaking_file_details(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sink_path = Path(tmpdir) / "auth.json"
            sink_path.write_text(
                json.dumps(
                    {
                        "profiles": {
                            "work": {
                                "access_token": "unlink-revoke-access-token",
                                "refresh_token": "unlink-revoke-refresh-token",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            with patch("app.services.codex_oauth._resolve_token_sink_path", return_value=sink_path):
                result = codex_oauth_service.revoke_session(None)

            sink_exists = sink_path.exists()

        serialized_result = json.dumps(result, default=str, sort_keys=True)
        self.assertFalse(result["session_present"])
        self.assertFalse(result["session_revoked"])
        self.assertTrue(result["token_sink_attempted"])
        self.assertTrue(result["token_sink_revoked"])
        self.assertEqual(result["token_sink_reason"], "revoked")
        self.assertEqual(
            result["provider_revoke"],
            {"attempted": False, "revoked": False, "reason": "not_configured"},
        )
        self.assertFalse(sink_exists)
        self.assertNotIn("unlink-revoke-access-token", serialized_result)
        self.assertNotIn("unlink-revoke-refresh-token", serialized_result)
        self.assertNotIn(str(sink_path), serialized_result)
        self.assertNotIn(tmpdir, serialized_result)

    def test_revoke_session_reports_unsafe_token_sink_path_without_leaking_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = Path(tmpdir) / "target"
            symlink_parent = Path(tmpdir) / "unsafe-parent"
            target_dir.mkdir()
            try:
                symlink_parent.symlink_to(target_dir, target_is_directory=True)
            except OSError as exc:
                raise unittest.SkipTest(f"symlink setup unavailable: {exc}") from exc
            sink_path = symlink_parent / "auth.json"

            with patch("app.services.codex_oauth._resolve_token_sink_path", return_value=sink_path):
                result = codex_oauth_service.revoke_session(None)

        serialized_result = json.dumps(result, default=str, sort_keys=True)
        self.assertFalse(result["session_present"])
        self.assertFalse(result["session_revoked"])
        self.assertTrue(result["token_sink_attempted"])
        self.assertFalse(result["token_sink_revoked"])
        self.assertEqual(result["token_sink_reason"], "path_unsafe")
        self.assertEqual(
            result["provider_revoke"],
            {"attempted": False, "revoked": False, "reason": "not_configured"},
        )
        self.assertNotIn(str(sink_path), serialized_result)
        self.assertNotIn(str(symlink_parent), serialized_result)
        self.assertNotIn(tmpdir, serialized_result)

    def test_revoke_token_sink_profile_api_revokes_explicit_profile_without_leaking_profile_or_tokens(self):
        now = int(time.time())
        active_id_token = _fake_signed_jwt(
            {
                "sub": "profile-revoke-api-active-sub",
                "email": "profile-revoke-api-active@example.test",
                "email_verified": True,
            }
        )
        backup_id_token = _fake_signed_jwt(
            {
                "sub": "profile-revoke-api-backup-sub",
                "email": "profile-revoke-api-backup@example.test",
                "email_verified": True,
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            sink_path = Path(tmpdir) / "auth.json"
            sink_path.write_text(
                json.dumps(
                    {
                        "schema_version": "codex_oauth_sink.v1",
                        "active_profile": "work",
                        "profiles": {
                            "work": {
                                "access_token": "api-active-access-token",
                                "expires_at": now + 3600,
                                "id_token": active_id_token,
                            },
                            "alice-work": {
                                "access_token": "api-profile-revoke-access-token",
                                "refresh_token": "api-profile-revoke-refresh-token",
                                "expires_at": now + 7200,
                                "id_token": backup_id_token,
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            with patch("app.services.codex_oauth._resolve_token_sink_path", return_value=sink_path):
                resp = self.client.post(
                    "/api/v1/codex-auth/token-sink/profile/revoke?profile_name=alice-work",
                    headers=self.headers,
                )

            updated_sink = json.loads(sink_path.read_text(encoding="utf-8"))

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body.get("status"), "ok")
        data = body.get("data") or {}
        serialized_body = json.dumps(body, default=str, sort_keys=True)
        self.assertTrue(data.get("revoked"))
        self.assertEqual(data.get("reason"), "revoked")
        self.assertEqual(data.get("profile_name"), "redacted")
        self.assertNotIn("alice-work", serialized_body)
        self.assertNotIn("api-profile-revoke-access-token", serialized_body)
        self.assertNotIn("api-profile-revoke-refresh-token", serialized_body)
        self.assertNotIn(backup_id_token, serialized_body)
        self.assertFalse(updated_sink["profiles"]["work"].get("revoked", False))
        revoked_profile = updated_sink["profiles"]["alice-work"]
        self.assertTrue(revoked_profile["revoked"])
        self.assertIsInstance(revoked_profile["revoked_at"], int)
        self.assertNotIn("access_token", revoked_profile)
        self.assertNotIn("refresh_token", revoked_profile)
        self.assertNotIn("id_token", revoked_profile)

    def test_token_sink_fallback_allowlist_blocks_unlisted_valid_profile(self):
        now = int(time.time())
        active_expires_at = now - 60
        fallback_expires_at = now + 3600
        active_id_token = _fake_signed_jwt(
            {
                "sub": "expired-active-allowlist-blocked-sub",
                "email": "expired-active-allowlist-blocked@example.test",
                "email_verified": True,
            }
        )
        fallback_id_token = _fake_signed_jwt(
            {
                "sub": "blocked-valid-fallback-profile-sub",
                "email": "blocked-valid-fallback-profile@example.test",
                "email_verified": True,
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            sink_path = Path(tmpdir) / "auth.json"
            sink_path.write_text(
                json.dumps(
                    {
                        "schema_version": "codex_oauth_sink.v1",
                        "active_profile": "work",
                        "profiles": {
                            "work": {
                                "access_token": "expired-active-access-token",
                                "expires_at": active_expires_at,
                                "id_token": active_id_token,
                            },
                            "backup": {
                                "access_token": "blocked-valid-fallback-access-token",
                                "expires_at": fallback_expires_at,
                                "id_token": fallback_id_token,
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch("app.services.codex_oauth.settings.codex_oauth_token_sink_enabled", True),
                patch("app.services.codex_oauth.settings.codex_oauth_token_sink_fallback_profiles", "missing"),
                patch("app.services.codex_oauth._resolve_token_sink_path", return_value=sink_path),
                patch("app.services.codex_oauth._has_valid_codex_cli_auth", return_value=False),
            ):
                claims_context = codex_oauth_service.get_token_sink_claims_context()
                has_valid_sink = codex_oauth_service.has_valid_token_sink()

        self.assertFalse(claims_context.has_valid_token_sink)
        self.assertFalse(claims_context.from_token_sink)
        self.assertEqual(claims_context.claims, {})
        self.assertNoTokenSinkProfileMetadata(claims_context)
        self.assertFalse(has_valid_sink)

    def test_token_sink_fallback_allowlist_selects_allowed_profile_over_earlier_valid_profile(self):
        now = int(time.time())
        active_expires_at = now - 60
        earlier_expires_at = now + 1800
        allowed_expires_at = now + 3600
        active_id_token = _fake_signed_jwt(
            {
                "sub": "expired-active-allowlist-choice-sub",
                "email": "expired-active-allowlist-choice@example.test",
                "email_verified": True,
            }
        )
        earlier_id_token = _fake_signed_jwt(
            {
                "sub": "earlier-valid-fallback-profile-sub",
                "email": "earlier-valid-fallback-profile@example.test",
                "email_verified": True,
            }
        )
        allowed_id_token = _fake_signed_jwt(
            {
                "sub": "allowed-valid-fallback-profile-sub",
                "email": "allowed-valid-fallback-profile@example.test",
                "email_verified": True,
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            sink_path = Path(tmpdir) / "auth.json"
            sink_path.write_text(
                json.dumps(
                    {
                        "schema_version": "codex_oauth_sink.v1",
                        "active_profile": "work",
                        "profiles": {
                            "work": {
                                "access_token": "expired-active-access-token",
                                "expires_at": active_expires_at,
                                "id_token": active_id_token,
                            },
                            "aaa": {
                                "access_token": "earlier-valid-fallback-access-token",
                                "expires_at": earlier_expires_at,
                                "id_token": earlier_id_token,
                            },
                            "backup": {
                                "access_token": "allowed-valid-fallback-access-token",
                                "expires_at": allowed_expires_at,
                                "id_token": allowed_id_token,
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch("app.services.codex_oauth.settings.codex_oauth_token_sink_enabled", True),
                patch("app.services.codex_oauth.settings.codex_oauth_token_sink_fallback_profiles", "backup"),
                patch("app.services.codex_oauth._resolve_token_sink_path", return_value=sink_path),
                patch("app.services.codex_oauth._has_valid_codex_cli_auth", return_value=False),
            ):
                claims_context = codex_oauth_service.get_token_sink_claims_context()
                has_valid_sink = codex_oauth_service.has_valid_token_sink()

        self.assertTrue(claims_context.has_valid_token_sink)
        self.assertTrue(claims_context.from_token_sink)
        self.assertEqual(claims_context.claims.get("sub"), "allowed-valid-fallback-profile-sub")
        self.assertEqual(claims_context.claims.get("email"), "allowed-valid-fallback-profile@example.test")
        self.assertNotEqual(claims_context.claims.get("sub"), "earlier-valid-fallback-profile-sub")
        metadata = self.assertTokenSinkProfileMetadata(
            claims_context,
            profile_name="backup",
            expires_at=allowed_expires_at,
            fallback_used=True,
        )
        self.assertNoSensitiveTokenSinkMetadata(
            metadata,
            forbidden_values=(
                "expired-active-access-token",
                "earlier-valid-fallback-access-token",
                "allowed-valid-fallback-access-token",
                active_id_token,
                earlier_id_token,
                allowed_id_token,
                "expired-active-allowlist-choice@example.test",
                "earlier-valid-fallback-profile@example.test",
                "allowed-valid-fallback-profile@example.test",
            ),
        )
        self.assertTrue(has_valid_sink)

    def test_token_sink_fallback_allowlist_does_not_block_valid_active_profile(self):
        now = int(time.time())
        active_expires_at = now + 3600
        fallback_expires_at = now + 7200
        active_id_token = _fake_signed_jwt(
            {
                "sub": "active-not-allowlisted-profile-sub",
                "email": "active-not-allowlisted-profile@example.test",
                "email_verified": True,
            }
        )
        fallback_id_token = _fake_signed_jwt(
            {
                "sub": "allowlisted-backup-profile-sub",
                "email": "allowlisted-backup-profile@example.test",
                "email_verified": True,
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            sink_path = Path(tmpdir) / "auth.json"
            sink_path.write_text(
                json.dumps(
                    {
                        "schema_version": "codex_oauth_sink.v1",
                        "active_profile": "work",
                        "profiles": {
                            "work": {
                                "access_token": "active-not-allowlisted-access-token",
                                "expires_at": active_expires_at,
                                "id_token": active_id_token,
                            },
                            "backup": {
                                "access_token": "allowlisted-backup-access-token",
                                "expires_at": fallback_expires_at,
                                "id_token": fallback_id_token,
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch("app.services.codex_oauth.settings.codex_oauth_token_sink_enabled", True),
                patch("app.services.codex_oauth.settings.codex_oauth_token_sink_fallback_profiles", "backup"),
                patch("app.services.codex_oauth._resolve_token_sink_path", return_value=sink_path),
                patch("app.services.codex_oauth._has_valid_codex_cli_auth", return_value=False),
            ):
                claims_context = codex_oauth_service.get_token_sink_claims_context()
                has_valid_sink = codex_oauth_service.has_valid_token_sink()

        self.assertTrue(claims_context.has_valid_token_sink)
        self.assertTrue(claims_context.from_token_sink)
        self.assertEqual(claims_context.claims.get("sub"), "active-not-allowlisted-profile-sub")
        self.assertNotEqual(claims_context.claims.get("sub"), "allowlisted-backup-profile-sub")
        self.assertTokenSinkProfileMetadata(
            claims_context,
            profile_name="work",
            expires_at=active_expires_at,
            fallback_used=False,
        )
        self.assertTrue(has_valid_sink)

    def test_token_sink_claims_context_empty_when_all_profiles_invalid(self):
        now = int(time.time())
        expired_id_token = _fake_signed_jwt(
            {
                "sub": "expired-profile-sub",
                "email": "expired-profile@example.test",
                "email_verified": True,
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            sink_path = Path(tmpdir) / "auth.json"
            sink_path.write_text(
                json.dumps(
                    {
                        "schema_version": "codex_oauth_sink.v1",
                        "active_profile": "work",
                        "profiles": {
                            "work": {
                                "access_token": "expired-active-access-token",
                                "expires_at": now - 60,
                                "id_token": expired_id_token,
                            },
                            "default": {
                                "access_token": "",
                                "expires_at": now + 3600,
                                "id_token": expired_id_token,
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch("app.services.codex_oauth.settings.codex_oauth_token_sink_enabled", True),
                patch("app.services.codex_oauth._resolve_token_sink_path", return_value=sink_path),
                patch("app.services.codex_oauth._has_valid_codex_cli_auth", return_value=False),
            ):
                claims_context = codex_oauth_service.get_token_sink_claims_context()
                has_valid_sink = codex_oauth_service.has_valid_token_sink()

        self.assertFalse(claims_context.has_valid_token_sink)
        self.assertFalse(claims_context.from_token_sink)
        self.assertEqual(claims_context.claims, {})
        self.assertFalse(has_valid_sink)

    def test_token_sink_claims_context_rejects_invalid_id_token_trust_claims(self):
        now = int(time.time())
        cases = [
            ("aud", {"aud": "wrong-client"}),
            ("iss", {"iss": "https://evil.example"}),
            ("exp", {"exp": now - 1}),
            ("source", {"source": "browser"}),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            sink_path = Path(tmpdir) / "auth.json"
            for label, invalid_claims in cases:
                with self.subTest(label=label):
                    sink_path.write_text(
                        json.dumps(
                            {
                                "schema_version": "codex_oauth_sink.v1",
                                "active_profile": "work",
                                "profiles": {
                                    "work": {
                                        "access_token": f"token-{label}",
                                        "expires_at": now + 3600,
                                        "id_token": _fake_signed_jwt(
                                            {
                                                **invalid_claims,
                                                "sub": f"invalid-sink-{label}-sub",
                                                "email": f"invalid-sink-{label}@example.test",
                                                "email_verified": True,
                                            }
                                        ),
                                    }
                                },
                            }
                        ),
                        encoding="utf-8",
                    )
                    with patch("app.services.codex_oauth._resolve_token_sink_path", return_value=sink_path):
                        claims_context = codex_oauth_service.get_token_sink_claims_context()

                    self.assertTrue(claims_context.has_valid_token_sink)
                    self.assertTrue(claims_context.from_token_sink)
                    self.assertEqual(claims_context.claims, {})

    def test_token_sink_claims_actor_context_uses_subject_without_live_session(self):
        request = _request_with_headers_and_cookie(
            path="/api/v1/agent-batch/rule-sets/validate",
            headers={**self.headers, "X-Actor-Id": "spoofed-header-actor"},
            cookie_name="codex_session",
            cookie_value="stale-session",
        )
        claims_context = _token_sink_claims_context_from_id_token(
            _fake_signed_jwt(
                {
                    "sub": "token-sink-sub-123",
                    "email": "token-sink@example.test",
                    "email_verified": True,
                }
            )
        )

        with (
            patch("app.main.get_session", return_value=None),
            patch("app.main.has_valid_token_sink", return_value=True),
            patch("app.main.get_token_sink_claims_context", return_value=claims_context),
        ):
            actor_context = backend_main._resolve_codex_oauth_actor_context(request)

        self.assertIsNotNone(actor_context)
        self.assertEqual(actor_context.actor_id, "token-sink-sub-123")
        self.assertEqual(actor_context.actor_source, "authenticated_oauth_token_sink_claims")
        self.assertTrue(actor_context.actor_trusted)
        self.assertEqual(actor_context.actor_auth_mode, "codex_oauth_token_sink_oidc_claims")
        self.assertEqual(actor_context.legacy_actor_id, "spoofed-header-actor")

    def test_token_sink_profile_metadata_observability_is_scoped_to_token_sink(self):
        claims_profile_expires_at = int(time.time()) + 3600
        fixed_profile_expires_at = int(time.time()) + 7200
        claims_id_token = _fake_signed_jwt(
            {
                "sub": "token-sink-metadata-sub",
                "email": "token-sink-metadata@example.test",
                "email_verified": True,
            }
        )

        claims_context = _token_sink_claims_context_from_id_token(
            claims_id_token,
            profile_name="work",
            expires_at=claims_profile_expires_at,
            fallback_used=False,
        )
        request = _request_with_headers_and_cookie(
            path="/api/v1/agent-batch/rule-sets/validate",
            headers={**self.headers, "X-Actor-Id": "spoofed-header-actor"},
            cookie_name="codex_session",
            cookie_value="stale-session",
        )
        with (
            patch("app.main.get_session", return_value=None),
            patch("app.main.has_valid_token_sink", return_value=True),
            patch("app.main.get_token_sink_claims_context", return_value=claims_context),
        ):
            actor_context = backend_main._resolve_codex_oauth_actor_context(request)

        self.assertIsNotNone(actor_context)
        self.assertEqual(actor_context.actor_source, "authenticated_oauth_token_sink_claims")
        claims_observability = actor_context.to_observability()
        claims_metadata = self.assertTokenSinkProfileMetadata(
            claims_observability,
            profile_name="work",
            expires_at=claims_profile_expires_at,
            fallback_used=False,
        )
        self.assertNoSensitiveTokenSinkMetadata(
            claims_metadata,
            forbidden_values=(
                claims_id_token,
                "token-sink-metadata@example.test",
                "claims-access-token",
                "claims-refresh-token",
            ),
        )

        fixed_context = _token_sink_claims_context_from_id_token(
            None,
            profile_name="backup",
            expires_at=fixed_profile_expires_at,
            fallback_used=True,
        )
        fixed_request = _request_with_headers_and_cookie(
            path="/api/v1/agent-batch/rule-sets/validate",
            headers={**self.headers, "X-Actor-Id": "spoofed-header-actor"},
            cookie_name="codex_session",
            cookie_value="stale-session",
        )
        with (
            patch("app.main.get_session", return_value=None),
            patch("app.main.has_valid_token_sink", return_value=True),
            patch("app.main.get_token_sink_claims_context", return_value=fixed_context),
        ):
            fixed_actor_context = backend_main._resolve_codex_oauth_actor_context(fixed_request)

        self.assertIsNotNone(fixed_actor_context)
        self.assertEqual(fixed_actor_context.actor_source, "authenticated_oauth_token_sink")
        fixed_metadata = self.assertTokenSinkProfileMetadata(
            fixed_actor_context.to_observability(),
            profile_name="backup",
            expires_at=fixed_profile_expires_at,
            fallback_used=True,
        )
        self.assertNoSensitiveTokenSinkMetadata(
            fixed_metadata,
            forbidden_values=(
                "fixed-token-sink@example.test",
                "fixed-access-token",
                "fixed-refresh-token",
            ),
        )

        live_session_request = _request_with_headers_and_cookie(
            path="/api/v1/agent-batch/rule-sets/validate",
            headers={**self.headers, "X-Actor-Id": "spoofed-header-actor"},
            cookie_name="codex_session",
            cookie_value="live-session",
        )
        live_session = CodexSession(
            session_id="live-session",
            access_token="live-session-access-token",
            token_type="Bearer",
            scope="openid email",
            created_at=100,
            expires_at=999999,
            claims={
                "sub": "live-session-sub",
                "email": "live-session@example.test",
                "email_verified": True,
            },
        )
        with (
            patch("app.main.get_session", return_value=live_session),
            patch("app.main.get_token_sink_claims_context", side_effect=AssertionError("token sink must not be read")),
            patch("app.main.has_valid_token_sink", side_effect=AssertionError("token sink must not be read")),
        ):
            live_actor_context = backend_main._resolve_codex_oauth_actor_context(live_session_request)

        self.assertIsNotNone(live_actor_context)
        self.assertEqual(live_actor_context.actor_source, "authenticated_oauth_session_claims")
        self.assertNoTokenSinkProfileMetadata(live_actor_context.to_observability())

        cli_fallback_context = codex_oauth_service.TokenSinkClaimsContext(
            has_valid_token_sink=False,
            claims={
                "sub": "cli-should-not-be-used",
                "email": "cli-should-not-be-used@example.test",
                "email_verified": True,
            },
            from_token_sink=False,
            profile_name="cli-profile",
            expires_at=int(time.time()) + 3600,
            fallback_used=False,
        )
        cli_request = _request_with_headers_and_cookie(
            path="/api/v1/agent-batch/rule-sets/validate",
            headers={**self.headers, "X-Actor-Id": "spoofed-header-actor"},
            cookie_name="codex_session",
            cookie_value="stale-session",
        )
        with (
            patch("app.main.get_session", return_value=None),
            patch("app.main.has_valid_token_sink", return_value=True),
            patch("app.main.get_token_sink_claims_context", return_value=cli_fallback_context),
        ):
            cli_actor_context = backend_main._resolve_codex_oauth_actor_context(cli_request)

        self.assertIsNotNone(cli_actor_context)
        self.assertEqual(cli_actor_context.actor_source, "authenticated_oauth_token_sink")
        self.assertNoTokenSinkProfileMetadata(cli_actor_context.to_observability())

    def test_token_sink_claims_actor_context_uses_verified_email_when_subject_missing(self):
        verified_email = "verified-token-sink@example.test"

        def _resolve_from_token_sink():
            request = _request_with_headers_and_cookie(
                path="/api/v1/agent-batch/rule-sets/validate",
                headers={**self.headers, "X-Actor-Id": "spoofed-header-actor"},
                cookie_name="codex_session",
                cookie_value="stale-session",
            )
            claims_context = _token_sink_claims_context_from_id_token(
                _fake_signed_jwt(
                    {
                        "email": verified_email,
                        "email_verified": True,
                    }
                )
            )

            with (
                patch("app.main.get_session", return_value=None),
                patch("app.main.has_valid_token_sink", return_value=True),
                patch("app.main.get_token_sink_claims_context", return_value=claims_context),
            ):
                return backend_main._resolve_codex_oauth_actor_context(request)

        actor_context = _resolve_from_token_sink()
        repeated_actor_context = _resolve_from_token_sink()

        self.assertIsNotNone(actor_context)
        self.assertIsNotNone(repeated_actor_context)
        self.assertNotEqual(actor_context.actor_id, verified_email)
        self.assertTrue(actor_context.actor_id.startswith("codex_oauth_email:"))
        self.assertNotIn(verified_email, actor_context.actor_id)
        self.assertNotIn("@", actor_context.actor_id)
        self.assertEqual(actor_context.actor_id, repeated_actor_context.actor_id)
        self.assertEqual(actor_context.actor_source, "authenticated_oauth_token_sink_claims")
        self.assertEqual(actor_context.actor_auth_mode, "codex_oauth_token_sink_oidc_claims")
        self.assertEqual(actor_context.legacy_actor_id, "spoofed-header-actor")

    def test_token_sink_claims_actor_context_rejects_unverified_email_and_invalid_id_token(self):
        cases = [
            (
                "unverified-email",
                _fake_signed_jwt(
                    {
                        "email": "unverified-token-sink@example.test",
                        "email_verified": False,
                    }
                ),
                "unverified-token-sink@example.test",
            ),
            ("invalid-id-token", "not-an-id-token", "invalid-token-sink@example.test"),
        ]

        for label, id_token, forbidden_actor in cases:
            with self.subTest(label=label):
                request = _request_with_headers_and_cookie(
                    path="/api/v1/agent-batch/rule-sets/validate",
                    headers={**self.headers, "X-Actor-Id": "spoofed-header-actor"},
                    cookie_name="codex_session",
                    cookie_value="stale-session",
                )
                claims_context = _token_sink_claims_context_from_id_token(id_token)

                with (
                    patch("app.main.get_session", return_value=None),
                    patch("app.main.has_valid_token_sink", return_value=True),
                    patch("app.main.get_token_sink_claims_context", return_value=claims_context),
                ):
                    actor_context = backend_main._resolve_codex_oauth_actor_context(request)

                self.assertIsNotNone(actor_context)
                self.assertEqual(actor_context.actor_id, "codex_oauth_token_sink")
                self.assertNotEqual(actor_context.actor_id, forbidden_actor)
                self.assertEqual(actor_context.actor_source, "authenticated_oauth_token_sink")
                self.assertEqual(actor_context.actor_auth_mode, "codex_oauth_token_sink")
                self.assertEqual(actor_context.legacy_actor_id, "spoofed-header-actor")

    def test_cli_auth_fallback_does_not_fabricate_token_sink_claims_actor(self):
        request = _request_with_headers_and_cookie(
            path="/api/v1/agent-batch/rule-sets/validate",
            headers={**self.headers, "X-Actor-Id": "spoofed-header-actor"},
            cookie_name="codex_session",
            cookie_value="stale-session",
        )
        cli_fallback_context = codex_oauth_service.TokenSinkClaimsContext(
            has_valid_token_sink=False,
            claims={
                "sub": "cli-should-not-be-used",
                "email": "cli-should-not-be-used@example.test",
                "email_verified": True,
            },
            from_token_sink=False,
        )

        with (
            patch("app.main.get_session", return_value=None),
            patch("app.main.has_valid_token_sink", return_value=True),
            patch("app.main.get_token_sink_claims_context", return_value=cli_fallback_context),
        ):
            actor_context = backend_main._resolve_codex_oauth_actor_context(request)

        self.assertIsNotNone(actor_context)
        self.assertEqual(actor_context.actor_id, "codex_oauth_token_sink")
        self.assertEqual(actor_context.actor_source, "authenticated_oauth_token_sink")
        self.assertEqual(actor_context.actor_auth_mode, "codex_oauth_token_sink")
        self.assertEqual(actor_context.legacy_actor_id, "spoofed-header-actor")
        self.assertNoTokenSinkProfileMetadata(actor_context.to_observability())

    def test_login_redirects_to_oauth_provider(self):
        with (
            patch("app.api.codex_auth.has_valid_token_sink", return_value=False),
            patch("app.api.codex_auth.codex_oauth_enabled", return_value=True),
            patch("app.api.codex_auth.build_authorize_url", return_value="https://auth.example/authorize?state=abc"),
        ):
            resp = self.client.get("/api/v1/codex-auth/login", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.headers.get("location"), "https://auth.example/authorize?state=abc")

    def test_login_returns_error_envelope_when_oauth_config_missing(self):
        with (
            patch("app.api.codex_auth.has_valid_token_sink", return_value=False),
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

        revoke_result = {
            "session_present": True,
            "session_revoked": True,
            "token_sink_attempted": True,
            "token_sink_revoked": False,
            "token_sink_reason": "missing",
        }
        with patch("app.api.codex_auth.revoke_session", return_value=revoke_result) as revoke_mock:
            logout_resp = self.client.post(
                "/api/v1/codex-auth/logout",
                headers=self.headers,
                cookies={"codex_session": "sid-3"},
            )
        self.assertEqual(logout_resp.status_code, 200)
        body = logout_resp.json()
        data = body.get("data") or {}
        serialized_body = json.dumps(body, default=str, sort_keys=True)
        self.assertEqual(body.get("status"), "ok")
        self.assertTrue(data.get("logged_out"))
        self.assertEqual(data.get("revoke"), revoke_result)
        revoke_mock.assert_called_once_with("sid-3")
        self.assertIn("codex_session", str(logout_resp.headers.get("set-cookie") or ""))
        self.assertIn("Max-Age=0", str(logout_resp.headers.get("set-cookie") or ""))
        self.assertNotIn("sid-3", serialized_body)


if __name__ == "__main__":
    unittest.main()
