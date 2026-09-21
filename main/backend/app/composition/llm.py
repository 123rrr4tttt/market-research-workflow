"""Composition root for LLM provider adapters."""

from __future__ import annotations

from typing import Any

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.services.llm.adapters import LangChainProviderAdapter
from app.services.llm.ports import (
    ChatModelOptions,
    LLMProviderPort,
    register_llm_provider,
)
from app.settings.config import settings


class LiteLLMProviderAdapter(LLMProviderPort):
    def get_chat_model(self, options: ChatModelOptions) -> Any:
        extra = {
            key: value
            for key, value in (options.extra or {}).items()
            if key
            not in {
                "codex_cli_timeout_seconds",
                "codex_cli_reasoning_effort",
                "timeout_seconds",
            }
        }
        model_params: dict[str, Any] = {
            "temperature": (
                options.temperature if options.temperature is not None else 0.2
            )
        }
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
        return ChatOpenAI(
            model=options.model or "gpt-4o-mini",
            base_url=getattr(settings, "litellm_api_base", None) or None,
            api_key=getattr(settings, "litellm_api_key", "") or "",
            **model_params,
        )

    def get_embeddings(self, model: str | None = None) -> Any:
        return OpenAIEmbeddings(
            model=model or settings.embedding_model,
            base_url=getattr(settings, "litellm_api_base", None) or None,
            api_key=getattr(settings, "litellm_api_key", "") or "",
        )


def configure_llm_providers() -> None:
    register_llm_provider(
        ("openai", "azure", "ollama"),
        LangChainProviderAdapter(),
    )
    register_llm_provider(("litellm",), LiteLLMProviderAdapter())
