from __future__ import annotations

from pathlib import Path

from langchain.cache import SQLiteCache
from langchain.globals import set_llm_cache

from ...settings.config import settings


_CACHE_FILE = Path(__file__).resolve().parents[3] / "data" / "langchain-cache.db"


def setup_cache() -> None:
    """Configure LangChain cache using SQLite (disabled in production)."""
    if settings.env.lower() == "prod":
        return

    _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    set_llm_cache(SQLiteCache(database_path=str(_CACHE_FILE)))


setup_cache()


