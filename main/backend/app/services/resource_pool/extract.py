"""Extract URLs from documents and persist to resource pool."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import NoReturn, NotRequired, TypedDict, TypeGuard

from functorial_kit import Failure
from sqlalchemy import select
from sqlalchemy.orm import Session

from mrw_functorial_kit.core.provider_port_failures import resource_pool_contract_failures

from ...models.base import SessionLocal
from ...models.entities import Document, EtlJobRun, ResourcePoolUrl, SharedResourcePoolUrl
from ..projects import bind_project, bind_schema
from .url_utils import canonicalize_url, domain_from_url, extract_urls_from_json, extract_urls_from_text, normalize_url

logger = logging.getLogger(__name__)
ResourceSourceRef = dict[str, object]
_RESOURCE_EXTRACT_RECORD_WITNESS = "test:test_resource_extract_classifies_malformed_record_fields"


class DocumentExtractionResult(TypedDict):
    documents_scanned: int
    materials_scanned: int
    urls_extracted: int
    urls_new: int
    urls_duplicate: int
    scope: str


class TaskExtractionResult(TypedDict):
    tasks_scanned: int
    urls_extracted: int
    urls_new: int
    urls_duplicate: int
    scope: str
    dedupe_hit_reason: dict[str, int]
    warning: NotRequired[str]


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _string_object_mapping(value: object) -> ResourceSourceRef:
    if not _is_object_mapping(value):
        return {}
    return {str(key): item for key, item in value.items()}


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _record_value(record: object, name: str) -> object:
    return getattr(record, name, None)


def _record_field_failure(
    record: object,
    name: str,
    *,
    actual: object,
    expected: str,
    message: str,
) -> Failure:
    return resource_pool_contract_failures.fail(
        "record_field_type_invalid",
        message,
        {
            "actual": type(actual).__name__,
            "expected": expected,
            "field": name,
            "operation": "extract_resource_urls",
            "owner": "resource_pool.extract.record_parser",
            "public_exception": "TypeError",
            "public_message": message,
            "record_type": type(record).__name__,
            "witness": _RESOURCE_EXTRACT_RECORD_WITNESS,
        },
    )


def _try_record_int(record: object, name: str) -> int | Failure:
    value = _record_value(record, name)
    if isinstance(value, bool) or not isinstance(value, int):
        message = f"{type(record).__name__}.{name} must be an integer"
        return _record_field_failure(
            record,
            name,
            actual=value,
            expected="integer",
            message=message,
        )
    return value


def _try_record_text(record: object, name: str) -> str | None | Failure:
    value = _record_value(record, name)
    if value is None:
        return None
    if not isinstance(value, str):
        message = f"{type(record).__name__}.{name} must be text or null"
        return _record_field_failure(
            record,
            name,
            actual=value,
            expected="text or null",
            message=message,
        )
    return value


def _raise_record_field_failure(failure: Failure) -> NoReturn:
    context = failure.context or {}
    public_message = str(context.get("public_message") or failure.message)
    cause = TypeError(failure.message)
    # kit:boundary owner=resource_pool.extract.record_parser class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=resource_pool.contract.failure witness=test:test_resource_extract_preserves_type_error_abi_cause_and_no_write
    raise TypeError(public_message) from cause


def _record_int(record: object, name: str) -> int:
    parsed = _try_record_int(record, name)
    if isinstance(parsed, Failure):
        _raise_record_field_failure(parsed)
    return parsed


def _record_text(record: object, name: str) -> str | None:
    parsed = _try_record_text(record, name)
    if isinstance(parsed, Failure):
        _raise_record_field_failure(parsed)
    return parsed


def _set_resource_row_fields(
    row: object,
    *,
    url: str,
    domain: str | None,
    source: str,
    source_ref: ResourceSourceRef,
    project_key: str | None = None,
) -> None:
    setattr(row, "url", url)
    setattr(row, "domain", domain)
    setattr(row, "source", source)
    setattr(row, "source_ref", source_ref)
    if isinstance(row, ResourcePoolUrl):
        setattr(row, "project_key", project_key)


def extract_from_documents(
    *,
    project_key: str,
    scope: str = "project",
    doc_type: list[str] | None = None,
    state: list[str] | None = None,
    document_ids: list[int] | None = None,
    limit: int = 500,
) -> DocumentExtractionResult:
    """
    Extract URLs from Document content/extracted_data/uri and write to resource pool.
    scope: "project" | "shared"
    """
    if scope not in ("project", "shared"):
        scope = "project"

    urls_seen: set[str] = set()
    url_refs: list[tuple[str, ResourceSourceRef]] = []  # (url, source_ref)
    doc_count = 0

    def _collect(doc: Document) -> None:
        document_id = _record_int(doc, "id")
        ref: ResourceSourceRef = {"material_id": document_id, "document_id": document_id}
        uri = _record_text(doc, "uri")
        if uri:
            norm = normalize_url(uri)
            if norm and norm not in urls_seen:
                urls_seen.add(norm)
                url_refs.append((norm, ref))
        content = _record_text(doc, "content")
        if content:
            for u in extract_urls_from_text(content):
                norm = normalize_url(u)
                if norm and norm not in urls_seen:
                    urls_seen.add(norm)
                    url_refs.append((norm, ref))
        extracted_data = _record_value(doc, "extracted_data")
        if extracted_data:
            for u in extract_urls_from_json(extracted_data):
                if u not in urls_seen:
                    urls_seen.add(u)
                    url_refs.append((u, ref))

    with bind_project(project_key):
        with SessionLocal() as session:
            query = select(Document)
            if document_ids:
                query = query.where(Document.id.in_(document_ids))
            else:
                if doc_type:
                    query = query.where(Document.doc_type.in_(doc_type))
                if state:
                    query = query.where(Document.state.in_(state))
            query = query.limit(limit)
            rows = session.execute(query).scalars().all()
            doc_count = len(rows)
            for doc in rows:
                _collect(doc)

    if scope == "shared":
        with bind_schema("public"):
            with SessionLocal() as session:
                new, dup = _append_urls_batch(session, url_refs, "material", "shared", None)
                session.commit()
    else:
        with bind_project(project_key):
            with SessionLocal() as session:
                new, dup = _append_urls_batch(session, url_refs, "material", "project", project_key)
                session.commit()

    return {
        "documents_scanned": doc_count,
        "materials_scanned": doc_count,
        "urls_extracted": len(url_refs),
        "urls_new": new,
        "urls_duplicate": dup,
        "scope": scope,
    }


def append_url(
    url: str,
    source: str,
    source_ref: ResourceSourceRef,
    *,
    scope: str,
    project_key: str,
) -> bool:
    """
    Append a single URL to resource pool. Returns True if appended, False if duplicate/skipped.
    scope: "project" | "shared". For shared, project_key can be empty; for project it is required.
    """
    if scope not in ("project", "shared"):
        scope = "project"
    url_refs: list[tuple[str, ResourceSourceRef]] = [(url, source_ref)]
    if scope == "shared":
        with bind_schema("public"):
            with SessionLocal() as session:
                new, _ = _append_urls_batch(session, url_refs, source, "shared", None)
                session.commit()
                return new > 0
    with bind_project(project_key):
        with SessionLocal() as session:
            new, _ = _append_urls_batch(session, url_refs, source, "project", project_key)
            session.commit()
            return new > 0


def _append_urls_batch(
    session: Session,
    url_refs: list[tuple[str, ResourceSourceRef]],
    source: str,
    scope: str,
    project_key: str | None,
) -> tuple[int, int]:
    """Append URLs with per-url source_ref. Returns (new_count, duplicate_count)."""
    new_count = 0
    dup_count = 0
    for raw, ref in url_refs:
        norm = normalize_url(raw)
        if not norm:
            continue
        domain = domain_from_url(norm) or ""

        if scope == "shared":
            existing = session.execute(
                select(SharedResourcePoolUrl).where(SharedResourcePoolUrl.url == norm)
            ).scalar_one_or_none()
            if existing:
                dup_count += 1
                continue
            row = SharedResourcePoolUrl()
            _set_resource_row_fields(
                row,
                url=norm,
                domain=domain[:255] if domain else None,
                source=source[:32],
                source_ref=ref,
            )
            session.add(row)
            new_count += 1
        else:
            existing = session.execute(
                select(ResourcePoolUrl).where(ResourcePoolUrl.url == norm)
            ).scalar_one_or_none()
            if existing:
                dup_count += 1
                continue
            row = ResourcePoolUrl()
            _set_resource_row_fields(
                row,
                url=norm,
                domain=domain[:255] if domain else None,
                source=source[:32],
                source_ref=ref,
                project_key=project_key,
            )
            session.add(row)
            new_count += 1
    return new_count, dup_count


def extract_from_tasks(
    *,
    project_key: str,
    scope: str = "project",
    task_ids: list[int] | None = None,
    job_type: str | None = None,
    since: datetime | str | None = None,
    limit: int = 100,
) -> TaskExtractionResult:
    """
    Extract URLs from EtlJobRun.params (merged with result) and write to resource pool.
    task_ids: EtlJobRun.id list. job_type: filter by job_type. since: started_at >= since.
    """
    if scope not in ("project", "shared"):
        scope = "project"

    url_refs: list[tuple[str, ResourceSourceRef]] = []
    tasks_scanned = 0
    since_warning: str | None = None
    since_dt, since_warning = _parse_since_filter(since)

    with bind_project(project_key):
        with SessionLocal() as session:
            query = select(EtlJobRun).where(EtlJobRun.status == "completed")
            if task_ids:
                query = query.where(EtlJobRun.id.in_(task_ids))
            if job_type:
                query = query.where(EtlJobRun.job_type == job_type)
            if since_dt:
                query = query.where(EtlJobRun.started_at >= since_dt)
            query = query.order_by(EtlJobRun.started_at.desc()).limit(limit)
            rows = session.execute(query).scalars().all()
            tasks_scanned = len(rows)

            for job in rows:
                params = _string_object_mapping(_record_value(job, "params"))
                ref: ResourceSourceRef = {
                    "task_id": _record_int(job, "id"),
                    "job_type": _record_text(job, "job_type") or "",
                }
                links = params.get("links")
                if _is_object_list(links):
                    for u in links:
                        if isinstance(u, str):
                            url_refs.append((u, ref))
                for u in extract_urls_from_json(params):
                    url_refs.append((u, ref))

    seen: set[str] = set()
    deduped: list[tuple[str, ResourceSourceRef]] = []
    dedupe_hit_reason: dict[str, int] = {}
    for u, ref in url_refs:
        norm, reason = canonicalize_url(u)
        if not norm:
            continue
        dedupe_hit_reason[reason] = int(dedupe_hit_reason.get(reason, 0)) + 1
        if norm not in seen:
            seen.add(norm)
            deduped.append((norm, ref))

    if scope == "shared":
        with bind_schema("public"):
            with SessionLocal() as session:
                new, dup = _append_urls_batch(session, deduped, "task", "shared", None)
                session.commit()
    else:
        with bind_project(project_key):
            with SessionLocal() as session:
                new, dup = _append_urls_batch(session, deduped, "task", "project", project_key)
                session.commit()

    result: TaskExtractionResult = {
        "tasks_scanned": tasks_scanned,
        "urls_extracted": len(deduped),
        "urls_new": new,
        "urls_duplicate": dup,
        "scope": scope,
        "dedupe_hit_reason": dedupe_hit_reason,
    }
    if since_warning:
        result["warning"] = since_warning
    return result


def _parse_since_filter(value: datetime | str | None) -> tuple[datetime | None, str | None]:
    if value is None:
        return None, None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc), None
        return value.replace(tzinfo=timezone.utc), None

    text = str(value).strip()
    if not text:
        return None, "since was empty; ignored filter"

    candidates = [text, text.replace(" ", "T")]
    if text.endswith("Z") or text.endswith("z"):
        candidates.append(text[:-1] + "+00:00")
    if len(text) >= 5 and (text[-5] in ("+", "-")) and text[-3] != ":" and text[-4:].isdigit():
        candidates.append(f"{text[:-5]}{text[-5:-3]}:{text[-2:]}")

    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is not None:
                return parsed.astimezone(timezone.utc), None
            return parsed.replace(tzinfo=timezone.utc), None
        except ValueError:
            continue

    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            parsed = datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
            return parsed, None
        except ValueError:
            continue

    msg = f"invalid since value '{text}'; ignored filter"
    logger.warning("extract_from_tasks: %s", msg)
    return None, msg
