from typing import Any, Optional, Dict
from types import SimpleNamespace

from . import cache  # noqa: F401  # ensure cache setup on import
from .ports import ChatModelOptions, resolve_llm_provider
from ...settings.config import settings


def _provider() -> Any:
    return resolve_llm_provider(settings.llm_provider or "")


def get_chat_model(
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    top_p: Optional[float] = None,
    presence_penalty: Optional[float] = None,
    frequency_penalty: Optional[float] = None,
    **kwargs: Any,
):
    """按 composition 注册的 provider port 解析聊天模型。"""
    options = ChatModelOptions(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        presence_penalty=presence_penalty,
        frequency_penalty=frequency_penalty,
        extra=kwargs or {},
    )
    return _provider().get_chat_model(options)


def get_embeddings(model: Optional[str] = None):
    return _provider().get_embeddings(model=model)


def get_local_fallback_chat(
    model: Optional[str] = None,
    temperature: float = 0.0,
    **kwargs: Any,
):
    """返回轻量本地兜底 Chat 对象。

    - 具备 `.invoke(prompt) -> SimpleNamespace(content=...)`
    - 具备 `.with_retry() -> self`
    - 不参与 chains 组合，业务可直接按需调用
    """
    inner = _provider().get_chat_model(
        ChatModelOptions(
            model=model,
            temperature=temperature,
            extra=kwargs or {},
        )
    )

    class _LightChat:
        def __init__(self, chat: Any):
            self._chat = chat

        def with_retry(self):
            return self

        def invoke(self, prompt: Any):
            resp = self._chat.invoke(prompt)
            content = getattr(resp, "content", None)
            if content is None:
                if isinstance(resp, dict) and "content" in resp:
                    content = resp["content"]
                else:
                    content = str(resp)
            return SimpleNamespace(content=content)

    return _LightChat(inner)
