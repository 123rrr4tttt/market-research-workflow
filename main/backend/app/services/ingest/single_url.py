from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

from ...models.base import SessionLocal
from ...models.entities import Document, Source
from ..extraction.application import ExtractionApplicationService
from ..job_logger import complete_job, fail_job, start_job
from ..keyword_memory import record_keyword_history
from ..projects import current_project_key
from .adapters.http_utils import fetch_html, make_html_parser
from .doc_type_mapper import normalize_doc_type
from .light_filter import (
    apply_light_filter_fields,
    build_light_filter_not_run,
    evaluate_light_filter,
    normalize_light_filter_options,
)
from .meaningful_gate import content_quality_check, normalize_content_for_ingest, url_policy_check
from .url_pool import _extract_text_from_html

logger = logging.getLogger(__name__)

_SOURCE_NAME = "single_url"
_SOURCE_KIND = "url_fetch"
_DEFAULT_DOC_TYPE = "url_fetch"
_MAX_CONTENT_CHARS = 50000
_QUALITY_SUCCESS_THRESHOLD = 70.0
_CRAWLER_PROVIDER_TYPES = {"scrapy", "crawlee", "meltano"}
_SEARCH_AUTO_TARGET_CANDIDATES = 6
_SEARCH_REDIRECT_QUERY_KEYS = ("q", "url", "target", "redirect", "dest", "destination", "uddg", "u", "r")
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
_SEARCH_LOW_VALUE_PATH_MARKERS = (
    "/about",
    "/privacy",
    "/terms",
    "/login",
    "/signin",
    "/sign-in",
    "/register",
    "/account",
    "/settings",
    "/preferences",
    "/help",
    "/support",
)
_LOW_VALUE_PATH_MARKERS = (
    "/login",
    "/signin",
    "/sign-in",
    "/signup",
    "/sign-up",
    "/register",
    "/privacy",
    "/terms",
    "/about",
    "/account",
    "/settings",
    "/subscribe",
    "/topics",
)
_HIGH_JS_DOMAINS = {
    "x.com",
    "twitter.com",
    "instagram.com",
    "facebook.com",
    "linkedin.com",
    "tiktok.com",
}
_CRAWLER_FORCE_DOMAINS = {
    "reddit.com",
    "www.reddit.com",
}

_EXTRACTION_APP = ExtractionApplicationService()
_SCRIPT_NOISE_MARKERS = (
    "sourcemappingurl",
    "window.",
    "document.",
    "addeventlistener(",
    "function(",
    "var ",
    "<![cdata[",
    "wiz_progress",
)
_NAV_NOISE_MARKERS = (
    "skip to content",
    "privacy",
    "terms",
    "accessibility help",
    "more menu",
    "sign in",
    "cookie",
    "settings",
    "your account",
)
_NAV_TITLE_MARKERS = (
    "skip to content",
    "more menu",
    "accessibility help",
    "home news sport",
    "privacy",
    "terms",
)
_GITHUB_SHELL_MARKERS = (
    "navigation menu",
    "search or jump to",
    "saved searches",
    "stargazers",
    "pull requests",
    "issues",
)
_GITHUB_INTERMEDIATE_PAGE_TYPES = {
    "repo_root",
    "stargazers",
    "issues",
    "pulls",
    "pull",
    "network",
    "forks",
    "actions",
    "projects",
    "security",
}
_MOJIBAKE_MARKERS = ("Ã", "Â", "�", "â€”", "â€œ", "â€", "è", "æ", "é©¾")
_SCRIPT_SHELL_MARKERS = ("window.", "document.", "sourcemappingurl", "addeventlistener(", "var ", "function(")


def _safe_exc(exc: Exception) -> str:
    msg = str(exc).strip() or exc.__class__.__name__
    if exc.__class__.__name__ in msg:
        return msg
    return f"{exc.__class__.__name__}: {msg}"


def _normalized_terms(query_terms: list[str] | None) -> list[str]:
    if not isinstance(query_terms, list):
        return []
    return [str(x).strip() for x in query_terms if str(x or "").strip()]


def _normalize_url(url: str) -> str:
    return str(url or "").strip()


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


def _normalize_search_options(search_options: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(search_options or {})
    target_candidates = _clamp_int(raw.get("target_candidates"), _SEARCH_AUTO_TARGET_CANDIDATES, min_value=1, max_value=20)
    min_results = raw.get("min_results_required")
    min_results_required = _clamp_int(
        min_results,
        target_candidates if min_results is None else int(min_results),
        min_value=1,
        max_value=20,
    )
    out = {
        "search_expand": _as_bool(raw.get("search_expand"), True),
        "search_expand_limit": _clamp_int(raw.get("search_expand_limit"), 3, min_value=1, max_value=20),
        "search_provider": str(raw.get("search_provider") or "auto").strip().lower(),
        "search_fallback_provider": str(raw.get("search_fallback_provider") or "ddg_html").strip().lower(),
        "fallback_on_insufficient": _as_bool(raw.get("fallback_on_insufficient"), True),
        "allow_search_summary_write": _as_bool(raw.get("allow_search_summary_write"), False),
        "decode_redirect_wrappers": _as_bool(raw.get("decode_redirect_wrappers"), True),
        "filter_low_value_candidates": _as_bool(raw.get("filter_low_value_candidates"), True),
        "target_candidates": target_candidates,
        "min_results_required": min_results_required,
        "prefer_domain_diversity": _as_bool(raw.get("prefer_domain_diversity"), True),
    }
    out.update(normalize_light_filter_options(raw))
    return out


# Backward-compatible aliases for unit tests and staged migration.
_build_light_filter_not_run = build_light_filter_not_run
_apply_light_filter_fields = apply_light_filter_fields
_evaluate_light_filter = evaluate_light_filter


def _build_search_auto_config(url: str, query_terms: list[str], options: dict[str, Any] | None = None) -> dict[str, Any]:
    parsed = urlparse(str(url or ""))
    domain = str(parsed.netloc or "").strip().lower()
    normalized_options = _normalize_search_options(options)
    looks_search = bool(
        any(domain.endswith(d) for d in ("google.com", "bing.com", "duckduckgo.com", "yahoo.com"))
        or "/search" in str(parsed.path or "").lower()
        or any(k in {"q", "query", "keyword", "keywords", "search"} for k in parse_qs(parsed.query or ""))
    )
    default_min = int(normalized_options.get("target_candidates") or _SEARCH_AUTO_TARGET_CANDIDATES) if (looks_search and query_terms) else 3
    min_results_required = _clamp_int(
        normalized_options.get("min_results_required"),
        default_min,
        min_value=1,
        max_value=20,
    )
    return {
        "decode_redirect_wrappers": bool(normalized_options.get("decode_redirect_wrappers", True)),
        "filter_low_value_candidates": bool(normalized_options.get("filter_low_value_candidates", True)),
        "target_candidates": _clamp_int(
            normalized_options.get("target_candidates"),
            _SEARCH_AUTO_TARGET_CANDIDATES,
            min_value=1,
            max_value=20,
        ),
        "min_results_required": int(min_results_required),
        "source_domain": domain,
    }


def _is_valid_http_url(url: str) -> bool:
    try:
        p = urlparse(url)
    except Exception:
        return False
    return bool(p.scheme in {"http", "https"} and p.netloc)


def _infer_entry_type(url: str) -> str:
    p = urlparse(url)
    path = (p.path or "").lower()
    query = parse_qs(p.query or "")
    if path.endswith(".xml") or "sitemap" in path:
        return "sitemap"
    if "/rss" in path or "/feed" in path or "rss.xml" in path or "atom.xml" in path:
        return "rss"
    if path.startswith("/api/") or p.netloc.lower().startswith("api."):
        return "official_api"
    if "/search" in path:
        return "search_template"
    if any(k in {"q", "query", "keyword", "keywords", "search"} for k in query):
        return "search_template"
    if path in {"", "/"}:
        return "domain_root"
    return "detail"


def _profile_url_capabilities(url: str) -> dict[str, Any]:
    p = urlparse(url)
    domain = (p.netloc or "").lower()
    path = (p.path or "").lower()
    entry_type = _infer_entry_type(url)
    render_mode = "js" if any(domain.endswith(d) for d in _HIGH_JS_DOMAINS) else "static"
    anti_bot_risk = "high" if render_mode == "js" else "low"
    auth_required = any(marker in path for marker in ("/login", "/signin", "/register", "/account"))
    return {
        "entry_type": entry_type,
        "render_mode": render_mode,
        "anti_bot_risk": anti_bot_risk,
        "auth_required": auth_required,
        "domain": domain,
    }


def _allocate_fetch_tier(capability: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    flags: list[str] = []
    entry_type = str(capability.get("entry_type") or "")
    render_mode = str(capability.get("render_mode") or "static")
    anti_bot_risk = str(capability.get("anti_bot_risk") or "low")

    planned_handler = "native_http"
    fetch_tier = "tier_1_native_http"
    fallback_reason = None

    if entry_type == "official_api":
        planned_handler = "official_api"
        fetch_tier = "tier_0_official_api"
        # Keep minimal-invasive implementation: still run through native_http fetch.
        fallback_reason = "official_api_handler_unavailable"
        flags.append("official_api_handler_unavailable")
    elif render_mode == "js" or anti_bot_risk == "high":
        planned_handler = "browser_render"
        fetch_tier = "tier_2_browser_render"
        fallback_reason = "browser_render_handler_unavailable"
        flags.append("browser_render_handler_unavailable")

    return (
        {
            "planned_handler": planned_handler,
            "handler_used": "native_http",
            "fetch_tier": fetch_tier,
            "fallback_reason": fallback_reason,
        },
        flags,
    )


def _is_crawler_channel(channel: dict[str, Any] | None) -> bool:
    if not isinstance(channel, dict):
        return False
    provider_type = str(channel.get("provider_type") or "").strip().lower()
    return provider_type in _CRAWLER_PROVIDER_TYPES


def _pick_crawler_channel(
    *,
    url: str,
    query_terms: list[str],
    project_key: str | None,
) -> tuple[str, dict[str, Any]] | None:
    from ..source_library.resolver import list_effective_channels
    from ..source_library.url_router import resolve_channel_for_url

    channels = list_effective_channels(scope="effective", project_key=project_key)
    channel_map = {str(x.get("channel_key") or ""): x for x in channels if isinstance(x, dict)}
    has_query_terms = bool(query_terms)
    routed_key = resolve_channel_for_url(url, project_key, has_query_terms=has_query_terms)
    routed = channel_map.get(str(routed_key or ""))
    if routed and routed.get("enabled", True) and _is_crawler_channel(routed):
        return str(routed_key), routed

    project_norm = str(project_key or "").strip().lower()
    candidates: list[tuple[str, dict[str, Any]]] = []
    for key, channel in channel_map.items():
        if not key or not channel.get("enabled", True) or not _is_crawler_channel(channel):
            continue
        candidates.append((key, channel))
    if not candidates:
        return None

    def _score(pair: tuple[str, dict[str, Any]]) -> tuple[int, str]:
        key = pair[0].lower()
        if project_norm and key == f"crawler.{project_norm}":
            return (0, key)
        if project_norm and key.startswith(f"crawler.{project_norm}."):
            return (1, key)
        if key.startswith("crawler."):
            return (2, key)
        return (3, key)

    return sorted(candidates, key=_score)[0]


def _dispatch_via_crawler_pool(
    *,
    channel_key: str,
    channel: dict[str, Any],
    url: str,
    query_terms: list[str],
    project_key: str | None,
) -> dict[str, Any]:
    from ..source_library.runner import run_channel

    params = dict((channel.get("default_params") or {}) if isinstance(channel, dict) else {})
    params["url"] = url
    params["urls"] = [url]
    params.setdefault("auto_ingest_crawler_output", True)
    params.setdefault("crawler_output_enable_extraction", True)
    params.setdefault("crawler_output_doc_type", "url_fetch")
    params.setdefault("crawler_output_max_items", 5)
    if query_terms:
        params["query_terms"] = query_terms
    arguments = dict(params.get("arguments") or {})
    arguments.setdefault("url", url)
    arguments.setdefault("urls", [url])
    if query_terms:
        arguments.setdefault("query_terms", "\n".join(query_terms))
    params["arguments"] = arguments
    raw = run_channel(
        channel=channel,
        params=params,
        project_key=project_key,
        item_key=None,
    )
    out = dict(raw if isinstance(raw, dict) else {})
    out["channel_key"] = channel_key
    return out


def _extract_crawler_output_doc_ids(crawler_result: dict[str, Any]) -> list[int]:
    output_ingest = crawler_result.get("output_ingest")
    if not isinstance(output_ingest, dict):
        return []
    import_result = output_ingest.get("import_result")
    if not isinstance(import_result, dict):
        return []
    out: list[int] = []
    for row in import_result.get("items") or []:
        if not isinstance(row, dict):
            continue
        try:
            doc_id = int(row.get("doc_id"))
        except Exception:
            continue
        if doc_id not in out:
            out.append(doc_id)
    return out


def _is_meaningful_content_text(text: str) -> tuple[bool, str]:
    decision = content_quality_check(
        uri="",
        content=text,
        doc_type="url_fetch",
        extraction_status=None,
        config={"enable_strict_gate": True},
    )
    return bool(decision.accepted), str(decision.reason)


def _has_structured_signal(extracted_data: dict[str, Any]) -> bool:
    summary = extracted_data.get("_structured_summary")
    if not isinstance(summary, dict):
        return False
    if not bool(summary.get("extraction_enabled")):
        return False
    entity_count = int(summary.get("entity_count") or 0)
    if entity_count >= 3:
        return True
    for key in ("has_company", "has_product", "has_operation", "has_sentiment", "has_market", "has_policy"):
        if bool(summary.get(key)):
            return True
    return False


def _looks_like_navigation_shell(*, title: str, content: str) -> tuple[bool, str]:
    title_l = str(title or "").strip().lower()
    head_l = str(content or "")[:800].strip().lower()
    title_hits = sum(1 for marker in _NAV_TITLE_MARKERS if marker in title_l)
    if title_hits >= 2:
        return True, "navigation_shell_title"
    head_hits = sum(1 for marker in _NAV_NOISE_MARKERS if marker in head_l)
    if head_hits >= 4:
        return True, "navigation_shell_head"
    return False, "ok"


def _domain_of_url(url: str) -> str:
    try:
        return str(urlparse(url).netloc or "").strip().lower()
    except Exception:
        return ""


def _is_force_crawler_domain(url: str) -> bool:
    domain = _domain_of_url(url)
    if not domain:
        return False
    return domain in _CRAWLER_FORCE_DOMAINS


def _extract_github_structured_content(url: str, html: str, raw_content: str) -> dict[str, Any] | None:
    domain = _domain_of_url(url)
    if not domain.endswith("github.com"):
        return None
    path = str(urlparse(url).path or "").strip("/")
    segs = [x for x in path.split("/") if x]
    if len(segs) < 2:
        return None
    owner = segs[0]
    repo = segs[1]
    page_type = segs[2] if len(segs) >= 3 else "repo_root"

    parser = make_html_parser(html or "")
    og_title = ""
    og_title_node = parser.css_first("meta[property='og:title']")
    if og_title_node is not None:
        og_title = str(og_title_node.attributes.get("content") or "").strip()
    meta_desc = ""
    desc_node = parser.css_first("meta[name='description']")
    if desc_node is not None:
        meta_desc = str(desc_node.attributes.get("content") or "").strip()

    raw_lower = str(raw_content or "").lower()
    marker_hits = sum(1 for marker in _GITHUB_SHELL_MARKERS if marker in raw_lower)
    if marker_hits < 2 and not meta_desc:
        return None

    stars = None
    forks = None
    m_stars = re.search(r"([0-9][0-9,]*)\s+stars", raw_lower)
    if m_stars:
        stars = m_stars.group(1)
    m_forks = re.search(r"([0-9][0-9,]*)\s+forks", raw_lower)
    if m_forks:
        forks = m_forks.group(1)

    lines = [
        f"Source: GitHub repository page",
        f"Repository: {owner}/{repo}",
        f"Page type: {page_type}",
        f"URL: {url}",
    ]
    if meta_desc:
        lines.append(f"Description: {meta_desc}")
    if stars:
        lines.append(f"Stars: {stars}")
    if forks:
        lines.append(f"Forks: {forks}")
    if og_title:
        lines.append(f"Page title: {og_title}")
    structured_content = "\n".join(lines)
    title = og_title or f"{owner}/{repo} ({page_type}) - GitHub"
    return {
        "title": title,
        "content": structured_content,
        "metadata": {
            "domain_parser": "github_repo_page",
            "repo_owner": owner,
            "repo_name": repo,
            "repo_page_type": page_type,
            "shell_marker_hits": marker_hits,
        },
    }


def _contains_mojibake(text: str) -> bool:
    sample = str(text or "")
    if not sample:
        return False
    return any(marker in sample for marker in _MOJIBAKE_MARKERS)


def _is_script_heavy_shell(content: str) -> bool:
    head = str(content or "")[:2500].lower()
    if not head:
        return False
    marker_hits = sum(head.count(marker) for marker in _SCRIPT_SHELL_MARKERS)
    return marker_hits >= 4


def _provenance_dirty_decision(
    *,
    url: str,
    title: str,
    content: str,
    domain_specific_metadata: dict[str, Any] | None,
) -> tuple[bool, str, dict[str, Any]]:
    parsed = urlparse(str(url or ""))
    domain = str(parsed.netloc or "").strip().lower()
    path = str(parsed.path or "").strip().lower()
    metadata = dict(domain_specific_metadata or {})

    if domain == "api.github.com" and path.startswith("/repos/"):
        return True, "github_api_intermediate", {"domain": domain, "path": path}

    if domain in {"html.duckduckgo.com", "duckduckgo.com", "www.duckduckgo.com"}:
        if path.startswith("/html") or path.startswith("/l/") or path in {"", "/"}:
            return True, "ddg_intermediate_page", {"domain": domain, "path": path}
        query = parse_qs(parsed.query or "")
        if any(k in {"q", "ia", "iax"} for k in query.keys()):
            return True, "ddg_intermediate_page", {"domain": domain, "path": path}

    if domain.endswith("github.com"):
        if path in {"", "/"} or "/search" in path or "/topics" in path or "/marketplace" in path:
            return True, "github_navigation_intermediate", {"domain": domain, "path": path}
        if str(metadata.get("domain_parser") or "") == "github_repo_page":
            page_type = str(metadata.get("repo_page_type") or "").strip().lower()
            if page_type in _GITHUB_INTERMEDIATE_PAGE_TYPES:
                return True, "github_repo_intermediate", {"domain": domain, "path": path, "repo_page_type": page_type}

    if _contains_mojibake(title) and _is_script_heavy_shell(content):
        return True, "mojibake_script_shell", {"domain": domain, "path": path}

    return False, "ok", {"domain": domain, "path": path}


def _validate_crawler_output_docs(doc_ids: list[int], *, require_structured_signal: bool = False) -> dict[str, Any]:
    if not doc_ids:
        return {"passed_ids": [], "failed_ids": [], "reasons": {"missing_doc_ids": 1}}
    passed_ids: list[int] = []
    failed_ids: list[int] = []
    reasons: dict[str, int] = {}
    with SessionLocal() as session:
        for doc_id in doc_ids:
            doc = session.query(Document).filter(Document.id == int(doc_id)).first()
            if doc is None:
                failed_ids.append(int(doc_id))
                reasons["doc_not_found"] = int(reasons.get("doc_not_found", 0)) + 1
                continue
            uri_gate = url_policy_check(str(doc.uri or ""))
            if uri_gate.blocked:
                failed_ids.append(int(doc_id))
                reason = str(uri_gate.reason or "url_policy_blocked")
                reasons[reason] = int(reasons.get(reason, 0)) + 1
                continue
            ok, reason = _is_meaningful_content_text(str(doc.content or ""))
            if not ok:
                failed_ids.append(int(doc_id))
                reasons[reason] = int(reasons.get(reason, 0)) + 1
                continue
            nav_shell, nav_reason = _looks_like_navigation_shell(title=str(doc.title or ""), content=str(doc.content or ""))
            if nav_shell:
                failed_ids.append(int(doc_id))
                reasons[nav_reason] = int(reasons.get(nav_reason, 0)) + 1
                continue
            if require_structured_signal:
                extracted_data = doc.extracted_data if isinstance(doc.extracted_data, dict) else {}
                if not _has_structured_signal(extracted_data):
                    failed_ids.append(int(doc_id))
                    reasons["no_structured_signal"] = int(reasons.get("no_structured_signal", 0)) + 1
                    continue
            passed_ids.append(int(doc_id))
    return {"passed_ids": passed_ids, "failed_ids": failed_ids, "reasons": reasons}


def _classify_page_type(url: str, html: str, content: str) -> tuple[str, bool, str | None]:
    lu = str(url or "").lower()
    if any(marker in lu for marker in _LOW_VALUE_PATH_MARKERS):
        return "low_value", True, "low_value_path_marker"

    parser = make_html_parser(html or "")
    body_text = (content or "").strip()
    words = len(body_text.split())
    link_count = len(parser.css("a"))

    if parser.css_first("input[type='password']") is not None:
        return "login", True, "password_input_detected"
    if words < 80:
        return "nav", True, "content_too_short"
    if link_count > 80 and words < 400:
        return "list", True, "link_heavy_list_page"
    if ("/search" in lu or "query=" in lu or "q=" in lu) and words < 500:
        return "search_shell", True, "search_shell_like"
    if urlparse(url).path in {"", "/"} and words < 700:
        return "homepage", True, "home_like_low_information"
    return "detail", False, None


def _is_low_value_search_candidate(url: str, *, source_domain: str = "") -> bool:
    parsed = urlparse(str(url or "").strip())
    domain = str(parsed.netloc or "").strip().lower()
    if not domain:
        return True
    if domain == source_domain:
        return True
    if domain in _SEARCH_NOISE_DOMAINS:
        return True
    if any(domain.endswith(marker) for marker in _SEARCH_NOISE_HOST_MARKERS):
        return True
    path = str(parsed.path or "").lower()
    if path in {"", "/"}:
        return True
    if any(marker in path for marker in _SEARCH_LOW_VALUE_PATH_MARKERS):
        return True
    if path.endswith((".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif", ".css", ".js", ".ico", ".woff", ".woff2")):
        return True
    return False


def _unwrap_search_redirect_url(url: str) -> str:
    current = str(url or "").strip()
    for _ in range(2):
        parsed = urlparse(current)
        query = parse_qs(parsed.query or "")
        candidate = None
        for key in _SEARCH_REDIRECT_QUERY_KEYS:
            value = (query.get(key) or [None])[0]
            if value:
                candidate = str(value).strip()
                break
        if not candidate:
            break
        decoded = unquote(candidate).strip()
        if not decoded or decoded == current:
            break
        current = decoded
    return current


def _normalize_search_result_link(base_url: str, href: str, *, auto_config: dict[str, Any] | None = None) -> str | None:
    raw = str(href or "").strip()
    if not raw or raw.startswith("#") or raw.lower().startswith("javascript:"):
        return None
    abs_url = urljoin(base_url, raw)
    if bool((auto_config or {}).get("decode_redirect_wrappers", True)):
        abs_url = _unwrap_search_redirect_url(abs_url)
    parsed = urlparse(str(abs_url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    source_domain = str((auto_config or {}).get("source_domain") or "").strip().lower()
    if bool((auto_config or {}).get("filter_low_value_candidates", True)) and _is_low_value_search_candidate(
        abs_url,
        source_domain=source_domain,
    ):
        return None
    return str(abs_url).strip()


def _query_text_from_url(url: str) -> str:
    try:
        query = parse_qs(urlparse(str(url or "")).query or "")
    except Exception:
        query = {}
    for key in ("q", "query", "keyword", "keywords", "search"):
        value = (query.get(key) or [None])[0]
        if value:
            text = str(value).strip()
            if text:
                return text
    return ""


def _build_search_fallback_url(
    *,
    source_url: str,
    query_terms: list[str],
    provider: str,
) -> str | None:
    provider_norm = str(provider or "").strip().lower()
    query_text = " ".join(query_terms).strip() or _query_text_from_url(source_url)
    if not query_text:
        return None
    if provider_norm in {"ddg", "ddg_html", "duckduckgo", "duckduckgo_html"}:
        return f"https://html.duckduckgo.com/html/?q={quote_plus(query_text)}"
    return None


def _merge_search_result_payload(base: dict[str, Any], incoming: dict[str, Any], *, max_items: int) -> dict[str, Any]:
    merged_items: list[dict[str, str]] = []
    seen: set[str] = set()
    for payload in (base, incoming):
        for row in list(payload.get("items") or []):
            if not isinstance(row, dict):
                continue
            u = str(row.get("url") or "").strip()
            if not u or u in seen:
                continue
            seen.add(u)
            merged_items.append(
                {
                    "title": str(row.get("title") or "")[:300],
                    "url": u,
                    "snippet": str(row.get("snippet") or "")[:500],
                }
            )
            if len(merged_items) >= max_items:
                break
        if len(merged_items) >= max_items:
            break

    summary_lines = []
    for idx, item in enumerate(merged_items, start=1):
        line = f"{idx}. {item['title']} | {item['url']}"
        if item.get("snippet"):
            line = f"{line} | {item['snippet']}"
        summary_lines.append(line)
    summary_text = "\n".join(summary_lines)
    return {
        "items": merged_items,
        "result_count": len(merged_items),
        "summary_text": summary_text,
        "snippet_chars": len(summary_text),
        "auto_config": dict(base.get("auto_config") or incoming.get("auto_config") or {}),
    }


def _extract_search_results(url: str, html: str, *, auto_config: dict[str, Any] | None = None) -> dict[str, Any]:
    parser = make_html_parser(html or "")
    items: list[dict[str, str]] = []
    seen: set[str] = set()

    def _push(href: str | None, title: str, snippet: str) -> None:
        normalized = _normalize_search_result_link(url, href or "", auto_config=auto_config)
        if not normalized or normalized in seen:
            return
        title_text = str(title or "").strip()
        snippet_text = str(snippet or "").strip()
        if len(title_text) < 8:
            return
        seen.add(normalized)
        items.append({"title": title_text[:300], "url": normalized, "snippet": snippet_text[:500]})

    for card in parser.css("div.g, li.b_algo, li.arxiv-result, .result, article[data-testid='result'], li[class*='result']"):
        title_node = card.css_first("h3, h2, p.title, a[data-testid='result-title-a']")
        link_node = (
            title_node.css_first("a[href]")
            if title_node is not None
            else card.css_first("p.list-title a[href], a.result__a, a[href]")
        )
        if link_node is None:
            link_node = card.css_first("p.list-title a[href], a.result__a, a[href]")
        if link_node is None:
            continue
        href = str(link_node.attributes.get("href") or "").strip()
        title = title_node.text(strip=True) if title_node is not None else link_node.text(strip=True)
        snippet_node = card.css_first("span.abstract-full, span.abstract-short, div.VwiC3b, .b_caption p, .result__snippet, p")
        snippet = snippet_node.text(strip=True) if snippet_node is not None else ""
        _push(href, title, snippet)
        if len(items) >= 10:
            break

    if len(items) < 3:
        for link_node in parser.css("h3 a[href], h2 a[href]"):
            href = str(link_node.attributes.get("href") or "").strip()
            title = link_node.text(strip=True)
            snippet = ""
            parent = getattr(link_node, "parent", None)
            if parent is not None:
                snippet = parent.text(strip=True)
            _push(href, title, snippet)
            if len(items) >= 10:
                break

    summary_lines = []
    for idx, item in enumerate(items, start=1):
        line = f"{idx}. {item['title']} | {item['url']}"
        if item.get("snippet"):
            line = f"{line} | {item['snippet']}"
        summary_lines.append(line)
    summary_text = "\n".join(summary_lines)
    return {
        "items": items,
        "result_count": len(items),
        "summary_text": summary_text,
        "snippet_chars": len(summary_text),
        "auto_config": dict(auto_config or {}),
    }


def _content_line_is_noise(line: str) -> bool:
    text = str(line or "").strip().lower()
    if not text:
        return True
    nav_hits = sum(1 for marker in _NAV_NOISE_MARKERS if marker in text)
    script_hits = sum(1 for marker in _SCRIPT_NOISE_MARKERS if marker in text)
    if nav_hits >= 2:
        return True
    if script_hits >= 2:
        return True
    if len(text) <= 2:
        return True
    return False


def _preprocess_content_for_quality(*, url: str, title: str, html: str, content: str) -> str:
    lines = [str(x or "").strip() for x in str(content or "").splitlines()]
    filtered: list[str] = []
    for line in lines:
        if _content_line_is_noise(line):
            continue
        filtered.append(line)
        if len(filtered) >= 1200:
            break
    cleaned = "\n".join(filtered).strip()

    # Fallback enrichers for sparse pages: use meta description and heading text.
    if len(cleaned) < 300:
        try:
            parser = make_html_parser(html or "")
            extra_bits: list[str] = []
            meta_desc = ""
            desc_node = parser.css_first("meta[name='description']")
            if desc_node is not None:
                meta_desc = str(desc_node.attributes.get("content") or "").strip()
            if meta_desc and not _content_line_is_noise(meta_desc):
                extra_bits.append(meta_desc)
            for selector in ("h1", "main h1", "article h1", "h2", "main h2", "article h2"):
                node = parser.css_first(selector)
                if node is None:
                    continue
                heading = str(node.text(strip=True) or "").strip()
                if heading and not _content_line_is_noise(heading):
                    extra_bits.append(heading)
                if len(extra_bits) >= 3:
                    break
            if title and not _content_line_is_noise(title):
                extra_bits.insert(0, str(title).strip())
            if extra_bits:
                merged = "\n".join([x for x in [cleaned, *extra_bits] if x])
                cleaned = merged.strip()
        except Exception:  # noqa: BLE001
            pass

    return normalize_content_for_ingest(cleaned, max_chars=_MAX_CONTENT_CHARS)


def _domain_of_candidate(url: str) -> str:
    try:
        return str(urlparse(str(url or "")).netloc or "").strip().lower()
    except Exception:
        return ""


def _select_search_expand_urls(items: list[dict[str, Any]], *, limit: int, prefer_domain_diversity: bool) -> list[str]:
    candidates: list[str] = []
    for row in items:
        if not isinstance(row, dict):
            continue
        u = str(row.get("url") or "").strip()
        if u and u not in candidates:
            candidates.append(u)
    if not prefer_domain_diversity:
        return candidates[:limit]

    selected: list[str] = []
    seen_domain: set[str] = set()
    for u in candidates:
        domain = _domain_of_candidate(u)
        if domain and domain in seen_domain:
            continue
        if domain:
            seen_domain.add(domain)
        selected.append(u)
        if len(selected) >= limit:
            return selected
    for u in candidates:
        if u in selected:
            continue
        selected.append(u)
        if len(selected) >= limit:
            break
    return selected


def _classify_search_expand_child_outcome(child_result: dict[str, Any]) -> str:
    inserted_valid = int(child_result.get("inserted_valid") or 0)
    if inserted_valid > 0:
        return "success"
    flags = {str(x or "").strip().lower() for x in list(child_result.get("degradation_flags") or [])}
    if "document_already_exists" in flags:
        return "duplicate"
    if "fetch_failed" in flags:
        return "fetch_failed"
    if any(
        f.startswith("low_value_page:")
        or f.startswith("light_filter_rejected:")
        or f.startswith("url_gate_rejected:")
        or f.startswith("content_gate_rejected:")
        or f.startswith("provenance_gate_rejected:")
        or f == "strict_mode_quality_gate"
        for f in flags
    ):
        return "quality_rejected"
    rb = child_result.get("rejection_breakdown")
    if isinstance(rb, dict) and rb:
        return "quality_rejected"
    return "other"


def _build_quality_score(
    *,
    content_chars: int,
    structured_extraction_status: str,
    degradation_flags: list[str],
) -> float:
    score = 100.0
    if content_chars < 800:
        score -= 20.0
    if content_chars < 300:
        score -= 20.0
    if structured_extraction_status != "ok":
        score -= 25.0
    score -= min(30.0, float(len(degradation_flags) * 8.0))
    return float(max(0.0, min(100.0, round(score, 2))))


def _get_or_create_source(session, name: str, kind: str, base_url: str | None) -> Source:
    row = session.query(Source).filter(Source.name == name, Source.kind == kind).first()
    if row:
        return row
    source = Source(name=name, kind=kind, base_url=base_url or "")
    session.add(source)
    session.flush()
    return source


def ingest_single_url(
    *,
    url: str,
    query_terms: list[str] | None = None,
    strict_mode: bool = False,
    search_options: dict[str, Any] | None = None,
    track_keyword_history: bool = True,
) -> dict[str, Any]:
    """Fetch one URL, run extraction, and return canonical single-url ingest result."""
    normalized_url = _normalize_url(url)
    normalized_terms = _normalized_terms(query_terms)
    normalized_search_options = _normalize_search_options(search_options)
    light_filter_payload = build_light_filter_not_run()
    job_id = start_job(
        "single_url",
        {
            "url": normalized_url,
            "query_terms": normalized_terms,
            "strict_mode": bool(strict_mode),
            "search_options": normalized_search_options,
        },
    )
    keyword_source_domain = _domain_of_url(normalized_url) or None
    def _record_keyword_history_for_result(result: dict[str, Any] | None) -> None:
        if not track_keyword_history or not normalized_terms or not isinstance(result, dict):
            return
        try:
            status = str(result.get("status") or "").strip() or None
            filter_decision = str(result.get("filter_decision") or "").strip() or None
            rejection_breakdown = result.get("rejection_breakdown")
            extra: dict[str, Any] = {
                "url": normalized_url,
                "job_id": int(job_id),
                "doc_type": str(result.get("doc_type") or normalize_doc_type(_DEFAULT_DOC_TYPE)),
                "chain": "single_url",
            }
            if isinstance(rejection_breakdown, dict):
                extra["rejection_breakdown"] = dict(rejection_breakdown)
            record_keyword_history(
                keywords=normalized_terms,
                source=_SOURCE_NAME,
                source_domain=keyword_source_domain,
                status=status,
                inserted=int(result.get("inserted") or 0),
                inserted_valid=int(result.get("inserted_valid") or 0),
                rejected_count=int(result.get("rejected_count") or 0),
                filter_decision=filter_decision,
                extra=extra,
            )
        except Exception as history_exc:  # noqa: BLE001
            logger.warning("record keyword history failed url=%s err=%s", normalized_url, _safe_exc(history_exc))

    def finalize_job(job_id_value: int, *, status: str, result: dict[str, Any]) -> None:
        _record_keyword_history_for_result(result)
        complete_job(job_id_value, status=status, result=result)

    try:
        if not _is_valid_http_url(normalized_url):
            result = {
                "status": "failed",
                "inserted": 0,
                "inserted_valid": 0,
                "skipped": 0,
                "url": normalized_url,
                "document_id": None,
                "doc_type": normalize_doc_type(_DEFAULT_DOC_TYPE),
                "structured_extraction_status": "failed",
                "quality_score": 0.0,
                "rejected_count": 1,
                "rejection_breakdown": {"invalid_url": 1},
                "degradation_flags": ["invalid_url"],
                "error": "invalid_url",
            }
            apply_light_filter_fields(result, light_filter_payload)
            finalize_job(job_id, status="failed", result=result)
            return result

        pre_fetch_gate = url_policy_check(normalized_url)
        if pre_fetch_gate.blocked:
            result_status = "failed" if strict_mode else "degraded_success"
            reason = str(pre_fetch_gate.reason or "url_policy_blocked")
            gate_flags = list(dict.fromkeys([reason, f"url_gate_rejected:{reason}"]))
            result = {
                "status": result_status,
                "inserted": 0,
                "inserted_valid": 0,
                "skipped": 1,
                "url": normalized_url,
                "document_id": None,
                "doc_type": normalize_doc_type(_DEFAULT_DOC_TYPE),
                "structured_extraction_status": "failed",
                "quality_score": float(pre_fetch_gate.quality_score),
                "rejected_count": 1,
                "rejection_breakdown": {reason: 1},
                "pre_fetch_url_gate": pre_fetch_gate.to_dict(),
                "degradation_flags": gate_flags,
            }
            apply_light_filter_fields(result, light_filter_payload)
            finalize_job(job_id, status="completed" if result_status != "failed" else "failed", result=result)
            return result

        capability = _profile_url_capabilities(normalized_url)
        allocation, degradation_flags = _allocate_fetch_tier(capability)
        project_key = str(current_project_key() or "").strip() or None
        should_try_crawler_pool = bool(
            capability.get("entry_type") in {"search_template", "official_api"}
            or str(capability.get("anti_bot_risk") or "").lower() == "high"
            or _is_force_crawler_domain(normalized_url)
        )

        def _try_crawler_pool(*, fallback_reason: str) -> dict[str, Any] | None:
            if not should_try_crawler_pool:
                return None
            picked = _pick_crawler_channel(
                url=normalized_url,
                query_terms=normalized_terms,
                project_key=project_key,
            )
            if picked is None:
                return None
            channel_key, channel = picked
            allocation["matched_channel_key"] = channel_key
            allocation["planned_handler"] = "crawler_pool"
            try:
                crawler_result = _dispatch_via_crawler_pool(
                    channel_key=channel_key,
                    channel=channel,
                    url=normalized_url,
                    query_terms=normalized_terms,
                    project_key=project_key,
                )
                allocation["handler_used"] = "crawler_pool"
                allocation["crawler_provider_type"] = str(crawler_result.get("provider_type") or "")
                allocation["crawler_provider_status"] = str(crawler_result.get("provider_status") or "")
                inserted = int(crawler_result.get("inserted") or 0)
                updated = int(crawler_result.get("updated") or 0)
                skipped = int(crawler_result.get("skipped") or 0)
                if inserted + updated <= 0:
                    degradation_flags.append("crawler_pool_no_immediate_output")
                    return None
                output_doc_ids = _extract_crawler_output_doc_ids(crawler_result)
                validation = _validate_crawler_output_docs(
                    output_doc_ids,
                    require_structured_signal=bool(capability.get("entry_type") == "search_template"),
                )
                valid_doc_ids = list(validation.get("passed_ids") or [])
                if not valid_doc_ids:
                    degradation_flags.append("crawler_pool_low_quality_output")
                    allocation["crawler_quality_reasons"] = validation.get("reasons") or {}
                    return None
                crawler_result_payload = {
                    "status": "success",
                    "inserted": inserted,
                    "inserted_valid": len(valid_doc_ids),
                    "updated": updated,
                    "skipped": skipped,
                    "url": normalized_url,
                    "document_id": None,
                    "doc_type": normalize_doc_type(_DEFAULT_DOC_TYPE),
                    "capability_profile": capability,
                    "handler_allocation": allocation,
                    "page_gate": {
                        "page_type": "crawler_pool",
                        "is_low_value": False,
                        "reason": fallback_reason,
                    },
                    "structured_extraction_status": "ok",
                    "quality_score": 100.0,
                    "rejected_count": 0,
                    "rejection_breakdown": {},
                    "degradation_flags": list(dict.fromkeys(degradation_flags)),
                    "crawler_dispatch": {
                        "provider_job_id": crawler_result.get("provider_job_id"),
                        "provider_status": crawler_result.get("provider_status"),
                        "attempt_count": crawler_result.get("attempt_count"),
                        "output_doc_ids": output_doc_ids,
                        "valid_output_doc_ids": valid_doc_ids,
                    },
                }
                return apply_light_filter_fields(crawler_result_payload, light_filter_payload)
            except Exception as ex:  # noqa: BLE001
                degradation_flags.append("crawler_pool_dispatch_failed")
                allocation["crawler_dispatch_error"] = _safe_exc(ex)
                return None

        try:
            html, response = fetch_html(normalized_url, timeout=20.0, retries=2)
        except Exception as fetch_exc:  # noqa: BLE001
            crawler_fallback_result = _try_crawler_pool(fallback_reason="native_fetch_failed")
            if crawler_fallback_result is not None:
                finalize_job(job_id, status="completed", result=crawler_fallback_result)
                return crawler_fallback_result
            result = {
                "status": "failed",
                "inserted": 0,
                "inserted_valid": 0,
                "skipped": 1,
                "url": normalized_url,
                "document_id": None,
                "doc_type": normalize_doc_type(_DEFAULT_DOC_TYPE),
                "capability_profile": capability,
                "handler_allocation": allocation,
                "structured_extraction_status": "failed",
                "quality_score": 0.0,
                "rejected_count": 1,
                "rejection_breakdown": {"fetch_failed": 1},
                "degradation_flags": list(dict.fromkeys([*degradation_flags, "fetch_failed"])),
                "error": _safe_exc(fetch_exc),
            }
            apply_light_filter_fields(result, light_filter_payload)
            finalize_job(job_id, status="failed", result=result)
            return result

        raw_content = _extract_text_from_html(html)
        content = _preprocess_content_for_quality(
            url=normalized_url,
            title="",
            html=html,
            content=raw_content,
        )
        parser = make_html_parser(html)
        title_node = parser.css_first("title")
        title = str(title_node.text(strip=True) if title_node is not None else "").strip()
        if not title:
            title = capability.get("domain") or normalized_url
        content = _preprocess_content_for_quality(
            url=normalized_url,
            title=title,
            html=html,
            content=content,
        )
        light_filter_payload = evaluate_light_filter(
            url=normalized_url,
            title=title,
            snippet=content[:240],
            source_domain=str(capability.get("domain") or ""),
            http_status=int(getattr(response, "status_code", 0) or 0),
            entry_type=str(capability.get("entry_type") or ""),
            options=normalized_search_options,
            search_noise_domains=_SEARCH_NOISE_DOMAINS,
            search_noise_host_markers=_SEARCH_NOISE_HOST_MARKERS,
        )
        if str(light_filter_payload.get("filter_decision") or "") == "reject":
            light_reason = str(light_filter_payload.get("filter_reason_code") or "light_filter_rejected")
            status = "failed" if strict_mode else "degraded_success"
            gate_flags = list(dict.fromkeys([*degradation_flags, light_reason, f"light_filter_rejected:{light_reason}"]))
            result = {
                "status": status,
                "inserted": 0,
                "inserted_valid": 0,
                "skipped": 1,
                "url": normalized_url,
                "document_id": None,
                "doc_type": normalize_doc_type(_DEFAULT_DOC_TYPE),
                "capability_profile": capability,
                "handler_allocation": allocation,
                "page_gate": {
                    "page_type": "light_filter",
                    "is_low_value": True,
                    "reason": light_reason,
                },
                "structured_extraction_status": "failed",
                "quality_score": 0.0,
                "rejected_count": 1,
                "rejection_breakdown": {light_reason: 1},
                "degradation_flags": gate_flags,
            }
            apply_light_filter_fields(result, light_filter_payload)
            finalize_job(job_id, status="completed" if status != "failed" else "failed", result=result)
            return result

        search_results_payload = None
        search_auto_config = None
        if capability.get("entry_type") == "search_template":
            search_input_url = normalized_url
            search_input_html = html
            requested_provider = str(normalized_search_options.get("search_provider") or "auto")
            if requested_provider in {"ddg", "ddg_html", "duckduckgo", "duckduckgo_html"}:
                provider_url = _build_search_fallback_url(
                    source_url=normalized_url,
                    query_terms=normalized_terms,
                    provider=requested_provider,
                )
                if provider_url and provider_url != normalized_url:
                    try:
                        provider_html, _ = fetch_html(provider_url, timeout=20.0, retries=1)
                        search_input_url = provider_url
                        search_input_html = provider_html
                        allocation["search_provider_used"] = "ddg_html"
                    except Exception as provider_exc:  # noqa: BLE001
                        degradation_flags.append("search_provider_fetch_failed")
                        allocation["search_provider_error"] = _safe_exc(provider_exc)

            search_auto_config = _build_search_auto_config(
                search_input_url,
                normalized_terms,
                normalized_search_options,
            )
            search_results_payload = _extract_search_results(
                search_input_url,
                search_input_html,
                auto_config=search_auto_config,
            )
            min_results_required = int(search_auto_config.get("min_results_required") or 3)
            target_candidates = int(search_auto_config.get("target_candidates") or _SEARCH_AUTO_TARGET_CANDIDATES)
            fallback_used = False
            if (
                int(search_results_payload.get("result_count") or 0) < min_results_required
                and bool(normalized_search_options.get("fallback_on_insufficient", True))
            ):
                fallback_url = _build_search_fallback_url(
                    source_url=normalized_url,
                    query_terms=normalized_terms,
                    provider=str(normalized_search_options.get("search_fallback_provider") or "ddg_html"),
                )
                if fallback_url and fallback_url != normalized_url:
                    try:
                        fallback_html, _ = fetch_html(fallback_url, timeout=20.0, retries=1)
                        fallback_auto_config = dict(search_auto_config)
                        fallback_auto_config["source_domain"] = _domain_of_url(fallback_url)
                        fallback_payload = _extract_search_results(
                            fallback_url,
                            fallback_html,
                            auto_config=fallback_auto_config,
                        )
                        search_results_payload = _merge_search_result_payload(
                            search_results_payload,
                            fallback_payload,
                            max_items=max(10, target_candidates),
                        )
                        fallback_used = True
                    except Exception as fallback_exc:  # noqa: BLE001
                        degradation_flags.append("search_fallback_fetch_failed")
                        allocation["search_fallback_error"] = _safe_exc(fallback_exc)

            if fallback_used:
                search_results_payload["fallback_provider"] = str(
                    normalized_search_options.get("search_fallback_provider") or "ddg_html"
                )
                search_results_payload["fallback_used"] = True

            min_results_required = int(search_auto_config.get("min_results_required") or 3)
            if int(search_results_payload.get("result_count") or 0) >= min_results_required:
                if bool(normalized_search_options.get("search_expand")):
                    max_expand = int(normalized_search_options.get("search_expand_limit") or target_candidates)
                    child_urls = _select_search_expand_urls(
                        list(search_results_payload.get("items") or []),
                        limit=max_expand,
                        prefer_domain_diversity=bool(normalized_search_options.get("prefer_domain_diversity", True)),
                    )

                    expanded_results: list[dict[str, Any]] = []
                    agg_inserted = 0
                    agg_inserted_valid = 0
                    agg_skipped = 0
                    child_outcome_breakdown = {
                        "duplicate": 0,
                        "fetch_failed": 0,
                        "quality_rejected": 0,
                        "other": 0,
                    }
                    child_search_options = dict(normalized_search_options)
                    child_search_options["search_expand"] = False
                    child_search_options["fallback_on_insufficient"] = False
                    for child_url in child_urls:
                        child_result = ingest_single_url(
                            url=child_url,
                            query_terms=normalized_terms,
                            strict_mode=False,
                            search_options=child_search_options,
                            track_keyword_history=False,
                        )
                        agg_inserted += int(child_result.get("inserted") or 0)
                        agg_inserted_valid += int(child_result.get("inserted_valid") or 0)
                        agg_skipped += int(child_result.get("skipped") or 0)
                        child_outcome = _classify_search_expand_child_outcome(child_result if isinstance(child_result, dict) else {})
                        if child_outcome in child_outcome_breakdown:
                            child_outcome_breakdown[child_outcome] += 1
                        if len(expanded_results) < 10:
                            expanded_results.append(
                                {
                                    "url": child_url,
                                    "status": child_result.get("status"),
                                    "inserted": int(child_result.get("inserted") or 0),
                                    "inserted_valid": int(child_result.get("inserted_valid") or 0),
                                    "document_id": child_result.get("document_id"),
                                    "degradation_flags": list(child_result.get("degradation_flags") or []),
                                }
                            )

                    status = "success" if agg_inserted_valid > 0 else ("failed" if strict_mode else "degraded_success")
                    rejection_breakdown: dict[str, int] = {}
                    if agg_inserted_valid <= 0:
                        degradation_flags.append("search_expand_no_inserted")
                        rejection_breakdown["search_expand_no_inserted"] = 1
                        if child_outcome_breakdown["duplicate"] > 0:
                            rejection_breakdown["search_expand_duplicate"] = int(child_outcome_breakdown["duplicate"])
                        if child_outcome_breakdown["fetch_failed"] > 0:
                            rejection_breakdown["search_expand_fetch_failed"] = int(child_outcome_breakdown["fetch_failed"])
                        if child_outcome_breakdown["quality_rejected"] > 0:
                            rejection_breakdown["search_expand_quality_rejected"] = int(child_outcome_breakdown["quality_rejected"])
                        if child_outcome_breakdown["other"] > 0:
                            rejection_breakdown["search_expand_other"] = int(child_outcome_breakdown["other"])
                    expand_result = {
                        "status": status,
                        "inserted": agg_inserted,
                        "inserted_valid": agg_inserted_valid,
                        "skipped": agg_skipped,
                        "url": normalized_url,
                        "document_id": None,
                        "doc_type": normalize_doc_type(_DEFAULT_DOC_TYPE),
                        "capability_profile": capability,
                        "handler_allocation": allocation,
                        "page_gate": {
                            "page_type": "search_results",
                            "is_low_value": False,
                            "reason": "search_expand_ingested",
                        },
                        "search_results": {
                            "result_count": int(search_results_payload.get("result_count") or 0),
                            "items": list(search_results_payload.get("items") or [])[:10],
                            "auto_config": dict(search_auto_config or {}),
                            "fallback_used": bool(search_results_payload.get("fallback_used")),
                            "fallback_provider": search_results_payload.get("fallback_provider"),
                        },
                        "search_expand": {
                            "enabled": True,
                            "expanded_count": len(child_urls),
                            "outcome_breakdown": child_outcome_breakdown,
                            "expanded_results": expanded_results,
                        },
                        "structured_extraction_status": "ok" if agg_inserted_valid > 0 else "failed",
                        "quality_score": 100.0 if agg_inserted_valid > 0 else 0.0,
                        "rejected_count": 0 if agg_inserted_valid > 0 else 1,
                        "rejection_breakdown": rejection_breakdown,
                        "degradation_flags": list(dict.fromkeys(degradation_flags)),
                    }
                    apply_light_filter_fields(expand_result, light_filter_payload)
                    finalize_job(
                        job_id,
                        status="completed" if status != "failed" else "failed",
                        result=expand_result,
                    )
                    return expand_result
                if not bool(normalized_search_options.get("allow_search_summary_write", False)):
                    result_status = "failed" if strict_mode else "degraded_success"
                    result = {
                        "status": result_status,
                        "inserted": 0,
                        "inserted_valid": 0,
                        "skipped": 1,
                        "url": normalized_url,
                        "document_id": None,
                        "doc_type": normalize_doc_type(_DEFAULT_DOC_TYPE),
                        "capability_profile": capability,
                        "handler_allocation": allocation,
                        "page_gate": {
                            "page_type": "search_results",
                            "is_low_value": True,
                            "reason": "search_summary_write_disabled",
                        },
                        "search_results": {
                            "result_count": int(search_results_payload.get("result_count") or 0),
                            "items": list(search_results_payload.get("items") or [])[:10],
                            "auto_config": dict(search_auto_config or {}),
                            "fallback_used": bool(search_results_payload.get("fallback_used")),
                            "fallback_provider": search_results_payload.get("fallback_provider"),
                        },
                        "structured_extraction_status": "failed",
                        "quality_score": 0.0,
                        "rejected_count": 1,
                        "rejection_breakdown": {"search_summary_write_disabled": 1},
                        "degradation_flags": list(
                            dict.fromkeys([*degradation_flags, "search_summary_write_disabled"])
                        ),
                    }
                    apply_light_filter_fields(result, light_filter_payload)
                    finalize_job(
                        job_id,
                        status="completed" if result_status != "failed" else "failed",
                        result=result,
                    )
                    return result

                page_type, is_low_value, low_value_reason = ("search_results", False, None)
                search_summary = str(search_results_payload.get("summary_text") or "").strip()
                if search_summary:
                    content = normalize_content_for_ingest(search_summary, max_chars=_MAX_CONTENT_CHARS)
                    title = f"Search Results - {capability.get('domain') or normalized_url}"
            else:
                crawler_fallback_result = _try_crawler_pool(fallback_reason="search_template_results_insufficient")
                if crawler_fallback_result is not None:
                    finalize_job(job_id, status="completed", result=crawler_fallback_result)
                    return crawler_fallback_result
                degradation_flags.append("search_template_no_results")
                status = "failed" if strict_mode else "degraded_success"
                result = {
                    "status": status,
                    "inserted": 0,
                    "inserted_valid": 0,
                    "skipped": 1,
                    "url": normalized_url,
                    "document_id": None,
                    "doc_type": normalize_doc_type(_DEFAULT_DOC_TYPE),
                    "capability_profile": capability,
                    "handler_allocation": allocation,
                    "page_gate": {
                        "page_type": "search_shell",
                        "is_low_value": True,
                        "reason": "search_template_results_insufficient",
                    },
                    "search_results": {
                        "result_count": int(search_results_payload.get("result_count") or 0),
                        "items": list(search_results_payload.get("items") or [])[:10],
                        "auto_config": dict(search_auto_config or {}),
                    },
                    "structured_extraction_status": "failed",
                    "quality_score": 0.0,
                    "rejected_count": 1,
                    "rejection_breakdown": {"search_template_results_insufficient": 1},
                    "degradation_flags": list(dict.fromkeys(degradation_flags)),
                }
                apply_light_filter_fields(result, light_filter_payload)
                finalize_job(job_id, status="completed" if status != "failed" else "failed", result=result)
                return result
        else:
            page_type, is_low_value, low_value_reason = _classify_page_type(normalized_url, html, content)

        if is_low_value:
            provenance_blocked_early, provenance_reason_early, provenance_diag_early = _provenance_dirty_decision(
                url=normalized_url,
                title=title,
                content=raw_content,
                domain_specific_metadata=None,
            )
            if provenance_blocked_early:
                degradation_flags.append(str(provenance_reason_early))
                degradation_flags.append(f"provenance_gate_rejected:{provenance_reason_early}")
                status = "failed" if strict_mode else "degraded_success"
                result = {
                    "status": status,
                    "inserted": 0,
                    "inserted_valid": 0,
                    "skipped": 1,
                    "url": normalized_url,
                    "document_id": None,
                    "doc_type": normalize_doc_type(_DEFAULT_DOC_TYPE),
                    "capability_profile": capability,
                    "handler_allocation": allocation,
                    "page_gate": {
                        "page_type": "provenance_intermediate",
                        "is_low_value": True,
                        "reason": provenance_reason_early,
                    },
                    "provenance_gate": {
                        "blocked": True,
                        "reason": provenance_reason_early,
                        "diagnostics": provenance_diag_early,
                    },
                    "structured_extraction_status": "failed",
                    "quality_score": 0.0,
                    "rejected_count": 1,
                    "rejection_breakdown": {str(provenance_reason_early): 1},
                    "degradation_flags": list(dict.fromkeys(degradation_flags)),
                }
                apply_light_filter_fields(result, light_filter_payload)
                finalize_job(job_id, status="completed" if status != "failed" else "failed", result=result)
                return result

            degradation_flags.append(f"low_value_page:{page_type}")
            status = "failed" if strict_mode else "degraded_success"
            result = {
                "status": status,
                "inserted": 0,
                "inserted_valid": 0,
                "skipped": 1,
                "url": normalized_url,
                "document_id": None,
                "doc_type": normalize_doc_type(_DEFAULT_DOC_TYPE),
                "capability_profile": capability,
                "handler_allocation": allocation,
                "page_gate": {
                    "page_type": page_type,
                    "is_low_value": True,
                    "reason": low_value_reason,
                },
                "structured_extraction_status": "failed",
                "quality_score": 0.0,
                "rejected_count": 1,
                "rejection_breakdown": {str(low_value_reason or "low_value_page"): 1},
                "degradation_flags": list(dict.fromkeys(degradation_flags)),
            }
            apply_light_filter_fields(result, light_filter_payload)
            finalize_job(job_id, status="completed" if status != "failed" else "failed", result=result)
            return result

        domain_specific_metadata: dict[str, Any] = {}
        github_structured = _extract_github_structured_content(normalized_url, html, content)
        if isinstance(github_structured, dict):
            override_content = str(github_structured.get("content") or "").strip()
            override_title = str(github_structured.get("title") or "").strip()
            if override_content:
                content = normalize_content_for_ingest(override_content, max_chars=_MAX_CONTENT_CHARS)
                degradation_flags.append("domain_specific_parser_applied:github_repo_page")
            if override_title:
                title = override_title
            domain_specific_metadata = dict(github_structured.get("metadata") or {})

        provenance_blocked, provenance_reason, provenance_diag = _provenance_dirty_decision(
            url=normalized_url,
            title=title,
            content=raw_content,
            domain_specific_metadata=domain_specific_metadata,
        )
        if provenance_blocked:
            degradation_flags.append(str(provenance_reason))
            degradation_flags.append(f"provenance_gate_rejected:{provenance_reason}")
            status = "failed" if strict_mode else "degraded_success"
            result = {
                "status": status,
                "inserted": 0,
                "inserted_valid": 0,
                "skipped": 1,
                "url": normalized_url,
                "document_id": None,
                "doc_type": normalize_doc_type(_DEFAULT_DOC_TYPE),
                "capability_profile": capability,
                "handler_allocation": allocation,
                "page_gate": {
                    "page_type": "provenance_intermediate",
                    "is_low_value": True,
                    "reason": provenance_reason,
                },
                "provenance_gate": {
                    "blocked": True,
                    "reason": provenance_reason,
                    "diagnostics": provenance_diag,
                },
                "structured_extraction_status": "failed",
                "quality_score": 0.0,
                "rejected_count": 1,
                "rejection_breakdown": {provenance_reason: 1},
                "degradation_flags": list(dict.fromkeys(degradation_flags)),
            }
            apply_light_filter_fields(result, light_filter_payload)
            finalize_job(job_id, status="completed" if status != "failed" else "failed", result=result)
            return result

        extracted_data: dict[str, Any] = {
            "platform": "single_url",
            "handler_used": allocation["handler_used"],
            "fetch_tier": allocation["fetch_tier"],
            "source_ref": {"url": normalized_url},
        }
        if domain_specific_metadata:
            extracted_data["domain_specific_parser"] = domain_specific_metadata
        if search_results_payload is not None:
            extracted_data["search_results"] = {
                "result_count": int(search_results_payload.get("result_count") or 0),
                "items": list(search_results_payload.get("items") or [])[:10],
            }
            if isinstance(search_auto_config, dict) and search_auto_config:
                extracted_data["search_auto_config"] = dict(search_auto_config)
        structured_status = "failed"
        structured_reason = None
        try:
            payload = "\n\n".join([x for x in [title, content] if x])
            enriched = _EXTRACTION_APP.extract_structured_enriched(
                payload,
                include_market=True,
                include_policy=True,
                include_sentiment=True,
                include_company=True,
                include_product=True,
                include_operation=True,
            )
            if isinstance(enriched, dict) and enriched:
                extracted_data.update(enriched)
                structured_status = "ok"
            else:
                structured_reason = "empty_structured_output"
                degradation_flags.append("structured_extraction_empty")
        except Exception as ex:  # noqa: BLE001
            structured_reason = "extractor_exception"
            extracted_data["structured_extraction_error"] = _safe_exc(ex)
            degradation_flags.append("structured_extraction_exception")

        quality_score = _build_quality_score(
            content_chars=len(content or ""),
            structured_extraction_status=structured_status,
            degradation_flags=degradation_flags,
        )
        pre_write_gate = content_quality_check(
            uri=normalized_url,
            content=content or "",
            doc_type=normalize_doc_type(_DEFAULT_DOC_TYPE),
            extraction_status={"extraction_enabled": structured_status == "ok"},
        )
        if pre_write_gate.blocked:
            reason = str(pre_write_gate.reason or "content_gate_rejected")
            result_status = "failed" if strict_mode else "degraded_success"
            gate_flags = list(dict.fromkeys([*degradation_flags, reason, f"content_gate_rejected:{reason}"]))
            result = {
                "status": result_status,
                "inserted": 0,
                "inserted_valid": 0,
                "skipped": 1,
                "url": normalized_url,
                "document_id": None,
                "doc_type": normalize_doc_type(_DEFAULT_DOC_TYPE),
                "capability_profile": capability,
                "handler_allocation": allocation,
                "page_gate": {
                    "page_type": page_type,
                    "is_low_value": False,
                    "reason": None,
                },
                "pre_write_content_gate": pre_write_gate.to_dict(),
                "structured_extraction_status": structured_status,
                "quality_score": float(pre_write_gate.quality_score),
                "rejected_count": 1,
                "rejection_breakdown": {reason: 1},
                "degradation_flags": gate_flags,
            }
            if structured_reason:
                result["structured_extraction_reason"] = structured_reason
            apply_light_filter_fields(result, light_filter_payload)
            finalize_job(job_id, status="completed" if result_status != "failed" else "failed", result=result)
            return result
        if domain_specific_metadata and len(content or "") >= 120:
            quality_score = max(quality_score, 72.0)

        if strict_mode and quality_score < _QUALITY_SUCCESS_THRESHOLD:
            result = {
                "status": "failed",
                "inserted": 0,
                "inserted_valid": 0,
                "skipped": 1,
                "url": normalized_url,
                "document_id": None,
                "doc_type": normalize_doc_type(_DEFAULT_DOC_TYPE),
                "capability_profile": capability,
                "handler_allocation": allocation,
                "page_gate": {
                    "page_type": page_type,
                    "is_low_value": False,
                    "reason": None,
                },
                "structured_extraction_status": structured_status,
                "quality_score": quality_score,
                "rejected_count": 1,
                "rejection_breakdown": {"strict_mode_quality_gate": 1},
                "degradation_flags": list(dict.fromkeys([*degradation_flags, "strict_mode_quality_gate"])),
            }
            if structured_reason:
                result["structured_extraction_reason"] = structured_reason
            apply_light_filter_fields(result, light_filter_payload)
            finalize_job(job_id, status="failed", result=result)
            return result

        normalized_doc_type = normalize_doc_type(_DEFAULT_DOC_TYPE)
        summary = (content or "")[:800] or None

        with SessionLocal() as session:
            source = _get_or_create_source(session, _SOURCE_NAME, _SOURCE_KIND, capability.get("domain"))
            existed = session.query(Document).filter(Document.uri == normalized_url).first()
            if existed:
                degradation_flags.append("document_already_exists")
                doc_id = existed.id
                inserted = 0
                skipped = 1
            else:
                extracted_data["structured_extraction_status"] = structured_status
                if structured_reason:
                    extracted_data["structured_extraction_reason"] = structured_reason
                extracted_data["quality_score"] = quality_score
                extracted_data["degradation_flags"] = list(dict.fromkeys(degradation_flags))
                extracted_data["capability_profile"] = capability
                extracted_data["http_status"] = int(getattr(response, "status_code", 0) or 0)
                extracted_data["light_filter"] = dict(light_filter_payload)
                doc = Document(
                    source_id=source.id,
                    doc_type=normalized_doc_type,
                    title=title,
                    summary=summary,
                    content=(content or "")[:_MAX_CONTENT_CHARS] or None,
                    uri=normalized_url,
                    extracted_data=extracted_data,
                )
                session.add(doc)
                session.commit()
                doc_id = doc.id
                inserted = 1
                skipped = 0

        final_flags = list(dict.fromkeys(degradation_flags))
        if structured_status != "ok" and "structured_extraction_failed" not in final_flags:
            final_flags.append("structured_extraction_failed")
        status = "success" if quality_score >= _QUALITY_SUCCESS_THRESHOLD and not final_flags else "degraded_success"

        result = {
            "status": status,
            "inserted": inserted,
            "inserted_valid": inserted,
            "skipped": skipped,
            "url": normalized_url,
            "document_id": doc_id,
            "doc_type": normalized_doc_type,
            "capability_profile": capability,
            "handler_allocation": allocation,
            "page_gate": {
                "page_type": page_type,
                "is_low_value": False,
                "reason": None,
            },
            "structured_extraction_status": structured_status,
            "quality_score": quality_score,
            "rejected_count": 0,
            "rejection_breakdown": {},
            "degradation_flags": final_flags,
        }
        if structured_reason:
            result["structured_extraction_reason"] = structured_reason
        apply_light_filter_fields(result, light_filter_payload)

        finalize_job(job_id, status="completed", result=result)
        return result

    except Exception as exc:  # noqa: BLE001
        logger.exception("ingest_single_url failed url=%s", normalized_url)
        fail_job(job_id, _safe_exc(exc))
        result = {
            "status": "failed",
            "inserted": 0,
            "inserted_valid": 0,
            "skipped": 0,
            "url": normalized_url,
            "document_id": None,
            "doc_type": normalize_doc_type(_DEFAULT_DOC_TYPE),
            "structured_extraction_status": "failed",
            "quality_score": 0.0,
            "rejected_count": 1,
            "rejection_breakdown": {"unexpected_exception": 1},
            "degradation_flags": ["unexpected_exception"],
            "error": _safe_exc(exc),
        }
        apply_light_filter_fields(result, light_filter_payload)
        _record_keyword_history_for_result(result)
        return result
