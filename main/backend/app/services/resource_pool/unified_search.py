"""Unified search over site entries bound to a source_library item."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import json
from typing import Any
from urllib.parse import urljoin, urlsplit
import xml.etree.ElementTree as ET
import gzip

from ..ingest.adapters.http_utils import HttpFetchError, fetch_html, make_html_parser
from .auto_classify import infer_keyword_capabilities
from .candidate_source_plan import build_candidate_source_plan, plan_to_metadata
from ..source_library.resolver import list_effective_items
from ..source_library.item_plan import build_item_execution_plan
from ..source_library.relevance_review import build_relevance_review_queue
from .extract import append_url
from .resolver import list_urls
from .search_capabilities import make_search_candidate
from .search_capabilities import normalize_match_text
from .search_capabilities import select_search_candidates
from .site_search_policy import resolve_site_search_policy_for_entry
from .search_template_service import execute_feed_probe
from .search_template_service import execute_external_site_search
from .search_template_service import execute_search_template
from .search_template_service import execute_sitemap_probe
from .search_template_service import extract_feed_candidates
from .search_template_adapters import apply_search_template_adapter_plan
from .search_template_adapters import resolve_search_template_adapter_plan
from .search_template_service import normalize_candidate_url
from .search_template_service import normalize_search_template_placeholders
from .search_template_service import resolve_search_template_pagination
from .site_entries import get_site_entry_by_url
from .url_utils import domain_from_url, normalize_url
from ..source_library.adapters.official_access import handle_official_access_api


@dataclass
class UnifiedSearchResult:
    item_key: str
    query_terms: list[str]
    site_entries_used: list[dict[str, Any]]
    runtime_diagnostics: list[dict[str, Any]]
    candidates: list[str]
    written: dict[str, int] | None
    ingest_result: dict[str, Any] | None
    errors: list[dict[str, str]]
    relevance_review_queue: dict[str, Any]


@dataclass(frozen=True)
class CandidateTargetConfig:
    bucket_by: str
    ratios: dict[str, float]
    minimums: dict[str, int]
    maximums: dict[str, int]
    default_ratio: float
    target_total: int | None
    allocation_mode: str = "weighted"
    target_per_bucket: int | None = None


_PRIORITY_KEEP_DOMAINS = {
    "arxiv.org",
    "help.openai.com",
    "github.com",
    "docs.github.com",
    "developer.mozilla.org",
    "docs.anthropic.com",
    "cloud.google.com",
}


def _apply_site_search_service_policy(params: dict[str, Any], policy: Any) -> dict[str, Any]:
    routed = dict(params or {})
    preferred = str(getattr(policy, "preferred_search_service", None) or "").strip().lower()
    if preferred in {"basic", "resilient"} and not str(routed.get("search_service") or "").strip():
        routed["search_service"] = preferred
    if preferred == "resilient" and "enable_search_service_fallback" not in routed:
        routed["enable_search_service_fallback"] = True
    return routed


def _effective_candidate_target_limit(
    *,
    max_candidates: int,
    config: CandidateTargetConfig | None,
) -> int:
    if config is None or config.target_total is None:
        return max_candidates
    return max(1, min(max_candidates, int(config.target_total)))


def _derive_default_candidate_target_config(
    *,
    site_entry_urls: list[str],
    max_candidates: int,
) -> CandidateTargetConfig | None:
    entry_domains = {
        str(domain_from_url(site_url) or "").strip().lower()
        for site_url in site_entry_urls
        if str(site_url or "").strip()
    }
    entry_domains.discard("")
    if len(entry_domains) <= 1:
        return None
    return CandidateTargetConfig(
        bucket_by="entry_domain",
        ratios={},
        minimums={},
        maximums={},
        default_ratio=0.0,
        target_total=max_candidates,
        allocation_mode="equal",
        target_per_bucket=None,
    )


def _should_allow_wave_early_stop(config: CandidateTargetConfig | None) -> bool:
    return config is None


def _build_site_entry_execution_batches(
    *,
    site_entry_urls: list[str],
    project_key: str,
    config: CandidateTargetConfig | None,
) -> list[list[str]]:
    waves = _build_site_entry_execution_waves(
        site_entry_urls=site_entry_urls,
        project_key=project_key,
    )
    if _should_allow_wave_early_stop(config):
        return waves
    merged = [site_url for wave in waves for site_url in wave]
    return [merged] if merged else []


def _site_entry_execution_priority(site_url: str, entry: dict[str, Any] | None, policy: Any) -> int:
    entry_domain = str((entry or {}).get("domain") or domain_from_url(site_url) or "").strip().lower()
    if getattr(policy, "category", None) == "api_preferred":
        return 0
    if entry_domain in _PRIORITY_KEEP_DOMAINS:
        return 1
    if getattr(policy, "category", None) == "keep":
        return 2
    if getattr(policy, "category", None) == "external_preferred":
        return 3
    return 4


def _build_site_entry_execution_waves(
    *,
    site_entry_urls: list[str],
    project_key: str,
) -> list[list[str]]:
    prioritized: list[tuple[int, str]] = []
    for site_url in site_entry_urls:
        entry = get_site_entry_by_url(scope="effective", project_key=project_key, site_url=site_url) or {
            "site_url": site_url,
            "domain": domain_from_url(site_url),
            "entry_type": "domain_root",
        }
        base_url = str(entry.get("site_url") or site_url)
        policy = resolve_site_search_policy_for_entry(base_url, entry)
        prioritized.append((_site_entry_execution_priority(base_url, entry, policy), site_url))
    prioritized.sort(key=lambda item: (item[0], item[1]))
    waves: dict[int, list[str]] = {}
    for priority, site_url in prioritized:
        waves.setdefault(priority, []).append(site_url)
    return [waves[key] for key in sorted(waves)]


def _resolve_candidate_target_config(
    params: dict[str, Any] | None,
    *,
    max_candidates: int,
) -> CandidateTargetConfig | None:
    if not isinstance(params, dict):
        return None
    raw = params.get("candidate_target_config") or params.get("candidate_mix_config")
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        try:
            raw = json.loads(text)
        except Exception:
            return None
    if not isinstance(raw, dict):
        return None
    bucket_by = str(raw.get("bucket_by") or raw.get("group_by") or "").strip().lower()
    if bucket_by not in {"entry_type", "route_kind", "candidate_source", "entry_domain", "site_policy", "search_service"}:
        return None
    ratios = _parse_ratio_map(raw.get("ratios") or raw.get("weights"))
    minimums = _parse_int_map(raw.get("minimums") or raw.get("mins"))
    maximums = _parse_int_map(raw.get("maximums") or raw.get("caps") or raw.get("maximum_caps"))
    allocation_mode = str(raw.get("allocation_mode") or raw.get("distribution_mode") or "weighted").strip().lower()
    if allocation_mode not in {"weighted", "equal"}:
        allocation_mode = "weighted"
    default_ratio = 0.0
    try:
        default_ratio = max(0.0, float(raw.get("default_ratio") or 0.0))
    except Exception:
        default_ratio = 0.0
    target_total = None
    if raw.get("target_total") is not None or raw.get("total") is not None:
        try:
            target_total = max(1, min(int(raw.get("target_total") or raw.get("total")), max_candidates))
        except Exception:
            target_total = None
    target_per_bucket = None
    if raw.get("target_per_bucket") is not None or raw.get("per_bucket_target") is not None:
        try:
            target_per_bucket = max(1, min(int(raw.get("target_per_bucket") or raw.get("per_bucket_target")), max_candidates))
        except Exception:
            target_per_bucket = None
    if not ratios and not minimums and not maximums and allocation_mode != "equal" and target_per_bucket is None:
        return None
    return CandidateTargetConfig(
        bucket_by=bucket_by,
        ratios=ratios,
        minimums=minimums,
        maximums=maximums,
        default_ratio=default_ratio,
        target_total=target_total,
        allocation_mode=allocation_mode,
        target_per_bucket=target_per_bucket,
    )


def _parse_ratio_map(raw: Any) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, float] = {}
    for key, value in raw.items():
        normalized_key = str(key or "").strip()
        if not normalized_key:
            continue
        try:
            numeric = float(value)
        except Exception:
            continue
        if numeric < 0:
            continue
        out[normalized_key] = numeric
    return out


def _parse_int_map(raw: Any) -> dict[str, int]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    for key, value in raw.items():
        normalized_key = str(key or "").strip()
        if not normalized_key:
            continue
        try:
            numeric = int(value)
        except Exception:
            continue
        if numeric < 0:
            continue
        out[normalized_key] = numeric
    return out


def _candidate_bucket_value(ref: dict[str, Any], bucket_by: str, url: str) -> str:
    if bucket_by == "route_kind":
        return str(ref.get("route_kind") or "page").strip() or "page"
    if bucket_by == "candidate_source":
        return str(ref.get("candidate_source") or "unknown").strip() or "unknown"
    if bucket_by == "entry_domain":
        return str(ref.get("entry_domain") or domain_from_url(url) or "unknown").strip().lower() or "unknown"
    if bucket_by == "site_policy":
        return str(ref.get("site_policy") or "unknown").strip().lower() or "unknown"
    if bucket_by == "search_service":
        return str(ref.get("search_service") or "unknown").strip().lower() or "unknown"
    return str(ref.get("entry_type") or "unknown").strip().lower() or "unknown"


def _apply_candidate_target_selection(
    scored_candidates: list[tuple[float, str, dict[str, Any]]],
    *,
    max_candidates: int,
    config: CandidateTargetConfig | None,
) -> list[tuple[float, str, dict[str, Any]]]:
    deduped: list[tuple[float, str, dict[str, Any]]] = []
    seen_urls: set[str] = set()
    for score, url, ref in scored_candidates:
        if not url or url in seen_urls or _is_low_value_candidate_url(url):
            continue
        seen_urls.add(url)
        deduped.append((score, url, ref))
    if config is None:
        return deduped[:max_candidates]
    buckets: dict[str, list[tuple[float, str, dict[str, Any]]]] = {}
    for score, url, ref in deduped:
        bucket = _candidate_bucket_value(ref, config.bucket_by, url)
        buckets.setdefault(bucket, []).append((score, url, ref))
    if not buckets:
        return []

    derived_target_total = config.target_total
    if derived_target_total is None and config.target_per_bucket is not None:
        derived_target_total = max(1, min(max_candidates, config.target_per_bucket * len(buckets)))
    target_total = min(max_candidates, derived_target_total or max_candidates)
    if target_total <= 0:
        return []

    quotas: dict[str, int] = {}
    allocated = 0
    for bucket, items in buckets.items():
        cap = config.maximums.get(bucket, len(items))
        minimum = min(config.minimums.get(bucket, 0), len(items), cap)
        per_bucket_target = min(config.target_per_bucket or 0, len(items), cap)
        quota = max(minimum, per_bucket_target)
        quotas[bucket] = quota
        allocated += quota
    remaining = max(0, target_total - allocated)

    weighted_buckets = []
    total_weight = 0.0
    for bucket, items in buckets.items():
        cap = min(config.maximums.get(bucket, len(items)), len(items))
        room = max(0, cap - quotas.get(bucket, 0))
        if config.allocation_mode == "equal":
            weight = 1.0
        else:
            weight = float(config.ratios.get(bucket, config.default_ratio))
        if room <= 0 or weight <= 0:
            continue
        weighted_buckets.append((bucket, room, weight))
        total_weight += weight

    if remaining > 0 and total_weight > 0:
        provisional: dict[str, int] = {}
        fractions: list[tuple[float, str]] = []
        used = 0
        for bucket, room, weight in weighted_buckets:
            exact = remaining * (weight / total_weight)
            whole = min(room, int(exact))
            provisional[bucket] = whole
            used += whole
            fractions.append((exact - int(exact), bucket))
        for bucket, whole in provisional.items():
            quotas[bucket] = quotas.get(bucket, 0) + whole
        leftover = remaining - used
        for _, bucket in sorted(fractions, key=lambda item: (-item[0], item[1])):
            if leftover <= 0:
                break
            cap = min(config.maximums.get(bucket, len(buckets[bucket])), len(buckets[bucket]))
            if quotas.get(bucket, 0) >= cap:
                continue
            quotas[bucket] = quotas.get(bucket, 0) + 1
            leftover -= 1

    selected: list[tuple[float, str, dict[str, Any]]] = []
    selected_urls: set[str] = set()
    for bucket, items in buckets.items():
        limit = min(quotas.get(bucket, 0), len(items))
        if limit <= 0:
            continue
        for item in items[:limit]:
            if item[1] in selected_urls:
                continue
            selected.append(item)
            selected_urls.add(item[1])

    if len(selected) < target_total:
        for item in deduped:
            if len(selected) >= target_total:
                break
            score, url, ref = item
            if url in selected_urls:
                continue
            bucket = _candidate_bucket_value(ref, config.bucket_by, url)
            cap = min(config.maximums.get(bucket, len(buckets.get(bucket, []))), len(buckets.get(bucket, [])) or target_total)
            already = sum(1 for _, existing_url, existing_ref in selected if _candidate_bucket_value(existing_ref, config.bucket_by, existing_url) == bucket)
            if already >= cap:
                continue
            selected.append(item)
            selected_urls.add(url)

    selected.sort(key=lambda item: (-item[0], item[1]))
    return selected[:target_total]


def _resolve_pinned_search_contract(entry: dict[str, Any], terms: list[str]) -> tuple[str | None, list[str]]:
    extra = entry.get("extra") if isinstance(entry, dict) else None
    profile = extra.get("search_contract_profile") if isinstance(extra, dict) else None
    if not isinstance(profile, dict):
        return None, terms
    best_template = str(profile.get("best_template") or "").strip() or None
    best_suffix = str(profile.get("best_suffix") or "").strip()
    if not best_suffix:
        return best_template, terms
    return best_template, [f"{term} {best_suffix}".strip() for term in terms if str(term or "").strip()]


def _collect_history_pool_urls(
    *,
    scope: str,
    project_key: str,
    source: str,
    limit: int = 3000,
) -> set[str]:
    if not source:
        return set()
    out: set[str] = set()
    page = 1
    page_size = 100
    while len(out) < max(1, int(limit)):
        items, total = list_urls(
            scope=scope,
            project_key=project_key,
            source=source,
            page=page,
            page_size=page_size,
        )
        if not items:
            break
        for item in items:
            url = str((item or {}).get("url") or "").strip()
            if url:
                out.add(url)
            if len(out) >= limit:
                break
        if page * page_size >= int(total or 0):
            break
        page += 1
    return out


def _as_terms(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        s = raw.strip()
        return [s] if s else []
    if isinstance(raw, list):
        out: list[str] = []
        for x in raw:
            s = str(x).strip()
            if s:
                out.append(s)
        # preserve order, dedup
        return list(dict.fromkeys(out))
    return [str(raw).strip()] if str(raw).strip() else []


def _normalize_search_template_placeholders(template: str | None) -> str:
    return normalize_search_template_placeholders(template)


def _resolve_search_template_pagination(params: dict[str, Any]) -> tuple[int, int]:
    return resolve_search_template_pagination(params)


def _normalize_candidate_url(url: str) -> str | None:
    return normalize_candidate_url(url)


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _extract_urls_from_rss_xml(xml_text: str) -> list[str]:
    return [item["url"] for item in _extract_rss_candidates_from_xml(xml_text)]


def _extract_rss_candidates_from_xml(xml_text: str) -> list[dict[str, str]]:
    return [
        {"url": item.url, "title": item.title, "text": item.text, "extra": {"title_hint": item.title}}
        for item in extract_feed_candidates(xml_text)
    ]


def _parse_sitemap_xml(xml_text: str) -> tuple[str, list[str]]:
    """Return (kind, locs). kind: urlset|sitemapindex|unknown."""
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return "unknown", []

    kind = _local_name(root.tag).lower()
    locs: list[str] = []
    for loc in root.findall(".//{*}loc"):
        if loc.text:
            norm = _normalize_candidate_url(loc.text.strip())
            if norm and norm not in locs:
                locs.append(norm)
    return kind, locs


def _fetch_text_maybe_gzip(url: str, *, timeout: float) -> str:
    text, resp = fetch_html(url, timeout=timeout, retries=1)
    if url.lower().endswith(".gz"):
        try:
            raw = resp.content
            return gzip.decompress(raw).decode("utf-8", errors="ignore")
        except Exception:
            return text
    return text


def _collect_sitemap_urls(
    *,
    sitemap_url: str,
    timeout: float,
    max_depth: int = 2,
    max_sitemaps: int = 50,
) -> list[str]:
    """Fetch sitemap urlset, or recursively expand sitemapindex, with limits."""
    seen: set[str] = set()
    urls: list[str] = []
    to_fetch: list[tuple[str, int]] = [(sitemap_url, 0)]
    fetched = 0

    while to_fetch and fetched < max_sitemaps:
        u, depth = to_fetch.pop(0)
        if u in seen:
            continue
        seen.add(u)
        fetched += 1

        xml_text = _fetch_text_maybe_gzip(u, timeout=timeout)
        kind, locs = _parse_sitemap_xml(xml_text)
        if kind.endswith("sitemapindex") and depth < max_depth:
            for loc in locs:
                if loc not in seen:
                    to_fetch.append((loc, depth + 1))
            continue

        for loc in locs:
            if loc not in urls:
                urls.append(loc)

    return urls


def _build_sitemap_candidates(urls: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for url in urls:
        norm = _normalize_candidate_url(url)
        if not norm:
            continue
        path = urlsplit(norm).path or ""
        slug = path.rstrip("/").rsplit("/", 1)[-1].rsplit(".", 1)[0]
        title_hint = slug.replace("-", " ").replace("_", " ")
        out.append({"url": norm, "title": "", "text": "", "extra": {"title_hint": title_hint}})
    return out


def _extract_urls_from_html(html: str, *, base_url: str) -> list[str]:
    urls: list[str] = []
    try:
        parser = make_html_parser(html)
        for node in parser.css("a"):
            href = (node.attributes.get("href") or "").strip()
            if not href:
                continue
            abs_url = urljoin(base_url, href)
            norm = _normalize_candidate_url(abs_url)
            if norm and norm not in urls:
                urls.append(norm)
    except Exception:
        return urls
    return urls


def _normalize_match_text(value: str | None) -> str:
    return normalize_match_text(value)


def _term_matches_texts(term: str, texts: list[str]) -> bool:
    normalized_term = _normalize_match_text(term)
    if not normalized_term:
        return False
    return any(normalized_term in _normalize_match_text(text) for text in texts if str(text or "").strip())


def _extract_link_candidates_from_html(html: str, *, base_url: str) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    try:
        parser = make_html_parser(html)
        for node in parser.css("a"):
            href = (node.attributes.get("href") or "").strip()
            if not href:
                continue
            abs_url = urljoin(base_url, href)
            norm = _normalize_candidate_url(abs_url)
            if not norm or norm in seen_urls:
                continue
            seen_urls.add(norm)
            candidates.append(
                {
                    "url": norm,
                    "text": str(node.text(separator=" ", strip=True) or "").strip(),
                    "title": str(node.attributes.get("title") or "").strip(),
                }
            )
    except Exception:
        return candidates
    return candidates


def _filter_urls_by_terms(urls: list[str], terms: list[str]) -> list[str]:
    if not terms:
        return urls
    t = [x.lower() for x in terms if x]
    out: list[str] = []
    for u in urls:
        lu = u.lower()
        if any(term in lu for term in t):
            out.append(u)
    return out


def _filter_urls_by_terms_with_fallback(
    urls: list[str],
    terms: list[str],
    *,
    fallback_limit: int = 30,
    allow_fallback: bool = True,
) -> tuple[list[str], bool]:
    """
    First try strict URL-term match; if nothing matches, fall back to top URLs.
    This avoids false-zero results on sites where result URLs don't carry query terms.
    """
    filtered = _filter_urls_by_terms(urls, terms)
    if filtered:
        return filtered, False
    if not terms:
        return urls, False
    if not allow_fallback:
        return [], True
    return urls[: max(1, int(fallback_limit))], True


def _filter_link_candidates_by_terms_with_fallback(
    candidates: list[dict[str, str]],
    terms: list[str],
    *,
    strategy: str = "search_template",
    entry_domain: str | None = None,
    search_url: str | None = None,
    fallback_limit: int = 30,
    allow_fallback: bool = True,
    scoring_config: dict[str, Any] | str | None = None,
) -> tuple[list[dict[str, str]], bool]:
    scored = [
        item
        for item in (
            make_search_candidate(
                url=str(candidate.get("url") or "").strip(),
                strategy=strategy,
                title=str(candidate.get("title") or "").strip(),
                text=str(candidate.get("text") or "").strip(),
                extra=dict(candidate.get("extra") or {}),
            )
            for candidate in candidates
        )
        if item is not None
    ]
    decisions, used_fallback = select_search_candidates(
        scored,
        terms,
        strategy=strategy,
        entry_domain=entry_domain,
        search_url=search_url,
        fallback_limit=fallback_limit,
        allow_fallback=allow_fallback,
        scoring_config=scoring_config,
    )
    by_url = {str(candidate.get("url") or "").strip(): candidate for candidate in candidates}
    return [by_url[item.url] for item in decisions if item.url in by_url], used_fallback


def _is_low_value_candidate_url(url: str) -> bool:
    u = str(url or "").strip().lower()
    if not u:
        return True
    low_markers = (
        "/login",
        "/signin",
        "/sign-in",
        "/signup",
        "/sign-up",
        "/register",
        "/privacy",
        "/tos",
        "/terms",
        "/about",
        "/account",
        "/settings",
        "/subscribe",
    )
    return any(marker in u for marker in low_markers)


def _resolve_item_site_entries(
    item: dict[str, Any],
    execution_plan: dict[str, Any] | None = None,
) -> list[str]:
    plan = execution_plan if isinstance(execution_plan, dict) else build_item_execution_plan(item)
    urls = plan.get("site_entry_urls") if isinstance(plan, dict) else None
    if not isinstance(urls, list):
        return []
    return [str(u or "").strip() for u in urls if str(u or "").strip()]


def _build_site_entry_definition_view(entry: dict[str, Any], *, site_url: str) -> dict[str, Any]:
    view = {
        "site_url": str(entry.get("site_url") or site_url or "").strip(),
        "domain": str(entry.get("domain") or domain_from_url(site_url) or "").strip().lower() or None,
        "entry_type": str(entry.get("entry_type") or "domain_root").strip().lower() or "domain_root",
        "channel_key": str(entry.get("channel_key") or "").strip() or None,
        "scope": entry.get("scope"),
    }
    template = str(entry.get("template") or "").strip()
    if template:
        view["template"] = template
    return {key: value for key, value in view.items() if value is not None}


def _entry_supports_query_terms(entry: dict[str, Any], entry_type: str) -> bool:
    capabilities = _resolve_entry_keyword_capabilities(entry, entry_type)
    return bool(capabilities.get("supports_query_terms"))


def _entry_keyword_mode(entry: dict[str, Any], entry_type: str) -> str:
    capabilities = _resolve_entry_keyword_capabilities(entry, entry_type)
    return str(capabilities.get("keyword_mode") or "none").strip().lower()


def _resolve_entry_keyword_capabilities(entry: dict[str, Any], entry_type: str) -> dict[str, Any]:
    capabilities = entry.get("capabilities") if isinstance(entry, dict) else None
    inferred = infer_keyword_capabilities(
        entry_type,
        str(entry.get("channel_key") or "").strip().lower() if isinstance(entry, dict) else None,
    )
    if not isinstance(capabilities, dict) or not capabilities:
        return inferred
    merged = dict(inferred)
    for key, value in capabilities.items():
        if value not in (None, ""):
            merged[key] = value
    return merged


def _build_search_candidates(
    raw_candidates: list[dict[str, Any]],
    *,
    strategy: str,
    source_url: str,
    entry_domain: str,
) -> list[Any]:
    built = []
    for candidate in raw_candidates:
        metadata = dict(candidate.get("extra") or {}) if isinstance(candidate.get("extra"), dict) else {}
        item = make_search_candidate(
            url=str(candidate.get("url") or "").strip(),
            strategy=strategy,
            title=str(candidate.get("title") or "").strip(),
            text=str(candidate.get("text") or "").strip(),
            source_url=source_url,
            entry_domain=entry_domain,
            metadata=metadata,
        )
        if item is not None:
            built.append(item)
    return built


def unified_search_by_item(
    *,
    project_key: str,
    item_key: str,
    query_terms: list[str] | str,
    max_candidates: int = 200,
    write_to_pool: bool = False,
    pool_scope: str = "project",
    pool_source: str = "unified_search",
    probe_timeout: float = 10.0,
    sitemap_max_depth: int = 2,
    sitemap_max_sitemaps: int = 50,
    auto_ingest: bool = False,
    ingest_limit: int = 10,
    enable_extraction: bool = True,
    allow_term_fallback: bool = True,
) -> UnifiedSearchResult:
    terms = _as_terms(query_terms)
    item_key = (item_key or "").strip()
    if not item_key:
        raise ValueError("item_key is required")
    if not project_key:
        raise ValueError("project_key is required")
    max_candidates = min(max(1, int(max_candidates)), 2000)
    if pool_scope not in {"project", "shared"}:
        pool_scope = "project"

    items = list_effective_items(scope="effective", project_key=project_key)
    item_map = {x.get("item_key"): x for x in items if isinstance(x, dict)}
    item = item_map.get(item_key)
    if not item:
        raise ValueError(f"source item not found: {item_key}")

    return unified_search_by_item_payload(
        project_key=project_key,
        item=item,
        query_terms=terms,
        max_candidates=max_candidates,
        write_to_pool=write_to_pool,
        pool_scope=pool_scope,
        pool_source=pool_source,
        probe_timeout=probe_timeout,
        sitemap_max_depth=sitemap_max_depth,
        sitemap_max_sitemaps=sitemap_max_sitemaps,
        auto_ingest=auto_ingest,
        ingest_limit=ingest_limit,
        enable_extraction=enable_extraction,
        allow_term_fallback=allow_term_fallback,
    )


def unified_search_by_item_payload(
    *,
    project_key: str,
    item: dict[str, Any],
    execution_plan: dict[str, Any] | None = None,
    query_terms: list[str] | str,
    max_candidates: int = 200,
    write_to_pool: bool = False,
    pool_scope: str = "project",
    pool_source: str = "unified_search",
    probe_timeout: float = 10.0,
    sitemap_max_depth: int = 2,
    sitemap_max_sitemaps: int = 50,
    auto_ingest: bool = False,
    ingest_limit: int = 10,
    enable_extraction: bool = True,
    allow_term_fallback: bool = True,
) -> UnifiedSearchResult:
    terms = _as_terms(query_terms)
    item_key = str(item.get("item_key") or "").strip()
    if not item_key:
        raise ValueError("item.item_key is required")
    if not project_key:
        raise ValueError("project_key is required")
    max_candidates = min(max(1, int(max_candidates)), 2000)
    if pool_scope not in {"project", "shared"}:
        pool_scope = "project"

    params = item.get("params") or {}
    if not isinstance(params, dict):
        params = {}
    extra = item.get("extra") or {}
    if not isinstance(extra, dict):
        extra = {}
    resolved_execution_plan = execution_plan if isinstance(execution_plan, dict) else build_item_execution_plan(item)
    expected_entry_type = str(params.get("expected_entry_type") or extra.get("expected_entry_type") or "").strip().lower()
    allow_deprioritized = bool(
        params.get("allow_deprioritized_site_entries")
        or extra.get("allow_deprioritized_site_entries")
    )
    site_entry_urls = _resolve_item_site_entries(item, resolved_execution_plan)
    if not site_entry_urls:
        raise ValueError("item.params.site_entries is required and cannot be empty for unified search")
    candidate_target_config = _resolve_candidate_target_config(params, max_candidates=max_candidates)
    if candidate_target_config is None:
        candidate_target_config = _derive_default_candidate_target_config(
            site_entry_urls=site_entry_urls,
            max_candidates=max_candidates,
        )

    used_entries: list[dict[str, Any]] = []
    runtime_diagnostics: list[dict[str, Any]] = []
    candidates: list[str] = []
    candidate_refs: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, str]] = []
    history_pool_urls: set[str] = set()

    def _push(u: str, *, ref: dict[str, Any]) -> None:
        if u and u not in candidates:
            candidates.append(u)
            candidate_refs[u] = ref

    def _process_site_entry(su: str) -> dict[str, Any]:
        local_errors: list[dict[str, str]] = []
        local_candidates: list[tuple[str, dict[str, Any], float]] = []
        try:
            entry = get_site_entry_by_url(scope="effective", project_key=project_key, site_url=su) or {
                "site_url": su,
                "domain": domain_from_url(su),
                "entry_type": "domain_root",
                "template": None,
                "scope": None,
            }
            etype = str(entry.get("entry_type") or "domain_root").strip().lower()
            if expected_entry_type and etype != expected_entry_type:
                local_errors.append(
                    {
                        "site_url": su,
                        "error": f"entry_type mismatch: expected={expected_entry_type}, actual={etype}",
                    }
                )
                return {
                    "entry": _build_site_entry_definition_view(entry, site_url=su),
                    "runtime": None,
                    "candidates": local_candidates,
                    "errors": local_errors,
                }

            base_url = str(entry.get("site_url") or su)
            template = entry.get("template")
            entry_domain = (entry.get("domain") or domain_from_url(base_url) or "").strip().lower()
            entry_view = _build_site_entry_definition_view(entry, site_url=base_url)
            policy = resolve_site_search_policy_for_entry(base_url, entry)
            routed_params = _apply_site_search_service_policy(params, policy)
            if policy.parser_profile:
                routed_params["parser_profile"] = policy.parser_profile
            external_search_enabled = bool(routed_params.get("enable_external_search_fallback", True))
            plan = build_candidate_source_plan(
                entry_type=etype,
                policy_category=policy.category,
                allow_deprioritized=allow_deprioritized,
                external_search_enabled=external_search_enabled,
            )
            entry_runtime = dict(entry_view)
            entry_runtime["site_policy"] = policy.category
            entry_runtime["policy_reason"] = policy.reason
            entry_runtime["service_chain"] = plan.service_chain
            entry_runtime["candidate_source_plan"] = plan_to_metadata(plan)
            if policy.preferred_search_service:
                entry_runtime["preferred_search_service"] = policy.preferred_search_service
            if policy.implementation_hint:
                entry_runtime["implementation_hint"] = policy.implementation_hint
            if policy.parser_profile:
                entry_runtime["parser_profile"] = policy.parser_profile
            if policy.category == "api_preferred":
                result = handle_official_access_api(
                    {
                        "provider_key": policy.provider_key or "official_access",
                        "query_terms": terms,
                        "probe_timeout": probe_timeout,
                        "allow_term_fallback": allow_term_fallback,
                        "max_results": min(max_candidates, max(1, int(routed_params.get("limit") or 10))),
                        "candidate_scoring_config": routed_params.get("candidate_scoring_config")
                        or routed_params.get("candidate_selection_config"),
                    },
                    project_key=project_key,
                )
                for error_row in result.get("errors") or []:
                    local_errors.append(
                        {
                            "site_url": base_url,
                            "error": str(error_row.get("error") or f"official_api_search_failed:{policy.provider_key or 'official_access'}"),
                            "policy_category": policy.category,
                            "policy_reason": policy.reason,
                            "error_class": str(error_row.get("error_class") or "").strip() or "transport_failure",
                            "search_service_used": "official_api",
                            "recommended_search_service": "official_api",
                        }
                    )
                for u in result.get("candidates") or []:
                    candidate_url = str(u or "").strip()
                    if not candidate_url:
                        continue
                    local_candidates.append(
                        (
                            candidate_url,
                            {
                                "site_entry_url": base_url,
                                "entry_type": etype,
                                "domain": entry_domain,
                                "entry_domain": entry_domain,
                                "tool": "official_access.api",
                                "candidate_source": "official_api_search",
                                "site_policy": policy.category,
                                "search_service": "official_api",
                                "search_service_fallbacks": 0,
                                "provider_key": policy.provider_key or "official_access",
                            },
                            1.0,
                        )
                    )
                if not local_candidates and not local_errors:
                    local_errors.append(
                        {
                            "site_url": base_url,
                            "error": f"site_policy_api_preferred:{policy.provider_key or 'official_access'}",
                            "policy_category": policy.category,
                            "policy_reason": policy.reason,
                            "search_service_used": "official_api",
                            "recommended_search_service": "official_api",
                        }
                    )
                entry_runtime["search_service"] = "official_api"
                return {"entry": entry_view, "runtime": entry_runtime, "candidates": local_candidates, "errors": local_errors}
            if policy.category == "social_skip":
                local_errors.append(
                    {
                        "site_url": base_url,
                        "error": "site_policy_social_skip",
                        "policy_category": policy.category,
                        "policy_reason": policy.reason,
                        "search_service_used": policy.preferred_search_service or "skip",
                        "recommended_search_service": policy.preferred_search_service or "platform_api",
                    }
                )
                return {"entry": entry_view, "runtime": entry_runtime, "candidates": local_candidates, "errors": local_errors}
            if policy.category == "deprioritized" and not allow_deprioritized:
                local_errors.append(
                    {
                        "site_url": base_url,
                        "error": "site_policy_deprioritized_skip",
                        "policy_category": policy.category,
                        "policy_reason": policy.reason,
                        "search_service_used": policy.preferred_search_service or "skip",
                        "recommended_search_service": policy.preferred_search_service or "resilient",
                    }
                )
                return {"entry": entry_view, "runtime": entry_runtime, "candidates": local_candidates, "errors": local_errors}
            if policy.category == "external_preferred" and etype == "search_template":
                execution = execute_external_site_search(
                    entry_domain=entry_domain,
                    query_terms=terms,
                    probe_timeout=probe_timeout,
                    allow_term_fallback=allow_term_fallback,
                    params=routed_params,
                )
                for error_row in execution.errors:
                    local_errors.append(
                        {
                            "site_url": base_url,
                            "error": str(error_row.get("error") or "external_search_execution_failed"),
                            "error_class": str(error_row.get("error_class") or "").strip() or None,
                            "search_url": str(error_row.get("search_url") or "").strip() or None,
                            "search_service_used": str(execution.diagnostics.get("search_service") or "external_search"),
                            "recommended_search_service": str(error_row.get("recommended_search_service") or "").strip() or "external_search",
                        }
                    )
                for decision in execution.selected_candidates:
                    u = str(decision.url or "").strip()
                    if not u:
                        continue
                    if entry_domain and (domain_from_url(u) or "").lower() != entry_domain:
                        continue
                    local_candidates.append(
                        (
                            u,
                            {
                                "site_entry_url": base_url,
                                "entry_type": etype,
                                "domain": entry_domain,
                                "entry_domain": entry_domain,
                                "tool": "search_template",
                                "candidate_source": "external_search",
                                "site_policy": policy.category,
                                "search_service": str(execution.diagnostics.get("search_service") or "external_search"),
                                "search_service_fallbacks": int(execution.diagnostics.get("search_service_fallbacks") or 0),
                                "matched_by": getattr(decision, "matched_by", None),
                                "route_kind": getattr(decision, "route_kind", "page"),
                                "candidate_quality": getattr(decision, "candidate_quality", None),
                                "usable_for_search": getattr(decision, "usable_for_search", None),
                            },
                            float(getattr(decision, "score", 0.0) or 0.0),
                        )
                    )
                entry_runtime["search_service"] = str(execution.diagnostics.get("search_service") or "external_search")
                entry_runtime["search_service_fallbacks"] = int(execution.diagnostics.get("search_service_fallbacks") or 0)
                if not execution.selected_candidates:
                    local_errors.append(
                        {
                            "site_url": base_url,
                            "error": "browser_candidate_required",
                            "error_class": "deferred_browser_required",
                            "search_service_code": "browser_candidate_deferred",
                            "search_service_used": str(execution.diagnostics.get("search_service") or "external_search"),
                            "recommended_search_service": "browser_candidate_deferred",
                            "next_step": "slow_lane_deferred",
                            "browser_candidate_enqueued": True,
                            "browser_candidate_reason": "throttle_or_blocking_signals",
                        }
                    )
                    entry_runtime["browser_candidate_deferred"] = True
                    entry_runtime["browser_candidate_reason"] = "throttle_or_blocking_signals"
                    entry_runtime["search_service_degraded_to"] = "browser_candidate_deferred"
                return {"entry": entry_view, "runtime": entry_runtime, "candidates": local_candidates, "errors": local_errors}
            if not _entry_supports_query_terms(entry, etype):
                return {"entry": None, "runtime": entry_runtime, "candidates": local_candidates, "errors": local_errors}
            # Only keep sources that can accept keyword parameters directly.
            # e.g. search_template(q={{q}}). Filter-style sources (rss/sitemap) are excluded
            # from keyword candidate pool to avoid semantic confusion.
            if _entry_keyword_mode(entry, etype) not in {"search", "filter"}:
                return {"entry": None, "runtime": entry_runtime, "candidates": local_candidates, "errors": local_errors}

            def _push_local(u: str, *, ref: dict[str, Any], score: float = 0.0) -> None:
                if u:
                    local_candidates.append((u, ref, score))

            if etype == "rss":
                execution = execute_feed_probe(
                    feed_url=base_url,
                    query_terms=terms,
                    probe_timeout=probe_timeout,
                    allow_term_fallback=allow_term_fallback,
                    params=routed_params,
                )
                for error_row in execution.errors:
                    local_errors.append(
                        {
                            "site_url": base_url,
                            "error": str(error_row.get("error") or "rss_candidate_generation_failed"),
                            "error_class": str(error_row.get("error_class") or "").strip() or None,
                            "search_service_used": "feed_native",
                        }
                    )
                if execution.used_term_fallback:
                    local_errors.append(
                        {
                            "site_url": base_url,
                            "error": (
                                "url_term_filter_empty_fallback_used"
                                if allow_term_fallback
                                else "url_term_filter_empty_no_fallback"
                            ),
                        }
                    )
                for decision in execution.selected_candidates:
                    u = str(decision.url or "").strip()
                    if not u:
                        continue
                    _push_local(
                        u,
                        ref={
                            "site_entry_url": base_url,
                            "entry_type": etype,
                            "domain": entry_domain,
                            "entry_domain": entry_domain,
                            "tool": "rss",
                            "candidate_source": "rss_feed",
                            "site_policy": policy.category,
                            "matched_by": decision.matched_by,
                            "route_kind": getattr(decision, "route_kind", "page"),
                            "candidate_quality": decision.candidate_quality,
                            "usable_for_search": decision.usable_for_search,
                        },
                        score=decision.score,
                    )
                entry_runtime["search_service"] = "feed_native"
            elif etype == "sitemap":
                execution = execute_sitemap_probe(
                    sitemap_url=base_url,
                    query_terms=terms,
                    probe_timeout=probe_timeout,
                    max_depth=max(0, int(sitemap_max_depth)),
                    max_sitemaps=max(1, int(sitemap_max_sitemaps)),
                    allow_term_fallback=allow_term_fallback,
                    params=routed_params,
                )
                for error_row in execution.errors:
                    local_errors.append(
                        {
                            "site_url": base_url,
                            "error": str(error_row.get("error") or "sitemap_candidate_generation_failed"),
                            "error_class": str(error_row.get("error_class") or "").strip() or None,
                            "search_service_used": "sitemap_native",
                        }
                    )
                if execution.used_term_fallback:
                    local_errors.append(
                        {
                            "site_url": base_url,
                            "error": (
                                "url_term_filter_empty_fallback_used"
                                if allow_term_fallback
                                else "url_term_filter_empty_no_fallback"
                            ),
                        }
                    )
                for decision in execution.selected_candidates:
                    u = str(decision.url or "").strip()
                    if not u:
                        continue
                    if entry_domain and (domain_from_url(u) or "").lower() != entry_domain:
                        continue
                    _push_local(
                        u,
                        ref={
                            "site_entry_url": base_url,
                            "entry_type": etype,
                            "domain": entry_domain,
                            "entry_domain": entry_domain,
                            "tool": "sitemap",
                            "candidate_source": "sitemap_probe",
                            "site_policy": policy.category,
                            "matched_by": decision.matched_by,
                            "route_kind": getattr(decision, "route_kind", "page"),
                            "candidate_quality": decision.candidate_quality,
                            "usable_for_search": decision.usable_for_search,
                        },
                        score=decision.score,
                    )
                entry_runtime["search_service"] = "sitemap_native"
            elif etype == "search_template":
                adapter_plan = resolve_search_template_adapter_plan(
                    site_url=base_url,
                    entry_domain=entry_domain,
                    params=routed_params,
                )
                routed_params = apply_search_template_adapter_plan(
                    plan=adapter_plan,
                    params=routed_params,
                )
                entry_runtime["search_template_adapter"] = adapter_plan.adapter_key
                for key in (
                    "adapter_capability_status",
                    "adapter_capability_reason",
                    "parser_profile_requested",
                    "parser_profile_resolved",
                ):
                    value = routed_params.get(key)
                    if value not in (None, ""):
                        entry_runtime[key] = value
                if routed_params.get("candidate_relevance_review_required"):
                    entry_runtime["relevance_review_required"] = True
                    entry_runtime["relevance_review_reason"] = str(
                        routed_params.get("adapter_capability_reason") or "parser_profile_review"
                    )
                if adapter_plan.reason:
                    entry_runtime["search_template_adapter_reason"] = adapter_plan.reason
                pinned_template, pinned_terms = _resolve_pinned_search_contract(entry, terms)
                tpl = _normalize_search_template_placeholders(str(pinned_template or template or base_url).strip())
                if "{{q}}" not in tpl:
                    local_errors.append(
                        {
                            "site_url": base_url,
                            "error": "search_template_missing_query_placeholder",
                            "error_class": "invalid_configuration",
                            "search_service_used": str(routed_params.get("search_service") or policy.preferred_search_service or "basic"),
                            "recommended_search_service": None,
                        }
                    )
                    entry_runtime["search_service"] = str(routed_params.get("search_service") or policy.preferred_search_service or "basic")
                    entry_runtime["template_config_valid"] = False
                    return {"entry": entry_view, "runtime": entry_runtime, "candidates": local_candidates, "errors": local_errors}
                execution = execute_search_template(
                    template=tpl,
                    query_terms=pinned_terms,
                    params=routed_params,
                    probe_timeout=probe_timeout,
                    allow_term_fallback=allow_term_fallback,
                    entry_domain=entry_domain,
                )
                external_execution = None
                if (
                    policy.category == "keep"
                    and external_search_enabled
                    and not execution.selected_candidates
                ):
                    external_execution = execute_external_site_search(
                        entry_domain=entry_domain,
                        query_terms=pinned_terms,
                        probe_timeout=probe_timeout,
                        allow_term_fallback=allow_term_fallback,
                        params=routed_params,
                    )
                    if external_execution.selected_candidates:
                        execution = external_execution
                for error_row in execution.errors:
                    local_errors.append(
                        {
                            "site_url": base_url,
                            "error": str(error_row.get("error") or "search_template_execution_failed"),
                            "error_class": str(error_row.get("error_class") or "").strip() or None,
                            "search_url": str(error_row.get("search_url") or "").strip() or None,
                            "search_service_used": str(execution.diagnostics.get("search_service") or routed_params.get("search_service") or "basic"),
                            "recommended_search_service": str(error_row.get("recommended_search_service") or "").strip() or None,
                        }
                    )
                if external_execution is not None and external_execution.selected_candidates:
                    local_errors.append(
                        {
                            "site_url": base_url,
                            "error": "external_search_fallback_used",
                            "search_service_used": "external_search",
                            "recommended_search_service": "external_search",
                        }
                    )
                if not execution.selected_candidates and policy.category == "keep":
                    local_errors.append(
                        {
                            "site_url": base_url,
                            "error": "browser_candidate_required",
                            "error_class": "deferred_browser_required",
                            "search_service_code": "browser_candidate_deferred",
                            "search_service_used": str(execution.diagnostics.get("search_service") or routed_params.get("search_service") or "basic"),
                            "recommended_search_service": "browser_candidate_deferred",
                            "next_step": "slow_lane_deferred",
                            "browser_candidate_enqueued": True,
                            "browser_candidate_reason": "throttle_or_blocking_signals",
                        }
                    )
                    entry_runtime["browser_candidate_deferred"] = True
                    entry_runtime["browser_candidate_reason"] = "throttle_or_blocking_signals"
                    entry_runtime["search_service_degraded_to"] = "browser_candidate_deferred"
                if execution.used_term_fallback:
                    local_errors.append(
                        {
                            "site_url": base_url,
                            "error": (
                                "url_term_filter_empty_fallback_used"
                                if allow_term_fallback
                                else "url_term_filter_empty_no_fallback"
                            ),
                        }
                    )
                    entry_runtime["relevance_review_required"] = True
                    entry_runtime["relevance_review_reason"] = "term_fallback_candidates"
                start_page, max_pages = _resolve_search_template_pagination(params)
                review_required = bool(entry_runtime.get("relevance_review_required"))
                for decision in execution.selected_candidates:
                    u = str(decision.url or "").strip()
                    if not u:
                        continue
                    if entry_domain and (domain_from_url(u) or "").lower() != entry_domain:
                        continue
                    _push_local(
                        u,
                        ref={
                            "site_entry_url": base_url,
                            "entry_type": etype,
                            "domain": entry_domain,
                            "entry_domain": entry_domain,
                            "tool": "search_template",
                            "candidate_source": "external_search" if external_execution is not None and execution is external_execution else "search_template",
                            "site_policy": policy.category,
                            "search_service": str(execution.diagnostics.get("search_service") or "basic"),
                            "search_service_fallbacks": int(execution.diagnostics.get("search_service_fallbacks") or 0),
                            "search_pages": [start_page, start_page + max_pages - 1],
                            "matched_by": decision.matched_by,
                            "route_kind": getattr(decision, "route_kind", "page"),
                            "candidate_quality": decision.candidate_quality,
                            "usable_for_search": decision.usable_for_search,
                            "parser_container_hit": int(execution.diagnostics.get("parser_container_hit") or 0),
                            "parser_structured_hit": int(execution.diagnostics.get("parser_structured_hit") or 0),
                            "parser_json_ld_hit": int(execution.diagnostics.get("parser_json_ld_hit") or 0),
                            "parser_global_anchor_hit": int(execution.diagnostics.get("parser_global_anchor_hit") or 0),
                            "parser_candidate_rejected_low_value": int(
                                execution.diagnostics.get("parser_candidate_rejected_low_value") or 0
                            ),
                            "adapter_capability_status": str(routed_params.get("adapter_capability_status") or "allow"),
                            "parser_profile_resolved": str(
                                routed_params.get("parser_profile_resolved")
                                or routed_params.get("parser_profile")
                                or ""
                            ),
                            "candidate_review_state": "relevance_review" if review_required else "auto_selected",
                            "relevance_review_required": review_required,
                        },
                        score=decision.score,
                    )
                entry_runtime["search_service"] = str(execution.diagnostics.get("search_service") or routed_params.get("search_service") or "basic")
                entry_runtime["search_service_fallbacks"] = int(execution.diagnostics.get("search_service_fallbacks") or 0)
                entry_runtime["search_template_adapter_mode"] = adapter_plan.execution_mode
                for key in (
                    "parser_container_hit",
                    "parser_structured_hit",
                    "parser_json_ld_hit",
                    "parser_global_anchor_hit",
                    "parser_candidate_rejected_low_value",
                ):
                    entry_runtime[key] = int(execution.diagnostics.get(key) or 0)
            else:
                local_errors.append({"site_url": base_url, "error": f"unsupported query entry_type: {etype}"})
            return {"entry": entry_view, "runtime": entry_runtime, "candidates": local_candidates, "errors": local_errors}
        except HttpFetchError as exc:
            local_errors.append({"site_url": su, "error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            local_errors.append({"site_url": su, "error": str(exc)})
        return {"entry": None, "runtime": None, "candidates": local_candidates, "errors": local_errors}

    scored_candidates: list[tuple[float, str, dict[str, Any]]] = []
    target_limit = _effective_candidate_target_limit(
        max_candidates=max_candidates,
        config=candidate_target_config,
    )
    execution_batches = _build_site_entry_execution_batches(
        site_entry_urls=site_entry_urls,
        project_key=project_key,
        config=candidate_target_config,
    )
    for wave in execution_batches:
        max_workers = max(1, min(8, len(wave)))
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = [ex.submit(_process_site_entry, su) for su in wave]
            for fut in as_completed(futures):
                res = fut.result()
                entry = res.get("entry")
                if isinstance(entry, dict):
                    used_entries.append(entry)
                runtime = res.get("runtime")
                if isinstance(runtime, dict):
                    runtime_diagnostics.append(runtime)
                for e in res.get("errors") or []:
                    if isinstance(e, dict):
                        errors.append(e)
                for u, ref, score in (res.get("candidates") or []):
                    scored_candidates.append((float(score or 0.0), u, ref))
        scored_candidates.sort(key=lambda item: (-item[0], item[1]))
        selected_scored_candidates = _apply_candidate_target_selection(
            scored_candidates,
            max_candidates=max_candidates,
            config=candidate_target_config,
        )
        if _should_allow_wave_early_stop(candidate_target_config) and len(selected_scored_candidates) >= target_limit:
            break

    scored_candidates.sort(key=lambda item: (-item[0], item[1]))
    selected_scored_candidates = _apply_candidate_target_selection(
        scored_candidates,
        max_candidates=max_candidates,
        config=candidate_target_config,
    )
    for _, u, ref in selected_scored_candidates:
        _push(u, ref=ref)

    relevance_review_queue = build_relevance_review_queue(
        project_key=project_key,
        item_key=item_key,
        query_terms=terms,
        candidates=candidates,
        candidate_refs=candidate_refs,
        runtime_diagnostics=runtime_diagnostics,
        errors=errors,
    )
    review_entries_by_url = {
        str((entry.get("reviewer_fields") or {}).get("url") or "").strip(): entry
        for entry in relevance_review_queue.get("entries") or []
        if isinstance(entry, dict)
    }

    written: dict[str, int] | None = None
    if auto_ingest:
        try:
            history_pool_urls = _collect_history_pool_urls(
                scope=pool_scope,
                project_key=project_key,
                source=pool_source,
            )
        except Exception:
            history_pool_urls = set()

    if write_to_pool and candidates:
        new_count = 0
        skipped = 0
        for u in candidates:
            ref = dict(candidate_refs.get(u) or {})
            if not str(ref.get("domain") or "").strip():
                ref["domain"] = (
                    str(ref.get("entry_domain") or domain_from_url(str(ref.get("site_entry_url") or u)) or "").strip().lower()
                    or None
                )
            review_entry = review_entries_by_url.get(u)
            if review_entry:
                ref["candidate_review_state"] = "relevance_review"
                ref["source_library_relevance_review"] = {
                    "contract_version": relevance_review_queue["contract_version"],
                    "queue_id": str(review_entry.get("queue_id") or "").strip(),
                    "reason_codes": list(review_entry.get("reason_codes") or []),
                    "auto_accept_allowed": False,
                    "auto_ingest_allowed": False,
                    "review_completed": False,
                }
            ok = append_url(
                url=u,
                source=pool_source,
                source_ref={"item_key": item_key, "query_terms": terms, **ref},
                scope=pool_scope,
                project_key=project_key,
            )
            if ok:
                new_count += 1
            else:
                skipped += 1
        written = {"urls_new": new_count, "urls_skipped": skipped}

    ingest_result: dict[str, Any] | None = None
    if auto_ingest and (written or candidates):
        try:
            from ..ingest.url_pool import collect_urls_from_list
            from ..projects import bind_project

            ingest_candidates = [u for u in candidates if u not in history_pool_urls]
            review_blocked = [u for u in ingest_candidates if u in review_entries_by_url]
            if review_blocked:
                errors.append(
                    {
                        "phase": "auto_ingest",
                        "error": "relevance_review_required_auto_ingest_skipped",
                        "error_class": "relevance_review_required",
                        "skipped_count": str(len(review_blocked)),
                    }
                )
            ingest_candidates = [u for u in ingest_candidates if u not in review_entries_by_url]
            ingest_candidates = ingest_candidates[: max(1, min(int(ingest_limit), len(ingest_candidates)))]
            with bind_project(project_key):
                # Auto-ingest should consume current-run candidates directly, instead of
                # pulling historical URLs from shared unified_search pool.
                ir = collect_urls_from_list(
                    ingest_candidates,
                    project_key=project_key,
                    query_terms=terms,
                    enable_extraction=bool(enable_extraction),
                    extra_params={"url_target_mode": "detail_only"},
                )
            debug = ir.get("debug")
            if not isinstance(debug, dict):
                debug = {}
                ir["debug"] = debug
            debug["history_pool_filter_applied"] = True
            debug["history_pool_size"] = len(history_pool_urls)
            debug["ingest_candidates_count"] = len(ingest_candidates)
            ingest_result = ir
        except Exception as exc:  # noqa: BLE001
            errors.append({"phase": "auto_ingest", "error": str(exc)})

    return UnifiedSearchResult(
        item_key=item_key,
        query_terms=terms,
        site_entries_used=used_entries,
        runtime_diagnostics=runtime_diagnostics,
        candidates=candidates,
        written=written,
        ingest_result=ingest_result,
        errors=errors,
        relevance_review_queue=relevance_review_queue,
    )
