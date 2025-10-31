from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    env: str = Field(default="dev")

    # Database
    database_url: str = Field(
        default=(
            "postgresql+psycopg2://postgres:postgres@db:5432/postgres"
        )
    )

    # Elasticsearch / Redis
    es_url: str = Field(default="http://es:9200")
    redis_url: str = Field(default="redis://localhost:6379/0")

    # LLM providers
    llm_provider: str = Field(default="openai")  # openai | azure | ollama
    openai_api_key: str | None = Field(default=None)
    openai_api_base: str | None = Field(default=None)

    azure_api_key: str | None = Field(default=None)
    azure_api_base: str | None = Field(default=None)
    azure_api_version: str | None = Field(default="2024-06-01")
    azure_chat_deployment: str | None = Field(default=None)
    azure_embedding_deployment: str | None = Field(default=None)

    ollama_base_url: str | None = Field(default="http://localhost:11434")

    # External APIs
    legiscan_api_key: str | None = Field(default=None)
    news_api_key: str | None = Field(default=None)
    serpapi_key: str | None = Field(default=None)
    magayo_api_key: str | None = Field(default=None)
    lotterydata_api_key: str | None = Field(default=None)
    reddit_client_id: str | None = Field(default=None)
    reddit_client_secret: str | None = Field(default=None)
    reddit_user_agent: str | None = Field(default=None)
    twitter_bearer_token: str | None = Field(default=None)
    rapidapi_key: str | None = Field(default=None)

    # Embeddings
    embedding_model: str = Field(default="text-embedding-3-large")
    embedding_dim: int = Field(default=3072)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()  # Singleton settings instance


def reload_settings() -> Settings:
    global settings
    settings = Settings()
    return settings


