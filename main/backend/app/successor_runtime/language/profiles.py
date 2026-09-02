"""Canonical versioned profile contract types for the successor language.\n\nCapability packages publish profile instances; the language owns the one shared\nPython contract identity and canonical codec.\n"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.successor_runtime.language.object_contracts import OperationContractRef
from app.successor_runtime.research.codec import (
    dataclass_to_json,
    is_sha256_hex,
    sha256_hex,
)


def require_hex64(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not is_sha256_hex(value):
        raise ValueError(f"{field_name} must be a 64-char lowercase hex digest")
    return value


def content_digest(value, *, omit_fields: tuple[str, ...] = ()) -> str:
    if hasattr(value, "__dataclass_fields__"):
        return sha256_hex(dataclass_to_json(value, omit_fields))
    if isinstance(value, dict) and omit_fields:
        value = {key: item for key, item in value.items() if key not in omit_fields}
    return sha256_hex(value)

PROFILE_FAMILIES: tuple[str, ...] = (
    "SemanticProfile",
    "EffectProfile",
    "ResourceProfile",
    "FailureProfile",
    "AuthorityProfile",
    "InterpreterProfile",
)


@dataclass(frozen=True, slots=True)
class ContractProfileRef:
    profile_id: str
    profile_version: str
    profile_digest: str

    def __post_init__(self) -> None:
        require_hex64(self.profile_digest, "ContractProfileRef.profile_digest")

    def to_ref_string(self) -> str:
        return f"{self.profile_id}@{self.profile_version}"


class _ProfileRefMixin:
    @property
    def ref(self) -> ContractProfileRef:
        return ContractProfileRef(
            profile_id=self.profile_id,
            profile_version=self.profile_version,
            profile_digest=self.profile_digest,
        )


@dataclass(frozen=True, slots=True)
class SemanticProfile(_ProfileRefMixin):
    semantic_profile_id: str
    semantic_profile_version: str
    reads: tuple[str, ...]
    creates: tuple[str, ...]
    creates_relations: tuple[str, ...]
    declared_loss: tuple[str, ...]
    observation_profile_ref: str
    profile_digest: str

    @property
    def profile_id(self) -> str:
        return self.semantic_profile_id

    @property
    def profile_version(self) -> str:
        return self.semantic_profile_version

    @property
    def allowed_read_object_refs(self) -> tuple[str, ...]:
        return self.reads

    @property
    def allowed_write_object_refs(self) -> tuple[str, ...]:
        return self.creates

    @property
    def allowed_relation_refs(self) -> tuple[str, ...]:
        return self.creates_relations

    @property
    def declared_loss_profile_refs(self) -> tuple[str, ...]:
        return self.declared_loss

    def __post_init__(self) -> None:
        recomputed = content_digest(self, omit_fields=("profile_digest",))
        if recomputed != self.profile_digest:
            raise ValueError("SemanticProfile.profile_digest does not match content")


@dataclass(frozen=True, slots=True)
class EffectProfile(_ProfileRefMixin):
    effect_profile_id: str
    effect_profile_version: str
    execution_class: Literal["PURE_TRANSFORM", "EFFECTFUL", "ADMISSION", "PROJECTION"]
    external_visibility: Literal["NONE", "INTERNAL_ONLY", "EXTERNAL"]
    network_required: bool
    irreversible: bool
    cancellation_points: tuple[str, ...]
    internal_export_only: bool
    human_approval_required: bool
    external_acquisition: bool
    idempotency_profile_ref: str
    profile_digest: str

    @property
    def profile_id(self) -> str:
        return self.effect_profile_id

    @property
    def profile_version(self) -> str:
        return self.effect_profile_version

    def __post_init__(self) -> None:
        recomputed = content_digest(self, omit_fields=("profile_digest",))
        if recomputed != self.profile_digest:
            raise ValueError("EffectProfile.profile_digest does not match content")
        if self.network_required and self.external_visibility == "NONE":
            raise ValueError("network_required is incompatible with external_visibility=NONE")
        if self.external_acquisition:
            raise ValueError("P0-A first specimen forbids external acquisition")
        if self.external_visibility == "EXTERNAL" and not self.internal_export_only:
            raise ValueError("P0-A first specimen allows internal export only")
        if self.human_approval_required and not self.irreversible:
            raise ValueError("human_approval_required implies an irreversible effect boundary")


@dataclass(frozen=True, slots=True)
class ResourceProfile(_ProfileRefMixin):
    resource_profile_id: str
    resource_profile_version: str
    resource_classes: tuple[str, ...]
    concurrency_key: str
    budget_units: str
    default_soft_limit_seconds: int
    default_hard_limit_seconds: int
    node_profile_selector: str
    budget_ref: str
    deadline_policy_ref: str
    node_profile_requirements: tuple[str, ...]
    units: int
    profile_digest: str

    @property
    def profile_id(self) -> str:
        return self.resource_profile_id

    @property
    def profile_version(self) -> str:
        return self.resource_profile_version

    def __post_init__(self) -> None:
        recomputed = content_digest(self, omit_fields=("profile_digest",))
        if recomputed != self.profile_digest:
            raise ValueError("ResourceProfile.profile_digest does not match content")
        if self.default_hard_limit_seconds > 1800:
            raise ValueError("maximum operation hard limit is 1800s")


@dataclass(frozen=True, slots=True)
class FailureProfile(_ProfileRefMixin):
    failure_profile_id: str
    failure_profile_version: str
    typed_failures: tuple[str, ...]
    retryable: bool
    degraded_acceptable: bool
    unknown_outcome_supported: bool
    readback_or_compensation: str
    failure_union_ref: str
    retryable_failure_kinds: tuple[str, ...]
    readback_profile_ref: str | None
    compensation_profile_ref: str | None
    profile_digest: str

    @property
    def profile_id(self) -> str:
        return self.failure_profile_id

    @property
    def profile_version(self) -> str:
        return self.failure_profile_version

    def __post_init__(self) -> None:
        recomputed = content_digest(self, omit_fields=("profile_digest",))
        if recomputed != self.profile_digest:
            raise ValueError("FailureProfile.profile_digest does not match content")


@dataclass(frozen=True, slots=True)
class AuthorityProfile(_ProfileRefMixin):
    authority_profile_id: str
    authority_profile_version: str
    grant_scopes: tuple[str, ...]
    approval_required: bool
    approval_kinds: tuple[str, ...]
    credential_refs: tuple[str, ...]
    canonical_owner: str
    revalidation_points: tuple[str, ...]
    authority_epoch: int
    profile_digest: str

    @property
    def profile_id(self) -> str:
        return self.authority_profile_id

    @property
    def profile_version(self) -> str:
        return self.authority_profile_version

    def __post_init__(self) -> None:
        recomputed = content_digest(self, omit_fields=("profile_digest",))
        if recomputed != self.profile_digest:
            raise ValueError("AuthorityProfile.profile_digest does not match content")


@dataclass(frozen=True, slots=True)
class InterpreterProfile(_ProfileRefMixin):
    interpreter_profile_id: str
    interpreter_profile_version: str
    supported_contract_kinds: tuple[str, ...]
    supported_contract_refs: tuple[OperationContractRef, ...]
    dependency_digest: str
    security_profile_ref: str
    resource_profile_ref: str
    credential_requirements_ref: str | None
    cancellation_profile_ref: str
    idempotency_profile_ref: str
    authoritative_readback_profile_ref: str | None
    receipt_codec_ref: str
    profile_digest: str

    @property
    def profile_id(self) -> str:
        return self.interpreter_profile_id

    @property
    def profile_version(self) -> str:
        return self.interpreter_profile_version

    @property
    def interpreter_id(self) -> str:
        return self.interpreter_profile_id

    @property
    def interpreter_version(self) -> str:
        return self.interpreter_profile_version

    def __post_init__(self) -> None:
        require_hex64(self.dependency_digest, "InterpreterProfile.dependency_digest")
        recomputed = content_digest(self, omit_fields=("profile_digest",))
        if recomputed != self.profile_digest:
            raise ValueError("InterpreterProfile.profile_digest does not match content")


@dataclass(frozen=True, slots=True)
class ObservationProfile(_ProfileRefMixin):
    observation_profile_id: str
    observation_profile_version: str
    dimensions: tuple[str, ...]
    compatible_with_legacy: bool
    observation_schema_ref: str
    profile_digest: str

    @property
    def profile_id(self) -> str:
        return self.observation_profile_id

    @property
    def profile_version(self) -> str:
        return self.observation_profile_version

    def __post_init__(self) -> None:
        recomputed = content_digest(self, omit_fields=("profile_digest",))
        if recomputed != self.profile_digest:
            raise ValueError("ObservationProfile.profile_digest does not match content")
