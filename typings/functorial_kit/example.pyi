from dataclasses import dataclass
from typing import Literal, Protocol
from .core.codec import Codec

"""Example objects shipped with the kit: used by scaffolds, law-suite examples, and golden vectors."""
@dataclass(frozen=True, slots=True)
class Nested:
    flag: bool
    note: str | None
    ...


@dataclass(frozen=True, slots=True)
class KitExample:
    id: str
    tags: tuple[str, ...]
    count: int
    nested: Nested
    kind: Literal["kit-example.v1"] = ...


kit_example_codec: Codec[KitExample]
class Counter(Protocol):
    """Example port used by the scaffold's law suite."""
    def increment(self, by: int) -> None:
        ...

    def read(self) -> int:
        ...



class InMemoryCounter:
    def __init__(self) -> None:
        ...

    def increment(self, by: int) -> None:
        ...

    def read(self) -> int:
        ...
