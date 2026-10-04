"""Legacy WorkflowGraph as a no-effect named-observation oracle only."""

from __future__ import annotations

import inspect
from dataclasses import replace

import pytest

from app.successor_migration import legacy_workflow_graph as legacy_graph
from app.successor_runtime.capabilities.c1_slice_acceptance import (
    C1StepStatus,
)
from app.successor_runtime.capabilities.checksum import content_digest

from .test_p5_c1_slice_programs import (
    _c8_writing_program_plan,
    _observations,
    _rollback,
    _runtime_evidence,
)


def _compare(
    oracle: legacy_graph.LegacyWorkflowGraphOracle,
    status: C1StepStatus,
):
    program, plan = _c8_writing_program_plan()
    observations = _observations(plan, status)
    return oracle.compare(
        in_slice_id="B",
        in_legacy_program=program,
        in_legacy_plan=plan,
        in_successor_program=program,
        in_successor_plan=plan,
        in_legacy_step_observations=observations,
        in_successor_step_observations=observations,
        in_runtime_evidence=_runtime_evidence(),
        in_rollback_before_after=_rollback(),
    )


@pytest.mark.parametrize(
    ("status", "accepted", "finding"),
    (
        (C1StepStatus.SUCCESS, True, None),
        (C1StepStatus.DEGRADED, True, None),
        (C1StepStatus.BLOCKED, False, "OBSERVED_BLOCKED"),
        (C1StepStatus.FAILURE, False, "OBSERVED_FAILURE"),
        (C1StepStatus.UNKNOWN, False, "OBSERVED_UNKNOWN"),
    ),
)
def test_oracle_supports_bounded_named_statuses_without_executing_effects(
    status: C1StepStatus,
    accepted: bool,
    finding: str | None,
) -> None:
    oracle = legacy_graph.LegacyWorkflowGraphOracle()
    receipt = _compare(oracle, status)

    assert receipt.acceptance.observational_compatibility is True
    assert receipt.acceptance.accepted is accepted
    if finding is not None:
        assert any(
            item.startswith(finding) for item in receipt.acceptance.blocking_findings
        )
    if status == C1StepStatus.DEGRADED:
        assert any(
            item.startswith("MATCHED_DEGRADED_OBSERVATION")
            for item in receipt.acceptance.declared_differences
        )
    assert receipt.compatibility_claim == "NAMED_OBSERVATIONAL_COMPATIBILITY_ONLY"
    assert receipt.provider_calls == 0
    assert receipt.store_writes == 0
    assert receipt.canonical_effect_calls == 0
    assert receipt.duplicated_effect_calls == 0
    assert receipt.graph_json_reads == 0
    assert oracle.comparison_calls == 1


def test_named_observation_mismatch_is_declared_and_blocks_compatibility() -> None:
    program, plan = _c8_writing_program_plan()
    legacy = _observations(plan)
    successor_first = replace(
        legacy[0],
        status=C1StepStatus.FAILURE,
        result_digest=content_digest({"successor": "failure"}),
    )
    oracle = legacy_graph.LegacyWorkflowGraphOracle()
    receipt = oracle.compare(
        in_slice_id="B",
        in_legacy_program=program,
        in_legacy_plan=plan,
        in_successor_program=program,
        in_successor_plan=plan,
        in_legacy_step_observations=legacy,
        in_successor_step_observations=(successor_first,) + legacy[1:],
        in_runtime_evidence=_runtime_evidence(),
        in_rollback_before_after=_rollback(),
    )

    assert receipt.acceptance.observational_compatibility is False
    assert receipt.acceptance.accepted is False
    assert receipt.acceptance.blocking_findings == (
        f"OBSERVATION_MISMATCH:{legacy[0].name}",
    )
    assert any(
        legacy[0].name in item for item in receipt.acceptance.declared_differences
    )


def test_oracle_rejects_any_second_program_or_plan_before_observation() -> None:
    program, plan = _c8_writing_program_plan()
    observations = _observations(plan)
    drifted_plan = replace(plan, plan_id="plan:second-graph-is-forbidden")
    oracle = legacy_graph.LegacyWorkflowGraphOracle()

    with pytest.raises(
        legacy_graph.LegacyWorkflowGraphOracleError,
        match="same exact ExecutionPlan",
    ):
        oracle.compare(
            in_slice_id="B",
            in_legacy_program=program,
            in_legacy_plan=plan,
            in_successor_program=program,
            in_successor_plan=drifted_plan,
            in_legacy_step_observations=observations,
            in_successor_step_observations=observations,
            in_runtime_evidence=_runtime_evidence(),
            in_rollback_before_after=_rollback(),
        )

    assert oracle.comparison_calls == 0
    assert oracle.provider_calls == 0
    assert oracle.store_writes == 0
    assert oracle.canonical_effect_calls == 0
    assert oracle.duplicated_effect_calls == 0
    assert oracle.graph_json_reads == 0


def test_oracle_surface_has_no_legacy_runtime_db_provider_or_graph_json_input() -> None:
    source = inspect.getsource(legacy_graph)
    forbidden_imports = (
        "app.services.workflow_graph",
        "sqlalchemy",
        "openai",
        "app.models",
        "app.successor_runtime.substrate",
    )
    assert all(item not in source for item in forbidden_imports)
    signature = inspect.signature(legacy_graph.LegacyWorkflowGraphOracle.compare)
    assert "graph_json" not in signature.parameters
    assert "provider" not in signature.parameters
    assert "database" not in signature.parameters


def test_oracle_claim_is_not_naturality_commutativity_or_effect_equivalence() -> None:
    receipt = _compare(
        legacy_graph.LegacyWorkflowGraphOracle(),
        C1StepStatus.SUCCESS,
    )
    assert receipt.compatibility_claim == "NAMED_OBSERVATIONAL_COMPATIBILITY_ONLY"
    assert receipt.acceptance.compatibility_claim == (
        "NAMED_OBSERVATIONAL_COMPATIBILITY_ONLY"
    )
    assert "naturality" not in receipt.compatibility_claim.lower()
    assert "commut" not in receipt.compatibility_claim.lower()
    assert "effect" not in receipt.compatibility_claim.lower()


def test_named_observation_requires_exact_step_order() -> None:
    program, plan = _c8_writing_program_plan()
    observations = _observations(plan)
    swapped = tuple(reversed(observations))
    oracle = legacy_graph.LegacyWorkflowGraphOracle()
    with pytest.raises(ValueError, match="exact ordered ExecutionPlan steps"):
        oracle.compare(
            in_slice_id="B",
            in_legacy_program=program,
            in_legacy_plan=plan,
            in_successor_program=program,
            in_successor_plan=plan,
            in_legacy_step_observations=swapped,
            in_successor_step_observations=swapped,
            in_runtime_evidence=_runtime_evidence(),
            in_rollback_before_after=_rollback(),
        )
