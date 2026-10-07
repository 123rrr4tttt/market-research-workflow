"""Domain-kernel witnesses for ordered acquisition plans and result folds."""

from __future__ import annotations

from dataclasses import replace

import pytest
from functorial_kit import Failure

from app.successor_runtime.capabilities import acquisition_batch as acquisition

pytestmark = pytest.mark.unit


def _request_ref() -> acquisition.CollectRequestRef:
    return acquisition.build_collect_request_ref(
        request_id="request:acquisition-kernel",
        project_key="project:acquisition-kernel",
        channel="search.market",
    )


def _snapshot(*, options: dict[str, object] | None = None) -> acquisition.CollectLegacyRequestSnapshot:
    return acquisition.CollectLegacyRequestSnapshot(
        schema_version=acquisition.COLLECT_REQUEST_SNAPSHOT_SCHEMA_REF,
        flow="collect",
        channel="search.market",
        project_key="project:acquisition-kernel",
        query_terms=("a1", "a2", "a3", "a4", "b1", "b2", "b3", "b4"),
        urls=(),
        limit=80,
        options=acquisition.freeze_json_object(dict(options or {})),
        source_context=acquisition.freeze_json_object({}),
        snapshot_digest="",
    )


def _policy() -> acquisition.CollectResourcePolicy:
    return acquisition.CollectResourcePolicy(
        schema_ref=acquisition.COLLECT_RESOURCE_POLICY_SCHEMA_REF,
        max_parallelism=2,
        deadline_seconds=60,
        cancellation="COORDINATED",
        backpressure=True,
        provider_concurrency_key="search.market",
        policy_digest="",
    )


def _plan(*, options: dict[str, object] | None = None) -> acquisition.CollectBatchPlan:
    return acquisition.build_collect_batch_plan(
        request_ref=_request_ref(),
        snapshot=_snapshot(options=options),
        plan_id="plan:acquisition-kernel",
        resource_policy=_policy(),
        authority_scope_ref="project:acquisition-kernel",
    )


def _receipt(job_id: str, *, raw_digest: str = "0" * 64) -> acquisition.CollectAttemptReceipt:
    return acquisition.CollectAttemptReceipt(
        schema_version=acquisition.COLLECT_ATTEMPT_RECEIPT_SCHEMA_REF,
        receipt_kind="DISPATCH_ACKNOWLEDGEMENT",
        provider_type="search.market",
        provider_job_id=job_id,
        provider_status="queued",
        attempt_count=1,
        observed_at="2026-10-07T00:00:00Z",
        raw_digest=raw_digest,
        authoritative_readback=False,
        receipt_digest="",
    )


def _succeeded(
    index: int,
    *,
    inserted: int = 1,
    links: tuple[str, ...] = (),
    receipt: acquisition.CollectAttemptReceipt | None = None,
) -> acquisition.CollectElementSucceeded:
    return acquisition.CollectElementSucceeded(
        schema_version=acquisition.COLLECT_ELEMENT_OUTCOME_SCHEMA_REF,
        element_id=f"element:{index}",
        input_index=index,
        counts=acquisition.CollectCounts(inserted=inserted),
        links=links,
        receipt=receipt,
        legacy_observation_ref="legacy:" + f"{index:064x}",
        outcome_digest="",
    )


def _failed(index: int, message: str) -> acquisition.CollectElementFailed:
    return acquisition.CollectElementFailed(
        schema_version=acquisition.COLLECT_ELEMENT_OUTCOME_SCHEMA_REF,
        element_id=f"element:{index}",
        input_index=index,
        error=acquisition.CollectElementError(
            code="auto_batch_execution_failed",
            message=message,
            error_digest="",
        ),
        legacy_observation_ref="legacy:" + f"{index + 100:064x}",
        outcome_digest="",
    )


def _fold(*outcomes: acquisition.CollectElementOutcome) -> acquisition.CollectAggregateOutcome:
    sequence = acquisition.OrderedCollectElementOutcomeSequence(
        schema_version=acquisition.ORDERED_OUTCOME_SEQUENCE_SCHEMA_REF,
        parent_request_ref=_request_ref(),
        outcomes=outcomes,
        sequence_digest="",
    )
    return acquisition.fold_ordered_results(
        sequence,
        aggregation_policy_ref=acquisition.COLLECT_AGGREGATION_POLICY_ACCUMULATE_REF,
        observation_profile_ref=acquisition.COLLECT_FOLD_OBSERVATION_PROFILE,
    )


def test_acquisition_plan_is_ordered_and_resource_bounded() -> None:
    plan = _plan(options={"batch_parallelism": 8})
    assert [element.input_index for element in plan.elements] == [0, 1]
    assert [element.query_terms for element in plan.elements] == [
        ("a1", "a2", "a3", "a4"),
        ("b1", "b2", "b3", "b4"),
    ]
    assert plan.requested_parallelism == 8
    assert plan.effective_parallelism == 2
    assert plan.per_batch_limit == 40


def test_acquisition_plan_rejects_order_and_shape_drift() -> None:
    plan = _plan()
    with pytest.raises(ValueError, match="contiguous"):
        replace(plan, elements=(plan.elements[1], plan.elements[0]))

    malformed = replace(
        plan.elements[0],
        traversal_policy="STATIC_SHAPE",
        query_terms=("different",),
        element_digest="",
    )
    result = acquisition.try_build_collect_batch_plan(
        request_ref=_request_ref(),
        snapshot=_snapshot(),
        plan_id="plan:acquisition-kernel",
        resource_policy=_policy(),
        authority_scope_ref="project:acquisition-kernel",
        traversal_policy="STATIC_SHAPE",
        static_elements=(malformed,),
    )
    assert isinstance(result, Failure)
    assert result.code == "INVALID_INPUT"


def test_acquisition_fold_preserves_order_counts_errors_links_and_receipts() -> None:
    queued = _receipt("job-1")
    aggregate = _fold(
        _succeeded(0, inserted=2, links=("https://a", "https://b"), receipt=queued),
        _failed(1, "second batch failed"),
        _succeeded(2, inserted=3, links=("https://b", "https://c")),
    )
    assert isinstance(aggregate, acquisition.CollectAggregatePartial)
    assert [outcome.input_index for outcome in aggregate.ordered_outcomes.outcomes] == [0, 1, 2]
    assert aggregate.aggregate_counts.inserted == 5
    assert [error.message for error in aggregate.errors] == ["second batch failed"]
    assert aggregate.links == ("https://a", "https://b", "https://c")
    assert aggregate.receipts == (queued,)
    assert acquisition.receipt_implies_completed(queued) is False


def test_acquisition_fold_deduplicates_identical_receipts_and_rejects_drift() -> None:
    first = _receipt("job-same")
    identical = _receipt("job-same")
    accepted = _fold(_succeeded(0, receipt=first), _succeeded(1, receipt=identical))
    assert isinstance(accepted, acquisition.CollectAggregateSucceeded)
    assert accepted.receipts == (first,)

    divergent = _receipt("job-same", raw_digest="1" * 64)
    rejected = _fold(_succeeded(0, receipt=first), _succeeded(1, receipt=divergent))
    assert isinstance(rejected, acquisition.CollectFoldContractFailure)
    assert "duplicate provider_job_id" in rejected.reason


def test_acquisition_contract_failures_use_canonical_value() -> None:
    failure = acquisition.collect_contract_failure(
        code="INVALID_INPUT",
        reason_code="schema_contract_invalid",
        message="exact rejection",
        operation="collect.test",
        site="test",
        domain_outcome="INVALID_INPUT",
    )
    assert acquisition.ACQUISITION_BATCH_FAILURES.matches(failure)
    assert failure.context is not None
    assert failure.context["witness"] == (
        "test:test_acquisition_contract_failures_use_canonical_value"
    )


def test_acquisition_compatibility_lift_preserves_exception_abi() -> None:
    failure = acquisition.collect_contract_failure(
        code="INVALID_INPUT",
        message="public rejection",
        operation="collect.test",
        site="test",
        domain_outcome="INVALID_INPUT",
    )
    with pytest.raises(ValueError, match="public rejection"):
        acquisition.raise_collect_contract_failure(failure, ValueError)


def test_acquisition_programmer_defect_lift_preserves_exception_abi() -> None:
    with pytest.raises(RuntimeError, match="internal invariant"):
        acquisition.raise_collect_programmer_defect("internal invariant", RuntimeError)
