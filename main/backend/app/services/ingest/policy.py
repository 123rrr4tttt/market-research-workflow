from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from typing import Any, NoReturn, Iterable, Protocol, runtime_checkable, TypeGuard

from sqlalchemy.orm import Session

from app.successor_runtime.capabilities import acquisition_batch as acquisition
from app.successor_runtime.capabilities.checksum import content_digest
from functorial_kit import Failure
from mrw_functorial_kit.core.provider_port_failures import ingest_policy_failures

from ...models.base import SessionLocal
from ...models.entities import Document, Source
from ..collect_runtime.contracts import (
    COLLECT_BATCH_FOLD_SCHEMA_REF,
    CollectBatchCounts,
    CollectBatchFold,
    CollectBatchRow,
    CollectFailure,
    collect_failure_to_plain,
    fold_collect_batch_rows,
)
from ..job_logger import start_job, complete_job, fail_job
from .frontdoor_ingress import build_frontdoor_ingress_envelope
from .postprocess_frontdoor import run_postprocess_frontdoor
from .provider_ports import PolicyDocument, get_policy_adapter

POLICY_MATERIALIZATION_PROJECTION_SCHEMA_REF = (
    "mrw.successor.ingest.policy.materialization-projection.v2"
)


def _is_string_key(value: object) -> bool:
    return isinstance(value, str)


@runtime_checkable
class _StringKeyInspectable(Protocol):
    def keys(self) -> Iterable[object]: ...


def _has_only_string_keys(value: object) -> bool:
    if not isinstance(value, _StringKeyInspectable):
        return False
    return all(map(_is_string_key, value.keys()))


def _is_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not _has_only_string_keys(value):
        return False
    return isinstance(value, dict)


def _object_dict(value: object) -> dict[str, object]:
    return dict(value) if _is_object_dict(value) else {}


def _safe_int(value: object) -> int:
    try:
        return int(value) if isinstance(value, (str, bytes, int, float)) else 0
    except (TypeError, ValueError):
        return 0


def _isoformat(value: object) -> str | None:
    formatter = getattr(value, "isoformat", None)
    return str(formatter()) if callable(formatter) else None


def _get_or_create_source(session: Session, doc: PolicyDocument) -> Source:
    name = doc.source_name or "Unknown Source"
    source = (
        session.query(Source)
        .filter(Source.name == name, Source.kind == "state_site")
        .one_or_none()
    )
    if source:
        return source

    source = Source()
    setattr(source, "name", name)
    setattr(source, "kind", "state_site")
    setattr(source, "base_url", doc.uri)
    session.add(source)
    session.flush()
    return source


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _policy_request_ref(
    state: str,
    *,
    request_id: str | None = None,
    idempotency_key: str | None = None,
) -> acquisition.CollectRequestRef:
    state_key = str(state).strip().upper()
    identity = str(request_id or idempotency_key or "").strip()
    if not identity:
        identity = content_digest({"state": state_key, "channel": "search.policy"})
    return acquisition.build_collect_request_ref(
        request_id=f"policy-materialize:{state_key}:{identity}",
        project_key=f"policy:{state_key}",
        channel="search.policy",
    )


def _policy_document_row(
    *,
    document: PolicyDocument,
    state: str,
    input_index: int,
) -> CollectBatchRow:
    raw = {
        "state": str(getattr(document, "state", None) or state),
        "title": str(getattr(document, "title", None) or ""),
        "status": getattr(document, "status", None),
        "publish_date": _isoformat(getattr(document, "publish_date", None)),
        "summary": getattr(document, "summary", None),
        "content": str(getattr(document, "content", None) or ""),
        "uri": getattr(document, "uri", None),
        "source_name": getattr(document, "source_name", None),
    }
    raw_digest = content_digest(raw)
    replay_identity = content_digest({
        "schema": "mrw.successor.ingest.policy.materialization.v1",
        "state": str(state).strip().upper(),
        "input_index": input_index,
        "raw_digest": raw_digest,
    })
    receipt = acquisition.CollectAttemptReceipt(
        schema_version=acquisition.COLLECT_ATTEMPT_RECEIPT_SCHEMA_REF,
        receipt_kind="DISPATCH_ACKNOWLEDGEMENT",
        provider_type="policy.adapter",
        provider_job_id=f"policy:{str(state).strip().upper()}:{replay_identity}",
        provider_status="yielded",
        attempt_count=1,
        observed_at="1970-01-01T00:00:00Z",
        raw_digest=raw_digest,
        authoritative_readback=False,
        receipt_digest="",
    )
    return CollectBatchRow(
        element_id=f"policy:{str(state).strip().upper()}:document:{input_index}",
        input_index=input_index,
        query_terms=(str(state).strip().upper(),),
        observation=None,
        counts=CollectBatchCounts(),
        links=((str(raw["uri"]).strip(),) if raw["uri"] else ()),
        receipt=receipt,
        result_status="succeeded",
        execution_state="attempted",
    )


def _policy_failure_row(
    *, state: str, input_index: int, message: str, exception_type: str
) -> CollectBatchRow:
    error: CollectFailure = {
        "code": "auto_batch_execution_failed",
        "message": message,
        "query_terms": (str(state).strip().upper(),),
        "exception_type": exception_type,
    }
    return CollectBatchRow(
        element_id=f"policy:{str(state).strip().upper()}:document:{input_index}",
        input_index=input_index,
        query_terms=(str(state).strip().upper(),),
        observation=None,
        counts=CollectBatchCounts(),
        errors=(error,),
        result_status="failed",
        execution_state="attempted",
    )


def materialize_policy_documents(
    documents: Iterable[PolicyDocument],
    *,
    state: str,
    max_documents: int | None = None,
    cancel_check: Callable[[int], bool] | None = None,
    request_id: str | None = None,
    idempotency_key: str | None = None,
    _iteration_error_out: list[BaseException] | None = None,
) -> tuple[list[PolicyDocument], CollectBatchFold]:
    """Materialize the provider iterable and fold its ordered observations once."""
    bounded = max(0, int(max_documents)) if max_documents is not None else None
    materialized: list[PolicyDocument] = []
    rows: list[CollectBatchRow] = []
    request_ref = _policy_request_ref(
        state, request_id=request_id, idempotency_key=idempotency_key
    )
    iterator = iter(documents)
    index = 0
    while bounded is None or index < bounded:
        if cancel_check is not None and bool(cancel_check(index)):
            cancellation = acquisition.CollectCancellationReceipt(
                schema_version=acquisition.COLLECT_CANCELLATION_RECEIPT_SCHEMA_REF,
                code="FAIL_FAST_CANCELLED",
                message="policy materialization cancelled",
                trigger_input_index=index,
                observed="SERIAL_EXECUTION",
                receipt_digest="",
            )
            return materialized, fold_collect_batch_rows(
                tuple(rows), request_ref=request_ref, cancellation=cancellation
            )
        try:
            document = next(iterator)
        except StopIteration:
            break
        except Exception as exc:  # noqa: BLE001 - provider iterable boundary
            if _iteration_error_out is not None:
                _iteration_error_out.append(exc)
            rows.append(_policy_failure_row(
                state=state, input_index=index,
                message=str(exc) or exc.__class__.__name__,
                exception_type=exc.__class__.__name__,
            ))
            break
        if any(not hasattr(document, field) for field in ("content", "title", "state")):
            rows.append(_policy_failure_row(
                state=state, input_index=index,
                message="policy provider yielded an invalid document",
                exception_type="TypeError",
            ))
            index += 1
            continue
        materialized.append(document)
        rows.append(_policy_document_row(document=document, state=state, input_index=index))
        index += 1
    return materialized, fold_collect_batch_rows(tuple(rows), request_ref=request_ref)


def _extraction_readback(
    *,
    requested: bool,
    outcome: dict[str, object] | None,
) -> dict[str, object]:
    if not requested:
        payload: dict[str, object] = {
            "operation": "ingest.policy.structured_extraction.v1",
            "status": "SKIPPED_NOT_REQUESTED",
            "reason": "extraction_not_requested",
            "error": None,
            "domains": {},
        }
        return {**payload, "readback_digest": content_digest(payload)}
    raw = dict(outcome or {})
    status = str(raw.get("status") or "failed").strip().lower()
    typed_status = "SUCCEEDED" if status == "ok" else "FAILED"
    payload: dict[str, object] = {
        "operation": "ingest.policy.structured_extraction.v1",
        "status": typed_status,
        "reason": raw.get("reason"),
        "error": raw.get("error"),
        "domains": _object_dict(raw.get("domains")),
    }
    return {**payload, "readback_digest": content_digest(payload)}


def _policy_provider_iteration_failure(
    state: str, cause: BaseException
) -> Failure:
    return ingest_policy_failures.fail(
        "policy_provider_iteration_failed",
        str(cause) or "policy provider iteration failed",
        {
            "state": str(state).strip().upper(),
            "cause_message": str(cause),
            "exception_type": type(cause).__name__,
        },
    )


def _raise_invalid_policy_failure_lift() -> NoReturn:
    # kit:boundary owner=ingest.policy.provider class=PROGRAMMER_DEFECT failure_family=none witness=test:test_latest_ingest_provider_iteration_failure_lifts
    raise TypeError("policy provider iteration failure lift context is inconsistent")


def _raise_policy_provider_iteration_failure(
    failure: Failure, cause: BaseException
) -> NoReturn:
    if not ingest_policy_failures.matches(failure):
        _raise_invalid_policy_failure_lift()
    # kit:boundary owner=ingest.policy.provider class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=ingest.policy.failure witness=test:test_latest_ingest_provider_iteration_failure_lifts
    raise cause


def ingest_policy_documents(
    state: str,
    source_hint: str | None = None,
    *,
    enable_extraction: bool = False,
    max_documents: int | None = None,
    cancel_check: Callable[[int], bool] | None = None,
    request_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, object]:
    """Ingest policy documents through the frontdoor writer.

    Provider iteration completes before ``start_job``. Bounded/cancellable
    calls use the typed materializer, so the provider tail is not consumed.
    """
    adapter = get_policy_adapter(state, source_hint)
    inserted = 0
    skipped = 0
    # Keep provider iteration before job creation; this preserves the legacy
    # failure boundary while the typed materializer records each item.
    iteration_error: list[BaseException] = []

    documents, materialization = materialize_policy_documents(
        adapter.fetch_documents(),
        state=state,
        max_documents=max_documents,
        cancel_check=cancel_check,
        request_id=request_id,
        idempotency_key=idempotency_key,
        _iteration_error_out=iteration_error,
    )
    if iteration_error:
        _raise_policy_provider_iteration_failure(
            _policy_provider_iteration_failure(state, iteration_error[0]),
            iteration_error[0],
        )
    inserted_ids: list[int] = []

    job_id = start_job("ingest_policy", {"state": state})

    with SessionLocal() as session:
        try:
            extraction_stats = {"requested": bool(enable_extraction), "succeeded": 0, "skipped": 0, "failed": 0}
            item_results: list[dict[str, Any]] = []
            for doc in documents:
                content = doc.content or doc.summary or ""
                if not content:
                    skipped += 1
                    item_results.append({"status": "skipped_empty_content", "uri": doc.uri})
                    continue

                text_hash = _hash_text(content)
                existed = session.query(Document).filter(Document.text_hash == text_hash).first()
                if existed:
                    skipped += 1
                    item_results.append({"status": "skipped_exists", "doc_id": existed.id, "uri": doc.uri})
                    continue

                source = _get_or_create_source(session, doc)

                extraction_plan = {
                    "enabled": bool(enable_extraction),
                    "mode": "policy",
                    "chunks": [content] if enable_extraction else [],
                    "include_policy": True,
                    "include_market": False,
                    "include_sentiment": False,
                    "include_company": True,
                    "include_product": True,
                    "include_operation": True,
                }
                extraction_outcome = None
                if not enable_extraction:
                    extraction_outcome = _extraction_readback(requested=False, outcome=None)
                ingress_envelope = build_frontdoor_ingress_envelope(
                    ingress_type="discovery",
                    entrypoint="ingest.policy_documents",
                    source_mode="provider_harvest",
                    project_key=None,
                    source_ref={"url": doc.uri, "locator": doc.uri},
                    collection_payload={
                        "document_candidate": {
                            "source_name": source.name,
                            "source_kind": "state_site",
                            "source_base_url": doc.uri,
                            "state": doc.state,
                            "doc_type": "policy",
                            "title": doc.title,
                            "status": doc.status,
                            "publish_date": doc.publish_date,
                            "summary": doc.summary,
                            "content": doc.content,
                            "text_hash": text_hash,
                            "uri": doc.uri,
                            "extracted_data_base": {},
                        },
                        "terminal_context": {
                            "platform": "policy_adapter",
                            "ingestion_entrypoint": "ingest.policy_documents",
                            "source_mode": "provider_harvest",
                            "quality_score": 0.0,
                            "degradation_flags": [],
                            "http_status": None,
                            "capability_profile": {},
                            "light_filter": {},
                        },
                        "extraction_plan": extraction_plan,
                        **({"extraction_outcome": extraction_outcome} if extraction_outcome else {}),
                    },
                    raw_snapshot={
                        "state": doc.state,
                        "title": doc.title,
                        "uri": doc.uri,
                        "source_name": source.name,
                    },
                )
                frontdoor_result = run_postprocess_frontdoor(
                    ingress_envelope=ingress_envelope,
                    run_writer=True,
                )
                frontdoor_data = frontdoor_result["data"]
                writer_result = _object_dict(frontdoor_data.get("writer_result"))
                normalized_payload = _object_dict(frontdoor_data.get("normalized_payload"))
                extracted_data = _object_dict(normalized_payload.get("extracted_data"))
                extraction = _object_dict(extracted_data.get("extraction"))
                if extraction:
                    extraction = {**extraction, "domains": _object_dict(extracted_data.get("domains"))}
                extraction_readback = _extraction_readback(
                    requested=bool(enable_extraction),
                    outcome=(
                        extraction
                        if extraction
                        else _object_dict(frontdoor_data.get("extraction_outcome")) or None
                    ),
                )
                extraction_stats["succeeded" if extraction_readback["status"] == "SUCCEEDED" else "failed" if extraction_readback["status"] == "FAILED" else "skipped"] += 1
                item_result = {
                    "status": "ok",
                    "uri": doc.uri,
                    "doc_id": writer_result.get("doc_id"),
                    "extraction": extraction_readback,
                }
                if _safe_int(writer_result.get("inserted")) > 0:
                    inserted_ids.append(_safe_int(writer_result.get("doc_id")))
                    inserted += 1
                elif str(writer_result.get("reason") or "") == "skipped_exists":
                    skipped += 1
                    item_result["status"] = "skipped_exists"
                item_results.append(item_result)

            session.commit()
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            fail_job(job_id, str(exc))
            # kit:boundary owner=ingest.policy.persistence class=SHELL_BOUNDARY_EXCEPTION failure_family=ingest.policy.failure witness=test:test_latest_service_a_ingest_shell_boundaries_reraise_original_errors
            raise

    try:
        if inserted_ids:
            from ..indexer import index_policy_documents

            index_policy_documents(document_ids=inserted_ids)

        materialization_status = (
            "CANCELLED"
            if materialization.cancellation is not None
            else "FAILED"
            if materialization.failed_count or materialization.receipt_conflict
            else "OUTCOME_UNKNOWN"
            if any(
                not acquisition.receipt_implies_completed(receipt)
                for receipt in materialization.receipts
            )
            else "COMPLETED"
        )
        aggregate_kind = (
            "failed"
            if materialization.receipt_conflict
            or (
                materialization.attempted_count > 0
                and materialization.failed_count == materialization.attempted_count
            )
            else "partial"
            if materialization.failed_count
            else "succeeded"
        )
        result: dict[str, object] = {
            "inserted": inserted,
            "skipped": skipped,
            "state": state.upper(),
            "document_ids": inserted_ids,
            "items": item_results[:50],
            "materialization": {
                "schema_version": POLICY_MATERIALIZATION_PROJECTION_SCHEMA_REF,
                "status": materialization_status,
                "outcome_count": len(materialization.rows),
                "sequence_digest": materialization.sequence_digest,
                "aggregate": {
                    "schema_version": COLLECT_BATCH_FOLD_SCHEMA_REF,
                    "kind": aggregate_kind,
                    "aggregate_counts": materialization.counts.to_plain(),
                    "errors": [
                        collect_failure_to_plain(error)
                        for error in materialization.errors
                    ],
                    "receipts": [receipt.to_plain() for receipt in materialization.receipts],
                    "links": list(materialization.links),
                    "ordered_rows": [row.to_plain() for row in materialization.rows],
                },
                "replay_identity": (
                    materialization.request_ref.request_digest
                    if materialization.request_ref is not None
                    else None
                ),
                "cancellation": (
                    materialization.cancellation.to_plain()
                    if materialization.cancellation is not None
                    else None
                ),
            },
            "extraction": extraction_stats,
        }
        if materialization.cancellation is not None:
            fail_job(job_id, "policy materialization cancelled")
        else:
            complete_job(job_id, result=result)
        return result
    except Exception as exc:  # noqa: BLE001
        fail_job(job_id, str(exc))
        # kit:boundary owner=ingest.policy.indexing class=SHELL_BOUNDARY_EXCEPTION failure_family=ingest.policy.failure witness=test:test_latest_service_a_ingest_shell_boundaries_reraise_original_errors
        raise
