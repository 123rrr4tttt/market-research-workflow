"""Modular HTML search-result parser service used by route/execution layers."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable
from urllib.parse import parse_qs, parse_qsl, urlencode, unquote, urljoin, urlsplit, urlunsplit

from ..ingest.adapters.http_utils import make_html_parser
from .search_result_parser_profiles import SearchResultParserProfile
from .search_result_parser_profiles import build_search_result_parser_profile
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


@dataclass(frozen=True)
class SearchResultParserModule:
    module_id: str
    parse: Callable[..., None]


def resolve_search_result_parser_profile(
    entry_domain: str | None,
    *,
    parser_profile: str | None = None,
) -> SearchResultParserProfile:
    return build_search_result_parser_profile(entry_domain, parser_profile=parser_profile)


def parse_search_result_candidates(
    html: str,
    *,
    base_url: str,
    entry_domain: str | None = None,
    parser_profile: str | None = None,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    profile = resolve_search_result_parser_profile(
        entry_domain or domain_from_url(base_url),
        parser_profile=parser_profile,
    )
    parser = make_html_parser(html)
    state = _SearchResultParserState(profile=profile, parser=parser, base_url=base_url)
    for module in resolve_search_result_parser_modules(profile):
        module.parse(state)
    diagnostics = {
        "parser_profile_resolved": profile.profile_key,
        "parser_module_used": state.module_trace[0] if state.module_trace else "",
        "parser_modules_tried": list(state.module_trace),
        "container_hit": state.diagnostics["container_hit"],
        "structured_hit": state.diagnostics["structured_hit"],
        "json_ld_hit": state.diagnostics["json_ld_hit"],
        "global_anchor_hit": state.diagnostics["global_anchor_hit"],
        "candidate_rejected_low_value": state.diagnostics["candidate_rejected_low_value"],
    }
    return state.candidates, diagnostics


def resolve_search_result_parser_modules(profile: SearchResultParserProfile) -> list[SearchResultParserModule]:
    registry = {
        "container": SearchResultParserModule("container", _run_container_module),
        "structured": SearchResultParserModule("structured", _run_structured_module),
        "jsonld": SearchResultParserModule("jsonld", _run_jsonld_module),
        "global_anchor": SearchResultParserModule("global_anchor", _run_global_anchor_module),
    }
    modules: list[SearchResultParserModule] = []
    for module_id in profile.module_chain:
        module = registry.get(module_id)
        if module is not None:
            modules.append(module)
    return modules


@dataclass
class _SearchResultParserState:
    profile: SearchResultParserProfile
    parser: Any
    base_url: str
    candidates: list[dict[str, str]] = None  # type: ignore[assignment]
    seen_urls: set[str] = None  # type: ignore[assignment]
    diagnostics: dict[str, int] = None  # type: ignore[assignment]
    module_trace: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.candidates = []
        self.seen_urls = set()
        self.diagnostics = {
            "container_hit": 0,
            "structured_hit": 0,
            "json_ld_hit": 0,
            "global_anchor_hit": 0,
            "candidate_rejected_low_value": 0,
        }
        self.module_trace = []


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


def _run_container_module(state: _SearchResultParserState) -> None:
    container_nodes = []
    for selector in state.profile.container_selectors:
        found = state.parser.css(selector)
        if found:
            container_nodes.extend(found[:40])
    deduped_container_nodes = []
    seen_container_ids: set[int] = set()
    for container in container_nodes:
        marker = id(container)
        if marker in seen_container_ids:
            continue
        seen_container_ids.add(marker)
        deduped_container_nodes.append(container)
    for container in deduped_container_nodes:
        container_text = _node_text(container, max_chars=600)
        for node in _iter_container_anchor_nodes(container, title_link_selectors=state.profile.title_link_selectors):
            candidate = _candidate_from_anchor(
                node,
                base_url=state.base_url,
                context_text=container_text,
                container=container,
                profile=state.profile,
            )
            if candidate is None:
                state.diagnostics["candidate_rejected_low_value"] += 1
                continue
            if candidate["url"] in state.seen_urls:
                continue
            state.seen_urls.add(candidate["url"])
            state.candidates.append(candidate)
            state.diagnostics["container_hit"] += 1
    if state.diagnostics["container_hit"] > 0:
        state.module_trace.append("container")


def _run_structured_module(state: _SearchResultParserState) -> None:
    before = state.diagnostics["structured_hit"]
    for selector in state.profile.container_selectors:
        found = state.parser.css(selector)
        if not found:
            continue
        for container in found[:20]:
            container_text = _node_text(container, max_chars=600)
            for attr_name in state.profile.structured_result_url_attributes:
                raw_url = str(container.attributes.get(attr_name) or "").strip()
                if not raw_url:
                    continue
                candidate_url = normalize_candidate_url(urljoin(state.base_url, raw_url))
                if (
                    not candidate_url
                    or candidate_url in state.seen_urls
                    or _is_low_value_candidate_href(candidate_url, profile=state.profile)
                ):
                    state.diagnostics["candidate_rejected_low_value"] += 1
                    continue
                title = _extract_container_title(container, profile=state.profile)
                summary = _extract_container_summary(container, profile=state.profile)
                state.seen_urls.add(candidate_url)
                state.candidates.append(
                    {
                        "url": candidate_url,
                        "text": " ".join(part for part in [title, summary, container_text] if part)[:800],
                        "title": title[:240],
                        "summary": summary[:400],
                        "extra": _build_candidate_extra(candidate_url, profile=state.profile),
                    }
                )
                state.diagnostics["structured_hit"] += 1
    if state.diagnostics["structured_hit"] > before:
        state.module_trace.append("structured")


def _run_jsonld_module(state: _SearchResultParserState) -> None:
    before = state.diagnostics["json_ld_hit"]
    for node in state.parser.css("script[type='application/ld+json']"):
        raw = _node_text(node, max_chars=20000)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        for item in _iter_json_ld_items(payload):
            candidate = _candidate_from_json_ld_item(item, base_url=state.base_url, profile=state.profile)
            if candidate is None or candidate["url"] in state.seen_urls:
                continue
            state.seen_urls.add(candidate["url"])
            state.candidates.append(candidate)
            state.diagnostics["json_ld_hit"] += 1
    if state.diagnostics["json_ld_hit"] > before:
        state.module_trace.append("jsonld")


def _run_global_anchor_module(state: _SearchResultParserState) -> None:
    before = state.diagnostics["global_anchor_hit"]
    for node in state.parser.css("a"):
        candidate = _candidate_from_anchor(
            node,
            base_url=state.base_url,
            context_text="",
            container=None,
            profile=state.profile,
        )
        if candidate is None:
            state.diagnostics["candidate_rejected_low_value"] += 1
            continue
        if candidate["url"] in state.seen_urls or not _is_high_signal_global_anchor(candidate, profile=state.profile):
            continue
        state.seen_urls.add(candidate["url"])
        state.candidates.append(candidate)
        state.diagnostics["global_anchor_hit"] += 1
    if state.diagnostics["global_anchor_hit"] > before:
        state.module_trace.append("global_anchor")


def _candidate_from_anchor(
    node: Any,
    *,
    base_url: str,
    context_text: str,
    container: Any | None,
    profile: SearchResultParserProfile,
) -> dict[str, str] | None:
    href = (node.attributes.get("href") or "").strip()
    if not href:
        return None
    candidate_url = normalize_candidate_url(urljoin(base_url, href))
    if not candidate_url or _is_low_value_candidate_href(candidate_url, profile=profile):
        return None
    anchor_text = _node_text(node, max_chars=240)
    title = str(node.attributes.get("title") or node.attributes.get("aria-label") or "").strip()
    if not title and container is not None:
        title = _extract_container_title(container, profile=profile)
    if not title:
        title = anchor_text
    normalized_anchor_text = " ".join(anchor_text.lower().split())
    if normalized_anchor_text in profile.low_value_anchor_texts and title:
        anchor_text = title
    summary = _extract_container_summary(container, profile=profile) if container is not None else ""
    text = " ".join(part for part in [anchor_text, summary, context_text] if part).strip()
    return {
        "url": candidate_url,
        "text": text[:800],
        "title": title[:240],
        "summary": summary[:400],
        "extra": _build_candidate_extra(candidate_url, profile=profile),
    }


def _candidate_from_json_ld_item(
    item: dict[str, Any],
    *,
    base_url: str,
    profile: SearchResultParserProfile,
) -> dict[str, str] | None:
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
    if not candidate_url or _is_low_value_candidate_href(candidate_url, profile=profile):
        return None
    title = str(item.get("headline") or item.get("name") or "").strip()
    if not title and isinstance(child_item, dict):
        title = str(child_item.get("name") or child_item.get("headline") or "").strip()
    text = str(item.get("description") or "").strip()
    if not text and isinstance(child_item, dict):
        text = str(child_item.get("description") or child_item.get("summary") or "").strip()
    return {
        "url": candidate_url,
        "text": text[:800],
        "title": title[:240],
        "summary": text[:400],
        "extra": _build_candidate_extra(candidate_url, profile=profile),
    }


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


def _node_text(node: Any, *, max_chars: int) -> str:
    try:
        text = str(node.text(separator=" ", strip=True) or "").strip()
    except Exception:
        text = ""
    return " ".join(text.split())[:max_chars]


def _extract_container_title(container: Any, *, profile: SearchResultParserProfile) -> str:
    for selector in profile.title_selectors:
        try:
            title_nodes = container.css(selector)
        except Exception:
            title_nodes = []
        if title_nodes:
            title = _node_text(title_nodes[0], max_chars=240)
            if title:
                return title
    return ""


def _extract_container_summary(container: Any, *, profile: SearchResultParserProfile) -> str:
    for selector in profile.summary_selectors:
        try:
            nodes = container.css(selector)
        except Exception:
            nodes = []
        for node in nodes:
            text = _node_text(node, max_chars=400)
            normalized = " ".join(text.lower().split())
            if text and normalized not in profile.low_value_anchor_texts:
                return text
    return ""


def _is_low_value_candidate_href(url: str, *, profile: SearchResultParserProfile) -> bool:
    parts = urlsplit(str(url or "").strip())
    host = str(parts.netloc or "").lower()
    path = str(parts.path or "").lower()
    if any(marker in host for marker in profile.low_value_host_markers):
        return True
    if any(marker in path for marker in profile.low_value_href_markers):
        return True
    if any(path.endswith(suffix) for suffix in profile.low_value_path_suffixes):
        return True
    if path in {"", "/"}:
        return True
    if profile.article_path_pattern is not None and not profile.article_path_pattern.search(path):
        return True
    return False


def _is_high_signal_global_anchor(candidate: dict[str, str], *, profile: SearchResultParserProfile) -> bool:
    text = " ".join((candidate.get("title") or candidate.get("text") or "").split()).strip()
    if len(text) < profile.global_anchor_min_text_length:
        return False
    parts = urlsplit(str(candidate.get("url") or ""))
    if parts.scheme not in {"http", "https"}:
        return False
    path = str(parts.path or "").strip("/")
    if path.count("/") < 1:
        return False
    return True


def _build_candidate_extra(url: str, *, profile: SearchResultParserProfile) -> dict[str, str]:
    return {
        "route_kind": _classify_candidate_route_kind(url, profile=profile),
        "parser_profile": profile.profile_key,
    }


def _classify_candidate_route_kind(url: str, *, profile: SearchResultParserProfile) -> str:
    path = str(urlsplit(url).path or "").lower()
    for pattern, route_kind in profile.route_rules:
        if pattern.search(path):
            return route_kind
    if profile.article_path_pattern is not None and profile.article_path_pattern.search(path):
        return "article"
    return profile.default_route_kind


def _iter_container_anchor_nodes(container: Any, *, title_link_selectors: tuple[str, ...]) -> list[Any]:
    selected: list[Any] = []
    seen_ids: set[int] = set()
    for selector in title_link_selectors:
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
