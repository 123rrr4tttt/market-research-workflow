"""C7.1 staged candidate boundary tests."""

from __future__ import annotations

from app.successor_runtime.capabilities.ingest_c7_common import (
    INGEST_STAGE_CANDIDATE,
    EffectOutcome,
    stage_ingest_submission,
)
from tests.successor_runtime.p4_c7_fixture import submission


def test_stage_creates_candidate_without_admission_or_provider_effect() -> None:
    outcome = stage_ingest_submission(submission(), candidate_id="candidate-1")
    assert isinstance(outcome, EffectOutcome)
    assert outcome.disposition == "SUCCEEDED"
    assert outcome.receipt["candidate_id"] == "candidate-1"
    assert outcome.receipt["stage"] == INGEST_STAGE_CANDIDATE
    assert outcome.receipt["admission_implied"] is False
    assert outcome.receipt["provider_calls"] == 0
    assert outcome.receipt["authority"] is False


def test_staging_is_deterministic_and_preserves_normalized_content() -> None:
    first = stage_ingest_submission(submission())
    second = stage_ingest_submission(submission())
    assert first.receipt == second.receipt
    assert first.receipt["content_digest"]
    assert len(first.receipt["content_digest"]) == 64


def test_submission_payload_digest_is_content_addressed() -> None:
    payload = submission()
    assert payload.payload_digest
    assert len(payload.payload_digest) == 64
    assert payload.payload_digest == submission().payload_digest


def test_staged_candidate_vocabulary_has_no_document_write_surface() -> None:
    outcome = stage_ingest_submission(submission())
    assert "document_write" not in outcome.receipt
