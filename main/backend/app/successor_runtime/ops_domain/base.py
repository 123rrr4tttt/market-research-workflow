"""Shared authority and text helpers for S2c ops-domain surfaces."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from functorial_kit import Failure
from mrw_functorial_kit.core.w07_semantics import ops_surface_failures

OPS_SURFACE_FAILURE_WITNESS = "test:test_w07_ops_surface_failure_family"


def ops_surface_failure(
    code: str,
    message: str,
    *,
    site: str,
    **context: Any,
) -> Failure:
    """Build a closed W07 ops-surface failure value for a future lift."""

    return ops_surface_failures.fail(
        code,
        message,
        {
            "owner": "successor_runtime.ops_domain",
            "site": site,
            "failure_family": ops_surface_failures.name,
            "witness": OPS_SURFACE_FAILURE_WITNESS,
            **context,
        },
    )

AUTHORITY_KEYS: tuple[str, ...] = (
    "canonical_write",
    "live_provider",
    "external_delivery",
    "cutover",
    "authority_transfer",
    "scheduler",
    "executor",
    "credential_read",
)


def authority_ceiling() -> dict[str, bool]:
    """Return the only authority state an ops-domain surface may carry."""

    return {name: False for name in AUTHORITY_KEYS}


def require_authority_false(value: Mapping[str, bool]) -> None:
    """Fail closed unless every authority key is explicitly false."""

    if not isinstance(value, Mapping):
        # kit:boundary owner=successor_runtime.ops_domain.base.require_authority_false class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w07_ops_surface_programmer_defect_boundaries
        raise TypeError("authority must be a mapping")
    plain = dict(value)
    if set(plain) != set(AUTHORITY_KEYS):
        # kit:boundary owner=successor_runtime.ops_domain.base.require_authority_false class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w07_ops_surface_programmer_defect_boundaries
        raise ValueError("authority keys must equal " + ",".join(AUTHORITY_KEYS))
    for name in AUTHORITY_KEYS:
        if plain[name] is not False:
            # kit:boundary owner=successor_runtime.ops_domain.base.require_authority_false class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w07_ops_surface_programmer_defect_boundaries
            raise ValueError(f"{name} authority must remain false")


def normalized_text(
    value: Any,
    name: str,
    *,
    required: bool = True,
    max_bytes: int = 4096,
) -> str:
    """Normalize one non-credential string field."""

    if value is None and not required:
        return ""
    if not isinstance(value, str):
        # kit:boundary owner=successor_runtime.ops_domain.base.normalized_text class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w07_ops_surface_programmer_defect_boundaries
        raise TypeError(f"{name} must be a string")
    text = value.strip()
    if not text and required:
        # kit:boundary owner=successor_runtime.ops_domain.base.normalized_text class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w07_ops_surface_programmer_defect_boundaries
        raise ValueError(f"{name} must not be blank")
    if len(text.encode("utf-8")) > max_bytes:
        # kit:boundary owner=successor_runtime.ops_domain.base.normalized_text class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w07_ops_surface_programmer_defect_boundaries
        raise ValueError(f"{name} exceeds the {max_bytes}-byte ceiling")
    lowered = text.lower()
    if any(
        marker in lowered
        for marker in ("secret", "token", "password", "api_key", "apikey")
    ):
        # kit:boundary owner=successor_runtime.ops_domain.base.normalized_text class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w07_ops_surface_programmer_defect_boundaries
        raise ValueError(f"{name} must not carry credential-like raw material")
    return text


def normalized_string_tuple(value: Any, name: str) -> tuple[str, ...]:
    """Normalize a tuple of trimmed string refs."""

    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        # kit:boundary owner=successor_runtime.ops_domain.base.normalized_string_tuple class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w07_ops_surface_programmer_defect_boundaries
        raise TypeError(f"{name} must be a sequence of strings")
    items = tuple(
        normalized_text(item, f"{name}[{index}]") for index, item in enumerate(value)
    )
    return items


def stable_sha256(payload: Any) -> str:
    """Deterministic sha256 over a JSON-compatible payload."""

    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "AUTHORITY_KEYS",
    "OPS_SURFACE_FAILURE_WITNESS",
    "authority_ceiling",
    "ops_surface_failure",
    "normalized_string_tuple",
    "normalized_text",
    "require_authority_false",
    "stable_sha256",
]
