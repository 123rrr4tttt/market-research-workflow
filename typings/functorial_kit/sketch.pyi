from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal
from .core.vocab import Vocabulary

"""Sketch registry (`sketches.json`) validator. Pure."""
SKETCHES_VERSION: str
Shape = Literal["map-in-context", "natural-transformation", "independent-requests", "dependent-sequence", "traverse", "views-fold", "command-adt", "capability-interface", "codec", "anchor", "resource-discipline", "parameter-family", "core-upgrade",]
shapes: Vocabulary
ClaimClass = Literal["strict", "testable", "heuristic"]
claim_classes: Vocabulary
ChangeKind = Literal["extension", "refinement", "loss"]
change_kinds: Vocabulary
@dataclass(frozen=True, slots=True)
class SketchIssue:
    entry: int
    message: str
    ...


def validate_sketches(text: str, test_id_exists: Callable[[str], bool]) -> list[SketchIssue]:
    ...
