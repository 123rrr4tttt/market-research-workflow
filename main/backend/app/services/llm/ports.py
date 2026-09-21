from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Protocol


@dataclass
class ChatModelOptions:
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    extra: dict[str, Any] | None = None


class ChatPort(Protocol):
    def get_chat_model(self, options: ChatModelOptions) -> Any:
        ...


class EmbeddingPort(Protocol):
    def get_embeddings(self, model: Optional[str] = None) -> Any:
        ...


class PromptConfigPort(Protocol):
    def get_config(self, service_name: str) -> dict[str, Any] | None:
        ...


class LLMProviderPort(Protocol):
    """Runtime provider boundary shared by chat and embedding requests."""

    def get_chat_model(self, options: ChatModelOptions) -> Any:
        ...

    def get_embeddings(self, model: Optional[str] = None) -> Any:
        ...


LLM_PROVIDER_NOT_REGISTERED = "provider_not_registered"


class LLMProviderResolutionError(RuntimeError):
    """The composition root did not install the requested provider."""

    code = LLM_PROVIDER_NOT_REGISTERED


_LLM_PROVIDER_PORTS: dict[str, LLMProviderPort] = {}


def register_llm_provider(provider_names: tuple[str, ...], port: LLMProviderPort) -> None:
    for provider_name in provider_names:
        _LLM_PROVIDER_PORTS[provider_name.lower()] = port


def reset_llm_provider_registry() -> None:
    _LLM_PROVIDER_PORTS.clear()


def resolve_llm_provider(provider_name: str) -> LLMProviderPort:
    normalized = provider_name.strip().lower()
    port = _LLM_PROVIDER_PORTS.get(normalized)
    if port is None:
        # kit:boundary
        raise LLMProviderResolutionError(
            f"No LLM provider port registered for {normalized!r}"
        )
    return port
