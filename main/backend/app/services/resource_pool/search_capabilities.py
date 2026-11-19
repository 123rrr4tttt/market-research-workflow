"""Capability-style scoring helpers for resource pool search strategies."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Annotated, Any, SupportsFloat, SupportsIndex, TypeGuard, cast
from urllib.parse import parse_qsl, urlsplit

from .url_utils import domain_from_url, normalize_url

_GENERIC_NAV_TEXTS = {
    "",
    "skip to content",
    "skip to main content",
    "sign in",
    "sign up",
    "log in",
    "login",
    "posts",
    "comments",
    "communities",
    "media",
    "cookie preferences",
}

_LOW_SIGNAL_URL_MARKERS = (
    "/search",
    "/find",
    "/query",
    "/login",
    "/signin",
    "/sign-in",
    "/signup",
    "/sign-up",
    "/register",
    "/privacy",
    "/terms",
    "/account",
)
_DEFAULT_MATCH_WEIGHTS = {
    "title": 1.0,
    "text": 0.9,
    "summary": 0.8,
    "title_hint": 0.65,
    "url": 0.55,
}
_DEFAULT_ROUTE_KIND_SCORE_BONUS = {
    "article": 0.12,
    "publication_hub": 0.05,
    "research_tool": 0.03,
    "event": 0.01,
    "section": 0.0,
    "collection": -0.05,
    "page": 0.0,
}
_DEFAULT_PENALTIES = {
    "cross_domain": 0.2,
    "self_search_link": 0.45,
    "low_signal_navigation": 0.35,
}
_DEFAULT_THRESHOLDS = {
    "search_template": 0.65,
    "rss": 0.45,
    "sitemap": 0.45,
    "external_search": 0.65,
    "default": 0.45,
}


def _is_string_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict) and all(
        isinstance(key, str) for key in cast(dict[object, object], value)
    )


def _optional_float(value: object) -> float | None:
    if isinstance(value, (str, bytes, bytearray, SupportsFloat, SupportsIndex)):
        try:
            return float(value)
        except Exception:
            return None
    return None


@dataclass(frozen=True)
class SearchCapabilityCandidate:
    url: str
    strategy: str
    text: str = ""
    title: str = ""
    summary: str = ""
    extra: dict[str, Any] = field(default_factory=dict[str, object])


@dataclass(frozen=True)
class SearchCapabilityScore:
    url: str
    strategy: str
    fetchability: str
    matched_by: str
    route_kind: str
    candidate_quality: str
    score: float
    usable_for_search: bool
    reasons: tuple[str, ...] = ()
    text: str = ""
    title: str = ""


@dataclass(frozen=True)
class SearchCapabilityScoringConfig:
    match_weights: dict[str, float]
    route_kind_bonus: dict[str, float]
    penalties: dict[str, float]
    thresholds: dict[str, float]
    raw_overrides: dict[str, Any] = field(default_factory=dict[str, object])


def resolve_candidate_scoring_config(raw: dict[str, Any] | str | None) -> SearchCapabilityScoringConfig:
    payload = _parse_scoring_config_payload(raw)
    return SearchCapabilityScoringConfig(
        match_weights=_merge_numeric_map(
            _DEFAULT_MATCH_WEIGHTS,
            payload.get("match_weights"),
            minimum=0.0,
            maximum=2.0,
        ),
        route_kind_bonus=_merge_numeric_map(
            _DEFAULT_ROUTE_KIND_SCORE_BONUS,
            payload.get("route_kind_bonus") or payload.get("route_kind_weights"),
            minimum=-1.0,
            maximum=1.0,
        ),
        penalties=_merge_numeric_map(
            _DEFAULT_PENALTIES,
            payload.get("penalties"),
            minimum=0.0,
            maximum=2.0,
        ),
        thresholds=_merge_numeric_map(
            _DEFAULT_THRESHOLDS,
            payload.get("thresholds") or payload.get("strategy_thresholds"),
            minimum=0.0,
            maximum=2.0,
        ),
        raw_overrides=payload,
    )


def build_capability_candidates(
    strategy: str,
    raw_candidates: list[dict[str, Any] | str],
) -> Annotated[
    list[SearchCapabilityCandidate],
    "kit:non-authoritative derived_as=view fact_source=strategy+raw_candidates+url_normalization witness=test:test_ingest_ports_declare_sources_and_effect_authority",
]:
    out: list[SearchCapabilityCandidate] = []
    seen: set[str] = set()
    normalized_strategy = (strategy or "").strip().lower() or "unknown"
    for raw in raw_candidates:
        if isinstance(raw, dict):
            url = normalize_url(str(raw.get("url") or "").strip())
            text = str(raw.get("text") or "").strip()
            title = str(raw.get("title") or "").strip()
            summary = str(raw.get("summary") or "").strip()
            raw_extra = raw.get("extra")
            extra: dict[str, Any] = raw_extra if _is_string_object_dict(raw_extra) else {}
        else:
            url = normalize_url(str(raw).strip())
            text = ""
            title = ""
            summary = ""
            extra = {}
        if not url or url in seen:
            continue
        seen.add(url)
        extra = dict(extra)
        parts = urlsplit(url)
        extra.setdefault("source_url", str(extra.get("source_url") or "").strip())
        extra.setdefault("entry_domain", str(extra.get("entry_domain") or "").strip().lower())
        slug = (parts.path or "").rstrip("/").rsplit("/", 1)[-1].rsplit(".", 1)[0]
        extra.setdefault("title_hint", slug.replace("-", " ").replace("_", " "))
        extra.setdefault("route_kind", _infer_route_kind(url))
        out.append(
            SearchCapabilityCandidate(
                url=url,
                strategy=normalized_strategy,
                text=text,
                title=title,
                summary=summary,
                extra=extra,
            )
        )
    return out


def make_search_candidate(
    *,
    url: str,
    strategy: str,
    title: str = "",
    text: str = "",
    summary: str = "",
    source_url: str = "",
    entry_domain: str = "",
    metadata: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> SearchCapabilityCandidate | None:
    payload_extra = {"source_url": source_url, "entry_domain": entry_domain}
    if metadata:
        payload_extra.update(metadata)
    if extra:
        payload_extra.update(extra)
    built = build_capability_candidates(
        strategy,
        [
            {
                "url": url,
                "title": title,
                "text": text,
                "summary": summary,
                "extra": payload_extra,
            }
        ],
    )
    return built[0] if built else None


def select_scored_candidates(
    scored: list[SearchCapabilityScore],
    *,
    allow_fallback: bool,
    fallback_limit: int = 30,
) -> tuple[list[SearchCapabilityScore], bool]:
    usable = [item for item in scored if item.usable_for_search]
    if usable:
        return usable, False
    if not allow_fallback:
        return [], True
    limit = max(1, int(fallback_limit))
    return scored[:limit], True


def select_search_candidates(
    candidates: list[SearchCapabilityCandidate],
    query_terms: list[str],
    *,
    strategy: str | None = None,
    entry_domain: str | None = None,
    search_url: str | None = None,
    allow_fallback: bool,
    fallback_limit: int = 30,
    scoring_config: dict[str, Any] | str | None = None,
) -> tuple[list[SearchCapabilityScore], bool]:
    if not candidates:
        return [], bool(query_terms)

    first = candidates[0]
    normalized_strategy = (strategy or first.strategy or "").strip().lower()
    effective_domain = entry_domain or str(first.extra.get("entry_domain") or "").strip().lower() or None
    effective_search_url = search_url or str(first.extra.get("source_url") or "").strip() or None
    if normalized_strategy == "rss":
        scored = score_rss_candidates(
            candidates,
            query_terms=query_terms,
            entry_domain=effective_domain,
            scoring_config=scoring_config,
        )
    elif normalized_strategy == "sitemap":
        scored = score_sitemap_candidates(
            candidates,
            query_terms=query_terms,
            entry_domain=effective_domain,
            scoring_config=scoring_config,
        )
    else:
        scored = score_search_template_candidates(
            candidates,
            query_terms=query_terms,
            entry_domain=effective_domain,
            search_url=effective_search_url,
            scoring_config=scoring_config,
        )
    return select_scored_candidates(
        scored,
        allow_fallback=allow_fallback,
        fallback_limit=fallback_limit,
    )


def evaluate_search_candidate(
    candidate: SearchCapabilityCandidate,
    query_terms: list[str],
    *,
    entry_domain: str | None = None,
    search_url: str | None = None,
    scoring_config: dict[str, Any] | str | None = None,
) -> SearchCapabilityScore:
    strategy = (candidate.strategy or "").strip().lower()
    effective_domain = entry_domain or str(candidate.extra.get("entry_domain") or "").strip().lower() or None
    effective_search_url = search_url or str(candidate.extra.get("source_url") or "").strip() or None
    if strategy == "rss":
        return score_rss_candidates(
            [candidate],
            query_terms=query_terms,
            entry_domain=effective_domain,
            scoring_config=scoring_config,
        )[0]
    if strategy == "sitemap":
        return score_sitemap_candidates(
            [candidate],
            query_terms=query_terms,
            entry_domain=effective_domain,
            scoring_config=scoring_config,
        )[0]
    return score_search_template_candidates(
        [candidate],
        query_terms=query_terms,
        entry_domain=effective_domain,
        search_url=effective_search_url,
        scoring_config=scoring_config,
    )[0]


def score_search_template_candidates(
    candidates: list[SearchCapabilityCandidate],
    *,
    query_terms: list[str],
    entry_domain: str | None,
    search_url: str | None,
    scoring_config: dict[str, Any] | str | None = None,
) -> list[SearchCapabilityScore]:
    config = resolve_candidate_scoring_config(scoring_config)
    return _score_candidates(
        candidates,
        strategy="search_template",
        query_terms=query_terms,
        entry_domain=entry_domain,
        low_confidence_min_score=float(config.thresholds.get("search_template", _DEFAULT_THRESHOLDS["search_template"])),
        search_url=search_url,
        include_summary=True,
        config=config,
    )


def score_rss_candidates(
    candidates: list[SearchCapabilityCandidate],
    *,
    query_terms: list[str],
    entry_domain: str | None,
    scoring_config: dict[str, Any] | str | None = None,
) -> list[SearchCapabilityScore]:
    config = resolve_candidate_scoring_config(scoring_config)
    return _score_candidates(
        candidates,
        strategy="rss",
        query_terms=query_terms,
        entry_domain=entry_domain,
        low_confidence_min_score=float(config.thresholds.get("rss", _DEFAULT_THRESHOLDS["rss"])),
        search_url=None,
        include_summary=True,
        config=config,
    )


def score_sitemap_candidates(
    candidates: list[SearchCapabilityCandidate],
    *,
    query_terms: list[str],
    entry_domain: str | None,
    scoring_config: dict[str, Any] | str | None = None,
) -> list[SearchCapabilityScore]:
    config = resolve_candidate_scoring_config(scoring_config)
    return _score_candidates(
        candidates,
        strategy="sitemap",
        query_terms=query_terms,
        entry_domain=entry_domain,
        low_confidence_min_score=float(config.thresholds.get("sitemap", _DEFAULT_THRESHOLDS["sitemap"])),
        search_url=None,
        include_summary=False,
        config=config,
    )


def _score_candidates(
    candidates: list[SearchCapabilityCandidate],
    *,
    strategy: str,
    query_terms: list[str],
    entry_domain: str | None,
    low_confidence_min_score: float,
    search_url: str | None,
    include_summary: bool,
    config: SearchCapabilityScoringConfig,
) -> list[SearchCapabilityScore]:
    scored: list[SearchCapabilityScore] = []
    normalized_entry_domain = (entry_domain or "").strip().lower()
    normalized_search_url = normalize_url(search_url or "")
    for candidate in candidates:
        reasons: list[str] = []
        match_score = 0.0
        matched_by = "none"
        route_kind = str(candidate.extra.get("route_kind") or "page").strip() or "page"

        title_hit = _matches_any(query_terms, [candidate.title])
        text_hit = _matches_any(query_terms, [candidate.text])
        summary_hit = include_summary and _matches_any(query_terms, [candidate.summary])
        title_hint_hit = _matches_any(query_terms, [str(candidate.extra.get("title_hint") or "")])
        url_hit = _matches_any(query_terms, [candidate.url])
        if title_hit:
            matched_by = "title"
            match_score = float(config.match_weights.get("title", _DEFAULT_MATCH_WEIGHTS["title"]))
        elif text_hit:
            matched_by = "text"
            match_score = float(config.match_weights.get("text", _DEFAULT_MATCH_WEIGHTS["text"]))
        elif summary_hit:
            matched_by = "summary"
            match_score = float(config.match_weights.get("summary", _DEFAULT_MATCH_WEIGHTS["summary"]))
        elif title_hint_hit:
            matched_by = "title_hint"
            match_score = float(config.match_weights.get("title_hint", _DEFAULT_MATCH_WEIGHTS["title_hint"]))
        elif url_hit:
            matched_by = "url"
            match_score = float(config.match_weights.get("url", _DEFAULT_MATCH_WEIGHTS["url"]))

        if matched_by != "none":
            reasons.append(f"matched:{matched_by}")
        reasons.append(f"route_kind:{route_kind}")

        penalty = 0.0
        candidate_domain = (domain_from_url(candidate.url) or "").strip().lower()
        if normalized_entry_domain and candidate_domain and candidate_domain != normalized_entry_domain:
            penalty += float(config.penalties.get("cross_domain", _DEFAULT_PENALTIES["cross_domain"]))
            reasons.append("cross_domain")

        if _is_search_self_link(candidate.url, normalized_search_url):
            penalty += float(config.penalties.get("self_search_link", _DEFAULT_PENALTIES["self_search_link"]))
            reasons.append("self_search_link")

        if _is_low_signal_candidate(candidate):
            penalty += float(config.penalties.get("low_signal_navigation", _DEFAULT_PENALTIES["low_signal_navigation"]))
            reasons.append("low_signal_navigation")

        route_bonus = float(config.route_kind_bonus.get(route_kind, 0.0))
        if route_bonus:
            reasons.append(f"route_bonus:{route_bonus:+.2f}")
        score = max(0.0, round(match_score + route_bonus - penalty, 3))
        fetchability = "direct" if not candidate_domain or candidate_domain == normalized_entry_domain else "cross_domain"
        candidate_quality = _quality_label(score)
        effective_threshold = float(config.thresholds.get(strategy, config.thresholds.get("default", low_confidence_min_score)))
        usable = score >= effective_threshold and matched_by != "none"
        scored.append(
            SearchCapabilityScore(
                url=candidate.url,
                strategy=candidate.strategy,
                fetchability=fetchability,
                matched_by=matched_by,
                route_kind=route_kind,
                candidate_quality=candidate_quality,
                score=score,
                usable_for_search=usable,
                reasons=tuple(reasons),
                text=candidate.text,
                title=candidate.title,
            )
        )

    scored.sort(key=lambda item: (-item.score, item.url))
    return scored


def _parse_scoring_config_payload(raw: dict[str, Any] | str | None) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except Exception:
            return {}
        return dict(parsed) if _is_string_object_dict(parsed) else {}
    return {}


def _merge_numeric_map(
    default_map: dict[str, float],
    raw_overrides: Any,
    *,
    minimum: float,
    maximum: float,
) -> dict[str, float]:
    merged = dict(default_map)
    if not _is_string_object_dict(raw_overrides):
        return merged
    for key, value in raw_overrides.items():
        normalized_key = str(key or "").strip()
        if not normalized_key:
            continue
        numeric = _optional_float(value)
        if numeric is None:
            continue
        numeric = max(minimum, min(maximum, numeric))
        merged[normalized_key] = numeric
    return merged


def _normalize_match_text(value: str | None) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def normalize_match_text(value: str | None) -> str:
    return _normalize_match_text(value)


def _matches_any(query_terms: list[str], values: list[str]) -> bool:
    if not query_terms:
        return True
    normalized_values = [_normalize_match_text(value) for value in values if str(value or "").strip()]
    if not normalized_values:
        return False
    for term in query_terms:
        normalized_term = _normalize_match_text(term)
        if normalized_term and any(normalized_term in value for value in normalized_values):
            return True
    return False


def _quality_label(score: float) -> str:
    if score >= 0.95:
        return "high"
    if score >= 0.75:
        return "medium"
    if score >= 0.45:
        return "low"
    return "poor"


def _is_search_self_link(url: str, search_url: str | None) -> bool:
    normalized_url = normalize_url(url)
    if not normalized_url:
        return False
    if search_url and normalized_url == search_url:
        return True
    parts = urlsplit(normalized_url)
    path = (parts.path or "").lower()
    if any(marker in path for marker in ("/search", "/find", "/query")):
        query_keys = {k.lower() for (k, _) in parse_qsl(parts.query, keep_blank_values=True)}
        return bool({"q", "query", "search", "s"} & query_keys)
    return False


def _is_low_signal_candidate(candidate: SearchCapabilityCandidate) -> bool:
    text = _normalize_match_text(candidate.text or candidate.title)
    if text and text in _GENERIC_NAV_TEXTS:
        return True
    parts = urlsplit(candidate.url)
    path = (parts.path or "").lower()
    return any(marker in path for marker in _LOW_SIGNAL_URL_MARKERS)


def _infer_route_kind(url: str) -> str:
    path = str(urlsplit(url).path or "").lower()
    if re.search(r"/20\d{2}/\d{2}/", path):
        return "article"
    if any(marker in path for marker in ("/news/", "/article/", "/articles/", "/post/", "/posts/", "/story/", "/stories/")):
        return "article"
    if any(marker in path for marker in ("/publications", "/papers", "/reports", "/resources")):
        return "publication_hub"
    if any(marker in path for marker in ("/tool", "/index", "/dashboard")):
        return "research_tool"
    if any(marker in path for marker in ("/events", "/event/")):
        return "event"
    if any(marker in path for marker in ("/topic/", "/section/", "/sections/", "/category/", "/categories/", "/tag/", "/tags/")):
        return "section"
    if any(marker in path for marker in ("/collection", "/collections/", "/tracker", "/trendscapes", "/hub/")):
        return "collection"
    return "page"
