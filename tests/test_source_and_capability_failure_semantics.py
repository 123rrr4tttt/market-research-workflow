from __future__ import annotations

from typing import get_args

import pytest
from functorial_kit import Failure, FailureFamily

from mrw_functorial_kit.core.source_and_capability_failure_semantics import (
    C1CapabilityFailureCode,
    C2InterpreterFailureCode,
    C2ProviderEffectFailureCode,
    CapabilityPrimitiveContractFailureCode,
    FirstSpecimenCapabilityFailureCode,
    LineEventReadbackFailureCode,
    ProjectionEvidenceSurfaceFailureCode,
    QualityPromotionContractFailureCode,
    SourceLibrarySingleSourceGuardFailureCode,
    c1_capability_failures,
    capability_primitive_contract_failures,
    first_specimen_capability_failures,
    line_event_readback_failures,
    projection_evidence_surface_failures,
    quality_promotion_contract_failures,
    source_provider_acquisition_failures,
    source_runtime_binding_failures,
    source_single_source_guard_failures,
)

FAMILIES: tuple[tuple[object, FailureFamily, str], ...] = (
    (C1CapabilityFailureCode, c1_capability_failures, "c1.capability.failure"),
    (C2InterpreterFailureCode, source_runtime_binding_failures, "source.runtime-binding.failure"),
    (
        C2ProviderEffectFailureCode,
        source_provider_acquisition_failures,
        "source.provider-acquisition.failure",
    ),
    (
        ProjectionEvidenceSurfaceFailureCode,
        projection_evidence_surface_failures,
        "projection.evidence-surface.failure",
    ),
    (
        CapabilityPrimitiveContractFailureCode,
        capability_primitive_contract_failures,
        "capability.primitive.contract_failure",
    ),
    (
        FirstSpecimenCapabilityFailureCode,
        first_specimen_capability_failures,
        "first_specimen.capability.failure",
    ),
    (
        LineEventReadbackFailureCode,
        line_event_readback_failures,
        "line_event.readback.failure",
    ),
    (
        QualityPromotionContractFailureCode,
        quality_promotion_contract_failures,
        "quality.promotion.contract_failure",
    ),
    (
        SourceLibrarySingleSourceGuardFailureCode,
        source_single_source_guard_failures,
        "source.single-source-guard.failure",
    ),
)


EXPECTED_CODES: dict[str, tuple[str, ...]] = {
    "c1.capability.failure": (
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
    ),
    "source.runtime-binding.failure": ("ASSIGNMENT_BINDING_MISMATCH",),
    "source.provider-acquisition.failure": (
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
    ),
    "projection.evidence-surface.failure": (
        "authority_contract_invalid",
        "evidence_integrity_invalid",
        "evidence_line_set_invalid",
        "evidence_source_invalid",
        "projection_input_invalid",
        "surface_contract_invalid",
    ),
    "capability.primitive.contract_failure": (
        "codec_input_type_invalid",
        "digest_contract_invalid",
    ),
    "first_specimen.capability.failure": (
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
    ),
    "line_event.readback.failure": (
        "event_migration_illegal",
        "line_event_unknown",
        "line_key_unknown",
    ),
    "quality.promotion.contract_failure": (
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
    ),
    "source.single-source-guard.failure": (
        "single_source_guard_allowed_urls_invalid",
        "single_source_guard_blocked",
        "single_source_guard_invalid_shape",
        "single_source_guard_missing",
        "single_source_guard_site_entries_mismatch",
        "single_source_guard_strict_source_required",
    ),
}


def test_INVARIANT__source_and_capability_family_names_and_literal_codes_are_exact() -> None:
    assert {family.name for _, family, _ in FAMILIES} == set(EXPECTED_CODES)

    for code_alias, family, family_name in FAMILIES:
        assert family.name == family_name
        assert family.codes == get_args(code_alias)
        assert family.codes == EXPECTED_CODES[family_name]
        assert len(family.codes) == len(set(family.codes))


@pytest.mark.parametrize(("code_alias", "family", "family_name"), FAMILIES)
def test_INVARIANT__source_and_capability_rejects_unknown_code(
    code_alias: object,
    family: FailureFamily,
    family_name: str,
) -> None:
    assert get_args(code_alias)

    with pytest.raises(
        ValueError,
        match=f"failure family {family_name}: unknown code 'NOT_REGISTERED'",
    ):
        family.fail("NOT_REGISTERED", "outside the closed family")


@pytest.mark.parametrize(("code_alias", "family", "family_name"), FAMILIES)
def test_FAILURE_PRESERVED__source_and_capability_fail_returns_kit_failure(
    code_alias: object,
    family: FailureFamily,
    family_name: str,
) -> None:
    assert family.codes == get_args(code_alias)
    code = family.codes[0]
    failure = family.fail(code, f"registered {family_name} failure", {"kind": "test"})

    assert type(failure) is Failure
    assert failure.failure is True
    assert failure.family == family_name
    assert failure.code == code
    assert failure.message == f"registered {family_name} failure"
    assert failure.context == {"kind": "test"}
    assert family.matches(failure)
