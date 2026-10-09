"""Policy channel adapter: wrap ingest.policy.ingest_policy_documents."""

from __future__ import annotations

from collections.abc import Mapping
from importlib import import_module
from typing import Protocol, TypeGuard, runtime_checkable


@runtime_checkable
class _CancelCheck(Protocol):
    def __call__(self, progress: int) -> bool: ...


@runtime_checkable
class _PolicyIngestPort(Protocol):
    def __call__(
        self,
        state: str,
        source_hint: str | None = None,
        *,
        enable_extraction: bool = False,
        max_documents: int | None = None,
        cancel_check: _CancelCheck | None = None,
        request_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, object]: ...


def _is_object(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict)


def _object(value: object) -> dict[str, object]:
    return dict(value) if _is_object(value) else {}


def _optional_bound(value: object) -> int | None:
    """Normalize a caller-provided document bound without inventing one."""
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, int | float | str):
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def _extraction_requested(params: Mapping[object, object]) -> bool:
    """Read explicit extraction intent while keeping the historical default off."""
    extraction = params.get("extraction")
    extraction_payload = _object(extraction)
    if extraction_payload:
        for key in ("requested", "enabled", "enable_extraction", "intent"):
            if key in extraction_payload:
                return bool(extraction_payload[key])
    for key in (
        "enable_extraction",
        "structured_extraction",
        "extraction_requested",
        "extract",
    ):
        if key in params:
            return bool(params[key])
    return False


def _request_identity(params: Mapping[object, object], key: str) -> str | None:
    value = params.get(key)
    identity = _object(params.get("request_identity"))
    if value is None and identity:
        value = identity.get(key)
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _cancel_check(params: Mapping[object, object]) -> _CancelCheck | None:
    """Project only callable cancellation hooks; JSON flags cannot be a hook."""
    for key in ("cancel_check", "cancel_safe"):
        candidate = params.get(key)
        if isinstance(candidate, _CancelCheck):
            return candidate
        candidate_payload = _object(candidate)
        if candidate_payload:
            for check_key in ("check", "cancel_check"):
                nested = candidate_payload.get(check_key)
                if isinstance(nested, _CancelCheck):
                    return nested
    cancellation_payload = _object(params.get("cancellation"))
    if cancellation_payload:
        for check_key in ("check", "cancel_check"):
            nested = cancellation_payload.get(check_key)
            if isinstance(nested, _CancelCheck):
                return nested
    return None


def _resolve_policy_ingest() -> _PolicyIngestPort:
    module = import_module("app.services.ingest.policy")
    candidate = getattr(module, "ingest_policy_documents", None)
    if not isinstance(candidate, _PolicyIngestPort):
        raise RuntimeError("ingest.policy adapter is unavailable")
    return candidate


def handle_policy(params: Mapping[object, object], _project_key: str | None) -> dict[str, object]:
    """Ingest policy documents by state."""
    state = str(params.get("state") or "")
    source_hint_value = params.get("source_hint")
    source_hint = str(source_hint_value).strip() or None if source_hint_value is not None else None
    extraction = params.get("extraction")
    extraction_payload = _object(extraction)
    extraction_bound = (
        extraction_payload.get("max_documents", extraction_payload.get("bound"))
        if extraction_payload
        else None
    )
    bound = params.get("max_documents", params.get("bound", extraction_bound))
    result = _resolve_policy_ingest()(
        state=state,
        source_hint=source_hint,
        enable_extraction=_extraction_requested(params),
        max_documents=_optional_bound(bound),
        cancel_check=_cancel_check(params),
        request_id=_request_identity(params, "request_id"),
        idempotency_key=_request_identity(params, "idempotency_key"),
    )
    return _object(result)
