"""Invocation identity supplied only by the native dispatch host."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class NativeToolCallContext:
    call_id: str
    thread_id: str
    turn_id: str


_current_call: ContextVar[NativeToolCallContext | None] = ContextVar("native_tool_call", default=None)


def current_native_tool_call_context() -> NativeToolCallContext | None:
    return _current_call.get()


@contextmanager
def native_tool_call_context(context: NativeToolCallContext) -> Iterator[None]:
    token = _current_call.set(context)
    try:
        yield
    finally:
        _current_call.reset(token)
