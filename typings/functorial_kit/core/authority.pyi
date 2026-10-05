from dataclasses import dataclass
from typing import Generic, Literal, TypeVar
from .vocab import Vocabulary

"""Non-authoritative markers for boxed and ABI-preserving derived values."""
DerivedKind = Literal["view", "plan", "preflight", "simulation", "external_claim", "generated_evidence",]
derived_kinds: Vocabulary
T = TypeVar("T")
@dataclass(frozen=True, slots=True)
class NonAuthoritative(Generic[T]):
    derived_as: DerivedKind
    value: T
    fact_source: str = ...
    authoritative: Literal[False] = ...
    reverse_write: Literal[False] = ...


@dataclass(frozen=True, slots=True)
class NonAuthoritativeReturn:
    """Typing metadata for a legacy return whose runtime ABI must stay unchanged."""
    derived_as: DerivedKind
    fact_source: str
    witness: str
    authoritative: Literal[False] = ...
    reverse_write: Literal[False] = ...


@dataclass(frozen=True, slots=True)
class PreparedCommandReturn:
    """Typing metadata for a description that has not executed its effect."""
    effect_boundary: str
    witness: str
    ...


@dataclass(frozen=True, slots=True)
class CanonicalReadReturn:
    """Typing metadata for a read from the named canonical owner."""
    canonical_owner: str
    witness: str
    ...


@dataclass(frozen=True, slots=True)
class AuthoritativeWriteReturn:
    """Typing metadata for a return produced by the named canonical writer."""
    canonical_writer: str
    witness: str
    ...


class NonAuthoritativeDict(dict[str, object]):
    """Dict-compatible realization for an existing public dictionary ABI."""
    authoritative: Literal[False] = ...
    reverse_write: Literal[False] = ...
    derived_as: DerivedKind
    fact_source: str
    def __init__(self, value: dict[str, object], *, derived_as: DerivedKind, fact_source: str = ...) -> None:
        ...



def derived(kind: DerivedKind, value: T, *, fact_source: str = ...) -> NonAuthoritative[T]:
    ...

def is_non_authoritative(value: object) -> bool:
    ...
