"""Pure observations of collect delivery and declared provider concurrency.

This module never changes worker/provider state. In particular, a worker's
successful return is not a provider terminal readback.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

DeliveryState = Literal["delivered", "failed", "cancelled", "waiting", "unknown"]
Compatibility = Literal["compatible", "conflict", "unknown"]


@dataclass(frozen=True, slots=True)
class DeliveryObservation:
    state: DeliveryState
    worker_status: str | None
    provider_job_id: str | None
    provider_type: str | None
    provider_status: str | None
    readback_kind: str | None
    readback_status: str | None
    provider_state: DeliveryState
    expected_delivery: str
    readback_job_id: str | None
    identity_match: bool | None


def observe_delivery(result: Any | None, *, expected_delivery: str = "provider_terminal") -> DeliveryObservation:
    """Summarize provider facts and a separately declared delivery target."""
    if result is None:
        return DeliveryObservation("unknown", None, None, None, None, None, None, "unknown", expected_delivery, None, None)

    worker_status = _normalized(getattr(result, "status", None))
    provider_status = _normalized(getattr(result, "provider_status", None))
    provider_job_id = _string_or_none(getattr(result, "provider_job_id", None))
    meta = getattr(result, "meta", None)
    meta = meta if isinstance(meta, dict) else {}
    readback = meta.get("terminal_readback")
    if not isinstance(readback, dict):
        raw = meta.get("raw")
        readback = raw.get("terminal_readback") if isinstance(raw, dict) else None
    if not isinstance(readback, dict):
        readback = {}
    kind = _normalized(readback.get("kind"))
    readback_status = _normalized(readback.get("status"))
    # Source Library typed readback nests the terminal status in `readback`.
    nested = readback.get("readback")
    if readback_status is None and isinstance(nested, dict):
        readback_status = _normalized(nested.get("terminal_status"))
    readback_job_id = _string_or_none(
        readback.get("provider_job_id")
        or readback.get("readback_job_id")
        or (nested.get("provider_job_id") if isinstance(nested, dict) else None)
    )
    identity_match = (
        provider_job_id == readback_job_id
        if provider_job_id is not None and readback_job_id is not None
        else None
    )

    if kind == "terminal" and identity_match is not True:
        provider_state: DeliveryState = "unknown"
    elif kind == "terminal" and readback_status in {"completed", "complete", "succeeded"}:
        provider_state = "delivered" if worker_status in {"completed", "complete", "succeeded"} else "unknown"
    elif kind == "terminal" and readback_status == "failed":
        provider_state = "failed"
    elif kind == "terminal" and readback_status == "cancelled":
        provider_state = "cancelled"
    elif kind == "waiting" or provider_status in {"waiting", "pending", "running", "accepted"}:
        provider_state = "waiting"
    elif worker_status in {"failed", "error"}:
        # Worker failure alone says nothing about whether an effect escaped.
        provider_state = "unknown"
    elif worker_status in {"cancelled", "canceled"}:
        provider_state = "unknown"
    else:
        provider_state = "unknown"

    state: DeliveryState = (
        provider_state if expected_delivery == "provider_terminal" or provider_state != "delivered" else "unknown"
    )

    return DeliveryObservation(
        state=state,
        worker_status=worker_status,
        provider_job_id=provider_job_id,
        provider_type=_string_or_none(getattr(result, "provider_type", None)),
        provider_status=provider_status,
        readback_kind=kind,
        readback_status=readback_status,
        provider_state=provider_state,
        expected_delivery=expected_delivery,
        readback_job_id=readback_job_id,
        identity_match=identity_match,
    )


def resource_compatibility(left: Any | None, right: Any | None) -> Compatibility:
    """Compare declared C3 provider-concurrency keys.

    A repeated key is a declared conflict. Different keys do not establish
    compatibility: C3 supplies neither write scopes nor a shared capacity
    ledger, so all non-conflicting pairs remain unknown.
    """
    left_key = _normalized(getattr(left, "provider_concurrency_key", None))
    right_key = _normalized(getattr(right, "provider_concurrency_key", None))
    if not left_key or not right_key:
        return "unknown"
    return "conflict" if left_key == right_key else "unknown"


def _normalized(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
