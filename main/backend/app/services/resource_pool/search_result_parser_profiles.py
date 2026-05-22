"""Search-result parser profile registry for site-search candidate extraction."""

from __future__ import annotations

from dataclasses import dataclass
import re

DEFAULT_CONTAINER_SELECTORS = (
    "article",
    "[role='article']",
    ".search-result",
    ".search-results .search-result",
    ".search-results .result-item",
    ".search-results li",
    ".search-results article",
    ".results article",
    ".results li",
    ".result",
    "[class*='search-item']",
    "[class*='result-item']",
    "[class*='news-item']",
    "[class*='teaser']",
    ".story",
    ".post",
    ".entry-item",
    ".list-item",
    ".content",
    "main li",
    "main article",
)

DEFAULT_STRUCTURED_RESULT_URL_ATTRIBUTES = (
    "data-url",
    "data-href",
    "data-link",
    "data-permalink",
    "data-url-path",
)

DEFAULT_TITLE_SELECTORS = (
    "h1",
    "h2",
    "h3",
    "[role='heading']",
    ".entry-title",
    ".post-title",
    ".story-title",
    ".headline",
    ".title",
    "[class*='title']",
)

DEFAULT_SUMMARY_SELECTORS = (
    ".excerpt",
    ".summary",
    ".dek",
    ".intro",
    ".description",
    ".lead",
    ".teaser__desc",
    "[data-role='description']",
    "p",
    "span.description",
)

DEFAULT_LOW_VALUE_ANCHOR_TEXTS = {
    "read more",
    "continue reading",
    "continue",
    "more",
    "learn more",
    "view more",
    "details",
}

DEFAULT_LOW_VALUE_HREF_MARKERS = (
    "/login",
    "/signin",
    "/sign-in",
    "/signup",
    "/register",
    "/account",
    "/pricing",
    "/privacy",
    "/terms",
    "/cookie",
    "/about",
    "/contact",
    "/newsletter",
    "/subscribe",
    "/advertis",
    "/careers",
    "/jobs",
    "/authors",
    "/author/",
    "/tag/",
    "/tags/",
    "/category/",
    "/categories/",
    "/search",
    "/wp-json",
)

DEFAULT_LOW_VALUE_HOST_MARKERS = (
    "facebook.com",
    "instagram.com",
    "x.com",
    "twitter.com",
    "linkedin.com",
    "youtube.com",
    "tiktok.com",
    "pinterest.com",
    "discord.com",
)
DEFAULT_LOW_VALUE_PATH_SUFFIXES = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".avif",
)

DEFAULT_GLOBAL_ANCHOR_MIN_TEXT_LENGTH = 8
COMMERCIAL_OBSERVER_ARTICLE_PATH = re.compile(r"/20\d{2}/\d{2}/")

@dataclass(frozen=True)
class SearchResultParserProfile:
    profile_key: str
    entry_domain: str
    module_chain: tuple[str, ...]
    container_selectors: tuple[str, ...]
    title_link_selectors: tuple[str, ...]
    title_selectors: tuple[str, ...]
    summary_selectors: tuple[str, ...]
    structured_result_url_attributes: tuple[str, ...]
    low_value_anchor_texts: frozenset[str]
    low_value_href_markers: tuple[str, ...]
    low_value_host_markers: tuple[str, ...]
    low_value_path_suffixes: tuple[str, ...]
    global_anchor_min_text_length: int
    article_path_pattern: re.Pattern[str] | None = None
    route_rules: tuple[tuple[re.Pattern[str], str], ...] = ()
    default_route_kind: str = "page"


@dataclass(frozen=True)
class ParserProfileCapability:
    requested_profile: str
    resolved_profile: str
    status: str
    reason: str
    review_required: bool = False


_GENERIC_PROFILE_KEYS = {"", "default", "site_adaptive"}
_REVIEW_PROFILE_ALIASES = {
    "anchor_only": "fallback_anchor_only",
    "fallback_anchor_only": "fallback_anchor_only",
}
_KNOWN_PROFILE_ALIASES = {
    "site_adaptive.commercialobserver_card",
    "commercialobserver.card",
    "site_adaptive.pymnts_card",
    "pymnts.card",
    "site_adaptive.investopedia_cards",
    "investopedia.cards",
    "site_adaptive.hai_research_shell",
    "hai.research_shell",
}


def _base_profile(*, profile_key: str, entry_domain: str) -> SearchResultParserProfile:
    return SearchResultParserProfile(
        profile_key=profile_key,
        entry_domain=entry_domain,
        module_chain=("container", "structured", "jsonld", "global_anchor"),
        container_selectors=DEFAULT_CONTAINER_SELECTORS,
        title_link_selectors=(),
        title_selectors=DEFAULT_TITLE_SELECTORS,
        summary_selectors=DEFAULT_SUMMARY_SELECTORS,
        structured_result_url_attributes=DEFAULT_STRUCTURED_RESULT_URL_ATTRIBUTES,
        low_value_anchor_texts=frozenset(DEFAULT_LOW_VALUE_ANCHOR_TEXTS),
        low_value_href_markers=DEFAULT_LOW_VALUE_HREF_MARKERS,
        low_value_host_markers=DEFAULT_LOW_VALUE_HOST_MARKERS,
        low_value_path_suffixes=DEFAULT_LOW_VALUE_PATH_SUFFIXES,
        global_anchor_min_text_length=DEFAULT_GLOBAL_ANCHOR_MIN_TEXT_LENGTH,
        route_rules=(),
        default_route_kind="page",
    )


def _commercialobserver_profile(entry_domain: str) -> SearchResultParserProfile:
    base = _base_profile(
        profile_key="site_adaptive.commercialobserver_card",
        entry_domain=entry_domain,
    )
    return SearchResultParserProfile(
        profile_key=base.profile_key,
        entry_domain=base.entry_domain,
        module_chain=base.module_chain,
        container_selectors=(
            ".card-text",
            ".large-card.card",
            ".large-card-wrapper.card-wrap.rest-item",
            *base.container_selectors,
        ),
        title_link_selectors=("h2 a[href]", "h3 a[href]"),
        title_selectors=base.title_selectors,
        summary_selectors=base.summary_selectors,
        structured_result_url_attributes=base.structured_result_url_attributes,
        low_value_anchor_texts=base.low_value_anchor_texts,
        low_value_href_markers=base.low_value_href_markers,
        low_value_host_markers=base.low_value_host_markers,
        low_value_path_suffixes=base.low_value_path_suffixes,
        global_anchor_min_text_length=base.global_anchor_min_text_length,
        article_path_pattern=COMMERCIAL_OBSERVER_ARTICLE_PATH,
        route_rules=((COMMERCIAL_OBSERVER_ARTICLE_PATH, "article"),),
        default_route_kind="page",
    )


def _pymnts_profile(entry_domain: str) -> SearchResultParserProfile:
    base = _base_profile(
        profile_key="site_adaptive.pymnts_card",
        entry_domain=entry_domain,
    )
    return SearchResultParserProfile(
        profile_key=base.profile_key,
        entry_domain=base.entry_domain,
        module_chain=base.module_chain,
        container_selectors=base.container_selectors,
        title_link_selectors=base.title_link_selectors,
        title_selectors=base.title_selectors,
        summary_selectors=base.summary_selectors,
        structured_result_url_attributes=base.structured_result_url_attributes,
        low_value_anchor_texts=base.low_value_anchor_texts,
        low_value_href_markers=base.low_value_href_markers,
        low_value_host_markers=base.low_value_host_markers,
        low_value_path_suffixes=base.low_value_path_suffixes,
        global_anchor_min_text_length=base.global_anchor_min_text_length,
        article_path_pattern=None,
        route_rules=(
            (re.compile(r"^/topic/"), "section"),
            (re.compile(r"^/(?:tracker|trendscapes|study/|pymnts-intelligence)"), "collection"),
            (re.compile(r"^/news/"), "article"),
        ),
        default_route_kind="page",
    )


def _investopedia_profile(entry_domain: str) -> SearchResultParserProfile:
    base = _base_profile(
        profile_key="site_adaptive.investopedia_cards",
        entry_domain=entry_domain,
    )
    return SearchResultParserProfile(
        profile_key=base.profile_key,
        entry_domain=base.entry_domain,
        module_chain=("container", "global_anchor"),
        container_selectors=(
            ".mntl-document-card",
            ".mntl-universal-card",
            ".mntl-search-results__list .mntl-document-card",
            ".mntl-search-results__list .mntl-universal-card",
            *base.container_selectors,
        ),
        title_link_selectors=("a[href]",),
        title_selectors=base.title_selectors,
        summary_selectors=base.summary_selectors,
        structured_result_url_attributes=base.structured_result_url_attributes,
        low_value_anchor_texts=base.low_value_anchor_texts,
        low_value_href_markers=(
            *base.low_value_href_markers,
            "/simulator",
        ),
        low_value_host_markers=base.low_value_host_markers,
        low_value_path_suffixes=base.low_value_path_suffixes,
        global_anchor_min_text_length=base.global_anchor_min_text_length,
        article_path_pattern=None,
        route_rules=(),
        default_route_kind="article",
    )


def _hai_stanford_profile(entry_domain: str) -> SearchResultParserProfile:
    base = _base_profile(
        profile_key="site_adaptive.hai_research_shell",
        entry_domain=entry_domain,
    )
    return SearchResultParserProfile(
        profile_key=base.profile_key,
        entry_domain=base.entry_domain,
        module_chain=("global_anchor",),
        container_selectors=base.container_selectors,
        title_link_selectors=base.title_link_selectors,
        title_selectors=base.title_selectors,
        summary_selectors=base.summary_selectors,
        structured_result_url_attributes=base.structured_result_url_attributes,
        low_value_anchor_texts=base.low_value_anchor_texts,
        low_value_href_markers=(
            *base.low_value_href_markers,
            "/research/partners",
            "/education/",
            "/policy/policymaker-education",
            "/policy/student-opportunities",
            "/site/accessibility",
            "/security/copyright-infringement",
            "/nonacademicregulations/",
        ),
        low_value_host_markers=(
            *base.low_value_host_markers,
            "bsky.app",
            "uit.stanford.edu",
            "adminguide.stanford.edu",
            "exploredegrees.stanford.edu",
            "www.stanford.edu",
        ),
        low_value_path_suffixes=base.low_value_path_suffixes,
        global_anchor_min_text_length=base.global_anchor_min_text_length,
        article_path_pattern=None,
        route_rules=(
            (re.compile(r"^/ai-index/"), "research_tool"),
            (re.compile(r"^/(?:research/publications|policy/publications)"), "publication_hub"),
            (re.compile(r"^/news/"), "article"),
            (re.compile(r"^/events/"), "event"),
            (re.compile(r"^/(?:research/|policy/|education/)"), "section"),
        ),
        default_route_kind="page",
    )


def _anchor_only_profile(entry_domain: str) -> SearchResultParserProfile:
    base = _base_profile(profile_key="fallback_anchor_only", entry_domain=entry_domain)
    return SearchResultParserProfile(
        profile_key=base.profile_key,
        entry_domain=base.entry_domain,
        module_chain=("global_anchor",),
        container_selectors=base.container_selectors,
        title_link_selectors=base.title_link_selectors,
        title_selectors=base.title_selectors,
        summary_selectors=base.summary_selectors,
        structured_result_url_attributes=base.structured_result_url_attributes,
        low_value_anchor_texts=base.low_value_anchor_texts,
        low_value_href_markers=base.low_value_href_markers,
        low_value_host_markers=base.low_value_host_markers,
        low_value_path_suffixes=base.low_value_path_suffixes,
        global_anchor_min_text_length=base.global_anchor_min_text_length,
        route_rules=base.route_rules,
        default_route_kind=base.default_route_kind,
    )


def build_search_result_parser_profile(
    entry_domain: str | None,
    *,
    parser_profile: str | None = None,
) -> SearchResultParserProfile:
    domain = (entry_domain or "").strip().lower()
    requested = str(parser_profile or "").strip().lower()

    if domain == "commercialobserver.com":
        return _commercialobserver_profile(domain)
    if domain == "www.pymnts.com":
        return _pymnts_profile(domain)
    if domain == "www.investopedia.com":
        return _investopedia_profile(domain)
    if domain == "hai.stanford.edu":
        return _hai_stanford_profile(domain)
    if requested in {"fallback_anchor_only", "anchor_only"}:
        return _anchor_only_profile(domain)
    if requested in {"site_adaptive.commercialobserver_card", "commercialobserver.card"}:
        return _commercialobserver_profile(domain)
    if requested in {"site_adaptive.pymnts_card", "pymnts.card"}:
        return _pymnts_profile(domain)
    if requested in {"site_adaptive.investopedia_cards", "investopedia.cards"}:
        return _investopedia_profile(domain)
    if requested in {"site_adaptive.hai_research_shell", "hai.research_shell"}:
        return _hai_stanford_profile(domain)
    if requested in {"default", "site_adaptive", ""}:
        return _base_profile(profile_key=requested or "default", entry_domain=domain)
    return _base_profile(profile_key=requested, entry_domain=domain)


def resolve_parser_profile_capability(
    entry_domain: str | None,
    *,
    parser_profile: str | None = None,
    default_profile: str | None = None,
) -> ParserProfileCapability:
    domain = (entry_domain or "").strip().lower()
    requested = str(parser_profile or "").strip().lower()
    fallback = str(default_profile or "").strip().lower()
    effective = requested or fallback or "site_adaptive"

    if effective in _REVIEW_PROFILE_ALIASES:
        resolved = _REVIEW_PROFILE_ALIASES[effective]
        return ParserProfileCapability(
            requested_profile=requested,
            resolved_profile=resolved,
            status="review",
            reason="low_confidence_anchor_only_profile",
            review_required=True,
        )

    if effective in _GENERIC_PROFILE_KEYS:
        resolved = build_search_result_parser_profile(domain, parser_profile=effective).profile_key
        return ParserProfileCapability(
            requested_profile=requested,
            resolved_profile=resolved,
            status="allow",
            reason="known_generic_or_domain_profile",
        )

    if effective in _KNOWN_PROFILE_ALIASES:
        resolved = build_search_result_parser_profile(domain, parser_profile=effective).profile_key
        return ParserProfileCapability(
            requested_profile=requested,
            resolved_profile=resolved,
            status="allow",
            reason="known_parser_profile",
        )

    downgraded_to = (
        fallback
        if fallback in _KNOWN_PROFILE_ALIASES or fallback in _GENERIC_PROFILE_KEYS
        else "site_adaptive"
    )
    resolved = build_search_result_parser_profile(domain, parser_profile=downgraded_to).profile_key
    return ParserProfileCapability(
        requested_profile=requested,
        resolved_profile=resolved,
        status="downgrade",
        reason="unknown_parser_profile_downgraded",
    )
