from __future__ import annotations

from dataclasses import dataclass

from ..projects import current_project_key
from ..search.web import SearchResult
from .ports import (
    DiscoveryAdapterPort,
    DiscoveryDeepResult,
    DiscoverySearchResult,
    DiscoverySmartResult,
    DiscoveryStoreResult,
)


@dataclass
class DiscoveryApplicationService:
    adapter: DiscoveryAdapterPort

    def _store_with_capture(self, results: list[SearchResult], job_type: str) -> DiscoveryStoreResult:
        project_key = (current_project_key() or "").strip() or None
        return self.adapter.store(
            results,
            project_key=project_key,
            job_type=job_type,
        )

    def run_search(
        self,
        *,
        persist: bool,
        job_type: str = "discovery_search",
        topic: str,
        language: str = "en",
        max_results: int = 10,
        provider: str = "auto",
        days_back: int | None = None,
        exclude_existing: bool = True,
        start_offset: int | None = None,
        keywords: tuple[str, ...] | None = None,
        project_ref: str | None = None,
        source_ref: str | None = None,
        facet_ref: str | None = None,
    ) -> DiscoverySearchResult:
        results = self.adapter.search(
            topic=topic,
            language=language,
            max_results=max_results,
            provider=provider,
            days_back=days_back,
            exclude_existing=exclude_existing,
            start_offset=start_offset,
            keywords=keywords,
            project_ref=project_ref,
            source_ref=source_ref,
            facet_ref=facet_ref,
        )
        body: DiscoverySearchResult = {
            "keywords": [r.get("keyword") for r in results],
            "results": results,
            "provider_used": results[0].get("source", "unknown") if results else "none",
        }
        if persist and results:
            body["stored"] = self._store_with_capture(results, job_type)
        return body

    def run_smart_search(
        self,
        *,
        persist: bool,
        job_type: str = "discovery_smart",
        topic: str,
        language: str = "en",
        max_results: int = 10,
        provider: str = "auto",
        days_back: int = 30,
    ) -> DiscoverySmartResult:
        results = self.adapter.smart_search(
            topic=topic,
            language=language,
            max_results=max_results,
            provider=provider,
            days_back=days_back,
        )
        body: DiscoverySmartResult = {
            "topic": topic,
            "results": results,
            "count": len(results),
            "provider_used": results[0].get("source", "unknown") if results else "none",
        }
        if persist and results:
            body["stored"] = self._store_with_capture(results, job_type)
        return body

    def run_deep_search(
        self,
        *,
        persist: bool,
        job_type: str = "discovery_deep",
        topic: str,
        language: str = "en",
        iterations: int = 2,
        breadth: int = 2,
        max_results: int = 20,
    ) -> DiscoveryDeepResult:
        result = self.adapter.deep_search(
            topic=topic,
            language=language,
            iterations=iterations,
            breadth=breadth,
            max_results=max_results,
        )
        if persist and result["results"]:
            result["stored"] = self._store_with_capture(result["results"], job_type)
        return result
