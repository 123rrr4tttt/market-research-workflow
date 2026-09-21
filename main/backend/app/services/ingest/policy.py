from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from typing import Any, NoReturn

from sqlalchemy.orm import Session

from app.successor_runtime.capabilities import collect_c3 as c3
from app.successor_runtime.capabilities.checksum import content_digest
from functorial_kit import Failure
from mrw_functorial_kit.core.provider_port_failures import ingest_policy_failures

from ...models.base import SessionLocal
from ...models.entities import Document, Source
from ..job_logger import start_job, complete_job, fail_job
from .frontdoor_ingress import build_frontdoor_ingress_envelope
from .postprocess_frontdoor import run_postprocess_frontdoor
from .provider_ports import PolicyDocument, get_policy_adapter


def _get_or_create_source(session: Session, doc: PolicyDocument) -> Source:
    name = doc.source_name or "Unknown Source"
    source = (
        session.query(Source)
        .filter(Source.name == name, Source.kind == "state_site")
        .one_or_none()
    )
    if source:
        return source

    source = Source(name=name, kind="state_site", base_url=doc.uri)
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
) -> c3.CollectRequestRef:
    state_key = str(state).strip().upper()
    identity = str(request_id or idempotency_key or "").strip()
    if not identity:
        identity = content_digest({"state": state_key, "channel": "search.policy"})
    return c3.build_collect_request_ref(
        request_id=f"policy-materialize:{state_key}:{identity}",
        project_key=f"policy:{state_key}",
        channel="search.policy",
    )


def _policy_document_observation(
    *,
    document: PolicyDocument,
    state: str,
    input_index: int,
) -> c3.CollectElementSucceeded:
    raw = {
        "state": str(getattr(document, "state", None) or state),
        "title": str(getattr(document, "title", None) or ""),
        "status": getattr(document, "status", None),
        "publish_date": (
            getattr(document, "publish_date", None).isoformat()
            if getattr(document, "publish_date", None) is not None
            else None
        ),
        "summary": getattr(document, "summary", None),
        "content": str(getattr(document, "content", None) or ""),
        "uri": getattr(document, "uri", None),
        "source_name": getattr(document, "source_name", None),
    }
    raw_digest = content_digest(raw)
    replay_identity = content_digest(
        {
            "schema": "mrw.successor.ingest.policy.materialization.v1",
            "state": str(state).strip().upper(),
            "input_index": input_index,
            "raw_digest": raw_digest,
        }
    )
    receipt = c3.CollectAttemptReceipt(
        schema_version=c3.COLLECT_ATTEMPT_RECEIPT_SCHEMA_REF,
        # The iterable yields a provider value, but the local content digest
        # is not an authoritative provider readback. Keep the acknowledgement
        # explicit so callers cannot treat materialization as completion.
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
    return c3.CollectElementSucceeded(
        schema_version=c3.COLLECT_ELEMENT_OUTCOME_SCHEMA_REF,
        element_id=f"policy:{str(state).strip().upper()}:document:{input_index}",
        input_index=input_index,
        counts=c3.CollectCounts(),
        links=((str(raw["uri"]).strip(),) if raw["uri"] else ()),
        receipt=receipt,
        legacy_observation_ref=f"legacy:{replay_identity}",
        outcome_digest="",
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
) -> tuple[list[PolicyDocument], c3.CollectTraversalResult]:
    """Materialize a bounded policy iterable with C3 ordered observations.

    The iterable is consumed in input order and each yielded document receives
    a content-bound attempt/readback receipt and replay identity. Cancellation
    is observed only at an element boundary, which is the strongest guarantee
    available for a synchronous provider iterable.
    """
    bounded = max(0, int(max_documents)) if max_documents is not None else None
    materialized: list[PolicyDocument] = []
    outcomes: list[c3.CollectElementOutcome] = []
    request_ref = _policy_request_ref(
        state,
        request_id=request_id,
        idempotency_key=idempotency_key,
    )
    iterator = iter(documents)
    index = 0
    while bounded is None or index < bounded:
        if cancel_check is not None and bool(cancel_check(index)):
            cause = c3.CollectElementError(
                code="auto_batch_execution_failed",
                message="policy materialization cancelled",
                query_terms=(str(state).strip().upper(),),
                exception_type="CancellationRequested",
                error_digest="",
            )
            return materialized, c3.OrderedTraversalAborted(
                schema_version="mrw.successor.collect.c3.traversal-result.v1",
                partial_outcomes=tuple(outcomes),
                cause=cause,
                cancellation_receipt=c3.CollectCancellationReceipt(
                    schema_version=c3.COLLECT_CANCELLATION_RECEIPT_SCHEMA_REF,
                    code="FAIL_FAST_CANCELLED",
                    message=cause.message,
                    trigger_input_index=index,
                    observed="SERIAL_EXECUTION",
                    receipt_digest="",
                ),
                cancellation_observed=True,
                request_ref=request_ref,
            )
        try:
            document = next(iterator)
        except StopIteration:
            break
        except Exception as exc:  # noqa: BLE001 - provider iterable boundary
            if _iteration_error_out is not None:
                _iteration_error_out.append(exc)
            error = c3.CollectElementError(
                code="auto_batch_execution_failed",
                message=str(exc) or exc.__class__.__name__,
                query_terms=(str(state).strip().upper(),),
                exception_type=exc.__class__.__name__,
                error_digest="",
            )
            outcomes.append(
                c3.CollectElementFailed(
                    schema_version=c3.COLLECT_ELEMENT_OUTCOME_SCHEMA_REF,
                    element_id=f"policy:{str(state).strip().upper()}:document:{index}",
                    input_index=index,
                    error=error,
                    legacy_observation_ref=f"legacy:{error.error_digest}",
                    outcome_digest="",
                )
            )
            break
        # Keep the legacy structural port contract: adapters and tests may
        # return compatible record objects rather than the concrete dataclass.
        if any(not hasattr(document, field) for field in ("content", "title", "state")):
            error = c3.CollectElementError(
                code="auto_batch_execution_failed",
                message="policy provider yielded an invalid document",
                query_terms=(str(state).strip().upper(),),
                exception_type="TypeError",
                error_digest="",
            )
            outcomes.append(
                c3.CollectElementFailed(
                    schema_version=c3.COLLECT_ELEMENT_OUTCOME_SCHEMA_REF,
                    element_id=f"policy:{str(state).strip().upper()}:document:{index}",
                    input_index=index,
                    error=error,
                    legacy_observation_ref=f"legacy:{error.error_digest}",
                    outcome_digest="",
                )
            )
            index += 1
            continue
        materialized.append(document)
        outcomes.append(
            _policy_document_observation(
                document=document,
                state=state,
                input_index=index,
            )
        )
        index += 1

    observation = c3.CollectTraversalObservation(
        schema_version=c3.COLLECT_TRAVERSAL_OBSERVATION_SCHEMA_REF,
        observation_profile=c3.COLLECT_TRAVERSAL_OBSERVATION_PROFILE,
        request_ref=request_ref,
        traversal_policy="MATERIALIZED_SHAPE",
        failure_policy="ACCUMULATE",
        ordered_outcomes=tuple(outcomes),
        requested_parallelism=1,
        effective_parallelism=1,
        cancellation_observed=False,
        observation_digest="",
    )
    traversal: c3.CollectTraversalResult
    if len(outcomes) == 1:
        traversal = c3.CollectTraversalSingleton(
            schema_version="mrw.successor.collect.c3.traversal-result.v1",
            observation=observation,
        )
    else:
        traversal = c3.OrderedTraversalCompleted(
            schema_version="mrw.successor.collect.c3.traversal-result.v1",
            observation=observation,
        )
    return materialized, traversal


def _extraction_readback(
    *,
    requested: bool,
    outcome: dict[str, Any] | None,
) -> dict[str, Any]:
    if not requested:
        payload = {
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
    payload = {
        "operation": "ingest.policy.structured_extraction.v1",
        "status": typed_status,
        "reason": raw.get("reason"),
        "error": raw.get("error"),
        "domains": dict(raw.get("domains") or {}),
    }
    return {**payload, "readback_digest": content_digest(payload)}


def _policy_materialization_typed_views(
    traversal: c3.CollectTraversalResult,
    *,
    state: str,
    request_id: str | None = None,
    idempotency_key: str | None = None,
) -> tuple[c3.OrderedCollectElementOutcomeSequence, c3.CollectAggregateOutcome]:
    observation = getattr(traversal, "observation", None)
    outcomes = (
        getattr(observation, "ordered_outcomes", None)
        if observation is not None
        else getattr(traversal, "partial_outcomes", ())
    ) or ()
    sequence = c3.OrderedCollectElementOutcomeSequence(
        schema_version="mrw.successor.collect.c3.outcome-sequence.v1",
        parent_request_ref=(
            getattr(observation, "request_ref", None)
            or _policy_request_ref(
                state,
                request_id=request_id,
                idempotency_key=idempotency_key,
            )
        ),
        outcomes=tuple(outcomes),
        sequence_digest="",
    )
    aggregate = c3.fold_ordered_results(
        sequence,
        aggregation_policy_ref=c3.COLLECT_AGGREGATION_POLICY_ACCUMULATE_REF,
        observation_profile_ref=c3.COLLECT_FOLD_OBSERVATION_PROFILE,
    )
    return sequence, aggregate


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
) -> dict:
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
                writer_result = (frontdoor_result.get("data") or {}).get("writer_result") if isinstance(frontdoor_result.get("data"), dict) else {}
                normalized_payload = (frontdoor_result.get("data") or {}).get("normalized_payload") if isinstance(frontdoor_result.get("data"), dict) else {}
                extracted_data = (normalized_payload or {}).get("extracted_data") if isinstance(normalized_payload, dict) else {}
                extraction = (extracted_data or {}).get("extraction") if isinstance(extracted_data, dict) else {}
                if isinstance(extraction, dict) and isinstance(extracted_data, dict):
                    extraction = {**extraction, "domains": extracted_data.get("domains") or {}}
                extraction_readback = _extraction_readback(
                    requested=bool(enable_extraction),
                    outcome=(
                        extraction
                        if isinstance(extraction, dict) and extraction
                        else ((frontdoor_result.get("data") or {}).get("extraction_outcome") if isinstance(frontdoor_result.get("data"), dict) else None)
                    ),
                )
                extraction_stats["succeeded" if extraction_readback["status"] == "SUCCEEDED" else "failed" if extraction_readback["status"] == "FAILED" else "skipped"] += 1
                item_result = {
                    "status": "ok",
                    "uri": doc.uri,
                    "doc_id": (writer_result or {}).get("doc_id"),
                    "extraction": extraction_readback,
                }
                if int((writer_result or {}).get("inserted") or 0) > 0:
                    inserted_ids.append(int((writer_result or {}).get("doc_id") or 0))
                    inserted += 1
                elif str((writer_result or {}).get("reason") or "") == "skipped_exists":
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

        sequence, aggregate = _policy_materialization_typed_views(
            materialization,
            state=state,
            request_id=request_id,
            idempotency_key=idempotency_key,
        )
        materialized_outcomes = sequence.outcomes
        materialization_status = (
            "CANCELLED"
            if isinstance(materialization, c3.OrderedTraversalAborted)
            else "FAILED"
            if any(isinstance(outcome, c3.CollectElementFailed) for outcome in materialized_outcomes)
            else "OUTCOME_UNKNOWN"
            if any(
                outcome.receipt is not None
                and not c3.receipt_implies_completed(outcome.receipt)
                for outcome in materialized_outcomes
            )
            else "COMPLETED"
        )
        result = {
            "inserted": inserted,
            "skipped": skipped,
            "state": state.upper(),
            "document_ids": inserted_ids,
            "items": item_results[:50],
            "materialization": {
                "status": materialization_status,
                "outcome_count": len(sequence.outcomes),
                "sequence_digest": sequence.sequence_digest,
                "aggregate": aggregate.to_plain(),
                "replay_identity": getattr(getattr(materialization, "observation", None), "request_ref", None).request_digest if getattr(getattr(materialization, "observation", None), "request_ref", None) else None,
                "cancellation": (getattr(materialization, "cancellation_receipt", None).to_plain() if getattr(materialization, "cancellation_receipt", None) is not None else None),
            },
            "extraction": extraction_stats,
        }
        if isinstance(materialization, c3.OrderedTraversalAborted):
            fail_job(job_id, "policy materialization cancelled")
        else:
            complete_job(job_id, result=result)
        return result
    except Exception as exc:  # noqa: BLE001
        fail_job(job_id, str(exc))
        # kit:boundary owner=ingest.policy.indexing class=SHELL_BOUNDARY_EXCEPTION failure_family=ingest.policy.failure witness=test:test_latest_service_a_ingest_shell_boundaries_reraise_original_errors
        raise
