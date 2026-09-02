"""Versioned canonical codecs for capability payload DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from .checksum import content_digest, decode_dataclass, require_hex64
from .contracts import OperationContractRef

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class PayloadCodec:
    codec_id: str
    codec_version: str
    contract_ref: OperationContractRef
    payload_type_id: str
    encode: Callable[[Any], dict[str, Any]]
    decode: Callable[[dict[str, Any]], Any]
    codec_digest: str

    def __post_init__(self) -> None:
        require_hex64(self.codec_digest, "PayloadCodec.codec_digest")

    def encode_payload(self, value: T) -> dict[str, Any]:
        return self.encode(value)

    def decode_payload(self, value: dict[str, Any]) -> T:
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
    dto_cls: type,
) -> PayloadCodec:
    digest = codec_digest(codec_id, codec_version, contract_ref, payload_type_id)

    def encode(value: Any) -> dict[str, Any]:
        if not isinstance(value, dto_cls):
            raise TypeError(f"{codec_id} codec expected {dto_cls.__name__}")
        return _canonical_dict(value)

    def decode(value: dict[str, Any]) -> Any:
        return decode_dataclass(dto_cls, _restore_tuple_fields(dto_cls, value))

    return PayloadCodec(
        codec_id=codec_id,
        codec_version=codec_version,
        contract_ref=contract_ref,
        payload_type_id=payload_type_id,
        encode=encode,
        decode=decode,
        codec_digest=digest,
    )


def _canonical_dict(value: Any) -> dict[str, Any]:
    import dataclasses

    if dataclasses.is_dataclass(value):
        return {k: _canonical_dict(v) for k, v in dataclasses.asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): _canonical_dict(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_dict(v) for v in value]
    if isinstance(value, bytes):
        return value.hex()
    return value


def _restore_tuple_fields(dto_cls: type, value: dict[str, Any]) -> dict[str, Any]:
    import dataclasses
    import typing

    restored = dict(value)
    hints = typing.get_type_hints(dto_cls)
    for field_def in dataclasses.fields(dto_cls):
        field_type = hints.get(field_def.name, field_def.type)
        if typing.get_origin(field_type) is tuple and field_def.name in restored:
            restored[field_def.name] = tuple(restored[field_def.name])
    return restored
