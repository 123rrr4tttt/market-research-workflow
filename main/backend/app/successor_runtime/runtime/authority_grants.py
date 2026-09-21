"""Typed public-control payloads for durable authority grants."""

from __future__ import annotations

from typing import Any, Callable, Literal, TypeVar

from functorial_kit import Failure

from pydantic import Field, model_validator

from .assignments import Digest, FrozenContract, canonical_digest
from .failure_policy import raise_runtime_failure, runtime_failure

_T = TypeVar("_T")


class AuthorityGrantUnavailable(RuntimeError):
    """Shared non-start signal when no current authority grant exists."""


def _authority_failure(
    message: object,
    *,
    site: str,
    exception_type: type[Exception] = ValueError,
) -> Failure:
    return runtime_failure(
        "AUTHORITY_GRANT_INVALID",
        message,
        exception_type,
        site=site,
        context={"owner": "successor_runtime.runtime.authority_grants", "operation": site},
    )


def _try_authority(call: Callable[[], _T], *, site: str) -> _T | Failure:
    try:
        return call()
    except (TypeError, ValueError, OverflowError, KeyError, AttributeError) as exc:
        return _authority_failure(str(exc), site=site, exception_type=type(exc))


def raise_authority_failure(failure: Failure) -> None:
    name = (failure.context or {}).get("public_exception")
    exception_type = {
        "TypeError": TypeError,
        "ValueError": ValueError,
        "OverflowError": OverflowError,
        "KeyError": KeyError,
        "AttributeError": AttributeError,
    }.get(name, ValueError)
    raise_runtime_failure(failure, exception_type)


class AuthorityOperationScope(FrozenContract):
    schema_version: Literal["mrw.runtime.authority-operation-scope.v1"] = (
        "mrw.runtime.authority-operation-scope.v1"
    )
    operation_kinds: tuple[str, ...]
    project_scope_digest: Digest
    scope_digest: Digest

    @model_validator(mode="after")
    def validate_scope(self) -> "AuthorityOperationScope":
        if not self.operation_kinds or len(self.operation_kinds) != len(
            set(self.operation_kinds)
        ):
            # kit:boundary owner=successor.runtime.validation class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.runtime.failure witness=test:test_w07_runtime_failure_lift_context
            raise ValueError("authority operation kinds must be non-empty and unique")
        expected = canonical_digest(
            {
                "schema_version": self.schema_version,
                "operation_kinds": self.operation_kinds,
                "project_scope_digest": self.project_scope_digest,
            }
        )
        if self.scope_digest != expected:
            # kit:boundary owner=successor.runtime.validation class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.runtime.failure witness=test:test_w07_runtime_failure_lift_context
            raise ValueError("authority operation scope digest drift")
        return self

    @classmethod
    def from_content(
        cls,
        *,
        operation_kinds: tuple[str, ...],
        project_scope_digest: str,
    ) -> "AuthorityOperationScope":
        body = {
            "schema_version": "mrw.runtime.authority-operation-scope.v1",
            "operation_kinds": operation_kinds,
            "project_scope_digest": project_scope_digest,
        }
        return cls(**body, scope_digest=canonical_digest(body))


class AuthorityResourceLimit(FrozenContract):
    resource_class: str = Field(min_length=1)
    units: int = Field(gt=0)


class AuthorityResourceCeiling(FrozenContract):
    schema_version: Literal["mrw.runtime.authority-resource-ceiling.v1"] = (
        "mrw.runtime.authority-resource-ceiling.v1"
    )
    limits: tuple[AuthorityResourceLimit, ...]
    max_active: int = Field(gt=0)
    ceiling_digest: Digest

    @model_validator(mode="after")
    def validate_ceiling(self) -> "AuthorityResourceCeiling":
        classes = tuple(item.resource_class for item in self.limits)
        if not classes or len(classes) != len(set(classes)):
            # kit:boundary owner=successor.runtime.validation class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.runtime.failure witness=test:test_w07_runtime_failure_lift_context
            raise ValueError("authority resource classes must be non-empty and unique")
        expected = canonical_digest(
            {
                "schema_version": self.schema_version,
                "limits": tuple(
                    item.model_dump(mode="json") for item in self.limits
                ),
                "max_active": self.max_active,
            }
        )
        if self.ceiling_digest != expected:
            # kit:boundary owner=successor.runtime.validation class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.runtime.failure witness=test:test_w07_runtime_failure_lift_context
            raise ValueError("authority resource ceiling digest drift")
        return self

    @classmethod
    def from_content(
        cls,
        *,
        limits: tuple[AuthorityResourceLimit, ...],
        max_active: int,
    ) -> "AuthorityResourceCeiling":
        body = {
            "schema_version": "mrw.runtime.authority-resource-ceiling.v1",
            "limits": tuple(item.model_dump(mode="json") for item in limits),
            "max_active": max_active,
        }
        return cls(
            schema_version=body["schema_version"],
            limits=limits,
            max_active=max_active,
            ceiling_digest=canonical_digest(body),
        )


def try_authority_operation_scope(**content: Any) -> AuthorityOperationScope | Failure:
    return _try_authority(
        lambda: AuthorityOperationScope(**content),
        site="authority_grants.operation_scope",
    )


def try_build_authority_operation_scope(**content: Any) -> AuthorityOperationScope | Failure:
    return _try_authority(
        lambda: AuthorityOperationScope.from_content(**content),
        site="authority_grants.build_operation_scope",
    )


def try_authority_resource_ceiling(**content: Any) -> AuthorityResourceCeiling | Failure:
    return _try_authority(
        lambda: AuthorityResourceCeiling(**content),
        site="authority_grants.resource_ceiling",
    )


def try_build_authority_resource_ceiling(**content: Any) -> AuthorityResourceCeiling | Failure:
    return _try_authority(
        lambda: AuthorityResourceCeiling.from_content(**content),
        site="authority_grants.build_resource_ceiling",
    )


__all__ = [
    "AuthorityOperationScope",
    "AuthorityResourceCeiling",
    "AuthorityResourceLimit",
    "raise_authority_failure",
    "try_authority_operation_scope",
    "try_authority_resource_ceiling",
    "try_build_authority_operation_scope",
    "try_build_authority_resource_ceiling",
]
