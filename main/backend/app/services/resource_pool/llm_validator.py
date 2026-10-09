"""Validate LLM output for site entry classification before persisting."""

from __future__ import annotations

import re
from typing import Any, TypeGuard, cast
from urllib.parse import urlparse

from .url_utils import domain_from_url

_ALLOWED_ENTRY_TYPES = frozenset(
    {"rss", "sitemap", "domain_root", "search_template", "official_api"}
)
_ALLOWED_CHANNEL_KEYS = frozenset(
    {
        "generic_web.rss",
        "generic_web.sitemap",
        "generic_web.search_template",
        "official_access.api",
        "url_pool",
    }
)
_SYMBOL_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")


def _is_string_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict) and all(
        isinstance(key, str) for key in cast(dict[object, object], value)
    )


def _clean_text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def validate_llm_recommendation(raw: object, site_url: str) -> dict[str, Any] | None:
    """
    Validate LLM output. Returns sanitized dict if valid, None if invalid.

    Checks:
    - entry_type in allowed set
    - channel_key in allowed set
    - template: if search_template, must contain {{q}}; domain must match site_url
    - symbol_suggestion: if present, must be valid identifier
    """
    if not _is_string_object_dict(raw):
        return None

    entry_type = _clean_text(raw.get("entry_type")).lower()
    channel_key = _clean_text(raw.get("channel_key"))
    template = _clean_text(raw.get("template")) or None
    symbol_suggestion = _clean_text(raw.get("symbol_suggestion")) or None

    if not entry_type or entry_type not in _ALLOWED_ENTRY_TYPES:
        return None
    if not channel_key or channel_key not in _ALLOWED_CHANNEL_KEYS:
        return None

    if entry_type == "search_template":
        if not template or "{{q}}" not in template:
            return None
        try:
            parsed = urlparse(template)
            if not parsed.netloc:
                return None
            tpl_domain = (parsed.netloc or "").lower().lstrip("www.")
            site_domain = domain_from_url(site_url) or ""
            if tpl_domain and site_domain and tpl_domain != site_domain:
                return None
        except Exception:
            return None

    if symbol_suggestion and not _SYMBOL_PATTERN.match(symbol_suggestion):
        return None

    return {
        "entry_type": entry_type,
        "channel_key": channel_key,
        "template": template,
        "symbol_suggestion": symbol_suggestion,
    }
