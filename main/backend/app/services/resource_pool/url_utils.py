"""URL extraction and normalization utilities for resource pool."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_TRACKING_QUERY_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "gclid",
    "fbclid",
    "msclkid",
    "ref",
    "ref_src",
    "source",
}


def extract_urls_from_text(text: str | None) -> list[str]:
    """Extract http/https URLs from text. Filters out data:, mailto:, etc."""
    if not text or not isinstance(text, str):
        return []
    pattern = re.compile(
        r"https?://[^\s<>\"')\]]+",
        re.IGNORECASE,
    )
    found = pattern.findall(text)
    result = []
    for url in found:
        url = url.rstrip(".,;:!?")
        if url.lower().startswith(("data:", "mailto:", "javascript:")):
            continue
        result.append(url)
    return result


def extract_urls_from_json(obj: object) -> list[str]:
    """Recursively extract URL-like strings from JSON/dict structure."""
    seen: set[str] = set()
    result: list[str] = []

    def _walk(o: object) -> None:
        if isinstance(o, str):
            if re.match(r"^https?://", o, re.I) and o.strip() not in seen:
                norm = normalize_url(o.strip())
                if norm and norm not in seen:
                    seen.add(norm)
                    result.append(norm)
        elif isinstance(o, dict):
            for v in o.values():
                _walk(v)
        elif isinstance(o, (list, tuple)):
            for item in o:
                _walk(item)

    _walk(obj)
    return result


def canonicalize_url(url: str) -> tuple[str | None, str]:
    """Return canonical URL and dedupe reason.

    Canonicalization rules (contract-level):
    - drop fragment
    - lowercase scheme/netloc
    - collapse trailing slash for non-root paths
    - remove known tracking query params (utm_*, gclid, fbclid...)
    - sort retained query params by key/value for stable dedupe
    """
    if not url or not isinstance(url, str):
        return None, "invalid_url"
    raw = url.strip()
    if not raw.lower().startswith(("http://", "https://")):
        return None, "invalid_scheme"

    try:
        parsed = urlparse(raw)
    except Exception:
        return None, "parse_failed"

    scheme = (parsed.scheme or "").lower()
    netloc = (parsed.netloc or "").lower()
    if not scheme or not netloc:
        return None, "missing_host"

    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"

    kept_params: list[tuple[str, str]] = []
    removed_tracking = False
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lk = (key or "").strip().lower()
        if lk.startswith("utm_") or lk in _TRACKING_QUERY_KEYS:
            removed_tracking = True
            continue
        kept_params.append((key, value))
    kept_params.sort(key=lambda x: (x[0], x[1]))
    query = urlencode(kept_params, doseq=True)

    canonical = urlunparse((scheme, netloc, path, "", query, ""))
    if removed_tracking:
        return canonical, "query_tracking_stripped"
    if query and query != parsed.query:
        return canonical, "query_reordered"
    if parsed.fragment:
        return canonical, "fragment_removed"
    if canonical != raw:
        return canonical, "canonicalized"
    return canonical, "exact_match"


def normalize_url(url: str) -> str | None:
    """Normalize URL to canonical format. Return None if invalid."""
    canonical, _ = canonicalize_url(url)
    return canonical


def domain_from_url(url: str) -> str | None:
    """Extract domain from URL. Returns None if invalid."""
    if not url:
        return None
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc or ""
        if not netloc:
            return None
        return netloc.lower().lstrip("www.")
    except Exception:
        return None
