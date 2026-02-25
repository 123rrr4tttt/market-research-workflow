from typing import Optional

from langchain_openai import (
    ChatOpenAI,
    OpenAIEmbeddings,
    AzureChatOpenAI,
    AzureOpenAIEmbeddings,
)

from ...settings.config import settings
from . import cache  # noqa: F401  # ensure cache setup on import


def _ensure(value: Optional[str], name: str) -> str:
    if not value:
        raise RuntimeError(f"缺少 {name} 配置")
    return value


def get_chat_model(model: Optional[str] = None):
    provider = settings.llm_provider.lower()

    if provider == "openai":
        return ChatOpenAI(
            model=model or "gpt-4o-mini",
            api_key=_ensure(settings.openai_api_key, "OPENAI_API_KEY"),
            base_url=settings.openai_api_base or None,
            temperature=0.2,
        )

    if provider == "azure":
        return AzureChatOpenAI(
            azure_endpoint=_ensure(settings.azure_api_base, "AZURE_API_BASE"),
            api_key=_ensure(settings.azure_api_key, "AZURE_API_KEY"),
            api_version=_ensure(settings.azure_api_version, "AZURE_API_VERSION"),
            deployment_name=_ensure(settings.azure_chat_deployment, "AZURE_CHAT_DEPLOYMENT"),
            temperature=0.2,
        )

    if provider == "ollama":
        from langchain_community.chat_models import ChatOllama

        return ChatOllama(
            base_url=settings.ollama_base_url or "http://localhost:11434",
            model=model or "llama3",
        )

    raise ValueError(f"未知的 llm_provider: {settings.llm_provider}")


def get_embeddings(model: Optional[str] = None):
    provider = settings.llm_provider.lower()

    if provider == "openai":
        return OpenAIEmbeddings(
            model=model or settings.embedding_model,
            api_key=_ensure(settings.openai_api_key, "OPENAI_API_KEY"),
            base_url=settings.openai_api_base or None,
        )

    if provider == "azure":
        return AzureOpenAIEmbeddings(
            azure_endpoint=_ensure(settings.azure_api_base, "AZURE_API_BASE"),
            api_key=_ensure(settings.azure_api_key, "AZURE_API_KEY"),
            api_version=_ensure(settings.azure_api_version, "AZURE_API_VERSION"),
            deployment=_ensure(settings.azure_embedding_deployment, "AZURE_EMBEDDING_DEPLOYMENT"),
        )

    if provider == "ollama":
        from langchain_community.embeddings import OllamaEmbeddings

        return OllamaEmbeddings(
            base_url=settings.ollama_base_url or "http://localhost:11434",
            model=model or "llama3",
        )

    raise ValueError(f"未知的 llm_provider: {settings.llm_provider}")


