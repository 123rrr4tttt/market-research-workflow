from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_DROP_QUERY_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "utm_name",
    "gclid",
    "fbclid",
    "igshid",
    "mc_cid",
    "mc_eid",
}

REASON_CODE_DICTIONARY: dict[str, tuple[str, ...]] = {
    "policy": (
        "robots_disallow",
        "domain_blocked",
        "rate_limited",
        "url_policy_blocked",
    ),
    "quality": (
        "low_value_page",
        "content_gate_rejected",
        "light_filter_rejected",
    ),
    "provenance": (
        "provenance_gate_rejected",
        "source_untrusted",
        "source_not_verified",
    ),
    "technical": (
        "fetch_failed",
        "parse_failed",
        "timeout",
        "unknown_rejection_reason",
    ),
}

DEDUPE_HIT_REASON: dict[str, str] = {
    "canonical_url_match": "canonical_url_equal",
    "content_hash_match": "content_hash_equal",
    "canonical_and_content_match": "canonical_url_and_content_hash_equal",
}

SOURCE_ITEM_CAPABILITY_DEFAULT: dict[str, object] = {
    "supports_incremental": True,
    "supports_backfill": False,
    "rate_limit_class": "normal",
}


def canonicalize_url(url: str) -> str | None:
    if not url or not isinstance(url, str):
        return None
    raw = url.strip()
    if not raw.lower().startswith(("http://", "https://")):
        return None
    parsed = urlparse(raw)
    if not parsed.netloc:
        return None

    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"

    query_pairs = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key.lower() in _DROP_QUERY_KEYS:
            continue
        query_pairs.append((key, value))
    query_pairs.sort(key=lambda x: (x[0], x[1]))

    query = urlencode(query_pairs, doseq=True)
    out = urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            "",
            query,
            "",  # always drop fragment
        )
    )
    return out


def build_idempotency_key(*, canonical_url: str, content_hash: str | None, scope: str) -> str:
    base = "|".join(
        [
            str(canonical_url or "").strip().lower(),
            str(content_hash or "").strip().lower(),
            str(scope or "project").strip().lower(),
        ]
    )
    return hashlib.sha256(base.encode("utf-8")).hexdigest()
