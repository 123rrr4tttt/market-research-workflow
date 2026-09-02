"""Immutable comprehensive-information-research domain objects and relations."""

from .artifacts import (
    DELIVERY_CHANNEL,
    DELIVERY_FORMAT,
    DELIVERY_IRREVERSIBILITY_PROFILE,
    EFFECT_DISPOSITIONS,
    DeliveryAttempt,
    DeliveryIntent,
    DeliveryReceiptRef,
    ResearchArtifact,
)
from .claims import CLAIM_LIFECYCLE_STATES, Claim, Gap
from .codec import (
    CanonicalCodecError,
    UnsupportedCanonicalValueError,
    canonical_json,
    digest_dataclass,
    encode,
    is_sha256_hex,
    sha256_hex,
)
from .evidence import QUALIFICATION_DIRECTIONS, EvidenceQualification
from .identities import LifecycleState, ResearchObjectRef
from .inquiries import Inquiry, PlanWorkItem, ResearchIntent, ResearchPlan
from .materials import CapturedMaterialSnapshot, MaterialRef
from .object_types import (
    CAPTURED_MATERIAL_SNAPSHOT_TYPE,
    CLAIM_TYPE,
    DELIVERY_ATTEMPT_TYPE,
    DELIVERY_INTENT_TYPE,
    DELIVERY_RECEIPT_REF_TYPE,
    EVIDENCE_QUALIFICATION_TYPE,
    GAP_TYPE,
    INQUIRY_TYPE,
    MATERIAL_REF_TYPE,
    OBJECT_TYPE_BY_ID,
    RESEARCH_ARTIFACT_TYPE,
    RESEARCH_INTENT_TYPE,
    RESEARCH_PLAN_TYPE,
    SOURCE_REF_TYPE,
    DomainContractSnapshot,
    ObjectContract,
    ObjectType,
    OwnerMode,
)
from .provenance import ProvenanceClosure, ProvenanceEntry
from .relations import (
    RELATION_CONTRACT_BY_ID,
    RELATION_CONTRACT_REFS,
    RELATION_CONTRACTS,
    RELATION_KINDS,
    RelationContract,
    ResearchRelation,
)
from .sources import SourceRef

__all__ = [
    "CLAIM_LIFECYCLE_STATES",
    "DELIVERY_CHANNEL",
    "DELIVERY_FORMAT",
    "DELIVERY_IRREVERSIBILITY_PROFILE",
    "EFFECT_DISPOSITIONS",
    "QUALIFICATION_DIRECTIONS",
    "RELATION_CONTRACT_BY_ID",
    "RELATION_CONTRACT_REFS",
    "RELATION_CONTRACTS",
    "RELATION_KINDS",
    "CanonicalCodecError",
    "CapturedMaterialSnapshot",
    "Claim",
    "DeliveryAttempt",
    "DeliveryIntent",
    "DeliveryReceiptRef",
    "DomainContractSnapshot",
    "EvidenceQualification",
    "Gap",
    "Inquiry",
    "LifecycleState",
    "MaterialRef",
    "ObjectContract",
    "ObjectType",
    "OwnerMode",
    "PlanWorkItem",
    "ProvenanceClosure",
    "ProvenanceEntry",
    "RelationContract",
    "ResearchArtifact",
    "ResearchIntent",
    "ResearchObjectRef",
    "ResearchPlan",
    "ResearchRelation",
    "SourceRef",
    "UnsupportedCanonicalValueError",
    "canonical_json",
    "digest_dataclass",
    "encode",
    "is_sha256_hex",
    "sha256_hex",
]
