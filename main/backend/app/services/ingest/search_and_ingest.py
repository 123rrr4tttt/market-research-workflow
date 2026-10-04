"""One search-to-material constructor with explicit effect and delivery policies.

The discovery bundle remains a candidate observation. Only fetched body text
can enter the full-text material builder; retention and writing are separate
caller-owned effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Callable, Literal, Mapping

from ..search.candidate_contracts import Candidate, CandidateBundle, CandidateSearchRequest
from ..search.candidate_search import discover_candidates
from ..search.facets import SearchFacet, instantiate_facet_query
from .material_ingress import MaterialSourceContext, MaterialTargetSpec, build_material_frontdoor_payload
from .material_input import GivenContent, prepare_material


MissingBodyAction = Literal["route", "wait", "fail"]
RetentionAction = Literal["none", "resource_pool"]


@dataclass(frozen=True, slots=True)
class SearchIngestTarget:
    doc_type: str
    extraction_enabled: bool
    extraction_flags: Mapping[str, bool]
    extraction_mode: str = "default"
    chunks: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SearchIngestSource:
    name: str
    kind: str
    base_url: str
    entrypoint: str
    source_mode: str = "protocol_search"


@dataclass(frozen=True, slots=True)
class SearchAndIngestSpec:
    facet: SearchFacet
    request: CandidateSearchRequest
    project_key: str | None
    target: SearchIngestTarget
    source: SearchIngestSource
    missing_body: MissingBodyAction
    retention: RetentionAction = "none"
    legacy_projectless: bool = False
    legacy_payload_shape: bool = False

    def __post_init__(self) -> None:
        if not str(self.project_key or "").strip() and not self.legacy_projectless:
            # kit:boundary owner=ingest.search_and_ingest.public_spec class=SHELL_BOUNDARY_EXCEPTION failure_family=ingest.operation.failure witness=test:test_search_ingest_spec_rejects_incompatible_policy_and_project
            raise ValueError("search-and-ingest requires the original project context")
        if self.request.project_ref and self.project_key and self.request.project_ref != self.project_key:
            # kit:boundary owner=ingest.search_and_ingest.public_spec class=SHELL_BOUNDARY_EXCEPTION failure_family=ingest.operation.failure witness=test:test_search_ingest_spec_rejects_incompatible_policy_and_project
            raise ValueError("request and ingest project contexts conflict")
        if self.request.exclude_existing:
            # kit:boundary owner=ingest.search_and_ingest.public_spec class=SHELL_BOUNDARY_EXCEPTION failure_family=ingest.operation.failure witness=test:test_search_ingest_spec_rejects_incompatible_policy_and_project
            raise ValueError("full-text ingestion requires an unfiltered candidate discovery")
        if self.missing_body not in ("route", "wait", "fail"):
            # kit:boundary owner=ingest.search_and_ingest.public_spec class=SHELL_BOUNDARY_EXCEPTION failure_family=ingest.operation.failure witness=test:test_search_ingest_spec_rejects_incompatible_policy_and_project
            raise ValueError("unsupported missing-body policy")
        if self.retention not in ("none", "resource_pool"):
            # kit:boundary owner=ingest.search_and_ingest.public_spec class=SHELL_BOUNDARY_EXCEPTION failure_family=ingest.operation.failure witness=test:test_search_ingest_spec_rejects_incompatible_policy_and_project
            raise ValueError("unsupported retention policy")


@dataclass(frozen=True, slots=True)
class SearchIngestPorts:
    exists: Callable[[str], bool]
    fetch_text: Callable[[str], str | None]
    write: Callable[[dict[str, Any]], Mapping[str, Any]]
    route_missing: Callable[[list[str]], Mapping[str, Any]] | None = None
    retain: Callable[[Candidate], None] | None = None
    discover: Callable[[CandidateSearchRequest], CandidateBundle] = discover_candidates


@dataclass(frozen=True, slots=True)
class SearchIngestResult:
    bundle: CandidateBundle
    links: tuple[str, ...]
    inserted: int
    skipped: int
    missing_urls: tuple[str, ...]
    routed: Mapping[str, Any]


def build_search_material_payload(
    candidate: Candidate,
    body_text: str,
    *,
    target: SearchIngestTarget,
    source: SearchIngestSource,
    provider: str,
    legacy_payload_shape: bool = False,
    resource_uri: str | None = None,
) -> Annotated[
    dict[str, dict[str, Any]],
    "kit:non-authoritative derived_as=view fact_source=candidate+acquired_body+target+source witness=test:test_third_facet_uses_same_search_material_constructor_and_keeps_occurrences",
]:
    """Use the R3 material projection after a real acquisition supplied body text."""
    uri = resource_uri or candidate.resource_uri
    prepared = prepare_material(GivenContent.from_text(body_text, source_locator=uri))
    payload = build_material_frontdoor_payload(
        prepared,
        target=MaterialTargetSpec(
            doc_type=target.doc_type,
            title=candidate.title or "",
            summary=candidate.snippet or "",
            publish_date=None,
            state=None,
            extraction_enabled=target.extraction_enabled,
            extraction_mode=target.extraction_mode,
            chunks=target.chunks,
            extraction_flags=target.extraction_flags,
        ),
        source=MaterialSourceContext(
            source_name=source.name,
            source_kind=source.kind,
            uri=uri,
            platform=candidate.source or provider or "search",
            entrypoint=source.entrypoint,
            source_mode=source.source_mode,
        ),
        extracted_data_base={"platform": candidate.source or provider, "keyword": candidate.keyword},
    )
    payload["document_candidate"]["source_base_url"] = source.base_url
    if legacy_payload_shape:
        payload["document_candidate"]["text_hash"] = None
        payload["extraction_plan"].pop("mode", None)
        payload["extraction_plan"].pop("chunks", None)
    return payload


def run_search_and_ingest(spec: SearchAndIngestSpec, ports: SearchIngestPorts) -> SearchIngestResult:
    """Run the fixed ordered shell against caller-owned effects and original writer."""
    request = instantiate_facet_query(spec.facet, spec.request)
    bundle = ports.discover(request)
    if bundle.request != request:
        # kit:boundary owner=ingest.search_and_ingest.effect_binding class=PROGRAMMER_DEFECT failure_family=none witness=test:test_search_ingest_ports_reject_invalid_bindings_and_body_failure
        raise ValueError("discovery returned a bundle for another request")
    if spec.retention == "resource_pool" and ports.retain is None:
        # kit:boundary owner=ingest.search_and_ingest.effect_binding class=PROGRAMMER_DEFECT failure_family=none witness=test:test_search_ingest_ports_reject_invalid_bindings_and_body_failure
        raise ValueError("resource retention effect is required")
    if spec.missing_body == "route" and ports.route_missing is None:
        # kit:boundary owner=ingest.search_and_ingest.effect_binding class=PROGRAMMER_DEFECT failure_family=none witness=test:test_search_ingest_ports_reject_invalid_bindings_and_body_failure
        raise ValueError("missing-body route effect is required")

    links: list[str] = []
    missing: list[str] = []
    inserted = 0
    skipped = 0
    for candidate in bundle.candidates:
        link = str((candidate.raw.get("link") if spec.legacy_payload_shape else None) or candidate.resource_uri).strip()
        if not link:
            continue
        links.append(link)
        if spec.retention == "resource_pool":
            assert ports.retain is not None
            ports.retain(candidate)
        if ports.exists(link):
            skipped += 1
            continue
        try:
            body = (ports.fetch_text(link) or "").strip()
        except Exception:
            body = ""
        if not body:
            missing.append(link)
            if spec.missing_body == "fail":
                # kit:boundary owner=ingest.search_and_ingest.acquisition_shell class=SHELL_BOUNDARY_EXCEPTION failure_family=ingest.operation.failure witness=test:test_search_ingest_ports_reject_invalid_bindings_and_body_failure
                raise ValueError(f"body acquisition failed for {link}")
            continue
        payload = build_search_material_payload(
            candidate,
            body,
            target=spec.target,
            source=spec.source,
            provider=request.provider,
            legacy_payload_shape=spec.legacy_payload_shape,
            resource_uri=link,
        )
        outcome = ports.write({
            "project_key": spec.project_key,
            "source_ref": {"url": link, "locator": link},
            "collection_payload": payload,
            "raw_snapshot": {"item": dict(candidate.raw), "link": link},
            "entrypoint": spec.source.entrypoint,
            "source_mode": spec.source.source_mode,
        })
        inserted += int(outcome.get("inserted") or 0)
        skipped += int(outcome.get("skipped") or 0)
    routed: Mapping[str, Any] = {}
    if missing and spec.missing_body == "route":
        assert ports.route_missing is not None
        routed = ports.route_missing(missing)
        inserted += int(routed.get("inserted") or 0)
        skipped += int(routed.get("skipped") or 0)
    return SearchIngestResult(bundle, tuple(links), inserted, skipped, tuple(missing), routed)


__all__ = [
    "SearchAndIngestSpec", "SearchIngestPorts", "SearchIngestResult", "SearchIngestSource",
    "SearchIngestTarget", "build_search_material_payload", "run_search_and_ingest",
]
