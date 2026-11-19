from __future__ import annotations

import logging
from typing import SupportsFloat, SupportsIndex

from ..search.candidate_contracts import (
    Candidate,
    CandidateBundle,
    CandidateOccurrence,
    CandidateSearchRequest,
    ProviderObservation,
)
from ..search.candidate_search import discover_candidates
from ..search.vector_contracts import (
    raise_search_contract_legacy,
    search_contract_failure,
)
from ..keyword_generation import generate_keywords
from ..search.web import SearchResult
from .ports import DiscoveryDeepResult

logger = logging.getLogger(__name__)


def _legacy_rows(bundle: CandidateBundle) -> list[SearchResult]:
    return [dict(row) for row in bundle.legacy_list()]


def _text(row: SearchResult, key: str) -> str | None:
    value = row.get(key)
    return value if isinstance(value, str) else None


def _rank(row: SearchResult) -> int | None:
    value = row.get("rank")
    return value if type(value) is int else None


def _score(row: SearchResult) -> float:
    value = row.get("relevance_score")
    if not value:
        return 0.0
    if isinstance(value, (str, bytes, bytearray, SupportsFloat, SupportsIndex)):
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            conversion_error = exc
    else:
        conversion_error = TypeError("relevance_score is not float-convertible")
    exception_type = ValueError if isinstance(conversion_error, ValueError) else TypeError
    raise_search_contract_legacy(
        search_contract_failure(
            "evidence_hit_invalid",
            str(conversion_error),
            operation="deep_search_candidates",
            site="discovery.deep_search.relevance_score",
            public_exception=exception_type,
            field="relevance_score",
            actual_type=type(value).__name__,
        ),
        exception_type=exception_type,
        cause=conversion_error,
    )


def deep_search(
    topic: str,
    language: str = "en",
    iterations: int = 2,
    breadth: int = 2,
    max_results: int = 20,
) -> DiscoveryDeepResult:
    """Iterative search: generate, expand, and return the compatibility projection."""

    bundle = deep_search_candidates(topic, language, iterations, breadth, max_results)
    return {"topic": topic, "language": language, "results": _legacy_rows(bundle)}


def deep_search_candidates(
    topic: str,
    language: str = "en",
    iterations: int = 2,
    breadth: int = 2,
    max_results: int = 20,
) -> CandidateBundle:
    """Run explicit expansion branches and retain typed observations; still candidates only."""
    all_results: list[SearchResult] = []
    observations: list[ProviderObservation] = []
    occurrences: list[CandidateOccurrence] = []
    base_request = CandidateSearchRequest(topic=topic, language=language, max_results=max_results)
    seen_links: set[str] = set()

    keywords = generate_keywords(topic, language)
    for keyword in keywords[:breadth]:
        branch = discover_candidates(
            CandidateSearchRequest(
                topic=keyword,
                keywords=(keyword,),
                language=language,
                max_results=max(1, max_results // breadth),
            )
        )
        observations.extend(branch.observations)
        occurrences.extend(branch.occurrences)
        for row in _legacy_rows(branch):
            link = (_text(row, "link") or "").strip()
            if link and link not in seen_links:
                seen_links.add(link)
                all_results.append(row)

    current_topics = [
        _text(row, "title") or _text(row, "snippet") or topic
        for row in all_results
    ][: max(10, breadth)]
    for _ in range(max(0, iterations - 1)):
        seed = ", ".join(current_topics)[:300]
        expand_query = f"{topic} {seed}"
        branch = discover_candidates(
            CandidateSearchRequest(
                topic=expand_query,
                keywords=(expand_query,),
                language=language,
                max_results=max_results,
            )
        )
        observations.extend(branch.observations)
        occurrences.extend(branch.occurrences)
        added = 0
        for row in _legacy_rows(branch):
            link = (_text(row, "link") or "").strip()
            if link and link not in seen_links:
                seen_links.add(link)
                all_results.append(row)
                added += 1
        logger.info("deep_search: expand added=%d", added)
        if added == 0:
            break

    candidates = tuple(
        Candidate(
            resource_uri=_text(row, "canonical_link") or _text(row, "link") or "",
            title=_text(row, "title"),
            snippet=_text(row, "snippet"),
            source=_text(row, "source"),
            keyword=_text(row, "keyword"),
            original_rank=_rank(row),
            result_rank=index,
            relevance_score=_score(row),
            raw=dict(row),
        )
        for index, row in enumerate(all_results[:max_results], start=1)
    )
    stop_reason = "candidates_observed" if candidates else (
        "no_candidates_observed" if observations else "not_attempted"
    )
    return CandidateBundle(
        base_request,
        candidates,
        tuple(occurrences),
        tuple(observations),
        stop_reason,
    )
