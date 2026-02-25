from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .adapters import DefaultDiscoveryAdapter


@dataclass
class DiscoveryApplicationService:
    adapter: DefaultDiscoveryAdapter

    @classmethod
    def build_default(cls) -> "DiscoveryApplicationService":
        return cls(adapter=DefaultDiscoveryAdapter())

    def run_search(self, *, persist: bool, **kwargs) -> dict[str, Any]:
        results = self.adapter.search(**kwargs)
        body: dict[str, Any] = {
            "keywords": [r.get("keyword") for r in results],
            "results": results,
            "provider_used": results[0].get("source", "unknown") if results else "none",
        }
        if persist and results:
            body["stored"] = self.adapter.store(results)
        return body

    def run_smart_search(self, *, persist: bool, **kwargs) -> dict[str, Any]:
        results = self.adapter.smart_search(**kwargs)
        body: dict[str, Any] = {
            "topic": kwargs["topic"],
            "results": results,
            "count": len(results),
            "provider_used": results[0].get("source", "unknown") if results else "none",
        }
        if persist and results:
            body["stored"] = self.adapter.store(results)
        return body

    def run_deep_search(self, *, persist: bool, **kwargs) -> dict[str, Any]:
        result = self.adapter.deep_search(**kwargs)
        if persist and result.get("results"):
            result["stored"] = self.adapter.store(result["results"])
        return result
