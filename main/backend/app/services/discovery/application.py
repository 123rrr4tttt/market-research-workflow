from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..projects import current_project_key
from .adapters import DefaultDiscoveryAdapter


@dataclass
class DiscoveryApplicationService:
    adapter: DefaultDiscoveryAdapter

    @classmethod
    def build_default(cls) -> "DiscoveryApplicationService":
        return cls(adapter=DefaultDiscoveryAdapter())

    def _store_with_capture(self, results: list, job_type: str) -> dict[str, int]:
        project_key = (current_project_key() or "").strip() or None
        return self.adapter.store(
            results,
            project_key=project_key,
            job_type=job_type,
        )

    def run_search(self, *, persist: bool, job_type: str = "discovery_search", **kwargs) -> dict[str, Any]:
        results = self.adapter.search(**kwargs)
        body: dict[str, Any] = {
            "keywords": [r.get("keyword") for r in results],
            "results": results,
            "provider_used": results[0].get("source", "unknown") if results else "none",
        }
        if persist and results:
            body["stored"] = self._store_with_capture(results, job_type)
        return body

    def run_smart_search(self, *, persist: bool, job_type: str = "discovery_smart", **kwargs) -> dict[str, Any]:
        results = self.adapter.smart_search(**kwargs)
        body: dict[str, Any] = {
            "topic": kwargs["topic"],
            "results": results,
            "count": len(results),
            "provider_used": results[0].get("source", "unknown") if results else "none",
        }
        if persist and results:
            body["stored"] = self._store_with_capture(results, job_type)
        return body

    def run_deep_search(self, *, persist: bool, job_type: str = "discovery_deep", **kwargs) -> dict[str, Any]:
        result = self.adapter.deep_search(**kwargs)
        if persist and result.get("results"):
            result["stored"] = self._store_with_capture(result["results"], job_type)
        return result
