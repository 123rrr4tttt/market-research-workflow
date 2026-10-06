from collections.abc import Callable
from typing import Generic, Literal, TypeVar, overload

_R_co = TypeVar("_R_co", covariant=True)

class AsyncResult(Generic[_R_co]):
    id: str
    parent: AsyncResult[object] | None

    def __init__(
        self,
        id: str,
        backend: object | None = None,
        task_name: str | None = None,
        app: object | None = None,
        parent: AsyncResult[object] | None = None,
    ) -> None: ...
    @property
    def status(self) -> str: ...
    @property
    def state(self) -> str: ...
    @property
    def result(self) -> _R_co | BaseException | None: ...
    @property
    def info(self) -> _R_co | BaseException | None: ...
    @overload
    def get(
        self,
        timeout: float | None = None,
        propagate: Literal[True] = True,
        interval: float = 0.5,
        no_ack: bool = True,
        follow_parents: bool = True,
        callback: Callable[[str, object], object] | None = None,
        on_message: Callable[[object], object] | None = None,
        on_interval: Callable[[], object] | None = None,
        disable_sync_subtasks: bool = True,
        **options: object,
    ) -> _R_co | None: ...
    @overload
    def get(
        self,
        timeout: float | None = None,
        propagate: Literal[False] = False,
        interval: float = 0.5,
        no_ack: bool = True,
        follow_parents: bool = True,
        callback: Callable[[str, object], object] | None = None,
        on_message: Callable[[object], object] | None = None,
        on_interval: Callable[[], object] | None = None,
        disable_sync_subtasks: bool = True,
        **options: object,
    ) -> _R_co | BaseException | None: ...
    @overload
    def get(
        self,
        timeout: float | None = None,
        propagate: bool = True,
        interval: float = 0.5,
        no_ack: bool = True,
        follow_parents: bool = True,
        callback: Callable[[str, object], object] | None = None,
        on_message: Callable[[object], object] | None = None,
        on_interval: Callable[[], object] | None = None,
        disable_sync_subtasks: bool = True,
        **options: object,
    ) -> _R_co | BaseException | None: ...
    def ready(self) -> bool: ...
    def successful(self) -> bool: ...
    def failed(self) -> bool: ...
    def revoke(
        self,
        connection: object | None = None,
        terminate: bool = False,
        signal: str | None = None,
        wait: bool = False,
        timeout: float | None = None,
    ) -> None: ...

class EagerResult(AsyncResult[_R_co]):
    def __init__(
        self,
        id: str,
        ret_value: _R_co | BaseException,
        state: str,
        traceback: object | None = None,
        name: str | None = None,
    ) -> None: ...
    @property
    def result(self) -> _R_co | BaseException: ...
    @overload
    def get(
        self,
        timeout: float | None = None,
        propagate: Literal[True] = True,
        interval: float = 0.5,
        no_ack: bool = True,
        follow_parents: bool = True,
        callback: Callable[[str, object], object] | None = None,
        on_message: Callable[[object], object] | None = None,
        on_interval: Callable[[], object] | None = None,
        disable_sync_subtasks: bool = True,
        **options: object,
    ) -> _R_co: ...
    @overload
    def get(
        self,
        timeout: float | None = None,
        propagate: Literal[False] = False,
        interval: float = 0.5,
        no_ack: bool = True,
        follow_parents: bool = True,
        callback: Callable[[str, object], object] | None = None,
        on_message: Callable[[object], object] | None = None,
        on_interval: Callable[[], object] | None = None,
        disable_sync_subtasks: bool = True,
        **options: object,
    ) -> _R_co | BaseException: ...
    @overload
    def get(
        self,
        timeout: float | None = None,
        propagate: bool = True,
        interval: float = 0.5,
        no_ack: bool = True,
        follow_parents: bool = True,
        callback: Callable[[str, object], object] | None = None,
        on_message: Callable[[object], object] | None = None,
        on_interval: Callable[[], object] | None = None,
        disable_sync_subtasks: bool = True,
        **options: object,
    ) -> _R_co | BaseException: ...
