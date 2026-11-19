"""Deterministic site entry classification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_ENTRY_TYPE_TO_CHANNEL: dict[str, str] = {
    "rss": "generic_web.rss",
    "sitemap": "generic_web.sitemap",
    "domain_root": "url_pool",
    "search_template": "generic_web.search_template",
    "official_api": "official_access.api",
}


@dataclass
class Recommendation:
    """Classify result: channel_key, entry_type, template (if search_template), validated flag."""

    channel_key: str
    entry_type: str
    template: str | None
    validated: bool
    source: Literal["rule", "fallback"]
    capabilities: dict[str, Any] | None = None


def infer_keyword_capabilities(entry_type: str | None, channel_key: str | None = None) -> dict[str, Any]:
    """
    Keyword capability classification for site entries (URL fact layer metadata).
    This does not store task keywords, only labels what the entry can support.
    """
    et = str(entry_type or "").strip().lower()
    ch = str(channel_key or "").strip().lower()
    supports = False
    keyword_mode = "none"
    if et == "search_template" or ch.endswith("search_template"):
        supports = True
        keyword_mode = "search"
    elif et in {"rss", "sitemap"} or ch.endswith(".rss") or ch.endswith(".sitemap"):
        supports = True
        keyword_mode = "filter"
    elif et in {"domain_root", "official_api"}:
        supports = False
        keyword_mode = "none"
    return {
        "supports_query_terms": supports,
        "keyword_mode": keyword_mode,
    }


def _path_from_url(url: str) -> str:
    """Extract path from URL (lowercase)."""
    if not url:
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


def _build_search_template_from_url(site_url: str) -> str | None:
    """
    Convert an obvious search URL to a reusable template:
    - replace q/query/keyword/keywords/search param value with {{q}}
    - preserve other query params
    - optionally normalize page-like params to {{page}}
    """
    try:
        parsed = urlparse(site_url)
    except Exception:
        return None
    if not (parsed.scheme and parsed.netloc):
        return None
    pairs = parse_qsl(parsed.query or "", keep_blank_values=True)
    if not pairs:
        return None
    replaced_any = False
    out_pairs: list[tuple[str, str]] = []
    for k, v in pairs:
        lk = (k or "").lower()
        if lk in {"q", "query", "keyword", "keywords", "search"}:
            out_pairs.append((k, "{{q}}"))
            replaced_any = True
            continue
        if lk in {"page", "p", "paged"} and str(v).strip():
            out_pairs.append((k, "{{page}}"))
            continue
        out_pairs.append((k, v))
    if not replaced_any:
        return None
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(out_pairs), ""))


def _rule_search_template(site_url: str) -> Recommendation | None:
    if not site_url or not site_url.strip().lower().startswith(("http://", "https://")):
        return None
    try:
        parsed = urlparse(site_url)
    except Exception:
        return None
    path = (parsed.path or "").lower()
    query_pairs = parse_qsl(parsed.query or "", keep_blank_values=True)
    query_keys = {str(k or "").lower() for k, _ in query_pairs}
    has_search_path = any(x in path for x in ("/search", "/find", "/query"))
    has_query_key = any(k in {"q", "query", "keyword", "keywords", "search"} for k in query_keys)
    if not (has_search_path or has_query_key):
        return None
    template = _build_search_template_from_url(site_url)
    if not template and has_search_path:
        # Path looks like search page even if example URL omitted q param.
        sep = "&" if parsed.query else "?"
        template = f"{site_url}{sep}q={{q}}"
    if not template:
        return None
    return Recommendation(
        channel_key="generic_web.search_template",
        entry_type="search_template",
        template=template,
        validated=True,
        source="rule",
        capabilities=infer_keyword_capabilities("search_template", "generic_web.search_template"),
    )


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
    if known_entry in _ENTRY_TYPE_TO_CHANNEL:
        ch = _ENTRY_TYPE_TO_CHANNEL[known_entry]
        if known_entry == "search_template" and not template:
            return None  # search_template needs template, cannot rule-classify
        return Recommendation(
            channel_key=ch,
            entry_type=known_entry,
            template=template,
            validated=True,
            source="rule",
            capabilities=infer_keyword_capabilities(known_entry, ch),
        )

    # URL path/query heuristics when entry_type unknown
    rec = _rule_search_template(site_url)
    if rec is not None:
        return rec

    if _path_suggests_sitemap(path):
        return Recommendation(
            channel_key="generic_web.sitemap",
            entry_type="sitemap",
            template=None,
            validated=True,
            source="rule",
            capabilities=infer_keyword_capabilities("sitemap", "generic_web.sitemap"),
        )
    if _path_suggests_rss(path):
        return Recommendation(
            channel_key="generic_web.rss",
            entry_type="rss",
            template=None,
            validated=True,
            source="rule",
            capabilities=infer_keyword_capabilities("rss", "generic_web.rss"),
        )

    return None


def classify_site_entries_batch(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return recommendations in input order, preserving caller row identities."""
    out: list[dict[str, Any]] = []
    for row in entries:
        item = dict(row)
        recommendation = classify_site_entry(
            str(item.get("site_url") or "").strip(), item.get("entry_type"), item.get("template")
        )
        item.update(
            channel_key=recommendation.channel_key,
            entry_type=recommendation.entry_type,
            template=recommendation.template,
            validated=recommendation.validated,
            source=recommendation.source,
            capabilities=recommendation.capabilities,
        )
        out.append(item)
    return out


def classify_site_entry(
    site_url: str,
    entry_type: str | None = None,
    template: str | None = None,
) -> Recommendation:
    """Classify a site entry, or offer an unvalidated URL-pool default."""
    rec = _rule_classify(site_url, entry_type, template)
    if rec is not None:
        return rec

    return Recommendation(
        channel_key="url_pool",
        entry_type="domain_root",
        template=None,
        validated=False,
        source="fallback",
        capabilities=infer_keyword_capabilities("domain_root", "url_pool"),
    )
