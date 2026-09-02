"""WP-I1-06 successor runtime app-mount dependencies (LOCAL_ONLY default).

This module owns the default app-entry wiring for the bounded v2 successor
runtime router.  The default uses the closed LOCAL_ONLY fixture options from
the I1 successor assembly and never opens a production resolver, live
provider, canonical writer, external delivery, cutover or authority transfer.
The router factory call itself stays in ``app/api/__init__.py`` so this
assembly layer never imports the API package.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from fastapi import Request

from app.successor_runtime.assembly.base import (
    FamilyAssemblyOptions,
    local_assembly_scope_digest,
)
from app.successor_runtime.assembly.c9_assembly import (
    build_deterministic_facade_closure,
)
from app.successor_runtime.assembly.successor_assembly import (
    build_local_offline_fixture_options,
)
from app.successor_runtime.runtime.facade import SuccessorRuntimeFacade
from app.successor_runtime.runtime.ports import ProjectScopeRef
from app.successor_runtime.substrate.postgres.session import (
    ProjectScopeResolver,
    ProjectScopeValidationError,
    ServerProjectScopeResolver,
    default_project_schema_name,
    validate_project_key,
)

LOCAL_ONLY_MOUNT_ACTOR = "actor:local-only-app-mount"
LOCAL_ONLY_MOUNT_INCARNATION = "incarnation:local-only-app-mount:v1"
LOCAL_ONLY_MOUNT_CONFIGURATION = "local_only_closed_fixture_options"
LOCAL_ONLY_ACTOR_IDENTITY_KIND = "actor-identity-kind:local-only"
PRODUCTION_REGISTRY_CONFIGURATION = "production_registry_closed_fixture_options"
PRODUCTION_ACTOR_IDENTITY_KIND = "production-authenticated"
SUCCESSOR_DEPENDENCIES_STATE_ATTR = "successor_runtime_dependencies"

AUTHORITY_CEILING_CLOSED: Mapping[str, bool] = MappingProxyType(
    {
        "canonical_write": False,
        "live_provider": False,
        "external_delivery": False,
        "cutover": False,
        "authority_transfer": False,
        "candidate_created": False,
    }
)


class LocalOnlyProjectScopeResolver:
    """Deterministic LOCAL_ONLY scope resolver; never reads the registry.

    Every valid project locator maps to one deterministic local-only scope
    identity bound to the assembly's ``local_assembly_scope_digest``.  The
    production ``resolve_expected`` registry path stays closed.
    """

    def __init__(self, *, scope_digest: str | None = None) -> None:
        self._scope_digest = scope_digest or local_assembly_scope_digest()

    def resolve(self, authenticated_project_key: str) -> ProjectScopeRef:
        project_key = validate_project_key(authenticated_project_key)
        return ProjectScopeRef(
            project_key=project_key,
            resolved_schema=default_project_schema_name(project_key),
            project_registry_revision=0,
            incarnation=LOCAL_ONLY_MOUNT_INCARNATION,
            scope_digest=self._scope_digest,
        )

    def resolve_expected(
        self,
        project_key: str,
        registry_revision: int,
        scope_digest: str,
    ) -> ProjectScopeRef:
        raise ProjectScopeValidationError(
            "resolve_expected is the production registry path; "
            "the LOCAL_ONLY app mount keeps it closed"
        )


class AuthActorUnresolvedError(RuntimeError):
    """Raised when no structural authenticated actor can be derived."""


class SuccessorProductionConfigurationError(RuntimeError):
    """Raised when the production registry mount is misconfigured."""


class RegistryBackedProjectScopeResolver:
    """Registry resolver that opens one fixed-public connection per call.

    The resolver never owns a connection at import/assembly time.  The engine
    (or a factory returning one) is supplied by the application startup point;
    each ``resolve``/``resolve_expected`` call opens a short-lived connection
    and delegates to the authoritative ``ServerProjectScopeResolver``.
    """

    def __init__(
        self,
        *,
        engine: Any | None = None,
        engine_factory: Callable[[], Any] | None = None,
    ) -> None:
        if (engine is None) == (engine_factory is None):
            raise ValueError(
                "RegistryBackedProjectScopeResolver requires exactly one of "
                "engine or engine_factory"
            )
        self._engine = engine
        self._engine_factory = engine_factory

    def _connect(self):
        engine = self._engine if self._engine is not None else self._engine_factory()
        return engine.connect()

    def resolve(self, authenticated_project_key: str) -> Any:
        with self._connect() as connection:
            resolver = ServerProjectScopeResolver(connection=connection)
            return resolver.resolve(authenticated_project_key)

    def resolve_expected(
        self,
        project_key: str,
        registry_revision: int,
        scope_digest: str,
    ) -> Any:
        with self._connect() as connection:
            resolver = ServerProjectScopeResolver(connection=connection)
            return resolver.resolve_expected(
                project_key,
                registry_revision,
                scope_digest,
            )


def _local_only_actor_provider(request: Request) -> str:
    return LOCAL_ONLY_MOUNT_ACTOR


def _request_actor_token(request: Request) -> str | None:
    auth_header = (request.headers.get("Authorization") or "").strip()
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        if token:
            return token
    custom_header = (request.headers.get("X-Codex-Auth") or "").strip()
    return custom_header or None


def _token_actor_ref(token: str) -> str:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return f"actor:codex-token:{digest}"


def authenticated_token_actor_ref(token: str) -> str:
    """Return a deterministic non-secret actor ref for an auth token."""

    return _token_actor_ref(token)


def authenticated_oauth_session_actor_ref(session_id: str) -> str:
    """Return a deterministic non-secret actor ref for an OAuth session."""

    return (
        "actor:codex-oauth-session:"
        + hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    )


def _authenticated_actor_provider(request: Request) -> str:
    """Derive a structural authenticated actor from the request only.

    This provider performs no secret comparison and never logs/returns the raw
    token.  It returns a deterministic actor ref for bearer/X-Codex-Auth
    credentials or a codex OAuth cookie when present; otherwise it fails
    closed with ``AuthActorUnresolvedError``.
    """

    token = _request_actor_token(request)
    if token:
        return _token_actor_ref(token)

    # The OAuth cookie is a structural fallback; the codex-auth middleware has
    # already validated the request before the route runs when auth is enabled.
    from app.settings.config import settings

    cookie_name = (
        str(getattr(settings, "codex_oauth_cookie_name", "codex_session") or "").strip()
        or "codex_session"
    )
    sid = (request.cookies.get(cookie_name) or "").strip()
    if sid:
        return authenticated_oauth_session_actor_ref(sid)

    raise AuthActorUnresolvedError(
        "no authenticated actor identity found on request "
        "(expected Authorization Bearer, X-Codex-Auth or codex oauth cookie)"
    )


def _production_validation_from_settings() -> None:
    from app.settings.config import settings, validate_successor_mount_mode

    try:
        validate_successor_mount_mode(
            mount_mode=getattr(settings, "successor_mount_mode", "local_only"),
            production_requires_auth=getattr(
                settings, "successor_production_requires_auth", True
            ),
            codex_auth_enabled=getattr(settings, "codex_auth_enabled", False),
        )
    except ValueError as exc:
        raise SuccessorProductionConfigurationError(str(exc)) from exc
    if str(getattr(settings, "successor_mount_mode", "local_only")).lower() != (
        "production_registry"
    ):
        raise SuccessorProductionConfigurationError(
            "successor registry dependencies require "
            "successor_mount_mode=production_registry"
        )


@dataclass(frozen=True, slots=True)
class SuccessorRuntimeAppDependencies:
    """Inspectable default dependencies for the mounted v2 router."""

    resolver: ProjectScopeResolver
    facade: SuccessorRuntimeFacade
    actor_provider: Callable[[Request], str]
    assembly_options: FamilyAssemblyOptions
    configuration: str = LOCAL_ONLY_MOUNT_CONFIGURATION
    authority_ceiling: Mapping[str, bool] = field(
        default_factory=lambda: dict(AUTHORITY_CEILING_CLOSED)
    )
    candidate: None = None
    actor_identity_kind: str = LOCAL_ONLY_ACTOR_IDENTITY_KIND


def build_successor_runtime_app_dependencies(
    *,
    options: FamilyAssemblyOptions | None = None,
    scope_digest: str | None = None,
) -> SuccessorRuntimeAppDependencies:
    """Build the default LOCAL_ONLY router dependencies.

    ``options`` defaults to the closed local-only fixture options; the C9
    facade closure from those options is the mounted command/query facade.
    """

    assembly_options = options or build_local_offline_fixture_options()
    facade = assembly_options.c9.facade
    if facade is None:
        facade = build_deterministic_facade_closure()
    if not isinstance(facade, SuccessorRuntimeFacade):
        raise TypeError("assembly options c9.facade must be a SuccessorRuntimeFacade")
    resolver = LocalOnlyProjectScopeResolver(scope_digest=scope_digest)
    return SuccessorRuntimeAppDependencies(
        resolver=resolver,
        facade=facade,
        actor_provider=_local_only_actor_provider,
        assembly_options=assembly_options,
        configuration=LOCAL_ONLY_MOUNT_CONFIGURATION,
        authority_ceiling=dict(AUTHORITY_CEILING_CLOSED),
        candidate=None,
        actor_identity_kind=LOCAL_ONLY_ACTOR_IDENTITY_KIND,
    )


def build_successor_registry_app_dependencies(
    *,
    engine: Any | None = None,
    engine_factory: Callable[[], Any] | None = None,
    options: FamilyAssemblyOptions | None = None,
    actor_provider: Callable[[Request], str] | None = None,
) -> SuccessorRuntimeAppDependencies:
    """Build production-registry dependencies (fail-closed, no live grants).

    The caller (app startup) supplies an engine or engine factory.  This
    function never opens a connection and never creates one implicitly; the
    resolver opens short-lived connections only when a request needs scope
    resolution.
    """

    _production_validation_from_settings()
    assembly_options = options or build_local_offline_fixture_options()
    facade = assembly_options.c9.facade
    if facade is None:
        facade = build_deterministic_facade_closure()
    if not isinstance(facade, SuccessorRuntimeFacade):
        raise TypeError("assembly options c9.facade must be a SuccessorRuntimeFacade")
    resolver = RegistryBackedProjectScopeResolver(
        engine=engine,
        engine_factory=engine_factory,
    )
    return SuccessorRuntimeAppDependencies(
        resolver=resolver,
        facade=facade,
        actor_provider=actor_provider or _authenticated_actor_provider,
        assembly_options=assembly_options,
        configuration=PRODUCTION_REGISTRY_CONFIGURATION,
        authority_ceiling=dict(AUTHORITY_CEILING_CLOSED),
        candidate=None,
        actor_identity_kind=PRODUCTION_ACTOR_IDENTITY_KIND,
    )


def initialize_successor_registry_mount(
    app: Any,
    *,
    engine: Any | None = None,
    engine_factory: Callable[[], Any] | None = None,
    actor_provider: Callable[[Request], str] | None = None,
) -> SuccessorRuntimeAppDependencies:
    """Initialize the app.state production registry mount at startup.

    Called by the application startup point (never from ``app/api`` import
    time).  If neither an engine nor a factory is supplied, a fixed-public
    successor engine is created lazily from settings (no database connection
    is opened by ``create_engine`` itself).
    """

    if engine is None and engine_factory is None:
        from app.settings.config import settings
        from app.successor_runtime.substrate.postgres.session import (
            create_runtime_engine,
        )

        engine = create_runtime_engine(settings.database_url)
    dependencies = build_successor_registry_app_dependencies(
        engine=engine,
        engine_factory=engine_factory,
        actor_provider=actor_provider,
    )
    setattr(app.state, SUCCESSOR_DEPENDENCIES_STATE_ATTR, dependencies)
    return dependencies


__all__ = [
    "AUTHORITY_CEILING_CLOSED",
    "LOCAL_ONLY_ACTOR_IDENTITY_KIND",
    "LOCAL_ONLY_MOUNT_ACTOR",
    "LOCAL_ONLY_MOUNT_CONFIGURATION",
    "LOCAL_ONLY_MOUNT_INCARNATION",
    "PRODUCTION_ACTOR_IDENTITY_KIND",
    "PRODUCTION_REGISTRY_CONFIGURATION",
    "SUCCESSOR_DEPENDENCIES_STATE_ATTR",
    "AuthActorUnresolvedError",
    "LocalOnlyProjectScopeResolver",
    "RegistryBackedProjectScopeResolver",
    "SuccessorProductionConfigurationError",
    "SuccessorRuntimeAppDependencies",
    "authenticated_oauth_session_actor_ref",
    "authenticated_token_actor_ref",
    "build_successor_registry_app_dependencies",
    "build_successor_runtime_app_dependencies",
    "initialize_successor_registry_mount",
]
