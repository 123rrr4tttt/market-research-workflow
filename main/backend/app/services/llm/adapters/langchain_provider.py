from __future__ import annotations

from typing import Any, Dict, Optional

from langchain_openai import (
    AzureChatOpenAI,
    AzureOpenAIEmbeddings,
    ChatOpenAI,
    OpenAIEmbeddings,
)

from ....settings.config import settings
from ..ports import ChatModelOptions, ChatPort, EmbeddingPort


def _ensure(value: Optional[str], name: str) -> str:
    if not value:
        raise RuntimeError(f"缺少 {name} 配置")
    return value


class LangChainProviderAdapter(ChatPort, EmbeddingPort):
    def get_chat_model(self, options: ChatModelOptions) -> Any:
        provider = settings.llm_provider.lower()
        default_temperature = options.temperature if options.temperature is not None else 0.2
        model_params: Dict[str, Any] = {"temperature": default_temperature}
        if options.max_tokens is not None:
            model_params["max_tokens"] = options.max_tokens
        if options.top_p is not None:
            model_params["top_p"] = options.top_p
        if options.presence_penalty is not None:
            model_params["presence_penalty"] = options.presence_penalty
        if options.frequency_penalty is not None:
            model_params["frequency_penalty"] = options.frequency_penalty
        if options.extra:
            model_params.update(options.extra)

        if provider == "openai":
            return ChatOpenAI(
                model=options.model or "gpt-4o-mini",
                api_key=_ensure(settings.openai_api_key, "OPENAI_API_KEY"),
                base_url=settings.openai_api_base or None,
                **model_params,
            )
        if provider == "azure":
            return AzureChatOpenAI(
                azure_endpoint=_ensure(settings.azure_api_base, "AZURE_API_BASE"),
                api_key=_ensure(settings.azure_api_key, "AZURE_API_KEY"),
                api_version=_ensure(settings.azure_api_version, "AZURE_API_VERSION"),
                deployment_name=_ensure(settings.azure_chat_deployment, "AZURE_CHAT_DEPLOYMENT"),
                **model_params,
            )
        if provider == "ollama":
            from langchain_community.chat_models import ChatOllama

            params = {k: v for k, v in model_params.items() if k != "max_tokens"}
            return ChatOllama(
                base_url=settings.ollama_base_url or "http://localhost:11434",
                model=options.model or "llama3",
                **params,
            )
        raise ValueError(f"未知的 llm_provider: {settings.llm_provider}")

    def get_embeddings(self, model: Optional[str] = None) -> Any:
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
