"""Claim and deterministic effect-attempt identity contracts."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from .assignments import (
    Digest,
    FrozenContract,
    RuntimeAssignment,
    canonical_digest,
    require_digest,
)


def derive_attempt_id(
    assignment: RuntimeAssignment,
    *,
    authorization_digest: str,
    handler_realization_digest: str,
) -> str:
    """Bind an attempt to both canonical work and exact realization.

    Lease renewal and transport redelivery retain this identity.  Any change to
    assignment or handler realization produces a different identity and must be
    accompanied by a successor execution epoch in persistent implementations.
    """

    require_digest(authorization_digest, "authorization_digest")
    require_digest(handler_realization_digest, "handler_realization_digest")
    if handler_realization_digest != assignment.handler_binding_digest:
        raise ValueError("handler realization does not match assignment binding")
    parts: tuple[object, ...] = (
        assignment.project_key,
        assignment.run_id,
        assignment.step_id,
        assignment.execution_epoch,
        assignment.incarnation,
        assignment.assignment_digest,
        handler_realization_digest,
        assignment.input_closure_digest,
        authorization_digest,
        assignment.capability_id,
        assignment.claim_authority_epoch,
        assignment.claim_policy_digest,
    )
    return canonical_digest(parts)


class ClaimBinding(FrozenContract):
    work_item_id: str = Field(min_length=1)
    assignment_digest: Digest
    handler_binding_digest: Digest
    handler_realization_digest: Digest
    authorization_digest: Digest
    attempt_id: Digest
    lease_token: str = Field(min_length=1)
    lease_expires_at: datetime
    node_id: str = Field(min_length=1)
    node_profile_digest: Digest
    interpreter_profile_digest: Digest | None = None
    authority_digest: Digest
    execution_reservation_ref: str | None = None
    execution_reservation_digest: Digest | None = None
    claim_authority_epoch: int = Field(ge=0)
    binding_digest: Digest

    @model_validator(mode="after")
    def validate_binding_content(self) -> "ClaimBinding":
        if (self.execution_reservation_ref is None) != (
            self.execution_reservation_digest is None
        ):
            raise ValueError("execution reservation ref and digest are an exact pair")
        if self.handler_binding_digest != self.handler_realization_digest:
            raise ValueError("claim handler realization differs from handler binding")
        expected = canonical_digest(self, exclude_fields={"binding_digest"})
        if self.binding_digest != expected:
            raise ValueError("binding_digest does not match canonical claim content")
        return self

    @classmethod
    def bind(
        cls,
        assignment: RuntimeAssignment,
        *,
        authorization_digest: str,
        lease_token: str,
        lease_expires_at: datetime,
        node_id: str,
        node_profile_digest: str,
        authority_digest: str,
        interpreter_profile_digest: str | None = None,
        execution_reservation_ref: str | None = None,
        execution_reservation_digest: str | None = None,
    ) -> "ClaimBinding":
        realization = assignment.handler_binding_digest
        attempt_id = derive_attempt_id(
            assignment,
            authorization_digest=authorization_digest,
            handler_realization_digest=realization,
        )
        content: dict[str, object] = {
            "work_item_id": assignment.work_item_id,
            "assignment_digest": assignment.assignment_digest,
            "handler_binding_digest": assignment.handler_binding_digest,
            "handler_realization_digest": realization,
            "authorization_digest": authorization_digest,
            "attempt_id": attempt_id,
            "lease_token": lease_token,
            "lease_expires_at": lease_expires_at,
            "node_id": node_id,
            "node_profile_digest": node_profile_digest,
            "interpreter_profile_digest": interpreter_profile_digest,
            "authority_digest": authority_digest,
            "execution_reservation_ref": execution_reservation_ref,
            "execution_reservation_digest": execution_reservation_digest,
            "claim_authority_epoch": assignment.claim_authority_epoch,
        }
        provisional = cls.model_construct(**content, binding_digest="0" * 64)
        return cls(
            **content,
            binding_digest=canonical_digest(
                provisional,
                exclude_fields={"binding_digest"},
            ),
        )

    def validate_against(self, assignment: RuntimeAssignment) -> None:
        if self.work_item_id != assignment.work_item_id:
            raise ClaimBindingMismatch("work item identity drift")
        if self.assignment_digest != assignment.assignment_digest:
            raise ClaimBindingMismatch("assignment content drift")
        if self.handler_binding_digest != assignment.handler_binding_digest:
            raise ClaimBindingMismatch("handler binding drift")
        if self.handler_realization_digest != assignment.handler_binding_digest:
            raise ClaimBindingMismatch("handler realization drift")
        if self.claim_authority_epoch != assignment.claim_authority_epoch:
            raise ClaimBindingMismatch("claim authority epoch drift")
        expected_attempt = derive_attempt_id(
            assignment,
            authorization_digest=self.authorization_digest,
            handler_realization_digest=self.handler_realization_digest,
        )
        if self.attempt_id != expected_attempt:
            raise ClaimBindingMismatch("attempt identity drift")


class ClaimBindingMismatch(ValueError):
    """Fail-closed mismatch between a live claim and its canonical assignment."""
