"""Production-only adapters for existing authoritative runtime sources.

Read adapters remain observation boundaries.  The explicitly installed C9
command port is the one bounded canonical effect for this Stage 4 milestone;
capabilities without an installed production authority source use explicit
conservative-denial ports.
"""

# ruff: noqa: TRY003

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
from typing import Annotated

import redis as redis_client
from fastapi import Request
from sqlalchemy import and_, or_, select
from sqlalchemy.engine import Connection, Engine

from app.production_contract import APPROVED_DECISION, ApprovalGrant, ProviderClass
from app.services.request_identity import RequestActorContext, require_trusted_actor_context
from app.services.llm.ports import LLMProviderResolutionError, resolve_llm_provider
from app.successor_runtime.runtime.authority_grants import AuthorityOperationScope
from app.successor_runtime.runtime.facade import SuccessorRuntimeFacade
from app.successor_runtime.runtime.facade_contracts import FacadeQueryV2, QueryResult
from app.successor_runtime.runtime.facade_contracts import CommandReceipt, FacadeCommandV2
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
from app.successor_runtime.substrate.postgres.facade_commands import (
    C9_CAPABILITY_ID,
    PostgresC9CommandRepository,
    PostgresC9QueryRepository,
)
from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES
from app.successor_runtime.substrate.postgres.session import (
    ProjectScopeResolver,
    ServerProjectScopeResolver,
)

from .production import ProductionRuntimeBindings, ProviderSelection, RateObservation
from .production import load_production_route_bindings


_RATE_LUA = """
local current = redis.call('INCR', KEYS[1])
local ttl = redis.call('TTL', KEYS[1])
if ttl <= 0 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
  ttl = tonumber(ARGV[1])
end
return {current, ttl}
"""
_KNOWN_LLM_PROVIDER_IDS = ("openai", "azure", "ollama", "litellm")


class ProductionRuntimeAuthorityUnavailable(RuntimeError):
    """A configured authority source cannot return a valid observation."""


@contextmanager
def _read_only_connection(engine: Engine) -> Iterator[Connection]:
    with engine.connect() as connection:
        # Adapters only issue SELECT statements; connection close rolls back
        # the implicit read transaction.
        yield connection


class EngineProjectScopeResolver:
    """Adapt the existing server resolver to fresh pooled connections."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def resolve(self, authenticated_project_key: str) -> ProjectScopeRef:
        with _read_only_connection(self._engine) as connection:
            return ServerProjectScopeResolver(connection=connection).resolve(authenticated_project_key)


class EngineC9QueryReadPort:
    """Open one read-only connection for an exact server-bound C9 query."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def read(self, query: FacadeQueryV2) -> QueryResult:
        runtime_scope = RuntimeScope(
            project_scope=query.project_scope_ref,
            actor_id=query.actor_ref,
        )
        with _read_only_connection(self._engine) as connection:
            return PostgresC9QueryRepository(connection, runtime_scope).read(query)


class PostgresC9CommandSubmissionPort:
    """Production C9 command port with the approved effect enabled."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def submit(self, command: FacadeCommandV2) -> CommandReceipt:
        runtime_scope = RuntimeScope(
            project_scope=command.project_scope_ref,
            actor_id=command.actor_ref,
        )
        with self._engine.begin() as connection:
            return PostgresC9CommandRepository(
                connection,
                runtime_scope,
                execute_effects=True,
            ).submit(command)


class C9ProjectionCanonicalWriterBinding:
    """Installed operation-specific writer marker used by policy admission."""

    capability = C9_CAPABILITY_ID

    def admit(self, command: FacadeCommandV2) -> bool:
        return command.command_kind == "rebuild_projection"


def _trusted_successor_runtime_actor(request: Request) -> str:
    """Reuse the authenticated request identity already checked by policy."""

    return require_trusted_actor_context(request).actor_id


@dataclass(frozen=True, slots=True)
class ProductionSuccessorRuntimeAppDependencies:
    """Production successor runtime dependencies with C9 effect execution."""

    resolver: ProjectScopeResolver
    facade: SuccessorRuntimeFacade
    actor_provider: Callable[[Request], str]


def build_production_successor_runtime_app_dependencies(
    engine: Engine,
) -> Annotated[
    ProductionSuccessorRuntimeAppDependencies,
    "kit:prepared-command effect_boundary=successor_runtime.production_query_assembly "
    "witness=test:test_production_successor_runtime_dependencies_preserve_scope_and_actor",
]:
    """Bind the mounted C9 command/query paths to PostgreSQL."""

    return ProductionSuccessorRuntimeAppDependencies(
        resolver=EngineProjectScopeResolver(engine),
        facade=SuccessorRuntimeFacade(
            submission_port=PostgresC9CommandSubmissionPort(engine),
            query_port=EngineC9QueryReadPort(engine),
        ),
        actor_provider=_trusted_successor_runtime_actor,
    )


class PostgresProductionActorScopes:
    """Read current, project-bound operation grants from the public registry."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def scopes(
        self,
        actor: RequestActorContext,
        operation: str,
        capability_id: str,
        scope: ProjectScopeRef,
    ) -> tuple[str, ...]:
        grants = PUBLIC_TABLES["runtime_authority_grants"]
        capabilities = PUBLIC_TABLES["runtime_capability_authority"]
        with _read_only_connection(self._engine) as connection:
            rows = connection.execute(
                select(grants.c.operation_scope_json)
                .join(
                    capabilities,
                    and_(
                        capabilities.c.project_key == grants.c.project_key,
                        capabilities.c.capability_id == grants.c.capability_id,
                        capabilities.c.successor_claim_enabled.is_(True),
                        capabilities.c.legacy_claim_enabled.is_(False),
                    ),
                )
                .where(
                    grants.c.project_key == scope.project_key,
                    grants.c.actor_id == actor.actor_id,
                    grants.c.capability_id == capability_id,
                    grants.c.revoked_at.is_(None),
                    or_(grants.c.expires_at.is_(None), grants.c.expires_at > datetime.now(UTC)),
                )
            ).mappings().all()
        matched = False
        for row in rows:
            try:
                grant_scope = AuthorityOperationScope.model_validate(row["operation_scope_json"])
            except Exception as exc:
                raise ProductionRuntimeAuthorityUnavailable("authority grant scope is malformed") from exc
            if grant_scope.project_scope_digest != scope.scope_digest:
                raise ProductionRuntimeAuthorityUnavailable("authority grant is bound to a stale project scope")
            matched = matched or operation in grant_scope.operation_kinds
        # The generic API admission scope does not authorize an effect.  PASS
        # remains non-authoritative and effect owners still enforce exact grants.
        return ("api:invoke",) if matched else ()


class PostgresProductionApprovals:
    """Read current actor approvals from the existing public registry."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def approvals(
        self,
        actor: RequestActorContext,
        operation: str,
        capability_id: str,
        scope: ProjectScopeRef,
        observed_at: datetime,
        approval_ref: str,
        payload_digest: str,
    ) -> tuple[ApprovalGrant, ...]:
        if not approval_ref:
            return ()
        try:
            valid_digest = len(payload_digest) == 64 and all(
                char in "0123456789abcdef" for char in payload_digest
            )
        except TypeError:
            valid_digest = False
        if not valid_digest:
            return ()
        approvals = PUBLIC_TABLES["runtime_approvals"]
        authorizations = PUBLIC_TABLES["runtime_step_authorizations"]
        capabilities = PUBLIC_TABLES["runtime_capability_authority"]
        with _read_only_connection(self._engine) as connection:
            rows = connection.execute(
                select(
                    approvals.c.approval_id,
                    approvals.c.actor_id,
                    approvals.c.decision,
                    approvals.c.expires_at,
                    authorizations.c.operation_kind,
                    authorizations.c.capability_id,
                    authorizations.c.payload_digest,
                    authorizations.c.claim_authority_epoch,
                )
                .join(
                    authorizations,
                    and_(
                        authorizations.c.project_key == approvals.c.project_key,
                        authorizations.c.approval_ref == approvals.c.approval_id,
                    ),
                )
                .join(
                    capabilities,
                    and_(
                        capabilities.c.project_key == authorizations.c.project_key,
                        capabilities.c.capability_id == authorizations.c.capability_id,
                        capabilities.c.authority_epoch
                        == authorizations.c.claim_authority_epoch,
                        capabilities.c.mode == "on",
                        capabilities.c.successor_claim_enabled.is_(True),
                        capabilities.c.legacy_claim_enabled.is_(False),
                        capabilities.c.effective_at <= observed_at,
                    ),
                )
                .where(
                    approvals.c.project_key == scope.project_key,
                    approvals.c.approval_id == approval_ref,
                    approvals.c.actor_id == actor.actor_id,
                    approvals.c.payload_digest == payload_digest,
                    approvals.c.decision == APPROVED_DECISION,
                    or_(approvals.c.expires_at.is_(None), approvals.c.expires_at > observed_at),
                    authorizations.c.operation_kind == operation,
                    authorizations.c.capability_id == capability_id,
                    authorizations.c.payload_digest == payload_digest,
                    authorizations.c.actor_id == actor.actor_id,
                    authorizations.c.claim_owner == "successor",
                    authorizations.c.claim_authority_epoch >= 0,
                    authorizations.c.project_registry_revision
                    == scope.project_registry_revision,
                    authorizations.c.project_scope_digest == scope.scope_digest,
                    or_(
                        authorizations.c.expires_at.is_(None),
                        authorizations.c.expires_at > observed_at,
                    ),
                )
            )
            rows = rows.mappings().all()
        if len(rows) > 1:
            raise ProductionRuntimeAuthorityUnavailable("operation authority observation is ambiguous")
        if not rows:
            return ()
        row = rows[0]
        if (
            str(row["capability_id"]) != capability_id
            or row["operation_kind"] != operation
            or row["payload_digest"] != payload_digest
        ):
            return ()
        return tuple(
            ApprovalGrant(
                approval_id=str(row["approval_id"]),
                actor_id=str(row["actor_id"]),
                decision=str(row["decision"]),
                expires_at=row["expires_at"],
                project_key=scope.project_key,
                operation=operation,
                capability_id=capability_id,
                payload_digest=payload_digest,
                claim_authority_epoch=int(row["claim_authority_epoch"]),
            )
            for row in rows
        )


class AtomicRedisRateObservations:
    """Atomic actor/operation windows backed by the configured Redis URL."""

    def __init__(
        self,
        client: redis_client.Redis,
        *,
        http_window_seconds: int,
        provider_window_seconds: int,
    ) -> None:
        self._script = client.register_script(_RATE_LUA)
        self._http_window_seconds = http_window_seconds
        self._provider_window_seconds = provider_window_seconds

    def _observe(self, actor: RequestActorContext, operation: str, scope: str) -> RateObservation:
        digest = hashlib.sha256(f"{actor.actor_id}\n{operation}".encode()).hexdigest()
        window = {
            "http": self._http_window_seconds,
            "provider": self._provider_window_seconds,
        }[scope]
        try:
            raw = self._script(keys=[f"mrw:production:rate:{scope}:v1:{digest}"], args=[window])
            if not isinstance(raw, (list, tuple)) or len(raw) != 2:
                raise ValueError("rate script response must contain count and ttl")  # noqa: TRY301
            count, ttl = (int(raw[0]), int(raw[1]))
            if count < 1 or ttl <= 0:
                raise ValueError("rate script returned an invalid observation")  # noqa: TRY301
        except Exception as exc:
            raise ProductionRuntimeAuthorityUnavailable("Redis rate authority is unavailable") from exc
        # Remaining TTL proves the key belongs to a live window; normalization
        # must use the configured window so partial TTLs do not amplify counts.
        return RateObservation(request_count=count, window_seconds=window)

    def observe_http(self, actor: RequestActorContext, operation: str) -> RateObservation:
        return self._observe(actor, operation, "http")

    def observe_provider(
        self,
        actor: RequestActorContext,
        operation: str,
        provider_id: str,
    ) -> RateObservation:
        return self._observe(actor, f"{operation}\n{provider_id}", "provider")


@dataclass(frozen=True, slots=True)
class RegisteredProviderCatalog:
    """Intersect deployment allowlist with actual registered provider ports."""

    deployment_allowlist: tuple[str, ...]
    llm_provider_ids: tuple[str, ...]
    crawler_provider_ids: tuple[str, ...]

    def allowed_provider_ids(self) -> tuple[str, ...]:
        actual = tuple(
            dict.fromkeys(
                item.strip().lower()
                for item in (*self.llm_provider_ids, *self.crawler_provider_ids)
                if item.strip()
            )
        )
        return tuple(item for item in self.deployment_allowlist if item in actual)


@dataclass(frozen=True, slots=True)
class RegisteredProviderSelection:
    """Select only an unambiguous intersection member for a capability class."""

    catalog: RegisteredProviderCatalog
    llm_provider_ids: tuple[str, ...]
    crawler_provider_ids: tuple[str, ...]

    def select(
        self,
        actor: RequestActorContext,
        provider_class: ProviderClass,
        request_payload_bytes: int,
    ) -> ProviderSelection | None:
        del actor
        allowed = self.catalog.allowed_provider_ids()
        candidates = tuple(
            item
            for item in (
                self.llm_provider_ids
                if provider_class is ProviderClass.LLM
                else self.crawler_provider_ids
                if provider_class is ProviderClass.CRAWLER
                else ()
            )
            if item in allowed
        )
        if len(candidates) != 1:
            return None
        return ProviderSelection(
            provider_id=candidates[0],
            provider_class=provider_class,
            request_payload_bytes=request_payload_bytes,
        )


@dataclass(frozen=True, slots=True)
class UnavailableProviderCatalog:
    capability = "provider_catalog"

@dataclass(frozen=True, slots=True)
class UnavailableProviderSelection:
    capability = "provider_selection"

    def select(
        self,
        actor: RequestActorContext,
        provider_class: ProviderClass,
        request_payload_bytes: int,
    ) -> ProviderSelection | None:
        return None


@dataclass(frozen=True, slots=True)
class UnavailableCanonicalWriter:
    capability = "canonical_writer"

    def owner(
        self,
        operation: str,
        project_key: str,
        canonical_owner_ref: str,
        writer_port_kind: str,
        approvals: tuple[ApprovalGrant, ...],
    ) -> str | None:
        return None


@dataclass(frozen=True, slots=True)
class InstalledCanonicalWriterBinding:
    operation: str
    canonical_owner_ref: str
    writer_port_kind: str
    port: object


@dataclass(frozen=True, slots=True)
class RegisteredCanonicalWriter:
    """Route requirements intersected with actually installed writer ports."""

    bindings: tuple[tuple[str, str, str], ...]
    installed: tuple[InstalledCanonicalWriterBinding, ...] = ()

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
        grant = approvals[0]
        exact_grant = (
            grant.project_key == project_key
            and grant.operation == operation
            and grant.payload_digest
            and grant.claim_authority_epoch >= 0
        )
        route_registered = (
            operation,
            canonical_owner_ref,
            writer_port_kind,
        ) in self.bindings
        installed = tuple(
            item
            for item in self.installed
            if (
                item.operation,
                item.canonical_owner_ref,
                item.writer_port_kind,
            )
            == (operation, canonical_owner_ref, writer_port_kind)
            and callable(getattr(item.port, "admit", None))
        )
        if not exact_grant or not route_registered or len(installed) != 1:
            return None
        return canonical_owner_ref


def _installed_canonical_writer_bindings() -> tuple[InstalledCanonicalWriterBinding, ...]:
    # This is an installation fact, not generated from route requirements.  The
    # C7 transport operation has no current HTTP route binding, so unmatched
    # route declarations still deny rather than becoming self-certified owners.
    return (
        InstalledCanonicalWriterBinding(
            operation="rebuild_projection",
            canonical_owner_ref="successor-runtime",
            writer_port_kind="postgres.projection_rebuild.v2",
            port=C9ProjectionCanonicalWriterBinding(),
        ),
    )


def _configured_provider_catalog(settings_obj: object) -> RegisteredProviderCatalog:
    raw_allowlist = str(getattr(settings_obj, "production_provider_ids", "") or "")
    allowlist = tuple(
        dict.fromkeys(item.strip().lower() for item in raw_allowlist.split(",") if item.strip())
    )
    llm_provider_ids = tuple(
        provider
        for provider in _KNOWN_LLM_PROVIDER_IDS
        if _llm_provider_is_registered(provider)
    )
    from app.services.crawlers.registry import list_providers

    return RegisteredProviderCatalog(
        deployment_allowlist=allowlist,
        llm_provider_ids=llm_provider_ids,
        crawler_provider_ids=tuple(list_providers()),
    )


def _llm_provider_is_registered(provider_id: str) -> bool:
    try:
        resolve_llm_provider(provider_id)
    except LLMProviderResolutionError:
        return False
    return True


def build_production_runtime_bindings(
    engine: Engine,
    settings_obj: object | None = None,
) -> Annotated[
    ProductionRuntimeBindings,
    "kit:prepared-command "
    "effect_boundary=app.composition.production_runtime.build_production_runtime_bindings "
    "witness=test:production_startup_installs_runtime_bindings_and_route_coverage_passes",
]:
    """Bind real read-only sources and explicit denial for missing authorities."""

    if settings_obj is None:
        from app.settings.config import settings

        settings_obj = settings
    provider_catalog = _configured_provider_catalog(settings_obj)
    writer_bindings = tuple(
        (
            binding.operation,
            binding.canonical_owner_ref or "",
            binding.writer_port_kind or "",
        )
        for binding in load_production_route_bindings()
        if binding.requires_canonical_writer
    )
    return ProductionRuntimeBindings(
        project_scope_resolver=EngineProjectScopeResolver(engine),
        actor_scopes=PostgresProductionActorScopes(engine),
        approvals=PostgresProductionApprovals(engine),
        rate_observations=AtomicRedisRateObservations(
            redis_client.Redis.from_url(str(getattr(settings_obj, "redis_url", "") or "")),
            http_window_seconds=int(getattr(settings_obj, "production_http_rate_window_seconds", 60)),
            provider_window_seconds=int(getattr(settings_obj, "production_provider_rate_window_seconds", 60)),
        ),
        provider_catalog=provider_catalog,
        provider_selection=RegisteredProviderSelection(
            catalog=provider_catalog,
            llm_provider_ids=provider_catalog.llm_provider_ids,
            crawler_provider_ids=provider_catalog.crawler_provider_ids,
        ),
        canonical_writer=RegisteredCanonicalWriter(
            bindings=writer_bindings,
            installed=_installed_canonical_writer_bindings(),
        ),
    )


__all__ = [
    "EngineC9QueryReadPort",
    "EngineProjectScopeResolver",
    "PostgresC9CommandSubmissionPort",
    "C9ProjectionCanonicalWriterBinding",
    "PostgresProductionActorScopes",
    "PostgresProductionApprovals",
    "ProductionSuccessorRuntimeAppDependencies",
    "ProductionRuntimeAuthorityUnavailable",
    "AtomicRedisRateObservations",
    "RegisteredProviderCatalog",
    "InstalledCanonicalWriterBinding",
    "RegisteredCanonicalWriter",
    "RegisteredProviderSelection",
    "UnavailableCanonicalWriter",
    "UnavailableProviderCatalog",
    "UnavailableProviderSelection",
    "build_production_runtime_bindings",
    "build_production_successor_runtime_app_dependencies",
]
