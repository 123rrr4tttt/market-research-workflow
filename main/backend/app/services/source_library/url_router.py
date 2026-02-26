"""URL-to-channel routing: resolve channel_key from URL using url_channel_routing config."""

from __future__ import annotations

from urllib.parse import urlparse, parse_qs

from ..ingest_config.service import get_config

_DEFAULT_CHANNEL = "url_pool"


def _domain_from_url(url: str) -> str:
    """Extract domain from URL (lowercase, without www). Returns empty string if invalid."""
    if not url or not isinstance(url, str):
        return ""
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc or ""
        if not netloc:
            return ""
        return netloc.lower().lstrip("www.")
    except Exception:
        return ""


def _path_from_url(url: str) -> str:
    """Extract path from URL (lowercase). Returns empty string if invalid."""
    if not url or not isinstance(url, str):
        return ""
    try:
        parsed = urlparse(url)
        return (parsed.path or "").lower()
    except Exception:
        return ""


def _pattern_matches(domain: str, pattern: str) -> bool:
    """
    Match pattern against domain.
    - "default": matches all
    - prefix (e.g. "news."): domain.startswith(pattern)
    - contains (e.g. "reddit.com"): pattern in domain
    """
    if not pattern:
        return False
    pattern = str(pattern).strip()
    if pattern == "default":
        return True
    if pattern.endswith("."):
        return domain.startswith(pattern)
    return pattern in domain


def _path_rule_matches(path: str, rule: dict) -> bool:
    """
    Match optional path constraints in rule.
    - path_contains: path must contain this substring
    - path_suffix: path must end with this (e.g. ".xml", "/feed", "/rss")
    - path_prefix: path must start with this
    """
    path_contains = rule.get("path_contains")
    if path_contains is not None:
        if str(path_contains).lower() not in path:
            return False
    path_suffix = rule.get("path_suffix")
    if path_suffix is not None:
        suf = str(path_suffix).lower()
        if not path.endswith(suf) and not path.endswith(suf + "/"):
            return False
    path_prefix = rule.get("path_prefix")
    if path_prefix is not None:
        pre = str(path_prefix).lower()
        if not path.startswith(pre):
            return False
    return True


def _heuristic_channel_by_path(path: str) -> str | None:
    """Heuristic fallback when no routing config matches."""
    p = (path or "").lower()
    if not p:
        return None
    # Prefer explicit sitemap markers first.
    if "sitemap" in p or p.endswith("/sitemap.xml") or p.endswith(".xml.gz"):
        return "generic_web.sitemap"
    # Common feed endpoints (RSS/Atom/blog feed).
    if (
        "/rss" in p
        or p.endswith("/feed")
        or p.endswith("/feed/")
        or "feed.xml" in p
        or "rss.xml" in p
        or "atom.xml" in p
    ):
        return "generic_web.rss"
    return None


def _heuristic_keyword_aware_channel(url: str, path: str, *, has_query_terms: bool) -> str | None:
    """
    Prefer keyword-aware channels when the execution request carries query terms.
    Only applies to URLs that look like search endpoints/templates.
    """
    if not has_query_terms:
        return None
    p = (path or "").lower()
    if not p:
        return None
    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query or "")
    except Exception:
        qs = {}
    searchish_path = any(x in p for x in ("/search", "/find", "/query"))
    searchish_qs = any(k.lower() in {"q", "query", "keyword", "keywords", "search"} for k in qs.keys())
    if searchish_path or searchish_qs:
        return "generic_web.search_template"
    return None


def resolve_channel_for_url(url: str, project_key: str | None, *, has_query_terms: bool = False) -> str:
    """
    Resolve channel_key for a URL using url_channel_routing config.

    Config payload.rules: [{ "pattern": str, "channel_key": str }], matched in order.
    Pattern types: prefix (e.g. "news."), contains (e.g. "reddit.com"), or "default".

    Returns channel_key; falls back to _DEFAULT_CHANNEL when no config or no match.
    """
    path = _path_from_url(url)
    kw_aware = _heuristic_keyword_aware_channel(url, path, has_query_terms=has_query_terms)
    guessed = _heuristic_channel_by_path(path)

    if not project_key:
        return kw_aware or guessed or _DEFAULT_CHANNEL

    cfg = get_config(project_key, "url_channel_routing")
    if not cfg or not isinstance(cfg.get("payload"), dict):
        return kw_aware or guessed or _DEFAULT_CHANNEL

    rules = cfg["payload"].get("rules")
    if not isinstance(rules, list) or not rules:
        return kw_aware or guessed or _DEFAULT_CHANNEL

    domain = _domain_from_url(url)
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        pattern = rule.get("pattern")
        channel_key = rule.get("channel_key")
        if not pattern or not channel_key:
            continue
        if not _pattern_matches(domain, str(pattern)):
            continue
        if not _path_rule_matches(path, rule):
            continue
        return str(channel_key).strip()

    if kw_aware:
        return kw_aware
    if guessed:
        return guessed

    return _DEFAULT_CHANNEL
