from collections.abc import Callable, Iterable
from typing import TypeVar
from .failure import Failure, FailureFamily

"""Ordered fold: sort by a total key, then fold left. Permutation-invariant by construction."""
fold_failures: FailureFamily
Item = TypeVar("Item")
Acc = TypeVar("Acc")
def fold_ordered(items: Iterable[Item], total_key: Callable[[Item], str], step: Callable[[Acc, Item], Acc], empty: Acc) -> Acc | Failure:
    ...
