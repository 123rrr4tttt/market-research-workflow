"""Request-local ordered interpretation for already-authorized typed effects.

This module owns only ordered value transport and the caller's explicit
continuation policy.  Effect lookup, permission checks, result states, partial
aggregation, and persistence remain with the calling domain.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TypeVar


StepT = TypeVar("StepT")
ValueT = TypeVar("ValueT")
ResultT = TypeVar("ResultT")


def interpret_ordered_sync(
    steps: Iterable[StepT],
    *,
    initial_value: ValueT,
    invoke: Callable[[StepT, ValueT], ResultT],
    continue_after: Callable[[ResultT], bool],
    output_value: Callable[[ResultT], ValueT],
) -> tuple[ResultT, ...]:
    """Interpret request-local steps once, in order, without runtime state.

    ``continue_after`` is a domain policy rather than a success predicate: a
    short-circuiting workflow can stop on any non-completed result, while a
    partial collection can continue after a classified leaf failure.  Every
    produced result is retained in declaration order.
    """

    current_value = initial_value
    results: list[ResultT] = []
    for step in steps:
        result = invoke(step, current_value)
        results.append(result)
        if not continue_after(result):
            break
        current_value = output_value(result)
    return tuple(results)
