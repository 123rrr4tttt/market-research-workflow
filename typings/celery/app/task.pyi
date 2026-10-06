from collections.abc import Mapping
from typing import Generic, ParamSpec, TypeVar, overload

from celery.result import AsyncResult, EagerResult

_P = ParamSpec("_P")
_R_co = TypeVar("_R_co", covariant=True)
_A = TypeVar("_A")
_B = TypeVar("_B")

class Context:
    id: str | None
    task: str | None
    args: tuple[object, ...] | None
    kwargs: Mapping[str, object] | None
    hostname: str | None
    delivery_info: Mapping[str, object] | None
    retries: int

    def get(self, key: str, default: object | None = None) -> object | None: ...

class Task(Generic[_P, _R_co]):
    name: str
    request: Context

    def __call__(self, *args: _P.args, **kwargs: _P.kwargs) -> _R_co: ...
    def run(self, *args: _P.args, **kwargs: _P.kwargs) -> _R_co: ...
    def delay(self, *args: _P.args, **kwargs: _P.kwargs) -> AsyncResult[_R_co]: ...
    def apply(
        self,
        args: tuple[object, ...] | None = None,
        kwargs: Mapping[str, object] | None = None,
        task_id: str | None = None,
        **options: object,
    ) -> EagerResult[_R_co]: ...
    @overload
    def apply_async(
        self: Task[[], _R_co],
        args: tuple[()] | None = None,
        kwargs: Mapping[str, object] | None = None,
        task_id: str | None = None,
        *,
        queue: str | None = None,
        routing_key: str | None = None,
        **options: object,
    ) -> AsyncResult[_R_co]: ...
    @overload
    def apply_async(
        self: Task[[_A], _R_co],
        args: tuple[_A] | None = None,
        kwargs: Mapping[str, object] | None = None,
        task_id: str | None = None,
        *,
        queue: str | None = None,
        routing_key: str | None = None,
        **options: object,
    ) -> AsyncResult[_R_co]: ...
    @overload
    def apply_async(
        self: Task[[_A, _B], _R_co],
        args: tuple[_A, _B] | None = None,
        kwargs: Mapping[str, object] | None = None,
        task_id: str | None = None,
        *,
        queue: str | None = None,
        routing_key: str | None = None,
        **options: object,
    ) -> AsyncResult[_R_co]: ...
    def update_state(
        self,
        task_id: str | None = None,
        state: str | None = None,
        meta: Mapping[str, object] | None = None,
        **kwargs: object,
    ) -> None: ...
    def push_request(self, *args: object, **kwargs: object) -> None: ...
    def pop_request(self) -> None: ...
