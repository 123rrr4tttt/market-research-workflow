from __future__ import annotations

import re
from typing import Any

_REASON_CODE_RE = re.compile(r"[^a-z0-9_]+")

REASON_CODE_CATALOG: dict[str, tuple[str, ...]] = {
    "policy": (
        "robots_disallow",
        "rate_limited",
        "domain_blocked",
        "url_policy_low_value_domain",
        "url_policy_low_value_endpoint",
        "url_policy_blocked",
    ),
    "quality": (
        "content_empty",
        "content_semantic_too_short",
        "content_shell_signature",
        "content_js_template_shell",
        "content_navigation_shell",
        "search_template_results_insufficient",
        "strict_mode_quality_gate",
    ),
    "provenance": (
        "provenance_untrusted_domain",
        "provenance_missing_citation",
        "provenance_gate_rejected",
    ),
    "technical": (
        "invalid_url",
        "fetch_failed",
        "unexpected_exception",
        "crawler_pool_dispatch_failed",
        "light_filter_rejected",
    ),
}

_REASON_CATEGORY_INDEX: dict[str, str] = {
    code: category for category, codes in REASON_CODE_CATALOG.items() for code in codes
}

_REASON_ALIAS: dict[str, str] = {
    "url_policy_blocked": "domain_blocked",
    "url_policy_low_value_domain": "domain_blocked",
    "url_policy_low_value_endpoint": "domain_blocked",
    "http_429": "rate_limited",
    "too_many_requests": "rate_limited",
    "robots_txt_disallow": "robots_disallow",
}


def normalize_reason_code(reason: Any, *, default: str = "unknown_rejection_reason") -> str:
    raw = str(reason or "").strip().lower()
    if not raw:
        return default
    normalized = _REASON_CODE_RE.sub("_", raw)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    if not normalized:
        return default
    return _REASON_ALIAS.get(normalized, normalized)


def reason_category(reason: Any, *, default: str = "technical") -> str:
    code = normalize_reason_code(reason)
    return _REASON_CATEGORY_INDEX.get(code, default)
