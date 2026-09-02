"""Typed public-control payloads for durable authority grants."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .assignments import Digest, FrozenContract, canonical_digest


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
            raise ValueError("authority operation kinds must be non-empty and unique")
        expected = canonical_digest(
            {
                "schema_version": self.schema_version,
                "operation_kinds": self.operation_kinds,
                "project_scope_digest": self.project_scope_digest,
            }
        )
        if self.scope_digest != expected:
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


__all__ = [
    "AuthorityOperationScope",
    "AuthorityResourceCeiling",
    "AuthorityResourceLimit",
]
