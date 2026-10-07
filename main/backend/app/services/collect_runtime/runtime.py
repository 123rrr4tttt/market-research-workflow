from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal, NoReturn, SupportsIndex, SupportsInt, TypeGuard

from functorial_kit.core.failure import Failure

from mrw_functorial_kit.core.provider_port_failures import collect_runtime_failures

from ..agent_batch.task_contract import parse_source_library_runtime_params
from app.successor_runtime.language.sync import interpret_ordered_sync

from .contracts import (
    FLOW_SOURCE_COLLECT,
    CollectEffectGateway,
    CollectFailure,
    CollectJsonObject,
    CollectJsonValue,
    CollectRequest,
    CollectResult,
    SourceLibraryCompatResponse,
    SourceLibraryCompatProjector,
)
from .delivery import DeliveryObservation, observe_delivery

if TYPE_CHECKING:
    from app.successor_runtime.capabilities import acquisition_batch as acquisition

_source_library_compat_projector: SourceLibraryCompatProjector | None = None
_successor_effect_gateway: CollectEffectGateway | None = None


def _collect_contract_failure(code: str, message: str, *, site: str) -> Failure:
    return collect_runtime_failures.fail(
        code,
        message,
        {"operation": "collect.runtime", "site": site},
    )


def _raise_collect_contract(failure: Failure, exception_type: type[Exception] = ValueError) -> NoReturn:
    # kit:boundary owner=collect.runtime.contract_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=collect.runtime.failure witness=test:test_w03_collect_contract_failures
    raise exception_type(failure.message)


def register_source_library_compat_projector(projector: SourceLibraryCompatProjector) -> None:
    """Inject the legacy source-library response projection at composition time."""

    global _source_library_compat_projector
    if not callable(projector):
        _raise_collect_contract(
            _collect_contract_failure(
                "compat_projector_contract_invalid",
                "source-library compatibility projector must be callable",
                site="register_source_library_compat_projector.projector",
            ),
            TypeError,
        )
    _source_library_compat_projector = projector


def register_successor_collect_effect_gateway(gateway: CollectEffectGateway) -> None:
    """Inject the effectful successor gateway; it is separate from legacy adapters."""

    global _successor_effect_gateway
    if not callable(gateway):
        _raise_collect_contract(
            _collect_contract_failure(
                "successor_effect_gateway_invalid",
                "successor collect effect gateway must be callable",
                site="register_successor_collect_effect_gateway.gateway",
            ),
            TypeError,
        )
    _successor_effect_gateway = gateway


def reset_successor_collect_effect_gateway() -> None:
    global _successor_effect_gateway

    _successor_effect_gateway = None



def run_collect(request: CollectRequest) -> CollectResult:
    """Dispatch every collect through the one typed adapter-effect gateway."""

    batched = _run_successor_collect(request)
    if batched is not None:
        return _attach_delivery_observation(batched)
    return _run_collect_no_batch(request)


@dataclass(slots=True)
class _CollectDeliveryView:
    status: str | None
    provider_job_id: str | None
    provider_type: str | None
    provider_status: str | None
    meta: dict[str, object] | None


@dataclass(slots=True)
class _CollectDeliveryCounts:
    inserted: int
    updated: int
    skipped: int


@dataclass(slots=True)
class _CollectDeliveryRow:
    element_id: str
    input_index: int
    query_terms: tuple[str, ...]
    observation: DeliveryObservation
    counts: _CollectDeliveryCounts | None = None
    links: tuple[str, ...] = ()
    execution_state: Literal["attempted", "attempted_unknown", "not_attempted"] = "not_attempted"

    def to_plain(self) -> CollectJsonObject:
        value: CollectJsonObject = {
            "element_id": self.element_id,
            "input_index": self.input_index,
            "query_terms": list(self.query_terms),
            "observation": asdict(self.observation),
            "execution_state": self.execution_state,
        }
        if self.counts is not None:
            value["counts"] = {
                "inserted": self.counts.inserted,
                "updated": self.counts.updated,
                "skipped": self.counts.skipped,
            }
            value["links"] = list(self.links)
        return value


def _collect_delivery_observation(
    result: CollectResult, *, expected_delivery: str = "unknown"
) -> DeliveryObservation:
    meta = result.meta
    raw = _json_object(meta.get("raw"))
    raw_result = _json_object(raw.get("result"))
    terminal_output = _json_object(meta.get("terminal_output"))
    terminal_meta = _json_object(terminal_output.get("meta"))
    handoff = _json_object(terminal_meta.get("provider_handoff"))
    readback = (
        meta.get("terminal_readback") or raw.get("terminal_readback")
        or raw_result.get("terminal_readback") or terminal_meta.get("terminal_readback")
    )
    provider_job_id = result.provider_job_id or raw.get("provider_job_id") or raw_result.get("provider_job_id") or terminal_meta.get("provider_job_id") or handoff.get("provider_job_id")
    return observe_delivery(_CollectDeliveryView(
        status=result.status,
        provider_job_id=_optional_text(provider_job_id),
        provider_type=_optional_text(result.provider_type or raw.get("provider_type") or raw_result.get("provider_type") or handoff.get("provider_type")),
        provider_status=_optional_text(result.provider_status or raw.get("provider_status") or raw_result.get("provider_status") or handoff.get("provider_status") or terminal_output.get("status")),
        meta={"terminal_readback": readback},
    ), expected_delivery=expected_delivery)


def _attach_delivery_observation(result: CollectResult) -> CollectResult:
    observation = _collect_delivery_observation(result)
    result.meta = dict(result.meta or {})
    result.meta["delivery_observation"] = asdict(observation)
    raw = result.meta.get("raw")
    if isinstance(raw, dict):
        result.meta["raw"] = {**raw, "delivery_observation": asdict(observation)}
    return result


def _outcome_unknown_result(request: CollectRequest) -> CollectResult:
    """Fail closed when no explicit collect effect gateway is bound."""

    result = CollectResult(
        flow=request.flow,
        channel=request.channel,
        status="unknown",
        errors=[{
            "code": "successor_effect_gateway_unavailable",
            "message": "collect requires an explicit effect gateway",
        }],
        meta={
            "raw": {
                "outcome": "OutcomeUnknown",
                "reason": "effect_gateway_unavailable",
            }
        },
    )
    from .display_meta import build_display_meta

    result.display_meta = build_display_meta(request, result)
    return result


def _json_object(value: CollectJsonValue) -> CollectJsonObject:
    return value if isinstance(value, dict) else {}


def _json_link_values(value: CollectJsonValue) -> list[CollectJsonValue] | dict[str, CollectJsonValue] | str | tuple[()]:
    # JSON arrays and strings are the iterable legacy link shapes.
    if not value:
        return ()
    if isinstance(value, (list, dict, str)):
        return value
    _raise_collect_contract(
        _collect_contract_failure(
            "auto_batch_execution_failed",
            f"'{type(value).__name__}' object is not iterable",
            site="collect_result_to_element_outcome.links",
        ),
        TypeError,
    )


def _json_links(value: CollectJsonValue) -> tuple[str, ...]:
    return tuple(str(link).strip() for link in _json_link_values(value) if str(link).strip())


def _collect_result_to_element_outcome(
    result: CollectResult, element: acquisition.CollectBatchElement
) -> acquisition.CollectElementOutcome:
    from app.successor_runtime.capabilities import acquisition_batch as acquisition
    from app.successor_runtime.capabilities.checksum import content_digest

    raw = dict(_json_object(result.meta.get("raw")))
    links = _json_links(raw.get("links"))
    delivery = _collect_delivery_observation(result)
    target_delivery_ok = delivery.state == "delivered"
    receipt = None
    if delivery.provider_job_id:
        provider_status = None if result.provider_status is None else str(result.provider_status)
        authoritative = target_delivery_ok
        receipt = acquisition.CollectAttemptReceipt(
            schema_version=acquisition.COLLECT_ATTEMPT_RECEIPT_SCHEMA_REF,
            receipt_kind=("AUTHORITATIVE_READBACK" if authoritative else "DISPATCH_ACKNOWLEDGEMENT"),
            provider_type=str(result.provider_type or "unknown"),
            provider_job_id=delivery.provider_job_id,
            provider_status=provider_status,
            attempt_count=int(result.attempt_count or 0),
            observed_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            raw_digest=content_digest(raw),
            authoritative_readback=authoritative,
            receipt_digest="",
        )
    counts = acquisition.CollectCounts(
        inserted=int(result.inserted or 0),
        updated=int(result.updated or 0),
        skipped=int(result.skipped or 0),
    )
    legacy_ref = "legacy:" + content_digest({"element": element.element_id, "result": raw})
    if target_delivery_ok:
        return acquisition.CollectElementSucceeded(
            schema_version=acquisition.COLLECT_ELEMENT_OUTCOME_SCHEMA_REF,
            element_id=element.element_id,
            input_index=element.input_index,
            counts=counts,
            links=links,
            receipt=receipt,
            legacy_observation_ref=legacy_ref,
            outcome_digest="",
        )
    first_error: CollectFailure = (result.errors or [{}])[0]
    if not target_delivery_ok and not first_error.get("message"):
        first_error = {
            "code": "runner_unavailable",
            "message": "target delivery readback is required for successor completion",
        }
    return acquisition.CollectElementFailed(
        schema_version=acquisition.COLLECT_ELEMENT_OUTCOME_SCHEMA_REF,
        element_id=element.element_id,
        input_index=element.input_index,
        error=acquisition.CollectElementError(
            code=(str(first_error.get("code") or "auto_batch_execution_failed") if str(first_error.get("code") or "") in acquisition.COLLECT_ELEMENT_ERROR_CODES else "auto_batch_execution_failed"),
            message=str(first_error.get("message") or result.status or "collect element failed"),
            query_terms=tuple(element.query_terms),
            exception_type=first_error.get("exception_type"),
            error_digest="",
        ),
        counts=counts,
        links=links,
        receipt=receipt,
        legacy_observation_ref=legacy_ref,
        outcome_digest="",
    )


def _build_collect_batch_plan(
    request: CollectRequest,
) -> tuple[acquisition.CollectBatchPlan, acquisition.CollectResourcePolicy]:
    from app.successor_runtime.capabilities import acquisition_batch as acquisition
    from app.successor_runtime.capabilities.checksum import content_digest

    project_key = str(request.project_key or "").strip()
    request_id = "collect:" + content_digest(
        {
            "flow": request.flow,
            "channel": request.channel,
            "project_key": project_key,
            "query_terms": list(request.query_terms or []),
            "urls": list(request.urls or []),
            "limit": request.limit,
            "provider": request.provider,
            "language": request.language,
            "scope": request.scope,
            "item_key": request.item_key,
            "options": dict(request.options or {}),
            "source_context": dict(request.source_context or {}),
        }
    )
    request_ref = acquisition.build_collect_request_ref(
        request_id=request_id,
        project_key=project_key,
        channel=request.channel,
    )
    snapshot = acquisition.CollectLegacyRequestSnapshot(
        schema_version=acquisition.COLLECT_REQUEST_SNAPSHOT_SCHEMA_REF,
        flow=request.flow,
        channel=request.channel,
        project_key=project_key,
        query_terms=tuple(request.query_terms or ()),
        urls=tuple(request.urls or ()),
        limit=request.limit,
        options=acquisition.freeze_json_object(dict(request.options or {})),
        source_context=acquisition.freeze_json_object(dict(request.source_context or {})),
        snapshot_digest="",
    )
    raw_deadline = request.options.get("deadline_seconds")
    deadline_seconds: int | None = None
    if isinstance(raw_deadline, (bool, int, float, str)):
        try:
            deadline_seconds = max(1, int(raw_deadline))
        except (TypeError, ValueError):
            deadline_seconds = None
    policy = acquisition.CollectResourcePolicy(
        schema_ref=acquisition.COLLECT_RESOURCE_POLICY_SCHEMA_REF,
        max_parallelism=1,
        deadline_seconds=deadline_seconds,
        cancellation=(
            "COORDINATED"
            if acquisition.resolve_auto_batch_fail_fast(request)
            else "NONE"
        ),
        backpressure=True,
        provider_concurrency_key=f"{request.channel}:{request.provider or 'default'}",
        policy_digest="",
    )
    plan = acquisition.build_collect_batch_plan(
        request_ref=request_ref,
        snapshot=snapshot,
        plan_id=f"collect-sync:{request_id}",
        resource_policy=policy,
        authority_scope_ref=f"project:{project_key}",
    )
    return plan, policy


def _failed_collect_outcome(
    element: acquisition.CollectBatchElement,
    exc: Exception,
) -> acquisition.CollectElementFailed:
    from app.successor_runtime.capabilities import acquisition_batch as acquisition

    error = acquisition.CollectElementError(
        code="auto_batch_execution_failed",
        message=str(exc) or exc.__class__.__name__,
        query_terms=element.query_terms,
        exception_type=exc.__class__.__name__,
        error_digest="",
    )
    return acquisition.CollectElementFailed(
        schema_version=acquisition.COLLECT_ELEMENT_OUTCOME_SCHEMA_REF,
        element_id=element.element_id,
        input_index=element.input_index,
        error=error,
        counts=acquisition.CollectCounts(),
        links=(),
        receipt=None,
        legacy_observation_ref="legacy:" + error.error_digest,
        outcome_digest="",
    )


def _collect_cancellation_receipt(
    cause: acquisition.CollectElementError,
    *,
    trigger_input_index: int,
) -> acquisition.CollectCancellationReceipt:
    from app.successor_runtime.capabilities import acquisition_batch as acquisition

    return acquisition.CollectCancellationReceipt(
        schema_version=acquisition.COLLECT_CANCELLATION_RECEIPT_SCHEMA_REF,
        code="FAIL_FAST_CANCELLED",
        message=cause.message,
        trigger_input_index=trigger_input_index,
        observed="SERIAL_EXECUTION",
        receipt_digest="",
    )


def _project_collect_aggregate(
    request: CollectRequest,
    aggregate: acquisition.CollectAggregateOutcome,
    sequence: acquisition.OrderedCollectElementOutcomeSequence,
    plan: acquisition.CollectBatchPlan,
    *,
    cancellation: acquisition.CollectCancellationReceipt | None = None,
) -> CollectResult:
    from app.successor_runtime.capabilities import acquisition_batch as acquisition

    counts: acquisition.CollectCounts | None = None
    receipts: tuple[acquisition.CollectAttemptReceipt, ...] = ()
    links: tuple[str, ...] = ()
    element_errors: tuple[acquisition.CollectElementError, ...] = ()
    if isinstance(
        aggregate,
        (
            acquisition.CollectAggregateSucceeded,
            acquisition.CollectAggregatePartial,
            acquisition.CollectAggregateFailed,
        ),
    ):
        counts = aggregate.aggregate_counts
        receipts = aggregate.receipts
        links = aggregate.links
    if isinstance(
        aggregate,
        (acquisition.CollectAggregatePartial, acquisition.CollectAggregateFailed),
    ):
        element_errors = aggregate.errors

    batch_results: list[CollectJsonValue] = []
    inserted_count = 0 if counts is None else counts.inserted
    updated_count = 0 if counts is None else counts.updated
    skipped_count = 0 if counts is None else counts.skipped
    raw: CollectJsonObject = {
        "inserted": inserted_count,
        "updated": updated_count,
        "skipped": skipped_count,
        "auto_batched": True,
        "batches_total": len(plan.elements),
        "batch_parallelism": plan.effective_parallelism,
        "batch_parallelism_requested": plan.requested_parallelism,
        "batch_independence_policy_explicit": plan.effective_parallelism > 1,
        "batch_results": batch_results,
        "typed_batch_results": [outcome.to_plain() for outcome in sequence.outcomes],
        "ordered_outcomes": sequence.to_plain(),
        "aggregate": aggregate.to_plain(),
        "aggregate_kind": aggregate.kind,
    }
    for outcome in sequence.outcomes:
        projection: CollectJsonObject = {
            "status": outcome.status,
            "inserted": outcome.counts.inserted,
            "updated": outcome.counts.updated,
            "skipped": outcome.counts.skipped,
            "errors": (
                [outcome.error.to_plain()]
                if isinstance(outcome, acquisition.CollectElementFailed)
                and outcome.error is not None
                else []
            ),
            "links": list(outcome.links),
        }
        item: CollectJsonObject = {
            "query_terms": list(
                plan.elements[outcome.input_index].query_terms
                if 0 <= outcome.input_index < len(plan.elements)
                else (
                    outcome.error.query_terms
                    if isinstance(outcome, acquisition.CollectElementFailed)
                    and outcome.error is not None
                    else ()
                )
            ),
            "result": projection,
        }
        if outcome.receipt is not None:
            item.update(
                {
                    "provider_job_id": outcome.receipt.provider_job_id,
                    "provider_type": outcome.receipt.provider_type,
                    "provider_status": outcome.receipt.provider_status,
                    "attempt_count": outcome.receipt.attempt_count,
                }
            )
        batch_results.append(item)
    if cancellation is not None:
        raw["cancellation_receipt"] = cancellation.to_plain()
    if receipts:
        raw["receipts"] = [receipt.to_plain() for receipt in receipts]
        raw["provider_job_ids"] = [receipt.provider_job_id for receipt in receipts]
    if links:
        raw["links"] = list(links)
    errors: list[CollectFailure] = [
        CollectFailure(**error.to_plain()) for error in element_errors
    ]
    terminal_receipts = bool(receipts) and all(
        acquisition.receipt_implies_completed(receipt) for receipt in receipts
    )
    if cancellation is not None:
        status = "cancelled"
    elif aggregate.kind == "succeeded" and terminal_receipts:
        status = "completed"
    elif aggregate.kind == "succeeded":
        status = "accepted"
    elif aggregate.kind == "partial":
        status = "partial"
    else:
        status = "failed"
    result = CollectResult(
        flow=request.flow,
        channel=request.channel,
        status=status,
        inserted=inserted_count,
        updated=updated_count,
        skipped=skipped_count,
        errors=errors,
        meta={
            "raw": raw,
            "batch_parallelism": plan.effective_parallelism,
            "batch_parallelism_requested": plan.requested_parallelism,
            "batch_independence_policy_explicit": plan.effective_parallelism > 1,
        },
    )
    if len(receipts) == 1:
        result.provider_job_id = receipts[0].provider_job_id
        result.provider_type = receipts[0].provider_type
        result.provider_status = receipts[0].provider_status
        result.attempt_count = receipts[0].attempt_count
    return result


def _run_successor_collect(request: CollectRequest) -> CollectResult | None:
    """Interpret one known finite collect batch in request-local order."""

    from app.successor_runtime.capabilities import acquisition_batch as acquisition
    if (
        request.channel not in acquisition.COLLECT_AUTO_BATCH_CHANNELS
        or not request.project_key
        or not acquisition.should_auto_batch(request)
    ):
        return None
    gateway = _successor_effect_gateway
    if gateway is None:
        return _outcome_unknown_result(request)
    plan, policy = _build_collect_batch_plan(request)
    delivery_by_index: dict[int, _CollectDeliveryRow] = {}

    def _run_bound_effect(
        element: acquisition.CollectBatchElement,
        _previous: None,
    ) -> acquisition.CollectElementOutcome:
        effect_request = replace(
            request,
            query_terms=list(element.query_terms),
            limit=element.per_batch_limit,
            source_context={
                **dict(request.source_context or {}),
                "auto_batched_child": True,
            },
        )
        try:
            effect_result = gateway(effect_request)
        except Exception as exc:  # noqa: BLE001 - domain failure row preserves partial order
            return _failed_collect_outcome(element, exc)
        effect_raw = _json_object(effect_result.meta.get("raw"))
        try:
            observed_links = tuple(
                str(link)
                for link in _json_link_values(effect_raw.get("links"))
                if str(link).strip()
            )
        except Exception as exc:  # noqa: BLE001 - preserve the attempted delivery before typed projection
            delivery_by_index[element.input_index] = _CollectDeliveryRow(
                element_id=element.element_id,
                input_index=element.input_index,
                query_terms=element.query_terms,
                observation=_collect_delivery_observation(effect_result),
                counts=_CollectDeliveryCounts(
                    inserted=int(effect_result.inserted or 0),
                    updated=int(effect_result.updated or 0),
                    skipped=int(effect_result.skipped or 0),
                ),
                execution_state="attempted_unknown",
            )
            return _failed_collect_outcome(element, exc)
        delivery_by_index[element.input_index] = _CollectDeliveryRow(
            element_id=element.element_id,
            input_index=element.input_index,
            query_terms=element.query_terms,
            observation=_collect_delivery_observation(effect_result),
            counts=_CollectDeliveryCounts(
                inserted=int(effect_result.inserted or 0),
                updated=int(effect_result.updated or 0),
                skipped=int(effect_result.skipped or 0),
            ),
            links=observed_links,
        )
        try:
            return _collect_result_to_element_outcome(effect_result, element)
        except Exception as exc:  # noqa: BLE001 - typed projection failure remains one ordered element failure
            row = delivery_by_index[element.input_index]
            if row.observation.state == "unknown" and row.observation.provider_state == "unknown":
                delivery_by_index[element.input_index] = replace(
                    row,
                    execution_state="attempted_unknown",
                )
            return _failed_collect_outcome(element, exc)

    ordered_outcomes = interpret_ordered_sync(
        plan.elements,
        initial_value=None,
        invoke=_run_bound_effect,
        continue_after=lambda outcome: not (
            isinstance(outcome, acquisition.CollectElementFailed)
            and plan.failure_policy == "FAIL_FAST_WITH_PARTIAL_OBSERVATION"
        ),
        output_value=lambda _outcome: None,
    )
    failed = next(
        (
            outcome
            for outcome in ordered_outcomes
            if isinstance(outcome, acquisition.CollectElementFailed)
        ),
        None,
    )
    if failed is not None and plan.failure_policy == "FAIL_FAST_WITH_PARTIAL_OBSERVATION":
        assert failed.error is not None
        cancelled = True
        cancellation = _collect_cancellation_receipt(
            failed.error,
            trigger_input_index=failed.input_index,
        )
    else:
        cancelled = False
        cancellation = None
    outcome_indexes = {item.input_index for item in ordered_outcomes}
    delivery_rows: list[_CollectDeliveryRow] = []
    for element in plan.elements:
        row = delivery_by_index.get(element.input_index)
        if row is None:
            row = _CollectDeliveryRow(
                element_id=element.element_id,
                input_index=element.input_index,
                query_terms=element.query_terms,
                observation=observe_delivery(None),
            )
        delivery_rows.append(replace(row,
            execution_state=(
                row.execution_state if row.execution_state != "not_attempted"
                else "attempted" if element.input_index in delivery_by_index
                else "attempted_unknown" if element.input_index in outcome_indexes
                else "not_attempted"
            ),
        ))
    delivery_states = [
        row.observation.state
        for row in delivery_rows if row.execution_state == "attempted"
    ]
    pending_delivery = any(state in {"waiting", "unknown"} for state in delivery_states)
    delivery_cancelled = any(state == "cancelled" for state in delivery_states)
    if pending_delivery or delivery_cancelled:
        # The acquisition outcome union has only succeeded/failed element variants. Preserve
        # uncertain or cancelled owner observations before its fold would
        # mislabel them as failures, and do not unlock the next collect step.
        counts = {
            "inserted": sum(row.counts.inserted for row in delivery_rows if row.counts is not None),
            "updated": sum(row.counts.updated for row in delivery_rows if row.counts is not None),
            "skipped": sum(row.counts.skipped for row in delivery_rows if row.counts is not None),
        }
        links = list(dict.fromkeys(
            link for row in delivery_rows for link in row.links
        ))
        state: Literal["unknown", "cancelled"] = "unknown" if pending_delivery else "cancelled"
        requested_parallelism = acquisition.resolve_auto_batch_parallelism(request)
        fail_fast = acquisition.resolve_auto_batch_fail_fast(request)
        reason = (
            "target_delivery_readback_required"
            if any(
                row.observation.state == "unknown"
                and row.observation.provider_state == "delivered"
                for row in delivery_rows if row.execution_state == "attempted"
            )
            else "provider_readback_pending" if pending_delivery else "provider_cancelled"
        )
        raw_meta: CollectJsonObject = {
            "links": list(links),
            "outcome": "OutcomeUnknown" if pending_delivery else "Cancelled",
            "reason": reason,
            "batch_parallelism": policy.max_parallelism,
            "batch_parallelism_requested": requested_parallelism,
            "batch_fail_fast": fail_fast,
            "delivery_observations": [row.to_plain() for row in delivery_rows],
            "typed_batch_results": [item.to_plain() for item in ordered_outcomes],
        }
        raw_meta.update(counts)
        if cancellation is not None:
            raw_meta["cancellation_receipt"] = cancellation.to_plain()
        return CollectResult(
            flow=request.flow,
            channel=request.channel,
            status=state,
            inserted=counts["inserted"],
            updated=counts["updated"],
            skipped=counts["skipped"],
            meta={
                "batch_parallelism": policy.max_parallelism,
                "batch_parallelism_requested": requested_parallelism,
                "batch_fail_fast": fail_fast,
                "raw": raw_meta,
            },
        )
    sequence = acquisition.OrderedCollectElementOutcomeSequence(
        schema_version=acquisition.ORDERED_OUTCOME_SEQUENCE_SCHEMA_REF,
        parent_request_ref=plan.request_ref,
        outcomes=ordered_outcomes,
        sequence_digest="",
    )
    aggregate = acquisition.fold_ordered_results(
        sequence,
        aggregation_policy_ref=acquisition.COLLECT_AGGREGATION_POLICY_ACCUMULATE_REF,
        observation_profile_ref=acquisition.COLLECT_FOLD_OBSERVATION_PROFILE,
    )

    result = _project_collect_aggregate(
        request,
        aggregate,
        sequence,
        plan,
        cancellation=(cancellation if cancelled else None),
    )
    delivery_plain: list[CollectJsonValue] = [row.to_plain() for row in delivery_rows]
    result.meta["delivery_observations"] = delivery_plain
    result_raw = result.meta["raw"]
    assert isinstance(result_raw, dict)
    result_raw["delivery_observations"] = delivery_plain
    from .display_meta import build_display_meta

    summary = request.source_context.get("summary")
    result.display_meta = build_display_meta(request, result, summary=(summary if isinstance(summary, str) else None))
    return result


def _run_collect_no_batch(request: CollectRequest) -> CollectResult:
    if _successor_effect_gateway is None:
        return _attach_delivery_observation(_outcome_unknown_result(request))
    return _attach_delivery_observation(_successor_effect_gateway(request))


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def normalize_query_terms(value: object) -> list[str]:
    if value is None:
        return []
    if _is_object_list(value):
        return [str(x).strip() for x in value if str(x).strip()]
    s = str(value).strip()
    return [s] if s else []


def normalize_urls(value: object) -> list[str]:
    if not _is_object_list(value):
        return []
    out: list[str] = []
    for x in value:
        s = str(x or "").strip()
        if s.startswith(("http://", "https://")):
            out.append(s)
    return out


def normalize_limit(value: object, default: int | None = None) -> int | None:
    if value is None:
        return default
    if isinstance(value, memoryview):
        value = value.tobytes()
    if not isinstance(value, (str, bytes, bytearray, SupportsInt, SupportsIndex)):
        return default
    try:
        return max(1, int(value))
    except Exception:
        return default


def normalize_language(value: object) -> str | None:
    s = str(value or "").strip().lower()
    return s or None


def normalize_provider(value: object) -> str | None:
    s = str(value or "").strip().lower()
    return s or None


def _optional_text(value: CollectJsonValue) -> str | None:
    return None if value is None else str(value)


def collect_request_from_market_api(*, query_terms: list[str], max_items: int, project_key: str | None, provider: str | None = None, language: str | None = None, start_offset: int | None = None, days_back: int | None = None, enable_extraction: bool = True) -> CollectRequest:
    return CollectRequest(
        channel="search.market",
        project_key=project_key,
        query_terms=normalize_query_terms(query_terms),
        limit=normalize_limit(max_items, 20),
        provider=normalize_provider(provider),
        language=normalize_language(language) or "en",
        options={"start_offset": start_offset, "days_back": days_back, "enable_extraction": enable_extraction},
        source_context={"summary": "市场信息采集"},
    )


def collect_request_from_policy_api(*, query_terms: list[str], max_items: int, project_key: str | None, provider: str | None = None, language: str | None = None, start_offset: int | None = None, days_back: int | None = None, enable_extraction: bool = True) -> CollectRequest:
    return CollectRequest(
        channel="search.policy",
        project_key=project_key,
        query_terms=normalize_query_terms(query_terms),
        limit=normalize_limit(max_items, 20),
        provider=normalize_provider(provider),
        language=normalize_language(language) or "en",
        options={"start_offset": start_offset, "days_back": days_back, "enable_extraction": enable_extraction},
        source_context={"summary": "法规来源"},
    )


def collect_request_from_source_library_api(
    *,
    item_key: str,
    project_key: str | None,
    override_params: CollectJsonObject | None = None,
) -> CollectRequest:
    parsed: CollectJsonObject = parse_source_library_runtime_params(override_params)
    platforms = parsed.get("platforms")
    return CollectRequest(
        flow=FLOW_SOURCE_COLLECT,
        channel="source_library",
        project_key=project_key,
        item_key=str(item_key or "").strip() or None,
        query_terms=normalize_query_terms(parsed.get("query_terms")),
        urls=normalize_urls(parsed.get("urls")),
        limit=normalize_limit(parsed.get("limit")),
        provider=normalize_provider(parsed.get("provider")),
        language=normalize_language(parsed.get("language")),
        scope=_optional_text(parsed.get("scope")),
        platforms=(normalize_query_terms(platforms) if platforms is not None else None),
        options={"override_params": dict(_json_object(parsed.get("override_params")))},
        source_context={"summary": f"执行来源项 {item_key}"},
    )


def collect_request_from_url_pool(
    *,
    project_key: str | None,
    urls: list[str] | None = None,
    scope: str | None = None,
    limit: int | None = None,
    source_filter: str | None = None,
    domain: str | None = None,
    query_terms: list[str] | None = None,
    options: CollectJsonObject | None = None,
) -> CollectRequest:
    extra_options = dict(options or {})
    if source_filter is not None:
        extra_options["source_filter"] = source_filter
    if domain is not None:
        extra_options["domain"] = domain
    return CollectRequest(
        channel="url_pool",
        project_key=project_key,
        urls=normalize_urls(urls or []),
        query_terms=normalize_query_terms(query_terms or []),
        scope=(str(scope).strip() if scope else None),
        limit=normalize_limit(limit, 50),
        options=extra_options,
        source_context={"summary": "URL 池抓取并写入文档"},
    )


def run_source_library_item_compat(
    *,
    item_key: str,
    project_key: str | None = None,
    override_params: CollectJsonObject | None = None,
) -> SourceLibraryCompatResponse:
    request = collect_request_from_source_library_api(
        item_key=item_key,
        project_key=project_key,
        override_params=override_params,
    )
    result = run_collect(request)
    if _source_library_compat_projector is None:
        # kit:boundary owner=collect.runtime.compat_projector class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w03_collect_programmer_defect_boundary
        raise RuntimeError("source-library compatibility projector is not configured")
    response = _source_library_compat_projector(result)
    response.setdefault("display_meta", result.display_meta)
    return response
