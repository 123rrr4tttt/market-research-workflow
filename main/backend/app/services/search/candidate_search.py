"""Single-call candidate discovery using the existing provider search kernel."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .candidate_contracts import (
    Candidate,
    CandidateBundle,
    CandidateOccurrence,
    CandidateSearchRequest,
    ProviderObservation,
)
from .web import search_sources


def discover_candidates(request: CandidateSearchRequest) -> CandidateBundle:
    """Perform one search; matrix strategy and ingest belong to their own owners."""
    request_failure = request.validation_failure()
    if request_failure is not None:
        return CandidateBundle(
            request=request,
            candidates=(),
            occurrences=(),
            observations=(),
            stop_reason="not_attempted",
            request_failure=request_failure,
        )
    raw_observations: list[dict[str, Any]] = []
    raw_occurrences: list[dict[str, Any]] = []
    rows = search_sources(
        request.topic,
        language=request.language,
        max_results=request.max_results,
        provider=request.provider,
        days_back=request.days_back,
        exclude_existing=request.exclude_existing,
        start_offset=request.start_offset,
        keywords_override=list(request.keywords) if request.keywords is not None else None,
        observation_sink=raw_observations,
        occurrence_sink=raw_occurrences,
    )
    observations = tuple(ProviderObservation(**item) for item in raw_observations)
    occurrences = tuple(CandidateOccurrence(**item, facet_ref=request.facet_ref) for item in raw_occurrences)
    next_rank: dict[tuple[str, str | None], int] = defaultdict(int)
    rank_by_uri: dict[str, int] = {}
    for occurrence in occurrences:
        key = (occurrence.provider, occurrence.keyword)
        next_rank[key] += 1
        if occurrence.retained:
            rank_by_uri.setdefault(occurrence.resource_uri, occurrence.original_rank or next_rank[key])
    candidates = tuple(
        Candidate(
            resource_uri=str(row.get("canonical_link") or row.get("link") or ""),
            title=row.get("title"),
            snippet=row.get("snippet"),
            source=row.get("source"),
            keyword=row.get("keyword"),
            original_rank=row.get("rank") or rank_by_uri.get(str(row.get("canonical_link") or row.get("link") or "")),
            result_rank=index,
            relevance_score=float(row.get("relevance_score") or 0.0),
            raw=dict(row),
        )
        for index, row in enumerate(rows, start=1)
    )
    if not observations:
        stop_reason = "not_attempted"
    elif len(candidates) >= request.max_results:
        stop_reason = "limit_reached"
    elif candidates:
        stop_reason = "candidates_observed"
    else:
        stop_reason = "no_candidates_observed"
    return CandidateBundle(
        request=request,
        candidates=candidates,
        occurrences=occurrences,
        observations=observations,
        stop_reason=stop_reason,
    )
