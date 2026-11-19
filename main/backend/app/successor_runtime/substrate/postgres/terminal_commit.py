"""Generic PostgreSQL terminal lifecycle enlisted in the RuntimeNode UoW."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from sqlalchemy import MetaData
from sqlalchemy.engine import Connection

from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompiledStepRole,
    RuntimeAssignment,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import (
    ExactHandlerMismatch,
    InterpreterOutcome,
    RuntimeClaim,
)
from app.successor_runtime.runtime.ports import RuntimeScope
from app.successor_runtime.runtime.reconciliation import (
    ReconciliationHandlerOutcome,
    ReconciliationState,
)
from app.successor_runtime.runtime.transitions import EffectDisposition

from .models import ProjectTables, project_tables
from .plans import PlanRepository
from .runtime_activation import ActivationReceipt, selected_completion_steps
from .runtime_lifecycle import (
    ClaimedLifecycle,
    RuntimeLifecycleRepository,
    TerminalOutcome,
)
from .terminal_contract import (
    FirstSpecimenCandidateDecodeError,
    FirstSpecimenTerminalError,
    FirstSpecimenTerminalLifecycleGap,
    TerminalActivationPort,
    TerminalAdmissionStrategyPort,
)


PlanRepositoryFactory = Callable[[Connection, ProjectTables], PlanRepository]


class PostgresTerminalCommitHook:
    """Activate successors and complete parents in the exact terminal UoW."""

    def __init__(
        self,
        *,
        activation: TerminalActivationPort,
        admission_strategy: TerminalAdmissionStrategyPort | None = None,
        plan_repository_factory: PlanRepositoryFactory | None = None,
    ) -> None:
        self._activation = activation
        self._admission_strategy = admission_strategy
        self._plan_repository_factory: PlanRepositoryFactory = (
            plan_repository_factory or PlanRepository
        )

    @staticmethod
    def assignment_requires_admission(assignment: RuntimeAssignment) -> bool:
        """Whether this exact assignment needs an installed terminal strategy."""

        if assignment.step_role is CompiledStepRole.ADMISSION:
            return True
        if assignment.assignment_kind is AssignmentKind.VERIFY_ADMIT:
            return True
        return (
            assignment.assignment_kind is AssignmentKind.INTERPRET
            and assignment.return_contract_binding is not None
            and assignment.return_contract_binding.admission_required
        )

    def admission_available(self, assignment: RuntimeAssignment) -> bool:
        return not self.assignment_requires_admission(assignment) or (
            self._admission_strategy is not None
        )

    def validate_assignment(self, assignment: RuntimeAssignment) -> None:
        """Fail deployment binding before effect when admission is unavailable."""

        if not self.admission_available(assignment):
            raise ExactHandlerMismatch("terminal admission strategy is not installed")

    def prepare_terminal(
        self,
        *,
        connection: Connection,
        scope: RuntimeScope,
        claim: RuntimeClaim,
        lifecycle: ClaimedLifecycle,
        outcome: InterpreterOutcome,
        terminal: TerminalOutcome,
    ) -> TerminalOutcome:
        if outcome.disposition is not EffectDisposition.SUCCEEDED:
            return terminal
        if not self.assignment_requires_admission(claim.assignment):
            return terminal
        strategy = self._admission_strategy
        if strategy is None:
            raise FirstSpecimenTerminalError(
                "terminal admission strategy is not installed"
            )
        return strategy.prepare_terminal(
            connection=connection,
            scope=scope,
            claim=claim,
            lifecycle=lifecycle,
            outcome=outcome,
            terminal=terminal,
        )

    def recover_admission(
        self,
        *,
        connection: Connection,
        scope: RuntimeScope,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        observed_at: datetime,
    ) -> ReconciliationHandlerOutcome:
        strategy = self._admission_strategy
        if strategy is None:
            raise FirstSpecimenTerminalError(
                "terminal admission strategy is not installed for recovery"
            )
        return strategy.recover_admission(
            connection=connection,
            scope=scope,
            assignment=assignment,
            claim=claim,
            observed_at=observed_at,
        )

    def after_terminal(
        self,
        *,
        connection: Connection,
        scope: RuntimeScope,
        claim: RuntimeClaim,
        lifecycle: ClaimedLifecycle,
        outcome: InterpreterOutcome,
        terminal: TerminalOutcome,
    ) -> None:
        del lifecycle, outcome
        observed = terminal.observed_at or datetime.now().astimezone()
        if terminal.kind.value == "FAILED":
            self._settle_active_parents(
                connection=connection,
                scope=scope,
                run_id=claim.assignment.run_id,
                observed_at=observed,
            )
            return
        if terminal.kind.value != "SUCCEEDED":
            return
        self._activate_and_complete(
            connection=connection,
            scope=scope,
            assignment=claim.assignment,
            authority_digest=terminal.authority_digest,
            observed_at=observed,
        )

    def after_reconciliation(
        self,
        *,
        connection: Connection,
        scope: RuntimeScope,
        claim: RuntimeClaim,
        outcome: ReconciliationHandlerOutcome,
        observed_at: datetime,
    ) -> None:
        if outcome.result.state is not ReconciliationState.RESOLVED:
            return
        if outcome.result.disposition is EffectDisposition.FAILED:
            self._settle_active_parents(
                connection=connection,
                scope=scope,
                run_id=claim.assignment.run_id,
                observed_at=observed_at,
            )
            return
        if outcome.result.disposition is not EffectDisposition.SUCCEEDED:
            return
        assignment = claim.assignment
        if assignment.step_role is not None and assignment.step_role.value == "ADMISSION":
            strategy = self._admission_strategy
            if strategy is None:
                raise FirstSpecimenTerminalError(
                    "terminal admission strategy is not installed"
                )
            strategy.admit_reconciled_stage(
                connection=connection,
                scope=scope,
                assignment=assignment,
                outcome=outcome,
            )
        self._activate_and_complete(
            connection=connection,
            scope=scope,
            assignment=assignment,
            authority_digest=claim.claim_binding.authorization_digest,
            observed_at=observed_at,
        )

    def _activate_and_complete(
        self,
        *,
        connection: Connection,
        scope: RuntimeScope,
        assignment: RuntimeAssignment,
        authority_digest: str,
        observed_at: datetime | None,
    ) -> None:
        observed = observed_at or datetime.now().astimezone()
        activation = self._activation.activate_after_terminal(
            connection=connection,
            scope=scope,
            run_id=assignment.run_id,
            observed_at=observed,
            authority_step_id=assignment.step_id,
            authority_digest=authority_digest,
        )
        if assignment.plan_digest is None:
            raise FirstSpecimenTerminalError(
                "terminal completion requires exact Plan identity"
            )
        tables = project_tables(MetaData(), scope.project_scope.resolved_schema)
        plan = self._plan_repository_factory(connection, tables).get(
            scope, assignment.plan_digest
        )
        required_step_ids = frozenset(
            step.step_id
            for step in plan.ordered_steps
            if step.step_kind in {"EFFECT", "ADMISSION"}
        )
        journal_steps: frozenset[str] = frozenset()
        if isinstance(activation, ActivationReceipt):
            completion = selected_completion_steps(plan, activation.result)
            if completion is None:
                self._settle_active_parents(
                    connection=connection,
                    scope=scope,
                    run_id=assignment.run_id,
                    observed_at=observed,
                )
                return
            required_step_ids, journal_steps = completion
        RuntimeLifecycleRepository(connection, scope).complete_if_satisfied(
            assignment.run_id,
            required_step_ids=required_step_ids,
            journal_succeeded_step_ids=journal_steps,
            authority_digest=authority_digest,
            observed_at=observed,
        )
        self._settle_active_parents(
            connection=connection,
            scope=scope,
            run_id=assignment.run_id,
            observed_at=observed,
        )

    def _settle_active_parents(
        self,
        *,
        connection: Connection,
        scope: RuntimeScope,
        run_id: str,
        observed_at: datetime,
    ) -> None:
        settle_parents = getattr(
            self._activation, "settle_parents_after_terminal", None
        )
        if settle_parents is not None:
            settle_parents(
                connection=connection,
                scope=scope,
                run_id=run_id,
                observed_at=observed_at,
            )


__all__ = [
    "FirstSpecimenCandidateDecodeError",
    "FirstSpecimenTerminalError",
    "FirstSpecimenTerminalLifecycleGap",
    "PlanRepositoryFactory",
    "PostgresTerminalCommitHook",
    "TerminalActivationPort",
]
