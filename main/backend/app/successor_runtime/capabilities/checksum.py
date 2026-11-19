"""Deterministic SHA-256 helpers shared by capability-owned contracts/codecs."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import asdict, fields, is_dataclass
from typing import NoReturn, TypeAlias, TypeGuard, TypeVar, Union

from functorial_kit import Failure
from mrw_functorial_kit.core.source_and_capability_failure_semantics import capability_primitive_contract_failures

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_PRIMITIVE_WITNESS = "test:test_capability_failure_preserves_public_errors"
PayloadModel = TypeVar("PayloadModel")
CanonicalJsonValue: TypeAlias = Union[
    None,
    bool,
    int,
    float,
    str,
    "CanonicalJsonObject",
    "CanonicalJsonArray",
]
CanonicalJsonObject: TypeAlias = dict[str, CanonicalJsonValue]
CanonicalJsonArray: TypeAlias = list[CanonicalJsonValue]
DecodedCanonicalValue: TypeAlias = CanonicalJsonValue | tuple[CanonicalJsonValue, ...]


def primitive_failure(
    code: str,
    message: str,
    *,
    exception_type: type[Exception],
    field_name: str,
) -> Failure:
    return capability_primitive_contract_failures.fail(
        code,
        message,
        {
            "owner": "successor_runtime.capabilities.checksum",
            "operation": "capability.primitive",
            "site": field_name,
            "public_exception": exception_type.__name__,
            "public_message": message,
            "witness": _PRIMITIVE_WITNESS,
        },
    )


def raise_primitive_failure(
    failure: Failure,
    exception_type: type[Exception],
) -> NoReturn:
    context = failure.context or {}
    if (
        failure.family != capability_primitive_contract_failures.name
        or context.get("public_exception") != exception_type.__name__
        or not context.get("public_message")
    ):
        # kit:boundary owner=checksum.py class=PROGRAMMER_DEFECT failure_family=none witness=test:test_capability_failure_preserves_public_errors
        raise TypeError("primitive contract lift context is incomplete")
    # kit:boundary owner=checksum.py class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=capability.primitive.contract_failure witness=test:test_capability_failure_preserves_public_errors
    raise exception_type(str(context["public_message"]))


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def require_hex64(value: str, field_name: str) -> str:
    if _HEX64.fullmatch(value) is None:
        failure = primitive_failure(
            "digest_contract_invalid",
            f"{field_name} must be a 64-char lowercase hex digest",
            exception_type=ValueError,
            field_name=field_name,
        )
        raise_primitive_failure(failure, ValueError)
    return value


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _is_object_sequence(
    value: object,
) -> TypeGuard[list[object] | tuple[object, ...]]:
    return isinstance(value, (list, tuple))


def _scrub(value: object) -> CanonicalJsonValue:
    if is_dataclass(value) and not isinstance(value, type):
        dataclass_value: object = asdict(value)
        return _scrub(dataclass_value)
    if _is_object_mapping(value):
        return {
            str(key): _scrub(item)
            for key, item in sorted(value.items(), key=lambda entry: str(entry[0]))
        }
    if _is_object_sequence(value):
        return [_scrub(item) for item in value]
    if isinstance(value, bytes):
        return value.hex()
    if value is None or isinstance(value, bool | int | float | str):
        return value
    failure = primitive_failure(
        "codec_input_type_invalid",
        f"canonical codec cannot encode {type(value).__name__}",
        exception_type=TypeError,
        field_name="canonical_json/value",
    )
    raise_primitive_failure(failure, TypeError)


def canonical_json(value: object, *, omit_fields: tuple[str, ...] = ()) -> str:
    """Sort-key canonical JSON for a dataclass, mapping or scalar."""

    def drop(mapping: CanonicalJsonObject) -> CanonicalJsonObject:
        return {k: v for k, v in mapping.items() if k not in omit_fields}

    payload = _scrub(value)
    if isinstance(payload, dict):
        payload = drop(payload)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def content_digest(value: object, *, omit_fields: tuple[str, ...] = ()) -> str:
    return sha256_hex(canonical_json(value, omit_fields=omit_fields).encode("utf-8"))


def dataclass_field_names(obj: object) -> tuple[str, ...]:
    if not is_dataclass(obj):
        failure = primitive_failure(
            "codec_input_type_invalid",
            "decode target must be a dataclass",
            exception_type=TypeError,
            field_name="decode_dataclass/target",
        )
        raise_primitive_failure(failure, TypeError)
    return tuple(f.name for f in fields(obj) if f.init)


def decode_dataclass(
    cls: type[PayloadModel],
    payload: Mapping[str, DecodedCanonicalValue],
) -> PayloadModel:
    allowed = set(dataclass_field_names(cls))
    return cls(**{k: v for k, v in payload.items() if k in allowed})
