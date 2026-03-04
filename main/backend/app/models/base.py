import logging

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, declarative_base, declarative_mixin
from sqlalchemy import BigInteger, Column
import os

from ..settings.config import settings
from ..services.projects.context import current_project_schema, project_schema_name


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
            "pool_reset_on_return": "commit",
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
    logging.getLogger("app.models.base").warning("db bootstrap skipped: %s", exc)


def _get_session_setup_sqls(schema):
    sqls: list[str] = []
    timeout_ms = max(0, int(settings.db_statement_timeout_ms or 0))
    if timeout_ms > 0 and "postgresql" in settings.database_url:
        sqls.append(f"SET LOCAL statement_timeout = {timeout_ms}")
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

