"""Kit projection for W06 failure families."""

from __future__ import annotations

from typing import Literal, get_args

from functorial_kit import FailureFamily, define_failure_family

C1CapabilityFailureCode = Literal[
    "C1_ACCEPTANCE_DIGEST_INVALID",
    "C1_ACCEPTANCE_INPUT_INVALID",
    "C1_CONTRACT_KIND_UNSUPPORTED",
    "C1_DSL_COMPILE_FAILURE",
    "C1_DSL_CYCLE",
    "C1_DSL_DUPLICATE_NODE_ID",
    "C1_DSL_MALFORMED_PAYLOAD",
    "C1_DSL_MISSING_ENDPOINT",
    "C1_DSL_UNSUPPORTED_NODE_TYPE",
    "C1_OBSERVATION_SHAPE_INVALID",
    "C1_PROGRAM_PLAN_BINDING_INVALID",
    "C1_RECEIPT_CONTRACT_INVALID",
    "C1_ROLLBACK_BINDING_INVALID",
    "C1_SLICE_SHAPE_INVALID",
]

C2InterpreterFailureCode = Literal[
    "ASSIGNMENT_BINDING_MISMATCH",
]

C2ProviderEffectFailureCode = Literal[
    "ARTIFACT_WRITE",
    "CANCELLED",
    "INVALID_PARAMS",
    "MISSING_CREDENTIAL",
    "OUTCOME_UNKNOWN",
    "PROVIDER_REJECTED",
    "RATE_LIMIT",
    "REQUEST_BINDING_MISMATCH",
    "RESOURCE_CEILING_EXCEEDED",
    "TIMEOUT",
    "TRANSPORT",
    "UNAUTHORIZED",
    "UNSUPPORTED_PROVIDER",
]

MaterialIngestContractFailureCode = Literal[
    "input_contract_invalid",
    "lookup_not_found",
    "program_binding_invalid",
    "stage_invalid",
]

MaterialIngestRegistryFailureCode = Literal[
    "backend_unavailable",
    "conflict",
    "credential_rejected",
    "input_contract_invalid",
    "integrity_violation",
    "not_found",
]

C8ContractFailureCode = Literal[
    "authority_contract_invalid",
    "canonical_json_invalid",
    "digest_binding_invalid",
    "evidence_surface_invalid",
    "input_contract_invalid",
    "lookup_not_found",
    "operation_contract_invalid",
    "payload_codec_invalid",
    "program_binding_invalid",
]

C8ReportExportTokenFailureCode = Literal[
    "export_token_actor_mismatch",
    "export_token_already_used",
    "export_token_expired",
    "export_token_markdown_hash_mismatch",
    "export_token_missing_expiry",
    "export_token_revoked",
    "invalid_export_token_format",
    "invalid_export_token_payload",
    "invalid_export_token_signature",
    "unsupported_export_token_contract",
]

C8ReportExportTokenStateFailureCode = Literal[
    "backend_unavailable",
    "conflict",
    "credential_rejected",
    "input_contract_invalid",
    "not_found",
]

ProjectionEvidenceSurfaceFailureCode = Literal[
    "authority_contract_invalid",
    "evidence_integrity_invalid",
    "evidence_line_set_invalid",
    "evidence_source_invalid",
    "projection_input_invalid",
    "surface_contract_invalid",
]

# Historical metadata readers retain this source-era type name without making
# it the authority for current projection failures.
C9EvidenceSurfaceFailureCode = ProjectionEvidenceSurfaceFailureCode

CapabilityPrimitiveContractFailureCode = Literal[
    "codec_input_type_invalid",
    "digest_contract_invalid",
]

FirstSpecimenCapabilityFailureCode = Literal[
    "CAPABILITY_CONTRACT_INVALID",
    "DELIVERY_AUTHORITY_OR_APPROVAL_INVALID",
    "DELIVERY_GATE_REJECTED",
    "DOCUMENT_OBSERVATION_MISMATCH",
    "GAP_SUCCESSOR_REJECTED",
    "INTERNAL_EXPORT_READBACK_CONFLICT",
    "INTERNAL_EXPORT_REJECTED",
    "INTERPRETER_UNAVAILABLE",
    "INVALID_ARTIFACT_CLOSURE",
    "INVALID_CAPTURED_MATERIAL",
    "INVALID_CLAIM_OR_GAP",
    "INVALID_EVIDENCE_QUALIFICATION",
    "LOOKUP_NOT_FOUND",
    "SUBMISSION_REJECTED",
]

LineEventReadbackFailureCode = Literal[
    "event_migration_illegal",
    "line_event_unknown",
    "line_key_unknown",
]

QualityPromotionContractFailureCode = Literal[
    "boolean_invalid",
    "case_id_required",
    "evidence_type_invalid",
    "executor_health_invalid",
    "integer_invalid",
    "number_invalid",
    "provider_replay_invalid",
    "sample_count_invalid",
    "sequence_invalid",
    "threshold_version_required",
]

SourceLibrarySingleSourceGuardFailureCode = Literal[
    "single_source_guard_allowed_urls_invalid",
    "single_source_guard_blocked",
    "single_source_guard_invalid_shape",
    "single_source_guard_missing",
    "single_source_guard_site_entries_mismatch",
    "single_source_guard_strict_source_required",
]


def read_historical_c1_capability_failure_family() -> FailureFamily:
    """Read the retired C1 metadata without declaring a current failure family."""

    return FailureFamily(
        "c1.capability.failure",
        get_args(C1CapabilityFailureCode),
    )


c1_capability_failures = read_historical_c1_capability_failure_family()
source_runtime_binding_failures = define_failure_family(
    "source.runtime-binding.failure",
    get_args(C2InterpreterFailureCode),
)
source_provider_acquisition_failures = define_failure_family(
    "source.provider-acquisition.failure",
    get_args(C2ProviderEffectFailureCode),
)
material_ingest_contract_failures = define_failure_family(
    "material.ingest.contract_failure",
    get_args(MaterialIngestContractFailureCode),
)
material_ingest_registry_failures = define_failure_family(
    "material.ingest.registry_failure",
    get_args(MaterialIngestRegistryFailureCode),
)


def read_historical_c7_ingest_contract_failure_family() -> FailureFamily:
    """Read exact retired C7 contract failure metadata without live registration."""

    return FailureFamily(
        "c7.ingest.contract_failure",
        get_args(MaterialIngestContractFailureCode),
    )


def read_historical_c7_ingest_registry_failure_family() -> FailureFamily:
    """Read exact retired C7 registry failure metadata without live registration."""

    return FailureFamily(
        "c7.ingest_registry.failure",
        get_args(MaterialIngestRegistryFailureCode),
    )


# Compatibility type spellings retain source-level annotations only.
C7IngestContractFailureCode = MaterialIngestContractFailureCode
C7IngestRegistryFailureCode = MaterialIngestRegistryFailureCode


def read_historical_c8_contract_failure_family() -> FailureFamily:
    """Read retired C8 contract metadata without declaring a live family."""

    return FailureFamily("c8.contract.failure", get_args(C8ContractFailureCode))


def read_historical_c8_report_export_token_failure_family() -> FailureFamily:
    """Read retired C8 token metadata without declaring a live family."""

    return FailureFamily(
        "c8.report_export_token.failure",
        get_args(C8ReportExportTokenFailureCode),
    )


def read_historical_c8_report_export_token_state_failure_family() -> FailureFamily:
    """Read retired C8 token-state metadata without declaring a live family."""

    return FailureFamily(
        "c8.report_export_token_state.failure",
        get_args(C8ReportExportTokenStateFailureCode),
    )


c8_contract_failures = read_historical_c8_contract_failure_family()
c8_report_export_token_failures = (
    read_historical_c8_report_export_token_failure_family()
)
c8_report_export_token_state_failures = (
    read_historical_c8_report_export_token_state_failure_family()
)

def read_historical_c9_evidence_surface_failure_family() -> FailureFamily:
    """Read retired C9 evidence metadata without declaring a live family."""

    return FailureFamily(
        "c9.evidence_surface.failure",
        get_args(C9EvidenceSurfaceFailureCode),
    )


c9_evidence_surface_failures = read_historical_c9_evidence_surface_failure_family()
projection_evidence_surface_failures = define_failure_family(
    "projection.evidence-surface.failure",
    get_args(ProjectionEvidenceSurfaceFailureCode),
)
capability_primitive_contract_failures = define_failure_family(
    "capability.primitive.contract_failure",
    get_args(CapabilityPrimitiveContractFailureCode),
)
first_specimen_capability_failures = define_failure_family(
    "first_specimen.capability.failure",
    get_args(FirstSpecimenCapabilityFailureCode),
)
line_event_readback_failures = define_failure_family(
    "line_event.readback.failure",
    get_args(LineEventReadbackFailureCode),
)
quality_promotion_contract_failures = define_failure_family(
    "quality.promotion.contract_failure",
    get_args(QualityPromotionContractFailureCode),
)
source_single_source_guard_failures = define_failure_family(
    "source.single-source-guard.failure",
    get_args(SourceLibrarySingleSourceGuardFailureCode),
)


__all__ = [
    "C1CapabilityFailureCode",
    "C2InterpreterFailureCode",
    "C2ProviderEffectFailureCode",
    "C7IngestContractFailureCode",
    "C7IngestRegistryFailureCode",
    "MaterialIngestContractFailureCode",
    "MaterialIngestRegistryFailureCode",
    "C8ContractFailureCode",
    "C8ReportExportTokenFailureCode",
    "C8ReportExportTokenStateFailureCode",
    "C9EvidenceSurfaceFailureCode",
    "ProjectionEvidenceSurfaceFailureCode",
    "CapabilityPrimitiveContractFailureCode",
    "FirstSpecimenCapabilityFailureCode",
    "LineEventReadbackFailureCode",
    "QualityPromotionContractFailureCode",
    "SourceLibrarySingleSourceGuardFailureCode",
    "c1_capability_failures",
    "read_historical_c1_capability_failure_family",
    "source_runtime_binding_failures",
    "source_provider_acquisition_failures",
    "material_ingest_contract_failures",
    "material_ingest_registry_failures",
    "read_historical_c7_ingest_contract_failure_family",
    "read_historical_c7_ingest_registry_failure_family",
    "c8_contract_failures",
    "c8_report_export_token_failures",
    "c8_report_export_token_state_failures",
    "read_historical_c8_contract_failure_family",
    "read_historical_c8_report_export_token_failure_family",
    "read_historical_c8_report_export_token_state_failure_family",
    "c9_evidence_surface_failures",
    "read_historical_c9_evidence_surface_failure_family",
    "projection_evidence_surface_failures",
    "capability_primitive_contract_failures",
    "first_specimen_capability_failures",
    "line_event_readback_failures",
    "quality_promotion_contract_failures",
    "source_single_source_guard_failures",
]
