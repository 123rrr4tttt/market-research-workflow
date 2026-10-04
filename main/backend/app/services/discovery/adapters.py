from __future__ import annotations

from typing import Any

from functorial_kit.core.failure import Failure

from app.services.search.candidate_search import discover_candidates
from app.successor_runtime.capabilities.retrieval_candidate_native import (
    CandidateAssemblyContext,
    CandidateNativeSource,
    CandidateSearchBinding,
    DEFAULT_CANDIDATE_NATIVE_SOURCE,
    compile_candidate_native_contribution,
)
from app.successor_runtime.capabilities.retrieval_common import (
    CANDIDATE_BUNDLE_TYPE,
    CANDIDATE_REQUEST_TYPE,
    FlowOperationBinding,
)
from app.successor_runtime.capabilities.retrieval_native_catalog import retrieval_candidate_native

from ..search.candidate_contracts import CandidateBundle, CandidateSearchRequest
from ..search.smart import smart_search
from .deep_search import deep_search
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

    def search(self, **kwargs) -> list[dict[str, Any]]:
        return self.search_candidates(CandidateSearchRequest.from_legacy(**kwargs)).legacy_list()

    def smart_search(self, **kwargs) -> list[dict[str, Any]]:
        return smart_search(**kwargs)

    def deep_search(self, **kwargs) -> dict[str, Any]:
        return deep_search(
            kwargs["topic"],
            kwargs.get("language", "en"),
            kwargs.get("iterations", 2),
            kwargs.get("breadth", 2),
            kwargs.get("max_results", 20),
        )

    def store(
        self,
        results: list[dict[str, Any]],
        *,
        project_key: str | None = None,
        job_type: str | None = None,
    ) -> dict[str, Any]:
        return store_results(
            results,
            project_key=project_key,
            job_type=job_type,
        )
