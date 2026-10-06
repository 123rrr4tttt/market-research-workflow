from collections.abc import Callable, Iterable
from typing import Concatenate, Literal, ParamSpec, TypeVar, overload

from celery.app.control import Control
from celery.app.registry import TaskRegistry
from celery.app.task import Task
from celery.app.utils import Settings
from celery.result import AsyncResult

_P = ParamSpec("_P")
_R = TypeVar("_R")

class Celery:
    main: str | None
    strict_typing: bool
    conf: Settings
    control: Control
    tasks: TaskRegistry

    def __init__(
        self,
        main: str | None = None,
        *,
        backend: str | None = None,
        broker: str | None = None,
        include: Iterable[str] | None = None,
        set_as_current: bool = True,
        autofinalize: bool = True,
        namespace: str | None = None,
        strict_typing: bool = True,
        **kwargs: object,
    ) -> None: ...

    @overload
    def task(self, function: Callable[_P, _R], /) -> Task[_P, _R]: ...
    @overload
    def task(
        self,
        *,
        bind: Literal[False] = False,
        name: str | None = None,
        **options: object,
    ) -> Callable[[Callable[_P, _R]], Task[_P, _R]]: ...
    @overload
    def task(
        self,
        *,
        bind: Literal[True],
        name: str | None = None,
        **options: object,
    ) -> Callable[[Callable[Concatenate[Task[_P, _R], _P], _R]], Task[_P, _R]]: ...

    def autodiscover_tasks(
        self,
        packages: Iterable[str] | Callable[[], Iterable[str]] | None = None,
        related_name: str | None = None,
        force: bool = False,
    ) -> object: ...
    def AsyncResult(self, id: str, *, backend: object | None = None) -> AsyncResult[object]: ...
