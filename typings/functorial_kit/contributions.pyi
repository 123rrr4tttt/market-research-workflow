from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Generic, Never, Protocol, TypeVar
from .core.failure import Failure, FailureFamily
from .core.vocab import Vocabulary

"""Declarative contribution composition.

The descriptions are pure: defining and composing them never invokes a factory. Assembly is
an explicit runtime operation and therefore lives on the composed value, not in projection.
"""
Context = TypeVar("Context", contravariant=True)
Binding = TypeVar("Binding", covariant=True)
contribution_failures: FailureFamily
@dataclass(frozen=True, slots=True)
class ContributionObject:
    id: str
    kind: str
    owner: str
    references: tuple[str, ...] = ...


@dataclass(frozen=True, slots=True)
class ContributionSketch:
    """Owned sketch projection: identity comes from a contributed domain object."""
    object_id: str
    entry: Mapping[str, object]
    ...


class ContributionCodec(Protocol):
    """Registry-only codec projection; composition still requires the real Codec object."""
    @property
    def name(self) -> str:
        ...

    @property
    def discriminant(self) -> str:
        ...



@dataclass(frozen=True, slots=True)
class ContributionCatalog:
    """Heterogeneous declarations have no shared assembly context.

    ``Never`` keeps their factories unavailable through this metadata view;
    native typed contributions retain their own context and binding association.
    """
    contributions: tuple[Contribution[Never, object], ...]
    registries_dir: str | None = ...
    sketches_path: str | None = ...


@dataclass(frozen=True, slots=True)
class ContributionSpec(Generic[Context, Binding]):
    id: str
    owner: str
    depends_on: tuple[str, ...] = ...
    objects: tuple[ContributionObject, ...] = ...
    codecs: tuple[ContributionCodec, ...] = ...
    vocabularies: tuple[Vocabulary, ...] = ...
    failures: tuple[FailureFamily, ...] = ...
    ports: tuple[Mapping[str, object], ...] = ...
    sketches: tuple[ContributionSketch, ...] = ...
    factory: Callable[[Context], Binding] | None = ...


@dataclass(frozen=True, slots=True)
class Contribution(Generic[Context, Binding]):
    id: str
    owner: str
    depends_on: tuple[str, ...]
    objects: tuple[ContributionObject, ...]
    codecs: tuple[ContributionCodec, ...]
    vocabularies: tuple[Vocabulary, ...]
    failures: tuple[FailureFamily, ...]
    ports: tuple[Mapping[str, object], ...]
    sketches: tuple[ContributionSketch, ...]
    factory: Callable[[Context], Binding] | None
    ...


def define_contribution(spec: ContributionSpec[Context, Binding]) -> Contribution[Context, Binding]:
    """Return the declarative contribution without interpreting or invoking its factory."""
    ...

@dataclass(frozen=True, slots=True)
class ContributionRegistries:
    codecs: tuple[Mapping[str, object], ...] = ...
    vocabularies: tuple[Mapping[str, object], ...] = ...
    failures: tuple[Mapping[str, object], ...] = ...
    ports: tuple[Mapping[str, object], ...] = ...


@dataclass(frozen=True, slots=True)
class ComposedContributions(Generic[Context, Binding]):
    contributions: tuple[Contribution[Context, Binding], ...] = ...
    objects: tuple[ContributionObject, ...] = ...
    registry_entries: ContributionRegistries = ...
    sketches: tuple[Mapping[str, object], ...] = ...
    def assemble(self, context: Context) -> tuple[Binding, ...]:
        """Explicit assembly of implemented contributions, preserving declaration order."""
        ...



def compose_contributions(contributions: Sequence[Contribution[Context, Binding]]) -> ComposedContributions[Context, Binding] | Failure:
    """Validate typed declarations and compose them in input order.

    All validation issues are collected before one ``Failure`` is returned. Malformed specs are
    not traversed as if they were Contributions; their position is still reported.
    """
    ...
