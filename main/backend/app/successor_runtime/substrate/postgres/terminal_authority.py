"""Same-UoW current-authority proof for terminal runtime mutations."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.engine import Connection

from app.successor_runtime.runtime.assignments import RuntimeAssignment
from app.successor_runtime.runtime.ports import RuntimeScope
from app.successor_runtime.runtime.qualification import require_current_authority

from .authority_provider import PostgresAuthorityProvider
from .models import PUBLIC_TABLES
from .runtime_journal import (
    ExactBindingConflict,
    validate_authorization_row,
)


class PostgresTerminalAuthorityVerifier:
    """Re-open the persisted and current binding before terminal CAS writes."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def require_current(
        self,
        *,
        scope: RuntimeScope,
        assignment: RuntimeAssignment,
        authorization_digest: str,
        observed_at: datetime,
    ) -> None:
        if assignment.operation_contract_ref is None or assignment.step_id is None:
            raise ExactBindingConflict(
                "terminal authority requires a step-scoped operation assignment"
            )
        rows = tuple(
            self._connection.execute(
                select(PUBLIC_TABLES["runtime_step_authorizations"])
                .where(
                    PUBLIC_TABLES["runtime_step_authorizations"].c.project_key
                    == assignment.project_key,
                    PUBLIC_TABLES["runtime_step_authorizations"].c.run_id
                    == assignment.run_id,
                    PUBLIC_TABLES["runtime_step_authorizations"].c.step_id
                    == assignment.step_id,
                )
                .with_for_update(read=True)
            ).mappings()
        )
        if len(rows) != 1:
            raise ExactBindingConflict(
                "terminal mutation requires one persisted step authorization"
            )
        stored = validate_authorization_row(rows[0])
        expected = {
            "operation_kind": assignment.operation_contract_ref.kind,
            "operation_contract_digest": assignment.operation_contract_digest,
            "capability_id": assignment.capability_id,
            "claim_policy_digest": assignment.claim_policy_digest,
            "project_key": assignment.project_key,
            "interpreter_binding_digest": assignment.handler_binding_digest,
            "deployment_catalog_digest": assignment.deployment_catalog_digest,
            "resource_policy_epoch": assignment.resource_policy_epoch,
            "queue_eligibility_digest": assignment.queue_eligibility_digest,
        }
        drift = tuple(
            name for name, value in expected.items() if getattr(stored, name) != value
        )
        if drift:
            raise ExactBindingConflict(
                "assignment/persisted terminal authority drift: " + ", ".join(drift)
            )
        current = PostgresAuthorityProvider(
            self._connection,
            RuntimeScope(
                project_scope=scope.project_scope,
                actor_id=stored.actor_id,
            ),
        ).current_step_binding(
            assignment.run_id,
            assignment.step_id or "",
            now=observed_at,
        )
        require_current_authority(stored, current, now=observed_at)
        if authorization_digest != stored.binding_digest:
            raise ExactBindingConflict(
                "claim authorization differs from current terminal authority"
            )


__all__ = ["PostgresTerminalAuthorityVerifier"]
