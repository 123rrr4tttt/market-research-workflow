"""First specimen capability-owned contracts, codecs and typed payload DTOs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.successor_runtime.language.object_contracts import (
    CAPTURE_DOCUMENT_SNAPSHOT_RETURN_CONTRACT_REF,
    CLAIM_OR_GAP_RETURN_CONTRACT_REF,
    DELIVERY_INTENT_RECEIPT_RETURN_CONTRACT_REF,
    EVIDENCE_QUALIFICATION_RETURN_CONTRACT_REF,
    READ_CANONICAL_REF_RETURN_CONTRACT_REF,
    RESEARCH_ARTIFACT_RETURN_CONTRACT_REF,
    RUNTIME_VALUE_RETURN_CONTRACT_REF,
    make_operation_contract,
)
from app.successor_runtime.research import (
    CapturedMaterialSnapshot,
    Claim,
    DeliveryReceiptRef,
    EvidenceQualification,
    Gap,
    MaterialRef,
    ResearchArtifact,
)
from app.successor_runtime.research.object_types import OBJECT_TYPE_BY_ID, ObjectType

from .checksum import content_digest, require_hex64
from .codecs import PayloadCodec, dataclass_codec
from .contracts import OperationContract
from .profiles import (
    AuthorityProfile,
    ContractProfileRef,
    EffectProfile,
    FailureProfile,
    InterpreterProfile,
    ObservationProfile,
    ResourceProfile,
    SemanticProfile,
)

__all__ = [
    "FIRST_SPECIMEN_OPERATION_KINDS",
    "CanonicalReadInput",
    "CaptureDocumentSnapshotInput",
    "CapturedMaterialSnapshot",
    "Claim",
    "ClaimOrGap",
    "ClaimOrGapInput",
    "DeliveryReceiptRef",
    "EvidenceQualification",
    "EvidenceQualificationInput",
    "FirstSpecimenCapabilityBundle",
    "Gap",
    "InternalExportInput",
    "MarkdownComposeInput",
    "MaterialRef",
    "ResearchArtifact",
    "build_first_specimen_bundle",
]


def _object_type(type_id: str) -> ObjectType:
    return OBJECT_TYPE_BY_ID.get(type_id, ObjectType(type_id))


def _profile_ref(profile_id: str, profile_version: str, digest: str) -> ContractProfileRef:
    return ContractProfileRef(
        profile_id=profile_id,
        profile_version=profile_version,
        profile_digest=digest,
    )


def _semantic_profile(
    kind: str,
    *,
    reads: tuple[str, ...],
    creates: tuple[str, ...],
    creates_relations: tuple[str, ...] = (),
) -> SemanticProfile:
    values = dict(
        semantic_profile_id=f"{kind}.semantic",
        semantic_profile_version="1.0.0",
        reads=reads,
        creates=creates,
        creates_relations=creates_relations,
        declared_loss=(),
        observation_profile_ref=f"{kind}.observation",
    )
    return SemanticProfile(**values, profile_digest=content_digest(values))


def _effect_profile(
    kind: str,
    *,
    execution_class: Literal["PURE_TRANSFORM", "EFFECTFUL", "ADMISSION", "PROJECTION"],
    external_visibility: Literal["NONE", "INTERNAL_ONLY", "EXTERNAL"],
    irreversible: bool = False,
    human_approval_required: bool = False,
) -> EffectProfile:
    values = dict(
        effect_profile_id=f"{kind}.effect",
        effect_profile_version="1.0.0",
        execution_class=execution_class,
        external_visibility=external_visibility,
        network_required=False,
        irreversible=irreversible,
        cancellation_points=("step_boundary",),
        internal_export_only=external_visibility == "INTERNAL_ONLY",
        human_approval_required=human_approval_required,
        external_acquisition=False,
        idempotency_profile_ref="logical_request_id",
    )
    return EffectProfile(**values, profile_digest=content_digest(values))


def _resource_profile(kind: str, *, soft_limit: int = 240, hard_limit: int = 300) -> ResourceProfile:
    values = dict(
        resource_profile_id=f"{kind}.resource",
        resource_profile_version="1.0.0",
        resource_classes=("cpu",),
        concurrency_key="project",
        budget_units="operation",
        default_soft_limit_seconds=soft_limit,
        default_hard_limit_seconds=hard_limit,
        node_profile_selector="any",
        budget_ref="mrw.functorial-successor.budget.p0-a.v1",
        deadline_policy_ref="mrw.functorial-successor.deadline.p0-a.v1",
        node_profile_requirements=("any",),
        units=1,
    )
    return ResourceProfile(**values, profile_digest=content_digest(values))


def _failure_profile(kind: str, *, retryable: bool = False, readback: str = "none") -> FailureProfile:
    values = dict(
        failure_profile_id=f"{kind}.failure",
        failure_profile_version="1.0.0",
        typed_failures=("INVALID_INPUT", "INTERPRETER_UNAVAILABLE", "ASSIGNMENT_BINDING_MISMATCH"),
        retryable=retryable,
        degraded_acceptable=False,
        unknown_outcome_supported=False,
        readback_or_compensation=readback,
        failure_union_ref="mrw.functorial-successor.failures.p0-a.v1",
        retryable_failure_kinds=("INTERPRETER_UNAVAILABLE",) if retryable else (),
        readback_profile_ref=None if readback == "none" else readback,
        compensation_profile_ref=None,
    )
    return FailureProfile(**values, profile_digest=content_digest(values))


def _authority_profile(
    kind: str,
    *,
    canonical_owner: str,
    approval_required: bool = False,
    approval_kinds: tuple[str, ...] = (),
) -> AuthorityProfile:
    values = dict(
        authority_profile_id=f"{kind}.authority",
        authority_profile_version="1.0.0",
        grant_scopes=("project",),
        approval_required=approval_required,
        approval_kinds=approval_kinds,
        credential_refs=(),
        canonical_owner=canonical_owner,
        revalidation_points=("claim_time",),
        authority_epoch=1,
    )
    return AuthorityProfile(**values, profile_digest=content_digest(values))


def _interpreter_profile(
    kind: str,
    *,
    readback: str | None,
    receipt_codec_ref: str,
) -> InterpreterProfile:
    values = dict(
        interpreter_profile_id=f"{kind}.interpreter",
        interpreter_profile_version="1.0.0",
        supported_contract_kinds=(kind,),
        supported_contract_refs=(),
        dependency_digest=content_digest({"interpreter": f"successor-native.{kind}", "version": "1.0.0"}),
        security_profile_ref="mrw.functorial-successor.security.p0-a.v1",
        resource_profile_ref=f"{kind}.resource",
        credential_requirements_ref=None,
        cancellation_profile_ref="step_boundary",
        idempotency_profile_ref="logical_request_id",
        authoritative_readback_profile_ref=readback,
        receipt_codec_ref=receipt_codec_ref,
    )
    return InterpreterProfile(**values, profile_digest=content_digest(values))


def _observation_profile(kind: str, *, compatible_with_legacy: bool = False) -> ObservationProfile:
    values = dict(
        observation_profile_id=f"{kind}.observation",
        observation_profile_version="1.0.0",
        dimensions=(
            "input_closure_digest",
            "output_closure_digest",
            "failure",
            "authority_epoch",
            "resource_units",
        ),
        compatible_with_legacy=compatible_with_legacy,
        observation_schema_ref="mrw.functorial-successor.observation.v1",
    )
    return ObservationProfile(**values, profile_digest=content_digest(values))


def _operation_contract(
    kind: str,
    *,
    input_type: ObjectType,
    output_type: ObjectType,
    return_contract_ref: str = RUNTIME_VALUE_RETURN_CONTRACT_REF,
    owner_capability_id: str,
    semantic: SemanticProfile,
    effect: EffectProfile,
    resource: ResourceProfile,
    failure: FailureProfile,
    authority: AuthorityProfile,
    interpreter: InterpreterProfile,
    observation: ObservationProfile,
) -> OperationContract:
    return make_operation_contract(
        kind=kind,
        contract_version="1.0.0",
        input_type=input_type,
        output_type=output_type,
        return_contract_ref=return_contract_ref,
        semantic_profile_ref=_profile_ref(
            semantic.semantic_profile_id,
            semantic.semantic_profile_version,
            semantic.profile_digest,
        ),
        effect_profile_ref=_profile_ref(
            effect.effect_profile_id,
            effect.effect_profile_version,
            effect.profile_digest,
        ),
        resource_profile_ref=_profile_ref(
            resource.resource_profile_id,
            resource.resource_profile_version,
            resource.profile_digest,
        ),
        failure_profile_ref=_profile_ref(
            failure.failure_profile_id,
            failure.failure_profile_version,
            failure.profile_digest,
        ),
        authority_profile_ref=_profile_ref(
            authority.authority_profile_id,
            authority.authority_profile_version,
            authority.profile_digest,
        ),
        interpreter_compatibility_ref=_profile_ref(
            interpreter.interpreter_profile_id,
            interpreter.interpreter_profile_version,
            interpreter.profile_digest,
        ),
        observation_profile_ref=_profile_ref(
            observation.observation_profile_id,
            observation.observation_profile_version,
            observation.profile_digest,
        ),
        allowed_override_schema_ref="mrw.functorial-successor.override.none.v1",
        owner_capability_id=owner_capability_id,
    )


@dataclass(frozen=True, slots=True)
class CaptureDocumentSnapshotInput:
    source_ref: str
    document_id: int
    content_sha256_hex: str
    observed_updated_at: str
    byte_size: int
    payload_digest: str

    def __post_init__(self) -> None:
        require_hex64(self.content_sha256_hex, "CaptureDocumentSnapshotInput.content_sha256_hex")
        require_hex64(self.payload_digest, "CaptureDocumentSnapshotInput.payload_digest")
        if content_digest(self, omit_fields=("payload_digest",)) != self.payload_digest:
            raise ValueError("CaptureDocumentSnapshotInput.payload_digest does not match content")


@dataclass(frozen=True, slots=True)
class CanonicalReadInput:
    source_ref: str
    locator: str
    owner_id: str
    observed_at: str
    payload_digest: str

    def __post_init__(self) -> None:
        require_hex64(self.payload_digest, "CanonicalReadInput.payload_digest")
        if content_digest(self, omit_fields=("payload_digest",)) != self.payload_digest:
            raise ValueError("CanonicalReadInput.payload_digest does not match content")


@dataclass(frozen=True, slots=True)
class EvidenceQualificationInput:
    qualification_id: str
    material_ref: str
    inquiry_ref: str
    direction: Literal["SUPPORTS", "CONTRADICTS", "CONTEXT", "INSUFFICIENT"]
    scope_statement_ref: str
    uncertainty_profile_ref: str
    verifier_profile_ref: str
    payload_digest: str

    def __post_init__(self) -> None:
        require_hex64(self.payload_digest, "EvidenceQualificationInput.payload_digest")
        if content_digest(self, omit_fields=("payload_digest",)) != self.payload_digest:
            raise ValueError("EvidenceQualificationInput.payload_digest does not match content")


@dataclass(frozen=True, slots=True)
class ClaimOrGapInput:
    claim_or_gap_id: str
    statement_ref: str
    inquiry_ref: str
    support_relation_refs: tuple[str, ...] = field(default_factory=tuple)
    contradiction_relation_refs: tuple[str, ...] = field(default_factory=tuple)
    uncertainty_profile_ref: str = ""
    requirement: str = ""
    reason: str = ""
    missing_evidence_or_decision: str = ""
    reopen_policy: dict[str, str] = field(default_factory=dict)
    closure_condition: str = ""
    payload_digest: str = ""

    def __post_init__(self) -> None:
        require_hex64(self.payload_digest, "ClaimOrGapInput.payload_digest")
        if content_digest(self, omit_fields=("payload_digest",)) != self.payload_digest:
            raise ValueError("ClaimOrGapInput.payload_digest does not match content")


ClaimOrGap = Claim | Gap


@dataclass(frozen=True, slots=True)
class MarkdownComposeInput:
    artifact_id: str
    claim_closure: tuple[str, ...]
    evidence_relation_closure: tuple[str, ...]
    citation_closure: tuple[str, ...]
    payload_digest: str

    def __post_init__(self) -> None:
        require_hex64(self.payload_digest, "MarkdownComposeInput.payload_digest")
        if content_digest(self, omit_fields=("payload_digest",)) != self.payload_digest:
            raise ValueError("MarkdownComposeInput.payload_digest does not match content")


@dataclass(frozen=True, slots=True)
class InternalExportInput:
    delivery_intent_id: str
    artifact_ref: str
    audience: str
    approval_refs: tuple[str, ...]
    idempotency_key: str
    payload_digest: str

    def __post_init__(self) -> None:
        require_hex64(self.payload_digest, "InternalExportInput.payload_digest")
        if not self.approval_refs:
            raise ValueError("InternalExportInput requires at least one human approval ref")
        if content_digest(self, omit_fields=("payload_digest",)) != self.payload_digest:
            raise ValueError("InternalExportInput.payload_digest does not match content")


@dataclass(frozen=True, slots=True)
class FirstSpecimenCapabilityBundle:
    bundle_id: str
    operations: tuple[OperationContract, ...]
    codecs: tuple[PayloadCodec, ...]
    profiles: dict[str, object]

    def operation_by_kind(self, kind: str) -> OperationContract:
        for contract in self.operations:
            if contract.ref.kind == kind:
                return contract
        raise KeyError(kind)

    def codec_by_kind(self, kind: str) -> PayloadCodec:
        for codec in self.codecs:
            if codec.contract_ref.kind == kind:
                return codec
        raise KeyError(kind)


FIRST_SPECIMEN_OPERATION_KINDS: tuple[str, ...] = (
    "material.capture_document_snapshot.v1",
    "material.read_canonical_ref.v1",
    "evidence.qualify.v1",
    "claim.form_or_open_gap.v1",
    "artifact.compose_markdown.v1",
    "delivery.internal_export.v1",
)


def build_first_specimen_bundle() -> FirstSpecimenCapabilityBundle:
    source_ref_type = _object_type("SourceRef.v1")
    captured_snapshot_type = _object_type("CapturedMaterialSnapshot.v1")
    material_ref_type = _object_type("MaterialRef.v1")
    evidence_bundle_type = _object_type("EvidenceBundle.v1")
    evidence_qualification_type = _object_type("EvidenceQualification.v1")
    evidence_qualification_bundle_type = _object_type("EvidenceQualificationBundle.v1")
    claim_or_gap_type = _object_type("ClaimOrGap.v1")
    research_artifact_type = _object_type("ResearchArtifact.v1")
    delivery_intent_type = _object_type("DeliveryIntent.v1")
    delivery_receipt_type = _object_type("DeliveryReceiptRef.v1")

    capture_kind = FIRST_SPECIMEN_OPERATION_KINDS[0]
    capture_contract = _operation_contract(
        capture_kind,
        input_type=source_ref_type,
        output_type=captured_snapshot_type,
        return_contract_ref=CAPTURE_DOCUMENT_SNAPSHOT_RETURN_CONTRACT_REF,
        owner_capability_id="material.first_specimen.v1",
        semantic=_semantic_profile(
            capture_kind,
            reads=("SourceRef.v1",),
            creates=("CapturedMaterialSnapshot.v1",),
        ),
        effect=_effect_profile(
            capture_kind,
            execution_class="EFFECTFUL",
            external_visibility="INTERNAL_ONLY",
        ),
        resource=_resource_profile(capture_kind),
        failure=_failure_profile(
            capture_kind,
            retryable=True,
            readback="DocumentCanonicalReadPort",
        ),
        authority=_authority_profile(
            capture_kind,
            canonical_owner="legacy_source_or_document_locator",
        ),
        interpreter=_interpreter_profile(
            capture_kind,
            readback="DocumentCanonicalReadPort",
            receipt_codec_ref="mrw.functorial-successor.receipt.document-capture.v1",
        ),
        observation=_observation_profile(capture_kind),
    )

    read_kind = FIRST_SPECIMEN_OPERATION_KINDS[1]
    read_contract = _operation_contract(
        read_kind,
        input_type=captured_snapshot_type,
        output_type=material_ref_type,
        return_contract_ref=READ_CANONICAL_REF_RETURN_CONTRACT_REF,
        owner_capability_id="material.first_specimen.v1",
        semantic=_semantic_profile(
            read_kind,
            reads=("SourceRef.v1",),
            creates=("MaterialRef.v1",),
        ),
        effect=_effect_profile(
            read_kind,
            execution_class="PURE_TRANSFORM",
            external_visibility="NONE",
        ),
        resource=_resource_profile(read_kind),
        failure=_failure_profile(read_kind),
        authority=_authority_profile(read_kind, canonical_owner="CapturedMaterialSnapshot"),
        interpreter=_interpreter_profile(
            read_kind,
            readback=None,
            receipt_codec_ref="mrw.functorial-successor.receipt.none.v1",
        ),
        observation=_observation_profile(read_kind),
    )

    qualify_kind = FIRST_SPECIMEN_OPERATION_KINDS[2]
    qualify_contract = _operation_contract(
        qualify_kind,
        input_type=evidence_bundle_type,
        output_type=evidence_qualification_type,
        return_contract_ref=EVIDENCE_QUALIFICATION_RETURN_CONTRACT_REF,
        owner_capability_id="evidence.first_specimen.v1",
        semantic=_semantic_profile(
            qualify_kind,
            reads=("MaterialRef.v1", "Inquiry.v1"),
            creates=(),
            creates_relations=("EvidenceQualification.v1",),
        ),
        effect=_effect_profile(qualify_kind, execution_class="PURE_TRANSFORM", external_visibility="NONE"),
        resource=_resource_profile(qualify_kind),
        failure=_failure_profile(qualify_kind),
        authority=_authority_profile(qualify_kind, canonical_owner="ResearchLedger"),
        interpreter=_interpreter_profile(
            qualify_kind,
            readback=None,
            receipt_codec_ref="mrw.functorial-successor.receipt.none.v1",
        ),
        observation=_observation_profile(qualify_kind),
    )

    claim_kind = FIRST_SPECIMEN_OPERATION_KINDS[3]
    claim_contract = _operation_contract(
        claim_kind,
        input_type=evidence_qualification_bundle_type,
        output_type=claim_or_gap_type,
        return_contract_ref=CLAIM_OR_GAP_RETURN_CONTRACT_REF,
        owner_capability_id="claim.first_specimen.v1",
        semantic=_semantic_profile(
            claim_kind,
            reads=("EvidenceQualification.v1", "Inquiry.v1"),
            creates=("Claim.v1", "Gap.v1"),
        ),
        effect=_effect_profile(claim_kind, execution_class="PURE_TRANSFORM", external_visibility="NONE"),
        resource=_resource_profile(claim_kind),
        failure=_failure_profile(claim_kind),
        authority=_authority_profile(claim_kind, canonical_owner="ResearchLedger"),
        interpreter=_interpreter_profile(
            claim_kind,
            readback=None,
            receipt_codec_ref="mrw.functorial-successor.receipt.none.v1",
        ),
        observation=_observation_profile(claim_kind),
    )

    compose_kind = FIRST_SPECIMEN_OPERATION_KINDS[4]
    compose_contract = _operation_contract(
        compose_kind,
        input_type=claim_or_gap_type,
        output_type=research_artifact_type,
        return_contract_ref=RESEARCH_ARTIFACT_RETURN_CONTRACT_REF,
        owner_capability_id="artifact.first_specimen.v1",
        semantic=_semantic_profile(
            compose_kind,
            reads=("Claim.v1", "EvidenceQualification.v1"),
            creates=("ResearchArtifact.v1",),
        ),
        effect=_effect_profile(compose_kind, execution_class="PURE_TRANSFORM", external_visibility="NONE"),
        resource=_resource_profile(compose_kind),
        failure=_failure_profile(compose_kind),
        authority=_authority_profile(compose_kind, canonical_owner="ResearchLedger_plus_project_artifact_store"),
        interpreter=_interpreter_profile(
            compose_kind,
            readback=None,
            receipt_codec_ref="mrw.functorial-successor.receipt.none.v1",
        ),
        observation=_observation_profile(compose_kind),
    )

    deliver_kind = FIRST_SPECIMEN_OPERATION_KINDS[5]
    deliver_contract = _operation_contract(
        deliver_kind,
        input_type=delivery_intent_type,
        output_type=delivery_receipt_type,
        return_contract_ref=DELIVERY_INTENT_RECEIPT_RETURN_CONTRACT_REF,
        owner_capability_id="delivery.first_specimen.v1",
        semantic=_semantic_profile(
            deliver_kind,
            reads=("ResearchArtifact.v1", "DeliveryIntent.v1"),
            creates=("DeliveryAttempt.v1", "DeliveryReceiptRef.v1"),
        ),
        effect=_effect_profile(
            deliver_kind,
            execution_class="EFFECTFUL",
            external_visibility="INTERNAL_ONLY",
            irreversible=True,
            human_approval_required=True,
        ),
        resource=_resource_profile(deliver_kind),
        failure=_failure_profile(deliver_kind, retryable=True, readback="internal_export_idempotency"),
        authority=_authority_profile(
            deliver_kind,
            canonical_owner="runtime_approvals",
            approval_required=True,
            approval_kinds=("HUMAN_APPROVAL",),
        ),
        interpreter=_interpreter_profile(
            deliver_kind,
            readback="internal_export_idempotency",
            receipt_codec_ref="mrw.functorial-successor.receipt.internal-export.v1",
        ),
        observation=_observation_profile(deliver_kind),
    )

    contracts = (
        capture_contract,
        read_contract,
        qualify_contract,
        claim_contract,
        compose_contract,
        deliver_contract,
    )
    codecs = (
        dataclass_codec(
            "material.capture_document_snapshot.v1.payload",
            "1.0.0",
            capture_contract.ref,
            "CaptureDocumentSnapshotInput.v1",
            CaptureDocumentSnapshotInput,
        ),
        dataclass_codec(
            "material.read_canonical_ref.v1.payload",
            "1.0.0",
            read_contract.ref,
            "CanonicalReadInput.v1",
            CanonicalReadInput,
        ),
        dataclass_codec(
            "evidence.qualify.v1.payload",
            "1.0.0",
            qualify_contract.ref,
            "EvidenceQualificationInput.v1",
            EvidenceQualificationInput,
        ),
        dataclass_codec(
            "claim.form_or_open_gap.v1.payload",
            "1.0.0",
            claim_contract.ref,
            "ClaimOrGapInput.v1",
            ClaimOrGapInput,
        ),
        dataclass_codec(
            "artifact.compose_markdown.v1.payload",
            "1.0.0",
            compose_contract.ref,
            "MarkdownComposeInput.v1",
            MarkdownComposeInput,
        ),
        dataclass_codec(
            "delivery.internal_export.v1.payload",
            "1.0.0",
            deliver_contract.ref,
            "InternalExportInput.v1",
            InternalExportInput,
        ),
    )
    profiles = {}
    for contract in contracts:
        profiles[contract.ref.kind] = {
            "semantic": f"{contract.ref.kind}.semantic",
            "effect": f"{contract.ref.kind}.effect",
            "resource": f"{contract.ref.kind}.resource",
            "failure": f"{contract.ref.kind}.failure",
            "authority": f"{contract.ref.kind}.authority",
            "interpreter": f"{contract.ref.kind}.interpreter",
            "observation": f"{contract.ref.kind}.observation",
        }
    return FirstSpecimenCapabilityBundle(
        bundle_id="mrw.functorial-successor.first-specimen.capabilities.v1",
        operations=contracts,
        codecs=codecs,
        profiles=profiles,
    )
