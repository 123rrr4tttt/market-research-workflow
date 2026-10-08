from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.ingest.policy import (
    _extraction_readback,
    ingest_policy_documents,
    materialize_policy_documents,
)
from app.services.ingest.provider_ports import PolicyDocument


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

    documents, folded = materialize_policy_documents(
        source(), state="CA", max_documents=2
    )
    assert [document.title for document in documents] == ["Policy 0", "Policy 1"]
    assert consumed == [0, 1]
    assert [row.input_index for row in folded.rows] == [0, 1]
    assert all(row.receipt is not None for row in folded.rows)
    assert folded.rows[0].receipt.authoritative_readback is False
    assert folded.rows[0].receipt.provider_job_id != folded.rows[1].receipt.provider_job_id
    assert folded.sequence_digest
    assert folded.receipts[0].provider_job_id == folded.rows[0].receipt.provider_job_id


def test_policy_materialization_cancellation_is_typed_and_partial() -> None:
    documents, folded = materialize_policy_documents(
        (_doc(index) for index in range(4)),
        state="CA",
        cancel_check=lambda index: index == 2,
    )
    assert len(documents) == 2
    assert folded.cancellation is not None
    assert folded.cancellation.trigger_input_index == 2
    assert [row.input_index for row in folded.rows] == [0, 1]


def test_policy_materialization_invalid_item_is_typed_failure() -> None:
    documents, folded = materialize_policy_documents(
        [SimpleNamespace(state="CA", title="bad")], state="CA"
    )
    assert documents == []
    assert folded.failed_count == 1
    assert folded.rows[0].result_status == "failed"
    assert folded.rows[0].errors[0]["exception_type"] == "TypeError"


def test_policy_materialization_records_provider_next_failure_after_partial_prefix() -> None:
    class ProviderFailure(RuntimeError):
        pass

    def source():
        yield _doc(0)
        yield _doc(1)
        raise ProviderFailure("provider next failed")

    iteration_errors: list[BaseException] = []
    documents, folded = materialize_policy_documents(
        source(), state="CA", _iteration_error_out=iteration_errors
    )

    assert [document.title for document in documents] == ["Policy 0", "Policy 1"]
    assert len(iteration_errors) == 1
    assert isinstance(iteration_errors[0], ProviderFailure)
    assert str(iteration_errors[0]) == "provider next failed"
    assert [row.input_index for row in folded.rows] == [0, 1, 2]
    assert folded.rows[-1].result_status == "failed"
    assert folded.rows[-1].errors[0]["exception_type"] == "ProviderFailure"
    assert folded.rows[-1].errors[0]["message"] == "provider next failed"


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


def test_policy_ingest_consumes_canonical_fold_without_upgrading_ack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Query:
        def filter(self, *_args: object) -> "_Query":
            return self

        def first(self) -> None:
            return None

    class _Session:
        def __enter__(self) -> "_Session":
            return self

        def __exit__(self, *_args: object) -> bool:
            return False

        def query(self, *_args: object) -> _Query:
            return _Query()

        def commit(self) -> None:
            return None

        def rollback(self) -> None:
            return None

    completed: list[dict[str, object]] = []
    monkeypatch.setattr(
        "app.services.ingest.policy.get_policy_adapter",
        lambda *_args: SimpleNamespace(fetch_documents=lambda: [_doc(0)]),
    )
    monkeypatch.setattr("app.services.ingest.policy.SessionLocal", _Session)
    monkeypatch.setattr(
        "app.services.ingest.policy._get_or_create_source",
        lambda *_args: SimpleNamespace(name="fixture"),
    )
    monkeypatch.setattr(
        "app.services.ingest.policy.build_frontdoor_ingress_envelope",
        lambda **_kwargs: {},
    )
    monkeypatch.setattr(
        "app.services.ingest.policy.run_postprocess_frontdoor",
        lambda **_kwargs: {"data": {"writer_result": {"reason": "skipped_exists"}}},
    )
    monkeypatch.setattr("app.services.ingest.policy.start_job", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(
        "app.services.ingest.policy.complete_job",
        lambda _job_id, *, result: completed.append(result),
    )
    monkeypatch.setattr("app.services.ingest.policy.fail_job", lambda *_args: None)

    result = ingest_policy_documents("CA", request_id="request-1")

    materialization = result["materialization"]
    assert (
        materialization["schema_version"]
        == "mrw.successor.ingest.policy.materialization-projection.v2"
    )
    assert materialization["status"] == "OUTCOME_UNKNOWN"
    assert materialization["outcome_count"] == 1
    assert materialization["sequence_digest"]
    assert materialization["replay_identity"]
    assert materialization["aggregate"]["schema_version"] == "mrw.collect.batch-fold.v1"
    row = materialization["aggregate"]["ordered_rows"][0]
    assert row["result_status"] == "succeeded"
    assert row["receipt"]["receipt_kind"] == "DISPATCH_ACKNOWLEDGEMENT"
    assert completed == [result]


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
