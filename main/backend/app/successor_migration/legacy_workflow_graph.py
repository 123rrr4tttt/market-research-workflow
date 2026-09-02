"""Read-only legacy WorkflowGraph oracle over the successor Program/Plan.

The oracle intentionally has no legacy graph parser, graph JSON input, store,
provider, database, or canonical-effect port.  It compares captured legacy and
successor observations against the same exact ``ProgramSpec`` and
``ExecutionPlan`` and returns only bounded observational compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.successor_runtime.capabilities.c1_slice_acceptance import (
    C1NamedStepObservation,
    C1RollbackBeforeAfter,
    C1RuntimeEvidenceRefs,
    C1SliceAcceptance,
    C1SliceId,
    accept_c1_slice,
)
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.language.plan import ExecutionPlan
from app.successor_runtime.language.program import ProgramSpec

__all__ = [
    "LegacyWorkflowGraphOracle",
    "LegacyWorkflowGraphOracleError",
    "LegacyWorkflowGraphReceipt",
]


class LegacyWorkflowGraphOracleError(ValueError):
    """Legacy and successor inputs do not bind the same exact Program/Plan."""


@dataclass(frozen=True, slots=True)
class LegacyWorkflowGraphReceipt:
    schema: str
    oracle_id: str
    acceptance: C1SliceAcceptance
    consumed_program_digest: str
    consumed_plan_digest: str
    provider_calls: int = 0
    store_writes: int = 0
    canonical_effect_calls: int = 0
    duplicated_effect_calls: int = 0
    graph_json_reads: int = 0
    compatibility_claim: str = "NAMED_OBSERVATIONAL_COMPATIBILITY_ONLY"
    receipt_digest: str = field(default="")

    def __post_init__(self) -> None:
        counters = (
            self.provider_calls,
            self.store_writes,
            self.canonical_effect_calls,
            self.duplicated_effect_calls,
            self.graph_json_reads,
        )
        if counters != (0, 0, 0, 0, 0):
            raise LegacyWorkflowGraphOracleError(
                "legacy WorkflowGraph oracle cannot execute or duplicate effects"
            )
        expected = content_digest(self, omit_fields=("receipt_digest",))
        if not self.receipt_digest:
            object.__setattr__(self, "receipt_digest", expected)
        elif self.receipt_digest != expected:
            raise LegacyWorkflowGraphOracleError(
                "receipt_digest does not bind the oracle receipt"
            )


class LegacyWorkflowGraphOracle:
    """Pure comparison facade; legacy WorkflowGraph is evidence, not runtime."""

    oracle_id = "legacy.workflow-graph.named-observation-oracle.v1"

    def __init__(self) -> None:
        self.comparison_calls = 0
        self.provider_calls = 0
        self.store_writes = 0
        self.canonical_effect_calls = 0
        self.duplicated_effect_calls = 0
        self.graph_json_reads = 0

    @staticmethod
    def _require_same_exact_program_plan(
        *,
        in_legacy_program: ProgramSpec,
        in_legacy_plan: ExecutionPlan,
        in_successor_program: ProgramSpec,
        in_successor_plan: ExecutionPlan,
    ) -> None:
        if (
            in_legacy_program.canonical_json() != in_successor_program.canonical_json()
            or in_legacy_program.program_digest != in_successor_program.program_digest
        ):
            raise LegacyWorkflowGraphOracleError(
                "legacy oracle and successor must consume the same exact ProgramSpec"
            )
        if (
            content_digest(in_legacy_plan) != content_digest(in_successor_plan)
            or in_legacy_plan.plan_digest != in_successor_plan.plan_digest
        ):
            raise LegacyWorkflowGraphOracleError(
                "legacy oracle and successor must consume the same exact ExecutionPlan"
            )

    def compare(
        self,
        *,
        in_slice_id: C1SliceId,
        in_legacy_program: ProgramSpec,
        in_legacy_plan: ExecutionPlan,
        in_successor_program: ProgramSpec,
        in_successor_plan: ExecutionPlan,
        in_legacy_step_observations: tuple[C1NamedStepObservation, ...],
        in_successor_step_observations: tuple[C1NamedStepObservation, ...],
        in_runtime_evidence: C1RuntimeEvidenceRefs,
        in_rollback_before_after: C1RollbackBeforeAfter,
    ) -> LegacyWorkflowGraphReceipt:
        """Compare named observations without interpreting either execution path."""

        self._require_same_exact_program_plan(
            in_legacy_program=in_legacy_program,
            in_legacy_plan=in_legacy_plan,
            in_successor_program=in_successor_program,
            in_successor_plan=in_successor_plan,
        )
        acceptance = accept_c1_slice(
            in_slice_id=in_slice_id,
            in_program=in_successor_program,
            in_plan=in_successor_plan,
            in_legacy_step_observations=in_legacy_step_observations,
            in_successor_step_observations=in_successor_step_observations,
            in_runtime_evidence=in_runtime_evidence,
            in_rollback_before_after=in_rollback_before_after,
        )
        self.comparison_calls += 1
        return LegacyWorkflowGraphReceipt(
            schema="mrw.functorial-successor.legacy-workflow-graph-receipt.v1",
            oracle_id=self.oracle_id,
            acceptance=acceptance,
            consumed_program_digest=in_successor_program.program_digest,
            consumed_plan_digest=in_successor_plan.plan_digest,
            provider_calls=self.provider_calls,
            store_writes=self.store_writes,
            canonical_effect_calls=self.canonical_effect_calls,
            duplicated_effect_calls=self.duplicated_effect_calls,
            graph_json_reads=self.graph_json_reads,
        )
