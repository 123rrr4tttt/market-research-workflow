"""Rule-first site entry classification. LLM fallback when rules cannot determine."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from ...settings.config import settings
from ..extraction.json_utils import extract_json_payload
from ..llm.config_loader import format_prompt_template, get_llm_config
from ..llm.provider import get_chat_model
from .llm_validator import validate_llm_recommendation
from .url_utils import domain_from_url

_log = logging.getLogger(__name__)

_DEFAULT_LLM_PROMPT = """Given this site URL: {site_url}

Classify it as one of: rss, sitemap, domain_root, search_template, official_api.

If it looks like a search page (has q=, query=, search in path), return search_template and provide a template URL with {{q}} and optionally {{page}} placeholders. The template domain must match the site domain.

Return JSON only:
{{"entry_type": "...", "channel_key": "generic_web.rss|generic_web.sitemap|generic_web.search_template|official_access.api|url_pool", "template": "optional for search_template"}}
"""

_ENTRY_TYPE_TO_CHANNEL: dict[str, str] = {
    "rss": "generic_web.rss",
    "sitemap": "generic_web.sitemap",
    "domain_root": "url_pool",
    "search_template": "generic_web.search_template",
    "official_api": "official_access.api",
}

_ALLOWED_ENTRY_TYPES = frozenset(_ENTRY_TYPE_TO_CHANNEL)
_ALLOWED_CHANNEL_KEYS = frozenset(_ENTRY_TYPE_TO_CHANNEL.values()) | {"url_pool"}


@dataclass
class Recommendation:
    """Classify result: channel_key, entry_type, template (if search_template), validated flag."""

    channel_key: str
    entry_type: str
    template: str | None
    validated: bool
    source: str  # "rule" | "llm" | "fallback"


def _path_from_url(url: str) -> str:
    """Extract path from URL (lowercase)."""
    if not url or not isinstance(url, str):
        return ""
    try:
        parsed = urlparse(url)
        return (parsed.path or "").lower()
    except Exception:
        return ""


def _path_suggests_rss(path: str) -> bool:
    """Check if path suggests RSS/Atom feed."""
    if not path:
        return False
    path = path.lower()
    return any(x in path for x in (".xml", "/feed", "/rss", "/atom"))


def _path_suggests_sitemap(path: str) -> bool:
    """Check if path suggests sitemap."""
    if not path:
        return False
    return "sitemap" in path.lower()


def _rule_classify(
    site_url: str,
    entry_type: str | None,
    template: str | None,
) -> Recommendation | None:
    """
    Pure rule-based classification. Returns None when rules cannot determine.
    """
    if not site_url or not site_url.strip().lower().startswith(("http://", "https://")):
        return None

    path = _path_from_url(site_url)
    known_entry = (entry_type or "").strip().lower()

    # Known entry_type -> direct channel mapping
    if known_entry in _ALLOWED_ENTRY_TYPES:
        ch = _ENTRY_TYPE_TO_CHANNEL[known_entry]
        if known_entry == "search_template" and not template:
            return None  # search_template needs template, cannot rule-classify
        return Recommendation(
            channel_key=ch,
            entry_type=known_entry,
            template=template,
            validated=True,
            source="rule",
        )

    # URL path heuristics when entry_type unknown
    if _path_suggests_sitemap(path):
        return Recommendation(
            channel_key="generic_web.sitemap",
            entry_type="sitemap",
            template=None,
            validated=True,
            source="rule",
        )
    if _path_suggests_rss(path):
        return Recommendation(
            channel_key="generic_web.rss",
            entry_type="rss",
            template=None,
            validated=True,
            source="rule",
        )

    return None


def _llm_available() -> bool:
    """Check if LLM is configured and has API key."""
    p = (settings.llm_provider or "").lower()
    if p == "openai":
        return bool(settings.openai_api_key)
    if p == "azure":
        return bool(settings.azure_api_key)
    if p == "ollama":
        return True
    return False


def _llm_classify(site_url: str, entry_type: str | None, template: str | None) -> Recommendation | None:
    """
    Call LLM to classify site entry. Returns None on failure or invalid output.
    """
    if not _llm_available():
        _log.debug("_llm_classify: LLM not available, skip")
        return None

    config = get_llm_config("site_entry_classification")
    if config and config.get("user_prompt_template"):
        prompt = format_prompt_template(
            config["user_prompt_template"],
            site_url=site_url,
            entry_type=entry_type or "",
            template=template or "",
        )
    else:
        prompt = _DEFAULT_LLM_PROMPT.format(site_url=site_url)

    try:
        model = get_chat_model(
            model=config.get("model") if config else None,
            temperature=config.get("temperature", 0.2) if config else 0.2,
            max_tokens=config.get("max_tokens", 500) if config else 500,
        )
        response = model.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        raw = extract_json_payload(content)
        if not raw:
            _log.warning("_llm_classify: no valid JSON in response")
            return None
        validated = validate_llm_recommendation(raw, site_url)
        if not validated:
            _log.warning("_llm_classify: validation failed for raw=%s", raw)
            return None
        return Recommendation(
            channel_key=validated["channel_key"],
            entry_type=validated["entry_type"],
            template=validated.get("template"),
            validated=True,
            source="llm",
        )
    except Exception as exc:
        _log.warning("_llm_classify: %s", exc, exc_info=False)
        return None


def classify_site_entry(
    site_url: str,
    entry_type: str | None = None,
    template: str | None = None,
    *,
    use_llm: bool = False,
) -> Recommendation:
    """
    Classify site entry: rule-first, LLM fallback when rules cannot determine.

    When use_llm=False or no LLM key available, falls back to url_pool/domain_root.
    """
    rec = _rule_classify(site_url, entry_type, template)
    if rec is not None:
        return rec

    if use_llm:
        rec = _llm_classify(site_url, entry_type, template)
        if rec is not None:
            return rec

    # Fallback
    return Recommendation(
        channel_key="url_pool",
        entry_type="domain_root",
        template=None,
        validated=False,
        source="fallback",
    )
