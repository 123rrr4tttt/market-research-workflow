from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypeGuard

"""Closed failure family. A failure is a plain value; core never raises it."""
@dataclass(frozen=True, slots=True)
class Failure:
    family: str
    code: str
    message: str
    context: Mapping[str, object] | None = ...
    @property
    def failure(self) -> bool:
        ...



@dataclass(frozen=True, slots=True)
class FailureFamily:
    name: str
    codes: tuple[str, ...]
    def fail(self, code: str, message: str, context: Mapping[str, object] | None = ...) -> Failure:
        ...

    def matches(self, value: object) -> bool:
        ...



def is_failure(value: object) -> TypeGuard[Failure]:
    ...

def define_failure_family(name: str, codes: tuple[str, ...]) -> FailureFamily:
    ...

class FailureError(Exception):
    """Shell-side only: lift a failure value into an exception at a declared boundary."""
    failure: Failure
    def __init__(self, failure: Failure) -> None:
        ...
