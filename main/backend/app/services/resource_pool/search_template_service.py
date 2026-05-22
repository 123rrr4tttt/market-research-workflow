"""Shared source-capability execution helpers used by adapters and unified search."""

from __future__ import annotations

from dataclasses import dataclass, field
import gzip
import json
import re
import time
from typing import Any
from urllib.parse import parse_qs, parse_qsl, urlencode, urljoin, urlsplit, urlunsplit, unquote
import xml.etree.ElementTree as ET

from ..ingest.adapters.http_utils import HttpFetchError, fetch_html, make_html_parser
from ..ingest.source_search_contract import build_query_url_from_contract, normalize_source_search_contract
from .search_result_parser_service import parse_search_result_candidates
from .search_capabilities import SearchCapabilityScore, make_search_candidate, select_search_candidates
from .url_utils import domain_from_url, normalize_url

_TRACKING_QUERY_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "utm_name",
    "utm_reader",
    "utm_referrer",
    "utm_social",
    "utm_social-type",
    "gclid",
    "fbclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "mkt_tok",
    "ref",
    "ref_src",
    "spm",
}

_ENCODED_Q_PLACEHOLDER = re.compile(r"%7B%7Bq%7D%7D", re.IGNORECASE)
_ENCODED_PAGE_PLACEHOLDER = re.compile(r"%7B%7Bpage%7D%7D", re.IGNORECASE)
_RESILIENT_SEARCH_MARKERS = ("403", "429", "Failed to fetch", "blocked", "rate limit")
_SEARCH_RESULT_CONTAINER_SELECTORS = (
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
_STRUCTURED_RESULT_URL_ATTRIBUTES = (
    "data-url",
    "data-href",
    "data-link",
    "data-permalink",
    "data-url-path",
)
_TITLE_SELECTORS = (
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
_SUMMARY_SELECTORS = (
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
_LOW_VALUE_ANCHOR_TEXTS = {
    "read more",
    "continue reading",
    "continue",
    "more",
    "learn more",
    "view more",
    "details",
}
_GLOBAL_ANCHOR_MIN_TEXT_LENGTH = 8
_COMMERCIAL_OBSERVER_ARTICLE_PATH = re.compile(r"/20\d{2}/\d{2}/")
_SITE_SPECIFIC_CONTAINER_SELECTORS: dict[str, tuple[str, ...]] = {
    "commercialobserver.com": (
        ".card-text",
        ".large-card.card",
        ".large-card-wrapper.card-wrap.rest-item",
    ),
}
_SITE_SPECIFIC_TITLE_LINK_SELECTORS: dict[str, tuple[str, ...]] = {
    "commercialobserver.com": (
        "h2 a[href]",
        "h3 a[href]",
    ),
}
_LOW_VALUE_HREF_MARKERS = (
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
_LOW_VALUE_HOST_MARKERS = (
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


@dataclass(frozen=True)
class SearchTemplateRawCandidate:
    url: str
    text: str = ""
    title: str = ""
    summary: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchTemplateExecutionResult:
    template: str
    search_urls: list[str]
    pages_scanned: int
    raw_candidates: list[SearchTemplateRawCandidate]
    selected_candidates: list[SearchCapabilityScore]
    used_term_fallback: bool
    errors: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


def _resolve_search_service(params: dict[str, Any]) -> str:
    service = str(params.get("search_service") or "basic").strip().lower()
    return service if service in {"basic", "resilient"} else "basic"


def _search_service_retries(service: str) -> int:
    return 2 if service == "resilient" else 1


def _fallback_search_service(error: Exception | str, current_service: str, *, enabled: bool) -> str | None:
    if not enabled or current_service != "basic":
        return None
    message = str(error or "")
    if any(marker.lower() in message.lower() for marker in _RESILIENT_SEARCH_MARKERS):
        return "resilient"
    return None


def normalize_search_template_placeholders(template: str | None) -> str:
    tpl = str(template or "").strip()
    if not tpl:
        return ""
    tpl = _ENCODED_Q_PLACEHOLDER.sub("{{q}}", tpl)
    tpl = _ENCODED_PAGE_PLACEHOLDER.sub("{{page}}", tpl)
    return tpl


def resolve_search_template_pagination(params: dict[str, Any]) -> tuple[int, int]:
    def _parse_int(value: Any, default: int, *, min_value: int, max_value: int) -> int:
        try:
            parsed = int(value)
        except Exception:
            parsed = int(default)
        return max(min_value, min(max_value, parsed))

    start_page = _parse_int(params.get("page"), 1, min_value=1, max_value=10000)
    max_pages = _parse_int(params.get("max_pages"), 1, min_value=1, max_value=50)
    return start_page, max_pages


def normalize_candidate_url(url: str) -> str | None:
    norm = normalize_url(url)
    if not norm:
        return None
    try:
        parts = urlsplit(norm)
        if "duckduckgo.com" in parts.netloc.lower():
            uddg = parse_qs(parts.query).get("uddg") or []
            if uddg:
                redirected = normalize_url(unquote(str(uddg[0] or "").strip()))
                if redirected:
                    return redirected
        query = urlencode(
            [(k, v) for (k, v) in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in _TRACKING_QUERY_KEYS],
            doseq=True,
        )
        cleaned = urlunsplit((parts.scheme, parts.netloc, parts.path or "/", query, ""))
        return normalize_url(cleaned) or norm
    except Exception:
        return norm


def extract_link_candidates_from_html(
    html: str,
    *,
    base_url: str,
    entry_domain: str | None = None,
    parser_profile: str | None = None,
) -> list[SearchTemplateRawCandidate]:
    return extract_link_candidates_with_diagnostics_from_html(
        html,
        base_url=base_url,
        entry_domain=entry_domain,
        parser_profile=parser_profile,
    )[0]


def extract_link_candidates_with_diagnostics_from_html(
    html: str,
    *,
    base_url: str,
    entry_domain: str | None = None,
    parser_profile: str | None = None,
) -> tuple[list[SearchTemplateRawCandidate], dict[str, Any]]:
    raw_candidates, diagnostics = parse_search_result_candidates(
        html,
        base_url=base_url,
        entry_domain=entry_domain,
        parser_profile=parser_profile,
    )
    return (
        [
            SearchTemplateRawCandidate(
                url=str(item.get("url") or "").strip(),
                text=str(item.get("text") or "").strip(),
                title=str(item.get("title") or "").strip(),
                summary=str(item.get("summary") or "").strip(),
                extra=dict(item.get("extra") or {}) if isinstance(item.get("extra"), dict) else {},
            )
            for item in raw_candidates
            if str(item.get("url") or "").strip()
        ],
        diagnostics,
    )


def _candidate_from_anchor(
    node: Any,
    *,
    base_url: str,
    context_text: str,
    container: Any | None,
    entry_domain: str | None,
) -> SearchTemplateRawCandidate | None:
    href = (node.attributes.get("href") or "").strip()
    if not href:
        return None
    candidate_url = normalize_candidate_url(urljoin(base_url, href))
    if not candidate_url or _is_low_value_candidate_href(candidate_url, entry_domain=entry_domain):
        return None
    anchor_text = _node_text(node, max_chars=240)
    title = str(node.attributes.get("title") or node.attributes.get("aria-label") or "").strip()
    if not title and container is not None:
        title = _extract_container_title(container)
    if not title:
        title = anchor_text
    normalized_anchor_text = " ".join(anchor_text.lower().split())
    if normalized_anchor_text in _LOW_VALUE_ANCHOR_TEXTS and title:
        anchor_text = title
    summary = _extract_container_summary(container) if container is not None else ""
    text = " ".join(part for part in [anchor_text, summary, context_text] if part).strip()
    return SearchTemplateRawCandidate(
        url=candidate_url,
        text=text[:800],
        title=title[:240],
        summary=summary[:400],
    )


def _node_text(node: Any, *, max_chars: int) -> str:
    try:
        text = str(node.text(separator=" ", strip=True) or "").strip()
    except Exception:
        text = ""
    text = " ".join(text.split())
    return text[:max_chars]


def _is_low_value_candidate_href(url: str, *, entry_domain: str | None = None) -> bool:
    parts = urlsplit(str(url or "").strip())
    host = str(parts.netloc or "").lower()
    path = str(parts.path or "").lower()
    if any(marker in host for marker in _LOW_VALUE_HOST_MARKERS):
        return True
    if any(marker in path for marker in _LOW_VALUE_HREF_MARKERS):
        return True
    if path in {"", "/"}:
        return True
    if (entry_domain or "").strip().lower() == "commercialobserver.com" and not _COMMERCIAL_OBSERVER_ARTICLE_PATH.search(path):
        return True
    return False


def _append_structured_candidates(
    parser: Any,
    *,
    base_url: str,
    entry_domain: str | None,
    candidates: list[SearchTemplateRawCandidate],
    seen_urls: set[str],
    diagnostics: dict[str, int],
) -> None:
    for selector in _SEARCH_RESULT_CONTAINER_SELECTORS:
        found = parser.css(selector)
        if not found:
            continue
        for container in found[:20]:
            container_text = _node_text(container, max_chars=600)
            for attr_name in _STRUCTURED_RESULT_URL_ATTRIBUTES:
                raw_url = str(container.attributes.get(attr_name) or "").strip()
                if not raw_url:
                    continue
                candidate_url = normalize_candidate_url(urljoin(base_url, raw_url))
                if not candidate_url or candidate_url in seen_urls or _is_low_value_candidate_href(candidate_url, entry_domain=entry_domain):
                    diagnostics["candidate_rejected_low_value"] += 1
                    continue
                title = _extract_container_title(container)
                summary = _extract_container_summary(container)
                seen_urls.add(candidate_url)
                candidates.append(
                    SearchTemplateRawCandidate(
                        url=candidate_url,
                        text=" ".join(part for part in [title, summary, container_text] if part)[:800],
                        title=title[:240],
                        summary=summary[:400],
                    )
                )
                diagnostics["structured_hit"] += 1


def _append_json_ld_candidates(
    parser: Any,
    *,
    base_url: str,
    entry_domain: str | None,
    candidates: list[SearchTemplateRawCandidate],
    seen_urls: set[str],
    diagnostics: dict[str, int],
) -> None:
    for node in parser.css("script[type='application/ld+json']"):
        raw = _node_text(node, max_chars=20000)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        for item in _iter_json_ld_items(payload):
            candidate = _candidate_from_json_ld_item(item, base_url=base_url, entry_domain=entry_domain)
            if candidate is None or candidate.url in seen_urls:
                continue
            seen_urls.add(candidate.url)
            candidates.append(candidate)
            diagnostics["json_ld_hit"] += 1


def _append_global_anchor_candidates(
    parser: Any,
    *,
    base_url: str,
    entry_domain: str | None,
    candidates: list[SearchTemplateRawCandidate],
    seen_urls: set[str],
    diagnostics: dict[str, int],
) -> None:
    for node in parser.css("a"):
        candidate = _candidate_from_anchor(
            node,
            base_url=base_url,
            context_text="",
            container=None,
            entry_domain=entry_domain,
        )
        if candidate is None:
            diagnostics["candidate_rejected_low_value"] += 1
            continue
        if candidate.url in seen_urls or not _is_high_signal_global_anchor(candidate):
            continue
        seen_urls.add(candidate.url)
        candidates.append(candidate)
        diagnostics["global_anchor_hit"] += 1


def _iter_json_ld_items(payload: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    def _visit(value: Any) -> None:
        if isinstance(value, dict):
            items.append(value)
            for key in ("@graph", "itemListElement", "mainEntity", "mainEntityOfPage"):
                child = value.get(key)
                if isinstance(child, list):
                    for row in child:
                        _visit(row)
                elif child is not None:
                    _visit(child)
        elif isinstance(value, list):
            for row in value:
                _visit(row)

    _visit(payload)
    return items


def _candidate_from_json_ld_item(
    item: dict[str, Any],
    *,
    base_url: str,
    entry_domain: str | None,
) -> SearchTemplateRawCandidate | None:
    raw_url = item.get("url") or item.get("@id")
    child_item = item.get("item")
    if not raw_url and isinstance(child_item, dict):
        raw_url = child_item.get("url") or child_item.get("@id")
    main_entity_of_page = item.get("mainEntityOfPage")
    if not raw_url and isinstance(main_entity_of_page, dict):
        raw_url = main_entity_of_page.get("@id") or main_entity_of_page.get("url")
    raw_url = str(raw_url or "").strip()
    if not raw_url:
        return None
    candidate_url = normalize_candidate_url(urljoin(base_url, raw_url))
    if not candidate_url or _is_low_value_candidate_href(candidate_url, entry_domain=entry_domain):
        return None
    title = str(item.get("headline") or item.get("name") or "").strip()
    if not title and isinstance(child_item, dict):
        title = str(child_item.get("name") or child_item.get("headline") or "").strip()
    text = str(item.get("description") or "").strip()
    if not text and isinstance(child_item, dict):
        text = str(child_item.get("description") or child_item.get("summary") or "").strip()
    return SearchTemplateRawCandidate(
        url=candidate_url,
        text=text[:800],
        title=title[:240],
        summary=text[:400],
    )


def _extract_container_title(container: Any) -> str:
    for selector in _TITLE_SELECTORS:
        try:
            title_nodes = container.css(selector)
        except Exception:
            title_nodes = []
        if title_nodes:
            title = _node_text(title_nodes[0], max_chars=240)
            if title:
                return title
    return ""


def _extract_container_summary(container: Any) -> str:
    for selector in _SUMMARY_SELECTORS:
        try:
            nodes = container.css(selector)
        except Exception:
            nodes = []
        for node in nodes:
            text = _node_text(node, max_chars=400)
            normalized = " ".join(text.lower().split())
            if text and normalized not in _LOW_VALUE_ANCHOR_TEXTS:
                return text
    return ""


def _is_high_signal_global_anchor(candidate: SearchTemplateRawCandidate) -> bool:
    text = " ".join((candidate.title or candidate.text or "").split()).strip()
    if len(text) < _GLOBAL_ANCHOR_MIN_TEXT_LENGTH:
        return False
    parts = urlsplit(candidate.url)
    if parts.scheme not in {"http", "https"}:
        return False
    path = str(parts.path or "").strip("/")
    if path.count("/") < 1:
        return False
    return True


def _iter_container_anchor_nodes(container: Any, *, entry_domain: str) -> list[Any]:
    selected: list[Any] = []
    seen_ids: set[int] = set()
    for selector in _SITE_SPECIFIC_TITLE_LINK_SELECTORS.get(entry_domain, ()):
        try:
            nodes = container.css(selector)
        except Exception:
            nodes = []
        for node in nodes:
            marker = id(node)
            if marker in seen_ids:
                continue
            seen_ids.add(marker)
            selected.append(node)
    try:
        generic_nodes = container.css("a")
    except Exception:
        generic_nodes = []
    for node in generic_nodes:
        marker = id(node)
        if marker in seen_ids:
            continue
        seen_ids.add(marker)
        selected.append(node)
    return selected


def _resolve_candidate_scoring_config(params: dict[str, Any] | None) -> dict[str, Any] | str | None:
    if not isinstance(params, dict):
        return None
    return params.get("candidate_scoring_config") or params.get("candidate_selection_config")


def _candidate_filter_state(
    *,
    raw_count: int,
    selected_count: int,
    query_terms: list[str],
    allow_term_fallback: bool,
    used_term_fallback: bool,
) -> str:
    if raw_count <= 0:
        return "empty_no_raw_candidates"
    if used_term_fallback:
        return "term_filter_empty_fallback_used" if allow_term_fallback else "term_filter_empty_no_fallback"
    if selected_count > 0:
        return "selected"
    if query_terms:
        return "term_filter_empty_no_fallback"
    return "selected_without_query_filter" if selected_count > 0 else "empty_without_query_filter"


def build_search_template_urls(template: str, query_terms: list[str], params: dict[str, Any]) -> tuple[list[str], int]:
    normalized_template = normalize_search_template_placeholders(template)
    if not normalized_template or "{{q}}" not in normalized_template:
        raise ValueError("search_template requires template containing {{q}}")
    start_page, max_pages = resolve_search_template_pagination(params)
    contract = normalize_source_search_contract(
        normalized_template,
        {
            "page": start_page,
            "page_size": params.get("page_size"),
            "sort": params.get("sort"),
            "lang": params.get("lang"),
            "region": params.get("region"),
        },
    )
    search_urls: list[str] = []
    for offset in range(max_pages):
        page_contract = dict(contract or {})
        page_contract["page"] = start_page + offset
        search_url = build_query_url_from_contract(normalized_template, query_terms, page_contract)
        if search_url and search_url not in search_urls:
            search_urls.append(search_url)
    return search_urls, len(search_urls)


def execute_search_template(
    *,
    template: str,
    query_terms: list[str],
    params: dict[str, Any],
    probe_timeout: float,
    allow_term_fallback: bool,
    entry_domain: str | None = None,
) -> SearchTemplateExecutionResult:
    normalized_template = normalize_search_template_placeholders(template)
    search_urls, pages_scanned = build_search_template_urls(normalized_template, query_terms, params)
    merged_candidates: list[SearchTemplateRawCandidate] = []
    seen_urls: set[str] = set()
    errors: list[dict[str, Any]] = []
    effective_domain = (entry_domain or domain_from_url(normalized_template) or "").strip().lower()
    active_service = _resolve_search_service(params)
    fallback_enabled = bool(params.get("enable_search_service_fallback", True))
    search_service_fallbacks = 0
    parser_diagnostics_acc: dict[str, int] = {}

    for search_url in search_urls:
        try:
            html, _ = fetch_html(search_url, timeout=probe_timeout, retries=_search_service_retries(active_service))
        except HttpFetchError as exc:
            fallback_service = _fallback_search_service(exc, active_service, enabled=fallback_enabled)
            if fallback_service is not None:
                try:
                    html, _ = fetch_html(search_url, timeout=probe_timeout, retries=_search_service_retries(fallback_service))
                    search_service_fallbacks += 1
                    active_service = fallback_service
                except Exception:
                    errors.append(
                        {
                            "site_url": normalized_template,
                            "search_url": search_url,
                            "error": str(exc),
                            "error_class": "transport_failure",
                            "recommended_search_service": fallback_service,
                        }
                    )
                    continue
            else:
                errors.append(
                    {
                        "site_url": normalized_template,
                        "search_url": search_url,
                        "error": str(exc),
                        "error_class": "transport_failure",
                        "recommended_search_service": _fallback_search_service(exc, active_service, enabled=True),
                    }
                )
                continue
        except Exception as exc:  # noqa: BLE001
            fallback_service = _fallback_search_service(exc, active_service, enabled=fallback_enabled)
            if fallback_service is not None:
                try:
                    html, _ = fetch_html(search_url, timeout=probe_timeout, retries=_search_service_retries(fallback_service))
                    search_service_fallbacks += 1
                    active_service = fallback_service
                except Exception:
                    errors.append(
                        {
                            "site_url": normalized_template,
                            "search_url": search_url,
                            "error": str(exc),
                            "error_class": "unexpected_failure",
                            "recommended_search_service": fallback_service,
                        }
                    )
                    continue
            else:
                errors.append(
                    {
                        "site_url": normalized_template,
                        "search_url": search_url,
                        "error": str(exc),
                        "error_class": "unexpected_failure",
                        "recommended_search_service": _fallback_search_service(exc, active_service, enabled=True),
                    }
                )
                continue
        extracted_candidates, extracted_diagnostics = extract_link_candidates_with_diagnostics_from_html(
            html,
            base_url=search_url,
            entry_domain=effective_domain,
            parser_profile=str(params.get("parser_profile") or "").strip() or None,
        )
        for key, value in extracted_diagnostics.items():
            diagnostics_key = f"parser_{key}"
            if isinstance(value, int):
                parser_diagnostics_acc[diagnostics_key] = int(parser_diagnostics_acc.get(diagnostics_key) or 0) + int(value or 0)
            else:
                parser_diagnostics_acc[diagnostics_key] = value
        for candidate in extracted_candidates:
            if candidate.url in seen_urls:
                continue
            seen_urls.add(candidate.url)
            merged_candidates.append(candidate)

    scored = [
        candidate
        for candidate in (
            make_search_candidate(
                url=item.url,
                strategy="search_template",
                title=item.title,
                text=item.text,
                summary=item.summary,
                source_url=search_urls[0] if search_urls else normalized_template,
                entry_domain=effective_domain,
                extra=item.extra,
            )
            for item in merged_candidates
        )
        if candidate is not None
    ]
    selected_candidates, used_term_fallback = select_search_candidates(
        scored,
        query_terms,
        strategy="search_template",
        entry_domain=effective_domain,
        search_url=search_urls[0] if search_urls else normalized_template,
        allow_fallback=allow_term_fallback,
        fallback_limit=int(params.get("fallback_limit") or 30),
        scoring_config=_resolve_candidate_scoring_config(params),
    )

    diagnostics = {
        "entry_domain": effective_domain,
        "raw_candidates": len(merged_candidates),
        "selected_candidates": len(selected_candidates),
        "transport_errors": sum(1 for row in errors if row.get("error_class") == "transport_failure"),
        "pages_scanned": pages_scanned,
        "search_service": active_service,
        "search_service_fallbacks": search_service_fallbacks,
        "fallback_allowed": bool(allow_term_fallback),
        "used_term_fallback": bool(used_term_fallback),
        "candidate_filter_state": _candidate_filter_state(
            raw_count=len(merged_candidates),
            selected_count=len(selected_candidates),
            query_terms=query_terms,
            allow_term_fallback=allow_term_fallback,
            used_term_fallback=used_term_fallback,
        ),
    }
    diagnostics.update(parser_diagnostics_acc)
    return SearchTemplateExecutionResult(
        template=normalized_template,
        search_urls=search_urls,
        pages_scanned=pages_scanned,
        raw_candidates=merged_candidates,
        selected_candidates=list(selected_candidates),
        used_term_fallback=used_term_fallback,
        errors=errors,
        diagnostics=diagnostics,
    )


def execute_external_site_search(
    *,
    entry_domain: str,
    query_terms: list[str],
    probe_timeout: float,
    allow_term_fallback: bool,
    params: dict[str, Any] | None = None,
) -> SearchTemplateExecutionResult:
    params = dict(params or {})
    if not entry_domain:
        raise ValueError("entry_domain is required for external site search")
    search_query = " ".join([f"site:{entry_domain}", *[term for term in query_terms if term]])
    search_url = f"external_search:{search_query}"
    raw_candidates: list[SearchTemplateRawCandidate] = []
    errors: list[dict[str, Any]] = []
    slowlane_used = False
    try:
        from ..search.web import search_sources

        provider = str(params.get("external_search_provider") or "auto").strip().lower() or "auto"
        results = search_sources(
            search_query,
            language=str(params.get("external_search_language") or "en"),
            max_results=max(1, int(params.get("external_search_limit") or 10)),
            provider=provider,
            exclude_existing=False,
        )
        for row in results:
            candidate_url = normalize_candidate_url(
                str(row.get("canonical_link") or row.get("link") or "").strip()
            )
            if not candidate_url:
                continue
            raw_candidates.append(
                SearchTemplateRawCandidate(
                    url=candidate_url,
                    title=str(row.get("title") or "").strip(),
                    text=str(row.get("snippet") or "").strip(),
                    summary=str(row.get("snippet") or "").strip(),
                )
            )
        if not raw_candidates and bool(params.get("enable_external_search_slowlane", True)):
            slowlane_used = True
            time.sleep(max(0.0, float(params.get("external_search_slowlane_sleep_seconds") or 1.25)))
            html, _ = fetch_html(
                f"https://html.duckduckgo.com/html/?{urlencode({'q': search_query})}",
                timeout=max(probe_timeout, float(params.get("external_search_slowlane_timeout") or probe_timeout)),
                retries=_search_service_retries("resilient"),
            )
            raw_candidates = extract_link_candidates_from_html(
                html,
                base_url="https://html.duckduckgo.com/html/",
                entry_domain=entry_domain,
                parser_profile=str(params.get("parser_profile") or "").strip() or None,
            )
    except HttpFetchError as exc:
        errors.append(
            {
                "site_url": entry_domain,
                "search_url": search_url,
                "error": str(exc),
                "error_class": "transport_failure",
                "recommended_search_service": "browser_candidate",
            }
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(
            {
                "site_url": entry_domain,
                "search_url": search_url,
                "error": str(exc),
                "error_class": "unexpected_failure",
                "recommended_search_service": "browser_candidate",
            }
        )

    scored = [
        candidate
        for candidate in (
            make_search_candidate(
                url=item.url,
                strategy="external_search",
                title=item.title,
                text=item.text,
                source_url=search_url,
                entry_domain=entry_domain,
            )
            for item in raw_candidates
        )
        if candidate is not None
    ]
    selected_candidates, used_term_fallback = select_search_candidates(
        scored,
        query_terms,
        strategy="external_search",
        entry_domain=entry_domain,
        search_url=search_url,
        allow_fallback=allow_term_fallback,
        fallback_limit=int(params.get("fallback_limit") or 20),
        scoring_config=_resolve_candidate_scoring_config(params),
    )
    return SearchTemplateExecutionResult(
        template=search_url,
        search_urls=[search_url],
        pages_scanned=1,
        raw_candidates=raw_candidates,
        selected_candidates=list(selected_candidates),
        used_term_fallback=used_term_fallback,
        errors=errors,
        diagnostics={
            "entry_domain": entry_domain,
            "raw_candidates": len(raw_candidates),
            "selected_candidates": len(selected_candidates),
            "transport_errors": sum(1 for row in errors if row.get("error_class") == "transport_failure"),
            "pages_scanned": 1,
            "search_service": "external_search_slowlane" if slowlane_used else "external_search",
            "search_service_fallbacks": 0,
            "slowlane_used": slowlane_used,
            "fallback_allowed": bool(allow_term_fallback),
            "used_term_fallback": bool(used_term_fallback),
            "candidate_filter_state": _candidate_filter_state(
                raw_count=len(raw_candidates),
                selected_count=len(selected_candidates),
                query_terms=query_terms,
                allow_term_fallback=allow_term_fallback,
                used_term_fallback=used_term_fallback,
            ),
        },
    )


def extract_feed_candidates(xml_text: str) -> list[SearchTemplateRawCandidate]:
    candidates: list[SearchTemplateRawCandidate] = []
    seen_urls: set[str] = set()
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return candidates

    for item in root.findall(".//{*}item"):
        title = str((item.findtext("{*}title") or "")).strip()
        description = str((item.findtext("{*}description") or "")).strip()
        link = item.find("{*}link")
        if link is not None and link.text:
            norm = normalize_candidate_url(link.text.strip())
            if norm and norm not in seen_urls:
                seen_urls.add(norm)
                candidates.append(SearchTemplateRawCandidate(url=norm, title=title, text=description))
        guid = item.find("{*}guid")
        if guid is not None and guid.text and str(guid.attrib.get("isPermaLink") or "").lower() == "true":
            norm = normalize_candidate_url(guid.text.strip())
            if norm and norm not in seen_urls:
                seen_urls.add(norm)
                candidates.append(SearchTemplateRawCandidate(url=norm, title=title, text=description))

    for entry in root.findall(".//{*}entry"):
        title = str((entry.findtext("{*}title") or "")).strip()
        summary = str((entry.findtext("{*}summary") or entry.findtext("{*}content") or "")).strip()
        for link in entry.findall("{*}link"):
            href = (link.attrib.get("href") or "").strip()
            if not href:
                continue
            rel = (link.attrib.get("rel") or "").strip().lower()
            typ = (link.attrib.get("type") or "").strip().lower()
            if rel and rel != "alternate":
                continue
            if typ and "html" not in typ and "xml" in typ:
                continue
            norm = normalize_candidate_url(href)
            if norm and norm not in seen_urls:
                seen_urls.add(norm)
                candidates.append(SearchTemplateRawCandidate(url=norm, title=title, text=summary))
    return candidates


def execute_feed_probe(
    *,
    feed_url: str,
    query_terms: list[str],
    probe_timeout: float,
    allow_term_fallback: bool,
    params: dict[str, Any] | None = None,
) -> SearchTemplateExecutionResult:
    raw_candidates: list[SearchTemplateRawCandidate] = []
    errors: list[dict[str, Any]] = []
    try:
        xml_text, _ = fetch_html(feed_url, timeout=probe_timeout, retries=1)
        raw_candidates = extract_feed_candidates(xml_text)
    except HttpFetchError as exc:
        errors.append({"site_url": feed_url, "error": str(exc), "error_class": "transport_failure"})
    except Exception as exc:  # noqa: BLE001
        errors.append({"site_url": feed_url, "error": str(exc), "error_class": "unexpected_failure"})

    effective_domain = (domain_from_url(feed_url) or "").strip().lower()
    scored = [
        candidate
        for candidate in (
            make_search_candidate(
                url=item.url,
                strategy="rss",
                title=item.title,
                text=item.text,
                source_url=feed_url,
                entry_domain=effective_domain,
            )
            for item in raw_candidates
        )
        if candidate is not None
    ]
    selected_candidates, used_term_fallback = select_search_candidates(
        scored,
        query_terms,
        strategy="rss",
        entry_domain=effective_domain,
        search_url=feed_url,
        allow_fallback=allow_term_fallback,
        scoring_config=_resolve_candidate_scoring_config(params),
    )
    return SearchTemplateExecutionResult(
        template=feed_url,
        search_urls=[feed_url],
        pages_scanned=1,
        raw_candidates=raw_candidates,
        selected_candidates=list(selected_candidates),
        used_term_fallback=used_term_fallback,
        errors=errors,
        diagnostics={
            "entry_domain": effective_domain,
            "raw_candidates": len(raw_candidates),
            "selected_candidates": len(selected_candidates),
            "transport_errors": sum(1 for row in errors if row.get("error_class") == "transport_failure"),
            "pages_scanned": 1,
            "fallback_allowed": bool(allow_term_fallback),
            "used_term_fallback": bool(used_term_fallback),
            "candidate_filter_state": _candidate_filter_state(
                raw_count=len(raw_candidates),
                selected_count=len(selected_candidates),
                query_terms=query_terms,
                allow_term_fallback=allow_term_fallback,
                used_term_fallback=used_term_fallback,
            ),
        },
    )


def _parse_sitemap_xml(xml_text: str) -> tuple[str, list[str]]:
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return "unknown", []
    kind = root.tag.split("}", 1)[-1].lower()
    locs: list[str] = []
    for loc in root.findall(".//{*}loc"):
        if loc.text:
            norm = normalize_candidate_url(loc.text.strip())
            if norm and norm not in locs:
                locs.append(norm)
    return kind, locs


def _fetch_text_maybe_gzip(url: str, *, timeout: float) -> str:
    text, resp = fetch_html(url, timeout=timeout, retries=1)
    if url.lower().endswith(".gz"):
        try:
            return gzip.decompress(resp.content).decode("utf-8", errors="ignore")
        except Exception:
            return text
    return text


def collect_sitemap_urls(
    sitemap_url: str,
    *,
    timeout: float,
    max_depth: int = 2,
    max_sitemaps: int = 50,
) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    to_fetch: list[tuple[str, int]] = [(sitemap_url, 0)]
    fetched = 0

    while to_fetch and fetched < max_sitemaps:
        url, depth = to_fetch.pop(0)
        if url in seen:
            continue
        seen.add(url)
        fetched += 1

        xml_text = _fetch_text_maybe_gzip(url, timeout=timeout)
        kind, locs = _parse_sitemap_xml(xml_text)
        if kind.endswith("sitemapindex") and depth < max_depth:
            for loc in locs:
                if loc not in seen:
                    to_fetch.append((loc, depth + 1))
            continue

        for loc in locs:
            if loc not in urls:
                urls.append(loc)
    return urls


def execute_sitemap_probe(
    *,
    sitemap_url: str,
    query_terms: list[str],
    probe_timeout: float,
    max_depth: int,
    max_sitemaps: int,
    allow_term_fallback: bool,
    params: dict[str, Any] | None = None,
) -> SearchTemplateExecutionResult:
    errors: list[dict[str, Any]] = []
    raw_candidates: list[SearchTemplateRawCandidate] = []
    try:
        urls = collect_sitemap_urls(
            sitemap_url,
            timeout=probe_timeout,
            max_depth=max_depth,
            max_sitemaps=max_sitemaps,
        )
        raw_candidates = [SearchTemplateRawCandidate(url=url) for url in urls]
    except HttpFetchError as exc:
        errors.append({"site_url": sitemap_url, "error": str(exc), "error_class": "transport_failure"})
    except Exception as exc:  # noqa: BLE001
        errors.append({"site_url": sitemap_url, "error": str(exc), "error_class": "unexpected_failure"})

    effective_domain = (domain_from_url(sitemap_url) or "").strip().lower()
    scored = [
        candidate
        for candidate in (
            make_search_candidate(
                url=item.url,
                strategy="sitemap",
                title=item.title,
                text=item.text,
                source_url=sitemap_url,
                entry_domain=effective_domain,
            )
            for item in raw_candidates
        )
        if candidate is not None
    ]
    selected_candidates, used_term_fallback = select_search_candidates(
        scored,
        query_terms,
        strategy="sitemap",
        entry_domain=effective_domain,
        search_url=sitemap_url,
        allow_fallback=allow_term_fallback,
        scoring_config=_resolve_candidate_scoring_config(params),
    )
    return SearchTemplateExecutionResult(
        template=sitemap_url,
        search_urls=[sitemap_url],
        pages_scanned=1,
        raw_candidates=raw_candidates,
        selected_candidates=list(selected_candidates),
        used_term_fallback=used_term_fallback,
        errors=errors,
        diagnostics={
            "entry_domain": effective_domain,
            "raw_candidates": len(raw_candidates),
            "selected_candidates": len(selected_candidates),
            "transport_errors": sum(1 for row in errors if row.get("error_class") == "transport_failure"),
            "pages_scanned": 1,
            "fallback_allowed": bool(allow_term_fallback),
            "used_term_fallback": bool(used_term_fallback),
            "candidate_filter_state": _candidate_filter_state(
                raw_count=len(raw_candidates),
                selected_count=len(selected_candidates),
                query_terms=query_terms,
                allow_term_fallback=allow_term_fallback,
                used_term_fallback=used_term_fallback,
            ),
        },
    )
