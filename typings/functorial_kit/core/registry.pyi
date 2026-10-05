from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal
from .failure import Failure, FailureFamily
from .vocab import Vocabulary

"""Append-only single-file registries with exact version literals. Pure: takes file text."""
registry_failures: FailureFamily
RegistryKind = Literal["codecs", "vocabularies", "failures", "ports"]
registry_kinds: Vocabulary
REGISTRY_VERSIONS: Mapping[str, str] = ...
@dataclass(frozen=True, slots=True)
class Registry:
    kind: RegistryKind
    entries: tuple[Mapping[str, object], ...]
    def members_by_name(self) -> dict[str, tuple[str, ...]]:
        ...



def parse_registry(kind: RegistryKind, text: str) -> Registry | Failure:
    ...

@dataclass(frozen=True, slots=True)
class Completeness:
    missing_from_registry: tuple[str, ...]
    missing_from_source: tuple[str, ...]
    members_differ: tuple[str, ...]
    ...


def completeness(registered: Mapping[str, Sequence[str]], declared: Mapping[str, Sequence[str]]) -> Completeness:
    ...
