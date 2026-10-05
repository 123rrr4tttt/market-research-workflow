from dataclasses import dataclass
from typing import NoReturn

"""Closed vocabulary: one owner, exhaustive matching everywhere else.

Pair with a ``Literal`` alias for the type level::

    Status = Literal["active", "blocked"]
    status = define_vocabulary("status", get_args(Status))
"""
@dataclass(frozen=True, slots=True)
class Vocabulary:
    name: str
    members: tuple[str, ...]
    def has(self, value: object) -> bool:
        ...

    def assert_never(self, value: NoReturn) -> NoReturn:
        ...



def define_vocabulary(name: str, members: tuple[str, ...]) -> Vocabulary:
    ...
