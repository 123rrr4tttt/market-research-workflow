from __future__ import annotations

import logging
import random
import time
from typing import Any, Callable, TypeVar

from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import DBAPIError, DisconnectionError, OperationalError, TimeoutError as SATimeoutError
from sqlalchemy.orm import sessionmaker, declarative_base, declarative_mixin
from sqlalchemy import BigInteger, Column
import os

from ..settings.config import settings
from ..services.projects.context import current_project_schema, project_schema_name

logger = logging.getLogger("app.models.base")
T = TypeVar("T")

_RETRIABLE_SQLSTATES = {
    "40001",  # serialization_failure
    "40P01",  # deadlock_detected
    "55P03",  # lock_not_available
    "08000",  # connection_exception
    "08003",  # connection_does_not_exist
    "08006",  # connection_failure
    "57P01",  # admin_shutdown
}

_ISOLATION_TO_SQL = {
    "read committed": "READ COMMITTED",
    "repeatable read": "REPEATABLE READ",
    "serializable": "SERIALIZABLE",
    "read uncommitted": "READ UNCOMMITTED",
}


def _is_local_database() -> bool:
    return "localhost" in settings.database_url or "127.0.0.1" in settings.database_url


def _get_connect_args():
    """根据数据库类型返回连接参数"""
    if "postgresql" in settings.database_url:
        connect_args = {
            "connect_timeout": settings.db_connect_timeout_seconds,
            "application_name": "lottery_intel",
        }
        if _is_local_database():
            # 本地开发尽量保持可连通，避免 ssl 强制导致启动失败
            connect_args["sslmode"] = "prefer"
        return connect_args
    return {}


def _get_pool_config():
    """根据环境返回连接池配置。优先使用显式配置，再根据本地/容器环境给出保守兜底。"""
    if _is_local_database():
        return {
            "pool_size": max(1, settings.db_pool_size if settings.db_pool_size > 0 else 2),
            "max_overflow": max(0, settings.db_pool_max_overflow),
            "pool_timeout": max(1, settings.db_pool_timeout_seconds),
            "pool_pre_ping": settings.db_pool_pre_ping,
            "pool_recycle": max(30, settings.db_pool_recycle_seconds),
            "echo": settings.db_pool_echo,
            "pool_reset_on_return": "rollback",
        }
    return {
        "pool_size": max(2, settings.db_pool_size),
        "max_overflow": max(0, settings.db_pool_max_overflow),
        "pool_timeout": max(1, settings.db_pool_timeout_seconds),
        "pool_pre_ping": settings.db_pool_pre_ping,
        "pool_recycle": max(30, settings.db_pool_recycle_seconds),
        "echo": settings.db_pool_echo,
    }


pool_config = _get_pool_config()
engine = create_engine(
    settings.database_url,
    future=True,
    connect_args=_get_connect_args(),
    **pool_config
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)

# Ensure default project schema exists. If DB is temporarily unavailable in local dev,
# allow process startup and let health/deep checks report degraded state.
try:
    with engine.begin() as _conn:
        _conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{project_schema_name(settings.active_project_key)}"'))
except Exception as exc:  # noqa: BLE001
    logger.warning("db bootstrap skipped: %s", exc)


def _normalize_isolation_level(raw: str | None) -> str | None:
    level = (raw or "").strip().lower()
    return _ISOLATION_TO_SQL.get(level)


def _get_session_setup_sqls(schema):
    sqls: list[str] = []
    is_postgres = "postgresql" in settings.database_url
    timeout_ms = max(0, int(settings.db_statement_timeout_ms or 0))
    if timeout_ms > 0 and is_postgres:
        sqls.append(f"SET LOCAL statement_timeout = {timeout_ms}")
    lock_timeout_ms = max(0, int(settings.db_lock_timeout_ms or 0))
    if lock_timeout_ms > 0 and is_postgres:
        sqls.append(f"SET LOCAL lock_timeout = {lock_timeout_ms}")
    idle_tx_timeout_ms = max(0, int(settings.db_idle_in_transaction_timeout_ms or 0))
    if idle_tx_timeout_ms > 0 and is_postgres:
        sqls.append(f"SET LOCAL idle_in_transaction_session_timeout = {idle_tx_timeout_ms}")
    isolation_level = _normalize_isolation_level(settings.db_transaction_isolation_level)
    if isolation_level and is_postgres:
        sqls.append(f"SET LOCAL TRANSACTION ISOLATION LEVEL {isolation_level}")
    if schema:
        # Use schema-only search path to prevent accidental fallback to public tenant tables.
        sqls.append(f'SET search_path TO "{schema}"')
    return sqls


@event.listens_for(SessionLocal, "after_begin")
def _set_project_schema(session, transaction, connection):  # noqa: ANN001
    """Set transaction safety defaults and route ORM operations to current project schema."""
    schema = current_project_schema()
    for statement in _get_session_setup_sqls(schema):
        connection.execute(text(statement))


def _extract_sqlstate(exc: Exception) -> str | None:
    orig = getattr(exc, "orig", None)
    for attr in ("sqlstate", "pgcode"):
        value = getattr(orig, attr, None)
        if value:
            return str(value)
    return None


def classify_db_exception(exc: Exception) -> dict[str, Any]:
    sqlstate = _extract_sqlstate(exc)
    lower = str(exc).lower()
    is_connection_issue = (
        isinstance(exc, (DisconnectionError, SATimeoutError))
        or "connection" in lower
        or "timeout" in lower
    )
    retriable = (
        is_connection_issue
        or isinstance(exc, (OperationalError, DBAPIError))
        and (sqlstate in _RETRIABLE_SQLSTATES or "deadlock" in lower or "could not serialize" in lower)
    )
    category = "database" if isinstance(exc, (OperationalError, DBAPIError, SATimeoutError, DisconnectionError)) else "application"
    return {
        "category": category,
        "retriable": retriable,
        "sqlstate": sqlstate,
        "exception_type": exc.__class__.__name__,
    }


def run_with_session_retry(
    operation: Callable[[Any], T],
    *,
    session_factory: Callable[[], Any] = SessionLocal,
    max_attempts: int | None = None,
    base_backoff_ms: int | None = None,
    max_backoff_ms: int | None = None,
    log_context: dict[str, Any] | None = None,
) -> T:
    attempts = max(1, int(max_attempts or settings.db_transaction_retry_attempts or 1))
    base_backoff = max(1, int(base_backoff_ms or settings.db_transaction_retry_base_backoff_ms or 100))
    max_backoff = max(base_backoff, int(max_backoff_ms or settings.db_transaction_retry_max_backoff_ms or 1000))
    context = log_context or {}
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        with session_factory() as session:
            try:
                result = operation(session)
                session.commit()
                if attempt > 1:
                    logger.info("event=db_tx_succeeded after_retry=true attempts=%s context=%s", attempt, context)
                return result
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                session.rollback()
                error_details = classify_db_exception(exc)
                should_retry = bool(error_details["retriable"] and attempt < attempts)
                log_fn = logger.warning if should_retry else logger.error
                log_fn(
                    "event=db_tx_failed attempt=%s/%s retriable=%s exception_type=%s sqlstate=%s context=%s",
                    attempt,
                    attempts,
                    error_details["retriable"],
                    error_details["exception_type"],
                    error_details["sqlstate"],
                    context,
                )
                if not should_retry:
                    raise
                delay_ms = min(max_backoff, base_backoff * (2 ** (attempt - 1)))
                delay_ms += random.randint(0, max(5, delay_ms // 4))
                time.sleep(delay_ms / 1000)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("run_with_session_retry reached unexpected empty state")


Base = declarative_base()


@declarative_mixin
class BigIDMixin:
    """统一的主键定义，使用BigInteger以提升容量，并保持自增语义。"""

    id = Column(BigInteger, primary_key=True, autoincrement=True)


def get_db_pool_status() -> dict:
    """Expose SQLAlchemy pool state for health/observability endpoints."""
    pool = engine.pool
    status = {
        "pool_class": pool.__class__.__name__,
        "status": pool.status(),
    }
    for attr in ("size", "checkedin", "checkedout", "overflow"):
        fn = getattr(pool, attr, None)
        if callable(fn):
            try:
                status[attr] = fn()
            except Exception:  # noqa: BLE001
                continue
    return status


def get_db():
    """Yield a SQLAlchemy session; FastAPI dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
