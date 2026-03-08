"""Capability-style scoring helpers for resource pool search strategies."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any
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
    candidate_quality: str
    score: float
    usable_for_search: bool
    reasons: tuple[str, ...] = ()
    text: str = ""
    title: str = ""


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
) -> tuple[list[SearchCapabilityScore], bool]:
    if not candidates:
        return [], bool(query_terms)

    first = candidates[0]
    normalized_strategy = (strategy or first.strategy or "").strip().lower()
    effective_domain = entry_domain or str(first.extra.get("entry_domain") or "").strip().lower() or None
    effective_search_url = search_url or str(first.extra.get("source_url") or "").strip() or None
    if normalized_strategy == "rss":
        scored = score_rss_candidates(candidates, query_terms=query_terms, entry_domain=effective_domain)
    elif normalized_strategy == "sitemap":
        scored = score_sitemap_candidates(candidates, query_terms=query_terms, entry_domain=effective_domain)
    else:
        scored = score_search_template_candidates(
            candidates,
            query_terms=query_terms,
            entry_domain=effective_domain,
            search_url=effective_search_url,
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
) -> SearchCapabilityScore:
    strategy = (candidate.strategy or "").strip().lower()
    effective_domain = entry_domain or str(candidate.extra.get("entry_domain") or "").strip().lower() or None
    effective_search_url = search_url or str(candidate.extra.get("source_url") or "").strip() or None
    if strategy == "rss":
        return score_rss_candidates([candidate], query_terms=query_terms, entry_domain=effective_domain)[0]
    if strategy == "sitemap":
        return score_sitemap_candidates([candidate], query_terms=query_terms, entry_domain=effective_domain)[0]
    return score_search_template_candidates(
        [candidate],
        query_terms=query_terms,
        entry_domain=effective_domain,
        search_url=effective_search_url,
    )[0]


def score_search_template_candidates(
    candidates: list[SearchCapabilityCandidate],
    *,
    query_terms: list[str],
    entry_domain: str | None,
    search_url: str | None,
) -> list[SearchCapabilityScore]:
    return _score_candidates(
        candidates,
        query_terms=query_terms,
        entry_domain=entry_domain,
        low_confidence_min_score=0.65,
        search_url=search_url,
        include_summary=False,
    )


def score_rss_candidates(
    candidates: list[SearchCapabilityCandidate],
    *,
    query_terms: list[str],
    entry_domain: str | None,
) -> list[SearchCapabilityScore]:
    return _score_candidates(
        candidates,
        query_terms=query_terms,
        entry_domain=entry_domain,
        low_confidence_min_score=0.45,
        search_url=None,
        include_summary=True,
    )


def score_sitemap_candidates(
    candidates: list[SearchCapabilityCandidate],
    *,
    query_terms: list[str],
    entry_domain: str | None,
) -> list[SearchCapabilityScore]:
    return _score_candidates(
        candidates,
        query_terms=query_terms,
        entry_domain=entry_domain,
        low_confidence_min_score=0.45,
        search_url=None,
        include_summary=False,
    )


def _score_candidates(
    candidates: list[SearchCapabilityCandidate],
    *,
    query_terms: list[str],
    entry_domain: str | None,
    low_confidence_min_score: float,
    search_url: str | None,
    include_summary: bool,
) -> list[SearchCapabilityScore]:
    scored: list[SearchCapabilityScore] = []
    normalized_entry_domain = (entry_domain or "").strip().lower()
    normalized_search_url = normalize_url(search_url or "")
    for candidate in candidates:
        reasons: list[str] = []
        match_score = 0.0
        matched_by = "none"

        title_hit = _matches_any(query_terms, [candidate.title])
        text_hit = _matches_any(query_terms, [candidate.text])
        summary_hit = include_summary and _matches_any(query_terms, [candidate.summary])
        title_hint_hit = _matches_any(query_terms, [str(candidate.extra.get("title_hint") or "")])
        url_hit = _matches_any(query_terms, [candidate.url])

        if title_hit:
            matched_by = "title"
            match_score = 1.0
        elif text_hit:
            matched_by = "text"
            match_score = 0.9
        elif summary_hit:
            matched_by = "summary"
            match_score = 0.8
        elif title_hint_hit:
            matched_by = "title_hint"
            match_score = 0.65
        elif url_hit:
            matched_by = "url"
            match_score = 0.55

        if matched_by != "none":
            reasons.append(f"matched:{matched_by}")

        penalty = 0.0
        candidate_domain = (domain_from_url(candidate.url) or "").strip().lower()
        if normalized_entry_domain and candidate_domain and candidate_domain != normalized_entry_domain:
            penalty += 0.2
            reasons.append("cross_domain")

        if _is_search_self_link(candidate.url, normalized_search_url):
            penalty += 0.45
            reasons.append("self_search_link")

        if _is_low_signal_candidate(candidate):
            penalty += 0.35
            reasons.append("low_signal_navigation")

        score = max(0.0, round(match_score - penalty, 3))
        fetchability = "direct" if not candidate_domain or candidate_domain == normalized_entry_domain else "cross_domain"
        candidate_quality = _quality_label(score)
        usable = score >= low_confidence_min_score and matched_by != "none"
        scored.append(
            SearchCapabilityScore(
                url=candidate.url,
                strategy=candidate.strategy,
                fetchability=fetchability,
                matched_by=matched_by,
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
