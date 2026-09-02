"""Authority qualification bindings and fail-closed drift checks."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import Field, model_validator

from .assignments import Digest, FrozenContract, canonical_digest


class AuthoritySourceBinding(FrozenContract):
    source_kind: Literal[
        "PROJECT_SCOPE", "GRANT", "APPROVAL", "CAPABILITY_AUTHORITY", "CREDENTIAL_REF"
    ]
    source_ref: str = Field(min_length=1)
    source_digest: str = Field(min_length=1)
    source_epoch: int = Field(ge=0)


class AuthorityContext(FrozenContract):
    actor_id: str = Field(min_length=1)
    project_key: str = Field(min_length=1)
    resolved_schema: str = Field(min_length=1)
    project_registry_revision: int = Field(ge=0)
    project_scope_digest: str = Field(min_length=1)
    authority_source_bindings: tuple[AuthoritySourceBinding, ...]
    grants_digest: str = Field(min_length=1)
    grant_epoch: int = Field(ge=0)
    expires_at: datetime
    operation_scope_digest: str = Field(min_length=1)
    resource_ceiling_digest: str = Field(min_length=1)
    canonical_base_revision: int = Field(ge=0)
    canonical_incarnation: str = Field(min_length=1)
    approval_refs: tuple[str, ...] = ()
    context_digest: Digest

    @model_validator(mode="after")
    def validate_context_digest(self) -> "AuthorityContext":
        expected = canonical_digest(self, exclude_fields={"context_digest"})
        if self.context_digest != expected:
            raise ValueError("context_digest does not bind exact authority context")
        return self

    @classmethod
    def from_content(cls, **content: object) -> "AuthorityContext":
        provisional = cls.model_construct(**content, context_digest="0" * 64)
        return cls(
            **content,
            context_digest=canonical_digest(
                provisional, exclude_fields={"context_digest"}
            ),
        )


class StepAuthorizationBinding(FrozenContract):
    run_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    operation_kind: str = Field(min_length=1)
    operation_contract_digest: str = Field(min_length=1)
    capability_id: str = Field(min_length=1)
    claim_owner: Literal["legacy", "successor"]
    claim_authority_epoch: int = Field(ge=0)
    claim_policy_digest: str = Field(min_length=1)
    payload_digest: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    project_key: str = Field(min_length=1)
    project_registry_revision: int = Field(ge=0)
    project_scope_digest: str = Field(min_length=1)
    interpreter_binding_digest: str = Field(min_length=1)
    deployment_catalog_digest: str = Field(min_length=1)
    authority_source_bindings: tuple[AuthoritySourceBinding, ...]
    grants_digest: str = Field(min_length=1)
    approval_refs: tuple[str, ...] = ()
    resource_ceiling_digest: str = Field(min_length=1)
    resource_policy_epoch: int = Field(ge=0)
    queue_eligibility_digest: str = Field(min_length=1)
    grant_epoch: int = Field(ge=0)
    expires_at: datetime
    canonical_base_revision: int = Field(ge=0)
    canonical_incarnation: str = Field(min_length=1)
    binding_digest: Digest

    @model_validator(mode="after")
    def validate_binding_digest(self) -> "StepAuthorizationBinding":
        expected = canonical_digest(self, exclude_fields={"binding_digest"})
        if self.binding_digest != expected:
            raise ValueError("binding_digest does not bind exact step authorization")
        return self

    @classmethod
    def from_content(cls, **content: object) -> "StepAuthorizationBinding":
        provisional = cls.model_construct(**content, binding_digest="0" * 64)
        return cls(
            **content,
            binding_digest=canonical_digest(
                provisional, exclude_fields={"binding_digest"}
            ),
        )


class QualificationFailure(FrozenContract):
    step_id: str = Field(min_length=1)
    reason_code: str = Field(min_length=1)
    failure_ref: str | None = None
    failure_digest: Digest

    @model_validator(mode="after")
    def validate_failure_digest(self) -> "QualificationFailure":
        expected = canonical_digest(self, exclude_fields={"failure_digest"})
        if self.failure_digest != expected:
            raise ValueError("failure_digest does not bind qualification failure")
        return self

    @classmethod
    def from_content(cls, **content: object) -> "QualificationFailure":
        provisional = cls.model_construct(**content, failure_digest="0" * 64)
        return cls(
            **content,
            failure_digest=canonical_digest(
                provisional, exclude_fields={"failure_digest"}
            ),
        )


class QualifiedPlan(FrozenContract):
    plan_digest: Digest
    authority_context_digest: Digest
    step_bindings: tuple[StepAuthorizationBinding, ...]
    awaiting_approval_steps: tuple[str, ...] = ()
    denied_steps: tuple[QualificationFailure, ...] = ()
    qualification_digest: Digest

    @model_validator(mode="after")
    def validate_qualified_plan(self) -> "QualifiedPlan":
        step_ids = [binding.step_id for binding in self.step_bindings]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("QualifiedPlan step bindings must be unique")
        awaiting = set(self.awaiting_approval_steps)
        denied = {failure.step_id for failure in self.denied_steps}
        if len(awaiting) != len(self.awaiting_approval_steps):
            raise ValueError("QualifiedPlan awaiting steps must be unique")
        if awaiting & denied:
            raise ValueError("QualifiedPlan step cannot be awaiting and denied")
        expected = canonical_digest(self, exclude_fields={"qualification_digest"})
        if self.qualification_digest != expected:
            raise ValueError("qualification_digest does not bind QualifiedPlan")
        return self

    @classmethod
    def from_content(cls, **content: object) -> "QualifiedPlan":
        provisional = cls.model_construct(
            **content,
            qualification_digest="0" * 64,
        )
        return cls(
            **content,
            qualification_digest=canonical_digest(
                provisional, exclude_fields={"qualification_digest"}
            ),
        )

    def step_binding(self, step_id: str) -> StepAuthorizationBinding | None:
        return next(
            (binding for binding in self.step_bindings if binding.step_id == step_id),
            None,
        )


class AuthorityDrift(ValueError):
    pass


def require_current_authority(
    expected: StepAuthorizationBinding,
    current: StepAuthorizationBinding,
    *,
    now: datetime | None = None,
) -> None:
    now = now or datetime.now(timezone.utc)
    identity_fields = (
        "run_id",
        "step_id",
        "operation_contract_digest",
        "capability_id",
        "claim_owner",
        "claim_authority_epoch",
        "claim_policy_digest",
        "payload_digest",
        "actor_id",
        "project_key",
        "project_registry_revision",
        "project_scope_digest",
        "interpreter_binding_digest",
        "deployment_catalog_digest",
        "authority_source_bindings",
        "grants_digest",
        "approval_refs",
        "resource_ceiling_digest",
        "resource_policy_epoch",
        "queue_eligibility_digest",
        "grant_epoch",
        "canonical_base_revision",
        "canonical_incarnation",
        "binding_digest",
    )
    drift = [name for name in identity_fields if getattr(expected, name) != getattr(current, name)]
    if drift:
        raise AuthorityDrift(f"authority drift: {', '.join(drift)}")
    if current.expires_at <= now:
        raise AuthorityDrift("authority binding expired")
