from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, TypeVar
from hypothesis import strategies as st
from .core.codec import Codec

"""Law-suite templates: functions returning pytest test classes, parameterized by the implementation.

Usage in a test module::

    TestRecordCodec = codec_laws(record_codec, record_strategy)

Test names carry the law tag as the first token after ``test_``.
"""
T = TypeVar("T")
Impl = TypeVar("Impl")
@dataclass(frozen=True, slots=True)
class Deviation:
    law: str
    reason: str
    ...


def codec_laws(codec: Codec[T], strategy: st.SearchStrategy[T], deviations: Sequence[Deviation] = ...) -> type:
    ...

@dataclass(frozen=True, slots=True)
class FoldSpec(Generic[T]):
    name: str
    total_key: Callable[[T], str]
    step: Callable[[T, T], T]
    empty: T
    items: st.SearchStrategy[list[T]]
    ...


def fold_laws(spec: FoldSpec[T], deviations: Sequence[Deviation] = ...) -> type:
    ...

def anchor_laws(ids_strategy: st.SearchStrategy[list[str]] | None = ...) -> type:
    ...

@dataclass(frozen=True, slots=True)
class Idempotent(Generic[Impl]):
    name: str
    run: Callable[[Impl], object]
    ...


@dataclass(frozen=True, slots=True)
class Ordered(Generic[Impl]):
    name: str
    first: Callable[[Impl], object]
    second: Callable[[Impl], object]
    observe: Callable[[Impl], object]
    commutes: bool
    ...


@dataclass(frozen=True, slots=True)
class FailureLaw(Generic[Impl]):
    name: str
    codes: tuple[str, ...]
    run: Callable[[Impl], object]
    ...


@dataclass(frozen=True, slots=True)
class PortLawSpec(Generic[Impl]):
    idempotent: Sequence[Idempotent[Impl]] = ...
    ordered: Sequence[Ordered[Impl]] = ...
    failures: Sequence[FailureLaw[Impl]] = ...
    deviations: Sequence[Deviation] = ...


def port_laws(port_name: str, make_impl: Callable[[], Impl], spec: PortLawSpec[Impl]) -> type:
    ...

def vector_laws(codec: Codec[T], vectors_dir: str | Path) -> type:
    ...
