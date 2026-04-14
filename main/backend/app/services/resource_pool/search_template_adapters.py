"""Domain-aware adapter routing for search_template execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .url_utils import domain_from_url


@dataclass(frozen=True)
class SearchTemplateAdapterPlan:
    adapter_key: str
    execution_mode: str = "search_template"
    parser_profile: str | None = None
    param_overrides: dict[str, Any] | None = None
    reason: str | None = None


_DOC_SEARCH_DOMAINS = {
    "help.openai.com",
    "docs.anthropic.com",
    "cloud.google.com",
    "developer.mozilla.org",
    "docs.github.com",
    "github.com",
}

_WORDPRESS_MEDIA_DOMAINS = {
    "venturebeat.com": SearchTemplateAdapterPlan(
        adapter_key="search_template.wordpress_fastlane",
        parser_profile="site_adaptive",
        param_overrides={
            "max_pages": 1,
            "enable_external_search_fallback": False,
            "enable_external_search_slowlane": False,
        },
        reason="WordPress search source should stay on a single lightweight search page.",
    ),
    "www.serverman.co.uk": SearchTemplateAdapterPlan(
        adapter_key="search_template.wordpress_fastlane",
        parser_profile="site_adaptive",
        param_overrides={
            "max_pages": 1,
            "enable_external_search_fallback": False,
            "enable_external_search_slowlane": False,
        },
        reason="Low-yield WordPress search source should not fan out into generic fallback paths.",
    ),
}

_PARSER_ENHANCED_DOMAINS = {
    "commercialobserver.com": SearchTemplateAdapterPlan(
        adapter_key="search_template.commercialobserver_card",
        parser_profile="site_adaptive.commercialobserver_card",
        param_overrides={
            "max_pages": 1,
            "search_service": "resilient",
            "enable_external_search_fallback": False,
            "enable_external_search_slowlane": False,
        },
        reason="Commercial Observer has a validated card parser and should avoid the generic fallback chain.",
    ),
    "pymnts.com": SearchTemplateAdapterPlan(
        adapter_key="search_template.pymnts_card",
        parser_profile="site_adaptive.pymnts_card",
        param_overrides={
            "max_pages": 1,
            "search_service": "resilient",
            "enable_external_search_fallback": False,
            "enable_external_search_slowlane": False,
        },
        reason="PYMNTS has a validated parser profile and should stay on the parser-enhanced path.",
    ),
}

_QUERY_SEARCH_DOMAINS = {
    "investopedia.com": SearchTemplateAdapterPlan(
        adapter_key="search_template.query_native",
        parser_profile="site_adaptive.investopedia_cards",
        param_overrides={
            "max_pages": 1,
            "enable_external_search_fallback": False,
            "enable_external_search_slowlane": False,
        },
        reason="Investopedia query search should remain on a single native search result page.",
    ),
}


def resolve_search_template_adapter_plan(
    *,
    site_url: str,
    entry_domain: str | None,
    params: dict[str, Any] | None = None,
) -> SearchTemplateAdapterPlan:
    del params
    domain = str(entry_domain or domain_from_url(site_url) or "").strip().lower()
    normalized = domain[4:] if domain.startswith("www.") else domain
    if normalized in _PARSER_ENHANCED_DOMAINS:
        return _PARSER_ENHANCED_DOMAINS[normalized]
    if domain in _WORDPRESS_MEDIA_DOMAINS:
        return _WORDPRESS_MEDIA_DOMAINS[domain]
    if normalized in _QUERY_SEARCH_DOMAINS:
        return _QUERY_SEARCH_DOMAINS[normalized]
    if domain in _DOC_SEARCH_DOMAINS:
        return SearchTemplateAdapterPlan(
            adapter_key="search_template.doc_native",
            parser_profile="site_adaptive",
            param_overrides={
                "max_pages": 1,
                "enable_external_search_fallback": False,
                "enable_external_search_slowlane": False,
            },
            reason="Docs/help search should stay on a single native search page.",
        )
    return SearchTemplateAdapterPlan(
        adapter_key="search_template.generic",
        parser_profile="site_adaptive",
        param_overrides={"max_pages": 1},
        reason="Default generic search_template adapter.",
    )


def apply_search_template_adapter_plan(
    *,
    plan: SearchTemplateAdapterPlan,
    params: dict[str, Any] | None,
) -> dict[str, Any]:
    routed = dict(params or {})
    if plan.param_overrides:
        for key, value in plan.param_overrides.items():
            routed[key] = value
    existing_parser_profile = str(routed.get("parser_profile") or "").strip()
    if plan.parser_profile and (
        not existing_parser_profile
        or existing_parser_profile == "site_adaptive"
    ):
        routed["parser_profile"] = plan.parser_profile
    return routed
