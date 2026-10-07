"""Canonical authority digest retained for C2.1 rehydration."""

from __future__ import annotations

from datetime import UTC, datetime

from app.successor_runtime.runtime.assignments import canonical_digest


def authority_digest(
    *,
    project_key: str,
    capability_id: str,
    mode: str,
    authority_epoch: int,
    successor_claim_enabled: bool,
    legacy_claim_enabled: bool,
    allowlist_digest: str,
    config_digest: str,
    effective_at: datetime,
    updated_by: str,
    approval_ref: str,
    rollback_target_ref: str,
    revision: int,
) -> str:
    """Content-addressed digest over one capability authority row."""

    if successor_claim_enabled and legacy_claim_enabled:
        raise ValueError("legacy and successor claim authority cannot both be enabled")
    return canonical_digest(
        {
            "project_key": project_key,
            "capability_id": capability_id,
            "mode": mode,
            "authority_epoch": authority_epoch,
            "successor_claim_enabled": successor_claim_enabled,
            "legacy_claim_enabled": legacy_claim_enabled,
            "allowlist_digest": allowlist_digest,
            "config_digest": config_digest,
            "effective_at": effective_at.astimezone(UTC).isoformat(),
            "updated_by": updated_by,
            "approval_ref": approval_ref,
            "rollback_target_ref": rollback_target_ref,
            "revision": revision,
        }
    )


__all__ = ["authority_digest"]
