"""Report staging plus admission/delivery interface contracts for C8.

P4 ahead-of-time family-local scaffold: report rows never manufacture source
facts, and admission/delivery exist only as pure contract values and Protocol
interfaces.  This module never calls admission, export, delivery, provider or
store code.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Annotated, Literal, Protocol

from app.successor_runtime.capabilities.knowledge_common import (
    KNOWLEDGE_REPORT_ADMISSION_INTERFACE_CONTRACT,
    KNOWLEDGE_REPORT_DELIVERY_INTERFACE_CONTRACT,
    KnowledgeResearchArtifactCandidate,
    CitationClosure,
    KnowledgeRead,
    Provenance,
    ReadHandle,
    ReportAdmissionReadback,
    ResearchDraftArtifact,
    TestOnlySealedValue,
    UnavailableProjection,
    knowledge_canonical_digest,
    research_draft_artifact_digest,
    reject_knowledge_unavailable,
)
from app.successor_runtime.capabilities.knowledge_common import (
    ReportAdmissionIntent as MovementReportAdmissionIntent,
)
from app.successor_runtime.capabilities.knowledge_common import (
    ReportDeliveryIntent as MovementReportDeliveryIntent,
)
from app.successor_runtime.capabilities.knowledge_common import (
    ReportExportPreparation as MovementReportExportPreparation,
)
from app.successor_runtime.capabilities.knowledge_common import (
    ReportStage as MovementReportStage,
)
from app.successor_runtime.capabilities.knowledge_common import (
    ReportVerification as MovementReportVerification,
)
from app.successor_runtime.research.artifacts import (
    ResearchArtifact,
    artifact_exact_ref,
)

ReportStage = MovementReportStage
ReportVerification = MovementReportVerification
ReportExportPreparation = MovementReportExportPreparation

__all__ = [
    "REPORT_ADMISSION_CONTRACT",
    "REPORT_DELIVERY_CONTRACT",
    "REPORT_STAGE_SEQUENCE",
    "REPORT_STAGING_SCHEMA",
    "ReportAdmissionContract",
    "ReportAdmissionIntent",
    "ReportAdmissionReadback",
    "ReportArtifact",
    "ReportDeliveryContract",
    "ReportDeliveryIntent",
    "ReportExportPreparation",
    "ReportRow",
    "ReportStage",
    "ReportVerification",
    "build_knowledge_research_artifact_candidate",
    "build_report_admission_intent",
    "build_report_admission_intent_v2",
    "build_report_artifact",
    "build_report_delivery_intent",
    "build_report_delivery_intent_v2",
    "build_report_stage",
    "confirm_report_admission_readback",
    "prepare_report_export",
    "research_artifact_from_candidate",
    "verify_report_stage",
]

REPORT_STAGING_SCHEMA = "mrw.successor.c8.report-staging.v1"
REPORT_ADMISSION_CONTRACT = KNOWLEDGE_REPORT_ADMISSION_INTERFACE_CONTRACT
REPORT_DELIVERY_CONTRACT = KNOWLEDGE_REPORT_DELIVERY_INTERFACE_CONTRACT
REPORT_STAGE_SEQUENCE = (
    "source_reads",
    "report_rows",
    "report_artifact",
    "admission_intent",
    "delivery_intent",
)


@dataclass(frozen=True, slots=True)
class ReportRow:
    report_id: str
    project_key: str
    source_key: str
    status: str
    evidence: str | None
    handle: ReadHandle
    provenance: Provenance


@dataclass(frozen=True, slots=True)
class ReportArtifact:
    report_id: str
    project_key: str
    topic: str
    rows: tuple[ReportRow, ...]
    artifact_digest: str
    staging_sequence: tuple[str, ...]
    provenance: Provenance
    declared_loss: tuple[str, ...] = (
        "export_body",
        "admission_receipt",
        "delivery_receipt",
    )
    source_identities: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReportAdmissionIntent:
    contract_version: str
    report_id: str
    project_key: str
    artifact_digest: str
    admitted: bool = False
    reason: str = "interface_contract_only"


@dataclass(frozen=True, slots=True)
class ReportDeliveryIntent:
    contract_version: str
    report_id: str
    project_key: str
    artifact_digest: str
    target_kind: str
    delivered: bool = False
    reason: str = "interface_contract_only"


class ReportAdmissionContract(Protocol):
    """Admission interface contract; not called by this scaffold."""

    def admit(self, intent: ReportAdmissionIntent) -> ReportAdmissionIntent: ...


class ReportDeliveryContract(Protocol):
    """Delivery/export interface contract; not called by this scaffold."""

    def deliver(self, intent: ReportDeliveryIntent) -> ReportDeliveryIntent: ...


def build_report_artifact(
    *,
    report_id: str,
    project_key: str,
    topic: str,
    source_reads: tuple[KnowledgeRead, ...],
) -> Annotated[  # NonAuthoritative
    ReportArtifact,
    Literal["kit:non-authoritative derived_as=view fact_source=report_identity_inputs+source_reads witness=test:test_w06_successor_authority_metadata"],
]:
    rows: list[ReportRow] = []
    for read in source_reads:
        if read.handle.project_key != project_key:
            reject_knowledge_unavailable(
                "report source handles must belong to the report project"
            )
        if not read.provenance.canonical_identity.startswith(
            f"knowledge:{project_key}:"
        ):
            reject_knowledge_unavailable(
                "report source provenance is not closed under the report project"
            )
        evidence_refs = read.fields.get("evidence_refs")
        if evidence_refs is None:
            rows.append(
                ReportRow(
                    report_id=report_id,
                    project_key=project_key,
                    source_key=read.item.key,
                    status="unavailable",
                    evidence=None,
                    handle=read.handle,
                    provenance=read.provenance,
                )
            )
            continue
        rows.append(
            ReportRow(
                report_id=report_id,
                project_key=project_key,
                source_key=read.item.key,
                status="ready",
                evidence=read.fields.get("canonical_statement"),
                handle=read.handle,
                provenance=read.provenance,
            )
        )
    row_observations = [
        {
            "source_key": row.source_key,
            "status": row.status,
            "handle_id": row.handle.handle_id,
            "canonical_identity": row.provenance.canonical_identity,
            "canonical_digest": row.provenance.canonical_digest,
            "canonical_revision": row.provenance.canonical_revision,
            "canonical_incarnation": row.provenance.canonical_incarnation,
        }
        for row in rows
    ]
    closure = {
        "source_identities": [
            read.provenance.canonical_identity for read in source_reads
        ],
        "source_digests": [read.provenance.canonical_digest for read in source_reads],
        "handle_ids": [read.handle.handle_id for read in source_reads],
    }
    artifact_digest = knowledge_canonical_digest(
        {
            "report_id": report_id,
            "project_key": project_key,
            "topic": topic,
            "rows": row_observations,
            "closure": closure,
        }
    )
    provenance = Provenance(
        projection_name="report.staged_artifact",
        canonical_identity=(
            source_reads[0].provenance.canonical_identity if source_reads else ""
        ),
        canonical_digest=(
            source_reads[0].provenance.canonical_digest if source_reads else ""
        ),
        canonical_revision=(
            source_reads[0].provenance.canonical_revision if source_reads else 1
        ),
        canonical_incarnation=(
            source_reads[0].provenance.canonical_incarnation
            if source_reads
            else "knowledge-generation-1"
        ),
    )
    return ReportArtifact(
        report_id=report_id,
        project_key=project_key,
        topic=topic,
        rows=tuple(rows),
        artifact_digest=artifact_digest,
        staging_sequence=REPORT_STAGE_SEQUENCE,
        provenance=provenance,
        source_identities=tuple(
            read.provenance.canonical_identity for read in source_reads
        ),
    )


def build_report_admission_intent(
    artifact: ReportArtifact,
) -> Annotated[  # NonAuthoritative
    ReportAdmissionIntent,
    Literal["kit:non-authoritative derived_as=view fact_source=ReportArtifact witness=test:test_w06_successor_authority_metadata"],
]:
    return ReportAdmissionIntent(
        contract_version=REPORT_ADMISSION_CONTRACT,
        report_id=artifact.report_id,
        project_key=artifact.project_key,
        artifact_digest=artifact.artifact_digest,
        admitted=False,
        reason="interface_contract_only; admission is not called",
    )


def build_report_delivery_intent(
    artifact: ReportArtifact,
    *,
    target_kind: str = "html_export",
) -> Annotated[  # NonAuthoritative
    ReportDeliveryIntent,
    Literal["kit:non-authoritative derived_as=view fact_source=ReportArtifact+target_kind witness=test:test_w06_successor_authority_metadata"],
]:
    return ReportDeliveryIntent(
        contract_version=REPORT_DELIVERY_CONTRACT,
        report_id=artifact.report_id,
        project_key=artifact.project_key,
        artifact_digest=artifact.artifact_digest,
        target_kind=target_kind,
        delivered=False,
        reason="interface_contract_only; export/delivery is not called",
    )


def build_report_stage(
    *,
    stage_id: str,
    project_key: str,
    artifact: ResearchDraftArtifact,
    citation_closure: CitationClosure,
) -> Annotated[  # NonAuthoritative
    MovementReportStage,
    Literal["kit:non-authoritative derived_as=view fact_source=ResearchDraftArtifact+CitationClosure witness=test:test_w06_successor_authority_metadata"],
]:
    if artifact.project_key != project_key:
        reject_knowledge_unavailable("report stage project scope mismatch")
    if citation_closure != artifact.citation_closure:
        reject_knowledge_unavailable("report stage citation closure mismatch")
    artifact_sources = tuple(entry.identity for entry in artifact.provenance_closure)
    return MovementReportStage(
        stage_id=stage_id,
        project_key=project_key,
        artifact_id=artifact.artifact_id,
        artifact_digest=artifact.artifact_digest,
        source_identities=artifact_sources,
        citation_closure=citation_closure,
    )


def verify_report_stage(
    stage: ReportStage,
    *,
    citation_closure: CitationClosure,
    artifact: ResearchDraftArtifact,
) -> MovementReportVerification:
    def closure_digest(closure: CitationClosure) -> str:
        return knowledge_canonical_digest(
            {
                "citation_ids": [ref.citation_id for ref in closure.refs],
                "source_digests": [ref.source_digest for ref in closure.refs],
            }
        )

    valid = (
        stage.citation_closure == citation_closure
        and closure_digest(citation_closure) == closure_digest(stage.citation_closure)
        and research_draft_artifact_digest(artifact) == stage.artifact_digest
        and stage.source_identities
        == tuple(entry.identity for entry in artifact.provenance_closure)
    )
    return MovementReportVerification(
        verification_id=f"verification:{stage.stage_id}",
        stage_id=stage.stage_id,
        project_key=stage.project_key,
        artifact_digest=stage.artifact_digest,
        citation_closure_digest=closure_digest(citation_closure),
        state="VERIFIED" if valid else "UNVERIFIED",
        failure_reason=None if valid else "citation closure mismatch",
    )


def build_report_admission_intent_v2(
    verification: ReportVerification,
) -> Annotated[  # NonAuthoritative
    MovementReportAdmissionIntent,
    Literal["kit:non-authoritative derived_as=view fact_source=ReportVerification witness=test:test_w06_successor_authority_metadata"],
]:
    if verification.state != "VERIFIED":
        reject_knowledge_unavailable("admission intent requires verified report stage")
    return MovementReportAdmissionIntent(
        intent_id=f"admission:{verification.verification_id}",
        verification_id=verification.verification_id,
        project_key=verification.project_key,
        artifact_digest=verification.artifact_digest,
    )


def confirm_report_admission_readback(
    intent: MovementReportAdmissionIntent,
    *,
    witness: object,
    verifier_registry: object,
    verification: ReportVerification,
    authority_epoch: int = 1,
) -> ReportAdmissionReadback:
    if isinstance(witness, TestOnlySealedValue):
        reject_knowledge_unavailable(
            "production admission readback rejects TEST_ONLY witness"
        )
    return confirm_report_admission_readback_test_only(
        intent,
        witness=witness,
        verifier_registry=verifier_registry,
        verification=verification,
        authority_epoch=authority_epoch,
    )


def confirm_report_admission_readback_test_only(
    intent: MovementReportAdmissionIntent,
    *,
    witness: object,
    verifier_registry: object,
    verification: ReportVerification,
    authority_epoch: int = 1,
) -> ReportAdmissionReadback:
    registered = verifier_registry.resolve(verification.verification_id)
    if registered is None or registered != verification:
        reject_knowledge_unavailable(
            "verification is not a registered exact verifier entry"
        )
    if witness._secret is not verifier_registry._authority._secret:
        reject_knowledge_unavailable("verification witness is not authentic")
    if (
        witness.verification_id != verification.verification_id
        or witness.object_digest != verification.object_digest
    ):
        reject_knowledge_unavailable("verification witness mismatch")
    if verification.state != "VERIFIED":
        reject_knowledge_unavailable(
            "admission readback requires a verified exact verification"
        )
    return ReportAdmissionReadback(
        readback_id=f"readback:{intent.intent_id}",
        intent_id=intent.intent_id,
        project_key=intent.project_key,
        artifact_digest=intent.artifact_digest,
        state="ADMITTED",
        authority_epoch=authority_epoch,
        verification_id=verification.verification_id,
        authority_kind=verifier_registry.authority_id,
        authority_digest=verifier_registry.authority_digest,
        verifier_registry_id=verifier_registry.registry_id,
        verifier_registry_digest=verifier_registry.registry_digest,
    )


def prepare_report_export(
    readback: ReportAdmissionReadback,
    *,
    export_format: str = "markdown",
) -> MovementReportExportPreparation:
    if readback.state != "ADMITTED":
        reject_knowledge_unavailable(
            "export preparation requires exact admitted readback"
        )
    return MovementReportExportPreparation(
        preparation_id=f"export-prep:{readback.readback_id}",
        project_key=readback.project_key,
        artifact_digest=readback.artifact_digest,
        export_format=export_format,
        state="PREPARED",
    )


def build_report_delivery_intent_v2(
    preparation: ReportExportPreparation,
    *,
    approval_digest: str,
    approval_epoch: int,
    external: bool = False,
) -> Annotated[  # NonAuthoritative
    MovementReportDeliveryIntent,
    Literal["kit:non-authoritative derived_as=view fact_source=ReportExportPreparation+approval_inputs witness=test:test_w06_successor_authority_metadata"],
]:
    if preparation.state != "PREPARED":
        reject_knowledge_unavailable(
            "delivery intent requires prepared export preparation"
        )
    if not approval_digest:
        reject_knowledge_unavailable(
            "delivery intent requires non-empty approval digest"
        )
    if approval_epoch < 1:
        reject_knowledge_unavailable("delivery intent requires positive approval epoch")
    if external:
        reject_knowledge_unavailable(
            "external delivery rejected in this local milestone"
        )
    return MovementReportDeliveryIntent(
        intent_id=f"delivery:{preparation.preparation_id}",
        project_key=preparation.project_key,
        preparation_id=preparation.preparation_id,
        artifact_digest=preparation.artifact_digest,
        state="APPROVED",
        approval_digest=approval_digest,
        approval_epoch=approval_epoch,
    )


def build_knowledge_research_artifact_candidate(
    *,
    candidate_id: str,
    draft: ResearchDraftArtifact,
    verification: ReportVerification,
    markdown_ref: str,
    markdown_digest: str,
    provenance_digest: str,
    exact_claim_refs: tuple[str, ...] = (),
    exact_evidence_refs: tuple[str, ...] = (),
    canonical_revision: int = 1,
    canonical_incarnation: str = "research-artifact-1",
    witness: object | None = None,
) -> Annotated[  # NonAuthoritative
    KnowledgeResearchArtifactCandidate,
    "kit:prepared-command "
    "effect_boundary=c8_report.research_artifact_from_candidate "
    "witness=test:test_c8_research_artifact_candidate_prepared_command_metadata",
]:
    if isinstance(witness, TestOnlySealedValue):
        reject_knowledge_unavailable(
            "research artifact adapter rejects TEST_ONLY witness"
        )
    if verification.state != "VERIFIED":
        reject_knowledge_unavailable(
            "research artifact adapter requires a verified draft"
        )
    if verification.project_key != draft.project_key:
        reject_knowledge_unavailable(
            "research artifact adapter rejects cross-project draft"
        )
    if verification.artifact_digest != draft.artifact_digest:
        reject_knowledge_unavailable(
            "research artifact adapter rejects stale verification"
        )
    metadata = {
        "candidate_id": candidate_id,
        "project_key": draft.project_key,
        "markdown_ref": markdown_ref,
        "markdown_digest": markdown_digest,
        "source_draft_digest": draft.artifact_digest,
        "verification_digest": verification.object_digest,
        "provenance_digest": provenance_digest,
        "citation_closure": [ref.citation_id for ref in draft.citation_closure.refs],
        "source_base_revision": draft.base_revision,
        "source_base_incarnation": draft.base_incarnation,
        "canonical_revision": canonical_revision,
        "canonical_incarnation": canonical_incarnation,
    }
    metadata_bytes = json.dumps(
        metadata,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return KnowledgeResearchArtifactCandidate(
        candidate_id=candidate_id,
        project_key=draft.project_key,
        canonical_metadata_bytes=metadata_bytes,
        canonical_metadata_digest=hashlib.sha256(metadata_bytes).hexdigest(),
        markdown_ref=markdown_ref,
        markdown_digest=markdown_digest,
        source_draft_digest=draft.artifact_digest,
        verification_digest=verification.object_digest,
        provenance_digest=provenance_digest,
        claim_closure=tuple(exact_claim_refs or ()),
        evidence_relation_closure=tuple(exact_evidence_refs or ()),
        citation_closure=tuple(ref.citation_id for ref in draft.citation_closure.refs),
        source_base_revision=draft.base_revision,
        source_base_incarnation=draft.base_incarnation,
        canonical_revision=canonical_revision,
        canonical_incarnation=canonical_incarnation,
    )


def research_artifact_from_candidate(
    candidate: KnowledgeResearchArtifactCandidate,
) -> ResearchArtifact:
    artifact = ResearchArtifact(
        artifact_id=candidate.candidate_id,
        content_ref=candidate.markdown_ref,
        content_digest=None,
        claim_closure=candidate.claim_closure,
        evidence_relation_closure=candidate.evidence_relation_closure,
        citation_closure=candidate.citation_closure,
        format="markdown",
        revision=candidate.canonical_revision,
        lifecycle_state=candidate.lifecycle_state,
    )
    assert artifact_exact_ref(artifact)
    return artifact
