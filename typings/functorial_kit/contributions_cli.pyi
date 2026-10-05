from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from .core.registry import RegistryKind

"""Read-only check and staged, idempotent sync for declarative contributions."""
OWNERSHIP_VERSION: str
OWNERSHIP_PATH: Path
REGISTRY_KINDS: tuple[RegistryKind, ...] = ...
@dataclass(frozen=True, slots=True)
class SyncPlan:
    issues: tuple[str, ...]
    writes: Mapping[Path, bytes]
    source_bytes: Mapping[Path, bytes | None]
    ...


@dataclass(frozen=True, slots=True)
class OwnedSketch:
    content: dict[str, object]
    entry_index: int
    ...


@dataclass(frozen=True, slots=True)
class OwnershipState:
    registries: dict[str, dict[str, dict[str, object]]]
    sketches: dict[str, OwnedSketch]
    ...


class WriteFailure(Exception):
    message: str
    ...


def perform_writes(root: Path, writes: Mapping[Path, bytes], planning_bytes: Mapping[Path, bytes | None]) -> list[Path]:
    """Stage every mutation, recheck planning sources, replace atomically, and roll back."""
    ...

def main(argv: Sequence[str]) -> int:
    ...

if __name__ == "__main__":
    ...
