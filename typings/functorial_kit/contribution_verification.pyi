from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal, Never
from .contributions import Contribution
from .core.failure import Failure
from .law_witness import LawWitness

"""Inert contribution verification planning and runner-neutral registration."""
VerificationMode = Literal["full", "affected"]
VerificationResultKind = Literal["prerequisite", "check"]
VerificationResultStatus = Literal["not_run", "passed", "failed", "blocked"]
CONTRIBUTION_STRUCTURE_VERIFICATION_WITNESS_ID: str
CONTRIBUTION_STRUCTURE_VERIFICATION_CONTRIBUTION_ID: str
VERIFICATION_PLAN_KIND: str
@dataclass(frozen=True, slots=True)
class VerificationPrerequisite:
    witness: LawWitness
    inputs: tuple[str, ...]
    ...


@dataclass(frozen=True, slots=True)
class VerificationCheck:
    witness: LawWitness
    inputs: tuple[str, ...] = ...
    prerequisites: tuple[VerificationPrerequisite, ...] = ...


@dataclass(frozen=True, slots=True)
class ContributionVerification:
    rule_id: str
    inputs: tuple[str, ...]
    checks: tuple[VerificationCheck, ...]
    complete: bool = ...


@dataclass(frozen=True, slots=True)
class VerificationSource:
    projection: Contribution[Never, object]
    verification: ContributionVerification | None = ...


@dataclass(frozen=True, slots=True)
class VerificationChanges:
    contributions: tuple[str, ...] = ...
    rules: tuple[str, ...] = ...
    inputs: tuple[str, ...] = ...
    unknown: bool = ...


@dataclass(frozen=True, slots=True)
class VerificationPlanPrerequisite:
    id: str
    witness: LawWitness
    inputs: tuple[str, ...]
    ...


@dataclass(frozen=True, slots=True)
class VerificationPlanCheck:
    witness: LawWitness
    contribution_id: str
    inputs: tuple[str, ...]
    prerequisites: tuple[str, ...]
    ...


@dataclass(frozen=True, slots=True)
class VerificationSelection:
    mode: VerificationMode
    reasons: tuple[str, ...]
    contribution_ids: tuple[str, ...]
    ...


@dataclass(frozen=True, slots=True)
class VerificationPlan:
    kind: str
    projections: tuple[Contribution[Never, object], ...]
    prerequisites: tuple[VerificationPlanPrerequisite, ...]
    checks: tuple[VerificationPlanCheck, ...]
    selection: VerificationSelection
    ...


@dataclass(frozen=True, slots=True)
class VerificationResult:
    id: str
    kind: VerificationResultKind
    status: VerificationResultStatus
    blocked_by: tuple[str, ...] = ...
    error: BaseException | None = ...


@dataclass(frozen=True, slots=True)
class VerificationReport:
    complete: bool
    passed: bool
    results: tuple[VerificationResult, ...]
    ...


class VerificationBlockedError(Exception):
    blocked_by: tuple[str, ...]
    cause: BaseException | None
    def __init__(self, blocked_by: tuple[str, ...], cause: BaseException | None = ...) -> None:
        ...




class VerificationReturnedFailureError(Exception):
    failure: Failure
    def __init__(self, failure: Failure) -> None:
        ...




class VerificationReturnedAwaitableError(Exception):
    awaitable: object
    def __init__(self, awaitable: object) -> None:
        ...




@dataclass(frozen=True, slots=True)
class _ParsedPrerequisite:
    source: VerificationPrerequisite
    witness: LawWitness
    inputs: tuple[str, ...]
    ...


@dataclass(frozen=True, slots=True)
class _ParsedCheck:
    witness: LawWitness
    inputs: tuple[str, ...]
    prerequisites: tuple[_ParsedPrerequisite, ...]
    ...


@dataclass(frozen=True, slots=True)
class _ParsedVerification:
    rule_id: str
    inputs: tuple[str, ...]
    complete: bool
    checks: tuple[_ParsedCheck, ...]
    ...


@dataclass(frozen=True, slots=True)
class _ParsedSource:
    projection: Contribution[Never, object]
    verification: ContributionVerification | None
    ...


@dataclass(frozen=True, slots=True)
class _ParsedChanges:
    contributions: tuple[str, ...]
    rules: tuple[str, ...]
    inputs: tuple[str, ...]
    unknown: bool
    ...


@dataclass(frozen=True, slots=True)
class _WitnessOwner:
    scope: Literal["check", "prerequisite"]
    witness: LawWitness
    path: str
    source: object | None = ...


class _VerificationState:
    """Single-registration, single-thread execution state for synchronous runners."""
    def __init__(self, plan: VerificationPlan) -> None:
        ...

    def run(self, witness_id: str) -> object:
        ...

    def report(self) -> VerificationReport:
        ...



@dataclass(frozen=True, slots=True)
class VerificationRegistration:
    registered: int
    _state: _VerificationState
    def report(self) -> VerificationReport:
        ...



def plan_contribution_verification(sources: Sequence[VerificationSource], changes: VerificationChanges | None = ...) -> VerificationPlan | Failure:
    """Build an inert plan; no verification callback or assembly runs here."""
    ...

def register_verification_plan(plan: VerificationPlan, register: Callable[[str, Callable[[], object]], object]) -> VerificationRegistration | Failure:
    """Validate and register all tests, but run nothing until a runner callback is invoked."""
    ...
