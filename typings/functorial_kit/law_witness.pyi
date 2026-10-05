from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal
from .core.failure import Failure, FailureFamily

"""Synchronous callable law witnesses and their runner-neutral registration adapter."""
LawWitnessIssueCode = Literal["invalid_witness", "invalid_id", "missing_callable", "async_callable", "duplicate_id", "invalid_register",]
law_witness_failures: FailureFamily
@dataclass(frozen=True, slots=True)
class LawWitness:
    id: str
    run: Callable[[], object]
    ...


@dataclass(frozen=True, slots=True)
class LawWitnessRegistration:
    registered: int
    ...


def define_law_witness(id: str, run: Callable[[], object]) -> LawWitness | Failure:
    """Define one inert synchronous witness. ``run`` is retained and never invoked."""
    ...

def law_witness_reference(witness: LawWitness) -> str:
    """Return the sketch-compatible test reference for a witness."""
    ...

def register_law_witnesses(witnesses: Sequence[object], register: Callable[[str, Callable[[], object]], object] | object) -> LawWitnessRegistration | Failure:
    """Validate the complete set, then synchronously register callbacks without running them."""
    ...
