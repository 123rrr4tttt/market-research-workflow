from __future__ import annotations

from pathlib import Path

from langchain_community.cache import SQLiteCache
from langchain_core.globals import set_llm_cache

from ...settings.config import settings


_CACHE_FILE = Path(__file__).resolve().parents[3] / "data" / "langchain-cache.db"


def setup_cache() -> None:
    """Configure LangChain cache using SQLite (disabled in production)."""
    if settings.env.lower() == "prod" or not settings.llm_cache_enabled:
        return

    cache_file = Path(settings.llm_cache_path) if settings.llm_cache_path else _CACHE_FILE
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    set_llm_cache(SQLiteCache(database_path=str(cache_file)))


setup_cache()
