"""Focused P0-C tests for capability-local first-specimen interpreters."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.first_specimen import (
    CanonicalReadInput,
    CaptureDocumentSnapshotInput,
    ClaimOrGapInput,
    EvidenceQualificationInput,
    InternalExportInput,
    MarkdownComposeInput,
)
from app.successor_runtime.capabilities.first_specimen_interpreters import (
    CapturedDocumentValue,
    ClaimOrGapOutput,
    ComposedMarkdownArtifact,
    FirstSpecimenInterpreters,
    InternalExportObservation,
    InterpreterFailure,
    InterpreterOutcomeUnknown,
    InterpreterSuccess,
    VerifiedDeliveryBinding,
    artifact_exact_ref,
)
from app.successor_runtime.research import (
    CapturedMaterialSnapshot,
    Claim,
    DeliveryIntent,
    EvidenceQualification,
    Gap,
    MaterialRef,
    ResearchArtifact,
)
from app.successor_runtime.research.evidence import Validity
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope

NOW = datetime(2026, 8, 31, 9, 0, tzinfo=UTC)
PROJECT_SCOPE_DIGEST = "1" * 64
AUTHORITY_DIGEST = "2" * 64
PROVENANCE_DIGEST = "3" * 64


def _scope() -> RuntimeScope:
    return RuntimeScope(
        project_scope=ProjectScopeRef(
            project_key="p0c-demo",
            resolved_schema="mrw_p_p0c_demo",
            project_registry_revision=4,
            incarnation="scope-incarnation:p0c-demo:4",
            scope_digest=PROJECT_SCOPE_DIGEST,
        ),
        actor_id="p0c-runtime-node",
    )


def _with_payload_digest(cls: type, **values: object):
    return cls(**values, payload_digest=content_digest(values))


class _DocumentReader:
    def __init__(self, exact_bytes: bytes) -> None:
        self.exact_bytes = exact_bytes


class _DeliveryValidator:
    def __init__(self) -> None:
        self.authority_digest = AUTHORITY_DIGEST
        self.approval_refs = ("approval:human:p0c",)
        self.expires_at = NOW + timedelta(hours=1)
        self.calls = 0

    def require_current(
        self,
        scope: RuntimeScope,
        payload: InternalExportInput,
        intent: DeliveryIntent,
        artifact: ResearchArtifact,
        *,
        now: datetime,
    ) -> VerifiedDeliveryBinding:
        self.calls += 1
        assert scope == _scope()
        assert artifact.lifecycle_state == "ADMITTED"
        assert intent.content_digest is not None
        return VerifiedDeliveryBinding.from_content(
            delivery_intent_digest=intent.content_digest,
            approved_payload_digest=intent.content_digest,
            approval_refs=self.approval_refs,
            approval_epoch=7,
            authority_digest=self.authority_digest,
            authority_epoch=11,
            validated_at=now - timedelta(seconds=1),
            expires_at=self.expires_at,
        )


class _InternalExporter:
    def __init__(self) -> None:
        self.observation: InternalExportObservation | None = None
        self.effect_calls = 0
        self.readback_calls = 0

    def readback(
        self,
        scope: RuntimeScope,
        *,
        idempotency_key: str,
        delivery_intent_digest: str,
        artifact_bytes_digest: str,
    ) -> InternalExportObservation | None:
        assert scope == _scope()
        self.readback_calls += 1
        return self.observation

    def write_once(
        self,
        scope: RuntimeScope,
        *,
        idempotency_key: str,
        delivery_intent_digest: str,
        artifact_bytes_digest: str,
        exact_bytes: bytes,
        attempt_ref: str,
    ) -> InternalExportObservation:
        assert scope == _scope()
        assert hashlib.sha256(exact_bytes).hexdigest() == artifact_bytes_digest
        self.effect_calls += 1
        if self.observation is None:
            self.observation = InternalExportObservation.from_content(
                idempotency_key=idempotency_key,
                delivery_intent_digest=delivery_intent_digest,
                artifact_bytes_digest=artifact_bytes_digest,
                attempt_ref=attempt_ref,
                provider_locator=(f"internal://export/sha256/{artifact_bytes_digest}"),
                outcome_time=NOW,
            )
        return self.observation


@pytest.fixture
def interpreter_stack():
    reader = _DocumentReader("第一 specimen 原始材料".encode())
    validator = _DeliveryValidator()
    exporter = _InternalExporter()
    interpreters = FirstSpecimenInterpreters(
        delivery_validator=validator,
        internal_export=exporter,
        clock=lambda: NOW,
    )
    return interpreters, reader, validator, exporter


def _capture(
    interpreters: FirstSpecimenInterpreters,
    reader: _DocumentReader,
) -> CapturedDocumentValue:
    digest = hashlib.sha256(reader.exact_bytes).hexdigest()
    payload = _with_payload_digest(
        CaptureDocumentSnapshotInput,
        source_ref="source:document:101",
        document_id=101,
        content_sha256_hex=digest,
        observed_updated_at="2026-08-31T09:00:00Z",
        byte_size=len(reader.exact_bytes),
    )
    captured = CapturedDocumentValue(
        exact_bytes=reader.exact_bytes,
        snapshot=CapturedMaterialSnapshot(
            value_ref=f"successor-value:sha256:{digest}",
            document_id=101,
            observed_text_hash=digest,
            observed_updated_at=NOW,
            byte_size=len(reader.exact_bytes),
        ),
        exact_bytes_digest=digest,
    )
    result = interpreters.capture_document_snapshot(payload, captured)
    assert isinstance(result, InterpreterSuccess)
    assert result.disposition == "SUCCEEDED"
    assert isinstance(result.value, CapturedDocumentValue)
    return result.value


def _material(
    interpreters: FirstSpecimenInterpreters,
    captured: CapturedDocumentValue,
) -> MaterialRef:
    payload = _with_payload_digest(
        CanonicalReadInput,
        source_ref="source:document:101",
        locator="document://p0c-demo/101",
        owner_id="legacy_document_store",
        observed_at="2026-08-31T09:00:00Z",
    )
    result = interpreters.read_canonical_ref(payload, captured)
    assert isinstance(result, InterpreterSuccess)
    return result.value


def _qualification(
    interpreters: FirstSpecimenInterpreters,
    material: MaterialRef,
) -> EvidenceQualification:
    payload = _with_payload_digest(
        EvidenceQualificationInput,
        qualification_id="qualification:101",
        material_ref=material.material_ref_id,
        inquiry_ref="inquiry:p0c",
        direction="SUPPORTS",
        scope_statement_ref="scope:bounded:p0c",
        uncertainty_profile_ref="uncertainty:explicit",
        verifier_profile_ref="verifier:human-reviewable",
    )
    result = interpreters.qualify_evidence(
        payload,
        project_key="p0c-demo",
        provenance_closure_digest=PROVENANCE_DIGEST,
        validity=Validity(valid_from=NOW, valid_to=None),
        observed_at=NOW,
    )
    assert isinstance(result, InterpreterSuccess)
    return result.value


def _claim(
    interpreters: FirstSpecimenInterpreters,
    qualification: EvidenceQualification,
) -> ClaimOrGapOutput:
    payload = _with_payload_digest(
        ClaimOrGapInput,
        claim_or_gap_id="claim:p0c",
        statement_ref="statement:p0c",
        inquiry_ref="inquiry:p0c",
        support_relation_refs=(qualification.qualification_id,),
        contradiction_relation_refs=(),
        uncertainty_profile_ref="uncertainty:explicit",
        requirement="",
        reason="",
        missing_evidence_or_decision="",
        reopen_policy={},
        closure_condition="",
    )
    result = interpreters.form_claim_or_open_gap(
        payload,
        provenance_closure_digest=PROVENANCE_DIGEST,
    )
    assert isinstance(result, InterpreterSuccess)
    return result.value


def _compose(
    interpreters: FirstSpecimenInterpreters,
    outcome: ClaimOrGapOutput,
    qualification: EvidenceQualification,
    material: MaterialRef,
) -> ComposedMarkdownArtifact:
    outcome_ref = (
        outcome.value.claim_id
        if isinstance(outcome.value, Claim)
        else outcome.value.gap_id
    )
    payload = _with_payload_digest(
        MarkdownComposeInput,
        artifact_id="artifact:p0c",
        claim_closure=(outcome_ref,),
        evidence_relation_closure=(qualification.qualification_id,),
        citation_closure=(material.material_ref_id,),
    )
    result = interpreters.compose_markdown(
        payload,
        outcome,
        qualifications=(qualification,),
        materials=(material,),
    )
    assert isinstance(result, InterpreterSuccess)
    return result.value


def _delivery(
    composed: ComposedMarkdownArtifact,
    *,
    authority_digest: str = AUTHORITY_DIGEST,
) -> tuple[ResearchArtifact, InternalExportInput, DeliveryIntent]:
    artifact = replace(
        composed.artifact,
        lifecycle_state="ADMITTED",
        content_digest=None,
    )
    exact_ref = artifact_exact_ref(artifact)
    payload = _with_payload_digest(
        InternalExportInput,
        delivery_intent_id="delivery-intent:p0c",
        artifact_ref=exact_ref,
        audience="internal-research-review",
        approval_refs=("approval:human:p0c",),
        idempotency_key="p0c-internal-export",
    )
    intent = DeliveryIntent(
        delivery_intent_id=payload.delivery_intent_id,
        artifact_ref=payload.artifact_ref,
        audience=payload.audience,
        channel="internal_export",
        format="markdown",
        approval_refs=payload.approval_refs,
        authority_digest=authority_digest,
        idempotency_key=payload.idempotency_key,
        irreversibility_profile="internal_content_addressed_export",
    )
    return artifact, payload, intent


def _pipeline_before_delivery(interpreter_stack):
    interpreters, reader, validator, exporter = interpreter_stack
    captured = _capture(interpreters, reader)
    material = _material(interpreters, captured)
    qualification = _qualification(interpreters, material)
    outcome = _claim(interpreters, qualification)
    composed = _compose(
        interpreters,
        outcome,
        qualification,
        material,
    )
    return (
        interpreters,
        reader,
        validator,
        exporter,
        captured,
        material,
        qualification,
        outcome,
        composed,
    )


def test_capture_returns_exact_bytes_and_runtime_snapshot_without_ledger_write(
    interpreter_stack,
) -> None:
    interpreters, reader, _, _ = interpreter_stack
    captured = _capture(interpreters, reader)

    assert captured.exact_bytes == reader.exact_bytes
    assert captured.snapshot.document_id == 101
    assert captured.snapshot.value_ref == (
        f"successor-value:sha256:{captured.exact_bytes_digest}"
    )
    assert captured.snapshot.observed_text_hash == captured.exact_bytes_digest


def test_capture_fails_closed_on_payload_or_captured_value_drift(
    interpreter_stack,
) -> None:
    interpreters, reader, _, _ = interpreter_stack
    payload = _with_payload_digest(
        CaptureDocumentSnapshotInput,
        source_ref="source:document:101",
        document_id=101,
        content_sha256_hex="a" * 64,
        observed_updated_at="2026-08-31T09:00:00Z",
        byte_size=len(reader.exact_bytes),
    )
    captured = _capture(interpreters, reader)
    result = interpreters.capture_document_snapshot(payload, captured)
    assert isinstance(result, InterpreterFailure)
    assert result.code == "DOCUMENT_OBSERVATION_MISMATCH"
    assert result.retryable is False


def test_material_and_qualification_preserve_single_owner_relation_semantics(
    interpreter_stack,
) -> None:
    interpreters, reader, _, _ = interpreter_stack
    material = _material(interpreters, _capture(interpreters, reader))
    qualification = _qualification(interpreters, material)

    assert material.snapshot.observed_text_hash is not None
    assert qualification.material_ref == material.material_ref_id
    assert qualification.RELATION_STORAGE == "research_relations_only"
    assert qualification.DUPLICATE_RESEARCH_OBJECT_FORBIDDEN is True
    assert qualification.provenance_closure_digest == PROVENANCE_DIGEST


def test_gap_keeps_support_contradiction_uncertainty_and_provenance_visible(
    interpreter_stack,
) -> None:
    interpreters, _, _, _ = interpreter_stack
    payload = _with_payload_digest(
        ClaimOrGapInput,
        claim_or_gap_id="gap:p0c",
        statement_ref="statement:still-open",
        inquiry_ref="inquiry:p0c",
        support_relation_refs=("qualification:support",),
        contradiction_relation_refs=("qualification:contradiction",),
        uncertainty_profile_ref="uncertainty:high",
        requirement="corroborate the contested observation",
        reason="support and contradiction remain unresolved",
        missing_evidence_or_decision="independent primary source",
        reopen_policy={"mode": "source_delta"},
        closure_condition="one independent primary source admitted",
    )
    result = interpreters.form_claim_or_open_gap(
        payload,
        provenance_closure_digest=PROVENANCE_DIGEST,
    )

    assert isinstance(result, InterpreterSuccess)
    assert isinstance(result.value.value, Gap)
    assert result.value.support_relation_refs == ("qualification:support",)
    assert result.value.contradiction_relation_refs == ("qualification:contradiction",)
    assert result.value.uncertainty_profile_ref == "uncertainty:high"
    assert result.value.provenance_closure_digest == PROVENANCE_DIGEST
    assert result.value.value.reopen_policy["provenance_closure_digest"] == (
        PROVENANCE_DIGEST
    )


def test_markdown_is_deterministic_and_binds_exact_citation_closure(
    interpreter_stack,
) -> None:
    (
        interpreters,
        _,
        _,
        _,
        _,
        material,
        qualification,
        outcome,
        composed,
    ) = _pipeline_before_delivery(interpreter_stack)
    repeated = _compose(
        interpreters,
        outcome,
        qualification,
        material,
    )

    assert repeated == composed
    assert composed.artifact.citation_closure == (material.material_ref_id,)
    assert composed.artifact.evidence_relation_closure == (
        qualification.qualification_id,
    )
    assert composed.artifact.content_ref == (f"sha256:{composed.exact_bytes_digest}")
    assert qualification.qualification_id.encode() in composed.exact_bytes
    assert material.material_ref_id.encode() in composed.exact_bytes


def test_internal_export_is_approval_gated_content_addressed_and_idempotent(
    interpreter_stack,
) -> None:
    (
        interpreters,
        _,
        validator,
        exporter,
        _,
        _,
        _,
        _,
        composed,
    ) = _pipeline_before_delivery(interpreter_stack)
    artifact, payload, intent = _delivery(composed)

    first = interpreters.internal_export(
        _scope(),
        payload,
        delivery_intent=intent,
        artifact=artifact,
        artifact_bytes=composed.exact_bytes,
        attempt_ref="attempt:delivery:1",
    )
    duplicate = interpreters.internal_export(
        _scope(),
        payload,
        delivery_intent=intent,
        artifact=artifact,
        artifact_bytes=composed.exact_bytes,
        attempt_ref="attempt:delivery:reconciliation",
    )

    assert isinstance(first, InterpreterSuccess)
    assert isinstance(duplicate, InterpreterSuccess)
    assert exporter.effect_calls == 1
    assert exporter.readback_calls == 3
    assert validator.calls == 2
    assert duplicate.value == first.value
    assert first.value.attempt_ref == "attempt:delivery:1"
    assert first.value.provider_locator == (
        f"internal://export/sha256/{composed.exact_bytes_digest}"
    )


@pytest.mark.parametrize("drift", ["approval", "authority", "expiry"])
def test_internal_export_rejects_current_approval_or_authority_drift(
    interpreter_stack,
    drift: str,
) -> None:
    (
        interpreters,
        _,
        validator,
        exporter,
        _,
        _,
        _,
        _,
        composed,
    ) = _pipeline_before_delivery(interpreter_stack)
    artifact, payload, intent = _delivery(composed)
    if drift == "approval":
        validator.approval_refs = ("approval:stale",)
    elif drift == "authority":
        validator.authority_digest = "4" * 64
    else:
        validator.expires_at = NOW - timedelta(microseconds=1)

    result = interpreters.internal_export(
        _scope(),
        payload,
        delivery_intent=intent,
        artifact=artifact,
        artifact_bytes=composed.exact_bytes,
        attempt_ref="attempt:delivery:drift",
    )

    assert isinstance(result, InterpreterFailure)
    assert result.code == "DELIVERY_AUTHORITY_OR_APPROVAL_INVALID"
    assert exporter.effect_calls == 0


def test_all_zero_combinator_authority_is_never_implicitly_adopted(
    interpreter_stack,
) -> None:
    (
        interpreters,
        _,
        _,
        exporter,
        _,
        _,
        _,
        _,
        composed,
    ) = _pipeline_before_delivery(interpreter_stack)
    artifact, payload, intent = _delivery(
        composed,
        authority_digest="0" * 64,
    )

    result = interpreters.internal_export(
        _scope(),
        payload,
        delivery_intent=intent,
        artifact=artifact,
        artifact_bytes=composed.exact_bytes,
        attempt_ref="attempt:delivery:zero-authority",
    )

    assert isinstance(result, InterpreterFailure)
    assert "all-zero" in result.message
    assert exporter.effect_calls == 0


def test_missing_post_effect_readback_is_outcome_unknown_not_redispatch(
    interpreter_stack,
) -> None:
    (
        interpreters,
        _,
        _,
        exporter,
        _,
        _,
        _,
        _,
        composed,
    ) = _pipeline_before_delivery(interpreter_stack)
    artifact, payload, intent = _delivery(composed)

    original_readback = exporter.readback

    def readback_then_hide(*args, **kwargs):
        if exporter.effect_calls:
            return None
        return original_readback(*args, **kwargs)

    exporter.readback = readback_then_hide  # type: ignore[method-assign]
    result = interpreters.internal_export(
        _scope(),
        payload,
        delivery_intent=intent,
        artifact=artifact,
        artifact_bytes=composed.exact_bytes,
        attempt_ref="attempt:delivery:unknown",
    )

    assert isinstance(result, InterpreterOutcomeUnknown)
    assert result.disposition == "OUTCOME_UNKNOWN"
    assert exporter.effect_calls == 1


def test_module_has_no_db_network_provider_or_legacy_control_flow_dependency() -> None:
    source = __import__(
        "app.successor_runtime.capabilities.first_specimen_interpreters",
        fromlist=["__file__"],
    ).__file__
    assert source is not None
    text = Path(source).read_text(encoding="utf-8")
    forbidden = (
        "sqlalchemy",
        "successor_migration",
        "app.models",
        "requests",
        "httpx",
        "runtime_work_items",
        "DocumentCanonicalReadPort",
    )
    assert not any(token in text for token in forbidden)
