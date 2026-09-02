"""Read-only aggregation of current authority sources.

This provider is deliberately not an authority owner.  It only locks/reads the
canonical scope, grant, approval, and capability-authority rows, recomputes the
content closure, and returns a fresh typed binding.  No method mutates, extends,
or renews authority.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import MetaData, or_, select
from sqlalchemy.engine import Connection

from app.successor_runtime.runtime.assignments import canonical_digest
from app.successor_runtime.runtime.ports import RuntimeScope
from app.successor_runtime.runtime.qualification import (
    AuthorityContext,
    AuthoritySourceBinding,
    StepAuthorizationBinding,
    require_current_authority,
)
from app.successor_runtime.capabilities import DeliveryAuthoritySnapshot

from .models import project_tables
from .runtime_journal import (
    ExactBindingConflict,
    RecordNotFound,
    _mapping_rows,
    _one_mapping,
    _scope_key,
    _table,
    _utcnow,
    validate_authorization_row,
)


def _digestable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _digestable(child) for key, child in value.items()}
    if isinstance(value, (tuple, list)):
        return [_digestable(child) for child in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _row_digest(row: Mapping[str, Any], fields: Sequence[str]) -> str:
    return canonical_digest({field: _digestable(row[field]) for field in fields})


class PostgresAuthorityProvider:
    def __init__(self, connection: Connection, scope: RuntimeScope) -> None:
        self.connection = connection
        self.scope = scope

    def current_context(
        self,
        actor_id: str,
        *,
        capability_id: str,
        approval_refs: tuple[str, ...] = (),
        canonical_base_revision: int,
        canonical_incarnation: str,
        now: datetime | None = None,
    ) -> AuthorityContext:
        if actor_id != self.scope.actor_id:
            raise ExactBindingConflict("authority actor differs from RuntimeScope")
        observed_at = now or _utcnow()
        project_key = _scope_key(self.scope)
        scope_ref = self.scope.project_scope

        scopes = _table("project_scope_registry")
        scope_row = _one_mapping(
            self.connection.execute(
                select(scopes)
                .where(
                    scopes.c.project_key == project_key,
                    scopes.c.registry_revision == scope_ref.project_registry_revision,
                    scopes.c.scope_digest == scope_ref.scope_digest,
                    scopes.c.incarnation == scope_ref.incarnation,
                    scopes.c.resolved_schema == scope_ref.resolved_schema,
                    scopes.c.state == "ACTIVE",
                )
                .with_for_update(read=True)
            )
        )
        if scope_row is None:
            raise ExactBindingConflict("current project scope binding is stale")

        capabilities = _table("runtime_capability_authority")
        capability = _one_mapping(
            self.connection.execute(
                select(capabilities)
                .where(
                    capabilities.c.project_key == project_key,
                    capabilities.c.capability_id == capability_id,
                )
                .with_for_update(read=True)
            )
        )
        if capability is None:
            raise RecordNotFound(f"capability authority not found: {capability_id}")
        if (
            not capability["successor_claim_enabled"]
            or capability["legacy_claim_enabled"]
        ):
            raise ExactBindingConflict(
                "successor is not the current single claim owner"
            )

        grants_table = _table("runtime_authority_grants")
        grants = _mapping_rows(
            self.connection.execute(
                select(grants_table)
                .where(
                    grants_table.c.project_key == project_key,
                    grants_table.c.actor_id == actor_id,
                    grants_table.c.capability_id == capability_id,
                    grants_table.c.revoked_at.is_(None),
                    or_(
                        grants_table.c.expires_at.is_(None),
                        grants_table.c.expires_at > observed_at,
                    ),
                )
                .order_by(grants_table.c.grant_epoch, grants_table.c.grant_id)
                .with_for_update(read=True)
            )
        )
        if not grants:
            raise ExactBindingConflict("no current authority grant")

        approvals_table = _table("runtime_approvals")
        approvals: list[Mapping[str, Any]] = []
        for approval_ref in approval_refs:
            approval = _one_mapping(
                self.connection.execute(
                    select(approvals_table)
                    .where(
                        approvals_table.c.project_key == project_key,
                        approvals_table.c.approval_id == approval_ref,
                    )
                    .with_for_update(read=True)
                )
            )
            if (
                approval is None
                or approval["decision"] != "APPROVED"
                or (
                    approval["expires_at"] is not None
                    and approval["expires_at"] <= observed_at
                )
            ):
                raise ExactBindingConflict(
                    f"approval is absent/revoked/expired: {approval_ref}"
                )
            approvals.append(approval)

        sources: list[AuthoritySourceBinding] = [
            AuthoritySourceBinding(
                source_kind="PROJECT_SCOPE",
                source_ref=f"project-scope:{project_key}:{scope_ref.project_registry_revision}",
                source_digest=_row_digest(
                    scope_row,
                    (
                        "project_key",
                        "registry_revision",
                        "resolved_schema",
                        "scope_digest",
                        "incarnation",
                        "state",
                    ),
                ),
                source_epoch=scope_ref.project_registry_revision,
            )
        ]
        for grant in grants:
            sources.append(
                AuthoritySourceBinding(
                    source_kind="GRANT",
                    source_ref=f"grant:{grant['grant_id']}",
                    source_digest=_row_digest(
                        grant,
                        (
                            "grant_id",
                            "actor_id",
                            "capability_id",
                            "operation_scope_json",
                            "resource_ceiling_json",
                            "credential_ref",
                            "grant_epoch",
                            "expires_at",
                            "revoked_at",
                            "revision",
                        ),
                    ),
                    source_epoch=int(grant["grant_epoch"]),
                )
            )
            if grant["credential_ref"] is not None:
                sources.append(
                    AuthoritySourceBinding(
                        source_kind="CREDENTIAL_REF",
                        source_ref=str(grant["credential_ref"]),
                        source_digest=canonical_digest(
                            {
                                "credential_ref": str(grant["credential_ref"]),
                                "grant_id": str(grant["grant_id"]),
                                "grant_epoch": int(grant["grant_epoch"]),
                            }
                        ),
                        source_epoch=int(grant["grant_epoch"]),
                    )
                )
        for approval in approvals:
            sources.append(
                AuthoritySourceBinding(
                    source_kind="APPROVAL",
                    source_ref=f"approval:{approval['approval_id']}",
                    source_digest=_row_digest(
                        approval,
                        (
                            "approval_id",
                            "actor_id",
                            "run_id",
                            "step_id",
                            "payload_digest",
                            "decision",
                            "expires_at",
                            "authority_digest",
                            "revision",
                        ),
                    ),
                    source_epoch=int(approval["revision"]),
                )
            )
        sources.append(
            AuthoritySourceBinding(
                source_kind="CAPABILITY_AUTHORITY",
                source_ref=f"capability-authority:{project_key}:{capability_id}",
                source_digest=_row_digest(
                    capability,
                    (
                        "project_key",
                        "capability_id",
                        "mode",
                        "authority_epoch",
                        "successor_claim_enabled",
                        "legacy_claim_enabled",
                        "allowlist_digest",
                        "config_digest",
                        "approval_ref",
                        "rollback_target_ref",
                        "revision",
                    ),
                ),
                source_epoch=int(capability["authority_epoch"]),
            )
        )
        ordered = tuple(
            sorted(sources, key=lambda item: (item.source_kind, item.source_ref))
        )
        grant_expiries = [
            grant["expires_at"] for grant in grants if grant["expires_at"] is not None
        ]
        approval_expiries = [
            approval["expires_at"]
            for approval in approvals
            if approval["expires_at"] is not None
        ]
        expiries = grant_expiries + approval_expiries
        if not expiries:
            raise ExactBindingConflict("authority context requires a bounded expiry")
        return AuthorityContext.from_content(
            actor_id=actor_id,
            project_key=project_key,
            resolved_schema=scope_ref.resolved_schema,
            project_registry_revision=scope_ref.project_registry_revision,
            project_scope_digest=scope_ref.scope_digest,
            authority_source_bindings=ordered,
            grants_digest=canonical_digest(
                tuple(
                    source.model_dump(mode="json")
                    for source in ordered
                    if source.source_kind in {"GRANT", "CREDENTIAL_REF"}
                )
            ),
            grant_epoch=max(int(grant["grant_epoch"]) for grant in grants),
            expires_at=min(expiries),
            operation_scope_digest=canonical_digest(
                tuple(_digestable(grant["operation_scope_json"]) for grant in grants)
            ),
            resource_ceiling_digest=canonical_digest(
                tuple(_digestable(grant["resource_ceiling_json"]) for grant in grants)
            ),
            canonical_base_revision=canonical_base_revision,
            canonical_incarnation=canonical_incarnation,
            approval_refs=approval_refs,
        )

    def current_delivery_authority(
        self,
        scope: object,
        capability_id: str,
    ) -> DeliveryAuthoritySnapshot:
        if scope != self.scope:
            raise ExactBindingConflict("delivery authority scope drift")
        table = _table("runtime_capability_authority")
        row = _one_mapping(
            self.connection.execute(
                select(table).where(
                    table.c.project_key == _scope_key(self.scope),
                    table.c.capability_id == capability_id,
                )
            )
        )
        if row is None:
            raise RecordNotFound("delivery capability authority is absent")
        authorizations = _table("runtime_step_authorizations")
        rows = self.connection.execute(
            select(
                authorizations.c.claim_authority_epoch,
                authorizations.c.claim_policy_digest,
            ).where(
                authorizations.c.project_key == _scope_key(self.scope),
                authorizations.c.capability_id == capability_id,
            )
        ).mappings().all()
        epochs = {int(item["claim_authority_epoch"]) for item in rows}
        policies = {str(item["claim_policy_digest"]) for item in rows}
        if len(epochs) != 1 or len(policies) != 1:
            raise ExactBindingConflict("delivery step authority is absent or ambiguous")
        epoch = epochs.pop()
        if epoch != int(row["authority_epoch"]):
            raise ExactBindingConflict("delivery capability/step authority epoch drift")
        return DeliveryAuthoritySnapshot(
            capability_id=capability_id,
            authority_epoch=epoch,
            authority_digest=str(row["config_digest"]),
            claim_policy_digest=policies.pop(),
            successor_claim_enabled=bool(row["successor_claim_enabled"]),
            legacy_claim_enabled=bool(row["legacy_claim_enabled"]),
        )

    def current_step_binding(
        self, run_id: str, step_id: str, *, now: datetime | None = None
    ) -> StepAuthorizationBinding:
        table = _table("runtime_step_authorizations")
        row = _one_mapping(
            self.connection.execute(
                select(table)
                .where(
                    table.c.project_key == _scope_key(self.scope),
                    table.c.run_id == run_id,
                    table.c.step_id == step_id,
                )
                .order_by(table.c.claim_authority_epoch.desc())
                .limit(1)
            )
        )
        if row is None:
            raise RecordNotFound(f"step authorization not found: {run_id}/{step_id}")
        previous = validate_authorization_row(row)
        # The RuntimeNode is the executor, not the frozen authority subject.
        # Rebuild the authorization context under its exact stored actor while
        # retaining the same server-resolved project scope.
        authority_scope = RuntimeScope(
            project_scope=self.scope.project_scope,
            actor_id=previous.actor_id,
        )
        context = PostgresAuthorityProvider(
            self.connection,
            authority_scope,
        ).current_context(
            previous.actor_id,
            capability_id=previous.capability_id,
            approval_refs=(
                previous.approval_refs
                if any(
                    source.source_kind == "APPROVAL"
                    for source in previous.authority_source_bindings
                )
                else ()
            ),
            canonical_base_revision=previous.canonical_base_revision,
            canonical_incarnation=previous.canonical_incarnation,
            now=now,
        )
        return StepAuthorizationBinding.from_content(
            **{
                **previous.model_dump(mode="python", exclude={"binding_digest"}),
                "authority_source_bindings": context.authority_source_bindings,
                "grants_digest": context.grants_digest,
                "resource_ceiling_digest": context.resource_ceiling_digest,
                "grant_epoch": context.grant_epoch,
                "expires_at": context.expires_at,
            }
        )

    def current_approval(self, approval_id: str) -> Mapping[str, Any]:
        table = _table("runtime_approvals")
        row = _one_mapping(
            self.connection.execute(
                select(table).where(
                    table.c.project_key == _scope_key(self.scope),
                    table.c.approval_id == approval_id,
                )
            )
        )
        if row is None:
            raise RecordNotFound(f"approval not found: {approval_id}")
        if row["decision"] != "APPROVED" or (
            row["expires_at"] is not None and row["expires_at"] <= _utcnow()
        ):
            raise ExactBindingConflict("approval is not currently effective")
        return row

    def current_canonical_head(
        self, canonical_owner: str, object_id: str
    ) -> Mapping[str, Any]:
        tables = project_tables(MetaData(), self.scope.project_scope.resolved_schema)
        objects = tables.research_objects
        row = _one_mapping(
            self.connection.execute(
                select(objects)
                .where(
                    objects.c.project_key == _scope_key(self.scope),
                    objects.c.object_id == object_id,
                    objects.c.object_type == canonical_owner,
                    objects.c.lifecycle_state.in_(("DRAFT", "ADMITTED")),
                )
                .order_by(objects.c.revision.desc())
                .limit(1)
            )
        )
        if row is None:
            raise RecordNotFound(
                f"canonical head not found: {canonical_owner}/{object_id}"
            )
        return row

    def is_revoked(
        self, binding_digest: str, grant_epoch: int, *, now: datetime | None = None
    ) -> bool:
        table = _table("runtime_step_authorizations")
        row = _one_mapping(
            self.connection.execute(
                select(table).where(
                    table.c.project_key == _scope_key(self.scope),
                    table.c.authorization_digest == binding_digest,
                )
            )
        )
        if row is None:
            return True
        expected = validate_authorization_row(row)
        if expected.grant_epoch != grant_epoch:
            return True
        try:
            current = self.current_step_binding(
                expected.run_id, expected.step_id, now=now
            )
            require_current_authority(expected, current, now=now)
        except (ExactBindingConflict, RecordNotFound, ValueError):
            return True
        return False


__all__ = ["PostgresAuthorityProvider"]
