"""Versioned, immutable input contract for capability-spec pilot compilation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from typing import Any, Literal

SPEC_SCHEMA = "mrw.functorial_successor.capability_cell_spec.v1"
SPEC_VERSION = "1.0.0"
IDENTITY_COMPOSITION_REF = "mrw.successor.composition.identity.v1"


def canonical_json_bytes(value: Any) -> bytes:
    """Encode JSON without representation-dependent whitespace or key order."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def digest_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _non_empty(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")


def _refs(
    values: Sequence[str], label: str, *, allow_empty: bool = False
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
        raise TypeError(f"{label} must be a list or tuple of references")
    result = tuple(values)
    if not allow_empty and not result:
        raise ValueError(f"{label} must not be empty")
    for index, value in enumerate(result):
        _non_empty(value, f"{label}[{index}]")
    return result


def compose_ordered(*parts: Sequence[str]) -> tuple[str, ...]:
    """Compose references in declaration order, with a strict identity unit.

    No sorting, deduplication, interchange, or commutativity is performed.
    """

    return tuple(
        ref for part in parts for ref in part if ref != IDENTITY_COMPOSITION_REF
    )


@dataclass(frozen=True, slots=True)
class ExactFileBinding:
    path: str
    file_sha256: str
    role: str

    def __post_init__(self) -> None:
        _non_empty(self.path, "ExactFileBinding.path")
        _non_empty(self.role, "ExactFileBinding.role")
        parsed = PurePosixPath(self.path)
        if (
            parsed.is_absolute()
            or ".." in parsed.parts
            or self.path != parsed.as_posix()
        ):
            raise ValueError("ExactFileBinding.path must be a normalized relative path")
        if len(self.file_sha256) != 64 or any(
            char not in "0123456789abcdef" for char in self.file_sha256
        ):
            raise ValueError("ExactFileBinding.file_sha256 must be lowercase SHA-256")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ExactFileBinding:
        return cls(
            path=str(value["path"]),
            file_sha256=str(value["file_sha256"]),
            role=str(value["role"]),
        )


@dataclass(frozen=True, slots=True)
class AuthorityCeiling:
    canonical_write: bool = False
    live_provider: bool = False
    external_delivery: bool = False
    cutover: bool = False
    authority_transfer: bool = False

    def __post_init__(self) -> None:
        if not all(isinstance(value, bool) for value in asdict(self).values()):
            raise TypeError("authority ceiling flags must be booleans")
        if any(asdict(self).values()):
            raise ValueError("pilot authority ceiling cannot enable live authority")

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> AuthorityCeiling:
        required = {
            "canonical_write",
            "live_provider",
            "external_delivery",
            "cutover",
            "authority_transfer",
        }
        if set(value) != required:
            raise ValueError(
                "authority_ceiling must contain exactly the five frozen flags"
            )
        return cls(**{key: value[key] for key in required})


@dataclass(frozen=True, slots=True)
class CapabilityCellSpec:
    """Handwritten semantic declaration consumed by the mechanical compiler."""

    cell_id: str
    family_id: str
    owner_capability_id: str
    entrypoint_kind: Literal["PROGRAM", "FACADE_VALIDATION"]
    commutativity_claim: Literal["NOT_CLAIMED"]
    input_contract_refs: tuple[str, ...]
    output_contract_refs: tuple[str, ...]
    object_contract_refs: tuple[str, ...]
    operation_contract_refs: tuple[str, ...]
    program_shape_ref: str
    ordered_composition_refs: tuple[str, ...]
    interpreter_refs: tuple[str, ...]
    profile_refs: tuple[str, ...]
    deployment_binding_refs: tuple[str, ...]
    legacy_oracle_ref: str
    shadow_observation_ref: str
    failure_union_refs: tuple[str, ...]
    declared_lossy_projection_refs: tuple[str, ...]
    effect_policy_ref: str
    resource_policy_ref: str
    recovery_policy_ref: str
    readback_policy_ref: str
    authority_ceiling: AuthorityCeiling
    adoption_prerequisites: tuple[str, ...]
    source_bindings: tuple[ExactFileBinding, ...]
    test_bindings: tuple[ExactFileBinding, ...]
    rollback_bindings: tuple[ExactFileBinding, ...]
    generated_ownership_refs: tuple[str, ...]
    handwritten_ownership_refs: tuple[str, ...]
    schema: str = SPEC_SCHEMA
    version: str = SPEC_VERSION

    def __post_init__(self) -> None:
        for label in (
            "cell_id",
            "family_id",
            "owner_capability_id",
            "program_shape_ref",
            "legacy_oracle_ref",
            "shadow_observation_ref",
            "effect_policy_ref",
            "resource_policy_ref",
            "recovery_policy_ref",
            "readback_policy_ref",
        ):
            _non_empty(getattr(self, label), label)
        if self.schema != SPEC_SCHEMA or self.version != SPEC_VERSION:
            raise ValueError("unsupported CapabilityCellSpec schema/version")
        if self.entrypoint_kind not in {"PROGRAM", "FACADE_VALIDATION"}:
            raise ValueError("entrypoint_kind must be PROGRAM or FACADE_VALIDATION")
        if self.commutativity_claim != "NOT_CLAIMED":
            raise ValueError("capability pilots do not claim commutativity")
        if not isinstance(self.authority_ceiling, AuthorityCeiling):
            raise TypeError("authority_ceiling must be an AuthorityCeiling")
        for label in (
            "input_contract_refs",
            "output_contract_refs",
            "object_contract_refs",
            "operation_contract_refs",
            "ordered_composition_refs",
            "interpreter_refs",
            "profile_refs",
            "deployment_binding_refs",
            "failure_union_refs",
            "adoption_prerequisites",
            "source_bindings",
            "test_bindings",
            "rollback_bindings",
            "generated_ownership_refs",
            "handwritten_ownership_refs",
        ):
            if not getattr(self, label):
                raise ValueError(f"{label} must not be empty")
        for label in (
            "input_contract_refs",
            "output_contract_refs",
            "object_contract_refs",
            "operation_contract_refs",
            "ordered_composition_refs",
            "interpreter_refs",
            "profile_refs",
            "deployment_binding_refs",
            "failure_union_refs",
            "declared_lossy_projection_refs",
            "adoption_prerequisites",
            "generated_ownership_refs",
            "handwritten_ownership_refs",
        ):
            object.__setattr__(
                self,
                label,
                _refs(getattr(self, label), label, allow_empty=True),
            )
        for label in ("source_bindings", "test_bindings", "rollback_bindings"):
            raw_bindings = getattr(self, label)
            if isinstance(raw_bindings, (str, bytes)) or not isinstance(
                raw_bindings, (list, tuple)
            ):
                raise TypeError(f"{label} must be a list or tuple of bindings")
            bindings = tuple(raw_bindings)
            if any(not isinstance(item, ExactFileBinding) for item in bindings):
                raise TypeError(f"{label} must contain ExactFileBinding values")
            object.__setattr__(self, label, bindings)
        normalized = compose_ordered(self.ordered_composition_refs)
        if not normalized:
            raise ValueError("ordered_composition_refs must contain a non-identity ref")
        object.__setattr__(self, "ordered_composition_refs", normalized)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def semantic_payload(self) -> dict[str, Any]:
        """Fields whose change invalidates semantic review.

        Exact source/test/rollback hashes are intentionally excluded.  Their
        byte identity remains mandatory in the artifact digest.
        """

        value = self.to_dict()
        for field in ("source_bindings", "test_bindings", "rollback_bindings"):
            value.pop(field)
        return value

    def semantic_digest(self) -> str:
        return digest_json(self.semantic_payload())

    def exact_bindings(self) -> tuple[ExactFileBinding, ...]:
        return self.source_bindings + self.test_bindings + self.rollback_bindings

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> CapabilityCellSpec:
        tuple_fields = {
            "input_contract_refs",
            "output_contract_refs",
            "object_contract_refs",
            "operation_contract_refs",
            "ordered_composition_refs",
            "interpreter_refs",
            "profile_refs",
            "deployment_binding_refs",
            "failure_union_refs",
            "declared_lossy_projection_refs",
            "adoption_prerequisites",
            "generated_ownership_refs",
            "handwritten_ownership_refs",
        }
        kwargs = dict(value)
        for field in tuple_fields:
            raw = kwargs.get(field)
            if isinstance(raw, (str, bytes)) or not isinstance(raw, (list, tuple)):
                raise TypeError(f"{field} must be a JSON array")
            kwargs[field] = tuple(raw)
        for field in ("source_bindings", "test_bindings", "rollback_bindings"):
            raw_bindings = kwargs.get(field)
            if not isinstance(raw_bindings, list):
                raise TypeError(f"{field} must be a JSON array of objects")
            if any(not isinstance(item, Mapping) for item in raw_bindings):
                raise TypeError(f"{field} must contain only JSON objects")
            kwargs[field] = tuple(
                ExactFileBinding.from_dict(item) for item in raw_bindings
            )
        authority = kwargs.get("authority_ceiling")
        if not isinstance(authority, Mapping):
            raise TypeError("authority_ceiling must be an object")
        kwargs["authority_ceiling"] = AuthorityCeiling.from_dict(authority)
        return cls(**kwargs)
