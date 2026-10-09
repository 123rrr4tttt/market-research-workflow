"""Shared source-capability execution helpers used by adapters and unified search."""

from __future__ import annotations

import gzip
import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Annotated, Any, NoReturn, SupportsIndex, SupportsInt, cast
from urllib.parse import parse_qs, parse_qsl, unquote, urlencode, urlsplit, urlunsplit

from functorial_kit import Failure

from mrw_functorial_kit.core.provider_port_failures import resource_pool_contract_failures

from ..ingest.source_search_contract import build_query_url_from_contract, normalize_source_search_contract
from .http_port import HttpFetchError, fetch_html
from .search_capabilities import SearchCapabilityScore, make_search_candidate, select_search_candidates
from .search_result_parser_service import (
    SearchResultParserDiagnostics,
    parse_search_result_candidates,
)
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

_RESOURCE_POOL_FAILURE_WITNESS = "test:test_latest_service_b_resource_pool_failure_lifts"
_RESOURCE_POOL_FAILURE_CONTEXT_KEYS = frozenset(
    {
        "boundary_class",
        "failure_family",
        "operation",
        "owner",
        "public_exception",
        "public_message",
        "site",
        "witness",
    }
)


def _contract_failure(code: str, message: str, *, operation: str, site: str) -> Failure:
    return resource_pool_contract_failures.fail(
        code,
        message,
        {
            "boundary_class": "PURE_CONTRACT_FAILURE",
            "failure_family": resource_pool_contract_failures.name,
            "operation": operation,
            "owner": site,
            "public_exception": "ValueError",
            "public_message": message,
            "site": site,
            "witness": _RESOURCE_POOL_FAILURE_WITNESS,
        },
    )


def _raise_contract_failure(
    failure: Failure,
    exception_type: type[Exception] = ValueError,
) -> NoReturn:
    context = failure.context or {}
    if (
        not resource_pool_contract_failures.matches(failure)
        or _RESOURCE_POOL_FAILURE_CONTEXT_KEYS - set(context)
        or context.get("public_exception") != exception_type.__name__
    ):
        # kit:boundary owner=resource_pool.search_template_service.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_latest_service_b_resource_pool_failure_lifts
        raise TypeError("resource pool failure lift context is incomplete or inconsistent")
    # kit:boundary owner=resource_pool.search_template_service.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=resource_pool.contract.failure witness=test:test_latest_service_b_resource_pool_failure_lifts
    raise exception_type(str(context["public_message"]))
@dataclass(frozen=True)
class SearchTemplateRawCandidate:
    url: str
    text: str = ""
    title: str = ""
    summary: str = ""
    extra: dict[str, Any] = field(default_factory=dict[str, object])


@dataclass(frozen=True)
class SearchTemplateExecutionResult:
    template: str
    search_urls: list[str]
    pages_scanned: int
    raw_candidates: list[SearchTemplateRawCandidate]
    selected_candidates: list[SearchCapabilityScore]
    used_term_fallback: bool
    errors: list[dict[str, Any]] = field(default_factory=list[dict[str, object]])
    diagnostics: dict[str, Any] = field(default_factory=dict[str, object])


def _resolve_search_service(params: Mapping[object, object]) -> str:
    service = str(params.get("search_service") or "basic").strip().lower()
    return service if service in {"basic", "resilient"} else "basic"


def _search_service_retries(service: str) -> int:
    return 2 if service == "resilient" else 1


def _integer(value: object, default: int) -> int:
    if not isinstance(value, (str, bytes, bytearray, SupportsInt, SupportsIndex)):
        return default
    try:
        return int(value)
    except Exception:
        return default


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


def resolve_search_template_pagination(params: Mapping[object, object]) -> tuple[int, int]:
    def _parse_int(value: object, default: int, *, min_value: int, max_value: int) -> int:
        parsed = _integer(value, default)
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
) -> tuple[list[SearchTemplateRawCandidate], SearchResultParserDiagnostics]:
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
                extra=dict(item["extra"]),
            )
            for item in raw_candidates
            if str(item.get("url") or "").strip()
        ],
        diagnostics,
    )


def _resolve_candidate_scoring_config(
    params: Mapping[object, object] | dict[str, Any] | None,
) -> dict[str, Any] | str | None:
    if params is None:
        return None
    raw = params.get("candidate_scoring_config") or params.get("candidate_selection_config")
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        return cast(dict[str, Any], raw)
    return None


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


def build_search_template_urls(
    template: str,
    query_terms: list[str],
    params: Mapping[object, object],
) -> Annotated[
    tuple[list[str], int],
    "kit:non-authoritative derived_as=view fact_source=search_template+query_terms+pagination_params witness=test:test_w03_ingest_ports_authority_metadata",
]:
    normalized_template = normalize_search_template_placeholders(template)
    if not normalized_template or "{{q}}" not in normalized_template:
        _raise_contract_failure(
            _contract_failure(
                "search_template_invalid",
                "search_template requires template containing {{q}}",
                operation="build_search_template_urls",
                site="resource_pool.search_template_service.build_search_template_urls",
            )
        )
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
    params: Mapping[object, object],
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
    parser_diagnostics_acc: dict[str, object] = {}

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
                previous = parser_diagnostics_acc.get(diagnostics_key)
                previous_count = previous if isinstance(previous, int) else 0
                parser_diagnostics_acc[diagnostics_key] = previous_count + value
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
        fallback_limit=int(cast(Any, params.get("fallback_limit") or 30)),
        scoring_config=_resolve_candidate_scoring_config(params),
    )

    diagnostics: dict[str, object] = {
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
        _raise_contract_failure(
            _contract_failure(
                "entry_domain_required",
                "entry_domain is required for external site search",
                operation="execute_external_site_search",
                site="resource_pool.search_template_service.execute_external_site_search",
            )
        )
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
    params: Mapping[object, object] | None = None,
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
