"""C7 malformed/resource/empty/reverse and digest failure tests."""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from app.successor_runtime.capabilities.ingest_c7_movements import (
    C7_CHUNK_MAX_BYTES,
    C7_CHUNK_MAX_COUNT,
    C7_NEW_ATTEMPT_POLICY,
    C7_NORMALIZATION_ONLY_LOSS,
    C7Deferred,
    C7Rejected,
    C7ReverseReturn,
    DeterministicChunkPort,
    DeterministicExtractPort,
    DeterministicPassThroughPort,
    DeterministicSummarizePort,
    RawSnapshot,
    StructuredMaterialCandidate,
    VerifiedMaterialCandidate,
    capture_raw_snapshot_exact,
    execute_c7_movement,
    normalize_ingest_envelope,
    return_for_cleanup,
    select_exactly_one_digestion_alternative,
    verify_structured_candidate,
)


def _snapshot(
    raw_text: str,
    *,
    name: str = "failure",
    mime_type: str = "text/plain",
) -> RawSnapshot:
    return capture_raw_snapshot_exact(
        project_key="demo_proj",
        source_locator="file:///tmp/c7-failure",
        raw_bytes=raw_text.encode("utf-8"),
        revision=1,
        incarnation=f"inc-{name}",
        mime_type=mime_type,
        provenance_refs=("ingest.c7.failure.v1",),
    )


def _trace(
    snapshot: RawSnapshot,
    *,
    input_kind: str,
    content_format: str,
    chunk_port: DeterministicChunkPort | None = None,
    text: str | None = None,
    ports: tuple[Any, Any, Any, Any] | None = None,
) -> Any:
    envelope = normalize_ingest_envelope(
        snapshot=snapshot,
        input_kind=input_kind,
        content_format=content_format,
        text=text,
    )
    decision = select_exactly_one_digestion_alternative(envelope)
    extract, chunk, summarize, pass_through = ports or (
        DeterministicExtractPort(),
        chunk_port or DeterministicChunkPort(),
        DeterministicSummarizePort(),
        DeterministicPassThroughPort(),
    )
    return execute_c7_movement(
        snapshot=snapshot,
        envelope=envelope,
        decision=decision,
        extract=extract,
        chunk=chunk,
        summarize=summarize,
        pass_through=pass_through,
    )


def _verify_inputs(
    snapshot: RawSnapshot,
    envelope: Any,
    decision: Any,
    candidate: StructuredMaterialCandidate,
    **overrides: Any,
) -> dict[str, Any]:
    base = {
        "snapshot": snapshot,
        "envelope": envelope,
        "decision": decision,
        "candidate": candidate,
        "expected_candidate_digest": candidate.candidate_digest,
        "expected_project_key": candidate.project_key,
        "actor": "actor:c7-test",
        "authority_digest": "a" * 64,
        "authority_epoch": 1,
        "canonical_base_revision": 1,
        "canonical_base_incarnation": "canonical-base-v1",
        "canonical_object_id": "doc:c7:test",
    }
    base.update(overrides)
    return base


def test_malformed_structured_json_is_typed_rejected() -> None:
    snapshot = _snapshot(
        '{"title": ',
        name="malformed-json",
        mime_type="application/json",
    )
    trace = _trace(
        snapshot,
        input_kind="url_driven_external",
        content_format="structured_json",
    )
    assert isinstance(trace.outcome, C7Rejected)
    assert trace.outcome.failure_code == "malformed_structured_json"
    assert trace.outcome.snapshot_ref == snapshot.snapshot_ref
    assert trace.outcome.provider_calls == 0
    assert trace.outcome.canonical_write is False
    assert trace.provider_calls == 0
    assert trace.branch_receipt == trace.outcome.rejected_digest


@pytest.mark.parametrize(
    "raw_json",
    ['{"x": NaN}', '{"x": Infinity}', '{"x": -Infinity}', '{"x": 1e9999}'],
)
def test_structured_json_non_finite_constants_are_malformed(
    raw_json: str,
) -> None:
    snapshot = _snapshot(
        raw_json,
        name="json-non-finite",
        mime_type="application/json",
    )
    trace = _trace(
        snapshot,
        input_kind="url_driven_external",
        content_format="structured_json",
    )
    assert isinstance(trace.outcome, C7Rejected)
    assert trace.outcome.failure_code == "malformed_structured_json"
    assert trace.outcome.snapshot_ref == snapshot.snapshot_ref
    assert trace.outcome.provider_calls == 0


def test_empty_structured_output_is_typed_rejected() -> None:
    snapshot = _snapshot(
        "{}",
        name="empty-json",
        mime_type="application/json",
    )
    trace = _trace(
        snapshot,
        input_kind="url_driven_external",
        content_format="structured_json",
    )
    assert isinstance(trace.outcome, C7Rejected)
    assert trace.outcome.failure_code == "empty_structured_output"


def test_chunk_resource_ceiling_fails_closed() -> None:
    snapshot = _snapshot(
        "word " * 8000,
        name="chunk-resource",
        mime_type="text/markdown",
    )
    trace = _trace(
        snapshot,
        input_kind="report_shaped",
        content_format="markdown",
        chunk_port=DeterministicChunkPort(
            max_chunk_bytes=16,
            max_chunk_count=2,
        ),
    )
    assert isinstance(trace.outcome, C7Rejected)
    assert trace.outcome.failure_code == "chunk_count_ceiling_exceeded"
    assert trace.outcome.provider_calls == 0
    assert trace.canonical_write is False


def test_chunk_port_constructor_rejects_global_ceiling_violations() -> None:
    with pytest.raises(ValueError, match="global C7 chunk byte ceiling"):
        DeterministicChunkPort(max_chunk_bytes=C7_CHUNK_MAX_BYTES + 1)
    with pytest.raises(ValueError, match="global C7 chunk count ceiling"):
        DeterministicChunkPort(max_chunk_count=C7_CHUNK_MAX_COUNT + 1)


def test_chunk_port_instance_field_mutation_rejected_before_candidate() -> None:
    snapshot = _snapshot("word " * 800, name="chunk-mutated", mime_type="text/plain")
    port = DeterministicChunkPort()
    port.max_chunk_bytes = C7_CHUNK_MAX_BYTES + 1
    trace = _trace(
        snapshot,
        input_kind="report_shaped",
        content_format="plain_text",
        chunk_port=port,
    )
    assert isinstance(trace.outcome, C7Rejected)
    assert trace.outcome.failure_code == "chunk_policy_ceiling_exceeded"
    assert trace.outcome.candidate_ref is None
    assert trace.outcome.provider_calls == 0
    assert trace.outcome.canonical_write is False


@pytest.mark.parametrize("field", ["max_chunk_bytes", "max_chunk_count"])
def test_chunk_port_infinite_policy_mutation_is_typed_rejected(field: str) -> None:
    snapshot = _snapshot("word " * 800, name=f"chunk-inf-{field}")
    port = DeterministicChunkPort()
    setattr(port, field, float("inf"))
    trace = _trace(
        snapshot,
        input_kind="report_shaped",
        content_format="plain_text",
        chunk_port=port,
    )
    assert isinstance(trace.outcome, C7Rejected)
    assert trace.outcome.failure_code == "chunk_policy_ceiling_exceeded"
    assert trace.outcome.candidate_ref is None


def test_chunk_candidate_never_forms_oversized_byte_chunk() -> None:
    snapshot = _snapshot("a" * 20000, name="chunk-4097", mime_type="text/plain")
    trace = _trace(
        snapshot,
        input_kind="report_shaped",
        content_format="plain_text",
    )
    candidate = trace.outcome
    assert isinstance(candidate, StructuredMaterialCandidate)
    chunks = candidate.structured_payload["chunks"]
    assert chunks
    assert all(chunk["byte_size"] <= C7_CHUNK_MAX_BYTES for chunk in chunks)
    assert candidate.structured_payload["chunk_policy"]["max_chunk_bytes"] == (
        C7_CHUNK_MAX_BYTES
    )


def test_multibyte_codepoint_exceeding_chunk_ceiling_is_typed_rejected() -> None:
    snapshot = _snapshot(
        "市" * 2,
        name="multibyte-chunk",
        mime_type="text/plain",
    )
    trace = _trace(
        snapshot,
        input_kind="report_shaped",
        content_format="plain_text",
        chunk_port=DeterministicChunkPort(
            max_chunk_bytes=2,
            max_chunk_count=4,
        ),
    )
    assert isinstance(trace.outcome, C7Rejected)
    assert trace.outcome.failure_code == "chunk_codepoint_exceeds_ceiling"
    assert trace.outcome.snapshot_ref == snapshot.snapshot_ref
    assert trace.outcome.provider_calls == 0
    assert trace.outcome.canonical_write is False


def test_empty_pass_through_is_rejected_without_candidate() -> None:
    snapshot = _snapshot("", name="empty-pass")
    trace = _trace(
        snapshot,
        input_kind="unknown",
        content_format="other",
        text="",
    )
    assert isinstance(trace.outcome, C7Rejected)
    assert trace.outcome.failure_code == "empty_pass_through_rejected"
    assert trace.outcome.candidate_ref is None


def test_unsafe_pass_through_is_deferred() -> None:
    snapshot = _snapshot("bad\x00content", name="unsafe-pass")
    trace = _trace(
        snapshot,
        input_kind="url_driven_external",
        content_format="plain_text",
    )
    assert isinstance(trace.outcome, C7Deferred)
    assert trace.outcome.failure_code == "unsafe_pass_through_deferred"
    assert trace.outcome.provider_calls == 0
    assert trace.outcome.canonical_write is False


def test_reverse_return_retains_snapshot_and_forbids_new_attempt() -> None:
    snapshot = _snapshot("safe pass-through", name="reverse")
    trace = _trace(
        snapshot,
        input_kind="url_driven_external",
        content_format="plain_text",
    )
    candidate = trace.outcome
    assert isinstance(candidate, StructuredMaterialCandidate)
    reverse = return_for_cleanup(
        snapshot=snapshot,
        candidate=candidate,
        reason="repair required",
        failure="content_quality",
    )
    assert isinstance(reverse, C7ReverseReturn)
    assert reverse.snapshot_ref == snapshot.snapshot_ref
    assert reverse.snapshot_identity_digest == snapshot.snapshot_identity_digest
    assert reverse.candidate_ref == candidate.payload_ref
    assert reverse.admission_disabled is True
    assert reverse.projection_disabled is True
    assert reverse.new_attempt_policy == C7_NEW_ATTEMPT_POLICY
    assert reverse.failure_digest
    assert len(reverse.failure_digest) == 64
    assert reverse.provider_calls == 0
    assert reverse.canonical_write is False
    assert reverse.external_delivery is False
    assert reverse.cutover is False
    assert reverse.authority_transfer is False
    no_candidate = return_for_cleanup(
        snapshot=snapshot,
        reason="repair required",
        failure="content_quality",
    )
    assert no_candidate.candidate_ref is None


def test_raw_snapshot_digest_aba_fails_closed() -> None:
    snapshot = _snapshot("original", name="aba")
    same = capture_raw_snapshot_exact(
        project_key=snapshot.project_key,
        source_locator=snapshot.source_locator,
        raw_bytes=b"original",
        supplied_digest=snapshot.raw_content_digest,
        revision=snapshot.revision,
        incarnation=snapshot.incarnation,
        mime_type=snapshot.mime_type,
        provenance_refs=snapshot.provenance_refs,
    )
    assert same.snapshot_ref == snapshot.snapshot_ref
    with pytest.raises(ValueError, match="does not match raw bytes"):
        capture_raw_snapshot_exact(
            project_key="demo_proj",
            source_locator="file:///tmp/c7-failure",
            raw_bytes=b"mutated",
            supplied_digest=snapshot.raw_content_digest,
            revision=1,
            incarnation=snapshot.incarnation,
        )
    with pytest.raises(ValueError, match="does not match identity fields"):
        capture_raw_snapshot_exact(
            project_key="demo_proj",
            source_locator="file:///tmp/c7-forged-locator",
            raw_bytes=snapshot.raw_bytes,
            supplied_digest=snapshot.raw_content_digest,
            supplied_identity_digest=snapshot.snapshot_identity_digest,
            revision=1,
            incarnation=snapshot.incarnation,
        )
    with pytest.raises(ValueError, match="does not match full identity"):
        capture_raw_snapshot_exact(
            project_key="demo_proj",
            source_locator="file:///tmp/c7-failure",
            raw_bytes=snapshot.raw_bytes,
            supplied_digest=snapshot.raw_content_digest,
            supplied_snapshot_ref=f"raw:c7:sha256:{'0' * 64}",
            revision=1,
            incarnation=snapshot.incarnation,
        )


def test_candidate_payload_mutation_and_verify_mismatch_fail_closed() -> None:
    snapshot = _snapshot('{"title": "ok"}', name="verify", mime_type="application/json")
    envelope = normalize_ingest_envelope(
        snapshot=snapshot,
        input_kind="url_driven_external",
        content_format="structured_json",
    )
    decision = select_exactly_one_digestion_alternative(envelope)
    trace = _trace(
        snapshot,
        input_kind="url_driven_external",
        content_format="structured_json",
    )
    candidate = trace.outcome
    with pytest.raises(ValueError, match="does not match"):
        dataclasses.replace(candidate, structured_payload={"mutated": True})

    self_consistent_forged = dataclasses.replace(
        candidate,
        structured_payload={"mutated": True},
        payload_content_digest="",
        candidate_digest="",
    )
    rejected = verify_structured_candidate(
        **_verify_inputs(
            snapshot,
            envelope,
            decision,
            self_consistent_forged,
            expected_candidate_digest=candidate.candidate_digest,
        )
    )
    assert isinstance(rejected, C7Rejected)
    assert rejected.failure_code == "expected_candidate_digest_mismatch"

    synced_forge = verify_structured_candidate(
        **_verify_inputs(
            snapshot,
            envelope,
            decision,
            self_consistent_forged,
            expected_candidate_digest=self_consistent_forged.candidate_digest,
        )
    )
    assert isinstance(synced_forge, C7Rejected)
    assert synced_forge.failure_code == "candidate_replay_mismatch"

    rejected = verify_structured_candidate(
        **_verify_inputs(
            snapshot,
            envelope,
            decision,
            candidate,
            expected_project_key="other_project",
        )
    )
    assert isinstance(rejected, C7Rejected)
    assert rejected.failure_code == "project_key_mismatch"


def test_verify_success_grants_no_canonical_write_and_epoch_can_defer() -> None:
    snapshot = _snapshot(
        '{"title": "ok"}', name="verify-ok", mime_type="application/json"
    )
    envelope = normalize_ingest_envelope(
        snapshot=snapshot,
        input_kind="url_driven_external",
        content_format="structured_json",
    )
    decision = select_exactly_one_digestion_alternative(envelope)
    trace = _trace(
        snapshot,
        input_kind="url_driven_external",
        content_format="structured_json",
    )
    candidate = trace.outcome
    verified = verify_structured_candidate(
        **_verify_inputs(snapshot, envelope, decision, candidate)
    )
    assert isinstance(verified, VerifiedMaterialCandidate)
    assert verified.candidate_id == candidate.candidate_id
    assert verified.candidate_digest == candidate.candidate_digest
    assert verified.envelope_digest == envelope.envelope_digest
    assert verified.snapshot_ref == snapshot.snapshot_ref
    assert verified.snapshot_identity_digest == snapshot.snapshot_identity_digest
    assert verified.raw_content_digest == snapshot.raw_content_digest
    assert verified.payload_content_digest == candidate.payload_content_digest
    assert (
        verified.ordered_source_closure_digest
        == candidate.ordered_source_closure_digest
    )
    assert verified.provenance_closure_digest == candidate.provenance_closure_digest
    assert verified.decision_digest == decision.decision_digest
    assert verified.alternative == decision.alternative
    assert verified.project_key == candidate.project_key
    assert verified.canonical_object_id == "doc:c7:test"
    assert verified.expected_base_revision == 1
    assert verified.expected_base_incarnation == "canonical-base-v1"
    assert verified.actor == "actor:c7-test"
    assert verified.authority_digest == "a" * 64
    assert verified.authority_epoch == 1
    assert verified.canonical_write_authorized is False
    assert verified.provider_calls == 0
    assert verified.verification_receipt
    assert verified.verification_digest

    deferred = verify_structured_candidate(
        **_verify_inputs(
            snapshot,
            envelope,
            decision,
            candidate,
            authority_epoch=2,
            revoked_authority_epochs=frozenset({2}),
        )
    )
    assert isinstance(deferred, C7Deferred)
    assert deferred.failure_code == "authority_epoch_revoked"


def test_verify_allows_base_revision_zero_and_rejects_negative() -> None:
    snapshot = _snapshot(
        '{"title": "base0"}', name="verify-base0", mime_type="application/json"
    )
    envelope = normalize_ingest_envelope(
        snapshot=snapshot,
        input_kind="url_driven_external",
        content_format="structured_json",
    )
    decision = select_exactly_one_digestion_alternative(envelope)
    trace = _trace(
        snapshot,
        input_kind="url_driven_external",
        content_format="structured_json",
    )
    candidate = trace.outcome
    verified = verify_structured_candidate(
        **_verify_inputs(
            snapshot,
            envelope,
            decision,
            candidate,
            canonical_base_revision=0,
        )
    )
    assert isinstance(verified, VerifiedMaterialCandidate)
    assert verified.expected_base_revision == 0
    assert verified.canonical_write_authorized is False
    assert verified.provider_calls == 0

    rejected = verify_structured_candidate(
        **_verify_inputs(
            snapshot,
            envelope,
            decision,
            candidate,
            canonical_base_revision=-1,
        )
    )
    assert isinstance(rejected, C7Rejected)
    assert rejected.failure_code == "server_identity_missing"

    with pytest.raises(ValueError, match="must be >= 0"):
        dataclasses.replace(
            verified,
            expected_base_revision=-1,
            verification_digest="",
        )


def test_chunk_verify_replays_digest_bound_non_default_policy() -> None:
    snapshot = _snapshot("word " * 800, name="chunk-policy", mime_type="text/plain")
    trace = _trace(
        snapshot,
        input_kind="report_shaped",
        content_format="plain_text",
        chunk_port=DeterministicChunkPort(
            max_chunk_bytes=512,
            max_chunk_count=16,
        ),
    )
    candidate = trace.outcome
    assert isinstance(candidate, StructuredMaterialCandidate)
    assert candidate.structured_payload["chunk_policy"] == {
        "max_chunk_bytes": 512,
        "max_chunk_count": 16,
    }
    envelope = normalize_ingest_envelope(
        snapshot=snapshot,
        input_kind="report_shaped",
        content_format="plain_text",
    )
    decision = select_exactly_one_digestion_alternative(envelope)
    verified = verify_structured_candidate(
        **_verify_inputs(snapshot, envelope, decision, candidate)
    )
    assert isinstance(verified, VerifiedMaterialCandidate)
    assert verified.candidate_digest == candidate.candidate_digest

    zero_policy = dict(candidate.structured_payload)
    zero_policy["chunk_policy"] = {"max_chunk_bytes": 0, "max_chunk_count": 16}
    zero_forged = dataclasses.replace(
        candidate,
        structured_payload=zero_policy,
        payload_content_digest="",
        candidate_digest="",
    )
    rejected = verify_structured_candidate(
        **_verify_inputs(
            snapshot,
            envelope,
            decision,
            zero_forged,
            expected_candidate_digest=zero_forged.candidate_digest,
        )
    )
    assert isinstance(rejected, C7Rejected)
    assert rejected.failure_code == "chunk_policy_invalid"

    oversized_policy = dict(candidate.structured_payload)
    oversized_policy["chunk_policy"] = {
        "max_chunk_bytes": C7_CHUNK_MAX_BYTES + 1,
        "max_chunk_count": 16,
    }
    oversized_forged = dataclasses.replace(
        candidate,
        structured_payload=oversized_policy,
        payload_content_digest="",
        candidate_digest="",
    )
    rejected = verify_structured_candidate(
        **_verify_inputs(
            snapshot,
            envelope,
            decision,
            oversized_forged,
            expected_candidate_digest=oversized_forged.candidate_digest,
        )
    )
    assert isinstance(rejected, C7Rejected)
    assert rejected.failure_code == "chunk_policy_invalid"


def test_pass_through_reports_normalization_loss_and_retains_raw_snapshot() -> None:
    raw_text = "  safe   pass-through  "
    snapshot = _snapshot(raw_text, name="loss", mime_type="text/plain")
    envelope = normalize_ingest_envelope(
        snapshot=snapshot,
        input_kind="url_driven_external",
        content_format="plain_text",
    )
    trace = _trace(
        snapshot,
        input_kind="url_driven_external",
        content_format="plain_text",
    )
    candidate = trace.outcome
    assert isinstance(candidate, StructuredMaterialCandidate)
    assert envelope.normalization_loss == C7_NORMALIZATION_ONLY_LOSS
    assert envelope.normalization_profile_ref
    assert envelope.raw_content_digest == snapshot.raw_content_digest
    assert envelope.raw_byte_length == len(snapshot.raw_bytes)
    assert envelope.snapshot_identity_digest == snapshot.snapshot_identity_digest
    assert snapshot.raw_bytes == raw_text.encode("utf-8")
    assert candidate.failure_loss_profile == C7_NORMALIZATION_ONLY_LOSS
    payload = candidate.structured_payload
    assert payload["raw_snapshot_retained"] is True
    assert payload["raw_content_digest"] == snapshot.raw_content_digest
    assert payload["normalization_loss"] == C7_NORMALIZATION_ONLY_LOSS
    assert payload["normalization_profile_ref"] == envelope.normalization_profile_ref


def test_reverse_return_binds_failure_outcome_digest_and_retry_prohibition() -> None:
    snapshot = _snapshot(
        '{"title": ',
        name="reverse-reject",
        mime_type="application/json",
    )
    trace = _trace(
        snapshot,
        input_kind="url_driven_external",
        content_format="structured_json",
    )
    rejected = trace.outcome
    assert isinstance(rejected, C7Rejected)
    reverse = return_for_cleanup(
        snapshot=snapshot,
        reason="repair required",
        failure="malformed_structured_json",
        outcome=rejected,
    )
    assert isinstance(reverse, C7ReverseReturn)
    assert reverse.snapshot_identity_digest == snapshot.snapshot_identity_digest
    assert reverse.failure_digest == rejected.rejected_digest
    assert reverse.new_attempt_policy == C7_NEW_ATTEMPT_POLICY
    assert reverse.admission_disabled is True
    assert reverse.projection_disabled is True
    assert reverse.provider_calls == 0
    assert reverse.canonical_write is False
    assert reverse.external_delivery is False
    assert reverse.cutover is False
    assert reverse.authority_transfer is False


def test_typed_reject_defer_short_circuits_branch_admission_write() -> None:
    snapshot = _snapshot("bad\x00content", name="defer-short")
    ports = (
        DeterministicExtractPort(),
        DeterministicChunkPort(),
        DeterministicSummarizePort(),
        DeterministicPassThroughPort(),
    )
    trace = _trace(
        snapshot,
        input_kind="url_driven_external",
        content_format="plain_text",
        ports=ports,
    )
    deferred = trace.outcome
    assert isinstance(deferred, C7Deferred)
    assert sum(port.calls for port in ports) == 1
    assert ports[3].calls == 1
    reverse = return_for_cleanup(
        snapshot=snapshot,
        reason="repair required",
        failure="unsafe_pass_through_deferred",
        outcome=deferred,
    )
    assert reverse.failure_digest == deferred.deferred_digest
    assert reverse.candidate_ref is None

    valid_snapshot = _snapshot("safe text", name="short-circuit-ok")
    valid_trace = _trace(
        valid_snapshot,
        input_kind="url_driven_external",
        content_format="plain_text",
    )
    candidate = valid_trace.outcome
    assert isinstance(candidate, StructuredMaterialCandidate)
    with pytest.raises(TypeError, match="typed C7Rejected or C7Deferred"):
        return_for_cleanup(
            snapshot=valid_snapshot,
            reason="repair required",
            failure="content_quality",
            outcome=candidate,
        )
    with pytest.raises(ValueError, match="mutually exclusive"):
        return_for_cleanup(
            snapshot=valid_snapshot,
            reason="repair required",
            failure="content_quality",
            candidate=candidate,
            outcome=deferred,
        )


def test_forged_input_closure_rejected_at_verification() -> None:
    snapshot = _snapshot(
        '{"title": "ok"}', name="verify-forged", mime_type="application/json"
    )
    envelope = normalize_ingest_envelope(
        snapshot=snapshot,
        input_kind="url_driven_external",
        content_format="structured_json",
    )
    decision = select_exactly_one_digestion_alternative(envelope)
    trace = _trace(
        snapshot,
        input_kind="url_driven_external",
        content_format="structured_json",
    )
    candidate = trace.outcome

    forged_envelope = dataclasses.replace(
        envelope, normalized_text="forged normalized text", envelope_digest=""
    )
    rejected = verify_structured_candidate(
        **_verify_inputs(snapshot, forged_envelope, decision, candidate)
    )
    assert rejected.failure_code == "input_closure_mismatch"

    forged_decision = dataclasses.replace(
        decision, reason="forged reason", decision_digest=""
    )
    rejected = verify_structured_candidate(
        **_verify_inputs(snapshot, envelope, forged_decision, candidate)
    )
    assert rejected.failure_code == "input_closure_mismatch"
    assert "exact envelope selector" in rejected.reason

    forged_snapshot = dataclasses.replace(
        snapshot,
        source_locator="file:///tmp/c7-forged-locator",
        snapshot_identity_digest="",
        snapshot_ref="",
    )
    rejected = verify_structured_candidate(
        **_verify_inputs(forged_snapshot, envelope, decision, candidate)
    )
    assert rejected.failure_code == "input_closure_mismatch"


def test_return_for_cleanup_outcome_must_match_snapshot() -> None:
    snapshot = _snapshot('{"title": ', name="reverse-own", mime_type="application/json")
    trace = _trace(
        snapshot,
        input_kind="url_driven_external",
        content_format="structured_json",
    )
    other_snapshot = _snapshot(
        '{"broken": ', name="reverse-other", mime_type="application/json"
    )
    other_trace = _trace(
        other_snapshot,
        input_kind="url_driven_external",
        content_format="structured_json",
    )
    other_outcome = other_trace.outcome
    assert isinstance(other_outcome, C7Rejected)
    with pytest.raises(
        ValueError, match="outcome is not bound to the returned snapshot"
    ):
        return_for_cleanup(
            snapshot=snapshot,
            reason="repair required",
            failure="malformed_structured_json",
            outcome=other_outcome,
        )
    same_outcome = trace.outcome
    assert isinstance(same_outcome, C7Rejected)
    reverse = return_for_cleanup(
        snapshot=snapshot,
        reason="repair required",
        failure="malformed_structured_json",
        outcome=same_outcome,
    )
    assert reverse.failure_digest == same_outcome.rejected_digest


def test_return_for_cleanup_candidate_checks_full_snapshot_identity() -> None:
    snapshot = _snapshot("safe pass-through", name="reverse-full-id")
    trace = _trace(
        snapshot,
        input_kind="url_driven_external",
        content_format="plain_text",
    )
    candidate = trace.outcome
    assert isinstance(candidate, StructuredMaterialCandidate)
    forged_identity = dataclasses.replace(
        candidate,
        snapshot_identity_digest="0" * 64,
        candidate_digest="",
    )
    with pytest.raises(ValueError, match="full snapshot identity"):
        return_for_cleanup(
            snapshot=snapshot,
            candidate=forged_identity,
            reason="repair required",
            failure="content_quality",
        )
    forged_content = dataclasses.replace(
        candidate,
        raw_content_digest="0" * 64,
        candidate_digest="",
    )
    with pytest.raises(ValueError, match="full snapshot identity"):
        return_for_cleanup(
            snapshot=snapshot,
            candidate=forged_content,
            reason="repair required",
            failure="content_quality",
        )
