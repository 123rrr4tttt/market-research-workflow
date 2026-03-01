import logging

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, declarative_base, declarative_mixin
from sqlalchemy import BigInteger, Column
import os

from ..settings.config import settings
from ..services.projects.context import current_project_schema, project_schema_name


def _get_connect_args():
    """根据数据库类型返回连接参数"""
    if "postgresql" in settings.database_url:
        # PostgreSQL连接参数
        connect_args = {
            "connect_timeout": 2,  # 连接超时2秒
            "application_name": "lottery_intel",
        }
        # 如果是本地开发环境，可以添加更多优化参数
        if "localhost" in settings.database_url or "127.0.0.1" in settings.database_url:
            connect_args.update({
                "connect_timeout": 2,
                # 本地开发可以禁用SSL
                "sslmode": "prefer",
            })
        return connect_args
    return {}


def _get_pool_config():
    """根据环境返回连接池配置"""
    # 本地开发环境：更小的连接池，更快的超时，避免卡住
    if "localhost" in settings.database_url or "127.0.0.1" in settings.database_url:
        return {
            "pool_size": 2,  # 本地开发用小连接池
            "max_overflow": 0,  # 不允许溢出，避免连接堆积
            "pool_timeout": 1,  # 1秒快速超时，快速失败
            "pool_pre_ping": True,  # 连接前ping检查，快速发现失效连接
            "pool_recycle": 180,  # 3分钟回收连接，本地开发更频繁回收
            "echo": False,  # 本地开发可以设为True查看SQL
            "pool_reset_on_return": "commit",  # 返回连接池时重置状态
        }
    # Docker/生产环境：更大的连接池
    return {
        "pool_size": 10,
        "max_overflow": 5,
        "pool_timeout": 5,
        "pool_pre_ping": True,
        "pool_recycle": 3600,
        "echo": False,
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


@event.listens_for(SessionLocal, "after_begin")
def _set_project_schema(session, transaction, connection):  # noqa: ANN001
    """Route all ORM operations to current project schema."""
    schema = current_project_schema()
    if not schema:
        return
    # Use schema-only search path to prevent accidental fallback to public tenant tables.
    connection.execute(text(f'SET search_path TO "{schema}"'))

Base = declarative_base()


@declarative_mixin
class BigIDMixin:
    """统一的主键定义，使用BigInteger以提升容量，并保持自增语义。"""

    id = Column(BigInteger, primary_key=True, autoincrement=True)


def get_db():
    """Yield a SQLAlchemy session; FastAPI dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

