from __future__ import annotations

from pathlib import Path
from typing import Dict
import os

from dotenv import dotenv_values, set_key

from ..settings.config import settings, reload_settings


ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

ENV_KEY_MAPPING = {
    "DATABASE_URL": "database_url",
    "ES_URL": "es_url",
    "REDIS_URL": "redis_url",
    "LLM_PROVIDER": "llm_provider",
    "OPENAI_API_KEY": "openai_api_key",
    "OPENAI_API_BASE": "openai_api_base",
    "AZURE_API_KEY": "azure_api_key",
    "AZURE_API_BASE": "azure_api_base",
    "AZURE_API_VERSION": "azure_api_version",
    "AZURE_CHAT_DEPLOYMENT": "azure_chat_deployment",
    "AZURE_EMBEDDING_DEPLOYMENT": "azure_embedding_deployment",
    "OLLAMA_BASE_URL": "ollama_base_url",
    "SERPAPI_KEY": "serpapi_key",
    "SERPSTACK_KEY": "serpstack_key",
    "GOOGLE_SEARCH_API_KEY": "google_search_api_key",
    "GOOGLE_SEARCH_CSE_ID": "google_search_cse_id",
    "AZURE_SEARCH_ENDPOINT": "azure_search_endpoint",
    "AZURE_SEARCH_KEY": "azure_search_key",
}


def load_env_settings() -> Dict[str, str | None]:
    env_data = dotenv_values(str(ENV_FILE)) if ENV_FILE.exists() else {}
    results: Dict[str, str | None] = {}

    for key, attr in ENV_KEY_MAPPING.items():
        value = env_data.get(key)
        if value is None:
            value = os.getenv(key)
        if value is None and hasattr(settings, attr):
            attr_value = getattr(settings, attr)
            value = attr_value if attr_value is not None else None
        results[key] = value

    return results


def update_env_settings(updates: Dict[str, str | None]) -> Dict[str, str | None]:
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not ENV_FILE.exists():
        ENV_FILE.touch()

    for key, value in updates.items():
        if key not in ENV_KEY_MAPPING:
            continue
        set_key(str(ENV_FILE), key, value or "")
        if value is None or value == "":
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    reload_settings()
    return load_env_settings()


