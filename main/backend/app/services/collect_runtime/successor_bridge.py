"""Typed C3 bridge for successor collect runtime observations.

This module contains only construction/projection helpers. Provider effects are
injected by ``runtime.register_successor_collect_effect_gateway`` and never
resolved from the legacy adapter registry here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from app.successor_runtime.capabilities.acquisition_batch import (
        CollectAggregateFailed,
        CollectAggregatePartial,
        CollectAggregateSucceeded,
        CollectAttemptReceipt,
        CollectBatchPlan,
        CollectCounts,
        CollectElementError,
        CollectFoldContractFailure,
        OrderedCollectElementOutcomeSequence,
    )

from .contracts import CollectFailure, CollectRequest, CollectResult
from .contracts import CollectJsonObject, CollectJsonValue


class _CancellationReceipt(Protocol):
    def to_plain(self) -> dict[str, Any]:
        ...



def outcome_unknown_result(request: CollectRequest) -> CollectResult:
    """Fail closed when no successor effect gateway/readback journal is bound."""

    unavailable_failure: CollectFailure = {
        "code": "successor_effect_gateway_unavailable",
        "message": "successor collect requires an explicit effect gateway",
    }
    result = CollectResult(
        flow=request.flow,
        channel=request.channel,
        status="unknown",
        errors=[unavailable_failure],
        meta={
            "raw": {
                "successor_interpreter": (
                    "mrw.acquisition.batch.fold_ordered_results.interpreter.v2"
                ),
                "outcome": "OutcomeUnknown",
                "reason": "effect_gateway_unavailable",
            }
        },
    )
    from .display_meta import build_display_meta

    result.display_meta = build_display_meta(request, result)
    return result


def project_successor_aggregate(
    request: CollectRequest,
    aggregate: (
        CollectAggregateSucceeded
        | CollectAggregatePartial
        | CollectAggregateFailed
        | CollectFoldContractFailure
    ),
    sequence: OrderedCollectElementOutcomeSequence,
    plan: CollectBatchPlan,
    c3: object,
    *,
    cancellation: _CancellationReceipt | None = None,
) -> CollectResult:
    """Project one typed C3 aggregate to the retained legacy result envelope."""

    from app.successor_runtime.capabilities.acquisition_batch import (
        CollectAggregateFailed,
        CollectAggregatePartial,
        CollectAggregateSucceeded,
        CollectElementFailed,
        receipt_implies_completed,
    )

    counts: CollectCounts | None = None
    receipts: tuple[CollectAttemptReceipt, ...] = ()
    links: tuple[str, ...] = ()
    element_errors: tuple[CollectElementError, ...] = ()
    if isinstance(aggregate, (CollectAggregateSucceeded, CollectAggregatePartial, CollectAggregateFailed)):
        counts = aggregate.aggregate_counts
        receipts = aggregate.receipts
        links = aggregate.links
    if isinstance(aggregate, (CollectAggregatePartial, CollectAggregateFailed)):
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
        "batch_independence_policy_explicit": bool(
            getattr(plan, "effective_parallelism", 1) > 1
        ),
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
                if isinstance(outcome, CollectElementFailed) and outcome.error is not None
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
                    if isinstance(outcome, CollectElementFailed) and outcome.error is not None
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

    kind = aggregate.kind
    terminal_receipts = bool(receipts) and all(receipt_implies_completed(receipt) for receipt in receipts)
    if cancellation is not None:
        status = "cancelled"
    elif kind == "succeeded" and terminal_receipts:
        status = "completed"
    elif kind == "succeeded":
        status = "accepted"
    elif kind == "partial":
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
            "successor_interpreter": (
                "mrw.acquisition.batch.fold_ordered_results.interpreter.v2"
            ),
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



__all__ = ["outcome_unknown_result", "project_successor_aggregate"]
