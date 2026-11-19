"""Core typed identities and operation contracts for the successor language.

This module follows the frozen runtime architecture contract (06 sections 4.1
and 8.2).  It intentionally has no runtime, facility or legacy imports.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Annotated, Any, Literal, NoReturn, Protocol, TypeAlias, TypeGuard, runtime_checkable
from collections.abc import Mapping, Sequence

from functorial_kit import Failure

from app.successor_runtime.research.object_types import ObjectType

from .catalog import OperationContractCatalogSnapshot
from .object_contracts import (
    OperationContract,
    OperationContractRef,
    ReturnContract,
    language_failure,
    raise_language_failure,
)

FrozenJsonAtom: TypeAlias = None | bool | int | float | str
FrozenJsonValue: TypeAlias = (
    "FrozenJsonAtom | tuple[FrozenJsonValue, ...] | frozenset[str]"
)
FrozenJsonObject: TypeAlias = "tuple[tuple[str, FrozenJsonValue], ...]"


def _is_sequence(value: object) -> TypeGuard[Sequence[object]]:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _is_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _is_set(value: object) -> TypeGuard[frozenset[object] | set[object]]:
    return isinstance(value, (frozenset, set))


def _mapping_items(value: Mapping[object, object]) -> "list[tuple[object, object]]":
    return [(key, item) for key, item in value.items()]


class _TaggedDataclass(Protocol):
    __dataclass_fields__: Mapping[str, object]


def _is_tagged_dataclass(value: object) -> TypeGuard[_TaggedDataclass]:
    return hasattr(value, "__dataclass_fields__")


@dataclass(frozen=True, slots=True)
class AlgebraRef:
    algebra_id: str
    algebra_version: str


def default_return_contract() -> ReturnContract:
    return ReturnContract(
        success_modes=("SUCCEEDED",),
        failure_modes=("FAILED",),
        admission_required=False,
        wait_modes=("WAIT",),
        cancel_modes=("CANCELED",),
    )


@dataclass(frozen=True, slots=True)
class EffectSpec:
    execution_class: Literal["PURE_TRANSFORM", "EFFECTFUL", "ADMISSION", "PROJECTION"]
    external_visibility: bool
    irreversible: bool
    cancellation_points: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CredentialRef:
    provider: str
    project_key: str
    secret_name: str
    required_scope: str
    credential_epoch: int


@dataclass(frozen=True, slots=True)
class ValueRef:
    value_id: str
    project_key: str
    object_type: ObjectType
    codec_id: str
    content_digest: str
    storage_kind: Literal[
        "project_value_ref", "runtime_blob_ref", "artifact_ref", "canonical_ref"
    ]
    store_id: str
    store_version: str
    storage_ref: str
    byte_size: int
    provenance_digest: str

    def to_plain(self) -> "dict[str, Any]":
        return {
            "value_id": self.value_id,
            "project_key": self.project_key,
            "object_type": {
                "type_id": self.object_type.type_id,
                "schema_version": self.object_type.schema_version,
                "codec_id": self.object_type.codec_id,
                "canonical_codec_version": self.object_type.canonical_codec_version,
            },
            "codec_id": self.codec_id,
            "content_digest": self.content_digest,
            "storage_kind": self.storage_kind,
            "store_id": self.store_id,
            "store_version": self.store_version,
            "storage_ref": self.storage_ref,
            "byte_size": self.byte_size,
            "provenance_digest": self.provenance_digest,
        }


@dataclass(frozen=True, slots=True)
class OperationSpec:
    operation_id: str
    contract_ref: OperationContractRef
    input_refs: "tuple[ValueRef, ...]"
    payload_ref: ValueRef
    allowed_overrides: FrozenJsonObject


_INVALID_JSON = object()
_TAG_MAP: "dict[type[Any], str]" = {
    ValueRef: "value_ref",
    OperationContractRef: "operation_contract_ref",
    AlgebraRef: "algebra_ref",
    CredentialRef: "credential_ref",
    OperationContract: "operation_contract",
    ReturnContract: "return_contract",
    EffectSpec: "effect_spec",
}


class _FrozenJsonObjectMarker(tuple[tuple[str, FrozenJsonValue], ...]):
    pass


def _freeze_json_value(value: object) -> FrozenJsonValue:
    if isinstance(value, _FrozenJsonObjectMarker):
        return value
    if value is None or isinstance(value, (bool, int, float, str)):
        if isinstance(value, float) and not math.isfinite(value):
            # kit:boundary owner=successor.language.algebra.domain class=PROGRAMMER_DEFECT failure_family=none witness=test:test_atom_node_rejects_malformed_object_types_as_typed_failure
            raise ValueError("non-finite float is not a frozen JSON value")
        return value
    if _is_mapping(value):
        return _FrozenJsonObjectMarker(
            (str(key_object), _freeze_json_value(item_object))
            for key_object, item_object in sorted(
                _mapping_items(value), key=lambda pair: str(pair[0])
            )
        )
    if _is_sequence(value):
        return tuple(_freeze_json_value(item) for item in value)
    if _is_set(value):
        items = [item for item in value]
        if not all(isinstance(item, str) for item in items):
            # kit:boundary owner=successor.language.algebra.domain class=PROGRAMMER_DEFECT failure_family=none witness=test:test_atom_node_rejects_malformed_object_types_as_typed_failure
            raise ValueError("frozenset members must be strings")
        return frozenset(item for item in items if isinstance(item, str))
    # kit:boundary owner=successor.language.algebra.domain class=PROGRAMMER_DEFECT failure_family=none witness=test:test_atom_node_rejects_malformed_object_types_as_typed_failure
    raise TypeError(f"unsupported JSON value type: {type(value)!r}")

def _failure_argument(error: Exception) -> object:
    return error.args[0] if len(error.args) == 1 else str(error)


def _lift_algebra_failure(failure: Failure) -> NoReturn:
    exception_name = str((failure.context or {}).get("public_exception") or "")
    exception_type = {"ValueError": ValueError, "TypeError": TypeError}.get(
        exception_name
    )
    if exception_type is None:
        raise_language_failure(failure, ValueError)
    raise_language_failure(failure, exception_type)


def try_freeze_json_value(value: Any) -> FrozenJsonValue | Failure:
    try:
        return _freeze_json_value(value)
    except (TypeError, ValueError) as error:
        code = "CANONICAL_VALUE_INVALID"
        return language_failure(
            code,
            _failure_argument(error),
            type(error),
            site="language.algebra.freeze_json_value",
        )


def freeze_json_value(value: Any) -> FrozenJsonValue:
    outcome = try_freeze_json_value(value)
    if isinstance(outcome, Failure):
        _lift_algebra_failure(outcome)
    return outcome


def freeze_json_object(value: "dict[str, Any]") -> FrozenJsonObject:
    outcome = try_freeze_json_object(value)
    if isinstance(outcome, Failure):
        _lift_algebra_failure(outcome)
    return outcome


def try_freeze_json_object(value: object) -> FrozenJsonObject | Failure:
    if not _is_mapping(value) or not isinstance(value, dict):
        return language_failure(
            "CANONICAL_VALUE_INVALID",
            "expected a JSON object value",
            TypeError,
            site="language.algebra.freeze_json_object.input",
        )
    try:
        result = _freeze_json_value(value)
        if not is_frozen_json_object(result):
            return language_failure(
                "CANONICAL_VALUE_INVALID",
                "expected a JSON object value",
                TypeError,
                site="language.algebra.freeze_json_object.value",
            )
        return result
    except (TypeError, ValueError) as error:
        return language_failure(
            "CANONICAL_VALUE_INVALID",
            _failure_argument(error),
            type(error),
            site="language.algebra.freeze_json_object.value",
        )


def is_frozen_json_object(value: object) -> TypeGuard[_FrozenJsonObjectMarker]:
    return isinstance(value, _FrozenJsonObjectMarker)


def thaw_json_value(value: object) -> object:
    """Restore declared JSON object/array shapes from a frozen Program value."""
    if is_frozen_json_object(value):
        return {key: thaw_json_value(item) for key, item in value}
    if _is_mapping(value):
        return {str(key): thaw_json_value(item) for key, item in value.items()}
    if _is_set(value):
        return [thaw_json_value(item) for item in sorted(value, key=str)]
    if _is_sequence(value):
        return [thaw_json_value(item) for item in value]
    return value


@runtime_checkable
class _PlainEncodable(Protocol):
    def to_plain(self) -> object: ...


def _encode_value(value: object, tag_map: "dict[type[object], str]") -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        if isinstance(value, float) and not math.isfinite(value):
            # kit:boundary owner=successor.language.algebra.domain class=PROGRAMMER_DEFECT failure_family=none witness=test:test_atom_node_rejects_malformed_object_types_as_typed_failure
            raise ValueError("non-finite float cannot be canonically encoded")
        return value
    if _is_set(value):
        encoded_items = [_encode_value(item, tag_map) for item in value]
        return sorted(str(item) for item in encoded_items)
    if isinstance(value, _FrozenJsonObjectMarker):
        return _encode_frozen_object(value, tag_map)
    if _is_sequence(value):
        return ["$array", [_encode_value(item, tag_map) for item in value]]
    if _is_mapping(value):
        encoded: "dict[str, object]" = {}
        for key_object, item in _mapping_items(value):
            encoded[str(key_object)] = _encode_value(item, tag_map)
        return encoded
    if isinstance(value, _PlainEncodable):
        return _encode_value(value.to_plain(), tag_map)
    if isinstance(value, ObjectType):
        return _encode_dataclass_fields(value, tag_map)
    tag = tag_map.get(type(value))
    if tag is not None:
        return {tag: _encode_dataclass_fields(value, tag_map)}
    # kit:boundary owner=successor.language.algebra.domain class=PROGRAMMER_DEFECT failure_family=none witness=test:test_atom_node_rejects_malformed_object_types_as_typed_failure
    raise TypeError(f"cannot canonically encode value of type {type(value)!r}")


def _encode_frozen_object(
    value: "tuple[tuple[str, FrozenJsonValue], ...]",
    tag_map: "dict[type[object], str]",
) -> object:
    encoded: "dict[str, object]" = {}
    for key, item in sorted(value, key=lambda pair: pair[0]):
        encoded[key] = _encode_value(item, tag_map)
    return encoded


def _encode_dataclass_fields(value: object, tag_map: "dict[type[object], str]") -> object:
    if not _is_tagged_dataclass(value):
        # kit:boundary owner=successor.language.algebra.codec class=PROGRAMMER_DEFECT failure_family=none witness=test:test_canonical_encoding_rejects_invalid_tag_registration
        raise TypeError("expected tagged dataclass")
    encoded: "dict[str, object]" = {}
    for field_name in value.__dataclass_fields__:
        encoded[field_name] = _encode_value(getattr(value, field_name), tag_map)
    return encoded

def canonical_json_bytes(value: Any) -> bytes:
    outcome = try_canonical_json_bytes(value)
    if isinstance(outcome, Failure):
        _lift_algebra_failure(outcome)
    return outcome


def try_canonical_json_bytes(value: Any) -> bytes | Failure:
    try:
        encoded = _encode_value(value, _TAG_MAP)
        return json.dumps(
            encoded,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        return language_failure(
            "CANONICAL_VALUE_INVALID",
            _failure_argument(error),
            type(error),
            site="language.algebra.canonical_json_bytes",
        )


def sha256_digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_digest(value: Any) -> str:
    outcome = try_canonical_digest(value)
    if isinstance(outcome, Failure):
        _lift_algebra_failure(outcome)
    return outcome


def try_canonical_digest(value: Any) -> str | Failure:
    encoded = try_canonical_json_bytes(value)
    if isinstance(encoded, Failure):
        return encoded
    return sha256_digest_bytes(encoded)


def build_catalog_snapshot(
    catalog_id: str,
    catalog_version: str,
    contracts: "tuple[OperationContract, ...]",
) -> Annotated[OperationContractCatalogSnapshot, "kit:non-authoritative derived_as=view fact_source=successor_runtime.language.object_contracts.OperationContract witness=test:test_workflow_language_projections_do_not_claim_authority"]:
    outcome = try_build_catalog_snapshot(catalog_id, catalog_version, contracts)
    if isinstance(outcome, Failure):
        _lift_algebra_failure(outcome)
    return outcome


def try_build_catalog_snapshot(
    catalog_id: str,
    catalog_version: str,
    contracts: "tuple[OperationContract, ...]",
) -> OperationContractCatalogSnapshot | Failure:
    try:
        entries = tuple(
            (
                contract.ref.kind,
                contract.ref.contract_version,
                contract.ref.contract_digest,
                contract.owner_capability_id,
            )
            for contract in contracts
        )
        return OperationContractCatalogSnapshot(
            catalog_id=catalog_id,
            catalog_version=catalog_version,
            entries=entries,
            catalog_digest=None,
        )
    except (TypeError, ValueError, AttributeError) as error:
        return language_failure(
            "CANONICAL_VALUE_INVALID",
            _failure_argument(error),
            type(error),
            site="language.algebra.build_catalog_snapshot",
        )
