"""Immutable operation contract catalog, registry, and first-specimen snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.successor_runtime.language.object_contracts import (
    OperationContract,
    OperationContractRef,
    OperationContractResolver,
)
from app.successor_runtime.research.codec import finalize_digest
from app.successor_runtime.research.object_types import (
    CAPTURED_MATERIAL_SNAPSHOT_TYPE,
    CLAIM_TYPE,
    DELIVERY_ATTEMPT_TYPE,
    DELIVERY_INTENT_TYPE,
    DELIVERY_RECEIPT_REF_TYPE,
    EVIDENCE_QUALIFICATION_TYPE,
    GAP_TYPE,
    INQUIRY_TYPE,
    MATERIAL_REF_TYPE,
    RESEARCH_ARTIFACT_TYPE,
    RESEARCH_INTENT_TYPE,
    RESEARCH_PLAN_TYPE,
    SOURCE_REF_TYPE,
    DomainContractSnapshot,
    ObjectContract,
    ObjectType,
)
from app.successor_runtime.research.relations import RELATION_CONTRACT_REFS

__all__ = [
    "FIRST_SPECIMEN_CAPABILITY_ID",
    "FIRST_SPECIMEN_CATALOG_ID",
    "FIRST_SPECIMEN_CATALOG_VERSION",
    "FIRST_SPECIMEN_CONTRACT_REF",
    "FIRST_SPECIMEN_DOMAIN_SNAPSHOT_ID",
    "FIRST_SPECIMEN_DOMAIN_SNAPSHOT_VERSION",
    "FIRST_SPECIMEN_OBJECT_CONTRACT_REFS",
    "FIRST_SPECIMEN_OPERATION_KINDS",
    "FIRST_SPECIMEN_RELATION_CONTRACT_REFS",
    "OperationContractCatalogSnapshot",
    "OperationContractRegistry",
    "build_first_specimen_domain_snapshot",
    "build_first_specimen_object_contracts",
]

FIRST_SPECIMEN_CAPABILITY_ID = "mrw.first-specimen"
FIRST_SPECIMEN_CATALOG_ID = "mrw.functorial-successor.first-specimen.operations"
FIRST_SPECIMEN_CATALOG_VERSION = "1.0.0"
FIRST_SPECIMEN_DOMAIN_SNAPSHOT_ID = "mrw.functorial-successor.first-specimen.domain"
FIRST_SPECIMEN_DOMAIN_SNAPSHOT_VERSION = "1.0.0"
FIRST_SPECIMEN_CONTRACT_REF = "11_functorial-successor-first-specimen-contract.v1.json"

FIRST_SPECIMEN_OPERATION_KINDS: tuple[str, ...] = (
    "material.capture_document_snapshot.v1",
    "material.read_canonical_ref.v1",
    "evidence.qualify.v1",
    "claim.form_or_open_gap.v1",
    "artifact.compose_markdown.v1",
    "delivery.internal_export.v1",
)

FIRST_SPECIMEN_OBJECT_CONTRACT_REFS: tuple[str, ...] = (
    "ResearchIntent.v1",
    "Inquiry.v1",
    "ResearchPlan.v1",
    "SourceRef.v1",
    "MaterialRef.v1",
    "Claim.v1",
    "Gap.v1",
    "ResearchArtifact.v1",
    "DeliveryIntent.v1",
    "DeliveryAttempt.v1",
    "DeliveryReceiptRef.v1",
)

FIRST_SPECIMEN_RELATION_CONTRACT_REFS: tuple[str, ...] = RELATION_CONTRACT_REFS


@dataclass(frozen=True, slots=True)
class OperationContractCatalogSnapshot:
    catalog_id: str
    catalog_version: str
    entries: tuple[tuple[str, str, str, str], ...]
    catalog_digest: str | None = None

    def __post_init__(self) -> None:
        refs = tuple(entry[:3] for entry in self.entries)
        if len(refs) != len(set(refs)):
            raise ValueError("duplicate operation contract ref in catalog")
        finalize_digest(self, "catalog_digest")

    def lookup(self, ref_or_kind: OperationContractRef | str) -> OperationContractRef | None:
        if isinstance(ref_or_kind, OperationContractRef):
            key = (
                ref_or_kind.kind,
                ref_or_kind.contract_version,
                ref_or_kind.contract_digest,
            )
            entry = next((item for item in self.entries if item[:3] == key), None)
        else:
            matches = tuple(item for item in self.entries if item[0] == ref_or_kind)
            if len(matches) > 1:
                raise ValueError(
                    f"ambiguous operation contract kind: {ref_or_kind}; exact ref required"
                )
            entry = matches[0] if matches else None
        if entry is None:
            return None
        return OperationContractRef(
            kind=entry[0],
            contract_version=entry[1],
            contract_digest=entry[2],
        )

    def requires(self, kind: str) -> bool:
        return any(entry[0] == kind for entry in self.entries)

    def find(self, kind: str) -> tuple[str, str, str, str] | None:
        """Return the immutable index entry for compatibility with validators."""
        matches = tuple(entry for entry in self.entries if entry[0] == kind)
        if len(matches) > 1:
            raise ValueError(
                f"ambiguous operation contract kind: {kind}; exact ref required"
            )
        return matches[0] if matches else None

    def registered_kinds(self) -> frozenset[str]:
        return frozenset(entry[0] for entry in self.entries)

    def as_operation_contract_snapshot(self) -> "OperationContractCatalogSnapshot":
        return self


@dataclass(frozen=True, slots=True)
class OperationContractRegistry:
    catalog: OperationContractCatalogSnapshot
    contracts: tuple[OperationContract, ...]
    _by_ref: dict[tuple[str, str, str], OperationContract] = field(
        default_factory=dict,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        by_ref: dict[tuple[str, str, str], OperationContract] = {}
        for contract in self.contracts:
            key = (
                contract.ref.kind,
                contract.ref.contract_version,
                contract.ref.contract_digest,
            )
            if key in by_ref:
                raise ValueError(
                    f"duplicate operation contract ref: {contract.ref.kind}@{contract.ref.contract_version}"
                )
            entry = self.catalog.lookup(contract.ref)
            if entry is None:
                raise ValueError(
                    f"exact operation contract {contract.ref.kind}@{contract.ref.contract_version} missing from catalog"
                )
            by_ref[key] = contract
        object.__setattr__(self, "_by_ref", by_ref)

    def resolve(self, ref: OperationContractRef) -> OperationContract | None:
        return self._by_ref.get(
            (ref.kind, ref.contract_version, ref.contract_digest)
        )

    def resolve_required(self, ref: OperationContractRef) -> OperationContract:
        contract = self.resolve(ref)
        if contract is None:
            raise KeyError(
                f"unresolved operation contract: {ref.kind}@{ref.contract_version}"
            )
        return contract


_OBJECT_CONTRACT_SPEC: tuple[
    tuple[ObjectType, str, str, tuple[str, ...]],
    ...,
] = (
    (
        RESEARCH_INTENT_TYPE,
        "CANONICAL_OWNED",
        "ResearchLedger",
        ("purpose", "audience_or_use", "scope", "as_of", "constraints", "expected_delivery"),
    ),
    (
        INQUIRY_TYPE,
        "CANONICAL_OWNED",
        "ResearchLedger",
        ("question_or_hypothesis", "acceptance_conditions", "stop_conditions", "uncertainty_ceiling"),
    ),
    (
        RESEARCH_PLAN_TYPE,
        "CANONICAL_OWNED",
        "ResearchLedger",
        ("inquiry_ref", "ordered_or_partial_order_work", "budget", "deadline", "replan_policy"),
    ),
    (
        SOURCE_REF_TYPE,
        "IMMUTABLE_EXTERNAL_REF",
        "legacy_source_or_document_locator",
        ("owner_id", "locator", "source_class", "access_profile", "observed_at"),
    ),
    (
        MATERIAL_REF_TYPE,
        "IMMUTABLE_EXTERNAL_REF",
        "CapturedMaterialSnapshot",
        (
            "source_ref",
            "snapshot_value_ref",
            "content_digest",
            "source_observed_hash",
            "source_observed_updated_at",
        ),
    ),
    (
        CLAIM_TYPE,
        "CANONICAL_OWNED",
        "ResearchLedger",
        (
            "statement_ref",
            "scope",
            "support_relation_refs",
            "contradiction_relation_refs",
            "uncertainty_profile_ref",
            "lifecycle_state",
        ),
    ),
    (
        GAP_TYPE,
        "CANONICAL_OWNED",
        "ResearchLedger",
        (
            "inquiry_ref",
            "requirement",
            "reason",
            "missing_evidence_or_decision",
            "reopen_policy",
            "closure_condition",
        ),
    ),
    (
        RESEARCH_ARTIFACT_TYPE,
        "CANONICAL_OWNED",
        "ResearchLedger_plus_project_artifact_store",
        (
            "content_ref",
            "content_digest",
            "claim_closure",
            "evidence_relation_closure",
            "citation_closure",
            "format",
            "revision",
            "lifecycle_state",
        ),
    ),
    (
        DELIVERY_INTENT_TYPE,
        "CANONICAL_OWNED",
        "ResearchLedger",
        (
            "artifact_ref",
            "audience",
            "channel",
            "format",
            "approval_refs",
            "authority_digest",
            "idempotency_key",
            "irreversibility_profile",
        ),
    ),
    (
        DELIVERY_ATTEMPT_TYPE,
        "RUNTIME_FACT",
        "ExecutionJournal",
        ("attempt_id", "intent_ref", "handler_binding_digest", "effect_disposition"),
    ),
    (
        DELIVERY_RECEIPT_REF_TYPE,
        "IMMUTABLE_EXTERNAL_REF",
        "project_receipt_store",
        ("intent_ref", "attempt_ref", "provider_locator", "receipt_digest", "outcome_time"),
    ),
)


def build_first_specimen_object_contracts() -> tuple[ObjectContract, ...]:
    return tuple(
        ObjectContract(
            object_type=object_type,
            identity_schema_ref=f"{object_type.type_id}:identity",
            content_schema_ref=f"{object_type.type_id}:content",
            lifecycle_schema_ref=f"{object_type.type_id}:lifecycle",
            owner_mode=owner_mode,
            owner_binding_ref=owner,
            provenance_requirement_ref="mrw.provenance.closure.v1",
            migration_profile_ref="mrw.migration.legacy.v1",
            required_fields=required_fields,
        )
        for object_type, owner_mode, owner, required_fields in _OBJECT_CONTRACT_SPEC
    )


def _catalog_from_contracts(
    contracts: tuple[OperationContract, ...],
) -> OperationContractCatalogSnapshot:
    entries = tuple(
        (
            contract.ref.kind,
            contract.ref.contract_version,
            contract.ref.contract_digest,
            contract.owner_capability_id,
        )
        for contract in contracts
    )
    return OperationContractCatalogSnapshot(
        catalog_id=FIRST_SPECIMEN_CATALOG_ID,
        catalog_version=FIRST_SPECIMEN_CATALOG_VERSION,
        entries=entries,
    )
def build_first_specimen_domain_snapshot() -> DomainContractSnapshot:
    return DomainContractSnapshot(
        snapshot_id=FIRST_SPECIMEN_DOMAIN_SNAPSHOT_ID,
        snapshot_version=FIRST_SPECIMEN_DOMAIN_SNAPSHOT_VERSION,
        object_contract_refs=FIRST_SPECIMEN_OBJECT_CONTRACT_REFS,
        relation_contract_refs=FIRST_SPECIMEN_RELATION_CONTRACT_REFS,
        operation_contract_refs=FIRST_SPECIMEN_OPERATION_KINDS,
        first_specimen_contract_ref=FIRST_SPECIMEN_CONTRACT_REF,
    )
