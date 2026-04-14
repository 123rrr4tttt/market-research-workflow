from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

_STATIC_ASSET_SUFFIXES = (
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".svg",
    ".gif",
    ".css",
    ".js",
    ".ico",
    ".woff",
    ".woff2",
    ".pdf",
    ".zip",
)
_SEARCH_NOISE_HOST_MARKERS = (
    "googleusercontent.com",
    "gstatic.com",
    "google-analytics.com",
    "googletagmanager.com",
    "fonts.googleapis.com",
    "fonts.gstatic.com",
    "w3.org",
)
_SEARCH_NOISE_DOMAINS = {
    "news.google.com",
    "ogs.google.com",
    "support.google.com",
    "policies.google.com",
}

def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return bool(default)


def _clamp_int(value: Any, default: int, *, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = int(default)
    return max(min_value, min(max_value, parsed))


def normalize_light_filter_options(raw: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(raw or {})
    return {
        "light_filter_enabled": _as_bool(payload.get("light_filter_enabled"), True),
        "light_filter_min_score": _clamp_int(payload.get("light_filter_min_score"), 30, min_value=0, max_value=100),
        "light_filter_reject_static_assets": _as_bool(payload.get("light_filter_reject_static_assets"), True),
        "light_filter_reject_search_noise_domain": _as_bool(payload.get("light_filter_reject_search_noise_domain"), True),
    }


def build_light_filter_not_run(reason: str = "not_evaluated") -> dict[str, Any]:
    return {
        "filter_decision": "not_run",
        "filter_reason_code": str(reason or "not_evaluated"),
        "filter_score": 100,
        "keep_for_vectorization": True,
        "diagnostics": {},
    }


def apply_light_filter_fields(result: dict[str, Any], light_filter: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(light_filter or build_light_filter_not_run())
    if not isinstance(result, dict):
        return result
    result["light_filter"] = payload
    result["filter_decision"] = str(payload.get("filter_decision") or "not_run")
    result["filter_reason_code"] = str(payload.get("filter_reason_code") or "unknown")
    result["filter_score"] = int(payload.get("filter_score") or 0)
    result["keep_for_vectorization"] = bool(payload.get("keep_for_vectorization"))
    return result


def evaluate_light_filter(
    *,
    url: str,
    title: str,
    snippet: str,
    source_domain: str,
    http_status: int,
    entry_type: str,
    options: dict[str, Any],
    search_noise_domains: set[str] | None = None,
    search_noise_host_markers: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    if not bool(options.get("light_filter_enabled", True)):
        return {
            "filter_decision": "allow",
            "filter_reason_code": "light_filter_disabled",
            "filter_score": 100,
            "keep_for_vectorization": True,
            "diagnostics": {"entry_type": str(entry_type or "")},
        }
    if str(entry_type or "") == "search_template":
        return {
            "filter_decision": "allow",
            "filter_reason_code": "search_template_bypass",
            "filter_score": 100,
            "keep_for_vectorization": True,
            "diagnostics": {"entry_type": str(entry_type or "")},
        }

    score = 100
    reasons: list[str] = []
    parsed = urlparse(str(url or ""))
    path = str(parsed.path or "").lower()
    domain = str(parsed.netloc or "").strip().lower() or str(source_domain or "").strip().lower()
    title_text = str(title or "").strip()
    snippet_text = str(snippet or "").strip()

    if bool(options.get("light_filter_reject_static_assets", True)) and path.endswith(_STATIC_ASSET_SUFFIXES):
        score -= 80
        reasons.append("static_asset_url")

    noise_domains = set(search_noise_domains or _SEARCH_NOISE_DOMAINS)
    noise_markers = tuple(search_noise_host_markers or _SEARCH_NOISE_HOST_MARKERS)
    if bool(options.get("light_filter_reject_search_noise_domain", True)):
        if domain in noise_domains or any(domain.endswith(marker) for marker in noise_markers):
            score -= 70
            reasons.append("search_noise_domain")

    if int(http_status or 0) >= 400:
        score -= 70
        reasons.append(f"http_status_{int(http_status)}")

    if len(title_text) < 8 and len(snippet_text) < 80:
        score -= 20
        reasons.append("sparse_preview_text")

    score = max(0, min(100, int(score)))
    min_score = int(options.get("light_filter_min_score") or 30)
    decision = "reject" if score < min_score else "allow"
    reason = reasons[0] if reasons else "ok"
    return {
        "filter_decision": decision,
        "filter_reason_code": reason,
        "filter_score": score,
        "keep_for_vectorization": decision == "allow",
        "diagnostics": {
            "min_score": min_score,
            "reasons": reasons,
            "entry_type": str(entry_type or ""),
            "domain": domain,
        },
    }


# Backward-compatible aliases for staged migration.
_build_light_filter_not_run = build_light_filter_not_run
_apply_light_filter_fields = apply_light_filter_fields
_evaluate_light_filter = evaluate_light_filter
