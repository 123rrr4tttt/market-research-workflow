from __future__ import annotations

from typing import get_args

import pytest
from functorial_kit import Failure

from mrw_functorial_kit.core.w07_semantics import (
    W07LanguageFailureCode,
    W07OpsSurfaceFailureCode,
    W07ResearchFailureCode,
    W07RuntimeFailureCode,
    language_failures,
    ops_surface_failures,
    research_failures,
    runtime_failures,
)


FAMILIES = (
    (W07LanguageFailureCode, language_failures, "successor.language.failure"),
    (W07OpsSurfaceFailureCode, ops_surface_failures, "successor.ops_surface.failure"),
    (W07ResearchFailureCode, research_failures, "successor.research.failure"),
    (W07RuntimeFailureCode, runtime_failures, "successor.runtime.failure"),
)


def test_INVARIANT__w07_family_names_and_codes_are_exact() -> None:
    expected_codes = {
        "successor.language.failure": (
            "CANONICAL_VALUE_INVALID",
            "COMPILED_PLAN_INVALID",
            "CONTRACT_BINDING_MISSING",
            "CONTRACT_REGISTRY_INVALID",
            "DEPENDENCY_CYCLE",
            "DUPLICATE_STEP_ID",
            "FIRST_SPECIMEN_INPUT_REJECTED",
            "INVALID_PROGRAM",
            "MISSING_DEPENDENCY",
            "MISSING_OPERATION_CONTRACT_RESOLVER",
            "PROFILE_INVALID",
            "PROGRAM_CODEC_INVALID",
            "PROGRAM_DIGEST_MISMATCH",
            "PROGRAM_MATERIALIZATION_INVALID",
            "PROGRAM_TYPE_INVALID",
            "SUCCESSOR_MATERIALIZATION_REJECTED",
            "TRANSFORM_BINDING_MISSING",
            "TRANSFORM_CALLABLE_INVALID",
            "TRANSFORM_REGISTRY_INVALID",
            "TRANSFORM_TYPE_INVALID",
            "TRAVERSAL_SHAPE_BINDING_REQUIRED",
            "TYPE_MISMATCH",
            "UNKNOWN_NODE_KIND",
            "UNKNOWN_RETURN_CONTRACT",
            "UNRESOLVED_OPERATION_CONTRACT",
            "UNSUPPORTED_TRAVERSAL",
        ),
        "successor.ops_surface.failure": (
            "AUTHORITY_PROJECTION_FORBIDDEN",
            "DASHBOARD_ADMIN_SURFACE_INVALID",
            "HEALTH_MATRIX_SURFACE_INVALID",
            "NORMALIZED_STRING_TUPLE_INVALID",
            "NORMALIZED_TEXT_INVALID",
            "OPS_MISC_SURFACE_INVALID",
            "PROJECTS_CONFIG_SURFACE_INVALID",
            "RUNTIME_OPS_SURFACE_INVALID",
        ),
        "successor.research.failure": (
            "ARTIFACT_IDENTITY_INVALID",
            "ARTIFACT_INVALID",
            "CANONICAL_ENCODING_INVALID",
            "CANONICAL_JSON_ROOT_INVALID",
            "CANONICAL_VALUE_UNSUPPORTED",
            "CLAIM_INVALID",
            "DELIVERY_ATTEMPT_INVALID",
            "DELIVERY_INTENT_INVALID",
            "DIGEST_FINALIZATION_INVALID",
            "EVIDENCE_QUALIFICATION_INVALID",
            "GAP_INVALID",
            "INQUIRY_INVALID",
            "MATERIAL_REF_INVALID",
            "RELATION_INVALID",
            "RESEARCH_INTENT_INVALID",
            "RESEARCH_OBJECT_REF_INVALID",
            "RESEARCH_PLAN_INVALID",
            "SOURCE_REF_INVALID",
            "VALIDITY_INVALID",
        ),
        "successor.runtime.failure": (
            "ACTIVATION_INVALID",
            "ADMISSION_BINDING_REJECTED",
            "ADMISSION_COMMIT_READBACK_INVALID",
            "ADMISSION_REGISTRY_INVALID",
            "ADMISSION_ROW_INVALID",
            "ASSIGNMENT_INVALID",
            "AUTHORITY_DRIFT",
            "AUTHORITY_EXPIRED",
            "AUTHORITY_GRANT_INVALID",
            "BRANCH_CONTROL_INVALID",
            "BRANCH_DECISION_UNRESOLVED",
            "CAPACITY_CONTRACT_INVALID",
            "CLAIM_BINDING_INVALID",
            "CLOCK_OBSERVATION_INVALID",
            "CONTROL_PLANE_PERMISSION_DENIED",
            "CONTROL_PLANE_SCOPE_INVALID",
            "FACADE_CONTRACT_INVALID",
            "FACADE_INPUT_INVALID",
            "FACADE_PORT_RESULT_INVALID",
            "FAILURE_POLICY_INVALID",
            "GUARD_EXPRESSION_INVALID",
            "ILLEGAL_RUN_TRANSITION",
            "ILLEGAL_STEP_TRANSITION",
            "LEGACY_OBSERVATION_INVALID",
            "NODE_CLAIM_REJECTED",
            "NODE_CONTRACT_INVALID",
            "NODE_HANDLER_CONTRACT_INVALID",
            "NODE_PORT_RESULT_INVALID",
            "NON_START_PROOF_INVALID",
            "PROCESS_OBSERVATION_INVALID",
            "PROJECT_SCOPE_INVALID",
            "QUALIFICATION_INVALID",
            "RECONCILIATION_BINDING_REJECTED",
            "RECONCILIATION_READBACK_INVALID",
            "RECONCILIATION_RESULT_INVALID",
            "REPLAY_BINDING_DRIFT",
            "REPLAY_EVENT_INVALID",
            "REPLAY_PROJECTION_INVALID",
            "REPLAY_SEQUENCE_INVALID",
            "REPLAY_STATE_INVALID",
            "RESOURCE_CONTRACT_INVALID",
            "RUN_EVENT_INVALID",
            "STAGED_RECOVERY_BINDING_REJECTED",
            "STAGED_RECOVERY_READBACK_INVALID",
            "STAGED_RECOVERY_REQUEST_INVALID",
            "SUCCESSOR_ATTEMPT_NOT_AUTHORIZED",
            "VERIFICATION_BINDING_INVALID",
            "WORK_ITEM_INVALID",
        ),
    }

    for code_alias, family, expected_name in FAMILIES:
        assert family.name == expected_name
        assert family.codes == get_args(code_alias)
        assert family.codes == expected_codes[expected_name]


def test_INVARIANT__w07_rejects_unknown_code() -> None:
    with pytest.raises(ValueError, match=r"unknown code 'NOT_REGISTERED'"):
        language_failures.fail("NOT_REGISTERED", "unknown")
    with pytest.raises(ValueError, match=r"unknown code 'NOT_REGISTERED'"):
        ops_surface_failures.fail("NOT_REGISTERED", "unknown")
    with pytest.raises(ValueError, match=r"unknown code 'NOT_REGISTERED'"):
        research_failures.fail("NOT_REGISTERED", "unknown")
    with pytest.raises(ValueError, match=r"unknown code 'NOT_REGISTERED'"):
        runtime_failures.fail("NOT_REGISTERED", "unknown")


def test_INVARIANT__w07_failures_are_values_with_exact_identity() -> None:
    expected = (
        (language_failures, "CANONICAL_VALUE_INVALID"),
        (ops_surface_failures, "AUTHORITY_PROJECTION_FORBIDDEN"),
        (research_failures, "ARTIFACT_IDENTITY_INVALID"),
        (runtime_failures, "ACTIVATION_INVALID"),
    )

    for family, code in expected:
        failure = family.fail(code, "registered W07 failure", {"kind": "test"})
        assert isinstance(failure, Failure)
        assert failure.failure is True
        assert failure.family == family.name
        assert failure.code == code
        assert failure.message == "registered W07 failure"
        assert failure.context == {"kind": "test"}
        assert family.matches(failure)
