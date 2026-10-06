"""Versioned canonical codecs for capability payload DTOs."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Generic, TypeGuard, TypeVar

from .checksum import (
    CanonicalJsonArray,
    CanonicalJsonObject,
    CanonicalJsonValue,
    DecodedCanonicalValue,
    content_digest,
    decode_dataclass,
    primitive_failure,
    raise_primitive_failure,
    require_hex64,
)
from .contracts import OperationContractRef

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class PayloadCodec(Generic[T]):
    codec_id: str
    codec_version: str
    contract_ref: OperationContractRef
    payload_type_id: str
    encode: Callable[[T], CanonicalJsonObject]
    decode: Callable[[CanonicalJsonObject], T]
    codec_digest: str

    def __post_init__(self) -> None:
        require_hex64(self.codec_digest, "PayloadCodec.codec_digest")

    def encode_payload(self, value: T) -> CanonicalJsonObject:
        return self.encode(value)

    def decode_payload(self, value: CanonicalJsonObject) -> T:
        return self.decode(value)


def codec_digest(
    codec_id: str,
    codec_version: str,
    contract_ref: OperationContractRef,
    payload_type_id: str,
) -> str:
    return content_digest(
        {
            "codec_id": codec_id,
            "codec_version": codec_version,
            "contract_kind": contract_ref.kind,
            "contract_version": contract_ref.contract_version,
            "payload_type_id": payload_type_id,
        }
    )


def dataclass_codec(
    codec_id: str,
    codec_version: str,
    contract_ref: OperationContractRef,
    payload_type_id: str,
    dto_cls: type[T],
) -> PayloadCodec[T]:
    digest = codec_digest(codec_id, codec_version, contract_ref, payload_type_id)

    def encode(value: T) -> CanonicalJsonObject:
        if not isinstance(value, dto_cls):
            failure = primitive_failure(
                "codec_input_type_invalid",
                f"{codec_id} codec expected {dto_cls.__name__}",
                exception_type=TypeError,
                field_name=f"codec/{codec_id}",
            )
            raise_primitive_failure(failure, TypeError)
        encoded = _canonical_value(value)
        if not isinstance(encoded, dict):
            failure = primitive_failure(
                "codec_input_type_invalid",
                f"{codec_id} codec root must encode as an object",
                exception_type=TypeError,
                field_name=f"codec/{codec_id}",
            )
            raise_primitive_failure(failure, TypeError)
        return encoded

    def decode(value: CanonicalJsonObject) -> T:
        decoded: object = decode_dataclass(
            dto_cls,
            _restore_tuple_fields(dto_cls, value),
        )
        if not isinstance(decoded, dto_cls):
            failure = primitive_failure(
                "codec_input_type_invalid",
                f"{codec_id} decoder returned an invalid payload type",
                exception_type=TypeError,
                field_name=f"codec/{codec_id}",
            )
            raise_primitive_failure(failure, TypeError)
        return decoded

    return PayloadCodec(
        codec_id=codec_id,
        codec_version=codec_version,
        contract_ref=contract_ref,
        payload_type_id=payload_type_id,
        encode=encode,
        decode=decode,
        codec_digest=digest,
    )


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _is_object_sequence(
    value: object,
) -> TypeGuard[list[object] | tuple[object, ...]]:
    return isinstance(value, (list, tuple))


def _canonical_value(value: object) -> CanonicalJsonValue:
    import dataclasses

    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        dataclass_value: object = dataclasses.asdict(value)
        return _canonical_value(dataclass_value)
    if _is_object_mapping(value):
        return {
            str(key): _canonical_value(item)
            for key, item in value.items()
        }
    if _is_object_sequence(value):
        return [_canonical_value(item) for item in value]
    if isinstance(value, bytes):
        return value.hex()
    if value is None or isinstance(value, bool | int | float | str):
        return value
    failure = primitive_failure(
        "codec_input_type_invalid",
        f"canonical codec cannot encode {type(value).__name__}",
        exception_type=TypeError,
        field_name="codec/value",
    )
    raise_primitive_failure(failure, TypeError)


def _restore_tuple_fields(
    dto_cls: type[T],
    value: CanonicalJsonObject,
) -> dict[str, DecodedCanonicalValue]:
    import typing

    restored: dict[str, DecodedCanonicalValue] = dict(value)
    hints: dict[str, object] = typing.get_type_hints(dto_cls)
    for field_name, field_type in hints.items():
        field_value = restored.get(field_name)
        if typing.get_origin(field_type) is tuple and _is_json_array(field_value):
            restored[field_name] = tuple(field_value)
    return restored


def _is_json_array(value: object) -> TypeGuard[CanonicalJsonArray]:
    return isinstance(value, list)
