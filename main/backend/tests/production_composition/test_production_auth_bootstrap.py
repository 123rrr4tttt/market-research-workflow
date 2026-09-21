"""Focused production tests for the Codex auth bootstrap route chain."""

# ruff: noqa: E402

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient


BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BACKEND_ROOT.parent.parent
for path in (str(BACKEND_ROOT), str(REPOSITORY_ROOT / "src")):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.api.codex_auth import codex_auth_bootstrap_routes
from app.composition.production import (
    load_production_route_bindings,
    ProductionRuntimeBindings,
    RateObservation,
)
from app.main import app as production_app
from app.production_contract import EffectAdmission, EffectClass, ProviderClass
from app.successor_runtime.runtime.ports import ProjectScopeRef
from app.successor_runtime.substrate.postgres.session import compute_scope_digest


pytestmark = pytest.mark.unit


EXPECTED_BOOTSTRAP_ROUTES = frozenset(
    {
        ("GET", "/api/v1/codex-auth/login"),
        ("GET", "/api/v1/codex-auth/callback"),
        ("GET", "/api/v1/codex-auth/status"),
    }
)


def test_checked_in_effect_contract_keeps_bootstrap_surface_fail_closed() -> None:
    bindings = load_production_route_bindings()
    contracts = {binding.operation: binding.effect_contract for binding in bindings}

    for operation in (
        "codex-auth.codex_auth_login",
        "codex-auth.codex_auth_callback",
        "codex-auth.codex_auth_status",
    ):
        contract = contracts[operation]
        assert contract.effect_class is EffectClass.EXTERNAL_AUTH
        assert contract.admitted
        assert contract.external_auth_port == "codex_oauth.bootstrap.v1"

    for operation in (
        "codex-auth.codex_auth_logout",
        "codex-auth.codex_auth_revoke_token_sink_profile",
        "codex-auth.codex_cli_bootstrap",
    ):
        contract = contracts[operation]
        assert contract.effect_class is EffectClass.EXTERNAL_AUTH
        assert contract.admission is EffectAdmission.BLOCKED_UNTIL_EFFECT_BINDING
        assert contract.external_auth_port is None


@dataclass(frozen=True, slots=True)
class FakeScopeResolver:
    def resolve(self, project_key: str) -> ProjectScopeRef:
        schema = "mrw_p_demo"
        incarnation = "project-demo-incarnation"
        return ProjectScopeRef(
            project_key=project_key,
            resolved_schema=schema,
            project_registry_revision=7,
            incarnation=incarnation,
            scope_digest=compute_scope_digest(project_key, schema, 7, incarnation),
        )


@dataclass(frozen=True, slots=True)
class FakeActorScopes:
    def scopes(
        self,
        actor: object,
        operation: str,
        capability_id: str,
        scope: ProjectScopeRef,
    ) -> tuple[str, ...]:
        return ("api:invoke",)


@dataclass(frozen=True, slots=True)
class FakeApprovals:
    def approvals(
        self,
        actor: object,
        operation: str,
        capability_id: str,
        scope: ProjectScopeRef,
        observed_at: object,
        approval_ref: str,
        payload_digest: str,
    ) -> tuple[()]:
        return ()


@dataclass(frozen=True, slots=True)
class FakeRates:
    http_operations: list[str] = field(default_factory=list)

    def observe_http(self, actor: object, operation: str) -> RateObservation:
        self.http_operations.append(operation)
        return RateObservation(request_count=0, window_seconds=60)

    def observe_provider(self, actor: object, operation: str, provider_id: str) -> RateObservation:
        return RateObservation(request_count=0, window_seconds=60)


@dataclass(frozen=True, slots=True)
class FakeProviderCatalog:
    def allowed_provider_ids(self) -> tuple[str, ...]:
        return ("serper",)


@dataclass(frozen=True, slots=True)
class FakeProviderSelection:
    def select(
        self,
        actor: object,
        provider_class: ProviderClass,
        request_payload_bytes: int,
    ) -> object | None:
        return None


@dataclass(frozen=True, slots=True)
class FakeWriter:
    def owner(
        self,
        operation: str,
        project_key: str,
        canonical_owner_ref: str,
        writer_port_kind: str,
        approvals: tuple[object, ...],
    ) -> str | None:
        return None


@dataclass
class SessionRecord:
    session_id: str
    created_at: int = 100
    expires_at: int = 700
    claims: dict[str, object] = field(default_factory=lambda: {"sub": "oauth-subject"})


def _production_settings() -> SimpleNamespace:
    return SimpleNamespace(
        env="production",
        production_allowed_hosts="testserver",
        production_allowed_origins="https://app.example",
        production_trusted_actor_sources="authenticated_oauth_session_claims",
        production_trusted_auth_modes="codex_oauth_session_oidc_claims",
        production_require_tls=True,
        production_allowed_methods="GET,POST",
        production_allowed_content_types="application/json",
        production_max_body_bytes=1024,
        production_http_rate_max_requests=10,
        production_http_rate_window_seconds=60,
        production_provider_rate_max_requests=5,
        production_provider_rate_window_seconds=60,
        production_provider_max_payload_bytes=1024,
        production_metrics_token="metrics-secret",
        codex_auth_enabled=True,
        codex_auth_protected_prefixes="/api/v1/codex-auth/logout,/api/v1/policies",
        codex_oauth_enabled=True,
        codex_oauth_cookie_secure=True,
    )


@pytest.fixture
def production_environment(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    import app.composition.production as production
    from app.settings.config import settings

    values = _production_settings()
    for name, value in vars(values).items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(production, "read_build_identity", lambda: SimpleNamespace(fully_bound=True))
    runtime = ProductionRuntimeBindings(
        project_scope_resolver=FakeScopeResolver(),
        actor_scopes=FakeActorScopes(),
        approvals=FakeApprovals(),
        rate_observations=FakeRates(),
        provider_catalog=FakeProviderCatalog(),
        provider_selection=FakeProviderSelection(),
        canonical_writer=FakeWriter(),
    )
    production_app.state.production_runtime_bindings = runtime
    try:
        yield values
    finally:
        production_app.state.production_runtime_bindings = None
        production_app.state.production_observability_r7 = None


def _dependencies(route: APIRoute) -> tuple[str, ...]:
    return tuple(
        getattr(dependency.call, "__name__", repr(dependency.call))
        for dependency in route.dependant.dependencies
    )


def test_bootstrap_surface_is_exact_and_excluded_from_production_policy(
    production_environment: SimpleNamespace,
) -> None:
    assert codex_auth_bootstrap_routes() == EXPECTED_BOOTSTRAP_ROUTES
    for method, path in sorted(EXPECTED_BOOTSTRAP_ROUTES):
        routes = [
            route
            for route in production_app.routes
            if isinstance(route, APIRoute) and route.path == path and method in route.methods
        ]
        assert len(routes) == 1
        assert _dependencies(routes[0]) == ()

    logout_routes = [
        route
        for route in production_app.routes
        if isinstance(route, APIRoute)
        and route.path == "/api/v1/codex-auth/logout"
        and "POST" in route.methods
    ]
    assert len(logout_routes) == 1
    assert "require_production_policy" in _dependencies(logout_routes[0])


def test_anonymous_bootstrap_is_reachable_and_business_api_fails_closed(
    production_environment: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.api.codex_auth as codex_auth
    from app.settings.config import settings

    monkeypatch.setattr(codex_auth, "has_valid_token_sink", lambda: False)
    monkeypatch.setattr(codex_auth, "codex_oauth_enabled", lambda: True)
    monkeypatch.setattr(
        codex_auth,
        "build_authorize_url",
        lambda *, next_url: "https://auth.example/authorize?state=binding-test",
    )
    monkeypatch.setattr(codex_auth, "codex_app_server_status", lambda: {"status": "stopped"})
    monkeypatch.setattr(settings, "codex_auth_enabled", False)

    client = TestClient(production_app, base_url="https://testserver")
    login = client.get("/api/v1/codex-auth/login", follow_redirects=False)
    assert login.status_code == 302
    assert login.headers["location"].startswith("https://auth.example/authorize?")

    status = client.get("/api/v1/codex-auth/status")
    assert status.status_code == 200
    assert status.json()["data"]["authenticated"] is False

    policies = client.get(
        "/api/v1/policies",
        headers={"X-Project-Key": "demo-project"},
    )
    assert policies.status_code == 403
    policy_error = policies.json()["error"]
    assert policy_error["details"]["reason_code"] == "actor_unauthenticated"


def test_oauth_callback_establishes_session_and_unadmitted_logout_fails_closed(
    production_environment: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.api.codex_auth as codex_auth
    import app.main as main_module

    session = SessionRecord(session_id="session-established-by-callback")
    async def exchange_code(*, code: str, state: str) -> tuple[SessionRecord, str]:
        assert code == "oauth-code"
        assert state == "oauth-state"
        return session, "/auth-complete"

    monkeypatch.setattr(
        codex_auth,
        "exchange_code_to_session",
        exchange_code,
    )
    monkeypatch.setattr(main_module, "get_session", lambda sid: session if sid == session.session_id else None)
    revoke_calls: list[str] = []
    monkeypatch.setattr(
        codex_auth,
        "revoke_session",
        lambda sid: revoke_calls.append(sid) or {"session_revoked": True},
    )

    client = TestClient(production_app, base_url="https://testserver")
    callback = client.get(
        "/api/v1/codex-auth/callback",
        params={"code": "oauth-code", "state": "oauth-state"},
        follow_redirects=False,
    )
    assert callback.status_code == 302
    assert callback.headers["location"] == "/auth-complete"
    assert "codex_session" in callback.cookies
    cookie_header = callback.headers["set-cookie"].lower()
    assert "secure" in cookie_header
    assert "httponly" in cookie_header

    logout = client.post(
        "/api/v1/codex-auth/logout",
        headers={"X-Project-Key": "demo-project"},
    )
    assert logout.status_code == 403, logout.text
    details = logout.json()["error"]["details"]
    assert details["reason_code"] == "public_effect_route_unadmitted"
    assert details["effect_class"] == EffectClass.EXTERNAL_AUTH.value
    assert details["admission"] == EffectAdmission.BLOCKED_UNTIL_EFFECT_BINDING.value
    assert production_app.state.production_runtime_bindings.rate_observations.http_operations == []
    assert revoke_calls == []
