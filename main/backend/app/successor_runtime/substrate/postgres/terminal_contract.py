"""Neutral terminal contracts shared by lifecycle and optional admission."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from sqlalchemy.engine import Connection

from app.successor_runtime.runtime.assignments import RuntimeAssignment
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import InterpreterOutcome, RuntimeClaim
from app.successor_runtime.runtime.ports import RuntimeScope
from app.successor_runtime.runtime.reconciliation import ReconciliationHandlerOutcome

from .runtime_journal import ExactBindingConflict
from .runtime_lifecycle import ClaimedLifecycle, TerminalOutcome


class FirstSpecimenTerminalError(ExactBindingConflict):
    """The terminal admission closure cannot be reconstructed exactly."""


class FirstSpecimenTerminalLifecycleGap(FirstSpecimenTerminalError):
    """Shared lifecycle has not yet entered the frozen admission state."""


class FirstSpecimenCandidateDecodeError(FirstSpecimenTerminalError):
    """Staged canonical bytes do not decode to the frozen result type."""


class TerminalActivationPort(Protocol):
    """Capability-local adapter around the shared ``activate_run`` fold."""

    def activate_after_terminal(
        self,
        *,
        connection: Connection,
        scope: RuntimeScope,
        run_id: str,
        observed_at: datetime,
        authority_step_id: str | None = None,
        authority_digest: str | None = None,
    ) -> object: ...


class TerminalAdmissionStrategyPort(Protocol):
    """Optional admission work enlisted inside the generic terminal UoW."""

    def prepare_terminal(
        self,
        *,
        connection: Connection,
        scope: RuntimeScope,
        claim: RuntimeClaim,
        lifecycle: ClaimedLifecycle,
        outcome: InterpreterOutcome,
        terminal: TerminalOutcome,
    ) -> TerminalOutcome: ...

    def admit_reconciled_stage(
        self,
        *,
        connection: Connection,
        scope: RuntimeScope,
        assignment: RuntimeAssignment,
        outcome: ReconciliationHandlerOutcome,
    ) -> None: ...

    def recover_admission(
        self,
        *,
        connection: Connection,
        scope: RuntimeScope,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        observed_at: datetime,
    ) -> ReconciliationHandlerOutcome: ...


__all__ = [
    "FirstSpecimenCandidateDecodeError",
    "FirstSpecimenTerminalError",
    "FirstSpecimenTerminalLifecycleGap",
    "TerminalActivationPort",
    "TerminalAdmissionStrategyPort",
]
