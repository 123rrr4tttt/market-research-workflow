"""Core typed identities and operation contracts for the successor language.

This module follows the frozen runtime architecture contract (06 sections 4.1
and 8.2).  It intentionally has no runtime, facility or legacy imports.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, fields
from typing import Annotated, Any, Literal, Union

from functorial_kit import Failure

from app.successor_runtime.research.object_types import ObjectType

from .catalog import OperationContractCatalogSnapshot
from .object_contracts import (
    OperationContract,
    OperationContractRef,
    ReturnContract,
    _failure as language_failure,
    _raise_failure as raise_language_failure,
)

FrozenJsonAtom = Union[None, bool, int, float, str]
FrozenJsonValue = Union[FrozenJsonAtom, "tuple[FrozenJsonValue, ...]", "frozenset[str]"]
FrozenJsonObject = "tuple[tuple[str, FrozenJsonValue], ...]"


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
            "object_type": self.object_type.to_plain()
            if hasattr(self.object_type, "to_plain")
            else {
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


class _FrozenJsonObjectMarker(tuple):
    pass


def _freeze_json_value(value: Any) -> FrozenJsonValue:
    if value is None or isinstance(value, (bool, int, float, str)):
        if isinstance(value, float) and not math.isfinite(value):
            # kit:boundary owner=successor.language.algebra.domain class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w07_language_a
            raise ValueError("non-finite float is not a frozen JSON value")
        return value
    if isinstance(value, dict):
        return tuple(
            (str(key), _freeze_json_value(item)) for key, item in sorted(value.items())
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json_value(item) for item in value)
    if isinstance(value, frozenset):
        if not all(isinstance(item, str) for item in value):
            # kit:boundary owner=successor.language.algebra.domain class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w07_language_a
            raise ValueError("frozenset members must be strings")
        return value
    if isinstance(value, set):
        if not all(isinstance(item, str) for item in value):
            # kit:boundary owner=successor.language.algebra.domain class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w07_language_a
            raise ValueError("set members must be strings")
        return frozenset(value)
    # kit:boundary owner=successor.language.algebra.domain class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w07_language_a
    raise TypeError(f"unsupported JSON value type: {type(value)!r}")


def _failure_argument(error: Exception) -> object:
    return error.args[0] if len(error.args) == 1 else str(error)


def _lift_algebra_failure(failure: Failure) -> None:
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


def try_freeze_json_object(value: "dict[str, Any]") -> FrozenJsonObject | Failure:
    if not isinstance(value, dict):
        return language_failure(
            "CANONICAL_VALUE_INVALID",
            "expected a JSON object value",
            TypeError,
            site="language.algebra.freeze_json_object.input",
        )
    try:
        return _FrozenJsonObjectMarker(
            (str(key), _freeze_json_value(item)) for key, item in sorted(value.items())
        )  # type: ignore[return-value]
    except (TypeError, ValueError) as error:
        return language_failure(
            "CANONICAL_VALUE_INVALID",
            _failure_argument(error),
            type(error),
            site="language.algebra.freeze_json_object.value",
        )


def _encode_value(value: Any, tag_map: "dict[type[Any], str]") -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        if isinstance(value, float) and not math.isfinite(value):
            # kit:boundary owner=successor.language.algebra.domain class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w07_language_a
            raise ValueError("non-finite float cannot be canonically encoded")
        return value
    if isinstance(value, frozenset):
        return sorted(_encode_value(item, tag_map) for item in value)
    if isinstance(value, _FrozenJsonObjectMarker):
        return _encode_frozen_object(value, tag_map)
    if isinstance(value, tuple):
        return ["$array", [_encode_value(item, tag_map) for item in value]]
    if isinstance(value, dict):
        return {
            str(key): _encode_value(item, tag_map) for key, item in sorted(value.items())
        }
    if isinstance(value, list):
        return ["$array", [_encode_value(item, tag_map) for item in value]]
    if hasattr(value, "to_plain"):
        return _encode_value(value.to_plain(), tag_map)
    if isinstance(value, ObjectType):
        return _encode_dataclass_fields(value, tag_map)
    tag = tag_map.get(type(value))
    if tag is not None:
        return {tag: _encode_dataclass_fields(value, tag_map)}
    if isinstance(value, tuple) and value and all(
        isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str)
        for item in value
    ):
        return _encode_frozen_object(value, tag_map)
    # kit:boundary owner=successor.language.algebra.domain class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w07_language_a
    raise TypeError(f"cannot canonically encode value of type {type(value)!r}")


def _encode_frozen_object(value: Any, tag_map: "dict[type[Any], str]") -> Any:
    return {
        str(key): _encode_value(item, tag_map)
        for key, item in sorted(value, key=lambda pair: pair[0])
    }


def _encode_dataclass_fields(value: Any, tag_map: "dict[type[Any], str]") -> Any:
    return {
        field.name: _encode_value(getattr(value, field.name), tag_map)
        for field in fields(value)
    }


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
) -> Annotated[OperationContractCatalogSnapshot, "kit:non-authoritative derived_as=view fact_source=successor_runtime.language.object_contracts.OperationContract witness=test:test_w07_derived_metadata_is_exact_and_non_authoritative"]:
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
