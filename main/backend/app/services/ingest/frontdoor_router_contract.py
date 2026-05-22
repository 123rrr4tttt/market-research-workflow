from __future__ import annotations

from typing import Any, Mapping

from .gate_reason_codes import normalize_reason_code, reason_category


CONTRACT_VERSION = "ingest.frontdoor_fetch_router.v1"
TRI_STATE_STATUSES: tuple[str, ...] = ("success", "degraded_success", "failed")
ROUTER_STATES: tuple[str, ...] = (
    "http_fetch",
    "search_candidate_route",
    "needs_browser",
    "unsupported",
    "blocked",
)


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _clean_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _normalize_status(value: Any, *, router_state: str) -> str:
    raw = str(value or "").strip().lower()
    if raw in TRI_STATE_STATUSES:
        return raw
    if router_state in {"blocked", "unsupported"}:
        return "failed"
    if router_state == "needs_browser":
        return "degraded_success"
    return "success"


def _normalize_router_state(
    value: Any,
    *,
    fetch_strategy: str | None,
    render_required: bool,
    high_js: bool,
) -> str:
    raw = str(value or "").strip().lower()
    if raw in ROUTER_STATES:
        return raw
    if raw in {"high_js", "browser_required", "browser_render"}:
        return "needs_browser"
    if raw in {"deny", "denied", "policy_blocked"}:
        return "blocked"
    if raw in {"unsupported_fetch_strategy", "unsupported_channel"}:
        return "unsupported"
    if high_js or render_required or fetch_strategy == "browser_render":
        return "needs_browser"
    if fetch_strategy == "search_candidate_route":
        return "search_candidate_route"
    return "http_fetch"


def _default_reason_code(router_state: str, reason_code: Any) -> str:
    explicit = normalize_reason_code(reason_code, default="")
    if explicit:
        return explicit
    if router_state == "needs_browser":
        return "needs_browser_runtime"
    if router_state == "unsupported":
        return "unsupported_fetch_strategy"
    if router_state == "blocked":
        return "domain_blocked"
    return "ok"


def _default_fallback_boundary(
    *,
    router_state: str,
    fetch_strategy: str | None,
    fallback_fetch_strategy: str | None,
) -> dict[str, Any]:
    return {
        "http_fetch_allowed": router_state in {"http_fetch", "search_candidate_route"},
        "browser_fetch_required": router_state == "needs_browser",
        "crawler_provider_allowed": router_state == "needs_browser",
        "http_fetch_fallback_allowed": router_state not in {"needs_browser", "unsupported", "blocked"},
        "fallback_fetch_strategy": fallback_fetch_strategy,
        "legacy_url_only_write_allowed": False,
        "public_browser_replay_performed": False,
        "boundary_reason": "body_only_after_fetch" if fetch_strategy else "router_contract_only",
    }


def build_frontdoor_fetch_router_contract(
    *,
    route_hint: str | None = None,
    fetch_strategy: str | None = None,
    router_state: str | None = None,
    status: str | None = None,
    reason_code: Any = None,
    retryable: bool = False,
    render_required: bool = False,
    high_js: bool = False,
    search_like: bool = False,
    fallback_fetch_strategy: str | None = None,
    fallback_boundary: Mapping[str, Any] | None = None,
    diagnostics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_fetch_strategy = _clean_text(fetch_strategy)
    normalized_router_state = _normalize_router_state(
        router_state,
        fetch_strategy=normalized_fetch_strategy,
        render_required=bool(render_required),
        high_js=bool(high_js),
    )
    normalized_reason = _default_reason_code(normalized_router_state, reason_code)
    boundary = _default_fallback_boundary(
        router_state=normalized_router_state,
        fetch_strategy=normalized_fetch_strategy,
        fallback_fetch_strategy=_clean_text(fallback_fetch_strategy),
    )
    if isinstance(fallback_boundary, Mapping):
        boundary.update(dict(fallback_boundary))

    return {
        "contract_version": CONTRACT_VERSION,
        "tri_state_statuses": list(TRI_STATE_STATUSES),
        "dashboard_status": _normalize_status(status, router_state=normalized_router_state),
        "router_state": normalized_router_state,
        "route_hint": _clean_text(route_hint),
        "fetch_strategy": normalized_fetch_strategy,
        "reason_code": normalized_reason,
        "reason_category": "none" if normalized_reason == "ok" else reason_category(normalized_reason),
        "retryable": bool(retryable),
        "render_required": bool(render_required),
        "high_js": bool(high_js),
        "search_like": bool(search_like),
        "fallback_boundary": boundary,
        "diagnostics": dict(diagnostics or {}),
    }


def router_contract_from_profile(profile: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(profile, Mapping):
        return None
    existing = profile.get("router_contract")
    if isinstance(existing, Mapping):
        return dict(existing)
    return build_frontdoor_fetch_router_contract(
        route_hint=_clean_text(profile.get("route_hint")),
        fetch_strategy=_clean_text(profile.get("fetch_strategy")),
        render_required=_as_bool(profile.get("render_required"), False),
        high_js=_as_bool(profile.get("high_js"), False),
        search_like=_as_bool(profile.get("search_like"), False),
        fallback_fetch_strategy=_clean_text(profile.get("fallback_fetch_strategy")),
        diagnostics={"source": "frontdoor_route_profile"},
    )


__all__ = [
    "CONTRACT_VERSION",
    "ROUTER_STATES",
    "TRI_STATE_STATUSES",
    "build_frontdoor_fetch_router_contract",
    "router_contract_from_profile",
]
