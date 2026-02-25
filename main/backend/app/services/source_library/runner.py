from __future__ import annotations

import os
from typing import Any, Callable, Dict

from ...project_customization import get_project_customization
from ..ingest.market_web import collect_market_info
from ..ingest.news import collect_google_news, collect_reddit_discussions
from ..ingest.policy import ingest_policy_documents

ChannelCallable = Callable[[Dict[str, Any], str | None], Dict[str, Any]]
ChannelKey = tuple[str, str]

_CHANNEL_HANDLERS: dict[ChannelKey, ChannelCallable] = {}
_REGISTERED = False


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


def register_handler(provider: str, kind: str, handler: ChannelCallable) -> None:
    key = (provider.strip().lower(), kind.strip().lower())
    _CHANNEL_HANDLERS[key] = handler


def get_handler(provider: str, kind: str) -> ChannelCallable | None:
    key = (provider.strip().lower(), kind.strip().lower())
    return _CHANNEL_HANDLERS.get(key)


def _register_builtin_handlers() -> None:
    global _REGISTERED
    if _REGISTERED:
        return

    register_handler(
        "reddit",
        "social",
        lambda params, _project_key: collect_reddit_discussions(
            subreddit=str(params.get("subreddit") or "Lottery"),
            limit=int(params.get("limit", 20)),
        ),
    )
    register_handler(
        "google_news",
        "news",
        lambda params, _project_key: collect_google_news(
            keywords=[str(x) for x in (([params.get("keywords")] if isinstance(params.get("keywords"), str) else params.get("keywords")) or [])],
            limit=int(params.get("limit", 20)),
        ),
    )
    register_handler(
        "policy",
        "policy",
        lambda params, _project_key: ingest_policy_documents(
            state=str(params.get("state") or ""),
            source_hint=params.get("source_hint"),
        ),
    )
    register_handler(
        "market",
        "market",
        lambda params, _project_key: collect_market_info(
            keywords=[str(x) for x in (params.get("keywords") or params.get("query_terms") or [])],
            limit=int(params.get("limit", 20)),
            enable_extraction=bool(params.get("enable_extraction", True)),
        ),
    )
    _REGISTERED = True


def run_channel(
    *,
    channel: Dict[str, Any],
    params: Dict[str, Any],
    project_key: str | None = None,
) -> Dict[str, Any]:
    _register_builtin_handlers()
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

    handler = get_handler(provider, kind)
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


__all__ = ["register_handler", "get_handler", "run_channel"]
