from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal
from ..core.registry import Registry
from .config import KitConfig
from ..core.vocab import Vocabulary

"""Pure architecture scans over in-memory source files. Regex-based; heuristic gates by design."""
GateName = Literal["import-direction", "no-throw-in-core", "registry-complete", "one-representation", "fakes-run-laws", "derived-marked", "sketch-valid",]
gate_names: Vocabulary
@dataclass(frozen=True, slots=True)
class SourceFile:
    path: str
    text: str
    ...


@dataclass(frozen=True, slots=True)
class Violation:
    gate: GateName
    file: str
    line: int
    message: str
    severity: Literal["fail", "report"]
    ...


@dataclass(frozen=True, slots=True)
class Declarations:
    vocabularies: Mapping[str, tuple[str, ...]]
    failures: Mapping[str, tuple[str, ...]]
    codecs: Mapping[str, str]
    ports: frozenset[str]
    ...


@dataclass(frozen=True, slots=True)
class Registries:
    codecs: Registry
    vocabularies: Registry
    failures: Registry
    ports: Registry
    ...


@dataclass(frozen=True, slots=True)
class ScanInput:
    config: KitConfig
    sources: Sequence[SourceFile]
    tests: Sequence[SourceFile]
    registries: Registries
    sketches_text: str | None
    ...


def collect_declarations(sources: Sequence[SourceFile]) -> Declarations:
    ...

def scan_architecture(inp: ScanInput) -> list[Violation]:
    ...

def violation_key(v: Violation) -> str:
    ...

@dataclass(frozen=True, slots=True)
class Ratchet:
    new_violations: tuple[Violation, ...]
    stale_baseline: tuple[str, ...]
    reports: tuple[Violation, ...]
    ...


def ratchet(violations: Sequence[Violation], baseline: Sequence[str]) -> Ratchet:
    ...

TestIdExists = Callable[[str], bool]
