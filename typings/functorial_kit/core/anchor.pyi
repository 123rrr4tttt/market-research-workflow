from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

"""Anchor: "I read this id set; refuse if it is no longer this set." """
@dataclass(frozen=True, slots=True)
class Anchor:
    ids: tuple[str, ...]
    digest: str
    ...


@dataclass(frozen=True, slots=True)
class Drift:
    kind: Literal["NONE", "DRIFT"]
    added: tuple[str, ...] = ...
    removed: tuple[str, ...] = ...


def anchor_of(ids: Iterable[str]) -> Anchor:
    ...

def drift_of(anchor: Anchor, current: Iterable[str]) -> Drift:
    ...
