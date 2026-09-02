"""Single-owner project scope, grant, and capability authority repositories."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Connection

from app.successor_runtime.runtime.ports import RuntimeScope
from app.successor_runtime.runtime.authority_grants import (
    AuthorityOperationScope,
    AuthorityResourceCeiling,
)

from .runtime_journal import (
    ExactBindingConflict,
    RecordNotFound,
    StaleRevisionError,
    _one_mapping,
    _project_values,
    _scope_key,
    _table,
    _utcnow,
)
from .session import compute_scope_digest, validate_project_schema_identifier


@dataclass(frozen=True, slots=True)
class AuthorityGrant:
    grant_id: str
    actor_id: str
    capability_id: str
    operation_scope_json: AuthorityOperationScope
    resource_ceiling_json: AuthorityResourceCeiling
    credential_ref: str | None
    grant_epoch: int
    expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class CapabilityAuthority:
    capability_id: str
    mode: str
    authority_epoch: int
    successor_claim_enabled: bool
    legacy_claim_enabled: bool
    allowlist_digest: str
    config_digest: str
    effective_at: datetime
    approval_ref: str
    rollback_target_ref: str | None = None

    def __post_init__(self) -> None:
        if self.successor_claim_enabled and self.legacy_claim_enabled:
            raise ValueError("legacy and successor claim authority cannot both be enabled")


class ProjectScopeRegistryRepository:
    def __init__(self, connection: Connection, scope: RuntimeScope) -> None:
        self.connection = connection
        self.scope = scope

    def load(self, *, for_update: bool = False) -> Mapping[str, Any]:
        """Load the sole current ACTIVE binding for this project."""

        table = _table("project_scope_registry")
        statement = select(table).where(
            table.c.project_key == _scope_key(self.scope),
            table.c.state == "ACTIVE",
        )
        if for_update:
            statement = statement.with_for_update()
        rows = self.connection.execute(statement).mappings().all()
        if not rows:
            raise RecordNotFound("active project scope registry row not found")
        if len(rows) != 1:
            raise ExactBindingConflict(
                "project scope registry has multiple ACTIVE rows"
            )
        return rows[0]

    def load_exact(
        self,
        registry_revision: int,
        *,
        incarnation: str | None = None,
        for_update: bool = False,
    ) -> Mapping[str, Any]:
        """Load one immutable historical binding by its exact revision."""

        table = _table("project_scope_registry")
        statement = select(table).where(
            table.c.project_key == _scope_key(self.scope),
            table.c.registry_revision == registry_revision,
        )
        if incarnation is not None:
            statement = statement.where(table.c.incarnation == incarnation)
        if for_update:
            statement = statement.with_for_update()
        row = _one_mapping(self.connection.execute(statement))
        if row is None:
            raise RecordNotFound(
                f"project scope registry revision not found: {registry_revision}"
            )
        return row

    def require_exact(self) -> Mapping[str, Any]:
        ref = self.scope.project_scope
        row = self.load_exact(
            ref.project_registry_revision,
            incarnation=ref.incarnation,
        )
        if (
            row["resolved_schema"] != ref.resolved_schema
            or int(row["registry_revision"]) != ref.project_registry_revision
            or row["incarnation"] != ref.incarnation
            or row["scope_digest"] != ref.scope_digest
        ):
            raise ExactBindingConflict("ProjectScopeRef is stale")
        return row

    def require_current(self) -> Mapping[str, Any]:
        row = self.require_exact()
        current = self.load()
        if (
            int(current["registry_revision"])
            != self.scope.project_scope.project_registry_revision
        ):
            raise ExactBindingConflict("ProjectScopeRef is not current")
        return row

    def revise(
        self,
        *,
        expected_revision: int,
        resolved_schema: str,
        registry_revision: int,
        scope_digest: str,
        incarnation: str,
        state: str,
        approval_ref: str,
    ) -> Mapping[str, Any]:
        """Append a successor scope row while retaining the predecessor.

        The predecessor's identity columns are immutable because runtime runs
        retain a foreign key to that exact revision.  Only its lifecycle state
        is retired; the successor gets a fresh revision and incarnation.
        """

        table = _table("project_scope_registry")
        if registry_revision != expected_revision + 1:
            raise ValueError(
                "successor registry_revision must equal expected_revision + 1"
            )
        if state != "ACTIVE":
            raise ValueError("successor project scope must enter ACTIVE state")
        validate_project_schema_identifier(resolved_schema)
        expected_digest = compute_scope_digest(
            _scope_key(self.scope),
            resolved_schema,
            registry_revision,
            incarnation,
        )
        if scope_digest != expected_digest:
            raise ExactBindingConflict("successor project scope digest mismatch")

        predecessor = self.require_current()
        if int(predecessor["registry_revision"]) != expected_revision:
            raise StaleRevisionError("project scope registry CAS failed")
        if predecessor["incarnation"] == incarnation:
            raise ExactBindingConflict(
                "successor project scope must use a fresh incarnation"
            )
        reused = (
            self.connection.execute(
                select(table)
                .where(table.c.incarnation == incarnation)
                .limit(1)
            )
            .mappings()
            .first()
        )
        if reused is not None:
            raise ExactBindingConflict(
                "project scope incarnation has already been used"
            )

        result = self.connection.execute(
            update(table)
            .where(
                table.c.project_key == _scope_key(self.scope),
                table.c.registry_revision == expected_revision,
                table.c.scope_digest == self.scope.project_scope.scope_digest,
                table.c.incarnation == self.scope.project_scope.incarnation,
                table.c.state == "ACTIVE",
            )
            .values(
                state="RETIRED",
                updated_at=_utcnow(),
            )
        )
        if getattr(result, "rowcount", None) != 1:
            raise StaleRevisionError("project scope registry CAS failed")
        now = _utcnow()
        self.connection.execute(
            insert(table).values(
                project_key=_scope_key(self.scope),
                resolved_schema=resolved_schema,
                registry_revision=registry_revision,
                scope_digest=scope_digest,
                incarnation=incarnation,
                state=state,
                updated_by=self.scope.actor_id,
                approval_ref=approval_ref,
                created_at=now,
                updated_at=now,
            )
        )
        return self.load_exact(registry_revision, incarnation=incarnation)


class AuthorityGrantRepository:
    def __init__(self, connection: Connection, scope: RuntimeScope) -> None:
        self.connection = connection
        self.scope = scope

    def create(self, grant: AuthorityGrant) -> Mapping[str, Any]:
        table = _table("runtime_authority_grants")
        values = _project_values(
            self.scope,
            {
                "grant_id": grant.grant_id,
                "actor_id": grant.actor_id,
                "capability_id": grant.capability_id,
                "operation_scope_json": grant.operation_scope_json.model_dump(mode="json"),
                "resource_ceiling_json": grant.resource_ceiling_json.model_dump(mode="json"),
                "credential_ref": grant.credential_ref,
                "grant_epoch": grant.grant_epoch,
                "expires_at": grant.expires_at,
                "revoked_at": None,
                "revision": 0,
                "created_at": _utcnow(),
                "updated_at": _utcnow(),
            },
        )
        self.connection.execute(insert(table).values(**values))
        return self.load(grant.grant_id)

    def load(self, grant_id: str, *, for_update: bool = False) -> Mapping[str, Any]:
        table = _table("runtime_authority_grants")
        statement = select(table).where(
            table.c.project_key == _scope_key(self.scope), table.c.grant_id == grant_id
        )
        if for_update:
            statement = statement.with_for_update()
        row = _one_mapping(self.connection.execute(statement))
        if row is None:
            raise RecordNotFound(f"authority grant not found: {grant_id}")
        return row

    def revoke(
        self, grant_id: str, *, expected_revision: int, revoked_at: datetime
    ) -> Mapping[str, Any]:
        table = _table("runtime_authority_grants")
        result = self.connection.execute(
            update(table)
            .where(
                table.c.project_key == _scope_key(self.scope),
                table.c.grant_id == grant_id,
                table.c.revision == expected_revision,
                table.c.revoked_at.is_(None),
            )
            .values(
                revoked_at=revoked_at,
                revision=expected_revision + 1,
                updated_at=_utcnow(),
            )
        )
        if getattr(result, "rowcount", None) != 1:
            raise StaleRevisionError("authority grant revoke CAS failed")
        return self.load(grant_id)

    def current_for(
        self, *, actor_id: str, capability_id: str, at: datetime
    ) -> tuple[Mapping[str, Any], ...]:
        table = _table("runtime_authority_grants")
        rows = self.connection.execute(
            select(table).where(
                table.c.project_key == _scope_key(self.scope),
                table.c.actor_id == actor_id,
                table.c.capability_id == capability_id,
                table.c.revoked_at.is_(None),
                (table.c.expires_at.is_(None) | (table.c.expires_at > at)),
            )
        ).mappings().all()
        return tuple(rows)


class CapabilityAuthorityRepository:
    def __init__(self, connection: Connection, scope: RuntimeScope) -> None:
        self.connection = connection
        self.scope = scope

    def load(self, capability_id: str, *, for_update: bool = False) -> Mapping[str, Any]:
        table = _table("runtime_capability_authority")
        statement = select(table).where(
            table.c.project_key == _scope_key(self.scope),
            table.c.capability_id == capability_id,
        )
        if for_update:
            statement = statement.with_for_update()
        row = _one_mapping(self.connection.execute(statement))
        if row is None:
            raise RecordNotFound(f"capability authority not found: {capability_id}")
        if row["successor_claim_enabled"] and row["legacy_claim_enabled"]:
            raise ExactBindingConflict("database contains double claim authority")
        return row

    def revise(
        self, authority: CapabilityAuthority, *, expected_revision: int
    ) -> Mapping[str, Any]:
        table = _table("runtime_capability_authority")
        result = self.connection.execute(
            update(table)
            .where(
                table.c.project_key == _scope_key(self.scope),
                table.c.capability_id == authority.capability_id,
                table.c.revision == expected_revision,
            )
            .values(
                mode=authority.mode,
                authority_epoch=authority.authority_epoch,
                successor_claim_enabled=authority.successor_claim_enabled,
                legacy_claim_enabled=authority.legacy_claim_enabled,
                allowlist_digest=authority.allowlist_digest,
                config_digest=authority.config_digest,
                effective_at=authority.effective_at,
                updated_by=self.scope.actor_id,
                approval_ref=authority.approval_ref,
                rollback_target_ref=authority.rollback_target_ref,
                revision=expected_revision + 1,
                updated_at=_utcnow(),
            )
        )
        if getattr(result, "rowcount", None) != 1:
            raise StaleRevisionError("capability authority CAS failed")
        return self.load(authority.capability_id)


__all__ = [
    "AuthorityGrant",
    "AuthorityGrantRepository",
    "CapabilityAuthority",
    "CapabilityAuthorityRepository",
    "ProjectScopeRegistryRepository",
]
