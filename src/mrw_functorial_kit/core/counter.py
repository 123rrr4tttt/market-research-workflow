"""Example port. Core: Protocol only; interpreters live in shell."""

from typing import Protocol


class Counter(Protocol):
    def increment(self, by: int) -> None: ...

    def read(self) -> int: ...
