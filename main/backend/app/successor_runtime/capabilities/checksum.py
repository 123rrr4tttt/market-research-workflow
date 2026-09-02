"""Deterministic SHA-256 helpers shared by capability-owned contracts/codecs."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, fields, is_dataclass
from typing import Any

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def require_hex64(value: str, field_name: str) -> str:
    if not isinstance(value, str) or _HEX64.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a 64-char lowercase hex digest")
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
