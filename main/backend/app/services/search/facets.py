"""Open search facets and explicit compatibility with a typed discovery request."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .candidate_contracts import CandidateSearchRequest


@dataclass(frozen=True, slots=True)
class SearchFacet:
    facet_id: str
    version: str
    object_refs: tuple[str, ...]
    source_scope: tuple[str, ...] = ()
    query_expression: str | None = None
    keywords: tuple[str, ...] | None = None
    language: str | None = None
    providers: tuple[str, ...] = ()
    max_results: int | None = None

    def __post_init__(self) -> None:
        if not self.facet_id.strip() or not self.version.strip():
            # kit:boundary owner=search.facets.public_input class=SHELL_BOUNDARY_EXCEPTION failure_family=search.failure witness=test:test_facet_constructor_rejects_invalid_declarations
            raise ValueError("facet identity and version are required")
        if not self.object_refs or any(not ref.strip() for ref in self.object_refs):
            # kit:boundary owner=search.facets.public_input class=SHELL_BOUNDARY_EXCEPTION failure_family=search.failure witness=test:test_facet_constructor_rejects_invalid_declarations
            raise ValueError("facet object references are required")
        if self.query_expression is not None and not self.query_expression.strip():
            # kit:boundary owner=search.facets.public_input class=SHELL_BOUNDARY_EXCEPTION failure_family=search.failure witness=test:test_facet_constructor_rejects_invalid_declarations
            raise ValueError("facet query expression must be nonempty")
        if self.max_results is not None and self.max_results < 1:
            # kit:boundary owner=search.facets.public_input class=SHELL_BOUNDARY_EXCEPTION failure_family=search.failure witness=test:test_facet_constructor_rejects_invalid_declarations
            raise ValueError("facet max_results must be positive")

    @property
    def ref(self) -> str:
        return f"{self.facet_id}@{self.version}"


def instantiate_facet_query(facet: SearchFacet, request: CandidateSearchRequest) -> CandidateSearchRequest:
    """Bind a compatible request; never infer target delivery from facet identity."""
    if request.facet_ref is not None and request.facet_ref != facet.ref:
        # kit:boundary owner=search.facets.request_binding class=SHELL_BOUNDARY_EXCEPTION failure_family=search.failure witness=test:test_facet_rejects_conflicting_source_provider_query_and_version
        raise ValueError("request facet reference conflicts with the facet")
    if facet.source_scope and request.source_ref not in facet.source_scope:
        # kit:boundary owner=search.facets.request_binding class=SHELL_BOUNDARY_EXCEPTION failure_family=search.failure witness=test:test_facet_rejects_conflicting_source_provider_query_and_version
        raise ValueError("request source is outside the facet scope")
    if facet.query_expression is not None and request.topic != facet.query_expression:
        # kit:boundary owner=search.facets.request_binding class=SHELL_BOUNDARY_EXCEPTION failure_family=search.failure witness=test:test_facet_rejects_conflicting_source_provider_query_and_version
        raise ValueError("request query conflicts with the facet")
    if facet.keywords is not None and request.keywords != facet.keywords:
        # kit:boundary owner=search.facets.request_binding class=SHELL_BOUNDARY_EXCEPTION failure_family=search.failure witness=test:test_facet_rejects_conflicting_source_provider_query_and_version
        raise ValueError("request keywords conflict with the facet")
    if facet.language is not None and request.language != facet.language:
        # kit:boundary owner=search.facets.request_binding class=SHELL_BOUNDARY_EXCEPTION failure_family=search.failure witness=test:test_facet_rejects_conflicting_source_provider_query_and_version
        raise ValueError("request language conflicts with the facet")
    if facet.providers and request.provider not in facet.providers:
        # kit:boundary owner=search.facets.request_binding class=SHELL_BOUNDARY_EXCEPTION failure_family=search.failure witness=test:test_facet_rejects_conflicting_source_provider_query_and_version
        raise ValueError("request provider is outside the facet scope")
    if facet.max_results is not None and request.max_results > facet.max_results:
        # kit:boundary owner=search.facets.request_binding class=SHELL_BOUNDARY_EXCEPTION failure_family=search.failure witness=test:test_facet_rejects_conflicting_source_provider_query_and_version
        raise ValueError("request limit exceeds the facet constraint")
    return replace(request, facet_ref=facet.ref)


MARKET_FACET = SearchFacet("market", "v1", ("market_information",))
POLICY_FACET = SearchFacet("policy", "v1", ("policy_regulation",))


__all__ = ["SearchFacet", "instantiate_facet_query", "MARKET_FACET", "POLICY_FACET"]
