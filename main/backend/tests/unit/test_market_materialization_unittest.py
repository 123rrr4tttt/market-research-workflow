from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.ingest import market
from app.services.ingest.provider_ports import MarketRecord
from app.successor_runtime.capabilities import collect_c3 as c3


def _record(*, day: int, replay_identity: str | None = None) -> MarketRecord:
    extra = {"replay_identity": replay_identity} if replay_identity else None
    return MarketRecord(state="CA", date=date(2026, 1, day), game="powerball", extra=extra)


def test_market_materialization_preserves_adapter_and_record_order_with_bound() -> None:
    adapters = [
        SimpleNamespace(fetch_records=lambda: iter([_record(day=1), _record(day=2), _record(day=3)])),
        SimpleNamespace(fetch_records=lambda: iter([_record(day=4), _record(day=5)])),
    ]

    records, traversal = market.materialize_market_records(
        adapters, state="ca", max_records_per_adapter=2
    )

    assert [record.date.day for record in records] == [1, 2, 4, 5]
    observation = traversal.observation
    assert observation is not None
    assert traversal.kind == "outcome_unknown"
    assert [outcome.input_index for outcome in observation.ordered_outcomes] == [0, 1, 2, 3]
    assert all(outcome.receipt is not None for outcome in observation.ordered_outcomes)
    assert all(outcome.receipt.authoritative_readback is False for outcome in observation.ordered_outcomes)
    assert all(c3.receipt_implies_completed(outcome.receipt) is False for outcome in observation.ordered_outcomes)
    assert len({outcome.receipt.provider_job_id for outcome in observation.ordered_outcomes}) == 4


def test_market_materialization_replay_identity_is_stable_after_projection() -> None:
    source_record = _record(day=1)
    first_records, first = market.materialize_market_records(
        [SimpleNamespace(fetch_records=lambda: iter([source_record]))], state="CA"
    )
    _second_records, second = market.materialize_market_records(
        [SimpleNamespace(fetch_records=lambda: iter(first_records))], state="CA"
    )

    first_outcome = first.observation.ordered_outcomes[0]
    second_outcome = second.observation.ordered_outcomes[0]
    assert first_outcome.receipt.raw_digest == second_outcome.receipt.raw_digest
    assert first_outcome.receipt.receipt_digest == second_outcome.receipt.receipt_digest


def test_market_materialization_records_iteration_failure_and_continues() -> None:
    def broken():
        yield _record(day=1)
        error_message = "provider iteration failed"
        raise RuntimeError(error_message)

    records, traversal = market.materialize_market_records(
        [SimpleNamespace(fetch_records=broken), SimpleNamespace(fetch_records=lambda: iter([_record(day=2)]))],
        state="CA",
        max_records_per_adapter=4,
    )

    assert [record.date.day for record in records] == [1, 2]
    outcomes = traversal.observation.ordered_outcomes
    assert outcomes[1].status == "failed"
    assert outcomes[1].error.message == "provider iteration failed"
    assert outcomes[2].status == "succeeded"


def test_ingest_market_data_reraises_provider_iteration_before_start_job() -> None:
    def broken():
        error_message = "provider iteration failed"
        raise RuntimeError(error_message)

    with (
        patch.object(
            market,
            "get_market_adapters",
            return_value=[SimpleNamespace(fetch_records=broken)],
        ),
        patch.object(market, "start_job") as start_job,
    ):
        with pytest.raises(RuntimeError, match="^provider iteration failed$"):
            market.ingest_market_data("CA")
    start_job.assert_not_called()


def test_market_materialization_cancellation_returns_typed_abort_and_closes_iterator() -> None:
    closed = []

    def source():
        try:
            yield _record(day=1)
            yield _record(day=2)
        finally:
            closed.append(True)

    records, traversal = market.materialize_market_records(
        [SimpleNamespace(fetch_records=source)],
        state="CA",
        max_records_per_adapter=4,
        cancel_check=lambda index: index >= 1,
    )

    assert [record.date.day for record in records] == [1]
    assert isinstance(traversal, c3.OrderedTraversalAborted)
    assert traversal.cancellation_observed is True
    assert traversal.cancellation_receipt.trigger_input_index == 1
    assert closed == [True]


def test_market_materialization_does_not_call_adapter_after_cancellation() -> None:
    called = []

    def fetch_records():
        called.append(True)
        return iter([_record(day=1)])

    records, traversal = market.materialize_market_records(
        [SimpleNamespace(fetch_records=fetch_records)],
        state="CA",
        cancel_check=lambda _index: True,
    )

    assert records == []
    assert isinstance(traversal, c3.OrderedTraversalAborted)
    assert called == []


def test_ingest_market_data_dedupes_same_replay_identity_before_persistence() -> None:
    duplicate_a = _record(day=1, replay_identity="same-replay")
    duplicate_b = _record(day=2, replay_identity="same-replay")

    class FakeSession:
        def __init__(self) -> None:
            self.added = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def add(self, value):
            self.added.append(value)

        def commit(self):
            return None

        def rollback(self):
            return None

    session = FakeSession()

    with (
        patch.object(
            market,
            "get_market_adapters",
            return_value=[
                SimpleNamespace(fetch_records=lambda: iter([duplicate_a, duplicate_b]))
            ],
        ),
        patch.object(market, "SessionLocal", return_value=session),
        patch.object(market, "start_job", return_value=1),
        patch.object(market, "complete_job"),
        patch.object(market, "_get_existing", return_value=None),
        patch.object(market, "_calculate_growth", return_value=(None, None)),
    ):
        result = market.ingest_market_data("CA", limit=4)

    assert result["inserted"] == 1
    assert result["skipped"] == 1
    assert len(session.added) == 1
