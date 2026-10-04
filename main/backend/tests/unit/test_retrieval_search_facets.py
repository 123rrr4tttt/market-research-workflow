"""R4 core witnesses; policy wrapper scenarios are added after interface handoff."""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.services.ingest.search_and_ingest import (
    SearchAndIngestSpec,
    SearchIngestPorts,
    SearchIngestSource,
    SearchIngestTarget,
    run_search_and_ingest,
)
from app.services.search.candidate_contracts import (
    Candidate,
    CandidateBundle,
    CandidateOccurrence,
    CandidateSearchRequest,
)
from app.services.search.facets import MARKET_FACET, POLICY_FACET, SearchFacet, instantiate_facet_query


def _request(*, facet_ref: str | None = None) -> CandidateSearchRequest:
    return CandidateSearchRequest(
        topic="chip supply",
        keywords=("chip supply",),
        max_results=2,
        provider="google",
        exclude_existing=False,
        project_ref="project-a",
        facet_ref=facet_ref,
    )


def _spec(*, facet: SearchFacet = MARKET_FACET, missing_body: str = "route") -> SearchAndIngestSpec:
    return SearchAndIngestSpec(
        facet=facet,
        request=_request(),
        project_key="project-a",
        target=SearchIngestTarget("market_info", False, {"include_market": True}),
        source=SearchIngestSource("Search API Market", "search", "search", "ingest.market_web"),
        missing_body=missing_body,
    )


def _bundle(request: CandidateSearchRequest) -> CandidateBundle:
    url = "https://example.org/report"
    return CandidateBundle(
        request=request,
        candidates=(Candidate(url, "Report", "Summary", "google", "chip supply", 1, 1, 0.9, {"link": url}),),
        occurrences=(
            CandidateOccurrence(url, "chip supply", "google", "google", 1, True, request.facet_ref),
            CandidateOccurrence(url, "chip supply", "google", "google", 2, False, request.facet_ref),
        ),
        observations=(),
        stop_reason="candidates_observed",
    )


def test_facet_constructor_rejects_invalid_declarations() -> None:
    with pytest.raises(ValueError, match="identity"):
        SearchFacet("", "v1", ("technology",))
    with pytest.raises(ValueError, match="object references"):
        SearchFacet("technical", "v1", ())
    with pytest.raises(ValueError, match="query expression"):
        SearchFacet("technical", "v1", ("technology",), query_expression=" ")
    with pytest.raises(ValueError, match="max_results"):
        SearchFacet("technical", "v1", ("technology",), max_results=0)


def test_facet_rejects_conflicting_source_provider_query_and_version() -> None:
    facet = SearchFacet(
        "technical", "v2", ("chip_architecture",),
        source_scope=("standards",), query_expression="chip supply",
        providers=("google",), max_results=2,
    )
    with pytest.raises(ValueError, match="source"):
        instantiate_facet_query(facet, _request())
    with pytest.raises(ValueError, match="facet"):
        instantiate_facet_query(MARKET_FACET, _request(facet_ref="market@v0"))
    request = CandidateSearchRequest(
        "chip supply", keywords=("chip supply",), max_results=2,
        provider="google", source_ref="standards", exclude_existing=False,
    )
    assert instantiate_facet_query(facet, request).facet_ref == "technical@v2"
    with pytest.raises(ValueError, match="provider"):
        instantiate_facet_query(facet, CandidateSearchRequest("chip supply", provider="ddg", source_ref="standards"))
    with pytest.raises(ValueError, match="query"):
        instantiate_facet_query(facet, CandidateSearchRequest("different query", source_ref="standards"))
    with pytest.raises(ValueError, match="keywords"):
        instantiate_facet_query(
            SearchFacet("technical", "v2", ("technology",), keywords=("fixed term",)),
            request,
        )
    with pytest.raises(ValueError, match="language"):
        instantiate_facet_query(
            SearchFacet("technical", "v2", ("technology",), language="zh"),
            request,
        )
    with pytest.raises(ValueError, match="limit"):
        instantiate_facet_query(
            SearchFacet("technical", "v2", ("technology",), max_results=1),
            request,
        )


def test_third_facet_uses_same_search_material_constructor_and_keeps_occurrences() -> None:
    facet = SearchFacet("technical", "v1", ("technology",))
    writes: list[dict] = []
    result = run_search_and_ingest(
        _spec(facet=facet),
        SearchIngestPorts(
            discover=_bundle,
            exists=lambda _: False,
            fetch_text=lambda _: "Actual acquired body",
            write=lambda payload: writes.append(payload) or {"inserted": 1},
            route_missing=lambda _: {},
        ),
    )
    assert result.inserted == 1
    assert [item.facet_ref for item in result.bundle.occurrences] == ["technical@v1"] * 2
    assert writes[0]["project_key"] == "project-a"
    assert writes[0]["collection_payload"]["document_candidate"]["content"] == "Actual acquired body"
    assert writes[0]["collection_payload"]["extraction_plan"]["include_market"] is True


def test_missing_body_routes_without_writing_snippet() -> None:
    writes: list[dict] = []
    routed: list[list[str]] = []
    result = run_search_and_ingest(
        _spec(),
        SearchIngestPorts(
            discover=_bundle,
            exists=lambda _: False,
            fetch_text=lambda _: "",
            write=lambda payload: writes.append(payload) or {"inserted": 1},
            route_missing=lambda urls: routed.append(urls) or {"skipped": 1},
        ),
    )
    assert writes == []
    assert routed == [["https://example.org/report"]]
    assert result.skipped == 1


def test_new_search_ingest_requires_project_and_separate_retention_effect() -> None:
    with pytest.raises(ValueError, match="project context"):
        SearchAndIngestSpec(
            facet=MARKET_FACET,
            request=_request(),
            project_key=None,
            target=SearchIngestTarget("market_info", False, {}),
            source=SearchIngestSource("Search", "search", "search", "entry"),
            missing_body="wait",
        )
    spec = SearchAndIngestSpec(
        facet=MARKET_FACET,
        request=_request(),
        project_key="project-a",
        target=SearchIngestTarget("market_info", False, {}),
        source=SearchIngestSource("Search", "search", "search", "entry"),
        missing_body="wait",
        retention="resource_pool",
    )
    with pytest.raises(ValueError, match="retention effect"):
        run_search_and_ingest(
            spec,
            SearchIngestPorts(discover=_bundle, exists=lambda _: False, fetch_text=lambda _: None, write=lambda _: {}),
        )


def test_search_ingest_spec_rejects_incompatible_policy_and_project() -> None:
    with pytest.raises(ValueError, match="project context"):
        replace(_spec(), project_key=None)
    with pytest.raises(ValueError, match="project contexts conflict"):
        replace(_spec(), project_key="project-b")
    with pytest.raises(ValueError, match="unfiltered candidate discovery"):
        replace(_spec(), request=replace(_request(), exclude_existing=True))
    with pytest.raises(ValueError, match="missing-body policy"):
        replace(_spec(), missing_body="accept_snippet")
    with pytest.raises(ValueError, match="retention policy"):
        replace(_spec(), retention="implicit")


def test_search_ingest_ports_reject_invalid_bindings_and_body_failure() -> None:
    base = SearchIngestPorts(
        discover=_bundle,
        exists=lambda _: False,
        fetch_text=lambda _: None,
        write=lambda _: {},
    )
    with pytest.raises(ValueError, match="another request"):
        run_search_and_ingest(_spec(missing_body="wait"), replace(base, discover=lambda _: _bundle(_request())))
    with pytest.raises(ValueError, match="retention effect"):
        run_search_and_ingest(replace(_spec(missing_body="wait"), retention="resource_pool"), base)
    with pytest.raises(ValueError, match="route effect"):
        run_search_and_ingest(_spec(), base)
    with pytest.raises(ValueError, match="body acquisition failed"):
        run_search_and_ingest(_spec(missing_body="fail"), base)


def test_policy_facet_is_data_and_uses_policy_delivery_with_explicit_retention() -> None:
    request = CandidateSearchRequest(
        topic="privacy regulation",
        keywords=("privacy regulation",),
        max_results=1,
        provider="google",
        exclude_existing=False,
        project_ref="project-policy",
        source_ref="policy",
    )
    spec = SearchAndIngestSpec(
        facet=POLICY_FACET,
        request=request,
        project_key="project-policy",
        target=SearchIngestTarget(
            "policy_regulation",
            True,
            {"include_market": False, "include_policy": True},
        ),
        source=SearchIngestSource("Search API Policy", "search", "search", "ingest.policy_regulation"),
        missing_body="route",
        retention="resource_pool",
    )
    retained: list[str] = []
    writes: list[dict] = []

    result = run_search_and_ingest(
        spec,
        SearchIngestPorts(
            discover=_bundle,
            exists=lambda _: False,
            fetch_text=lambda _: "Fetched regulation text",
            write=lambda payload: writes.append(payload) or {"inserted": 1},
            route_missing=lambda _: {},
            retain=lambda candidate: retained.append(candidate.resource_uri),
        ),
    )

    assert result.bundle.request.facet_ref == "policy@v1"
    assert retained == ["https://example.org/report"]
    assert writes[0]["collection_payload"]["document_candidate"]["content"] == "Fetched regulation text"
    assert writes[0]["collection_payload"]["document_candidate"]["doc_type"] == "policy_regulation"
    assert writes[0]["collection_payload"]["extraction_plan"]["include_policy"] is True
