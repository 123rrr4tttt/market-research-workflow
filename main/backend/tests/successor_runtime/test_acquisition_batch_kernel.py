"""Domain-kernel witnesses for ordered acquisition plans and result folds."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.successor_runtime.capabilities import acquisition_batch as acquisition
from app.services.collect_runtime.contracts import (
    CollectBatchCounts,
    CollectBatchFold,
    CollectBatchRow,
    CollectFailure,
    fold_collect_batch_rows,
)

pytestmark = pytest.mark.unit


def _request_ref() -> acquisition.CollectRequestRef:
    return acquisition.build_collect_request_ref(
        request_id="request:acquisition-kernel",
        project_key="project:acquisition-kernel",
        channel="search.market",
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


def _row(
    index: int,
    *,
    inserted: int = 1,
    links: tuple[str, ...] = (),
    receipt: acquisition.CollectAttemptReceipt | None = None,
    message: str | None = None,
) -> CollectBatchRow:
    errors: tuple[CollectFailure, ...] = ()
    if message is not None:
        errors = ({"code": "auto_batch_execution_failed", "message": message},)
    return CollectBatchRow(
        element_id=f"element:{index}",
        input_index=index,
        query_terms=(),
        observation=None,
        counts=CollectBatchCounts(inserted=0 if message is not None else inserted),
        links=links,
        errors=errors,
        receipt=receipt,
        result_status="failed" if message is not None else "succeeded",
        execution_state="attempted",
    )


def _fold(*rows: CollectBatchRow) -> CollectBatchFold:
    return fold_collect_batch_rows(
        rows,
        request_ref=_request_ref(),
    )


def test_acquisition_batch_rules_preserve_order_limits_and_options() -> None:
    request = SimpleNamespace(
        channel="search.market",
        query_terms=["a1", "a2", "a3", "a4", "b1", "b2", "b3", "b4"],
        limit=80,
        options={"batch_parallelism": 8, "batch_fail_fast": True},
        source_context={"batch_parallelism": 2},
    )
    assert acquisition.should_auto_batch(request)
    batches = acquisition.split_query_terms(request.query_terms)
    assert batches == [["a1", "a2", "a3", "a4"], ["b1", "b2", "b3", "b4"]]
    assert acquisition.per_batch_limit_for(request.limit, len(batches)) == 40
    assert acquisition.resolve_auto_batch_parallelism(request) == 8
    assert acquisition.resolve_auto_batch_fail_fast(request) is True


def test_acquisition_batch_rules_use_safe_defaults_for_invalid_options() -> None:
    request = SimpleNamespace(
        channel="search.market", query_terms=["a"] * 6, limit="bad",
        options={"batch_parallelism": []}, source_context={"batch_fail_fast": "off"},
    )
    assert acquisition.per_batch_limit_for(request.limit, 2) == 10
    assert acquisition.resolve_auto_batch_parallelism(request) == 1
    assert acquisition.resolve_auto_batch_fail_fast(request) is False


def test_acquisition_fold_preserves_order_counts_errors_links_and_receipts() -> None:
    queued = _receipt("job-1")
    folded = _fold(
        _row(0, inserted=2, links=("https://a", "https://b"), receipt=queued),
        _row(1, message="second batch failed"),
        _row(2, inserted=3, links=("https://b", "https://c")),
    )
    assert [row.input_index for row in folded.rows] == [0, 1, 2]
    assert folded.counts.inserted == 5
    assert [error["message"] for error in folded.errors] == ["second batch failed"]
    assert folded.links == ("https://a", "https://b", "https://c")
    assert folded.receipts == (queued,)
    assert folded.failed_count == 1
    assert acquisition.receipt_implies_completed(queued) is False


def test_acquisition_fold_deduplicates_identical_receipts_and_rejects_drift() -> None:
    first = _receipt("job-same")
    identical = _receipt("job-same")
    accepted = _fold(_row(0, receipt=first), _row(1, receipt=identical))
    assert accepted.receipts == (first,)
    assert accepted.receipt_conflict is False

    divergent = _receipt("job-same", raw_digest="1" * 64)
    rejected = _fold(_row(0, receipt=first), _row(1, receipt=divergent))
    assert rejected.receipt_conflict is True


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
