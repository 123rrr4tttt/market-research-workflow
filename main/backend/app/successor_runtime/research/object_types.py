"""Object type identity and immutable object contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .codec import digest_dataclass, finalize_digest

__all__ = [
    "CANONICAL_CODEC_ID",
    "CANONICAL_CODEC_VERSION",
    "CAPTURED_MATERIAL_SNAPSHOT_TYPE",
    "CLAIM_TYPE",
    "DELIVERY_ATTEMPT_TYPE",
    "DELIVERY_INTENT_TYPE",
    "DELIVERY_RECEIPT_REF_TYPE",
    "DomainContractSnapshot",
    "EVIDENCE_QUALIFICATION_TYPE",
    "GAP_TYPE",
    "INQUIRY_TYPE",
    "MATERIAL_REF_TYPE",
    "OBJECT_TYPE_BY_ID",
    "ObjectContract",
    "ObjectType",
    "RESEARCH_ARTIFACT_TYPE",
    "RESEARCH_INTENT_TYPE",
    "RESEARCH_PLAN_TYPE",
    "SOURCE_REF_TYPE",
    "OwnerMode",
]

CANONICAL_CODEC_ID = "mrw.canonical-json.v1"
CANONICAL_CODEC_VERSION = "1"

OwnerMode = Literal[
    "CANONICAL_OWNED",
    "IMMUTABLE_EXTERNAL_REF",
    "DECLARED_LOSS_PROJECTION",
    "RUNTIME_FACT",
]


@dataclass(frozen=True, slots=True)
class ObjectType:
    type_id: str
    schema_version: str = "1.0.0"
    codec_id: str = CANONICAL_CODEC_ID
    canonical_codec_version: str = CANONICAL_CODEC_VERSION


RESEARCH_INTENT_TYPE = ObjectType("ResearchIntent.v1")
INQUIRY_TYPE = ObjectType("Inquiry.v1")
RESEARCH_PLAN_TYPE = ObjectType("ResearchPlan.v1")
SOURCE_REF_TYPE = ObjectType("SourceRef.v1")
CAPTURED_MATERIAL_SNAPSHOT_TYPE = ObjectType("CapturedMaterialSnapshot.v1")
MATERIAL_REF_TYPE = ObjectType("MaterialRef.v1")
EVIDENCE_QUALIFICATION_TYPE = ObjectType("EvidenceQualification.v1")
CLAIM_TYPE = ObjectType("Claim.v1")
GAP_TYPE = ObjectType("Gap.v1")
RESEARCH_ARTIFACT_TYPE = ObjectType("ResearchArtifact.v1")
DELIVERY_INTENT_TYPE = ObjectType("DeliveryIntent.v1")
DELIVERY_ATTEMPT_TYPE = ObjectType("DeliveryAttempt.v1")
DELIVERY_RECEIPT_REF_TYPE = ObjectType("DeliveryReceiptRef.v1")

OBJECT_TYPE_BY_ID: dict[str, ObjectType] = {
    obj.type_id: obj
    for obj in (
        RESEARCH_INTENT_TYPE,
        INQUIRY_TYPE,
        RESEARCH_PLAN_TYPE,
        SOURCE_REF_TYPE,
        CAPTURED_MATERIAL_SNAPSHOT_TYPE,
        MATERIAL_REF_TYPE,
        EVIDENCE_QUALIFICATION_TYPE,
        CLAIM_TYPE,
        GAP_TYPE,
        RESEARCH_ARTIFACT_TYPE,
        DELIVERY_INTENT_TYPE,
        DELIVERY_ATTEMPT_TYPE,
        DELIVERY_RECEIPT_REF_TYPE,
    )
}


@dataclass(frozen=True, slots=True)
class ObjectContract:
    object_type: ObjectType
    identity_schema_ref: str
    content_schema_ref: str
    lifecycle_schema_ref: str
    owner_mode: OwnerMode
    owner_binding_ref: str
    provenance_requirement_ref: str
    migration_profile_ref: str
    required_fields: tuple[str, ...] = ()
    declared_loss_profile_ref: str | None = None
    contract_digest: str | None = None

    def __post_init__(self) -> None:
        finalize_digest(self, "contract_digest")


@dataclass(frozen=True, slots=True)
class DomainContractSnapshot:
    snapshot_id: str
    snapshot_version: str
    object_contract_refs: tuple[str, ...]
    relation_contract_refs: tuple[str, ...]
    operation_contract_refs: tuple[str, ...]
    first_specimen_contract_ref: str
    snapshot_digest: str | None = None

    def __post_init__(self) -> None:
        finalize_digest(self, "snapshot_digest")
