"""Generic market info collection via search API (default: Google Custom Search)."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import List, TypeAlias, TypeGuard

from sqlalchemy.orm import Session


from ..job_logger import start_job, complete_job, fail_job
from ..collect_runtime.display_meta import build_display_meta
from ..collect_runtime.contracts import (
    CollectRequest,
    CollectResult,
)
from ..projects import current_project_key
from ..search.candidate_contracts import CandidateSearchRequest
from ..search.facets import MARKET_FACET
from ...models.base import SessionLocal
from ...models.entities import Material, Source
from .material_type_mapper import normalize_material_type
from .frontdoor_ingress import build_frontdoor_ingress_envelope
from .postprocess_frontdoor import run_postprocess_frontdoor
from ..resource_pool.http_port import fetch_html
from . import url_pool as url_pool_module
from ..task_readback_metadata import merge_runtime_readback_payload
from .search_and_ingest import (
    SearchAndIngestSpec,
    SearchMaterialWritePayload,
    SearchIngestPorts,
    SearchIngestSource,
    SearchIngestTarget,
    run_search_and_ingest,
)

logger = logging.getLogger(__name__)
BATCH_COMMIT_SIZE = 100
ResultRecord: TypeAlias = dict[str, object]


def _is_object_map(value: object) -> TypeGuard[dict[object, object]]:
    return isinstance(value, dict)


def _json_object(value: object) -> dict[str, object] | None:
    if not _is_object_map(value):
        return None
    return {key: item for key, item in value.items() if isinstance(key, str)}


def _extract_text_from_html(html: str) -> str:
    legacy_extractor = getattr(url_pool_module, "_extract_text_from_html")
    return str(legacy_extractor(html))


def _result_int(value: object) -> int:
    if not value:
        return 0
    if isinstance(value, (int, float, str)):
        return int(value)
    return 0


def _writer_result(frontdoor_result: Mapping[str, object]) -> ResultRecord:
    data = _json_object(frontdoor_result.get("data"))
    if data is None:
        return {}
    writer_result = _json_object(data.get("writer_result"))
    return writer_result or {}


def _get_or_create_source(session: Session, name: str, kind: str, base_url: str) -> Source:
    source = (
        session.query(Source)
        .filter(Source.name == name, Source.kind == kind)
        .first()
    )
    if source:
        return source
    source = Source()
    setattr(source, "name", name)
    setattr(source, "kind", kind)
    setattr(source, "base_url", base_url)
    session.add(source)
    session.flush()
    return source


def collect_market_info(
    keywords: List[str],
    limit: int = 20,
    enable_extraction: bool = True,
    provider: str = "auto",
    start_offset: int | None = None,
    days_back: int | None = None,
    language: str = "en",
    runtime_readback: Mapping[str, object] | None = None,
    project_key: str | None = None,
) -> ResultRecord:
    """
    Collect market-related info via search API.
    Default: auto (Serper -> Google -> Serpstack -> SerpAPI -> DDG).
    """
    job_id = start_job(
        "market_info",
        {
            "keywords": keywords,
            "limit": limit,
            "provider": provider,
            **({"runtime_readback": dict(runtime_readback)} if runtime_readback else {}),
        },
    )

    try:
        normalized_material_type = normalize_material_type("market_info")
        effective_project = (project_key or current_project_key() or "").strip() or None
        request = CandidateSearchRequest(
            topic=" ".join(keywords),
            keywords=tuple(keywords),
            max_results=limit,
            provider=provider,
            exclude_existing=False,
            start_offset=start_offset,
            days_back=days_back,
            language=language,
            project_ref=effective_project,
        )
        spec = SearchAndIngestSpec(
            facet=MARKET_FACET,
            request=request,
            project_key=effective_project,
            target=SearchIngestTarget(
                material_type=normalized_material_type,
                extraction_enabled=bool(enable_extraction),
                extraction_flags={
                    "include_market": True,
                    "include_policy": False,
                    "include_sentiment": False,
                    "include_company": True,
                    "include_product": True,
                    "include_operation": True,
                },
            ),
            source=SearchIngestSource(
                name="Search API Market",
                kind="search",
                base_url="search",
                entrypoint="ingest.market_web",
            ),
            missing_body="route",
            retention="none",
            legacy_projectless=True,
            legacy_payload_shape=True,
        )

        def fetch_body(link: str) -> str | None:
            html, _ = fetch_html(link, timeout=8.0, retries=1)
            return (_extract_text_from_html(html) or "").strip()

        def write_frontdoor(data: SearchMaterialWritePayload) -> ResultRecord:
            ingress_envelope = build_frontdoor_ingress_envelope(
                ingress_type="discovery",
                **data,
            )
            frontdoor_result = run_postprocess_frontdoor(
                ingress_envelope=ingress_envelope,
                run_writer=True,
            )
            return _writer_result(frontdoor_result)

        def route_missing(urls: list[str]) -> ResultRecord:
            from ..collect_runtime.runtime import run_collect

            collect_result = run_collect(
                CollectRequest(
                    channel="url_pool",
                    project_key=effective_project,
                    urls=urls,
                    query_terms=list(keywords or []),
                    options={
                        "dispatch_mode": "inline",
                        "front_door_owner": "ingest.market_web",
                        "frontdoor_route_decision": "front_door_url_routing",
                        "frontdoor_write_mode": "front_door_url_routing",
                        "frontdoor_execution_mode": "url_routing",
                        "enable_extraction": enable_extraction,
                    },
                )
            )
            raw_result = collect_result.meta.get("raw")
            if not isinstance(raw_result, dict):
                return {}
            routed: ResultRecord = {}
            routed.update(raw_result)
            return routed

        with SessionLocal() as session:
            _get_or_create_source(session, "Search API Market", "search", "search")
            collection = run_search_and_ingest(
                spec,
                SearchIngestPorts(
                    exists=lambda link: session.query(Material).filter(Material.uri == link).first() is not None,
                    fetch_text=fetch_body,
                    write=write_frontdoor,
                    route_missing=route_missing,
                ),
            )

        routed_result = collection.routed
        inserted = collection.inserted
        skipped = collection.skipped

        result: ResultRecord = {
            "inserted": inserted,
            "inserted_valid": inserted,
            "skipped": skipped,
            "links": list(collection.links),
            "material_type": normalized_material_type,
            "body_fetch_routed_urls": len(collection.missing_urls),
            "body_fetch_inserted": _result_int(routed_result.get("inserted")),
            "body_fetch_skipped": _result_int(routed_result.get("skipped")),
        }
        if runtime_readback:
            result["runtime_readback"] = merge_runtime_readback_payload(
                dict(runtime_readback),
                runtime_readback,
                status="completed",
                event="completed",
                event_source="ingest_market",
            )
        result["display_meta"] = build_display_meta(
            CollectRequest(
                channel="search.market",
                query_terms=list(keywords or []),
                limit=limit,
                provider=provider,
                language=language,
                source_context={"summary": "市场信息采集"},
            ),
            CollectResult(
                channel="search.market",
                inserted=inserted,
                skipped=skipped,
                updated=0,
                status="completed",
            ),
            summary="市场信息采集",
        )
        complete_job(job_id, result=result)
        return result

    except Exception as exc:
        logger.exception("collect_market_info failed")
        fail_job(job_id, str(exc))
        # kit:boundary owner=ingest.market_web class=SHELL_BOUNDARY_EXCEPTION failure_family=ingest.operation.failure witness=test:test_ingest_service_a_failure_lifts
        raise
