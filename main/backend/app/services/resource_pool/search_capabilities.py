"""Capability-style scoring helpers for resource pool search strategies."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
import time
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from ..extraction.json_utils import extract_json_payload
from ..llm.provider import get_local_fallback_chat
from ...settings.config import settings
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
    "semantic_title": 0.78,
    "semantic_text": 0.62,
    "semantic_summary": 0.54,
    "semantic_title_hint": 0.5,
    "semantic_url": 0.45,
    "llm_semantic": 0.74,
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
_SEMANTIC_MATCH_CACHE_TTL_SECONDS = 900.0
_SEMANTIC_MATCH_CACHE: dict[str, tuple[float, list[str]]] = {}


@dataclass(frozen=True)
class SearchCapabilityCandidate:
    url: str
    strategy: str
    text: str = ""
    title: str = ""
    summary: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


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
    raw_overrides: dict[str, Any] = field(default_factory=dict)


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
) -> list[SearchCapabilityCandidate]:
    out: list[SearchCapabilityCandidate] = []
    seen: set[str] = set()
    normalized_strategy = (strategy or "").strip().lower() or "unknown"
    for raw in raw_candidates:
        if isinstance(raw, dict):
            url = normalize_url(str(raw.get("url") or "").strip())
            text = str(raw.get("text") or "").strip()
            title = str(raw.get("title") or "").strip()
            summary = str(raw.get("summary") or "").strip()
            extra = raw.get("extra") if isinstance(raw.get("extra"), dict) else {}
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
    selected, used_fallback = select_scored_candidates(
        scored,
        allow_fallback=allow_fallback,
        fallback_limit=fallback_limit,
    )
    if selected or not query_terms or normalized_strategy in {"rss", "sitemap"}:
        return selected, used_fallback

    semantic_terms = _expand_semantic_query_terms_with_llm(query_terms)
    if not semantic_terms:
        return selected, used_fallback

    if normalized_strategy == "external_search":
        semantic_scored = _score_candidates(
            candidates,
            strategy="external_search",
            query_terms=query_terms,
            entry_domain=effective_domain,
            low_confidence_min_score=float(
                resolve_candidate_scoring_config(scoring_config).thresholds.get(
                    "external_search",
                    _DEFAULT_THRESHOLDS["external_search"],
                )
            ),
            search_url=effective_search_url,
            include_summary=True,
            config=resolve_candidate_scoring_config(scoring_config),
            semantic_terms=semantic_terms,
        )
    else:
        semantic_scored = score_search_template_candidates(
            candidates,
            query_terms=query_terms,
            entry_domain=effective_domain,
            search_url=effective_search_url,
            scoring_config=scoring_config,
            semantic_terms=semantic_terms,
        )
    semantic_selected, _semantic_used_fallback = select_scored_candidates(
        semantic_scored,
        allow_fallback=allow_fallback,
        fallback_limit=fallback_limit,
    )
    if semantic_selected:
        return semantic_selected, False
    llm_selected = _select_candidates_with_llm(
        query_terms=query_terms,
        candidates=candidates,
        scored_candidates=semantic_scored or scored,
        max_selected=min(max(1, int(fallback_limit)), 8),
        scoring_config=resolve_candidate_scoring_config(scoring_config),
    )
    if llm_selected:
        return llm_selected, False
    return selected, used_fallback


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
    semantic_terms: list[str] | None = None,
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
        semantic_terms=semantic_terms,
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
    semantic_terms: list[str] | None = None,
) -> list[SearchCapabilityScore]:
    scored: list[SearchCapabilityScore] = []
    normalized_entry_domain = (entry_domain or "").strip().lower()
    normalized_search_url = normalize_url(search_url or "")
    normalized_semantic_terms = _normalize_semantic_terms(semantic_terms or [])
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
        semantic_title_hit = bool(normalized_semantic_terms) and _matches_any(normalized_semantic_terms, [candidate.title])
        semantic_text_hit = bool(normalized_semantic_terms) and _matches_any(normalized_semantic_terms, [candidate.text])
        semantic_summary_hit = include_summary and bool(normalized_semantic_terms) and _matches_any(normalized_semantic_terms, [candidate.summary])
        semantic_title_hint_hit = bool(normalized_semantic_terms) and _matches_any(
            normalized_semantic_terms,
            [str(candidate.extra.get("title_hint") or "")],
        )
        semantic_url_hit = bool(normalized_semantic_terms) and _matches_any(normalized_semantic_terms, [candidate.url])

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
        elif semantic_title_hit:
            matched_by = "semantic_title"
            match_score = float(config.match_weights.get("semantic_title", _DEFAULT_MATCH_WEIGHTS["semantic_title"]))
        elif semantic_text_hit:
            matched_by = "semantic_text"
            match_score = float(config.match_weights.get("semantic_text", _DEFAULT_MATCH_WEIGHTS["semantic_text"]))
        elif semantic_summary_hit:
            matched_by = "semantic_summary"
            match_score = float(config.match_weights.get("semantic_summary", _DEFAULT_MATCH_WEIGHTS["semantic_summary"]))
        elif semantic_title_hint_hit:
            matched_by = "semantic_title_hint"
            match_score = float(config.match_weights.get("semantic_title_hint", _DEFAULT_MATCH_WEIGHTS["semantic_title_hint"]))
        elif semantic_url_hit:
            matched_by = "semantic_url"
            match_score = float(config.match_weights.get("semantic_url", _DEFAULT_MATCH_WEIGHTS["semantic_url"]))

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
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _merge_numeric_map(
    default_map: dict[str, float],
    raw_overrides: Any,
    *,
    minimum: float,
    maximum: float,
) -> dict[str, float]:
    merged = dict(default_map)
    if not isinstance(raw_overrides, dict):
        return merged
    for key, value in raw_overrides.items():
        normalized_key = str(key or "").strip()
        if not normalized_key:
            continue
        try:
            numeric = float(value)
        except Exception:
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


def _semantic_llm_available() -> bool:
    provider = (settings.llm_provider or "").lower()
    if provider == "openai":
        return bool(settings.openai_api_key)
    if provider == "azure":
        return bool(settings.azure_api_key)
    if provider == "ollama":
        return True
    if provider == "litellm":
        return bool(getattr(settings, "litellm_api_base", None))
    return False


def _normalize_semantic_terms(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _normalize_match_text(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def _semantic_cache_key(query_terms: list[str]) -> str:
    return "|".join(_normalize_semantic_terms(list(query_terms or [])))


def _read_semantic_match_cache(cache_key: str) -> list[str] | None:
    cached = _SEMANTIC_MATCH_CACHE.get(cache_key)
    if not cached:
        return None
    cached_at, payload = cached
    if (time.monotonic() - float(cached_at)) > _SEMANTIC_MATCH_CACHE_TTL_SECONDS:
        _SEMANTIC_MATCH_CACHE.pop(cache_key, None)
        return None
    return list(payload)


def _write_semantic_match_cache(cache_key: str, terms: list[str]) -> None:
    normalized = _normalize_semantic_terms(terms)
    if normalized:
        _SEMANTIC_MATCH_CACHE[cache_key] = (time.monotonic(), normalized)


def _build_semantic_match_prompt(query_terms: list[str]) -> str:
    return (
        "You expand search matching phrases for a candidate-selection pipeline.\n"
        "Given query terms, return strict JSON with key expanded_terms as an array of up to 8 short, "
        "high-precision phrases that might appear in titles or snippets of relevant pages.\n"
        "Rules:\n"
        "- Keep phrases literal and compact.\n"
        "- Prefer branded or domain phrases over generic words.\n"
        "- Avoid broad one-word terms unless they are a brand or product name.\n"
        "- Do not explain.\n"
        f"Query terms: {json.dumps(list(query_terms or []), ensure_ascii=False)}\n"
        'Return: {"expanded_terms": ["..."]}'
    )


def _build_llm_candidate_selection_prompt(
    query_terms: list[str],
    candidates: list[dict[str, Any]],
    *,
    max_selected: int,
) -> str:
    return (
        "You select relevant search candidates for a source-library matching pipeline.\n"
        "Given a user query and a candidate pool, return strict JSON with key selected_ids.\n"
        "Rules:\n"
        "- Choose at most the requested number of candidates.\n"
        "- Allow semantic association, related branded entities, adjacent product names, and likely relevant docs/articles.\n"
        "- Reject navigation pages, generic search pages, account pages, policy pages, and weak topical noise.\n"
        "- Prefer concrete docs, articles, APIs, models, tools, and research pages.\n"
        "- Do not explain.\n"
        f"Max selected: {int(max_selected)}\n"
        f"Query terms: {json.dumps(list(query_terms or []), ensure_ascii=False)}\n"
        f"Candidates: {json.dumps(candidates, ensure_ascii=False)}\n"
        'Return: {"selected_ids": ["c1", "c2"]}'
    )


def _expand_semantic_query_terms_with_llm(query_terms: list[str]) -> list[str]:
    normalized_queries = _normalize_semantic_terms(list(query_terms or []))
    if not normalized_queries or not _semantic_llm_available():
        return []
    cache_key = _semantic_cache_key(normalized_queries)
    cached = _read_semantic_match_cache(cache_key)
    if cached is not None:
        return cached
    try:
        model = get_local_fallback_chat(temperature=0.0, max_tokens=220)
        response = model.invoke(_build_semantic_match_prompt(normalized_queries))
        content = response.content if hasattr(response, "content") else str(response)
        payload = extract_json_payload(str(content or "")) or {}
        expanded = payload.get("expanded_terms")
        if not isinstance(expanded, list):
            return []
        semantic_terms = [
            str(item or "").strip()
            for item in expanded
            if str(item or "").strip()
        ][:8]
        normalized = _normalize_semantic_terms(semantic_terms)
        _write_semantic_match_cache(cache_key, normalized)
        return normalized
    except Exception:
        return []


def _select_candidates_with_llm(
    *,
    query_terms: list[str],
    candidates: list[SearchCapabilityCandidate],
    scored_candidates: list[SearchCapabilityScore],
    max_selected: int,
    scoring_config: SearchCapabilityScoringConfig,
) -> list[SearchCapabilityScore]:
    normalized_queries = _normalize_semantic_terms(list(query_terms or []))
    if not normalized_queries or not candidates or not _semantic_llm_available():
        return []
    scored_by_url = {item.url: item for item in scored_candidates}
    candidate_payload: list[dict[str, Any]] = []
    for idx, candidate in enumerate(candidates[:16], start=1):
        score = scored_by_url.get(candidate.url)
        candidate_payload.append(
            {
                "id": f"c{idx}",
                "url": candidate.url,
                "title": candidate.title,
                "summary": candidate.summary,
                "text": candidate.text[:280],
                "title_hint": str(candidate.extra.get("title_hint") or ""),
                "route_kind": str(candidate.extra.get("route_kind") or "page"),
                "pre_score": float(score.score if score is not None else 0.0),
                "pre_match": str(score.matched_by if score is not None else "none"),
            }
        )
    if not candidate_payload:
        return []
    try:
        model = get_local_fallback_chat(temperature=0.0, max_tokens=320)
        response = model.invoke(
            _build_llm_candidate_selection_prompt(
                normalized_queries,
                candidate_payload,
                max_selected=max_selected,
            )
        )
        content = response.content if hasattr(response, "content") else str(response)
        payload = extract_json_payload(str(content or "")) or {}
        selected_ids = payload.get("selected_ids")
        if not isinstance(selected_ids, list):
            return []
        allowed_ids = {str(item["id"]) for item in candidate_payload}
        ordered_ids: list[str] = []
        for item in selected_ids:
            value = str(item or "").strip()
            if value and value in allowed_ids and value not in ordered_ids:
                ordered_ids.append(value)
        if not ordered_ids:
            return []
        id_to_url = {str(item["id"]): str(item["url"]) for item in candidate_payload}
        out: list[SearchCapabilityScore] = []
        base_weight = float(scoring_config.match_weights.get("llm_semantic", _DEFAULT_MATCH_WEIGHTS["llm_semantic"]))
        for rank, candidate_id in enumerate(ordered_ids[:max_selected]):
            url = id_to_url.get(candidate_id)
            if not url:
                continue
            base = scored_by_url.get(url)
            if base is None:
                continue
            llm_score = max(
                float(base.score),
                round(max(0.0, base_weight - (0.02 * rank)), 3),
            )
            effective_threshold = float(
                scoring_config.thresholds.get(
                    base.strategy,
                    scoring_config.thresholds.get("default", _DEFAULT_THRESHOLDS["default"]),
                )
            )
            if llm_score < effective_threshold:
                continue
            reasons = list(base.reasons)
            reasons.append("matched:llm_semantic")
            out.append(
                SearchCapabilityScore(
                    url=base.url,
                    strategy=base.strategy,
                    fetchability=base.fetchability,
                    matched_by="llm_semantic",
                    route_kind=base.route_kind,
                    candidate_quality=_quality_label(llm_score),
                    score=llm_score,
                    usable_for_search=True,
                    reasons=tuple(reasons),
                    text=base.text,
                    title=base.title,
                )
            )
        return out
    except Exception:
        return []


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
