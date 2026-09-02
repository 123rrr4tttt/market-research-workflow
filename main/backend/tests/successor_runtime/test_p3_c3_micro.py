"""P3 C3 micro semantics: ordered fold, receipts, fail-fast and parallelism."""

from __future__ import annotations

import threading
import time

import pytest

from app.successor_runtime.capabilities import collect_c3 as c3
from app.successor_runtime.capabilities import collect_c3_interpreters as ci

from .test_p3_c3_contracts import _plan, _request_ref

pytestmark = pytest.mark.unit


def _receipt(
    *,
    job_id: str,
    kind: str,
    status: str | None = None,
    attempt_count: int = 1,
    raw: str | None = None,
) -> c3.CollectAttemptReceipt:
    authoritative = kind == "AUTHORITATIVE_READBACK"
    return c3.CollectAttemptReceipt(
        schema_version=c3.COLLECT_ATTEMPT_RECEIPT_SCHEMA_REF,
        receipt_kind=kind,
        provider_type="search.market",
        provider_job_id=job_id,
        provider_status=status,
        attempt_count=attempt_count,
        observed_at="2026-09-01T00:00:00Z",
        raw_digest=raw or "0" * 64,
        authoritative_readback=authoritative,
        receipt_digest="",
    )


def _succeeded(
    index: int,
    *,
    inserted: int = 1,
    links: tuple[str, ...] = (),
    receipt: c3.CollectAttemptReceipt | None = None,
) -> c3.CollectElementSucceeded:
    return c3.CollectElementSucceeded(
        schema_version=c3.COLLECT_ELEMENT_OUTCOME_SCHEMA_REF,
        element_id=f"e{index}",
        input_index=index,
        counts=c3.CollectCounts(inserted=inserted),
        links=links,
        receipt=receipt,
        legacy_observation_ref="legacy:" + f"{index:064x}",
        outcome_digest="",
    )


def _failed(
    index: int,
    *,
    message: str = "boom",
    terms: tuple[str, ...] = (),
) -> c3.CollectElementFailed:
    return c3.CollectElementFailed(
        schema_version=c3.COLLECT_ELEMENT_OUTCOME_SCHEMA_REF,
        element_id=f"e{index}",
        input_index=index,
        error=c3.CollectElementError(
            code="auto_batch_execution_failed",
            message=message,
            query_terms=terms,
            error_digest="",
        ),
        counts=c3.CollectCounts(),
        links=(),
        receipt=None,
        legacy_observation_ref="legacy:" + f"{index + 100:064x}",
        outcome_digest="",
    )


def _sequence(
    *outcomes: c3.CollectElementOutcome,
) -> c3.OrderedCollectElementOutcomeSequence:
    return c3.OrderedCollectElementOutcomeSequence(
        schema_version="mrw.successor.collect.c3.outcome-sequence.v1",
        parent_request_ref=_request_ref(),
        outcomes=outcomes,
        sequence_digest="",
    )


def _aggregate(
    outcomes: c3.OrderedCollectElementOutcomeSequence,
) -> c3.CollectAggregateOutcome:
    return c3.fold_ordered_results(
        outcomes,
        aggregation_policy_ref=c3.COLLECT_AGGREGATION_POLICY_ACCUMULATE_REF,
        observation_profile_ref=c3.COLLECT_FOLD_OBSERVATION_PROFILE,
    )


def test_ordered_fold_singleton_identity() -> None:
    outcome = _succeeded(0, inserted=4, links=("https://a",))
    aggregate = _aggregate(_sequence(outcome))
    assert isinstance(aggregate, c3.CollectAggregateSucceeded)
    assert aggregate.aggregate_counts.to_plain() == {
        "inserted": 4,
        "updated": 0,
        "skipped": 0,
    }
    assert aggregate.links == ("https://a",)
    assert (
        aggregate.ordered_outcomes.sequence_digest == _sequence(outcome).sequence_digest
    )


def test_mixed_outcomes_are_partial_and_preserve_successful_siblings() -> None:
    first = _succeeded(0, inserted=2, links=("https://a",))
    second = _failed(1, message="batch exploded", terms=("t5",))
    third = _succeeded(2, inserted=3, links=("https://b",))
    aggregate = _aggregate(_sequence(first, second, third))
    assert isinstance(aggregate, c3.CollectAggregatePartial)
    assert aggregate.aggregate_counts.inserted == 5
    assert len(aggregate.errors) == 1
    assert aggregate.errors[0].message == "batch exploded"
    assert aggregate.errors[0].query_terms == ("t5",)


def test_all_failed_aggregate_preserves_error_order() -> None:
    first = _failed(0, message="first")
    second = _failed(1, message="second")
    aggregate = _aggregate(_sequence(first, second))
    assert isinstance(aggregate, c3.CollectAggregateFailed)
    assert [error.message for error in aggregate.errors] == ["first", "second"]
    assert aggregate.aggregate_counts.to_plain() == {
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
    }


def test_error_and_receipt_no_loss_with_stable_first_dedupe() -> None:
    queued = _receipt(
        job_id="job-1",
        kind="DISPATCH_ACKNOWLEDGEMENT",
        status="queued",
    )
    readback = _receipt(
        job_id="job-2",
        kind="AUTHORITATIVE_READBACK",
        status="completed",
        raw="1" * 64,
    )
    first = _succeeded(0, links=("https://a", "https://b"), receipt=queued)
    second = _failed(1)
    third = _succeeded(
        2,
        inserted=1,
        links=("https://b", "https://c"),
        receipt=readback,
    )
    aggregate = _aggregate(_sequence(first, second, third))
    assert isinstance(aggregate, c3.CollectAggregatePartial)
    assert aggregate.links == ("https://a", "https://b", "https://c")
    assert [receipt.receipt_kind for receipt in aggregate.receipts] == [
        "DISPATCH_ACKNOWLEDGEMENT",
        "AUTHORITATIVE_READBACK",
    ]
    job_ids = [
        receipt.provider_job_id
        for receipt in aggregate.receipts
        if receipt.provider_job_id is not None
    ]
    assert job_ids == ["job-1", "job-2"]
    assert aggregate.receipts[0].attempt_count == 1


def test_queued_ack_never_implies_completion() -> None:
    queued = _receipt(
        job_id="job-q",
        kind="DISPATCH_ACKNOWLEDGEMENT",
        status="queued",
    )
    assert c3.receipt_implies_completed(queued) is False
    readback = _receipt(
        job_id="job-r",
        kind="AUTHORITATIVE_READBACK",
        status="completed",
        raw="2" * 64,
    )
    assert c3.receipt_implies_completed(readback) is True
    outcome = _succeeded(0, inserted=1, receipt=queued)
    aggregate = _aggregate(_sequence(outcome))
    assert isinstance(aggregate, c3.CollectAggregateSucceeded)
    assert aggregate.receipts[0].authoritative_readback is False
    assert c3.receipt_implies_completed(aggregate.receipts[0]) is False


def test_fold_contract_failure_rejects_non_frozen_policy() -> None:
    outcome = _succeeded(0)
    aggregate = c3.fold_ordered_results(
        _sequence(outcome),
        aggregation_policy_ref="mrw.unknown.policy.v1",
        observation_profile_ref=c3.COLLECT_FOLD_OBSERVATION_PROFILE,
    )
    assert isinstance(aggregate, c3.CollectFoldContractFailure)
    assert (
        aggregate.unconsumed_outcomes.sequence_digest
        == _sequence(outcome).sequence_digest
    )


def test_resource_policy_backpressure_and_parallelism_clamp() -> None:
    plan = _plan(options={"batch_parallelism": 8})
    assert plan.requested_parallelism == 8
    assert plan.effective_parallelism == 2  # resource ceiling wins
    assert plan.elements[0].per_batch_limit == 40


def test_fail_fast_partial_outcomes_and_cancellation_observation() -> None:
    plan = _plan(options={"batch_fail_fast": True})

    class ExplodingRunner:
        def run(self, element: c3.CollectBatchElement) -> c3.CollectElementOutcome:
            if element.input_index == 1:
                raise RuntimeError("second batch exploded")
            return _succeeded(
                element.input_index,
                inserted=len(element.query_terms),
                links=(f"https://example.com/{element.input_index}",),
            )

    result = ci.run_ordered_traversal(plan, ExplodingRunner())
    assert isinstance(result, c3.OrderedTraversalAborted)
    assert result.cancellation_observed is True
    assert result.cancellation_receipt is not None
    assert result.cancellation_receipt.observed == "SERIAL_EXECUTION"
    assert result.cancellation_receipt.trigger_input_index == 1
    assert result.cause.message == "second batch exploded"
    assert [outcome.input_index for outcome in result.partial_outcomes] == [0, 1]
    assert result.partial_outcomes[1].status == "failed"


def test_parallel_fail_fast_preserves_all_executed_outcomes() -> None:
    plan = _plan(options={"batch_parallelism": 2, "batch_fail_fast": True})

    class BarrierRunner:
        def run(self, element: c3.CollectBatchElement) -> c3.CollectElementOutcome:
            if element.input_index == 1:
                raise RuntimeError("first completed failure")
            time.sleep(0.05)
            return _succeeded(
                element.input_index,
                inserted=len(element.query_terms),
            )

    result = ci.run_ordered_traversal(plan, BarrierRunner())
    assert isinstance(result, c3.OrderedTraversalAborted)
    # Later-index outcome executed and completed before the abort is observed.
    assert [outcome.input_index for outcome in result.partial_outcomes] == [0, 1]
    assert result.partial_outcomes[0].status == "succeeded"
    assert result.partial_outcomes[1].status == "failed"
    assert result.cancellation_receipt is not None
    assert result.cancellation_receipt.observed == "PARALLEL_COMPLETION"
    assert result.cancellation_receipt.trigger_input_index == 1


def test_serial_parallel_ordered_observation_with_noncommuting_trace() -> None:
    serial_plan = _plan(options={"batch_parallelism": 1})
    parallel_plan = _plan(options={"batch_parallelism": 2})
    completion_log: list[str] = []
    lock = threading.Lock()

    class SlowRunner:
        def run(self, element: c3.CollectBatchElement) -> c3.CollectElementOutcome:
            if element.input_index == 0:
                time.sleep(0.05)
            with lock:
                completion_log.append(element.element_id)
            return _succeeded(
                element.input_index,
                inserted=len(element.query_terms),
                links=(f"https://example.com/{element.input_index}",),
            )

    serial = ci.run_ordered_traversal(serial_plan, SlowRunner())
    completion_log.clear()
    parallel = ci.run_ordered_traversal(parallel_plan, SlowRunner())

    assert isinstance(serial, c3.OrderedTraversalCompleted)
    assert isinstance(parallel, c3.OrderedTraversalCompleted)
    assert serial.observation.ordered_outcomes == parallel.observation.ordered_outcomes
    assert (
        serial.observation.observation_digest != parallel.observation.observation_digest
    )
    assert parallel.observation.effective_parallelism == 2
    assert completion_log != [element.element_id for element in serial_plan.elements]
    serial_aggregate = _aggregate(_sequence(*serial.observation.ordered_outcomes))
    parallel_aggregate = _aggregate(_sequence(*parallel.observation.ordered_outcomes))
    assert serial_aggregate.aggregate_digest == parallel_aggregate.aggregate_digest


def test_fold_rejects_over_capacity_outcome_count() -> None:
    outcomes = tuple(
        _succeeded(index, inserted=1)
        for index in range(c3.COLLECT_FOLD_RESOURCE_CEILING.max_outcomes + 1)
    )
    aggregate = _aggregate(_sequence(*outcomes))
    assert isinstance(aggregate, c3.CollectFoldContractFailure)
    assert "exceed ceiling" in aggregate.reason


def test_fold_rejects_over_capacity_payload_bytes() -> None:
    huge_link = "https://example.com/" + ("x" * (300 * 1024))
    outcome = _succeeded(0, inserted=1, links=(huge_link,))
    aggregate = _aggregate(_sequence(outcome))
    assert isinstance(aggregate, c3.CollectFoldContractFailure)
    assert "payload bytes" in aggregate.reason


def test_duplicate_receipt_policy_is_explicit_stable_first_or_rejected() -> None:
    first = _receipt(
        job_id="job-same",
        kind="AUTHORITATIVE_READBACK",
        status="completed",
        raw="4" * 64,
    )
    duplicate = _receipt(
        job_id="job-same",
        kind="AUTHORITATIVE_READBACK",
        status="completed",
        raw="4" * 64,
    )
    assert duplicate.receipt_digest == first.receipt_digest
    aggregate = _aggregate(
        _sequence(
            _succeeded(0, receipt=first),
            _succeeded(1, receipt=duplicate),
        )
    )
    assert isinstance(aggregate, c3.CollectAggregateSucceeded)
    assert len(aggregate.receipts) == 1

    divergent = _receipt(
        job_id="job-same",
        kind="AUTHORITATIVE_READBACK",
        status="completed",
        raw="5" * 64,
    )
    rejected = _aggregate(
        _sequence(
            _succeeded(0, receipt=first),
            _succeeded(1, receipt=divergent),
        )
    )
    assert isinstance(rejected, c3.CollectFoldContractFailure)
    assert "duplicate provider_job_id" in rejected.reason
