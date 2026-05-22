from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..contracts import ApiEnvelope, ErrorCode, error_response, success_response
from ..settings.config import reload_settings, settings
from ..services.settings_manager import load_env_settings, update_env_settings, ENV_KEY_MAPPING


router = APIRouter(prefix="/config", tags=["config"])


class RuntimeConfigData(BaseModel):
    env: str | None = None
    llm_provider: str | None = None
    embedding_model: str | None = None
    es_url: str | None = None
    active_project_key: str | None = None
    project_key_enforcement_mode: str | None = None
    project_schema_prefix: str | None = None


class EnvSettingsUpdateData(BaseModel):
    updated: dict[str, Any]


class ReloadConfigData(BaseModel):
    status: str


RuntimeConfigEnvelope = ApiEnvelope[RuntimeConfigData]
EnvSettingsEnvelope = ApiEnvelope[dict[str, Any]]
EnvSettingsUpdateEnvelope = ApiEnvelope[EnvSettingsUpdateData]
ReloadConfigEnvelope = ApiEnvelope[ReloadConfigData]


def _raise_invalid_input(message: str) -> None:
    raise HTTPException(
        status_code=400,
        detail=error_response(
            ErrorCode.INVALID_INPUT,
            message,
        ),
    )


def _raise_internal_error(message: str) -> None:
    raise HTTPException(
        status_code=500,
        detail=error_response(
            ErrorCode.INTERNAL_ERROR,
            message,
        ),
    )


@router.get("", response_model=RuntimeConfigEnvelope)
def get_config():
    """Return selected runtime configuration (safe subset)."""
    return success_response({
        "env": settings.env,
        "llm_provider": settings.llm_provider,
        "embedding_model": settings.embedding_model,
        "es_url": settings.es_url,
        # Expose tenant/config boundaries for observability (safe subset)
        "active_project_key": settings.active_project_key,
        "project_key_enforcement_mode": settings.project_key_enforcement_mode,
        "project_schema_prefix": settings.project_schema_prefix,
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
    EXTRACTION_MAX_PARALLEL: str | None = None
    TOPIC_WORKFLOW_MAX_PARALLEL: str | None = None
    LEGISCAN_API_KEY: str | None = None
    NEWS_API_KEY: str | None = None
    SERPAPI_KEY: str | None = None
    SERPSTACK_KEY: str | None = None
    SERPER_API_KEY: str | None = None
    GOOGLE_SEARCH_API_KEY: str | None = None
    GOOGLE_SEARCH_CSE_ID: str | None = None
    AZURE_SEARCH_ENDPOINT: str | None = None
    AZURE_SEARCH_KEY: str | None = None
    # Multi-tenant / config boundaries (optional, additive)
    ACTIVE_PROJECT_KEY: str | None = None
    PROJECT_KEY_ENFORCEMENT_MODE: str | None = None
    PROJECT_SCHEMA_PREFIX: str | None = None
    # Twitter/X API credentials
    TWITTER_API_KEY: str | None = None
    TWITTER_API_SECRET: str | None = None
    TWITTER_BEARER_TOKEN: str | None = None
    TWITTER_ACCESS_TOKEN: str | None = None
    TWITTER_ACCESS_TOKEN_SECRET: str | None = None


@router.get("/env", response_model=EnvSettingsEnvelope)
def get_env_settings():
    try:
        return success_response(load_env_settings())
    except Exception as exc:  # noqa: BLE001
        _raise_internal_error(str(exc) or "加载环境配置失败")


@router.post("/env", response_model=EnvSettingsUpdateEnvelope)
def update_env(payload: EnvSettingsPayload):
    payload_dict = {k: v for k, v in payload.dict().items() if v is not None}
    if not payload_dict:
        _raise_invalid_input("没有需要更新的字段")

    invalid = [key for key in payload_dict if key not in ENV_KEY_MAPPING]
    if invalid:
        _raise_invalid_input(f"不支持的字段: {', '.join(invalid)}")

    updated = update_env_settings(payload_dict)
    return success_response({"updated": updated})


@router.post("/reload", response_model=ReloadConfigEnvelope)
def reload_env_settings():
    try:
        reload_settings()
        return success_response({"status": "reloaded"})
    except Exception as exc:  # noqa: BLE001
        _raise_internal_error(str(exc) or "重载环境配置失败")
