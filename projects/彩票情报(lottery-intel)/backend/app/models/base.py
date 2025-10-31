from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from ..settings.config import settings


engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)

Base = declarative_base()


def get_db():
    """Yield a SQLAlchemy session; FastAPI dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


