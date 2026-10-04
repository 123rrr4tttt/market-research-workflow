from __future__ import annotations

from typing import Set

from ...settings.config import settings


_DEFAULT_MODE = "on"


def _normalize_mode(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"", "on", "all", "enabled", "full"}:
        return "on"
    if raw in {"off", "disabled", "rollback"}:
        return "off"
    if raw in {"canary", "gray", "grey", "project_canary"}:
        return "canary"
    if raw in {"passthrough", "inherit", "legacy"}:
        return "passthrough"
    return _DEFAULT_MODE


def _parse_project_allowlist(value: str | None) -> Set[str]:
    raw = str(value or "")
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def is_ingest_frontdoor_enabled(*, requested_enabled: bool, project_key: str | None) -> bool:
    if not bool(requested_enabled):
        return False

    mode = _normalize_mode(getattr(settings, "ingest_frontdoor_rollout_mode", _DEFAULT_MODE))
    if mode in {"on", "passthrough"}:
        return True
    if mode == "off":
        return False

    # mode == "canary"
    normalized_project = str(project_key or "").strip().lower()
    if not normalized_project:
        return False
    allowlist = _parse_project_allowlist(getattr(settings, "ingest_frontdoor_canary_projects", ""))
    return normalized_project in allowlist


__all__ = ["is_ingest_frontdoor_enabled"]
