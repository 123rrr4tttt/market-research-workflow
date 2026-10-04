from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.ingest.policy import (
    _extraction_readback,
    ingest_policy_documents,
    _policy_materialization_typed_views,
    materialize_policy_documents,
)
from app.services.ingest.provider_ports import PolicyDocument
from app.successor_runtime.capabilities import acquisition_batch as acquisition


def _doc(index: int) -> PolicyDocument:
    return PolicyDocument(
        state="CA",
        title=f"Policy {index}",
        status="published",
        publish_date=None,
        summary=f"Summary {index}",
        content=f"Policy body {index}",
        uri=f"https://example.test/policy/{index}",
        source_name="fixture",
    )


def test_policy_materialization_is_bounded_ordered_and_replayable() -> None:
    consumed: list[int] = []

    def source():
        for index in range(5):
            consumed.append(index)
            yield _doc(index)

    documents, traversal = materialize_policy_documents(
        source(), state="CA", max_documents=2
    )
    assert [document.title for document in documents] == ["Policy 0", "Policy 1"]
    assert consumed == [0, 1]
    assert isinstance(traversal, acquisition.OrderedTraversalCompleted)
    outcomes = traversal.observation.ordered_outcomes
    assert [outcome.input_index for outcome in outcomes] == [0, 1]
    assert all(outcome.receipt is not None for outcome in outcomes)
    assert outcomes[0].receipt.authoritative_readback is False
    assert outcomes[0].legacy_observation_ref.startswith("legacy:")
    assert outcomes[0].legacy_observation_ref != outcomes[1].legacy_observation_ref

    sequence, aggregate = _policy_materialization_typed_views(traversal, state="CA")
    assert sequence.sequence_digest
    assert isinstance(aggregate, acquisition.CollectAggregateSucceeded)
    assert aggregate.receipts[0].provider_job_id == outcomes[0].receipt.provider_job_id


def test_policy_materialization_cancellation_is_typed_and_partial() -> None:
    documents, traversal = materialize_policy_documents(
        (_doc(index) for index in range(4)),
        state="CA",
        cancel_check=lambda index: index == 2,
    )
    assert len(documents) == 2
    assert isinstance(traversal, acquisition.OrderedTraversalAborted)
    assert traversal.cancellation_observed is True
    assert traversal.cancellation_receipt is not None
    assert traversal.cancellation_receipt.trigger_input_index == 2
    assert [outcome.input_index for outcome in traversal.partial_outcomes] == [0, 1]


def test_policy_materialization_invalid_item_is_typed_failure() -> None:
    documents, traversal = materialize_policy_documents(
        [SimpleNamespace(state="CA", title="bad")], state="CA"
    )
    assert documents == []
    assert isinstance(traversal, (acquisition.OrderedTraversalCompleted, acquisition.CollectTraversalSingleton))
    observation = getattr(traversal, "observation")
    assert isinstance(observation.ordered_outcomes[0], acquisition.CollectElementFailed)
    assert observation.ordered_outcomes[0].error is not None


def test_policy_materialization_records_provider_next_failure_after_partial_prefix() -> None:
    class ProviderFailure(RuntimeError):
        pass

    def source():
        yield _doc(0)
        yield _doc(1)
        raise ProviderFailure("provider next failed")

    iteration_errors: list[BaseException] = []
    documents, traversal = materialize_policy_documents(
        source(), state="CA", _iteration_error_out=iteration_errors
    )

    assert [document.title for document in documents] == ["Policy 0", "Policy 1"]
    assert len(iteration_errors) == 1
    assert isinstance(iteration_errors[0], ProviderFailure)
    assert str(iteration_errors[0]) == "provider next failed"
    assert isinstance(traversal, acquisition.OrderedTraversalCompleted)
    outcomes = traversal.observation.ordered_outcomes
    assert [outcome.input_index for outcome in outcomes] == [0, 1, 2]
    assert isinstance(outcomes[-1], acquisition.CollectElementFailed)
    assert outcomes[-1].error is not None
    assert outcomes[-1].error.exception_type == "ProviderFailure"
    assert outcomes[-1].error.message == "provider next failed"


def test_policy_ingest_reraises_provider_next_failure_before_start_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Adapter:
        @staticmethod
        def fetch_documents():
            yield _doc(0)
            yield _doc(1)
            raise RuntimeError("provider next failed")

    start_calls: list[object] = []
    monkeypatch.setattr("app.services.ingest.policy.get_policy_adapter", lambda *_args: _Adapter())
    monkeypatch.setattr(
        "app.services.ingest.policy.start_job",
        lambda *_args, **_kwargs: start_calls.append(True),
    )

    with pytest.raises(RuntimeError, match="provider next failed"):
        ingest_policy_documents("CA")
    assert start_calls == []


def test_policy_extraction_readback_distinguishes_skip_success_and_failure() -> None:
    skipped = _extraction_readback(requested=False, outcome=None)
    assert skipped["status"] == "SKIPPED_NOT_REQUESTED"
    assert skipped["readback_digest"]

    succeeded = _extraction_readback(
        requested=True,
        outcome={"status": "ok", "domains": {"policy": {"effective_date": "2026-01-01"}}},
    )
    assert succeeded["status"] == "SUCCEEDED"
    assert succeeded["domains"]["policy"]["effective_date"] == "2026-01-01"
    assert succeeded["readback_digest"]

    failed = _extraction_readback(
        requested=True,
        outcome={"status": "failed", "reason": "extractor_exception", "error": "boom"},
    )
    assert failed["status"] == "FAILED"
    assert failed["status"] != "SUCCEEDED"
    assert failed["readback_digest"]
