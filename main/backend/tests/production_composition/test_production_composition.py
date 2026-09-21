"""Focused tests for the production composition and request admission boundary."""

# ruff: noqa: E402

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest
from fastapi import HTTPException
from starlette.requests import Request


BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BACKEND_ROOT.parent.parent
for path in (str(BACKEND_ROOT), str(REPOSITORY_ROOT / "src")):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.composition.production import (
    ProductionRuntimeBindings,
    ProviderSelection,
    RateObservation,
    build_production_composition,
    is_production_environment,
    load_production_route_bindings,
    load_production_route_exemptions,
    production_metrics_label,
    require_production_policy,
    require_observability_token,
    validate_production_route_coverage,
)
from app.main import app as production_app
from app.production_observability import (
    CanaryRouteAction,
    CanaryRouteAdvice,
    ProductionObservabilityController,
)
from app.production_contract import (
    APPROVED_DECISION,
    ApprovalGrant,
    EffectAdmission,
    EffectClass,
    PolicyOutcome,
    ProviderClass,
)
from app.services.request_identity import authenticated_actor_context, set_request_actor_context
from app.successor_runtime.runtime.ports import ProjectScopeRef
from app.successor_runtime.substrate.postgres.session import compute_scope_digest


pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def production_test_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.composition.production as production
    from app.settings.config import settings

    for key, value in vars(_settings()).items():
        monkeypatch.setattr(settings, key, value)

    monkeypatch.setattr(
        production,
        "read_build_identity",
        lambda: SimpleNamespace(fully_bound=True),
    )


def _settings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "env": "production",
        "production_allowed_hosts": "testserver",
        "production_allowed_origins": "https://app.example",
        "production_trusted_actor_sources": "authenticated_request_state",
        "production_trusted_auth_modes": "oidc_claims",
        "production_require_tls": True,
        "production_allowed_methods": "GET,POST",
        "production_allowed_content_types": "application/json",
        "production_max_body_bytes": 1024,
        "production_http_rate_max_requests": 10,
        "production_http_rate_window_seconds": 60,
        "production_provider_rate_max_requests": 5,
        "production_provider_rate_window_seconds": 60,
        "production_provider_max_payload_bytes": 1024,
        "production_metrics_token": "metrics-secret",
        "production_project_keys": "env-project",
        "codex_oauth_enabled": True,
        "codex_oauth_cookie_secure": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@dataclass(frozen=True, slots=True)
class FakeScopeResolver:
    resolved: list[str]

    def resolve(self, authenticated_project_key: str) -> ProjectScopeRef:
        self.resolved.append(authenticated_project_key)
        schema = "mrw_p_demo"
        incarnation = "project-demo-incarnation"
        return ProjectScopeRef(
            project_key=authenticated_project_key,
            resolved_schema=schema,
            project_registry_revision=7,
            incarnation=incarnation,
            scope_digest=compute_scope_digest(
                authenticated_project_key, schema, 7, incarnation
            ),
        )


@dataclass(frozen=True, slots=True)
class FakeActorScopes:
    scopes_value: tuple[str, ...] = ("api:invoke",)

    def scopes(
        self,
        actor: object,
        operation: str,
        capability_id: str,
        scope: object,
    ) -> tuple[str, ...]:
        return self.scopes_value


@dataclass(frozen=True, slots=True)
class FakeApprovals:
    def approvals(
        self,
        actor: object,
        operation: str,
        capability_id: str,
        scope: object,
        observed_at: object,
        approval_ref: str,
        payload_digest: str,
    ) -> tuple[object, ...]:
        if not approval_ref:
            return ()
        return (
            ApprovalGrant(
                approval_id=approval_ref,
                actor_id=getattr(actor, "actor_id", "actor-1"),
                decision=APPROVED_DECISION,
                project_key=getattr(scope, "project_key", "demo"),
                operation=operation,
                capability_id=capability_id,
                payload_digest=payload_digest,
                claim_authority_epoch=7,
            ),
        )


@dataclass(frozen=True, slots=True)
class FakeRates:
    def observe_http(self, actor: object, operation: str) -> RateObservation:
        return RateObservation(0, 60)

    def observe_provider(self, actor: object, operation: str, provider_id: str) -> RateObservation:
        return RateObservation(0, 60)


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
    ) -> ProviderSelection | None:
        return ProviderSelection(
            provider_id="serper",
            provider_class=ProviderClass.CRAWLER,
            request_payload_bytes=request_payload_bytes,
        )


@dataclass(frozen=True, slots=True)
class FakeWriter:
    def owner(
        self,
        operation: str,
        project_key: str,
        canonical_owner_ref: str,
        writer_port_kind: str,
        approvals: tuple[ApprovalGrant, ...],
    ) -> str | None:
        if len(approvals) != 1:
            return None
        return canonical_owner_ref


def _runtime(
    *,
    resolver: FakeScopeResolver | None = None,
    actor_scopes: FakeActorScopes | None = None,
) -> ProductionRuntimeBindings:
    return ProductionRuntimeBindings(
        project_scope_resolver=resolver or FakeScopeResolver([]),
        actor_scopes=actor_scopes or FakeActorScopes(),
        approvals=FakeApprovals(),
        rate_observations=FakeRates(),
        provider_catalog=FakeProviderCatalog(),
        provider_selection=FakeProviderSelection(),
        canonical_writer=FakeWriter(),
    )


def test_checked_in_route_registry_exactly_covers_installed_routes() -> None:
    bindings = load_production_route_bindings()
    exemptions = load_production_route_exemptions()
    validate_production_route_coverage(bindings, production_app.routes, exemptions=exemptions)

    assert bindings
    assert all(binding.methods and binding.operation and binding.domain for binding in bindings)
    agent_chat = next(
        binding for binding in bindings if binding.operation == "agent-chat.run_agent_chat_turn"
    )
    assert not any(binding.effect_contract.requires_canonical_writer for binding in bindings)
    agent_contract = agent_chat.effect_contract
    assert agent_contract.effect_class is EffectClass.CONDITIONAL
    assert agent_contract.admission is EffectAdmission.BLOCKED_UNTIL_EFFECT_BINDING
    assert agent_contract.provider_class is ProviderClass.NULL
    assert agent_contract.conditional_branches == ("no_effect_or_read", "external_or_legacy_effect")


def test_new_route_is_not_admitted_by_method_or_route_name_inference() -> None:
    bindings = load_production_route_bindings()
    exemptions = load_production_route_exemptions()
    new_route = SimpleNamespace(path="/api/v1/unregistered/example", methods={"GET", "HEAD"})
    routes = [*production_app.routes, new_route]

    with pytest.raises(RuntimeError, match="unregistered"):
        validate_production_route_coverage(bindings, routes, exemptions=exemptions)


def test_production_build_requires_runtime_bindings_and_exact_route_coverage() -> None:
    runtime = _runtime()

    with pytest.raises(RuntimeError, match="production runtime binding"):
        build_production_composition(_settings(), routes=production_app.routes, runtime_bindings=None)  # type: ignore[arg-type]

    composition = build_production_composition(
        _settings(),
        routes=production_app.routes,
        runtime_bindings=runtime,
    )

    assert composition.policy.provider.allowed_provider_ids == ("serper",)
    discovery_binding = composition.binding_for("/api/v1/discovery/search", "POST")
    assert discovery_binding is not None
    discovery_contract = discovery_binding.effect_contract
    assert discovery_contract.effect_class is EffectClass.CONDITIONAL
    assert discovery_contract.admission is EffectAdmission.BLOCKED_UNTIL_EFFECT_BINDING
    assert not composition.policy.projects
    assert composition.binding_for("/api/v1/policies", "GET") is not None
    assert composition.binding_for("/api/v1/policies", "POST") is None


def test_production_oauth_requires_secure_session_cookie() -> None:
    with pytest.raises(RuntimeError, match="production OAuth requires secure session cookies"):
        build_production_composition(
            _settings(codex_oauth_cookie_secure=False),
            routes=production_app.routes,
            runtime_bindings=_runtime(),
        )


def _request(
    *,
    path: str,
    method: str = "GET",
    body: bytes = b'{"project_key":"demo"}',
    headers: list[tuple[bytes, bytes]],
    runtime: ProductionRuntimeBindings,
) -> Request:
    state = SimpleNamespace(production_runtime_bindings=runtime)
    application = SimpleNamespace(state=state, routes=production_app.routes)
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "https",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 443),
        "app": application,
        "state": dict(vars(state)),
        "route": SimpleNamespace(path=path),
        "path_params": {},
    }
    sent = False

    async def receive() -> dict[str, object]:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    request = Request(scope, receive=receive)
    request.scope["state"] = request.state
    actor = authenticated_actor_context(
        actor_id="actor-1",
        source="authenticated_request_state",
        auth_mode="oidc_claims",
        actor_metadata={"scopes": ("forged:scope",)},
    )
    set_request_actor_context(request, actor)
    request.state.actor_scopes = ("forged:scope",)
    request.state.approval_grants = ("forged-approval",)
    request.state.provider_id = "request-state-provider"
    request.state.canonical_writer_owner = "request-state-writer"
    return request


def _base_headers() -> list[tuple[bytes, bytes]]:
    return [
        (b"host", b"testserver"),
        (b"content-type", b"application/json"),
        (b"x-project-key", b"demo"),
    ]


def test_scope_and_authority_observations_come_only_from_runtime_ports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.settings.config.settings.env", "production")
    resolver = FakeScopeResolver([])
    runtime = _runtime(resolver=resolver)
    request = _request(
        path="/api/v1/policies",
        method="GET",
        body=b'{"project_key":"demo","provider_id":"payload-provider"}',
        headers=[
            *_base_headers(),
            (b"x-approval-id", b"approval-1"),
            (b"x-provider-id", b"header-provider"),
            (b"x-canonical-writer-owner", b"header-writer"),
        ],
        runtime=runtime,
    )

    decision = asyncio.run(require_production_policy(request))

    assert decision is not None
    assert decision.outcome is PolicyOutcome.PASS
    assert decision.authority is False
    assert resolver.resolved == ["demo"]


def test_r7_rollback_advice_denies_before_production_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.settings.config.settings.env", "production")

    class RollbackObservabilityController(ProductionObservabilityController):
        @property
        def route_advice(self) -> CanaryRouteAdvice:
            return CanaryRouteAdvice(
                canary_route_enabled=True,
                action=CanaryRouteAction.ROLLBACK,
                promotion_allowed=False,
            )

    class ContinueObservabilityController(ProductionObservabilityController):
        @property
        def route_advice(self) -> CanaryRouteAdvice:
            return CanaryRouteAdvice(
                canary_route_enabled=True,
                action=CanaryRouteAction.CONTINUE,
                promotion_allowed=False,
            )

    request = _request(
        path="/api/v1/policies",
        method="GET",
        headers=[*_base_headers(), (b"x-approval-id", b"approval-1")],
        runtime=_runtime(),
    )
    request.app.state.production_observability_r7 = object.__new__(RollbackObservabilityController)

    with pytest.raises(HTTPException) as raised:
        asyncio.run(require_production_policy(request))

    assert raised.value.status_code == 403
    assert raised.value.detail["reason_code"] == "observability_rollback_latched"

    request = _request(
        path="/api/v1/policies",
        method="GET",
        headers=[*_base_headers(), (b"x-approval-id", b"approval-1")],
        runtime=_runtime(),
    )
    request.app.state.production_observability_r7 = object.__new__(ContinueObservabilityController)
    decision = asyncio.run(require_production_policy(request))
    assert decision is not None and decision.outcome is PolicyOutcome.PASS and decision.authority is False


def test_port_missing_scope_is_not_replaced_by_request_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.settings.config.settings.env", "production")
    runtime = _runtime(actor_scopes=FakeActorScopes(scopes_value=()))
    request = _request(path="/api/v1/policies", headers=_base_headers(), runtime=runtime)

    with pytest.raises(HTTPException) as raised:
        asyncio.run(require_production_policy(request))

    assert raised.value.status_code == 403
    assert raised.value.detail["reason_code"] == "scope_denied"


def test_non_empty_malformed_json_body_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.settings.config.settings.env", "production")
    resolver = FakeScopeResolver([])
    request = _request(
        path="/api/v1/policies",
        body=b'{"project_key":',
        headers=_base_headers(),
        runtime=_runtime(resolver=resolver),
    )

    with pytest.raises(HTTPException) as raised:
        asyncio.run(require_production_policy(request))

    assert raised.value.status_code == 400
    assert raised.value.detail["reason_code"] == "json_payload_invalid"
    assert resolver.resolved == []


def test_production_metrics_fail_closed_without_runtime_or_route_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.settings.config.settings.env", "production")
    unavailable = _request(
        path="/api/v1/policies",
        headers=_base_headers(),
        runtime=_runtime(),
    )
    unavailable.app.state.production_runtime_bindings = None

    with pytest.raises(HTTPException) as unavailable_error:
        production_metrics_label(unavailable)

    assert unavailable_error.value.status_code == 503

    request = _request(
        path="/api/v1/not-registered",
        headers=_base_headers(),
        runtime=_runtime(),
    )
    with pytest.raises(HTTPException) as route_error:
        production_metrics_label(request)

    assert route_error.value.status_code == 404


def test_exact_observability_exemption_has_stable_production_metric_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.settings.config.settings.env", "production")
    request = _request(path="/api/v1/health", headers=_base_headers(), runtime=_runtime())

    assert production_metrics_label(request) == {
        "domain": "exempt",
        "route": "/api/v1/health",
        "release_version": production_app.version,
    }


def test_dev_metrics_keep_low_risk_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.settings.config.settings.env", "dev")
    assert not is_production_environment(_settings(env="dev"))
    request = _request(path="/local/path", headers=_base_headers(), runtime=_runtime())

    assert production_metrics_label(request) == {
        "domain": "unknown",
        "route": "/local/path",
        "release_version": production_app.version,
    }


def test_observability_token_rejects_query_and_accepts_bearer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.settings.config.settings.env", "production")

    async def call(query_token: bool, headers: list[tuple[bytes, bytes]]) -> None:
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/metrics",
            "headers": headers,
            "query_string": b"token=bad" if query_token else b"",
        }
        require_observability_token(Request(scope), "metrics-secret")

    with pytest.raises(HTTPException):
        asyncio.run(call(True, [(b"host", b"testserver")]))

    asyncio.run(
        call(
            False,
            [(b"host", b"testserver"), (b"authorization", b"Bearer metrics-secret")],
        )
    )
