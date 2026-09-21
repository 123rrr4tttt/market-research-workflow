"""Strict canonical JSON codec and SHA-256 digest helpers.

The successor codec never uses a lossy json.dumps default-string coercion.
Values that cannot be represented without lossy coercion produce
:class:`UnsupportedCanonicalValueError` instead of being stringified.  JSON
object keys are sorted by UTF-16 code units (RFC 8785 style) and datetimes are
normalized to fixed UTC ISO-8601 strings.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
from dataclasses import fields, is_dataclass
from typing import Any, Mapping, Sequence

from functorial_kit import Failure

from mrw_functorial_kit.core.w07_semantics import research_failures

_RESEARCH_FAILURE_WITNESS = "test:test_w07_language_research_failure_boundary"


def _failure(
    code: str,
    message: object,
    exception_type: type[Exception],
    *,
    site: str,
) -> Failure:
    """Create a closed research failure before lifting at the public ABI."""

    public_message = str(exception_type(message))
    return research_failures.fail(
        code,
        public_message,
        {
            "public_exception": exception_type.__name__,
            "public_argument": message,
            "public_message": public_message,
            "site": site,
            "witness": _RESEARCH_FAILURE_WITNESS,
        },
    )


def _raise_failure(
    failure: Failure,
    exception_type: type[Exception],
    *,
    cause: BaseException | None = None,
) -> None:
    """Lift a complete typed failure while retaining the existing exception ABI."""

    context = failure.context or {}
    if (
        not research_failures.matches(failure)
        or context.get("public_exception") != exception_type.__name__
        or not context.get("public_message")
    ):
        # kit:boundary owner=successor.research.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w07_language_research_failure_boundary
        raise TypeError("research failure lift context is incomplete")
    # kit:boundary owner=successor.research.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.research.failure witness=test:test_w07_language_research_failure_boundary
    if cause is None:
        # kit:boundary owner=successor.research.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.research.failure witness=test:test_w07_language_research_failure_boundary
        raise exception_type(context.get("public_argument", context["public_message"]))
    # kit:boundary owner=successor.research.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.research.failure witness=test:test_w07_language_research_failure_boundary
    raise exception_type(context.get("public_argument", context["public_message"])) from cause

__all__ = [
    "CanonicalCodecError",
    "UnsupportedCanonicalValueError",
    "canonical_bytes",
    "canonical_json",
    "dataclass_to_json",
    "digest_dataclass",
    "encode",
    "finalize_digest",
    "is_sha256_hex",
    "sha256_hex",
]


class CanonicalCodecError(ValueError):
    """Base error for canonical codec failures."""


class UnsupportedCanonicalValueError(CanonicalCodecError):
    """Raised when a value cannot be canonicalized without lossy coercion."""


def _utf16_key(text: str) -> bytes:
    return text.encode("utf-16-le")


def _quote(text: str) -> str:
    parts = ['"']
    for char in text:
        code = ord(char)
        if char == '"':
            parts.append('\\"')
        elif char == "\\":
            parts.append("\\\\")
        elif code < 0x20:
            parts.append(f"\\u{code:04x}")
        else:
            parts.append(char)
    parts.append('"')
    return "".join(parts)


def _datetime_text(value: _dt.datetime) -> str:
    if value.tzinfo is None:
        _raise_failure(
            _failure(
                "CANONICAL_ENCODING_INVALID",
                "naive datetime is not canonical",
                CanonicalCodecError,
                site="codec.datetime.tzinfo",
            ),
            CanonicalCodecError,
        )
    return value.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def encode(value: Any) -> str:
    """Return canonical JSON text for a supported value."""
    return _encode(value)


def _encode(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            _raise_failure(
                _failure(
                    "CANONICAL_ENCODING_INVALID",
                    f"non-finite float is not canonical: {value!r}",
                    CanonicalCodecError,
                    site="codec.float.finite",
                ),
                CanonicalCodecError,
            )
        return repr(value)
    if isinstance(value, str):
        return _quote(value)
    if isinstance(value, _dt.datetime):
        return _quote(_datetime_text(value))
    if isinstance(value, Mapping):
        for key in value:
            if not isinstance(key, str):
                _raise_failure(
                    _failure(
                        "CANONICAL_JSON_ROOT_INVALID",
                        f"non-string JSON object key is not canonical: {key!r}",
                        CanonicalCodecError,
                        site="codec.mapping.key",
                    ),
                    CanonicalCodecError,
                )
        items = sorted(value.items(), key=lambda item: _utf16_key(item[0]))
        body = ",".join(_quote(key) + ":" + _encode(item) for key, item in items)
        return "{" + body + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_encode(item) for item in value) + "]"
    if isinstance(value, (set, frozenset)):
        ordered = sorted(value, key=encode)
        return "[" + ",".join(_encode(item) for item in ordered) + "]"
    if is_dataclass(value):
        return _encode(dataclass_to_json(value))
    _raise_failure(
        _failure(
            "CANONICAL_VALUE_UNSUPPORTED",
            f"cannot canonicalize {type(value).__name__}; refusing lossy string coercion",
            UnsupportedCanonicalValueError,
            site="codec.value.type",
        ),
        UnsupportedCanonicalValueError,
    )


def dataclass_to_json(obj: Any, exclude: Sequence[str] = ()) -> dict[str, Any]:
    """Return a JSON-native mapping for a dataclass in declaration order."""
    if not is_dataclass(obj):
        _raise_failure(
            _failure(
                "CANONICAL_ENCODING_INVALID",
                f"expected a dataclass instance, got {type(obj).__name__}",
                TypeError,
                site="codec.dataclass_to_json.input",
            ),
            TypeError,
        )
    excluded = set(exclude)
    return {
        field.name: getattr(obj, field.name)
        for field in fields(obj)
        if field.name not in excluded
    }


def canonical_json(value: Any) -> str:
    """Return canonical JSON text without any lossy default coercion."""
    return encode(value)


def canonical_bytes(value: Any) -> bytes:
    """Return canonical JSON bytes without any lossy default coercion."""
    return canonical_json(value).encode("utf-8")


def sha256_hex(value: Any) -> str:
    """Return the SHA-256 digest of the canonical JSON encoding."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def digest_dataclass(obj: Any, exclude: Sequence[str] = ()) -> str:
    """Return the canonical digest of a dataclass, minus excluded fields."""
    return sha256_hex(dataclass_to_json(obj, exclude))


def finalize_digest(obj: Any, digest_field: str) -> None:
    """Compute or validate one self-referential digest field on a dataclass."""
    expected = digest_dataclass(obj, (digest_field,))
    current = getattr(obj, digest_field)
    if current is None:
        object.__setattr__(obj, digest_field, expected)
        return
    if current != expected:
        _raise_failure(
            _failure(
                "DIGEST_FINALIZATION_INVALID",
                f"{type(obj).__name__} {digest_field} mismatch",
                ValueError,
                site=f"codec.finalize_digest.{digest_field}",
            ),
            ValueError,
        )


def is_sha256_hex(value: str) -> bool:
    """Return True for a lowercase 64-hex SHA-256 digest."""
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)
