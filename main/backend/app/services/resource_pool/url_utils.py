"""URL extraction and normalization utilities for resource pool."""

from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse


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


def normalize_url(url: str) -> str | None:
    """Normalize URL: remove fragment, strip. Return None if invalid."""
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if not url.lower().startswith(("http://", "https://")):
        return None
    try:
        parsed = urlparse(url)
        normalized = urlunparse(
            (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", "", "", "")
        )
        return normalized.strip("/") or normalized
    except Exception:
        return None


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
