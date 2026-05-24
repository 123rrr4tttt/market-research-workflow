"""Site-level policy table for search candidate generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True)
class SiteSearchPolicy:
    category: str
    reason: str
    provider_key: str | None = None
    preferred_search_service: str | None = None
    implementation_hint: str | None = None
    parser_profile: str | None = None


_API_PREFERRED = {
    "arxiv.org": SiteSearchPolicy(
        category="api_preferred",
        reason="Prefer official arXiv API search over HTML search templates.",
        provider_key="arxiv",
        preferred_search_service="official_api",
        implementation_hint="official_access.api",
        parser_profile="official_api",
    ),
    "crossref.org": SiteSearchPolicy(
        category="api_preferred",
        reason="Prefer official Crossref works API search over HTML search templates.",
        provider_key="crossref",
        preferred_search_service="official_api",
        implementation_hint="official_access.api",
        parser_profile="official_api",
    ),
}

_EXTERNAL_PREFERRED = {
    "finextra.com": SiteSearchPolicy(
        category="external_preferred",
        reason="Finextra search endpoint is transport-unstable in the current stack; prefer external site search.",
        preferred_search_service="external_search",
        implementation_hint="external_search_only",
        parser_profile="site_adaptive",
    ),
}

_SOCIAL_SKIP = {
    "reddit.com": SiteSearchPolicy(
        category="social_skip",
        reason="Social platform requires explicit platform/API strategy.",
        preferred_search_service="platform_api",
        implementation_hint="social platform API not enabled",
        parser_profile="platform_api",
    ),
    "x.com": SiteSearchPolicy(
        category="social_skip",
        reason="Social platform requires explicit platform/API strategy.",
        preferred_search_service="platform_api",
        implementation_hint="social platform API not enabled",
        parser_profile="platform_api",
    ),
    "linkedin.com": SiteSearchPolicy(
        category="social_skip",
        reason="Social platform requires explicit platform/API strategy.",
        preferred_search_service="platform_api",
        implementation_hint="social platform API not enabled",
        parser_profile="platform_api",
    ),
    "youtube.com": SiteSearchPolicy(
        category="social_skip",
        reason="Social platform requires explicit platform/API strategy.",
        preferred_search_service="platform_api",
        implementation_hint="social platform API not enabled",
        parser_profile="platform_api",
    ),
}

_DEPRIORITIZED = {
    "news.cn",
    "iyiou.com",
    "stcn.com",
    "hai.stanford.edu",
    "actiontoaction.ai",
    "news.google.com",
    "dcrainmaker.com",
    "thequalityedit.com",
    "cybernews.com",
    "gizmodo.com",
    "supernote.com",
    "androidpolice.com",
    "moorinsightsstrategy.com",
    "cosmopolitan.com",
    "howtogeek.com",
    "theverge.com",
    "laptopmag.com",
    "arstechnica.com",
    "slashgear.com",
}


def _domain_from_url(url: str) -> str:
    try:
        netloc = str(urlparse(str(url or "")).netloc or "").strip().lower()
    except Exception:
        netloc = ""
    return netloc[4:] if netloc.startswith("www.") else netloc


def resolve_site_search_policy(site_url: str) -> SiteSearchPolicy:
    domain = _domain_from_url(site_url)
    if domain in _API_PREFERRED:
        return _API_PREFERRED[domain]
    if domain in _EXTERNAL_PREFERRED:
        return _EXTERNAL_PREFERRED[domain]
    if domain in _SOCIAL_SKIP:
        return _SOCIAL_SKIP[domain]
    if domain in _DEPRIORITIZED:
        return SiteSearchPolicy(
            category="deprioritized",
            reason="Low-yield search template source; deprioritized by policy.",
            preferred_search_service="resilient",
            implementation_hint="search_template_resilient",
            parser_profile="site_adaptive",
        )
    return SiteSearchPolicy(
        category="keep",
        reason="Default keep policy.",
        preferred_search_service="basic",
        implementation_hint="search_template_basic",
        parser_profile="site_adaptive",
    )


def resolve_site_search_policy_for_entry(site_url: str, entry: dict[str, Any] | None) -> SiteSearchPolicy:
    extra = entry.get("extra") if isinstance(entry, dict) else None
    remediation = extra.get("remediation") if isinstance(extra, dict) else None
    if isinstance(remediation, dict):
        status = str(remediation.get("status") or "").strip().lower()
        parser_profile = str(remediation.get("parser_profile") or "").strip() or None
        if status:
            return SiteSearchPolicy(
                category=status,
                reason=str(remediation.get("reason") or remediation.get("strategy") or "entry remediation override"),
                provider_key=str(remediation.get("provider_key") or "").strip() or None,
                preferred_search_service=str(remediation.get("preferred_search_service") or "").strip() or None,
                implementation_hint=str(remediation.get("implementation_hint") or remediation.get("strategy") or "").strip() or None,
                parser_profile=parser_profile,
            )
        if parser_profile:
            base_policy = resolve_site_search_policy(site_url)
            return SiteSearchPolicy(
                category=base_policy.category,
                reason=str(remediation.get("reason") or base_policy.reason or "entry parser profile override"),
                provider_key=str(remediation.get("provider_key") or "").strip() or base_policy.provider_key,
                preferred_search_service=str(remediation.get("preferred_search_service") or "").strip() or base_policy.preferred_search_service,
                implementation_hint=str(remediation.get("implementation_hint") or remediation.get("strategy") or "").strip() or base_policy.implementation_hint,
                parser_profile=parser_profile,
            )
    return resolve_site_search_policy(site_url)
