"""Production-only adapters for existing authoritative runtime sources.

Read adapters remain observation boundaries. Capabilities without an installed
production authority source use explicit conservative-denial ports.
"""

# ruff: noqa: TRY003

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
from typing import Annotated

import redis as redis_client
from sqlalchemy import MetaData, and_, inspect, or_, select, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.production_contract import APPROVED_DECISION, ApprovalGrant, ProviderClass
from app.services.request_identity import RequestActorContext
from app.services.llm.ports import LLMProviderResolutionError, resolve_llm_provider
from app.successor_runtime.runtime.authority_grants import AuthorityOperationScope
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
from app.successor_runtime.runtime.resources import ResourcePolicySnapshot
from app.successor_runtime.language.catalog import OperationContractRegistry
from app.successor_runtime.substrate.postgres.authority import (
    AuthorityGrant, AuthorityGrantRepository, CapabilityAuthority, ProjectScopeRegistryRepository,
)
from app.successor_runtime.substrate.postgres.runtime_journal import ExactBindingConflict
from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES, project_tables
from app.successor_runtime.substrate.postgres.session import (
    RegistryBackedProjectScopeResolver,
    ServerProjectScopeResolver,
    validate_project_scope_ref,
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


def _validate_runtime_authority_declaration(
    *, administrator: RequestActorContext,
    project_scope: ProjectScopeRef, grant: AuthorityGrant,
    capability: CapabilityAuthority,
    resource: ResourcePolicySnapshot | tuple[ResourcePolicySnapshot, ...],
    installed: OperationContractRegistry,
    connection: Connection | None = None,
) -> tuple[ResourcePolicySnapshot, ...]:
    """Share declaration checks, retaining original resolver error priority."""
    now = datetime.now(UTC)
    if (not administrator.actor_trusted or not administrator.actor_id or not grant.actor_id
            or grant.grant_epoch < 1 or grant.expires_at is None
            or grant.expires_at.tzinfo is None or grant.expires_at <= now):
        raise ProductionRuntimeAuthorityUnavailable("installation requires a trusted administrator and a finite grant")
    if (connection is not None
            and ServerProjectScopeResolver(connection=connection).resolve(project_scope.project_key) != project_scope):
        raise ExactBindingConflict("installation project scope is stale")
    resources = (resource,) if isinstance(resource, ResourcePolicySnapshot) else resource
    policies_by_class = {policy.resource_class.value: policy for policy in resources}
    if not resources or len(policies_by_class) != len(resources):
        raise ExactBindingConflict("installation resource policies must be non-empty and unique")
    if (
        grant.capability_id != capability.capability_id
        or any(policy.capability_id != capability.capability_id
               or policy.project_key != project_scope.project_key for policy in resources)
        or grant.operation_scope_json.project_scope_digest != project_scope.scope_digest
        or capability.legacy_claim_enabled or not capability.successor_claim_enabled
        or capability.mode not in {"on", "canary"}
        or not capability.rollback_target_ref or not capability.approval_ref
    ):
        raise ExactBindingConflict("installation scope/capability declaration mismatch")
    for kind in grant.operation_scope_json.operation_kinds:
        ref = installed.catalog.lookup(kind)
        if ref is None or installed.resolve_required(ref).owner_capability_id != capability.capability_id:
            raise ExactBindingConflict("installation grant references an uninstalled operation")
    resource_limits = grant.resource_ceiling_json.limits
    for limit in resource_limits:
        policy = policies_by_class.get(limit.resource_class)
        if (policy is None or limit.units > policy.max_units
                or grant.resource_ceiling_json.max_active > policy.max_capability_active):
            raise ExactBindingConflict("installation grant exceeds the declared resource policy")
    return resources


def install_runtime_authority(
    connection: Connection, *, administrator: RequestActorContext,
    project_scope: ProjectScopeRef, grant: AuthorityGrant,
    capability: CapabilityAuthority,
    resource: ResourcePolicySnapshot | tuple[ResourcePolicySnapshot, ...],
    installed: OperationContractRegistry,
) -> None:
    """Apply an explicit, finite administrator deployment declaration.

    This deployment entry is never called by a request or policy PASS. Existing
    mismatched/revoked records require their normal owner transition; installation
    cannot overwrite them or silently renew an expired grant.
    """
    resources = _validate_runtime_authority_declaration(
        administrator=administrator, project_scope=project_scope, grant=grant,
        capability=capability, resource=resource, installed=installed, connection=connection,
    )
    capability_values = {
        **asdict(capability), "project_key": project_scope.project_key,
        "updated_by": administrator.actor_id,
    }
    resource_values = tuple({
        "resource_policy_id": f"policy:{policy.policy_digest}",
        "project_key": policy.project_key, "capability_id": policy.capability_id,
        "resource_class": policy.resource_class.value,
        "concurrency_limit": policy.max_capability_active,
        "max_project_active": policy.max_project_active,
        "max_capability_active": policy.max_capability_active,
        "max_resource_active": policy.max_resource_active,
        "units_ceiling": policy.max_units, "provider_limit": policy.max_provider_active,
        "policy_epoch": policy.policy_epoch, "policy_digest": policy.policy_digest,
    } for policy in resources)
    for name, values in (("runtime_capability_authority", capability_values),
                         *(("runtime_resource_policies", values) for values in resource_values)):
        table = PUBLIC_TABLES[name]
        connection.execute(pg_insert(table).values(**values).on_conflict_do_nothing())
        row = connection.execute(select(table).where(
            table.c.project_key == project_scope.project_key,
            table.c.capability_id == capability.capability_id,
            *(() if name == "runtime_capability_authority" else (
                table.c.policy_epoch == values["policy_epoch"],
                table.c.resource_class == values["resource_class"],
            )),
        )).mappings().one()
        if any(row[key] != value for key, value in values.items()):
            raise ExactBindingConflict("installation conflicts with existing authority/resource facts")
    scope = RuntimeScope(project_scope=project_scope, actor_id=administrator.actor_id)
    table = PUBLIC_TABLES["runtime_authority_grants"]
    row = connection.execute(select(table).where(
        table.c.project_key == project_scope.project_key, table.c.grant_id == grant.grant_id,
    )).mappings().one_or_none()
    if row is None:
        AuthorityGrantRepository(connection, scope).create(grant)
    else:
        expected = {
            **asdict(grant),
            "operation_scope_json": grant.operation_scope_json.model_dump(mode="json"),
            "resource_ceiling_json": grant.resource_ceiling_json.model_dump(mode="json"),
        }
        if row["revoked_at"] is not None or any(row[key] != value for key, value in expected.items()):
            raise ExactBindingConflict("installation cannot replace or renew an existing grant")


def install_project_runtime(
    connection: Connection, *, administrator: RequestActorContext,
    project_scope: ProjectScopeRef, grant: AuthorityGrant,
    capability: CapabilityAuthority,
    resource: ResourcePolicySnapshot | tuple[ResourcePolicySnapshot, ...],
    installed: OperationContractRegistry,
) -> ProjectScopeRef:
    """Provision the first Runtime binding for an existing enabled Project.

    The caller owns commit. Scope, declared project tables and finite authority
    installation share one savepoint; this entry never bootstraps a Project.
    """
    validate_project_scope_ref(project_scope)
    _validate_runtime_authority_declaration(
        administrator=administrator, project_scope=project_scope, grant=grant,
        capability=capability, resource=resource, installed=installed,
    )
    with connection.begin_nested():
        project = connection.execute(text(
            "SELECT schema_name, enabled FROM public.projects "
            "WHERE project_key = :project_key FOR UPDATE"
        ), {"project_key": project_scope.project_key}).mappings().one_or_none()
        if (project is None or project["enabled"] is not True
                or project["schema_name"] != project_scope.resolved_schema):
            raise ExactBindingConflict("first installation requires the existing enabled Project schema")
        if not inspect(connection).has_schema(project_scope.resolved_schema):
            raise ExactBindingConflict("first installation requires the actual Project schema")
        scope = RuntimeScope(project_scope=project_scope, actor_id=administrator.actor_id)
        ProjectScopeRegistryRepository(connection, scope).create_initial(
            approval_ref=capability.approval_ref,
        )
        metadata = MetaData()
        tables = project_tables(metadata, project_scope.resolved_schema).as_dict()
        metadata.create_all(connection, tables=list(tables.values()), checkfirst=True)
        install_runtime_authority(
            connection, administrator=administrator, project_scope=project_scope, grant=grant,
            capability=capability, resource=resource, installed=installed,
        )
        return ServerProjectScopeResolver(connection=connection).resolve(project_scope.project_key)


@contextmanager
def _read_only_connection(engine: Engine) -> Iterator[Connection]:
    with engine.connect() as connection:
        # Adapters only issue SELECT statements; connection close rolls back
        # the implicit read transaction.
        yield connection


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
    return ()


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
        project_scope_resolver=RegistryBackedProjectScopeResolver(engine=engine),
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
    "PostgresProductionActorScopes",
    "PostgresProductionApprovals",
    "ProductionRuntimeAuthorityUnavailable",
    "AtomicRedisRateObservations",
    "RegisteredProviderCatalog",
    "InstalledCanonicalWriterBinding",
    "RegisteredCanonicalWriter",
    "RegisteredProviderSelection",
    "build_production_runtime_bindings",
]
