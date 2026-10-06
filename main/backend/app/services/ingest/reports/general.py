from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from typing import Literal, NoReturn, Protocol, TypedDict, TypeGuard

from functorial_kit import Failure
from sqlalchemy.orm import Session

from mrw_functorial_kit.core.provider_port_failures import ingest_operation_failures

from ....models.base import SessionLocal
from ....models.entities import Document, Source
from ...job_logger import complete_job, fail_job, start_job
from ...projects import current_project_key
from ...search.web import SearchResult, search_sources

logger = logging.getLogger(__name__)
ReportFailureCode = Literal[
    "weekly_report_collection_failed",
    "monthly_report_collection_failed",
]
_REPORT_FAILURE_WITNESS = (
    "test:test_FAILURE_PRESERVED__report_failure_lifts_preserve_original_exception"
)


class ReportIngestResult(TypedDict):
    inserted: int
    skipped: int
    doc_type: str
    links: list[str]


class _ResourcePoolAppendPort(Protocol):
    def append_url(
        self,
        url: str,
        source: str,
        source_ref: dict[str, object],
        *,
        project_key: str,
        job_type: str,
    ) -> None:
        ...


class _SourceRow(Protocol):
    id: int
    name: str
    kind: str
    base_url: str | None


class _DocumentRow(Protocol):
    source_id: int | None
    state: str | None
    doc_type: str
    title: str | None
    summary: str | None
    uri: str | None


def _is_source_row(value: object) -> TypeGuard[_SourceRow]:
    return isinstance(value, Source)


def _is_document_row(value: object) -> TypeGuard[_DocumentRow]:
    return isinstance(value, Document)


def _report_failure(
    code: ReportFailureCode,
    message: str,
    *,
    operation: str,
    site: str,
    public_exception: str,
    **details: object,
) -> Failure:
    context: dict[str, object] = {
        "boundary_class": "SHELL_BOUNDARY_EXCEPTION",
        "failure_family": ingest_operation_failures.name,
        "operation": operation,
        "owner": site,
        "public_exception": public_exception,
        "public_message": message,
        "site": site,
        "witness": _REPORT_FAILURE_WITNESS,
    }
    context.update(details)
    return ingest_operation_failures.fail(code, message, context)


def _raise_report_failure(
    failure: Failure,
    cause: Exception | None = None,
) -> NoReturn:
    context = failure.context or {}
    required = {
        "failure_family",
        "operation",
        "owner",
        "public_exception",
        "public_message",
        "site",
        "witness",
    }
    if (
        not ingest_operation_failures.matches(failure)
        or failure.code
        not in {"weekly_report_collection_failed", "monthly_report_collection_failed"}
        or required - set(context)
        or context.get("failure_family") != ingest_operation_failures.name
        or (
            cause is None
            and context.get("public_exception") != "TypeError"
        )
        or (
            cause is not None
            and (
                context.get("public_exception") != cause.__class__.__name__
                or context.get("public_message") != str(cause)
            )
        )
    ):
        # kit:boundary owner=ingest.report.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_FAILURE_PRESERVED__report_failure_lifts_preserve_original_exception
        raise TypeError("report failure lift context is incomplete or inconsistent")
    if cause is None:
        public_message = str(context["public_message"])
        original = TypeError(failure.message)
        # kit:boundary owner=ingest.report.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=ingest.operation.failure witness=test:test_FAILURE_PRESERVED__report_and_commodity_contract_branches_are_observable
        raise TypeError(public_message) from original
    # kit:boundary owner=ingest.report.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=ingest.operation.failure witness=test:test_FAILURE_PRESERVED__report_failure_lifts_preserve_original_exception
    raise cause


def _optional_text(
    item: Mapping[str, object],
    key: str,
    *,
    failure_code: ReportFailureCode,
    operation: str,
) -> str | None:
    value = item.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        message = f"report search result field {key} must be a string"
        _raise_report_failure(
            _report_failure(
                failure_code,
                message,
                operation=operation,
                site="app.services.ingest.reports.general._optional_text",
                public_exception="TypeError",
                field=key,
            ),
        )
    text = value.strip()
    return text or None


def _append_resource_pool_url(
    port: _ResourcePoolAppendPort,
    *,
    url: str,
    doc_type: str,
    project_key: str,
    job_type: str,
) -> None:
    port.append_url(
        url,
        source="ingest",
        source_ref={"doc_type": doc_type},
        project_key=project_key,
        job_type=job_type,
    )


def collect_weekly_market_reports(limit: int = 10) -> ReportIngestResult:
    job_id = start_job("weekly_market_reports", {"limit": limit})
    try:
        keywords = [
            "weekly market report",
            "weekly economic indicators report",
            "industry weekly research report",
        ]
        results: list[SearchResult] = []
        for keyword in keywords:
            results.extend(search_sources(keyword, language="en", max_results=limit))
        result = _store_documents(
            results,
            doc_type="weekly_report",
            limit=limit,
            job_type="weekly_market_reports",
            failure_code="weekly_report_collection_failed",
        )
        complete_job(job_id, result=dict(result))
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("collect_weekly_market_reports failed")
        fail_job(job_id, str(exc))
        _raise_report_failure(
            _report_failure(
                "weekly_report_collection_failed",
                str(exc),
                operation="collect_weekly_market_reports",
                site="app.services.ingest.reports.general.collect_weekly_market_reports",
                public_exception=exc.__class__.__name__,
            ),
            exc,
        )


def collect_monthly_financial_reports(limit: int = 8) -> ReportIngestResult:
    job_id = start_job("monthly_financial_reports", {"limit": limit})
    try:
        keywords = [
            "monthly financial report",
            "monthly market analysis",
            "monthly economic indicators report",
        ]
        results: list[SearchResult] = []
        for keyword in keywords:
            results.extend(search_sources(keyword, language="en", max_results=limit))
        result = _store_documents(
            results,
            doc_type="monthly_report",
            limit=limit,
            job_type="monthly_financial_reports",
            failure_code="monthly_report_collection_failed",
        )
        complete_job(job_id, result=dict(result))
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("collect_monthly_financial_reports failed")
        fail_job(job_id, str(exc))
        _raise_report_failure(
            _report_failure(
                "monthly_report_collection_failed",
                str(exc),
                operation="collect_monthly_financial_reports",
                site="app.services.ingest.reports.general.collect_monthly_financial_reports",
                public_exception=exc.__class__.__name__,
            ),
            exc,
        )


def _store_documents(
    results: Iterable[SearchResult],
    doc_type: str,
    limit: int,
    job_type: str | None = None,
    *,
    failure_code: ReportFailureCode,
) -> ReportIngestResult:
    inserted = 0
    skipped = 0
    stored_links: list[str] = []

    with SessionLocal() as session:
        for item in list(results)[: max(limit, 0)]:
            link = _optional_text(
                item,
                "link",
                failure_code=failure_code,
                operation="store_report_documents",
            ) or ""
            if not link:
                continue
            stored_links.append(link)
            if job_type:
                try:
                    from ...resource_pool import DefaultResourcePoolAppendAdapter

                    append_port: _ResourcePoolAppendPort = DefaultResourcePoolAppendAdapter()
                    pk = (current_project_key() or "").strip()
                    if pk:
                        _append_resource_pool_url(
                            append_port,
                            url=link,
                            doc_type=doc_type,
                            project_key=pk,
                            job_type=job_type,
                        )
                except Exception:  # noqa: BLE001
                    pass
            existed = session.query(Document).filter(Document.uri == link).one_or_none()
            if existed:
                skipped += 1
                continue

            domain = _optional_text(
                item,
                "domain",
                failure_code=failure_code,
                operation="store_report_documents",
            )
            source_name = domain or _optional_text(
                item,
                "source",
                failure_code=failure_code,
                operation="store_report_documents",
            ) or "external"
            source = _ensure_source(
                session,
                source_name,
                domain,
                failure_code=failure_code,
            )

            document_candidate: object = Document()
            if not _is_document_row(document_candidate):
                message = "Document ORM row does not expose the report fields"
                _raise_report_failure(
                    _report_failure(
                        failure_code,
                        message,
                        operation="construct_report_document",
                        site="app.services.ingest.reports.general._store_documents",
                        public_exception="TypeError",
                    ),
                )
            document_candidate.source_id = source.id
            document_candidate.state = None
            document_candidate.doc_type = doc_type
            document_candidate.title = _optional_text(
                item,
                "title",
                failure_code=failure_code,
                operation="store_report_documents",
            )
            document_candidate.summary = _optional_text(
                item,
                "snippet",
                failure_code=failure_code,
                operation="store_report_documents",
            )
            document_candidate.uri = link
            session.add(document_candidate)
            inserted += 1

        session.commit()

    return {"inserted": inserted, "skipped": skipped, "doc_type": doc_type, "links": stored_links}


def _ensure_source(
    session: Session,
    name: str | None,
    base_url: str | None,
    *,
    failure_code: ReportFailureCode,
) -> _SourceRow:
    label = name or "external"
    source_candidate: object = (
        session.query(Source)
        .filter(Source.name == label, Source.kind == "report")
        .one_or_none()
    )
    if source_candidate is not None:
        if not _is_source_row(source_candidate):
            message = "Source ORM query returned an invalid row"
            _raise_report_failure(
                _report_failure(
                    failure_code,
                    message,
                    operation="query_report_source",
                    site="app.services.ingest.reports.general._ensure_source",
                    public_exception="TypeError",
                ),
            )
        return source_candidate

    source_candidate = Source()
    if not _is_source_row(source_candidate):
        message = "Source ORM row does not expose the report fields"
        _raise_report_failure(
            _report_failure(
                failure_code,
                message,
                operation="construct_report_source",
                site="app.services.ingest.reports.general._ensure_source",
                public_exception="TypeError",
            ),
        )
    source_candidate.name = label
    source_candidate.kind = "report"
    source_candidate.base_url = base_url
    session.add(source_candidate)
    session.flush()
    return source_candidate
