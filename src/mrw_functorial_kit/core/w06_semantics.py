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

ProjectionEvidenceSurfaceFailureCode = Literal[
    "authority_contract_invalid",
    "evidence_integrity_invalid",
    "evidence_line_set_invalid",
    "evidence_source_invalid",
    "projection_input_invalid",
    "surface_contract_invalid",
]

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
    "projection_evidence_surface_failures",
    "capability_primitive_contract_failures",
    "first_specimen_capability_failures",
    "line_event_readback_failures",
    "quality_promotion_contract_failures",
    "source_single_source_guard_failures",
]
