from collections.abc import Callable
from typing import ParamSpec, TypeVar, overload

_P = ParamSpec("_P")
_R = TypeVar("_R")

class Signal:
    name: str | None
    providing_args: set[str]

    @overload
    def connect(
        self,
        receiver: Callable[_P, _R],
        /,
        *,
        sender: object | None = None,
        weak: bool = True,
        dispatch_uid: object | None = None,
        retry: bool = False,
    ) -> Callable[_P, _R]: ...
    @overload
    def connect(
        self,
        receiver: None = None,
        /,
        *,
        sender: object | None = None,
        weak: bool = True,
        dispatch_uid: object | None = None,
        retry: bool = False,
    ) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]: ...
    def _live_receivers(self, sender: object | None) -> list[object]: ...
