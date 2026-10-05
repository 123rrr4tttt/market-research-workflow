import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

"""Read-only lexical inspection of composed contribution declarations."""
INSPECT_VERSION: str
MATCH_LIMIT: int
SOURCE_EXTENSIONS: set[str]
IGNORED_DIRECTORIES: set[str]
SearchClassification = Literal["source", "test"]
InspectIssue = dict[str, str]
@dataclass(frozen=True, slots=True)
class SearchFile:
    path: Path
    relative: str
    classification: SearchClassification
    ...


@dataclass(frozen=True, slots=True)
class SearchScope:
    core_paths: tuple[str, ...]
    shell_paths: tuple[str, ...]
    test_paths: tuple[str, ...]
    missing_paths: tuple[str, ...]
    ...


def inspect_contributions(args: argparse.Namespace) -> int:
    ...

def main(argv: Sequence[str]) -> int:
    ...

if __name__ == "__main__":
    ...
