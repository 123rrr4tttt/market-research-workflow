"""Single-connection transaction boundary for the successor runtime.

The UoW owns exactly one transaction boundary.  Public control-plane writes
and validated project-scope writes share the same connection and transaction;
repositories never open implicit sessions.  When a caller supplies a
connection that already owns an outer transaction, the UoW owns a savepoint
and deliberately leaves the caller's transaction and connection open.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import sessionmaker

from app.successor_runtime.runtime.ports import ProjectScopeRef

from .session import (
    PUBLIC_SEARCH_PATH,
    pin_public_search_path,
    validate_project_schema_identifier,
    validate_project_scope_ref,
)

_TABLE_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

T = TypeVar("T")


class UnitOfWorkError(RuntimeError):
    """Base class for runtime unit-of-work state errors."""


class UnitOfWorkClosed(UnitOfWorkError):
    """Raised when a committed/rolled-back UoW is used again."""


class UnitOfWorkAlreadyOpen(UnitOfWorkError):
    """Raised when a UoW is entered twice."""


@dataclass(frozen=True, slots=True)
class ConnectionHandle:
    """Explicit handle repositories must receive; no implicit session."""

    connection: Connection
    schema: str | None = None

    def __post_init__(self) -> None:
        if self.schema is not None and self.schema != PUBLIC_SEARCH_PATH:
            validate_project_schema_identifier(self.schema)

    @property
    def schema_name(self) -> str:
        return self.schema or PUBLIC_SEARCH_PATH

    def qualified(self, table: str) -> str:
        """Return a schema-qualified table identifier for SQL text."""

        if _TABLE_IDENTIFIER_PATTERN.fullmatch(table) is None:
            raise ValueError(f"invalid table identifier {table!r}")
        return f'"{self.schema_name}"."{table}"'

    def execute(self, statement: Any, parameters: Any = None, **kwargs: Any) -> Any:
        return self.connection.execute(statement, parameters, **kwargs)


class RuntimeUnitOfWork:
    """One connection, one transaction across public and project handles."""

    def __init__(
        self,
        *,
        engine: Engine | None = None,
        session_factory: sessionmaker | None = None,
        connection: Connection | None = None,
    ) -> None:
        sources = sum(
            value is not None for value in (engine, session_factory, connection)
        )
        if sources != 1:
            raise ValueError(
                "RuntimeUnitOfWork requires exactly one of engine, "
                "session_factory, or connection"
            )
        self._engine = engine
        self._session_factory = session_factory
        self._caller_connection = connection
        self._connection: Connection | None = None
        self._session: Any = None
        self._transaction: Any = None
        self._owns_connection = False
        self._owns_session = False
        self._terminal = False
        self._bound: list[Any] = []

    def __enter__(self) -> "RuntimeUnitOfWork":
        if self._terminal:
            raise UnitOfWorkClosed("unit of work is already closed")
        if self._transaction is not None or self._connection is not None:
            raise UnitOfWorkAlreadyOpen("unit of work is already open")
        try:
            if self._engine is not None:
                self._connection = self._engine.connect()
                self._owns_connection = True
                self._transaction = self._connection.begin()
            elif self._session_factory is not None:
                self._session = self._session_factory()
                self._owns_session = True
                # A call to Session.connection() autobegins a transaction.
                # Begin through the Session first and retain that owner instead
                # of attempting a second Connection.begin() on the same DBAPI
                # transaction.
                if self._session.in_transaction():
                    self._transaction = self._session.begin_nested()
                else:
                    self._transaction = self._session.begin()
                self._connection = self._session.connection()
            else:
                self._connection = self._caller_connection
                assert self._connection is not None
                # Never commit or roll back a transaction owned by the caller.
                # A savepoint gives the UoW its own terminal boundary while all
                # public/project writes still use the exact same connection.
                if self._connection.in_transaction():
                    self._transaction = self._connection.begin_nested()
                else:
                    self._transaction = self._connection.begin()
            assert self._connection is not None
            pin_public_search_path(self._connection)
        except BaseException:
            self._cleanup_failed_enter()
            raise
        return self

    @property
    def connection(self) -> Connection:
        self._require_open()
        assert self._connection is not None
        return self._connection

    @property
    def in_transaction(self) -> bool:
        return self._transaction is not None and not self._terminal

    @property
    def bound_repositories(self) -> tuple[Any, ...]:
        return tuple(self._bound)

    def public_handle(self) -> ConnectionHandle:
        return ConnectionHandle(
            connection=self.connection, schema=PUBLIC_SEARCH_PATH
        )

    def project_handle(self, scope: ProjectScopeRef) -> ConnectionHandle:
        validate_project_scope_ref(scope)
        return ConnectionHandle(
            connection=self.connection, schema=scope.resolved_schema
        )

    def bind_repository(
        self,
        factory: Callable[..., T],
        *,
        scope: ProjectScopeRef | None = None,
        **kwargs: Any,
    ) -> T:
        """Construct a repository with an explicit connection and handle."""

        handle = (
            self.project_handle(scope)
            if scope is not None
            else self.public_handle()
        )
        repository = factory(connection=self.connection, handle=handle, **kwargs)
        self._bound.append(repository)
        return repository

    def commit(self) -> None:
        self._require_open()
        assert self._transaction is not None
        try:
            self._transaction.commit()
        except BaseException:
            # Preserve the commit failure while still making a best-effort
            # rollback and releasing every resource owned by this UoW.
            try:
                self._rollback_active_transaction()
            except BaseException:
                pass
            try:
                self._finish()
            except BaseException:
                pass
            raise
        else:
            self._finish()

    def rollback(self) -> None:
        self._require_open()
        try:
            self._rollback_active_transaction()
        except BaseException:
            try:
                self._finish()
            except BaseException:
                pass
            raise
        else:
            self._finish()

    def __exit__(
        self,
        exc_type: Any,
        exc: Any,
        traceback: Any,
    ) -> None:
        if not self._terminal and self._transaction is not None:
            self.rollback()
        return None

    def _require_open(self) -> None:
        if self._terminal or self._transaction is None:
            raise UnitOfWorkClosed("unit of work is closed")

    def _finish(self) -> None:
        # Transaction completion must precede Session.close(); otherwise a
        # session-owned connection can be returned to the pool before the UoW
        # has made its commit/rollback decision.
        session = self._session
        connection = self._connection
        self._session = None
        self._connection = None
        self._transaction = None
        self._terminal = True
        if session is not None:
            session.close()
        if self._owns_connection and connection is not None:
            connection.close()

    def _rollback_active_transaction(self) -> None:
        if self._transaction is None:
            return
        if getattr(self._transaction, "is_active", True):
            self._transaction.rollback()

    def _cleanup_failed_enter(self) -> None:
        """Release partially acquired resources without masking enter errors."""

        try:
            self._rollback_active_transaction()
        except BaseException:
            pass
        try:
            if self._session is not None:
                self._session.close()
        except BaseException:
            pass
        try:
            if self._owns_connection and self._connection is not None:
                self._connection.close()
        except BaseException:
            pass
        self._session = None
        self._connection = None
        self._transaction = None
        self._terminal = True
