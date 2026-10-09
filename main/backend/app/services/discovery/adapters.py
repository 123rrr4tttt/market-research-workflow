from __future__ import annotations

from app.services.search.candidate_search import discover_candidates
from app.successor_runtime.capabilities.retrieval_candidate_native import (
    DEFAULT_CANDIDATE_NATIVE_SOURCE,
    CandidateAssemblyContext,
    CandidateNativeSource,
    CandidateSearchBinding,
    compile_candidate_native_contribution,
)
from app.successor_runtime.capabilities.retrieval_common import (
    CANDIDATE_BUNDLE_TYPE,
    CANDIDATE_REQUEST_TYPE,
    FlowOperationBinding,
)
from app.successor_runtime.capabilities.retrieval_native_catalog import retrieval_candidate_native
from functorial_kit.core.failure import Failure

from ..search.candidate_contracts import CandidateBundle, CandidateSearchRequest
from ..search.smart import smart_search
from ..search.web import SearchResult
from .deep_search import deep_search
from .ports import DiscoveryDeepResult, DiscoveryStoreResult
from .store import store_results


def candidate_flow_binding(candidate: CandidateSearchBinding) -> FlowOperationBinding:
    """Bridge one assembled candidate binding into a typed flow operation."""

    return FlowOperationBinding(
        operation_id=candidate.definition.source.operation_id,
        version="1",
        input_type=CANDIDATE_REQUEST_TYPE,
        output_type=CANDIDATE_BUNDLE_TYPE,
        effect_refs=("provider.search",),
        failure_refs=("candidate.provider_observation",),
        authority_ref="",
        stop_ref="",
        entrypoint_ref="services.search.candidate_search.discover_candidates",
        invoke=candidate.discover,
    )


class DefaultDiscoveryAdapter:
    def __init__(self, native_source: CandidateNativeSource = DEFAULT_CANDIDATE_NATIVE_SOURCE) -> None:
        native = (
            retrieval_candidate_native
            if native_source == DEFAULT_CANDIDATE_NATIVE_SOURCE
            else compile_candidate_native_contribution(native_source)
        )
        if isinstance(native, Failure):
            raise ValueError(f"invalid candidate native source: {native}")
        binding = native.assemble(CandidateAssemblyContext(discover_candidates))
        if isinstance(binding, Failure):
            raise ValueError(f"invalid candidate native binding: {binding}")
        self._candidate_binding = binding

    def search_candidates(self, request: CandidateSearchRequest) -> CandidateBundle:
        return self._candidate_binding.discover(request)

    def search(
        self,
        *,
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
    ) -> list[SearchResult]:
        request = CandidateSearchRequest(
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
        return [dict(row) for row in self.search_candidates(request).legacy_list()]

    def smart_search(
        self,
        *,
        topic: str,
        days_back: int = 30,
        max_results: int = 10,
        language: str = "en",
        provider: str = "auto",
    ) -> list[SearchResult]:
        return smart_search(topic, days_back, max_results, language, provider)

    def deep_search(
        self,
        *,
        topic: str,
        language: str = "en",
        iterations: int = 2,
        breadth: int = 2,
        max_results: int = 20,
    ) -> DiscoveryDeepResult:
        return deep_search(topic, language, iterations, breadth, max_results)

    def store(
        self,
        results: list[SearchResult],
        *,
        project_key: str | None = None,
        job_type: str | None = None,
    ) -> DiscoveryStoreResult:
        return store_results(
            results,
            project_key=project_key,
            job_type=job_type,
        )
