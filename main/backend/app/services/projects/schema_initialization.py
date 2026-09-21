"""Explicit, serialized database-schema initialization boundaries."""

from __future__ import annotations

from collections.abc import Callable
import logging
from typing import Any, TypeVar

from sqlalchemy import text

from ...composition.production import is_production_environment
from ...models.base import classify_db_exception, engine
from ...settings.config import settings
from .context import project_schema_name


T = TypeVar("T")

_POSTGRESQL_SCHEMA_DDL_LOCK = text(
    "SELECT pg_advisory_xact_lock(hashtextextended(:lock_scope, 0))"
)
_LOCK_NAMESPACE = "mrw.schema-ddl.v1"


def schema_ddl_lock_scope(schema_name: str) -> str:
    """Return the stable PostgreSQL advisory-lock scope for one schema."""
    return f"{_LOCK_NAMESPACE}:{schema_name}"


def _dialect_name(database_engine: Any, connection: Any) -> str:
    dialect = getattr(connection, "dialect", None) or getattr(database_engine, "dialect", None)
    return str(getattr(dialect, "name", "") or "").strip().lower()


def run_serialized_schema_ddl(
    database_engine: Any,
    *,
    schema_name: str,
    operation: Callable[[Any], T],
    lock_timeout_ms: int | None = None,
) -> T:
    """Run schema DDL atomically and serialize it across PostgreSQL processes.

    PostgreSQL transaction advisory locks are released by commit or rollback. A
    failed initializer therefore publishes no partial DDL and a later caller can
    acquire the same lock and retry. Other dialects retain transaction atomicity
    but make no cross-process serialization claim.
    """
    with database_engine.begin() as connection:
        if _dialect_name(database_engine, connection) == "postgresql":
            resolved_lock_timeout_ms = max(
                0,
                int(
                    settings.db_lock_timeout_ms
                    if lock_timeout_ms is None
                    else lock_timeout_ms
                ),
            )
            if resolved_lock_timeout_ms:
                connection.execute(
                    text(f"SET LOCAL lock_timeout = {resolved_lock_timeout_ms}")
                )
            connection.execute(
                _POSTGRESQL_SCHEMA_DDL_LOCK,
                {"lock_scope": schema_ddl_lock_scope(schema_name)},
            )
        return operation(connection)


def initialize_default_project_schema(
    *,
    database_engine: Any | None = None,
    settings_obj: Any | None = None,
    logger_obj: logging.Logger | None = None,
    fail_closed: bool | None = None,
) -> bool:
    """Create the configured default schema at an explicit runtime boundary."""
    target_engine = engine if database_engine is None else database_engine
    target_settings = settings if settings_obj is None else settings_obj
    target_logger = logger_obj or logging.getLogger("app")
    schema_name = project_schema_name(target_settings.active_project_key)
    must_fail_closed = (
        is_production_environment(target_settings)
        if fail_closed is None
        else bool(fail_closed)
    )

    try:
        run_serialized_schema_ddl(
            target_engine,
            schema_name=schema_name,
            operation=lambda connection: connection.execute(
                text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"')
            ),
        )
    except Exception as exc:  # noqa: BLE001
        classification = classify_db_exception(exc)
        target_logger.warning(
            "db bootstrap skipped: %s "
            "(schema=%s production=%s category=%s retriable=%s sqlstate=%s exception_type=%s)",
            exc,
            schema_name,
            is_production_environment(target_settings),
            classification["category"],
            classification["retriable"],
            classification["sqlstate"],
            classification["exception_type"],
        )
        if must_fail_closed:
            raise
        return False
    return True


def initialize_cli_project_schema(
    *,
    project_key: str | None = None,
    name: str | None = None,
    settings_obj: Any | None = None,
    bootstrap: Callable[..., dict[str, str]] | None = None,
) -> dict[str, str]:
    """Fail-closed project-schema preflight for a database-using CLI."""
    target_settings = settings if settings_obj is None else settings_obj
    target_project_key = str(project_key or target_settings.active_project_key).strip()
    if bootstrap is None:
        from .bootstrap import ensure_project_schema_ready

        bootstrap = ensure_project_schema_ready
    return bootstrap(target_project_key, name=name)
