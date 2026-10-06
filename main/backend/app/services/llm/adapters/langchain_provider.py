from __future__ import annotations

from typing import Any, Optional

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_openai import (
    AzureChatOpenAI,
    AzureOpenAIEmbeddings,
    ChatOpenAI,
    OpenAIEmbeddings,
)
from pydantic import SecretStr

from ....settings.config import settings
from ..codex_cli import CodexCliChatModel, codex_cli_llm_available
from ..ports import ChatModelOptions, ChatPort, EmbeddingPort, LLMJsonValue


def _ensure(value: Optional[str], name: str) -> str:
    if not value:
        raise RuntimeError(f"缺少 {name} 配置")
    return value


def _ensure_secret(value: str | None, name: str) -> SecretStr:
    return SecretStr(_ensure(value, name))


def _optional_json_int(value: LLMJsonValue, name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    return value


def _optional_json_str(value: LLMJsonValue, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return value


class LangChainProviderAdapter(ChatPort, EmbeddingPort):
    def get_chat_model(self, options: ChatModelOptions) -> BaseChatModel | CodexCliChatModel:
        provider = settings.llm_provider.lower()
        default_temperature = (
            options.temperature if options.temperature is not None else 0.2
        )
        source_extra = options.extra or {}
        codex_timeout_value = source_extra.get("codex_cli_timeout_seconds")
        if codex_timeout_value is None:
            codex_timeout_value = source_extra.get("timeout_seconds")
        codex_timeout = _optional_json_int(
            codex_timeout_value, "extra.codex_cli_timeout_seconds"
        )
        codex_reasoning_effort = _optional_json_str(
            source_extra.get("codex_cli_reasoning_effort"),
            "extra.codex_cli_reasoning_effort",
        )
        excluded_codex_keys = {
            "codex_cli_timeout_seconds",
            "timeout_seconds",
            "codex_cli_reasoning_effort",
        }
        extra = {
            key: value
            for key, value in source_extra.items()
            if key not in excluded_codex_keys
        }
        model_params: dict[str, Any] = {"temperature": default_temperature}
        if options.max_tokens is not None:
            model_params["max_tokens"] = options.max_tokens
        if options.top_p is not None:
            model_params["top_p"] = options.top_p
        if options.presence_penalty is not None:
            model_params["presence_penalty"] = options.presence_penalty
        if options.frequency_penalty is not None:
            model_params["frequency_penalty"] = options.frequency_penalty
        if extra:
            model_params.update(extra)

        if provider == "openai":
            prefer_codex = bool(getattr(settings, "codex_cli_llm_preferred", True))
            if (
                prefer_codex or not settings.openai_api_key
            ) and codex_cli_llm_available():
                return CodexCliChatModel(
                    model=options.model,
                    timeout_seconds=codex_timeout,
                    reasoning_effort=codex_reasoning_effort,
                )
            return ChatOpenAI(
                model=options.model or "gpt-4o-mini",
                api_key=_ensure_secret(settings.openai_api_key, "OPENAI_API_KEY"),
                base_url=settings.openai_api_base or None,
                **model_params,
            )
        if provider == "azure":
            return AzureChatOpenAI(
                azure_endpoint=_ensure(settings.azure_api_base, "AZURE_API_BASE"),
                api_key=_ensure_secret(settings.azure_api_key, "AZURE_API_KEY"),
                api_version=_ensure(settings.azure_api_version, "AZURE_API_VERSION"),
                azure_deployment=_ensure(
                    settings.azure_chat_deployment, "AZURE_CHAT_DEPLOYMENT"
                ),
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

    def get_embeddings(self, model: Optional[str] = None) -> Embeddings:
        provider = settings.llm_provider.lower()
        if provider == "openai":
            return OpenAIEmbeddings(
                model=model or settings.embedding_model,
                api_key=_ensure_secret(settings.openai_api_key, "OPENAI_API_KEY"),
                base_url=settings.openai_api_base or None,
            )
        if provider == "azure":
            return AzureOpenAIEmbeddings(
                azure_endpoint=_ensure(settings.azure_api_base, "AZURE_API_BASE"),
                api_key=_ensure_secret(settings.azure_api_key, "AZURE_API_KEY"),
                api_version=_ensure(settings.azure_api_version, "AZURE_API_VERSION"),
                azure_deployment=_ensure(
                    settings.azure_embedding_deployment, "AZURE_EMBEDDING_DEPLOYMENT"
                ),
            )
        if provider == "ollama":
            from langchain_community.embeddings import OllamaEmbeddings

            return OllamaEmbeddings(
                base_url=settings.ollama_base_url or "http://localhost:11434",
                model=model or "llama3",
            )
        raise ValueError(f"未知的 llm_provider: {settings.llm_provider}")
