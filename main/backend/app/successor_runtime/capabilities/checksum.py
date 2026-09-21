"""Deterministic SHA-256 helpers shared by capability-owned contracts/codecs."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, fields, is_dataclass
from typing import Any, NoReturn

from functorial_kit import Failure
from mrw_functorial_kit.core.w06_semantics import capability_primitive_contract_failures

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_PRIMITIVE_WITNESS = "test:test_w06_c2_total_core_failure_lifts"


def _primitive_failure(
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


def _raise_primitive_failure(
    failure: Failure,
    exception_type: type[Exception],
) -> NoReturn:
    context = failure.context or {}
    if (
        failure.family != capability_primitive_contract_failures.name
        or context.get("public_exception") != exception_type.__name__
        or not context.get("public_message")
    ):
        # kit:boundary owner=checksum.py class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w06_c2_total_core_failure_lifts
        raise TypeError("primitive contract lift context is incomplete")
    # kit:boundary owner=checksum.py class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=capability.primitive.contract_failure witness=test:test_w06_c2_total_core_failure_lifts
    raise exception_type(str(context["public_message"]))


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def require_hex64(value: str, field_name: str) -> str:
    if not isinstance(value, str) or _HEX64.fullmatch(value) is None:
        failure = _primitive_failure(
            "digest_contract_invalid",
            f"{field_name} must be a 64-char lowercase hex digest",
            exception_type=ValueError,
            field_name=field_name,
        )
        _raise_primitive_failure(failure, ValueError)
    return value


def _scrub(value: Any) -> Any:
    if is_dataclass(value):
        return {k: _scrub(v) for k, v in sorted(asdict(value).items())}
    if isinstance(value, dict):
        return {str(k): _scrub(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_scrub(v) for v in value]
    if isinstance(value, bytes):
        return value.hex()
    return value


def canonical_json(value: Any, *, omit_fields: tuple[str, ...] = ()) -> str:
    """Sort-key canonical JSON for a dataclass, mapping or scalar."""

    def drop(mapping: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in mapping.items() if k not in omit_fields}

    payload = _scrub(value)
    if isinstance(payload, dict):
        payload = drop(payload)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def content_digest(value: Any, *, omit_fields: tuple[str, ...] = ()) -> str:
    return sha256_hex(canonical_json(value, omit_fields=omit_fields).encode("utf-8"))


def dataclass_field_names(obj: Any) -> tuple[str, ...]:
    return tuple(f.name for f in fields(obj) if f.init)


def decode_dataclass(cls: type, payload: dict[str, Any]) -> Any:
    allowed = set(dataclass_field_names(cls))
    return cls(**{k: v for k, v in payload.items() if k in allowed})
