"""Typed C3 bridge for successor collect runtime observations.

This module contains only construction/projection helpers. Provider effects are
injected by ``runtime.register_successor_collect_effect_gateway`` and never
resolved from the legacy adapter registry here.
"""

from __future__ import annotations

from typing import Any

from .contracts import CollectRequest, CollectResult


def outcome_unknown_result(request: CollectRequest) -> CollectResult:
    """Fail closed when no successor effect gateway/readback journal is bound."""

    result = CollectResult(
        flow=request.flow,
        channel=request.channel,
        status="unknown",
        errors=[
            {
                "code": "successor_effect_gateway_unavailable",
                "message": "successor collect requires an explicit effect gateway",
            }
        ],
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
    aggregate: Any,
    sequence: Any,
    plan: Any,
    c3: Any,
    *,
    cancellation: Any | None = None,
) -> CollectResult:
    """Project one typed C3 aggregate to the retained legacy result envelope."""

    counts = getattr(aggregate, "aggregate_counts", None)
    raw: dict[str, Any] = {
        "inserted": 0 if counts is None else counts.inserted,
        "updated": 0 if counts is None else counts.updated,
        "skipped": 0 if counts is None else counts.skipped,
        "auto_batched": True,
        "batches_total": len(plan.elements),
        "batch_parallelism": plan.effective_parallelism,
        "batch_parallelism_requested": plan.requested_parallelism,
        "batch_independence_policy_explicit": bool(
            getattr(plan, "effective_parallelism", 1) > 1
        ),
        "batch_results": [],
        "typed_batch_results": [outcome.to_plain() for outcome in sequence.outcomes],
        "ordered_outcomes": sequence.to_plain(),
        "aggregate": aggregate.to_plain(),
        "aggregate_kind": getattr(aggregate, "kind", "failed"),
    }
    for outcome in sequence.outcomes:
        item = {
            "query_terms": list(
                plan.elements[outcome.input_index].query_terms
                if 0 <= outcome.input_index < len(plan.elements)
                else getattr(getattr(outcome, "error", None), "query_terms", ())
            ),
            "result": {
                "status": getattr(outcome, "status", "failed"),
                "inserted": outcome.counts.inserted,
                "updated": outcome.counts.updated,
                "skipped": outcome.counts.skipped,
                "errors": (
                    [outcome.error.to_plain()]
                    if isinstance(outcome, c3.CollectElementFailed)
                    and outcome.error is not None
                    else []
                ),
                "links": list(outcome.links),
            },
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
        raw["batch_results"].append(item)
    if cancellation is not None:
        raw["cancellation_receipt"] = cancellation.to_plain()
    receipts = tuple(getattr(aggregate, "receipts", ()) or ())
    if receipts:
        raw["receipts"] = [receipt.to_plain() for receipt in receipts]
        raw["provider_job_ids"] = [receipt.provider_job_id for receipt in receipts]
    links = tuple(getattr(aggregate, "links", ()) or ())
    if links:
        raw["links"] = list(links)
    errors = [error.to_plain() for error in (getattr(aggregate, "errors", ()) or ())]

    kind = getattr(aggregate, "kind", "failed")
    terminal_receipts = bool(receipts) and all(
        c3.receipt_implies_completed(receipt) for receipt in receipts
    )
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
        inserted=raw["inserted"],
        updated=raw["updated"],
        skipped=raw["skipped"],
        errors=errors,
        meta={
            "raw": raw,
            "c3_aggregate": aggregate,
            "ordered_outcomes": sequence,
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
