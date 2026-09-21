"""Focused tests for production runtime binding installation and denial ports."""

# ruff: noqa: E402

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
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
    require_production_policy,
)
from app.composition.production_runtime import (
    AtomicRedisRateObservations,
    EngineC9QueryReadPort,
    EngineProjectScopeResolver,
    PostgresProductionActorScopes,
    PostgresProductionApprovals,
    ProductionRuntimeAuthorityUnavailable,
    RegisteredCanonicalWriter,
    RegisteredProviderCatalog,
    RegisteredProviderSelection,
    build_production_runtime_bindings,
    build_production_successor_runtime_app_dependencies,
)
from app.main import _validate_production_composition, app as production_app, engine
from app.production_contract import (
    APPROVED_DECISION,
    ApprovalGrant,
    EffectAdmission,
    EffectClass,
    EndpointEffectContract,
    ProviderClass,
)
from app.services.request_identity import (
    RequestActorContext,
    authenticated_actor_context,
    set_request_actor_context,
)
from app.successor_runtime.runtime.facade import SuccessorRuntimeFacade
from app.successor_runtime.runtime.facade_contracts import (
    FacadeQueryV2,
    QueryMetaV2,
)
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
from app.successor_runtime.substrate.postgres.session import compute_scope_digest


pytestmark = pytest.mark.unit


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        env="production",
        production_allowed_hosts="testserver",
        production_allowed_origins="https://app.example",
        production_trusted_actor_sources="authenticated_request_state",
        production_trusted_auth_modes="oidc_claims",
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
        production_observability_runtime_id="test-runtime",
        codex_oauth_enabled=True,
        codex_oauth_cookie_secure=True,
    )


@pytest.fixture(autouse=True)
def production_startup_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.composition.production as production
    from app.settings.config import settings

    for key, value in vars(_settings()).items():
        monkeypatch.setattr(settings, key, value)
    monkeypatch.setattr(
        production,
        "read_build_identity",
        lambda: SimpleNamespace(fully_bound=True),
    )


@dataclass
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


@dataclass
class FakeActorScopes:
    def scopes(
        self,
        actor: object,
        operation: str,
        capability_id: str,
        scope: object,
    ) -> tuple[str, ...]:
        return ("api:invoke",)


@dataclass
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


@dataclass
class FakeRates:
    def observe_http(self, actor: object, operation: str) -> RateObservation:
        return RateObservation(0, 60)

    def observe_provider(
        self,
        actor: object,
        operation: str,
        provider_id: str,
    ) -> RateObservation:
        return RateObservation(0, 60)


def _request(path: str, runtime: ProductionRuntimeBindings) -> Request:
    state = SimpleNamespace(production_runtime_bindings=runtime)
    application = SimpleNamespace(state=state, routes=production_app.routes)
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "method": "POST",
        "scheme": "https",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "headers": [
            (b"host", b"testserver"),
            (b"content-type", b"application/json"),
            (b"x-project-key", b"demo"),
            (b"x-approval-id", b"approval-1"),
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 443),
        "app": application,
        "state": {"production_runtime_bindings": runtime},
        "route": SimpleNamespace(path=path),
        "path_params": {},
    }
    body = b'{"project_key":"demo"}'
    sent = False

    async def receive() -> dict[str, object]:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    request = Request(scope, receive=receive)
    request.scope["state"] = request.state
    set_request_actor_context(
        request,
        authenticated_actor_context(
            actor_id="actor-1",
            source="authenticated_request_state",
            auth_mode="oidc_claims",
        ),
    )
    return request


def _runtime_without_database() -> ProductionRuntimeBindings:
    runtime = build_production_runtime_bindings(engine)
    return replace(
        runtime,
        project_scope_resolver=FakeScopeResolver(),
        actor_scopes=FakeActorScopes(),
        approvals=FakeApprovals(),
        rate_observations=FakeRates(),
    )


def _admit_synthetic_effect(
    monkeypatch: pytest.MonkeyPatch,
    route_template: str,
    effect_contract: EndpointEffectContract,
) -> None:
    import app.composition.production as production

    bindings = production.load_production_route_bindings()
    rewritten = tuple(
        replace(
            binding,
            effect_contract=effect_contract,
            capability_id=binding.capability_id or "synthetic.route-effect.v1",
        )
        if binding.route_template == route_template
        else binding
        for binding in bindings
    )
    assert rewritten != bindings
    monkeypatch.setattr(
        production,
        "load_production_route_bindings",
        lambda *_args, **_kwargs: rewritten,
    )


def _rate_actor() -> RequestActorContext:
    return authenticated_actor_context(
        actor_id="rate-actor-1",
        source="authenticated_request_state",
        auth_mode="oidc_claims",
    )


def _successor_query(scope: ProjectScopeRef) -> FacadeQueryV2:
    return FacadeQueryV2(
        query_id="query:production-scope",
        query_kind="projection_snapshot",
        project_scope_ref=scope,
        actor_ref="actor-production-1",
        meta=QueryMetaV2(
            project_key=scope.project_key,
            trace_id="trace:production-scope",
            query_id="query:production-scope",
            project_scope_ref=scope,
        ),
        params={
            "projection_id": "projection:production-scope",
            "projector_id": "projector:c9-production",
            "projector_version": "1",
            "source_kind": "successor_values",
            "source_ref": "source:c9-production",
            "source_incarnation": scope.incarnation,
        },
    )


def test_production_successor_runtime_dependencies_preserve_scope_and_actor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.composition.production_runtime as production_runtime

    connection = object()

    class _ConnectionContext:
        def __enter__(self) -> object:
            return connection

        def __exit__(self, *_args: object) -> None:
            return None

    class _Engine:
        def connect(self) -> _ConnectionContext:
            return _ConnectionContext()

    captured: dict[str, object] = {}
    readback = object()

    class _Repository:
        def __init__(self, observed_connection: object, scope: RuntimeScope) -> None:
            captured["connection"] = observed_connection
            captured["scope"] = scope

        def read(self, query: FacadeQueryV2) -> object:
            captured["query"] = query
            return readback

    monkeypatch.setattr(production_runtime, "PostgresC9QueryRepository", _Repository)
    engine = _Engine()
    dependencies = build_production_successor_runtime_app_dependencies(engine)  # type: ignore[arg-type]
    assert isinstance(dependencies.resolver, EngineProjectScopeResolver)
    assert isinstance(dependencies.facade, SuccessorRuntimeFacade)
    query_port = dependencies.facade._query_port  # noqa: SLF001
    assert isinstance(query_port, EngineC9QueryReadPort)

    scope = FakeScopeResolver().resolve("production-scope")
    query = _successor_query(scope)
    assert query_port.read(query) is readback
    assert captured == {
        "connection": connection,
        "scope": RuntimeScope(project_scope=scope, actor_id=query.actor_ref),
        "query": query,
    }

    request = Request({"type": "http", "state": {}, "headers": []})
    set_request_actor_context(
        request,
        authenticated_actor_context(
            actor_id=query.actor_ref,
            source="authenticated_request_state",
            auth_mode="oidc_claims",
        ),
    )
    assert dependencies.actor_provider(request) == query.actor_ref


def test_production_successor_runtime_actor_fails_closed_without_trusted_identity() -> None:
    dependencies = build_production_successor_runtime_app_dependencies(engine)
    request = Request({"type": "http", "state": {}, "headers": []})
    with pytest.raises(Exception, match="trusted actor required"):
        dependencies.actor_provider(request)


@dataclass
class FakeRedisScript:
    responses: list[object]
    failures: list[BaseException | None]
    calls: list[dict[str, object]] = field(default_factory=list)

    def __call__(self, *, keys: list[str], args: list[int]) -> list[int]:
        self.calls.append({"keys": keys, "args": args})
        failure = self.failures.pop(0) if self.failures else None
        if failure is not None:
            raise failure
        response = self.responses.pop(0)
        return list(response) if isinstance(response, (list, tuple)) else response  # type: ignore[return-value]


@dataclass
class FakeRedisClient:
    script: FakeRedisScript

    def register_script(self, lua: str) -> FakeRedisScript:
        assert "redis.call('INCR'" in lua
        assert "redis.call('EXPIRE'" in lua
        return self.script


def test_production_startup_installs_runtime_bindings_and_route_coverage_passes() -> None:
    production_app.state.production_runtime_bindings = None
    _validate_production_composition()

    runtime = production_app.state.production_runtime_bindings
    assert isinstance(runtime, ProductionRuntimeBindings)
    assert isinstance(runtime.project_scope_resolver, EngineProjectScopeResolver)
    assert isinstance(runtime.actor_scopes, PostgresProductionActorScopes)
    assert isinstance(runtime.approvals, PostgresProductionApprovals)


def test_missing_required_production_setting_fails_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.settings.config import settings

    production_app.state.production_runtime_bindings = None
    monkeypatch.setattr(settings, "production_metrics_token", "")
    with pytest.raises(RuntimeError, match="production_metrics_token"):
        _validate_production_composition()


def test_redis_rate_adapter_uses_atomic_script_protocol() -> None:
    script = FakeRedisScript(responses=[(1, 59), (2, 17)], failures=[])
    adapter = AtomicRedisRateObservations(
        FakeRedisClient(script),
        http_window_seconds=60,
        provider_window_seconds=30,
    )

    http = adapter.observe_http(_rate_actor(), "example.operation")
    provider = adapter.observe_provider(
        _rate_actor(),
        "example.operation",
        "scrapy",
    )

    assert http == RateObservation(1, 60)
    assert provider == RateObservation(2, 30)
    assert script.calls[0]["keys"] != script.calls[1]["keys"]
    assert all(str(call["keys"][0]).startswith("mrw:production:rate:") for call in script.calls)
    assert script.calls[0]["args"] == [60]
    assert script.calls[1]["args"] == [30]


@pytest.mark.parametrize(
    "failure",
    [
        ConnectionError("redis unavailable"),
        ValueError("malformed redis response"),
    ],
)
def test_redis_rate_adapter_fails_closed(failure: BaseException) -> None:
    script = FakeRedisScript(
        responses=[],
        failures=[failure],
    )
    adapter = AtomicRedisRateObservations(
        FakeRedisClient(script),
        http_window_seconds=60,
        provider_window_seconds=60,
    )

    with pytest.raises(ProductionRuntimeAuthorityUnavailable):
        adapter.observe_http(_rate_actor(), "example.operation")


@pytest.mark.parametrize("response", [(0, 60), (1, 0), (1,), ("1", "not-a-number")])
def test_redis_rate_adapter_rejects_invalid_script_response(response: object) -> None:
    script = FakeRedisScript(responses=[response], failures=[])
    adapter = AtomicRedisRateObservations(
        FakeRedisClient(script),
        http_window_seconds=60,
        provider_window_seconds=60,
    )

    with pytest.raises(ProductionRuntimeAuthorityUnavailable):
        adapter.observe_http(_rate_actor(), "example.operation")


def test_unavailable_provider_authority_denies_capability() -> None:
    catalog = RegisteredProviderCatalog(
        deployment_allowlist=("scrapy",),
        llm_provider_ids=("openai",),
        crawler_provider_ids=("scrapy", "serper"),
    )
    selection = RegisteredProviderSelection(
        catalog=catalog,
        llm_provider_ids=catalog.llm_provider_ids,
        crawler_provider_ids=catalog.crawler_provider_ids,
    )
    assert catalog.allowed_provider_ids() == ("scrapy",)
    assert selection.select(FakeActorScopes(), ProviderClass.CRAWLER, 23) == ProviderSelection(
        provider_id="scrapy",
        provider_class=ProviderClass.CRAWLER,
        request_payload_bytes=23,
    )
    assert selection.select(FakeActorScopes(), ProviderClass.LLM, 23) is None

    agent_catalog = RegisteredProviderCatalog(
        deployment_allowlist=("openai", "scrapy"),
        llm_provider_ids=("openai",),
        crawler_provider_ids=("scrapy",),
    )
    agent_selection = RegisteredProviderSelection(
        catalog=agent_catalog,
        llm_provider_ids=agent_catalog.llm_provider_ids,
        crawler_provider_ids=agent_catalog.crawler_provider_ids,
    )
    assert agent_selection.select(FakeActorScopes(), ProviderClass.LLM, 23) == ProviderSelection(
        provider_id="openai",
        provider_class=ProviderClass.LLM,
        request_payload_bytes=23,
    )

    ambiguous_catalog = RegisteredProviderCatalog(
        deployment_allowlist=("scrapy", "serper"),
        llm_provider_ids=("openai",),
        crawler_provider_ids=("scrapy", "serper"),
    )
    ambiguous_selection = RegisteredProviderSelection(
        catalog=ambiguous_catalog,
        llm_provider_ids=ambiguous_catalog.llm_provider_ids,
        crawler_provider_ids=ambiguous_catalog.crawler_provider_ids,
    )
    assert ambiguous_selection.select(FakeActorScopes(), ProviderClass.CRAWLER, 23) is None

    runtime = replace(_runtime_without_database())
    assert runtime.provider_catalog.allowed_provider_ids() == ()
    assert runtime.provider_selection.select(FakeActorScopes(), ProviderClass.CRAWLER, 23) is None

    with pytest.raises(HTTPException) as raised:
        import asyncio

        asyncio.run(require_production_policy(_request("/api/v1/discovery/search", runtime)))

    assert raised.value.status_code == 403
    assert raised.value.detail["reason_code"] == "public_effect_route_unadmitted"
    assert raised.value.detail["effect_class"] == "conditional"
    assert raised.value.detail["admission"] == "blocked_until_effect_binding"


def test_admitted_provider_effect_still_requires_provider_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _admit_synthetic_effect(
        monkeypatch,
        "/api/v1/discovery/search",
        EndpointEffectContract(
            effect_class=EffectClass.PROVIDER_CALL,
            admission=EffectAdmission.ADMITTED,
            provider_port="synthetic.llm-provider.v1",
            provider_class=ProviderClass.LLM,
        ),
    )

    with pytest.raises(HTTPException) as raised:
        asyncio.run(
            require_production_policy(
                _request("/api/v1/discovery/search", _runtime_without_database())
            )
        )

    assert raised.value.status_code == 403
    assert raised.value.detail["reason_code"] == "provider_denied"


def test_unavailable_canonical_writer_denies_write() -> None:
    runtime = _runtime_without_database()
    assert isinstance(runtime.canonical_writer, RegisteredCanonicalWriter)
    assert (
        runtime.canonical_writer.owner(
            "admin.bulk_update_document_extracted_data",
            "demo",
            "successor-runtime",
            "runtime_step_authorization.v1",
            (),
        )
        is None
    )

    with pytest.raises(HTTPException) as raised:
        import asyncio

        asyncio.run(require_production_policy(_request("/api/v1/config/env", runtime)))

    assert raised.value.status_code == 403
    assert raised.value.detail["reason_code"] == "public_effect_route_unadmitted"
    assert raised.value.detail["effect_class"] == "filesystem_subprocess"
    assert raised.value.detail["admission"] == "blocked_until_effect_binding"


def test_admitted_canonical_write_still_requires_installed_writer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _admit_synthetic_effect(
        monkeypatch,
        "/api/v1/config/env",
        EndpointEffectContract(
            effect_class=EffectClass.CANONICAL_WRITE,
            admission=EffectAdmission.ADMITTED,
            canonical_writer_port="runtime_step_authorization.v1",
        ),
    )

    with pytest.raises(HTTPException) as raised:
        asyncio.run(
            require_production_policy(
                _request("/api/v1/config/env", _runtime_without_database())
            )
        )

    assert raised.value.status_code == 403
    assert raised.value.detail["reason_code"] == "canonical_writer_owner_missing"
