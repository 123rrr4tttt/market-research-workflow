"""C7 four-mode legacy/target decision parity tests."""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from app.successor_migration.legacy_c7_decision_oracle import (
    legacy_c7_decision_oracle,
)
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.ingest_c7_movements import (
    C7_ALTERNATIVES,
    C7_LONG_REPORT_MIN_LENGTH,
    C7_PROVIDER_ENRICHMENT_DECLARED_LOSS_REF,
    C7_STAGING_ONLY_AUTHORITY,
    DeterministicChunkPort,
    DeterministicExtractPort,
    DeterministicPassThroughPort,
    DeterministicSummarizePort,
    NormalizedIngestEnvelope,
    RawSnapshot,
    StagingAuthority,
    StructuredMaterialCandidate,
    capture_raw_snapshot_exact,
    execute_c7_movement,
    normalize_ingest_envelope,
    select_exactly_one_digestion_alternative,
    verify_structured_candidate,
)


def _cases() -> dict[str, dict[str, Any]]:
    return {
        "structured_json": {
            "expected_alternative": "EXTRACT",
            "input_kind": "url_driven_external",
            "content_format": "structured_json",
            "mime_type": "application/json",
            "raw_text": '{"title": "Q2", "domains": ["market"]}',
        },
        "long_report": {
            "expected_alternative": "CHUNK",
            "input_kind": "report_shaped",
            "content_format": "markdown",
            "mime_type": "text/markdown",
            "raw_text": "Market report. " * 800,
        },
        "derived_report": {
            "expected_alternative": "SUMMARIZE",
            "input_kind": "derived_llm_report",
            "content_format": "markdown",
            "mime_type": "text/markdown",
            "raw_text": "# Derived report\n\nConclusion: demand grew.",
        },
        "pass_through": {
            "expected_alternative": "PASS_THROUGH",
            "input_kind": "url_driven_external",
            "content_format": "html",
            "mime_type": "text/html",
            "raw_text": "<p>short observation</p>",
        },
    }


def _ports() -> tuple[
    DeterministicExtractPort,
    DeterministicChunkPort,
    DeterministicSummarizePort,
    DeterministicPassThroughPort,
]:
    return (
        DeterministicExtractPort(),
        DeterministicChunkPort(),
        DeterministicSummarizePort(),
        DeterministicPassThroughPort(),
    )


def _run_mode(
    name: str,
) -> tuple[
    RawSnapshot,
    Any,
    dict[str, Any],
    Any,
    Any,
    tuple[Any, Any, Any, Any],
]:
    spec = _cases()[name]
    raw_text = str(spec["raw_text"])
    snapshot = capture_raw_snapshot_exact(
        project_key="demo_proj",
        source_locator="file:///tmp/c7-parity",
        raw_bytes=raw_text.encode("utf-8"),
        revision=1,
        incarnation=f"inc-{name}",
        mime_type=str(spec["mime_type"]),
        provenance_refs=("ingest.c7.parity.v1",),
    )
    envelope = normalize_ingest_envelope(
        snapshot=snapshot,
        input_kind=str(spec["input_kind"]),
        content_format=str(spec["content_format"]),
    )
    oracle = legacy_c7_decision_oracle()
    legacy = oracle.decide(
        input_kind=str(spec["input_kind"]),
        content_format=str(spec["content_format"]),
        content_length=len(raw_text),
    )
    decision = select_exactly_one_digestion_alternative(envelope)
    extract, chunk, summarize, pass_through = _ports()
    trace = execute_c7_movement(
        snapshot=snapshot,
        envelope=envelope,
        decision=decision,
        extract=extract,
        chunk=chunk,
        summarize=summarize,
        pass_through=pass_through,
    )
    return (
        snapshot,
        envelope,
        legacy,
        decision,
        trace,
        (extract, chunk, summarize, pass_through),
    )


def test_four_mode_legacy_and_target_decision_parity() -> None:
    expected_stages = {
        "EXTRACT": "extract_first",
        "CHUNK": "chunk_first",
        "SUMMARIZE": "summarize_first",
        "PASS_THROUGH": "pass_through",
    }
    for name in _cases():
        snapshot, envelope, legacy, decision, trace, _ = _run_mode(name)
        assert legacy["stage"] == expected_stages[decision.alternative]
        assert decision.alternative == _cases()[name]["expected_alternative"]
        assert legacy["content_length"] == len(str(_cases()[name]["raw_text"]))
        assert decision.source_character_length == envelope.source_character_length
        assert decision.source_character_length == len(str(_cases()[name]["raw_text"]))
        assert decision.raw_byte_length == len(snapshot.raw_bytes)
        assert envelope.raw_byte_length == len(snapshot.raw_bytes)
        assert decision.envelope_digest == envelope.envelope_digest
        assert trace.outcome.alternative == decision.alternative
        assert legacy["provider_calls"] == 0
        assert trace.provider_calls == 0
        assert legacy["authority"] is False
        assert trace.authority is False
        assert trace.canonical_write is False
        assert trace.external_delivery is False
        assert trace.cutover is False
        assert trace.authority_transfer is False


def test_exactly_one_target_branch_executes_per_trace() -> None:
    port_by_alternative = {
        "EXTRACT": 0,
        "CHUNK": 1,
        "SUMMARIZE": 2,
        "PASS_THROUGH": 3,
    }
    for name in _cases():
        snapshot, envelope, _legacy, decision, trace, ports = _run_mode(name)
        assert decision.alternative in C7_ALTERNATIVES
        assert not hasattr(decision, "extract_required")
        assert not hasattr(decision, "chunking_required")
        assert not hasattr(decision, "summarize_required")
        assert isinstance(trace.outcome, StructuredMaterialCandidate)
        assert sum(port.calls for port in ports) == 1
        selected_index = port_by_alternative[decision.alternative]
        assert ports[selected_index].calls == 1
        assert all(port.provider_calls == 0 for port in ports)
        assert trace.branch_receipt == trace.outcome.candidate_digest
        candidate = trace.outcome
        assert candidate.snapshot_ref == snapshot.snapshot_ref
        assert candidate.snapshot_identity_digest == snapshot.snapshot_identity_digest
        assert candidate.raw_content_digest == snapshot.raw_content_digest
        assert candidate.envelope_digest == envelope.envelope_digest
        assert candidate.decision_digest == decision.decision_digest
        assert candidate.ordered_source_refs == (snapshot.snapshot_ref,)
        assert candidate.provenance_closure == (
            snapshot.snapshot_ref,
            envelope.envelope_digest,
            decision.decision_digest,
        )
        assert candidate.authority is StagingAuthority.STAGING_ONLY_NO_DOCUMENT_WRITE


def test_legacy_dual_flag_conflicts_are_not_silently_normalized() -> None:
    for name in ("long_report", "derived_report"):
        _snapshot, _envelope, legacy, decision, trace, _ = _run_mode(name)
        assert legacy["dual_flag_conflict"] is True
        assert decision.alternative in {"CHUNK", "SUMMARIZE"}
        assert decision.branch_internal_structuring == ("extract_required",)
        assert not hasattr(decision, "extract_required")
        assert trace.outcome.alternative == decision.alternative
        assert trace.outcome.structured_payload["branch_internal_structuring"] == [
            "extract_required"
        ]
        structure = trace.outcome.structured_payload["branch_internal_structure"]
        assert structure["extract_required"]["formation"] == (
            "deterministic_branch_internal_structure_v1"
        )
        assert structure["extract_required"]["provider_model_enrichment"] == (
            "DECLARED_LOSS"
        )
        assert structure["extract_required"]["provider_calls"] == 0
        assert trace.outcome.failure_loss_profile == (
            C7_PROVIDER_ENRICHMENT_DECLARED_LOSS_REF
        )
        assert "without_extract" not in decision.reason


def test_candidate_digests_bind_snapshot_decision_and_branch() -> None:
    for name in ("structured_json", "long_report", "derived_report"):
        snapshot, envelope, _legacy, decision, trace, _ = _run_mode(name)
        candidate = trace.outcome
        assert isinstance(candidate, StructuredMaterialCandidate)
        assert candidate.decision_digest == decision.decision_digest
        assert candidate.snapshot_ref == trace.snapshot_ref
        assert candidate.snapshot_identity_digest == snapshot.snapshot_identity_digest
        assert candidate.raw_content_digest == snapshot.raw_content_digest
        assert candidate.envelope_digest == envelope.envelope_digest
        assert candidate.payload_content_digest == content_digest(
            candidate.structured_payload
        )
        assert candidate.ordered_source_closure_digest == content_digest(
            (snapshot.snapshot_ref,)
        )
        assert candidate.provenance_closure_digest == content_digest(
            (snapshot.snapshot_ref, envelope.envelope_digest, decision.decision_digest)
        )
        assert candidate.ordered_source_refs == (candidate.snapshot_ref,)
        assert candidate.provenance_closure
        assert candidate.candidate_digest
        assert len(candidate.candidate_digest) == 64
        assert candidate.authority.value == C7_STAGING_ONLY_AUTHORITY


def test_decision_digest_is_stable_and_content_addressed() -> None:
    first = _run_mode("pass_through")
    second = _run_mode("pass_through")
    assert first[3].decision_digest == second[3].decision_digest
    changed = _run_mode("structured_json")
    assert changed[3].decision_digest != first[3].decision_digest


def test_four_alternatives_one_of_common_prefix_only() -> None:
    assert C7_ALTERNATIVES == (
        "EXTRACT",
        "CHUNK",
        "SUMMARIZE",
        "PASS_THROUGH",
    )
    for name in _cases():
        _snapshot, _envelope, _legacy, decision, _trace, ports = _run_mode(name)
        selected = [port.calls for port in ports if port.receipts and port.calls == 1]
        assert len(selected) == 1
        assert decision.alternative in C7_ALTERNATIVES


def test_snapshot_identity_binds_project_source_and_provenance() -> None:
    base = capture_raw_snapshot_exact(
        project_key="demo_proj",
        source_locator="file:///tmp/c7-parity",
        raw_bytes=b"same raw bytes",
        revision=1,
        incarnation="inc-identity",
        mime_type="text/plain",
        provenance_refs=("ingest.c7.parity.v1",),
    )
    variants = [
        {"project_key": "other_proj", "source_locator": base.source_locator},
        {"project_key": base.project_key, "source_locator": "file:///tmp/c7-other"},
        {
            "project_key": base.project_key,
            "source_locator": base.source_locator,
            "provenance_refs": ("ingest.c7.parity.v2",),
        },
    ]
    for changes in variants:
        changed = capture_raw_snapshot_exact(
            project_key=changes.get("project_key", base.project_key),
            source_locator=changes.get("source_locator", base.source_locator),
            raw_bytes=base.raw_bytes,
            revision=base.revision,
            incarnation=base.incarnation,
            mime_type=base.mime_type,
            provenance_refs=changes.get("provenance_refs", base.provenance_refs),
        )
        assert changed.raw_content_digest == base.raw_content_digest
        assert changed.snapshot_identity_digest != base.snapshot_identity_digest
        assert changed.snapshot_ref != base.snapshot_ref
        assert changed.snapshot_ref == (
            f"raw:c7:sha256:{changed.snapshot_identity_digest}"
        )


def test_raw_byte_length_boundary_matches_legacy_selector() -> None:
    for length in (C7_LONG_REPORT_MIN_LENGTH - 1, C7_LONG_REPORT_MIN_LENGTH):
        raw_text = "a" * length
        snapshot = capture_raw_snapshot_exact(
            project_key="demo_proj",
            source_locator="file:///tmp/c7-boundary",
            raw_bytes=raw_text.encode("utf-8"),
            revision=1,
            incarnation=f"inc-boundary-{length}",
            mime_type="text/markdown",
            provenance_refs=("ingest.c7.boundary.v1",),
        )
        envelope = normalize_ingest_envelope(
            snapshot=snapshot,
            input_kind="url_driven_external",
            content_format="markdown",
        )
        legacy = legacy_c7_decision_oracle().decide(
            input_kind="url_driven_external",
            content_format="markdown",
            content_length=length,
        )
        decision = select_exactly_one_digestion_alternative(envelope)
        expected = "PASS_THROUGH" if length < C7_LONG_REPORT_MIN_LENGTH else "CHUNK"
        assert decision.alternative == expected
        assert legacy["stage"] == (
            "pass_through" if expected == "PASS_THROUGH" else "chunk_first"
        )
        assert decision.source_character_length == length
        assert decision.raw_byte_length == length == len(snapshot.raw_bytes)
        assert envelope.source_character_length == length
        assert legacy["content_length"] == length


def test_non_ascii_character_versus_byte_length_parity() -> None:
    short_text = "市" * 3000
    snapshot = capture_raw_snapshot_exact(
        project_key="demo_proj",
        source_locator="file:///tmp/c7-non-ascii",
        raw_bytes=short_text.encode("utf-8"),
        revision=1,
        incarnation="inc-non-ascii-3000",
        mime_type="text/markdown",
        provenance_refs=("ingest.c7.non-ascii.v1",),
    )
    envelope = normalize_ingest_envelope(
        snapshot=snapshot,
        input_kind="url_driven_external",
        content_format="markdown",
    )
    legacy = legacy_c7_decision_oracle().decide(
        input_kind="url_driven_external",
        content_format="markdown",
        content_length=len(short_text),
    )
    decision = select_exactly_one_digestion_alternative(envelope)
    assert envelope.source_character_length == 3000
    assert envelope.raw_byte_length == 9000
    assert decision.source_character_length == 3000
    assert decision.raw_byte_length == 9000
    assert decision.alternative == "PASS_THROUGH"
    assert legacy["stage"] == "pass_through"

    boundary_text = "市" * 6000
    boundary_snapshot = capture_raw_snapshot_exact(
        project_key="demo_proj",
        source_locator="file:///tmp/c7-non-ascii",
        raw_bytes=boundary_text.encode("utf-8"),
        revision=1,
        incarnation="inc-non-ascii-6000",
        mime_type="text/markdown",
        provenance_refs=("ingest.c7.non-ascii.v1",),
    )
    boundary_envelope = normalize_ingest_envelope(
        snapshot=boundary_snapshot,
        input_kind="url_driven_external",
        content_format="markdown",
    )
    boundary_decision = select_exactly_one_digestion_alternative(boundary_envelope)
    boundary_legacy = legacy_c7_decision_oracle().decide(
        input_kind="url_driven_external",
        content_format="markdown",
        content_length=len(boundary_text),
    )
    assert boundary_envelope.source_character_length == 6000
    assert boundary_envelope.raw_byte_length == 18000
    assert boundary_decision.alternative == "CHUNK"
    assert boundary_legacy["stage"] == "chunk_first"


def test_decision_digest_changes_with_envelope_identity() -> None:
    snapshot = capture_raw_snapshot_exact(
        project_key="demo_proj",
        source_locator="file:///tmp/c7-envelope",
        raw_bytes=b"short plain text",
        revision=1,
        incarnation="inc-envelope",
        mime_type="text/plain",
        provenance_refs=("ingest.c7.envelope.v1",),
    )
    envelope_a = normalize_ingest_envelope(
        snapshot=snapshot,
        input_kind="url_driven_external",
        content_format="plain_text",
    )
    envelope_b = normalize_ingest_envelope(
        snapshot=snapshot,
        input_kind="url_driven_external",
        content_format="plain_text",
        requested_downstream_targets=("writing",),
    )
    decision_a = select_exactly_one_digestion_alternative(envelope_a)
    decision_b = select_exactly_one_digestion_alternative(envelope_b)
    assert envelope_a.envelope_digest != envelope_b.envelope_digest
    assert decision_a.envelope_digest == envelope_a.envelope_digest
    assert decision_b.envelope_digest == envelope_b.envelope_digest
    assert decision_a.decision_digest != decision_b.decision_digest
    assert decision_a.alternative == decision_b.alternative == "PASS_THROUGH"


def test_same_branch_decision_metadata_mutation_fails_exact_selector_check() -> None:
    snapshot, envelope, _legacy, decision, trace, _ = _run_mode("pass_through")
    candidate = trace.outcome
    assert isinstance(candidate, StructuredMaterialCandidate)
    forged = dataclasses.replace(
        decision,
        reason="caller-forged-reason",
        profile_ref="caller-forged-profile",
        decision_digest="",
    )
    assert forged.alternative == decision.alternative
    assert forged.decision_digest != decision.decision_digest
    rejected = verify_structured_candidate(
        snapshot=snapshot,
        envelope=envelope,
        decision=forged,
        candidate=candidate,
        expected_candidate_digest=candidate.candidate_digest,
        expected_project_key=candidate.project_key,
        actor="actor:c7-forged-decision",
        authority_digest="a" * 64,
        authority_epoch=1,
        canonical_base_revision=0,
        canonical_base_incarnation="canonical-base-v1",
        canonical_object_id="doc:c7:forged-decision",
    )
    assert rejected.failure_code == "input_closure_mismatch"
    assert "exact envelope selector" in rejected.reason


def test_forged_envelope_order_provenance_candidate_rejected_after_recompute() -> None:
    snapshot, envelope, _legacy, decision, trace, _ = _run_mode("structured_json")
    candidate = trace.outcome
    assert isinstance(candidate, StructuredMaterialCandidate)

    def verify_forged(forged: StructuredMaterialCandidate) -> Any:
        return verify_structured_candidate(
            snapshot=snapshot,
            envelope=envelope,
            decision=decision,
            candidate=forged,
            expected_candidate_digest=candidate.candidate_digest,
            expected_project_key=candidate.project_key,
            actor="actor:c7-forge",
            authority_digest="a" * 64,
            authority_epoch=1,
            canonical_base_revision=1,
            canonical_base_incarnation="canonical-base-v1",
            canonical_object_id="doc:c7:test",
        )

    forged_envelope = dataclasses.replace(
        candidate, envelope_digest="0" * 64, candidate_digest=""
    )
    assert forged_envelope.candidate_digest != candidate.candidate_digest
    rejected = verify_forged(forged_envelope)
    assert rejected.failure_code == "envelope_digest_mismatch"

    forged_order = dataclasses.replace(
        candidate,
        ordered_source_refs=(snapshot.snapshot_ref, "file:///forged"),
        ordered_source_closure_digest="",
        candidate_digest="",
    )
    assert forged_order.candidate_digest != candidate.candidate_digest
    rejected = verify_forged(forged_order)
    assert rejected.failure_code == "ordered_source_mismatch"

    forged_provenance = dataclasses.replace(
        candidate,
        provenance_closure=(
            snapshot.snapshot_ref,
            envelope.envelope_digest,
            decision.decision_digest,
            "forged:provenance",
        ),
        provenance_closure_digest="",
        candidate_digest="",
    )
    assert forged_provenance.candidate_digest != candidate.candidate_digest
    rejected = verify_forged(forged_provenance)
    assert rejected.failure_code == "provenance_mismatch"

    self_consistent_payload = dataclasses.replace(
        candidate,
        structured_payload={"mutated": True},
        payload_content_digest="",
        candidate_digest="",
    )
    assert self_consistent_payload.candidate_digest != candidate.candidate_digest
    rejected = verify_forged(self_consistent_payload)
    assert rejected.failure_code == "expected_candidate_digest_mismatch"

    with pytest.raises(TypeError, match="closed staging-only enum"):
        dataclasses.replace(candidate, authority="canonical_write_allowed")


def test_caller_text_override_must_equal_raw_decode() -> None:
    snapshot = capture_raw_snapshot_exact(
        project_key="demo_proj",
        source_locator="file:///tmp/c7-text",
        raw_bytes=b"exact raw text",
        revision=1,
        incarnation="inc-text",
        mime_type="text/plain",
        provenance_refs=("ingest.c7.text.v1",),
    )
    with pytest.raises(ValueError, match="must equal the exact raw UTF-8 decode"):
        normalize_ingest_envelope(
            snapshot=snapshot,
            input_kind="url_driven_external",
            content_format="plain_text",
            text="forged text",
        )
    envelope = normalize_ingest_envelope(
        snapshot=snapshot,
        input_kind="url_driven_external",
        content_format="plain_text",
        text=snapshot.raw_bytes.decode("utf-8"),
    )
    assert envelope.normalized_text == "exact raw text"


def test_effective_time_falls_back_to_source_time() -> None:
    snapshot = capture_raw_snapshot_exact(
        project_key="demo_proj",
        source_locator="file:///tmp/c7-time",
        raw_bytes=b"timed content",
        revision=1,
        incarnation="inc-time",
        mime_type="text/plain",
        provenance_refs=("ingest.c7.time.v1",),
    )
    processed_time = "2026-01-01T00:00:00+00:00"
    source_time = "2026-01-01T23:04:05+00:00"
    envelope = normalize_ingest_envelope(
        snapshot=snapshot,
        input_kind="url_driven_external",
        content_format="plain_text",
        source_time=source_time,
        processed_time=processed_time,
    )
    assert envelope.source_time == source_time
    assert envelope.effective_time == source_time
    assert envelope.time_provenance == "source_time"


def test_future_source_time_falls_back_to_processed_with_marker() -> None:
    snapshot = capture_raw_snapshot_exact(
        project_key="demo_proj",
        source_locator="file:///tmp/c7-future-time",
        raw_bytes=b"future timed content",
        revision=1,
        incarnation="inc-future-time",
        mime_type="text/plain",
        provenance_refs=("ingest.c7.future-time.v1",),
    )
    processed_time = "2026-01-01T00:00:00+00:00"
    future_source = "2026-01-03T00:00:00+00:00"
    rejected = normalize_ingest_envelope(
        snapshot=snapshot,
        input_kind="url_driven_external",
        content_format="plain_text",
        source_time=future_source,
        processed_time=processed_time,
    )
    assert rejected.source_time == future_source
    assert rejected.effective_time == processed_time
    assert rejected.time_provenance == "source_time_future_rejected"

    boundary_source = "2026-01-02T00:00:00+00:00"
    accepted = normalize_ingest_envelope(
        snapshot=snapshot,
        input_kind="url_driven_external",
        content_format="plain_text",
        source_time=boundary_source,
        processed_time=processed_time,
    )
    assert accepted.effective_time == boundary_source
    assert accepted.time_provenance == "source_time"


def test_omitted_processed_time_anchors_to_source_time() -> None:
    snapshot = capture_raw_snapshot_exact(
        project_key="demo_proj",
        source_locator="file:///tmp/c7-anchor",
        raw_bytes=b"anchored content",
        revision=1,
        incarnation="inc-anchor",
        mime_type="text/plain",
        provenance_refs=("ingest.c7.anchor.v1",),
    )
    source_time = "2026-01-02T03:04:05+00:00"
    envelope = normalize_ingest_envelope(
        snapshot=snapshot,
        input_kind="url_driven_external",
        content_format="plain_text",
        source_time=source_time,
    )
    assert envelope.processed_time == source_time
    assert envelope.source_time == source_time
    assert envelope.effective_time == source_time
    assert envelope.time_provenance == "source_time"


def test_explicit_effective_time_and_provenance_must_match_derived() -> None:
    snapshot = capture_raw_snapshot_exact(
        project_key="demo_proj",
        source_locator="file:///tmp/c7-time-drift",
        raw_bytes=b"timed content",
        revision=1,
        incarnation="inc-time-drift",
        mime_type="text/plain",
        provenance_refs=("ingest.c7.time-drift.v1",),
    )
    processed_time = "2026-01-01T00:00:00+00:00"
    source_time = "2026-01-02T00:00:00+00:00"
    with pytest.raises(ValueError, match="must equal the derived"):
        normalize_ingest_envelope(
            snapshot=snapshot,
            input_kind="url_driven_external",
            content_format="plain_text",
            source_time=source_time,
            processed_time=processed_time,
            effective_time=processed_time,
        )
    with pytest.raises(ValueError, match="must equal the derived"):
        normalize_ingest_envelope(
            snapshot=snapshot,
            input_kind="url_driven_external",
            content_format="plain_text",
            source_time=source_time,
            processed_time=processed_time,
            time_provenance="processed_time_fallback",
        )
    envelope = normalize_ingest_envelope(
        snapshot=snapshot,
        input_kind="url_driven_external",
        content_format="plain_text",
        source_time=source_time,
        processed_time=processed_time,
        effective_time=source_time,
        time_provenance="source_time",
    )
    assert envelope.effective_time == source_time
    assert envelope.time_provenance == "source_time"


def test_direct_envelope_construction_cannot_drift() -> None:
    snapshot = capture_raw_snapshot_exact(
        project_key="demo_proj",
        source_locator="file:///tmp/c7-direct-envelope",
        raw_bytes=b"exact raw text",
        revision=1,
        incarnation="inc-direct-envelope",
        mime_type="text/plain",
        provenance_refs=("ingest.c7.direct-envelope.v1",),
    )
    envelope = normalize_ingest_envelope(
        snapshot=snapshot,
        input_kind="url_driven_external",
        content_format="plain_text",
    )
    decision = select_exactly_one_digestion_alternative(envelope)
    forged_text = NormalizedIngestEnvelope(
        snapshot_ref=snapshot.snapshot_ref,
        snapshot_identity_digest=snapshot.snapshot_identity_digest,
        raw_content_digest=snapshot.raw_content_digest,
        raw_byte_length=len(snapshot.raw_bytes),
        source_character_length=len("exact raw text"),
        project_key=snapshot.project_key,
        source_locator=snapshot.source_locator,
        input_kind="url_driven_external",
        content_format="plain_text",
        normalized_text="forged normalized text",
    )
    with pytest.raises(ValueError, match="normalized text does not match"):
        execute_c7_movement(
            snapshot=snapshot,
            envelope=forged_text,
            decision=decision,
            extract=DeterministicExtractPort(),
            chunk=DeterministicChunkPort(),
            summarize=DeterministicSummarizePort(),
            pass_through=DeterministicPassThroughPort(),
        )
    forged_length = NormalizedIngestEnvelope(
        snapshot_ref=snapshot.snapshot_ref,
        snapshot_identity_digest=snapshot.snapshot_identity_digest,
        raw_content_digest=snapshot.raw_content_digest,
        raw_byte_length=len(snapshot.raw_bytes),
        source_character_length=1,
        project_key=snapshot.project_key,
        source_locator=snapshot.source_locator,
        input_kind="url_driven_external",
        content_format="plain_text",
        normalized_text="exact raw text",
    )
    with pytest.raises(ValueError, match="source character length does not match"):
        execute_c7_movement(
            snapshot=snapshot,
            envelope=forged_length,
            decision=decision,
            extract=DeterministicExtractPort(),
            chunk=DeterministicChunkPort(),
            summarize=DeterministicSummarizePort(),
            pass_through=DeterministicPassThroughPort(),
        )


def test_instance_execute_substitution_rejected() -> None:
    snapshot, envelope, _legacy, decision, _trace, _ = _run_mode("pass_through")
    port = DeterministicPassThroughPort()
    port.execute = lambda *args, **kwargs: None  # type: ignore[method-assign]
    with pytest.raises(TypeError, match="exact built-in class implementation"):
        execute_c7_movement(
            snapshot=snapshot,
            envelope=envelope,
            decision=decision,
            extract=DeterministicExtractPort(),
            chunk=DeterministicChunkPort(),
            summarize=DeterministicSummarizePort(),
            pass_through=port,
        )


def test_instance_finish_substitution_and_state_override_rejected() -> None:
    snapshot, envelope, _legacy, decision, _trace, _ = _run_mode("pass_through")
    finish_port = DeterministicPassThroughPort()
    finish_port._finish = lambda *args, **kwargs: None  # type: ignore[method-assign]
    with pytest.raises(TypeError, match="exact built-in base implementation"):
        execute_c7_movement(
            snapshot=snapshot,
            envelope=envelope,
            decision=decision,
            extract=DeterministicExtractPort(),
            chunk=DeterministicChunkPort(),
            summarize=DeterministicSummarizePort(),
            pass_through=finish_port,
        )

    state_port = DeterministicPassThroughPort()
    state_port.forbidden_state = True  # type: ignore[attr-defined]
    with pytest.raises(ValueError, match="forbidden instance state"):
        execute_c7_movement(
            snapshot=snapshot,
            envelope=envelope,
            decision=decision,
            extract=DeterministicExtractPort(),
            chunk=DeterministicChunkPort(),
            summarize=DeterministicSummarizePort(),
            pass_through=state_port,
        )


def test_provenance_refs_preserve_ordered_duplicates_in_identity() -> None:
    duplicated = capture_raw_snapshot_exact(
        project_key="demo_proj",
        source_locator="file:///tmp/c7-provenance",
        raw_bytes=b"same bytes",
        revision=1,
        incarnation="inc-provenance",
        mime_type="text/plain",
        provenance_refs=("ingest.c7.a.v1", "ingest.c7.a.v1", " ", "ingest.c7.b.v1"),
    )
    deduped = capture_raw_snapshot_exact(
        project_key="demo_proj",
        source_locator="file:///tmp/c7-provenance",
        raw_bytes=b"same bytes",
        revision=1,
        incarnation="inc-provenance",
        mime_type="text/plain",
        provenance_refs=("ingest.c7.a.v1", "ingest.c7.b.v1"),
    )
    assert duplicated.provenance_refs == (
        "ingest.c7.a.v1",
        "ingest.c7.a.v1",
        "ingest.c7.b.v1",
    )
    assert duplicated.raw_content_digest == deduped.raw_content_digest
    assert duplicated.snapshot_identity_digest != deduped.snapshot_identity_digest
    assert duplicated.snapshot_ref != deduped.snapshot_ref


def test_exact_builtin_port_class_rejects_subclass() -> None:
    class SubclassPassThroughPort(DeterministicPassThroughPort):
        pass

    snapshot, envelope, _legacy, decision, _trace, _ports = _run_mode("pass_through")
    with pytest.raises(TypeError, match="exact built-in C7 port class"):
        execute_c7_movement(
            snapshot=snapshot,
            envelope=envelope,
            decision=decision,
            extract=DeterministicExtractPort(),
            chunk=DeterministicChunkPort(),
            summarize=DeterministicSummarizePort(),
            pass_through=SubclassPassThroughPort(),
        )
