from __future__ import annotations

from typing import TYPE_CHECKING, Self
from types import SimpleNamespace

from . import cache  # ensure cache setup on import
from .ports import (
    ChatModelOptions,
    LLMJsonValue,
    LLMProviderPort,
    resolve_llm_provider,
)
from ...settings.config import settings

_cache = cache

if TYPE_CHECKING:
    from .ports import ChatModel, EmbeddingModel


def _provider() -> LLMProviderPort:
    return resolve_llm_provider(settings.llm_provider or "")


def get_chat_model(
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    top_p: float | None = None,
    presence_penalty: float | None = None,
    frequency_penalty: float | None = None,
    **kwargs: LLMJsonValue,
) -> ChatModel:
    """按 composition 注册的 provider port 解析聊天模型。"""
    options = ChatModelOptions(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        presence_penalty=presence_penalty,
        frequency_penalty=frequency_penalty,
        extra=dict(kwargs),
    )
    return _provider().get_chat_model(options)


def get_embeddings(model: str | None = None) -> EmbeddingModel:
    return _provider().get_embeddings(model=model)


def get_local_fallback_chat(
    model: str | None = None,
    temperature: float = 0.0,
    **kwargs: LLMJsonValue,
) -> _LightChat:
    """返回轻量本地兜底 Chat 对象。

    - 具备 `.invoke(prompt) -> SimpleNamespace(content=...)`
    - 具备 `.with_retry() -> self`
    - 不参与 chains 组合，业务可直接按需调用
    """
    inner = _provider().get_chat_model(
        ChatModelOptions(
            model=model,
            temperature=temperature,
            extra=dict(kwargs),
        )
    )

    return _LightChat(inner)


class _LightChat:
    def __init__(self, chat: ChatModel):
        self._chat = chat

    def with_retry(self) -> Self:
        return self

    def invoke(self, prompt: str) -> SimpleNamespace:
        resp = self._chat.invoke(prompt)
        content: object = resp.content
        return SimpleNamespace(content=content)
