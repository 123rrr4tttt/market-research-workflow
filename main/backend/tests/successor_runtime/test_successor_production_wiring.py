"""Successor production-registry wiring (Lane A) focused coverage.

Covers the new settings surface, the fail-closed production registry
assembly, the authenticated actor provider, the disposable-PostgreSQL
registry resolver path and the app.state-backed production route mount.
The default LOCAL_ONLY mount contract is untouched and still covered by
``test_api_successor_runtime_mount.py``.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import NullPool

from app.api import successor_runtime as api_module
from app.settings.config import Settings
from app.settings.config import settings as app_settings
from app.successor_runtime.assembly.app_assembly import (
    AUTHORITY_CEILING_CLOSED,
    PRODUCTION_ACTOR_IDENTITY_KIND,
    PRODUCTION_REGISTRY_CONFIGURATION,
    SUCCESSOR_DEPENDENCIES_STATE_ATTR,
    AuthActorUnresolvedError,
    RegistryBackedProjectScopeResolver,
    SuccessorProductionConfigurationError,
    SuccessorRuntimeAppDependencies,
    _authenticated_actor_provider,
    build_successor_registry_app_dependencies,
    build_successor_runtime_app_dependencies,
)
from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES
from app.successor_runtime.substrate.postgres.session import (
    ProjectScopeStale,
    ProjectScopeValidationError,
    compute_scope_digest,
)

PROJECT_KEY = "production-wiring-demo"
REGISTRY_REVISION = 3
RESOLVED_SCHEMA = "mrw_production_wiring_demo"
SCOPE_INCARNATION = "scope-inc-production-wiring"
SCOPE_DIGEST = compute_scope_digest(
    PROJECT_KEY,
    RESOLVED_SCHEMA,
    REGISTRY_REVISION,
    SCOPE_INCARNATION,
)

DATABASE_NAME = "mrw_successor_production_wiring_test"
ENV_URL = "SUCCESSOR_TEST_DATABASE_URL"


class TestSettingsSurface:
    def test_defaults_and_successor_protected_prefix(self) -> None:
        settings = Settings(_env_file=None)
        assert settings.successor_mount_mode == "local_only"
        assert settings.successor_production_requires_auth is True
        assert "/api/v1/successor-runtime" in str(
            settings.codex_auth_protected_prefixes
        ).split(",")

    def test_invalid_mount_mode_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Settings(successor_mount_mode="registry_bypass", _env_file=None)

    def test_production_registry_without_auth_fails_closed(self) -> None:
        with pytest.raises(ValidationError, match="codex_auth_enabled"):
            Settings(
                successor_mount_mode="production_registry",
                codex_auth_enabled=False,
                successor_production_requires_auth=True,
                _env_file=None,
            )

    def test_production_registry_with_auth_is_allowed(self) -> None:
        settings = Settings(
            successor_mount_mode="production_registry",
            codex_auth_enabled=True,
            _env_file=None,
        )
        assert settings.successor_mount_mode == "production_registry"


class _StubHeaders:
    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    def get(self, key: str, default: str | None = None) -> str | None:
        return self._values.get(key, default)


class _StubAuthRequest:
    def __init__(
        self,
        *,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
    ) -> None:
        self.headers = _StubHeaders(headers or {})
        self.cookies = cookies or {}


class TestAuthenticatedActorProvider:
    def test_bearer_token_maps_to_structural_actor(self) -> None:
        request = _StubAuthRequest(
            headers={"Authorization": "Bearer secret-token-not-read"}
        )
        actor = _authenticated_actor_provider(request)  # type: ignore[arg-type]
        assert actor.startswith("actor:codex-token:")
        assert "secret-token-not-read" not in actor

    def test_x_codex_auth_header_maps_to_structural_actor(self) -> None:
        request = _StubAuthRequest(headers={"X-Codex-Auth": "claude-token"})
        actor = _authenticated_actor_provider(request)  # type: ignore[arg-type]
        assert actor.startswith("actor:codex-token:")
        assert "claude-token" not in actor

    def test_missing_authentication_fails_closed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "app.services.codex_oauth.has_valid_token_sink", lambda: False
        )
        with pytest.raises(AuthActorUnresolvedError):
            _authenticated_actor_provider(_StubAuthRequest())  # type: ignore[arg-type]


class TestProductionDependencies:
    def _enable_production(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(app_settings, "successor_mount_mode", "production_registry")
        monkeypatch.setattr(app_settings, "codex_auth_enabled", True)
        monkeypatch.setattr(app_settings, "successor_production_requires_auth", True)

    def test_registry_dependencies_are_closed_and_authenticated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._enable_production(monkeypatch)
        deps = build_successor_registry_app_dependencies(
            engine=sa.create_engine("sqlite+pysqlite:///:memory:")
        )
        assert isinstance(deps, SuccessorRuntimeAppDependencies)
        assert deps.configuration == PRODUCTION_REGISTRY_CONFIGURATION
        assert deps.actor_identity_kind == PRODUCTION_ACTOR_IDENTITY_KIND
        assert deps.authority_ceiling == dict(AUTHORITY_CEILING_CLOSED)
        assert deps.candidate is None

    def test_registry_dependencies_require_exactly_one_engine_source(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._enable_production(monkeypatch)
        with pytest.raises(ValueError, match="exactly one"):
            build_successor_registry_app_dependencies()

    def test_registry_dependencies_fail_closed_without_auth(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(app_settings, "successor_mount_mode", "production_registry")
        monkeypatch.setattr(app_settings, "codex_auth_enabled", False)
        monkeypatch.setattr(app_settings, "successor_production_requires_auth", True)
        with pytest.raises(SuccessorProductionConfigurationError):
            build_successor_registry_app_dependencies(
                engine=sa.create_engine("sqlite+pysqlite:///:memory:")
            )


@pytest.mark.integration
class TestRegistryBackedResolverPostgres:
    def test_current_and_expected_resolution_match_registry(
        self, disposable_database: Engine
    ) -> None:
        resolver = RegistryBackedProjectScopeResolver(engine=disposable_database)
        current = resolver.resolve(PROJECT_KEY)
        assert current.project_key == PROJECT_KEY
        assert current.resolved_schema == RESOLVED_SCHEMA
        assert current.project_registry_revision == REGISTRY_REVISION
        assert current.incarnation == SCOPE_INCARNATION
        assert current.scope_digest == SCOPE_DIGEST
        expected = resolver.resolve_expected(
            PROJECT_KEY, REGISTRY_REVISION, SCOPE_DIGEST
        )
        assert expected == current

    def test_expected_digest_mismatch_returns_stale(
        self, disposable_database: Engine
    ) -> None:
        resolver = RegistryBackedProjectScopeResolver(engine=disposable_database)
        result = resolver.resolve_expected(PROJECT_KEY, REGISTRY_REVISION, "0" * 64)
        assert isinstance(result, ProjectScopeStale)
        assert result.project_key == PROJECT_KEY
        assert result.expected_digest == SCOPE_DIGEST
        assert result.observed_digest == "0" * 64

    def test_missing_registry_row_fails_closed(
        self, disposable_database: Engine
    ) -> None:
        resolver = RegistryBackedProjectScopeResolver(engine=disposable_database)
        with pytest.raises(ProjectScopeValidationError, match="exactly one"):
            resolver.resolve("missing-production-project")


class TestProductionStateRouter:
    def _command_body(self) -> dict[str, Any]:
        return {
            "command_id": "cmd-production-wiring",
            "command_kind": "rebuild_projection",
            "project_locator": "local-mount-demo",
            "trace_id": "trace:production-wiring:1",
            "payload": {
                "payload_kind": "rebuild_projection",
                "projection_id": "projection.run-summary.v1",
                "projector_id": "projector:c9-mount",
                "projector_version": "1",
                "source_kind": "successor_values",
                "source_ref": "c9:mount:source:001",
                "source_incarnation": "inc:c9-mount",
            },
        }

    def test_uninitialized_production_mount_returns_typed_503(self) -> None:
        app = FastAPI()
        app.include_router(
            api_module.create_successor_runtime_state_router(),
            prefix="/api/v1",
        )
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/successor-runtime/v2/commands",
                json=self._command_body(),
            )
        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "error"
        assert body["error"]["code"] == "MOUNT_NOT_INITIALIZED"

    def test_initialized_production_mount_uses_app_state_dependencies(self) -> None:
        dependencies = build_successor_runtime_app_dependencies()
        app = FastAPI()
        setattr(app.state, SUCCESSOR_DEPENDENCIES_STATE_ATTR, dependencies)
        app.include_router(
            api_module.create_successor_runtime_state_router(),
            prefix="/api/v1",
        )
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/successor-runtime/v2/commands",
                json=self._command_body(),
            )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] in {"ok", "error", "blocked", "waiting", "conflict"}
        assert body["error"] is None or body["error"]["code"] != "MOUNT_NOT_INITIALIZED"


def _server_url() -> str:
    env_url = os.environ.get(ENV_URL)
    if env_url:
        url = make_url(env_url)
        return url.set(database="postgres").render_as_string(hide_password=False)
    return "postgresql+psycopg2://localhost/postgres"


def _create_database() -> Engine:
    server = sa.create_engine(
        _server_url(), isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    try:
        with server.connect() as connection:
            connection.execute(
                sa.text("DROP DATABASE IF EXISTS " + DATABASE_NAME + " WITH (FORCE)")
            )
            connection.execute(sa.text("CREATE DATABASE " + DATABASE_NAME))
    except Exception as exc:  # noqa: BLE001 - environment-dependent skip
        server.dispose()
        pytest.skip(f"cannot create disposable database {DATABASE_NAME}: {exc}")
    return server


def _drop_database(server: Engine) -> None:
    try:
        with server.connect() as connection:
            connection.execute(
                sa.text("DROP DATABASE IF EXISTS " + DATABASE_NAME + " WITH (FORCE)")
            )
    finally:
        server.dispose()


@pytest.fixture(scope="module")
def disposable_database() -> Iterator[Engine]:
    server = _create_database()
    engine = sa.create_engine(
        make_url(_server_url())
        .set(database=DATABASE_NAME)
        .render_as_string(hide_password=False),
        poolclass=NullPool,
    )
    with engine.begin() as connection:
        for table in PUBLIC_TABLES.values():
            table.create(connection)
        connection.execute(
            PUBLIC_TABLES["project_scope_registry"]
            .insert()
            .values(
                project_key=PROJECT_KEY,
                registry_revision=REGISTRY_REVISION,
                resolved_schema=RESOLVED_SCHEMA,
                scope_digest=SCOPE_DIGEST,
                incarnation=SCOPE_INCARNATION,
                state="ACTIVE",
                updated_by="successor-production-wiring-test",
                approval_ref=None,
            )
        )
    try:
        yield engine
    finally:
        engine.dispose()
        _drop_database(server)
