from __future__ import annotations

import os
from typing import Any, Dict

from ...project_customization import get_project_customization
from .handler_registry import get

_REGISTERED = False


def _ensure_handlers_registered() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    from . import adapters  # noqa: F401 - trigger handler registration (lazy to avoid circular import)
    _REGISTERED = True


def resolve_credential(cred_name: str, project_key: str | None) -> str | None:
    normalized = (project_key or "").strip().upper()
    normalized = "".join(ch if ch.isalnum() else "_" for ch in normalized)
    if normalized:
        project_scoped = f"PROJECT_{normalized}_{cred_name}"
        value = os.getenv(project_scoped)
        if value:
            return value
    return os.getenv(cred_name)


def validate_params(params: Dict[str, Any], param_schema: Dict[str, Any]) -> None:
    required = param_schema.get("required", [])
    if not isinstance(required, list):
        return
    missing = [key for key in required if key not in params]
    if missing:
        raise ValueError(f"missing required params: {missing}")


def run_channel(
    *,
    channel: Dict[str, Any],
    params: Dict[str, Any],
    project_key: str | None = None,
) -> Dict[str, Any]:
    _ensure_handlers_registered()
    credential_refs = channel.get("credential_refs") or []
    if isinstance(credential_refs, list):
        missing_creds = [
            c for c in credential_refs if isinstance(c, str) and resolve_credential(c, project_key) is None
        ]
        if missing_creds:
            raise ValueError(f"missing credentials for channel {channel.get('channel_key')}: {missing_creds}")

    validate_params(params=params, param_schema=channel.get("param_schema") or {})

    provider = str(channel.get("provider", "")).strip().lower()
    kind = str(channel.get("kind", "")).strip().lower()

    customization = get_project_customization(project_key)
    project_handlers = customization.get_channel_handlers()
    handler = project_handlers.get((provider, kind)) if project_handlers else None
    if handler is not None:
        return handler(channel, params, project_key)

    handler = get(provider, kind)
    if handler is None:
        raise ValueError(f"unsupported channel provider/kind: {provider}/{kind}")
    if provider == "policy" and not str(params.get("state") or "").strip():
        raise ValueError("policy channel requires params.state")
    if provider == "market":
        keywords = params.get("keywords") or params.get("query_terms")
        if not isinstance(keywords, list) or not keywords:
            raise ValueError("market channel requires params.keywords or params.query_terms")
    if provider == "google_news":
        keywords = params.get("keywords")
        if isinstance(keywords, str):
            keywords = [keywords]
            params = {**params, "keywords": keywords}
        if not isinstance(keywords, list) or not keywords:
            raise ValueError("google_news requires params.keywords list")
    return handler(params, project_key)


__all__ = ["run_channel", "resolve_credential", "validate_params"]
