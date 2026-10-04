from __future__ import annotations

from typing import List, Dict
import logging

from ..search.candidate_contracts import CandidateBundle, CandidateSearchRequest
from ..search.candidate_search import discover_candidates
from ..search.web import generate_keywords
from ...settings.config import settings


logger = logging.getLogger(__name__)


def deep_search(topic: str, language: str = "en", iterations: int = 2, breadth: int = 2, max_results: int = 20) -> Dict:
    """Iterative search: generate → search → summarize keywords → expand → search.
    Inspired by multi-agent deep research pipelines in BettaFish (deep-search)."""

    bundle = deep_search_candidates(topic, language, iterations, breadth, max_results)
    return {"topic": topic, "language": language, "results": bundle.legacy_list()}


def deep_search_candidates(topic: str, language: str = "en", iterations: int = 2, breadth: int = 2, max_results: int = 20) -> CandidateBundle:
    """Run explicit expansion branches and retain typed observations; still candidates only."""
    all_results: List[Dict] = []
    observations = []
    occurrences = []
    base_request = CandidateSearchRequest(topic=topic, language=language, max_results=max_results)
    seen_links = set()

    # First round
    keywords = generate_keywords(topic, language)
    for kw in keywords[:breadth]:
        branch = discover_candidates(CandidateSearchRequest(topic=kw, keywords=(kw,), language=language, max_results=max(1, max_results // breadth)))
        res = branch.legacy_list()
        observations.extend(branch.observations)
        occurrences.extend(branch.occurrences)
        for r in res:
            link = (r.get("link") or "").strip()
            if link and link not in seen_links:
                seen_links.add(link)
                all_results.append(r)

    # Expansion rounds（简单合并词汇）
    current_topics = [r.get("title") or r.get("snippet") or topic for r in all_results][:max(10, breadth)]
    for _ in range(max(0, iterations - 1)):
        seed = ", ".join([t for t in current_topics if t])[:300]
        expand_query = f"{topic} {seed}"
        branch = discover_candidates(CandidateSearchRequest(topic=expand_query, keywords=(expand_query,), language=language, max_results=max_results))
        res = branch.legacy_list()
        observations.extend(branch.observations)
        occurrences.extend(branch.occurrences)
        add = 0
        for r in res:
            link = (r.get("link") or "").strip()
            if link and link not in seen_links:
                seen_links.add(link)
                all_results.append(r)
                add += 1
        logger.info("deep_search: expand added=%d", add)
        if add == 0:
            break

    from ..search.candidate_contracts import Candidate
    candidates = tuple(
        Candidate(
            resource_uri=str(row.get("canonical_link") or row.get("link") or ""), title=row.get("title"),
            snippet=row.get("snippet"), source=row.get("source"), keyword=row.get("keyword"),
            original_rank=row.get("rank"), result_rank=index, relevance_score=float(row.get("relevance_score") or 0), raw=dict(row),
        ) for index, row in enumerate(all_results[:max_results], start=1)
    )
    stop = "candidates_observed" if candidates else ("no_candidates_observed" if observations else "not_attempted")
    return CandidateBundle(base_request, candidates, tuple(occurrences), tuple(observations), stop)
