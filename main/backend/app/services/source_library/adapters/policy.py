"""Policy channel adapter: wrap ingest.policy.ingest_policy_documents."""

from __future__ import annotations

from typing import Any, Dict


def _optional_bound(value: Any) -> int | None:
    """Normalize a caller-provided document bound without inventing one."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def _extraction_requested(params: Dict[str, Any]) -> bool:
    """Read explicit extraction intent while keeping the historical default off."""
    extraction = params.get("extraction")
    if isinstance(extraction, dict):
        for key in ("requested", "enabled", "enable_extraction", "intent"):
            if key in extraction:
                return bool(extraction[key])
    for key in (
        "enable_extraction",
        "structured_extraction",
        "extraction_requested",
        "extract",
    ):
        if key in params:
            return bool(params[key])
    return False


def _request_identity(params: Dict[str, Any], key: str) -> str | None:
    value = params.get(key)
    if value is None and isinstance(params.get("request_identity"), dict):
        value = params["request_identity"].get(key)
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _cancel_check(params: Dict[str, Any]):
    """Project only callable cancellation hooks; JSON flags cannot be a hook."""
    for key in ("cancel_check", "cancel_safe"):
        candidate = params.get(key)
        if callable(candidate):
            return candidate
        if isinstance(candidate, dict):
            for check_key in ("check", "cancel_check"):
                if callable(candidate.get(check_key)):
                    return candidate[check_key]
    cancellation = params.get("cancellation")
    if isinstance(cancellation, dict):
        for check_key in ("check", "cancel_check"):
            if callable(cancellation.get(check_key)):
                return cancellation[check_key]
    return None


def handle_policy(params: Dict[str, Any], _project_key: str | None) -> Dict[str, Any]:
    """Ingest policy documents by state."""
    from ...ingest.policy import ingest_policy_documents

    state = str(params.get("state") or "")
    source_hint = params.get("source_hint")
    extraction = params.get("extraction")
    extraction_bound = (
        extraction.get("max_documents", extraction.get("bound"))
        if isinstance(extraction, dict)
        else None
    )
    bound = params.get("max_documents", params.get("bound", extraction_bound))
    return ingest_policy_documents(
        state=state,
        source_hint=source_hint,
        enable_extraction=_extraction_requested(params),
        max_documents=_optional_bound(bound),
        cancel_check=_cancel_check(params),
        request_id=_request_identity(params, "request_id"),
        idempotency_key=_request_identity(params, "idempotency_key"),
    )
