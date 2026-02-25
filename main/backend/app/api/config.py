from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..settings.config import settings
from ..services.settings_manager import load_env_settings, update_env_settings, ENV_KEY_MAPPING
from ..settings.config import reload_settings
from ..contracts import success_response


router = APIRouter(prefix="/config", tags=["config"])


@router.get("")
def get_config():
    """Return selected runtime configuration (safe subset)."""
    return success_response({
        "env": settings.env,
        "llm_provider": settings.llm_provider,
        "embedding_model": settings.embedding_model,
        "es_url": settings.es_url,
    })


class EnvSettingsPayload(BaseModel):
    DATABASE_URL: str | None = None
    ES_URL: str | None = None
    REDIS_URL: str | None = None
    LLM_PROVIDER: str | None = None
    OPENAI_API_KEY: str | None = None
    OPENAI_API_BASE: str | None = None
    AZURE_API_KEY: str | None = None
    AZURE_API_BASE: str | None = None
    AZURE_API_VERSION: str | None = None
    AZURE_CHAT_DEPLOYMENT: str | None = None
    AZURE_EMBEDDING_DEPLOYMENT: str | None = None
    OLLAMA_BASE_URL: str | None = None
    LEGISCAN_API_KEY: str | None = None
    NEWS_API_KEY: str | None = None
    SERPAPI_KEY: str | None = None
    SERPSTACK_KEY: str | None = None
    GOOGLE_SEARCH_API_KEY: str | None = None
    GOOGLE_SEARCH_CSE_ID: str | None = None
    AZURE_SEARCH_ENDPOINT: str | None = None
    AZURE_SEARCH_KEY: str | None = None


@router.get("/env")
def get_env_settings():
    return success_response(load_env_settings())


@router.post("/env")
def update_env(payload: EnvSettingsPayload):
    payload_dict = {k: v for k, v in payload.dict().items() if v is not None}
    if not payload_dict:
        raise HTTPException(status_code=400, detail="没有需要更新的字段")

    invalid = [key for key in payload_dict if key not in ENV_KEY_MAPPING]
    if invalid:
        raise HTTPException(status_code=400, detail=f"不支持的字段: {', '.join(invalid)}")

    updated = update_env_settings(payload_dict)
    return success_response({"updated": updated})


@router.post("/reload")
def reload_env_settings():
    reload_settings()
    return success_response({"status": "reloaded"})


