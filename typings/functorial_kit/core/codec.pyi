from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Generic, TypeVar
from .failure import Failure

"""Codec: one pair T ⇄ canonical bytes with an exact-literal discriminant."""
T = TypeVar("T")
@dataclass(frozen=True, slots=True)
class Codec(Generic[T]):
    name: str
    discriminant: str
    discriminant_key: str
    keys: tuple[str, ...]
    _parse: Callable[[Mapping[str, object]], T | Failure]
    _to_wire: Callable[[T], Mapping[str, object]]
    def parse(self, value: object) -> T | Failure:
        ...

    def to_wire(self, value: T) -> Mapping[str, object]:
        ...

    def serialize(self, value: T) -> str | Failure:
        ...

    def digest(self, value: T) -> str | Failure:
        ...



def define_codec(*, name: str, discriminant: str, keys: tuple[str, ...], parse: Callable[[Mapping[str, object]], T | Failure], to_wire: Callable[[T], Mapping[str, object]], discriminant_key: str = ...) -> Codec[T]:
    ...
