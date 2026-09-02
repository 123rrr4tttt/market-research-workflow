"""Exact QualifiedPlan and per-step authorization persistence."""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy import insert, select
from sqlalchemy.engine import Connection

from app.successor_runtime.runtime.ports import RuntimeScope
from app.successor_runtime.runtime.qualification import StepAuthorizationBinding

from .runtime_journal import (
    ExactBindingConflict,
    ExactQualificationBinding,
    RecordNotFound,
    _one_mapping,
    _project_values,
    _scope_key,
    _table,
    _utcnow,
    validate_authorization_row,
    validate_qualification_row,
)


def _authorization_values(binding: StepAuthorizationBinding) -> dict[str, object]:
    return {
        "authorization_id": f"authorization:{binding.binding_digest}",
        "run_id": binding.run_id,
        "step_id": binding.step_id,
        "operation_kind": binding.operation_kind,
        "operation_contract_digest": binding.operation_contract_digest,
        "capability_id": binding.capability_id,
        "claim_owner": binding.claim_owner,
        "claim_authority_epoch": binding.claim_authority_epoch,
        "claim_policy_digest": binding.claim_policy_digest,
        "payload_digest": binding.payload_digest,
        "actor_id": binding.actor_id,
        "project_registry_revision": binding.project_registry_revision,
        "project_scope_digest": binding.project_scope_digest,
        "grant_epoch": binding.grant_epoch,
        "expires_at": binding.expires_at,
        "approval_ref": binding.approval_refs[0] if binding.approval_refs else None,
        "authorization_digest": binding.binding_digest,
        "interpreter_binding_digest": binding.interpreter_binding_digest,
        "deployment_catalog_digest": binding.deployment_catalog_digest,
        "authority_source_bindings_json": [
            source.model_dump(mode="json")
            for source in binding.authority_source_bindings
        ],
        "grants_digest": binding.grants_digest,
        "approval_refs_json": list(binding.approval_refs),
        "resource_ceiling_digest": binding.resource_ceiling_digest,
        "resource_policy_epoch": binding.resource_policy_epoch,
        "queue_eligibility_digest": binding.queue_eligibility_digest,
        "canonical_base_revision": binding.canonical_base_revision,
        "canonical_incarnation": binding.canonical_incarnation,
        "authorization_binding_json": binding.model_dump(mode="json"),
    }


class QualificationStoreRepository:
    """Persist one content-addressed qualification closure without granting authority."""

    def __init__(self, connection: Connection, scope: RuntimeScope) -> None:
        self.connection = connection
        self.scope = scope

    def persist(self, binding: ExactQualificationBinding) -> Mapping[str, object]:
        project_key = _scope_key(self.scope)
        if binding.project_key != project_key:
            raise ExactBindingConflict("qualification scope mismatch")
        if binding.authority_context.actor_id != self.scope.actor_id:
            raise ExactBindingConflict("qualification actor mismatch")
        scope_ref = self.scope.project_scope
        context = binding.authority_context
        if (
            context.project_key != project_key
            or context.resolved_schema != scope_ref.resolved_schema
            or context.project_registry_revision != scope_ref.project_registry_revision
            or context.project_scope_digest != scope_ref.scope_digest
        ):
            raise ExactBindingConflict("qualification ProjectScopeRef drift")
        for authorization in binding.qualified_plan.step_bindings:
            if (
                authorization.project_registry_revision
                != scope_ref.project_registry_revision
                or authorization.project_scope_digest != scope_ref.scope_digest
            ):
                raise ExactBindingConflict("step authorization ProjectScopeRef drift")

        qualifications = _table("runtime_qualifications")
        current = _one_mapping(
            self.connection.execute(
                select(qualifications).where(
                    qualifications.c.project_key == project_key,
                    qualifications.c.qualification_id == binding.qualification_id,
                )
            )
        )
        values = _project_values(
            self.scope,
            {
                "qualification_id": binding.qualification_id,
                "run_id": binding.run_id,
                "plan_id": binding.plan_id,
                "plan_digest": binding.plan_digest,
                "authority_context_digest": binding.authority_context_digest,
                "decision": binding.decision,
                "qualification_digest": binding.qualified_plan.qualification_digest,
                "qualification_binding_digest": binding.qualification_binding_digest,
                "qualified_plan_json": binding.qualified_plan.model_dump(mode="json"),
                "qualification_binding_json": binding.model_dump(mode="json"),
                "queue_eligibility_digest": _common_or_none(
                    item.queue_eligibility_digest
                    for item in binding.qualified_plan.step_bindings
                ),
                "resource_policy_epoch": _common_or_none(
                    item.resource_policy_epoch
                    for item in binding.qualified_plan.step_bindings
                ),
                "approval_ref": (
                    binding.authority_context.approval_refs[0]
                    if binding.authority_context.approval_refs
                    else None
                ),
            },
        )
        if current is not None:
            validate_qualification_row(current)
            if (
                current["qualification_binding_digest"]
                != binding.qualification_binding_digest
            ):
                raise ExactBindingConflict("qualification identity was rebound")
        else:
            now = _utcnow()
            self.connection.execute(
                insert(qualifications).values(**values, created_at=now, updated_at=now)
            )

        authorizations = _table("runtime_step_authorizations")
        for authorization in binding.qualified_plan.step_bindings:
            # These nested JSON columns are themselves covered by the exact
            # typed StepAuthorizationBinding.  Do not pass them through the
            # generic public metadata allowlist, which intentionally rejects
            # untyped nested control objects.
            auth_values = {
                "project_key": _scope_key(self.scope),
                **_authorization_values(authorization),
            }
            current_auth = _one_mapping(
                self.connection.execute(
                    select(authorizations).where(
                        authorizations.c.project_key == project_key,
                        authorizations.c.run_id == authorization.run_id,
                        authorizations.c.step_id == authorization.step_id,
                        authorizations.c.claim_authority_epoch
                        == authorization.claim_authority_epoch,
                    )
                )
            )
            if current_auth is not None:
                validate_authorization_row(current_auth)
                if current_auth["authorization_digest"] != authorization.binding_digest:
                    raise ExactBindingConflict("step authorization epoch was rebound")
                continue
            now = _utcnow()
            self.connection.execute(
                insert(authorizations).values(
                    **auth_values, created_at=now, updated_at=now
                )
            )
        return self.load(binding.qualification_id)

    def load(self, qualification_id: str) -> Mapping[str, object]:
        table = _table("runtime_qualifications")
        row = _one_mapping(
            self.connection.execute(
                select(table).where(
                    table.c.project_key == _scope_key(self.scope),
                    table.c.qualification_id == qualification_id,
                )
            )
        )
        if row is None:
            raise RecordNotFound(f"qualification not found: {qualification_id}")
        validate_qualification_row(row)
        return row

    def load_step_binding(self, run_id: str, step_id: str) -> StepAuthorizationBinding:
        table = _table("runtime_step_authorizations")
        rows = (
            self.connection.execute(
                select(table)
                .where(
                    table.c.project_key == _scope_key(self.scope),
                    table.c.run_id == run_id,
                    table.c.step_id == step_id,
                )
                .order_by(table.c.claim_authority_epoch.desc())
            )
            .mappings()
            .all()
        )
        if not rows:
            raise RecordNotFound(f"step authorization not found: {run_id}/{step_id}")
        current = rows[0]
        if (
            len(rows) > 1
            and rows[1]["claim_authority_epoch"] == current["claim_authority_epoch"]
        ):
            raise ExactBindingConflict("multiple current step authorization rows")
        return validate_authorization_row(current)


def _common_or_none(values: object) -> object | None:
    items = tuple(values)  # type: ignore[arg-type]
    if not items:
        return None
    return items[0] if all(item == items[0] for item in items) else None


__all__ = ["QualificationStoreRepository"]
