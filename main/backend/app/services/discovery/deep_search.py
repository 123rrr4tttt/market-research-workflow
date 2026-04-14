from __future__ import annotations

from typing import List, Dict
import logging

from ..search.web import search_sources, generate_keywords
from ...settings.config import settings


logger = logging.getLogger(__name__)


def deep_search(topic: str, language: str = "en", iterations: int = 2, breadth: int = 2, max_results: int = 20) -> Dict:
    """Iterative search: generate → search → summarize keywords → expand → search.
    Inspired by multi-agent deep research pipelines in BettaFish (deep-search)."""

    all_results: List[Dict] = []
    seen_links = set()

    # First round
    keywords = generate_keywords(topic, language)
    for kw in keywords[:breadth]:
        res = search_sources(kw, language, max_results=max(1, max_results // breadth))
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
        res = search_sources(expand_query, language, max_results=max_results)
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

    return {"topic": topic, "language": language, "results": all_results[:max_results]}


