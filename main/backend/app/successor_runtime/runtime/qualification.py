"""Authority qualification bindings and fail-closed drift checks."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Literal, NotRequired, TypeVar, TypedDict, Unpack

from functorial_kit import Failure

from pydantic import Field, model_validator

from .assignments import Digest, FrozenContract, canonical_digest

_RUNTIME_CONTRACT_WITNESS = "test:test_runtime_non_start_proof_negative"
_T = TypeVar("_T")


def _qualification_failure(
    code: str, message: object, *, site: str, exception_type: type[Exception] = ValueError
) -> Failure:
    from .failure_policy import runtime_failure

    return runtime_failure(
        code,
        message,
        exception_type,
        site=site,
        context={"owner": "successor_runtime.runtime.qualification", "operation": site},
    )


def raise_qualification_failure(
    failure: Failure, exception_type: type[Exception] = ValueError
) -> None:
    from .failure_policy import raise_runtime_failure

    raise_runtime_failure(failure, exception_type)


def _public_exception_type(exc: Exception) -> type[Exception]:
    candidate = type(exc)
    try:
        candidate(str(exc))
    except Exception:
        return ValueError
    return candidate


def _try_qualification(
    call: Callable[[], _T],
    *,
    site: str,
    code: str = "QUALIFICATION_INVALID",
) -> _T | Failure:
    try:
        return call()
    except (TypeError, ValueError, OverflowError, KeyError, AttributeError) as exc:
        return _qualification_failure(code, str(exc), site=site, exception_type=_public_exception_type(exc))


class AuthoritySourceBinding(FrozenContract):
    source_kind: Literal[
        "PROJECT_SCOPE", "GRANT", "APPROVAL", "CAPABILITY_AUTHORITY", "CREDENTIAL_REF"
    ]
    source_ref: str = Field(min_length=1)
    source_digest: str = Field(min_length=1)
    source_epoch: int = Field(ge=0)


class AuthorityContextContent(TypedDict):
    actor_id: str
    project_key: str
    resolved_schema: str
    project_registry_revision: int
    project_scope_digest: str
    authority_source_bindings: tuple[AuthoritySourceBinding, ...]
    grants_digest: str
    grant_epoch: int
    expires_at: datetime
    operation_scope_digest: str
    resource_ceiling_digest: str
    canonical_base_revision: int
    canonical_incarnation: str
    approval_refs: NotRequired[tuple[str, ...]]


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
            # kit:boundary owner=successor.runtime.qualification.authority_context class=PROGRAMMER_DEFECT failure_family=none witness=test:test_runtime_non_start_proof_negative
            raise ValueError("context_digest does not bind exact authority context")
        return self

    @classmethod
    def from_content(
        cls, **content: Unpack[AuthorityContextContent]
    ) -> "AuthorityContext":
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
            # kit:boundary owner=successor.runtime.qualification.step_binding class=PROGRAMMER_DEFECT failure_family=none witness=test:test_runtime_non_start_proof_negative
            raise ValueError("binding_digest does not bind exact step authorization")
        return self

    @classmethod
    def from_content(
        cls, **content: Unpack[StepAuthorizationBindingContent]
    ) -> "StepAuthorizationBinding":
        provisional = cls.model_construct(**content, binding_digest="0" * 64)
        return cls(
            **content,
            binding_digest=canonical_digest(
                provisional, exclude_fields={"binding_digest"}
            ),
        )


class StepAuthorizationBindingContent(TypedDict):
    run_id: str
    step_id: str
    operation_kind: str
    operation_contract_digest: str
    capability_id: str
    claim_owner: Literal["legacy", "successor"]
    claim_authority_epoch: int
    claim_policy_digest: str
    payload_digest: str
    actor_id: str
    project_key: str
    project_registry_revision: int
    project_scope_digest: str
    interpreter_binding_digest: str
    deployment_catalog_digest: str
    authority_source_bindings: tuple[AuthoritySourceBinding, ...]
    grants_digest: str
    approval_refs: NotRequired[tuple[str, ...]]
    resource_ceiling_digest: str
    resource_policy_epoch: int
    queue_eligibility_digest: str
    grant_epoch: int
    expires_at: datetime
    canonical_base_revision: int
    canonical_incarnation: str

class QualificationFailure(FrozenContract):
    step_id: str = Field(min_length=1)
    reason_code: str = Field(min_length=1)
    failure_ref: str | None = None
    failure_digest: Digest

    @model_validator(mode="after")
    def validate_failure_digest(self) -> "QualificationFailure":
        expected = canonical_digest(self, exclude_fields={"failure_digest"})
        if self.failure_digest != expected:
            # kit:boundary owner=successor.runtime.qualification.failure class=PROGRAMMER_DEFECT failure_family=none witness=test:test_runtime_non_start_proof_negative
            raise ValueError("failure_digest does not bind qualification failure")
        return self

    @classmethod
    def from_content(
        cls, **content: Unpack[QualificationFailureContent]
    ) -> "QualificationFailure":
        provisional = cls.model_construct(**content, failure_digest="0" * 64)
        return cls(
            **content,
            failure_digest=canonical_digest(
                provisional, exclude_fields={"failure_digest"}
            ),
        )


class QualificationFailureContent(TypedDict):
    step_id: str
    reason_code: str
    failure_ref: NotRequired[str | None]

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
            # kit:boundary owner=successor.runtime.qualification.plan class=PROGRAMMER_DEFECT failure_family=none witness=test:test_runtime_non_start_proof_negative
            raise ValueError("QualifiedPlan step bindings must be unique")
        awaiting = set(self.awaiting_approval_steps)
        denied = {failure.step_id for failure in self.denied_steps}
        if len(awaiting) != len(self.awaiting_approval_steps):
            # kit:boundary owner=successor.runtime.qualification.plan class=PROGRAMMER_DEFECT failure_family=none witness=test:test_runtime_non_start_proof_negative
            raise ValueError("QualifiedPlan awaiting steps must be unique")
        if awaiting & denied:
            # kit:boundary owner=successor.runtime.qualification.plan class=PROGRAMMER_DEFECT failure_family=none witness=test:test_runtime_non_start_proof_negative
            raise ValueError("QualifiedPlan step cannot be awaiting and denied")
        expected = canonical_digest(self, exclude_fields={"qualification_digest"})
        if self.qualification_digest != expected:
            # kit:boundary owner=successor.runtime.qualification.plan class=PROGRAMMER_DEFECT failure_family=none witness=test:test_runtime_non_start_proof_negative
            raise ValueError("qualification_digest does not bind QualifiedPlan")
        return self

    @classmethod
    def from_content(cls, **content: Unpack[QualifiedPlanContent]) -> "QualifiedPlan":
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


class QualifiedPlanContent(TypedDict):
    plan_digest: Digest
    authority_context_digest: Digest
    step_bindings: tuple[StepAuthorizationBinding, ...]
    awaiting_approval_steps: NotRequired[tuple[str, ...]]
    denied_steps: NotRequired[tuple[QualificationFailure, ...]]

class AuthorityDrift(ValueError):
    pass


def _require_current_authority_impl(
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
        raise_qualification_failure(
            _qualification_failure(
                "AUTHORITY_DRIFT",
                f"authority drift: {', '.join(drift)}",
                site="qualification.authority_check",
                exception_type=AuthorityDrift,
            ),
            AuthorityDrift,
        )
    if current.expires_at <= now:
        raise_qualification_failure(
            _qualification_failure(
                "AUTHORITY_EXPIRED",
                "authority binding expired",
                site="qualification.authority_check",
                exception_type=AuthorityDrift,
            ),
            AuthorityDrift,
        )


def try_require_current_authority(
    expected: StepAuthorizationBinding,
    current: StepAuthorizationBinding,
    *,
    now: datetime | None = None,
) -> None | Failure:
    try:
        _require_current_authority_impl(expected, current, now=now)
    except AuthorityDrift as exc:
        code = "AUTHORITY_EXPIRED" if "expired" in str(exc).lower() else "AUTHORITY_DRIFT"
        return _qualification_failure(code, str(exc), site="qualification.require_current_authority", exception_type=AuthorityDrift)
    except (TypeError, ValueError, AttributeError) as exc:
        return _qualification_failure("QUALIFICATION_INVALID", str(exc), site="qualification.require_current_authority", exception_type=type(exc))
    return None


def require_current_authority(
    expected: StepAuthorizationBinding,
    current: StepAuthorizationBinding,
    *,
    now: datetime | None = None,
) -> None:
    result = try_require_current_authority(expected, current, now=now)
    if isinstance(result, Failure):
        from .failure_policy import raise_runtime_failure

        raise_runtime_failure(result, AuthorityDrift if result.code.startswith("AUTHORITY_") else ValueError)


def try_authority_context_from_content(
    **content: Unpack[AuthorityContextContent],
) -> AuthorityContext | Failure:
    return _try_qualification(
        lambda: AuthorityContext.from_content(**content),
        site="qualification.authority_context",
    )


def try_step_authorization_binding_from_content(
    **content: Unpack[StepAuthorizationBindingContent],
) -> StepAuthorizationBinding | Failure:
    return _try_qualification(
        lambda: StepAuthorizationBinding.from_content(**content),
        site="qualification.step_authorization_binding",
    )


def try_qualification_failure_from_content(
    **content: Unpack[QualificationFailureContent],
) -> QualificationFailure | Failure:
    return _try_qualification(
        lambda: QualificationFailure.from_content(**content),
        site="qualification.failure",
    )


def try_qualified_plan_from_content(
    **content: Unpack[QualifiedPlanContent],
) -> QualifiedPlan | Failure:
    return _try_qualification(
        lambda: QualifiedPlan.from_content(**content),
        site="qualification.qualified_plan",
    )


__all__ = [
    "AuthorityContext",
    "AuthorityContextContent",
    "AuthorityDrift",
    "AuthoritySourceBinding",
    "QualificationFailure",
    "QualificationFailureContent",
    "QualifiedPlan",
    "QualifiedPlanContent",
    "StepAuthorizationBinding",
    "StepAuthorizationBindingContent",
    "require_current_authority",
    "try_require_current_authority",
    "try_authority_context_from_content",
    "try_step_authorization_binding_from_content",
    "try_qualification_failure_from_content",
    "try_qualified_plan_from_content",
    "raise_qualification_failure",
]
