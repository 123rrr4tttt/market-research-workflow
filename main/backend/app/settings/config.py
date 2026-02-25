from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
import os


def _get_default_database_url() -> str:
    """根据环境自动选择数据库URL"""
    if os.getenv("DOCKER_ENV") == "true" or os.path.exists("/.dockerenv"):
        return "postgresql+psycopg2://postgres:postgres@db:5432/postgres"
    return "postgresql+psycopg2://postgres:postgres@localhost:5432/postgres"


def _get_default_es_url() -> str:
    """根据环境自动选择Elasticsearch URL"""
    if os.getenv("DOCKER_ENV") == "true" or os.path.exists("/.dockerenv"):
        return "http://es:9200"
    return "http://localhost:9200"


def _get_default_redis_url() -> str:
    """根据环境自动选择Redis URL"""
    if os.getenv("DOCKER_ENV") == "true" or os.path.exists("/.dockerenv"):
        return "redis://redis:6379/0"
    return "redis://localhost:6379/0"


class Settings(BaseSettings):
    env: str = Field(default="dev")

    # Database
    database_url: str = Field(default_factory=_get_default_database_url)
    # Neutral default project key for local bootstrap.
    active_project_key: str = Field(default="default")
    project_schema_prefix: str = Field(default="project_")

    # Elasticsearch / Redis
    es_url: str = Field(default_factory=_get_default_es_url)
    redis_url: str = Field(default_factory=_get_default_redis_url)

    # LLM providers
    llm_provider: str = Field(default="openai")  # openai | azure | ollama
    openai_api_key: Optional[str] = Field(default=None)
    openai_api_base: Optional[str] = Field(default=None)

    azure_api_key: Optional[str] = Field(default=None)
    azure_api_base: Optional[str] = Field(default=None)
    azure_api_version: Optional[str] = Field(default="2024-06-01")
    azure_chat_deployment: Optional[str] = Field(default=None)
    azure_embedding_deployment: Optional[str] = Field(default=None)

    ollama_base_url: Optional[str] = Field(default="http://localhost:11434")

    # External APIs
    legiscan_api_key: Optional[str] = Field(default=None)
    news_api_key: Optional[str] = Field(default=None)
    serpapi_key: Optional[str] = Field(default=None)
    serpstack_key: Optional[str] = Field(default=None)
    serper_api_key: Optional[str] = Field(default=None)
    google_search_api_key: Optional[str] = Field(default=None)
    google_search_cse_id: Optional[str] = Field(default=None)
    azure_search_endpoint: Optional[str] = Field(default="https://lotto.search.windows.net")
    azure_search_key: Optional[str] = Field(default=None)
    azure_search_index_name: Optional[str] = Field(default="index1761979777378")
    magayo_api_key: Optional[str] = Field(default=None)
    lotterydata_api_key: Optional[str] = Field(default=None)
    reddit_client_id: Optional[str] = Field(default=None)
    reddit_client_secret: Optional[str] = Field(default=None)
    reddit_user_agent: Optional[str] = Field(default=None)
    # Twitter/X API credentials
    twitter_api_key: Optional[str] = Field(default=None)
    twitter_api_secret: Optional[str] = Field(default=None)
    twitter_bearer_token: Optional[str] = Field(default=None)
    twitter_access_token: Optional[str] = Field(default=None)
    twitter_access_token_secret: Optional[str] = Field(default=None)
    rapidapi_key: Optional[str] = Field(default=None)

    # Embeddings
    embedding_model: str = Field(default="text-embedding-3-large")
    embedding_dim: int = Field(default=3072)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()


def reload_settings() -> Settings:
    global settings
    settings = Settings()
    return settings
